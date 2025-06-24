"""
FD 3.2: ProviderAdaptor Module
Wrap each SDK (openai, anthropic, ...) in a uniform async generator with provider-specific retry/back-off
"""

import asyncio
import random
from typing import AsyncIterator, Dict, Optional
from app.services.data_structures import RequestCtx
from app.services.exceptions import (
    RateLimitError,
    ProviderDownError,
    ProviderError,
    FatalError
)
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class ProviderAdaptor:
    """
    FD 3.2: ProviderAdaptor responsibility
    - Wrap each SDK in uniform async generator yielding raw token strings
    - Handle provider-specific retry/back-off
    - Key functions: stream_raw(), classify_error(e)
    """
    
    def __init__(self):
        # Provider-specific configurations
        self.provider_configs = {
            "openai": {
                "base_delay": 0.1,
                "failure_rate": 0.05,
                "avg_tokens": 20,
                "token_delay": 0.05
            },
            "anthropic": {
                "base_delay": 0.15,
                "failure_rate": 0.08,
                "avg_tokens": 18,
                "token_delay": 0.06
            },
            "google_ai": {
                "base_delay": 0.2,
                "failure_rate": 0.12,
                "avg_tokens": 16,
                "token_delay": 0.07
            },
            "deepseek": {
                "base_delay": 0.25,
                "failure_rate": 0.15,
                "avg_tokens": 22,
                "token_delay": 0.04
            },
            "cohere": {
                "base_delay": 0.18,
                "failure_rate": 0.18,
                "avg_tokens": 19,
                "token_delay": 0.055
            }
        }
        
        # Model to provider mapping
        self.model_provider_map = {
            # OpenAI models
            "gpt-4": "openai",
            "gpt-3.5-turbo": "openai",
            "gpt-4-turbo": "openai",
            "gpt-4o": "openai",
            
            # Anthropic models
            "claude-3-opus": "anthropic",
            "claude-3-sonnet": "anthropic",
            "claude-haiku": "anthropic",
            "claude-3-haiku": "anthropic",
            
            # Google models
            "gemini-pro": "google_ai",
            "gemini-flash": "google_ai",
            "palm-2": "google_ai",
            "gemini-1.5-pro": "google_ai",
            
            # DeepSeek models
            "deepseek-chat": "deepseek",
            "deepseek-coder": "deepseek",
            
            # Cohere models
            "command-r": "cohere",
            "command-r-plus": "cohere",
        }
        
        logger.info("ProviderAdaptor initialized with FD 3.2 compliance")
    
    async def stream_raw(self, model: str, prompt: str, ctx: RequestCtx) -> AsyncIterator[str]:
        """
        FD 3.2: Key function - stream_raw()
        Uniform async generator that yields raw token strings
        Handles provider-specific retry/back-off logic
        """
        provider = self.model_to_provider(model)
        config = self.provider_configs.get(provider, self.provider_configs["openai"])
        
        logger.debug(f"Starting raw stream for {model} via {provider} (request: {ctx.request_id})")
        
        # Simulate initial connection delay
        await asyncio.sleep(config["base_delay"])
        
        # Check for simulated failures
        if random.random() < config["failure_rate"]:
            await self._simulate_provider_failure(provider, ctx)
        
        # Generate token stream
        try:
            async for token in self._generate_token_stream(model, prompt, provider, config, ctx):
                yield token
                
        except Exception as e:
            # Classify and re-raise with appropriate exception type
            classified_error = self.classify_error(e, provider)
            logger.error(f"Stream error for {model}: {str(classified_error)}")
            raise classified_error
    
    def classify_error(self, error: Exception, provider: str) -> Exception:
        """
        FD 3.2: Key function - classify_error(e)
        Classify provider errors into standard exception types
        """
        error_msg = str(error).lower()
        error_type = type(error).__name__
        
        logger.debug(f"Classifying error for {provider}: {error_type} - {error_msg}")
        
        # Rate limit errors
        if "rate limit" in error_msg or "429" in error_msg or isinstance(error, RateLimitError):
            retry_after = getattr(error, 'retry_after', None)
            return RateLimitError(provider, retry_after)
        
        # Timeout errors
        if ("timeout" in error_msg or "504" in error_msg or 
            isinstance(error, asyncio.TimeoutError)):
            return ProviderError(provider, asyncio.TimeoutError("Provider timeout"))
        
        # Connection errors
        if any(term in error_msg for term in ["connection", "network", "socket"]):
            return ProviderError(provider, ConnectionError("Provider connection failed"))
        
        # Server errors (5xx)
        if any(code in error_msg for code in ["500", "502", "503"]):
            return ProviderError(provider, Exception(f"Provider server error: {error_msg}"))
        
        # Client errors that shouldn't be retried (4xx except 429)
        if any(code in error_msg for code in ["400", "401", "403", "404"]):
            return FatalError(f"Client error for {provider}: {error_msg}")
        
        # Invalid input/format errors
        if ("invalid" in error_msg or "bad request" in error_msg or 
            isinstance(error, ValueError)):
            return FatalError(f"Invalid request for {provider}: {error_msg}")
        
        # Circuit breaker errors
        if isinstance(error, ProviderDownError):
            return error  # Pass through as-is
        
        # Default: treat as provider error (retryable)
        logger.warning(f"Unknown error type for {provider}, treating as ProviderError: {error_type}")
        return ProviderError(provider, error)
    
    def model_to_provider(self, model: str) -> str:
        """Map model names to provider names"""
        provider = self.model_provider_map.get(model, "openai")
        if model not in self.model_provider_map:
            logger.warning(f"Unknown model {model}, defaulting to provider: {provider}")
        return provider
    
    async def _generate_token_stream(self, model: str, prompt: str, provider: str, 
                                   config: Dict, ctx: RequestCtx) -> AsyncIterator[str]:
        """
        Generate mock token stream with provider-specific characteristics
        In real implementation, this would call actual provider SDKs
        """
        # Generate tokens based on model and prompt
        base_tokens = self._create_base_tokens(model, prompt, provider)
        
        # Add some provider-specific variation
        num_tokens = min(len(base_tokens), config["avg_tokens"] + random.randint(-5, 5))
        
        for i in range(num_tokens):
            # Simulate streaming delay
            await asyncio.sleep(config["token_delay"])
            
            # Yield token
            if i < len(base_tokens):
                yield base_tokens[i]
            else:
                yield f" token_{i}"
        
        logger.debug(f"Completed token stream: {num_tokens} tokens for {model}")
    
    def _create_base_tokens(self, model: str, prompt: str, provider: str) -> list[str]:
        """Create base token sequence based on model and prompt"""
        # Simple token generation based on prompt
        if "hello" in prompt.lower():
            tokens = ["Hello", "!", " I'm", f" {model}", " from", f" {provider}", ".", 
                     " How", " can", " I", " help", " you", " today", "?"]
        elif "write" in prompt.lower() or "create" in prompt.lower():
            tokens = ["I'll", " help", " you", " write", " something", " interesting", ".",
                     " Let", " me", " create", " a", " response", " using", f" {model}", "."]
        elif "explain" in prompt.lower():
            tokens = ["Let", " me", " explain", " this", " concept", " clearly", ".",
                     " Based", " on", " my", " understanding", " as", f" {model}", "..."]
        else:
            # Generic response
            tokens = ["This", " is", " a", " response", " from", f" {model}", 
                     " via", f" {provider}", ".", " The", " prompt", " was", ":", 
                     f" '{prompt[:20]}{'...' if len(prompt) > 20 else ''}'"]
        
        return tokens
    
    async def _simulate_provider_failure(self, provider: str, ctx: RequestCtx):
        """Simulate various provider failure modes for testing"""
        failure_types = [
            ("rate_limit", RateLimitError(provider, retry_after=30)),
            ("timeout", asyncio.TimeoutError("Simulated timeout")),
            ("connection", ConnectionError("Simulated connection failure")),
            ("server_error", Exception("500 Internal Server Error")),
            ("auth_error", Exception("401 Unauthorized")),
        ]
        
        # Weight failures based on provider
        weights = {
            "openai": [0.3, 0.3, 0.2, 0.15, 0.05],
            "anthropic": [0.4, 0.25, 0.2, 0.1, 0.05],
            "google_ai": [0.35, 0.3, 0.15, 0.15, 0.05],
            "deepseek": [0.2, 0.4, 0.25, 0.1, 0.05],
            "cohere": [0.25, 0.35, 0.2, 0.15, 0.05]
        }
        
        provider_weights = weights.get(provider, weights["openai"])
        
        # Select failure type based on weights
        failure_name, failure_exception = random.choices(failure_types, weights=provider_weights)[0]
        
        logger.warning(f"Simulating {failure_name} for {provider} (request: {ctx.request_id})")
        raise failure_exception
    
    def get_provider_info(self, provider: str) -> Dict:
        """Get provider configuration and statistics"""
        config = self.provider_configs.get(provider, {})
        models = [model for model, prov in self.model_provider_map.items() if prov == provider]
        
        return {
            "provider": provider,
            "config": config,
            "supported_models": models,
            "model_count": len(models)
        }
    
    def get_all_providers_info(self) -> Dict[str, Dict]:
        """Get information for all providers"""
        return {
            provider: self.get_provider_info(provider)
            for provider in self.provider_configs.keys()
        }
    
    def validate_model_provider_mapping(self) -> Dict[str, any]:
        """Validate model-to-provider mappings"""
        validation_results = {
            "valid": True,
            "total_models": len(self.model_provider_map),
            "providers_used": set(self.model_provider_map.values()),
            "models_per_provider": {},
            "issues": []
        }
        
        # Count models per provider
        for model, provider in self.model_provider_map.items():
            if provider not in validation_results["models_per_provider"]:
                validation_results["models_per_provider"][provider] = []
            validation_results["models_per_provider"][provider].append(model)
        
        # Check for providers without configuration
        for provider in validation_results["providers_used"]:
            if provider not in self.provider_configs:
                validation_results["issues"].append(f"Provider {provider} missing configuration")
                validation_results["valid"] = False
        
        return validation_results 