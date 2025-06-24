"""
FD 2: Concurrency & Provider Safety Service
Main service implementing FD 2.2 public API with semaphores, circuit breakers, and retry logic.
"""

import asyncio
import random
from typing import AsyncIterator, Dict, Optional
from app.services.data_structures import RequestCtx, Token
from app.services.exceptions import (
    ProviderDownError, 
    RateLimitError,
    ProviderError,
    FatalError,
    GenerationError
)
from app.services.circuit_breaker import circuit_breaker_service
from app.services.provider_semaphore import provider_semaphore_service
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class ProviderAdaptor:
    """
    Mock provider adaptor for demonstration
    In a full implementation, this would wrap actual provider SDKs
    """
    
    @staticmethod
    def model_to_provider(model: str) -> str:
        """Map model names to provider names"""
        model_provider_map = {
            # OpenAI models
            "gpt-4": "openai",
            "gpt-3.5-turbo": "openai",
            "gpt-4-turbo": "openai",
            
            # Anthropic models
            "claude-3-opus": "anthropic",
            "claude-3-sonnet": "anthropic", 
            "claude-haiku": "anthropic",
            
            # Google models
            "gemini-pro": "google_ai",
            "gemini-flash": "google_ai",
            "palm-2": "google_ai",
            
            # DeepSeek models
            "deepseek-chat": "deepseek",
            "deepseek-coder": "deepseek",
            
            # Cohere models
            "command-r": "cohere",
            "command-r-plus": "cohere",
        }
        
        provider = model_provider_map.get(model, "openai")  # Default to openai
        if model not in model_provider_map:
            logger.warning(f"Unknown model {model}, defaulting to provider: {provider}")
        
        return provider
    
    @staticmethod
    async def stream_raw(model: str, prompt: str, ctx: RequestCtx) -> AsyncIterator[str]:
        """
        Mock streaming raw tokens from provider
        In real implementation, this would call actual provider SDKs
        """
        provider = ProviderAdaptor.model_to_provider(model)
        
        # Simulate different provider behaviors and failure modes
        await asyncio.sleep(0.1)  # Simulate initial latency
        
        # Simulate various error conditions for testing
        failure_rate = {
            "openai": 0.05,      # 5% failure rate
            "anthropic": 0.08,   # 8% failure rate
            "google_ai": 0.12,   # 12% failure rate
            "deepseek": 0.15,    # 15% failure rate
            "cohere": 0.18,      # 18% failure rate
        }.get(provider, 0.1)
        
        if random.random() < failure_rate:
            # Simulate different types of failures
            error_types = [
                (asyncio.TimeoutError, "Request timeout"),
                (RateLimitError, f"Rate limit for {provider}"),
                (ConnectionError, "Connection failed"),
                (Exception, "Generic provider error")
            ]
            
            error_class, error_msg = random.choice(error_types)
            if error_class == RateLimitError:
                raise RateLimitError(provider, retry_after=60)
            elif error_class == asyncio.TimeoutError:
                raise asyncio.TimeoutError(error_msg)
            else:
                raise ProviderError(provider, Exception(error_msg))
        
        # Generate mock tokens
        tokens = [
            "The", " quick", " brown", " fox", " jumps", " over", " the", " lazy", " dog", ".",
            " This", " is", " a", " sample", " response", " from", f" {model}", " via", f" {provider}", "."
        ]
        
        for i, token in enumerate(tokens):
            # Simulate streaming delay
            await asyncio.sleep(0.05)
            yield token


