"""
FD 3: Token Generation Pipeline Service
Main service implementing FD 3.1 public interface and integrating all FD 3.2 modules.
"""

import asyncio
from typing import AsyncIterator, Dict, List, Optional
from app.services.data_structures import RequestCtx, Token
from app.services.token_builder import TokenBuilder
from app.services.buffer_manager import BufferManager
from app.services.error_router import ErrorRouter
from app.services.provider_adaptor import ProviderAdaptor
from app.services.exceptions import (
    GenerationError,
    ProviderError,
    UserAbortError,
    FatalError,
    ProviderDownError
)
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class TokenGenerationPipeline:
    """
    FD 3: Token Generation Pipeline
    Implements FD 3.1 public interface and integrates all FD 3.2 modules:
    - ProviderAdaptor: Wrap SDKs in uniform async generator
    - TokenBuilder: Convert raw token text → Token dataclass
    - BufferManager: Buffer tokens with flush triggers
    - ErrorRouter: Map exceptions to retry/fallback decisions
    """
    
    def __init__(self, 
                 batch_size: int = 16,
                 flush_timeout_seconds: float = 1.0,
                 persistence_service=None):
        
        # FD 3.2: Initialize all modules
        self.provider_adaptor = ProviderAdaptor()
        self.error_router = ErrorRouter()
        
        # FD 4: Real persistence service integration
        self.persistence_service = persistence_service
        
        # BufferManager will be created per request to maintain isolation
        self.buffer_config = {
            "batch_size": batch_size,
            "flush_timeout_seconds": flush_timeout_seconds
        }
        
        # Pipeline statistics
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.total_tokens_generated = 0
        
        logger.info(f"TokenGenerationPipeline initialized with batch_size={batch_size}, "
                   f"flush_timeout={flush_timeout_seconds}s")
    
    async def generate_tokens(self, model: str, prompt: str, ctx: RequestCtx) -> AsyncIterator[Token]:
        """
        FD 3.1: Public Interface
        await generate_tokens(model: str, prompt: str, ctx: RequestCtx) -> AsyncIterator[Token]
        
        - Stream contract: yields Token(model_id, text, index) strictly monotonically increasing index
        - Back-pressure: stops yielding when BufferManager is flushing
        - Raises GenerationError subclasses (ProviderError, UserAbort, FatalError)
        """
        self.total_requests += 1
        request_start_time = asyncio.get_event_loop().time()
        
        logger.info(f"Starting token generation for {model} (request: {ctx.request_id})")
        
        # FD 3.2: Initialize modules for this request
        token_builder = TokenBuilder(ctx.request_id, ctx.attempt_seq, model)
        
        # FD 4: Create BufferManager with real persistence service
        buffer_manager = BufferManager(
            batch_size=self.buffer_config["batch_size"],
            flush_timeout_seconds=self.buffer_config["flush_timeout_seconds"],
            persistence_service=self.persistence_service
        )
        
        try:
            # FD 3.6: Main pipeline logic
            token_count = 0
            
            # Integration with FD 2: Use provider adaptor with concurrency safety
            async for raw_token in self.provider_adaptor.stream_raw(model, prompt, ctx):
                try:
                    # FD 3.2: TokenBuilder - convert raw token to Token dataclass
                    token = token_builder.build(raw_token)
                    
                    # FD 3.4: Back-pressure - wait if buffer is flushing
                    await buffer_manager.wait_ready()
                    
                    # FD 3.2: BufferManager - add token to buffer
                    await buffer_manager.add(token)
                    
                    # Trigger flush if needed
                    if buffer_manager.flush_needed():
                        logger.debug(f"Triggering buffer flush (request: {ctx.request_id})")
                        await buffer_manager.drain()
                    
                    # FD 3.1: Yield token to caller
                    yield token
                    token_count += 1
                    
                except Exception as e:
                    logger.error(f"Error processing token {token_count}: {str(e)}")
                    # Handle token-level errors
                    error_result = await self.error_router.handle_error(e, ctx)
                    
                    if self.error_router.should_abort_request(error_result):
                        raise GenerationError(f"Token processing aborted: {error_result['reason']}")
                    # Continue with next token for non-fatal errors
            
            # Final flush of any remaining tokens
            await buffer_manager.force_flush()
            
            # Update statistics
            self.successful_requests += 1
            self.total_tokens_generated += token_count
            
            elapsed_time = asyncio.get_event_loop().time() - request_start_time
            logger.info(f"Token generation completed: {token_count} tokens in {elapsed_time:.2f}s "
                       f"(request: {ctx.request_id})")
            
        except ProviderDownError as e:
            # FD 3.5: ProviderDown - mark attempt failed → invoke fallback
            logger.error(f"Provider down during generation: {str(e)}")
            await self._handle_provider_down_error(e, ctx, buffer_manager)
            raise
            
        except (FatalError, ValueError) as e:
            # FD 3.5: FatalError - abort request, propagate up
            logger.error(f"Fatal error during generation: {str(e)}")
            await self._handle_fatal_error(e, ctx, buffer_manager)
            raise
            
        except Exception as e:
            # Handle unexpected errors
            logger.error(f"Unexpected error during generation: {str(e)}")
            error_result = await self.error_router.handle_error(e, ctx)
            
            if self.error_router.should_abort_request(error_result):
                await self._handle_fatal_error(e, ctx, buffer_manager)
                raise GenerationError(f"Generation failed: {error_result['reason']}")
            else:
                # This shouldn't happen in normal flow, but handle gracefully
                await buffer_manager.cleanup()
                raise
        
        finally:
            # Cleanup
            await buffer_manager.cleanup()
    
    async def _handle_provider_down_error(self, error: Exception, ctx: RequestCtx, 
                                        buffer_manager: BufferManager):
        """Handle provider down errors with proper cleanup"""
        self.failed_requests += 1
        
        # Force flush any buffered tokens before failing
        try:
            await buffer_manager.force_flush()
            logger.info("Flushed buffered tokens before provider down failure")
        except Exception as e:
            logger.error(f"Failed to flush tokens during provider down: {str(e)}")
    
    async def _handle_fatal_error(self, error: Exception, ctx: RequestCtx,
                                buffer_manager: BufferManager):
        """Handle fatal errors with proper cleanup"""
        self.failed_requests += 1
        
        # Force flush any buffered tokens before failing
        try:
            await buffer_manager.force_flush()
            logger.info("Flushed buffered tokens before fatal error")
        except Exception as e:
            logger.error(f"Failed to flush tokens during fatal error: {str(e)}")
    
    async def simulate_generation_with_retries(self, model: str, prompt: str, 
                                             ctx: RequestCtx, max_attempts: int = 3) -> AsyncIterator[Token]:
        """
        Enhanced generation with FD 3.5 error handling and retry logic
        Integrates with FD 2 circuit breakers and FD 5 fallback
        """
        for attempt in range(max_attempts):
            try:
                # Update context for current attempt
                ctx.attempt_seq = attempt + 1
                
                logger.info(f"Generation attempt {attempt + 1}/{max_attempts} for {model}")
                
                async for token in self.generate_tokens(model, prompt, ctx):
                    yield token
                
                # Success - exit retry loop
                return
                
            except (ProviderDownError, ProviderError) as e:
                error_result = await self.error_router.handle_error(e, ctx)
                
                if self.error_router.should_retry_with_backoff(error_result):
                    if attempt < max_attempts - 1:  # Not the last attempt
                        delay = self.error_router.get_retry_delay(error_result)
                        logger.warning(f"Retrying after {delay:.1f}s due to: {error_result['reason']}")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        logger.error(f"Max retry attempts reached, failing")
                        raise
                elif self.error_router.should_invoke_fallback(error_result):
                    # Would integrate with FD 5 fallback service here
                    logger.error(f"Fallback needed: {error_result['reason']}")
                    raise
                else:
                    # Abort immediately
                    raise
            
            except FatalError:
                # Don't retry fatal errors
                raise
    
    def get_pipeline_status(self) -> Dict:
        """Get comprehensive pipeline status for monitoring"""
        return {
            "statistics": {
                "total_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "success_rate": self.successful_requests / max(self.total_requests, 1) * 100,
                "total_tokens_generated": self.total_tokens_generated
            },
            "config": self.buffer_config,
            "modules": {
                "provider_adaptor": self.provider_adaptor.get_all_providers_info(),
                "error_router": self.error_router.get_error_summary(),
            },
            "persistence": {
                "enabled": self.persistence_service is not None,
                "service_type": "FD4_PersistenceService" if self.persistence_service else "None"
            }
        }
    
    def reset_statistics(self):
        """Reset pipeline statistics"""
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.total_tokens_generated = 0
        self.error_router.reset_statistics()
        
        # FD 4: Reset persistence service statistics if available
        if self.persistence_service and hasattr(self.persistence_service, 'reset_statistics'):
            self.persistence_service.reset_statistics()
        
        logger.info("Pipeline statistics reset")
    
    async def validate_pipeline_components(self) -> Dict:
        """Validate all pipeline components"""
        validation_results = {
            "valid": True,
            "issues": [],
            "component_status": {}
        }
        
        # Validate ProviderAdaptor
        provider_validation = self.provider_adaptor.validate_model_provider_mapping()
        validation_results["component_status"]["provider_adaptor"] = provider_validation
        if not provider_validation["valid"]:
            validation_results["valid"] = False
            validation_results["issues"].extend(provider_validation["issues"])
        
        # Validate buffer configuration
        if self.buffer_config["batch_size"] <= 0:
            validation_results["valid"] = False
            validation_results["issues"].append("Invalid batch_size: must be > 0")
        
        if self.buffer_config["flush_timeout_seconds"] <= 0:
            validation_results["valid"] = False
            validation_results["issues"].append("Invalid flush_timeout_seconds: must be > 0")
        
        validation_results["component_status"]["buffer_config"] = {
            "batch_size": self.buffer_config["batch_size"],
            "flush_timeout_seconds": self.buffer_config["flush_timeout_seconds"]
        }
        
        return validation_results


# Global instance - will be configured with persistence service during app startup
token_generation_pipeline = TokenGenerationPipeline() 