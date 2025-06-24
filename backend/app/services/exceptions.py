"""
Custom exceptions for FD 2: Concurrency & Provider Safety
Defines provider-specific errors and circuit breaker exceptions.
"""

from typing import Optional


class LLMServiceError(Exception):
    """Base exception for LLM service errors"""
    pass


class ProviderDownError(LLMServiceError):
    """Raised when circuit breaker is OPEN for a provider"""
    
    def __init__(self, provider: str, message: Optional[str] = None):
        self.provider = provider
        super().__init__(message or f"Provider {provider} is currently down (circuit breaker OPEN)")


class RateLimitError(LLMServiceError):
    """Raised when provider returns rate limit error (HTTP 429)"""
    
    def __init__(self, provider: str, retry_after: Optional[int] = None):
        self.provider = provider
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded for provider {provider}")


class ProviderError(LLMServiceError):
    """General provider error (network, API, etc.)"""
    
    def __init__(self, provider: str, original_error: Exception):
        self.provider = provider
        self.original_error = original_error
        super().__init__(f"Provider {provider} error: {str(original_error)}")


class FatalError(LLMServiceError):
    """Fatal error that should not be retried (4xx user errors, etc.)"""
    pass


class GenerationError(LLMServiceError):
    """Base class for token generation errors"""
    pass


class UserAbortError(GenerationError):
    """User aborted the request"""
    pass 