class ConcurrencyAndProviderSafetyService:
    """
    FD 2: Main service implementing provider safety with semaphores and circuit breakers
    """
    
    def __init__(self):
        self.provider_adaptor = ProviderAdaptor()
    
    async def call_model(self, model: str, prompt: str, ctx: RequestCtx) -> AsyncIterator[str]:
        """
        FD 2.2: Public API - Yield raw token strings from provider respecting semaphores & CB
        FD 2.1: Implements retry envelope (max 3 retries per attempt)
        """
        provider = self.provider_adaptor.model_to_provider(model)
        
        logger.info(f"Calling model {model} via provider {provider} (request: {ctx.request_id})")
        
        max_retries = min(ctx.max_retries, 3)  # FD 2.1: at most 3 retries per attempt
        
        for attempt in range(max_retries + 1):  # 0-based, so +1 for initial attempt
            try:
                # FD 2.7: Check if circuit breaker is OPEN
                if circuit_breaker_service.is_open(provider):
                    raise ProviderDownError(provider)
                
                # FD 2.7: Acquire semaphore for concurrency control
                async with provider_semaphore_service.acquire_semaphore(provider):
                    logger.debug(f"Starting model call attempt {attempt + 1}/{max_retries + 1} "
                                f"for {model} (request: {ctx.request_id})")
                    
                    # Stream tokens from provider
                    token_count = 0
                    async for token in self.provider_adaptor.stream_raw(model, prompt, ctx):
                        token_count += 1
                        yield token
                    
                    # Success! Record for circuit breaker
                    circuit_breaker_service.record_success(provider)
                    logger.info(f"Successfully streamed {token_count} tokens from {model} "
                               f"(request: {ctx.request_id})")
                    return
                    
            except ProviderDownError:
                # Circuit breaker is OPEN, don't retry
                logger.error(f"Provider {provider} is down (circuit breaker OPEN)")
                raise
                
            except (asyncio.TimeoutError, RateLimitError, ProviderError) as e:
                # Record failure for circuit breaker
                circuit_breaker_service.record_failure(provider, e)
                
                if attempt < max_retries:
                    # Calculate exponential backoff delay
                    delay = (1.5 ** attempt) + random.uniform(0, 1)
                    logger.warning(f"Attempt {attempt + 1} failed for {model}: {str(e)}. "
                                 f"Retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"All {max_retries + 1} attempts failed for {model}: {str(e)}")
                    raise
                    
            except (ValueError, FatalError) as e:
                # Don't retry user errors or fatal errors
                logger.error(f"Fatal error for {model}: {str(e)} (no retry)")
                raise
                
            except Exception as e:
                # Unknown error - record as failure and potentially retry
                circuit_breaker_service.record_failure(provider, e)
                
                if attempt < max_retries:
                    delay = (1.5 ** attempt) + random.uniform(0, 1)
                    logger.error(f"Unknown error for {model}: {str(e)}. Retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"All attempts failed for {model} with unknown error: {str(e)}")
                    raise GenerationError(f"Failed to generate tokens: {str(e)}")
    
    def get_provider_for_model(self, model: str) -> str:
        """Get the provider name for a given model"""
        return self.provider_adaptor.model_to_provider(model)
    
    async def get_provider_status(self) -> Dict[str, Dict[str, any]]:
        """Get comprehensive status for all providers"""
        status = {}
        
        for provider in ["openai", "anthropic", "google_ai", "deepseek", "cohere"]:
            # Get circuit breaker status
            cb_status = circuit_breaker_service.get_status(provider)
            
            # Get semaphore status  
            semaphore_status = provider_semaphore_service.get_semaphore_status(provider)
            
            status[provider] = {
                "circuit_breaker": {
                    "state": cb_status.state.value if cb_status else "unknown",
                    "failure_count": cb_status.failure_count if cb_status else 0,
                    "last_failure": cb_status.last_failure_time.isoformat() if cb_status and cb_status.last_failure_time else None,
                    "last_success": cb_status.last_success_time.isoformat() if cb_status and cb_status.last_success_time else None,
                },
                "semaphore": semaphore_status,
                "config": {
                    "max_concurrency": semaphore_status.get("max_concurrency", 0),
                    "failure_threshold": 3,
                    "timeout_seconds": 30
                }
            }
        
        return status
    
    async def reset_provider(self, provider: str):
        """Reset circuit breaker for a provider (admin function)"""
        circuit_breaker_service.reset_circuit_breaker(provider)
        logger.info(f"Reset provider {provider}")
    
    async def probe_provider(self, provider: str) -> bool:
        """
        FD 2.5: Manually trigger provider probe
        """
        return await circuit_breaker_service.probe_provider(provider)


# Global instance
concurrency_safety_service = ConcurrencyAndProviderSafetyService() 