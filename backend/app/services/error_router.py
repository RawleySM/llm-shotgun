"""
FD 3.5: ErrorRouter Module
Maps adaptor exceptions to retry / fallback decisions as specified in FSD.
"""

import asyncio
import random
from enum import Enum
from typing import Dict, Any, Optional
from app.services.data_structures import RequestCtx
from app.services.exceptions import (
    RateLimitError,
    ProviderDownError,
    ProviderError,
    FatalError,
    GenerationError
)
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class ErrorAction(Enum):
    """Actions that can be taken for different error types"""
    RETRY = "retry"                 # Retry with exponential backoff
    FALLBACK = "fallback"          # Mark attempt failed, invoke fallback
    ABORT = "abort"                # Abort request, propagate up
    CONTINUE = "continue"          # Continue processing (non-fatal)


class ErrorRouter:
    """
    FD 3.2: ErrorRouter responsibility
    Map adaptor exceptions to retry / fallback decisions
    Integrates with FD 2 (Circuit Breaker) and FD 5 (Fallback) services
    """
    
    def __init__(self):
        self.error_stats: Dict[str, Dict[str, int]] = {}
        self._initialize_error_stats()
        
        logger.info("ErrorRouter initialized")
    
    def _initialize_error_stats(self):
        """Initialize error statistics tracking"""
        error_types = ["RateLimit", "Timeout", "ProviderDown", "FatalError", "Unknown"]
        actions = [action.value for action in ErrorAction]
        
        self.error_stats = {
            error_type: {action: 0 for action in actions}
            for error_type in error_types
        }
    
    async def handle_error(self, error: Exception, ctx: RequestCtx) -> Dict[str, Any]:
        """
        FD 3.2: Key function - handle_error(e, ctx)
        FD 3.5: Map exceptions to actions per error handling table
        
        Returns:
            Dict with action, retry_delay, should_circuit_break, etc.
        """
        error_type = type(error).__name__
        error_category = self._classify_error(error)
        
        logger.debug(f"Handling error {error_type}: {str(error)} (request: {ctx.request_id})")
        
        # FD 3.5: Apply error handling table logic
        if error_category == "RateLimit":
            result = await self._handle_rate_limit_error(error, ctx)
        elif error_category == "Timeout":
            result = await self._handle_timeout_error(error, ctx)
        elif error_category == "ProviderDown":
            result = await self._handle_provider_down_error(error, ctx)
        elif error_category == "FatalError":
            result = await self._handle_fatal_error(error, ctx)
        else:
            result = await self._handle_unknown_error(error, ctx)
        
        # Update statistics
        action = result.get("action", ErrorAction.ABORT.value)
        self.error_stats[error_category][action] += 1
        
        logger.info(f"Error routing result: {error_category} → {action} "
                   f"(request: {ctx.request_id})")
        
        return result
    
    async def _handle_rate_limit_error(self, error: Exception, ctx: RequestCtx) -> Dict[str, Any]:
        """
        FD 3.5: RateLimit - retry ≤3 with exponential 1.5^n, counts toward CB failures
        """
        retry_after = getattr(error, 'retry_after', None)
        
        if ctx.attempt_seq < ctx.max_retries:
            # Calculate exponential backoff: 1.5^n + jitter
            base_delay = (1.5 ** ctx.attempt_seq) + random.uniform(0, 1)
            
            # Respect provider's retry_after if provided
            if retry_after:
                delay = max(base_delay, retry_after)
            else:
                delay = base_delay
            
            return {
                "action": ErrorAction.RETRY.value,
                "retry_delay": delay,
                "should_circuit_break": True,  # Counts toward CB failures
                "reason": f"Rate limit exceeded, retrying in {delay:.1f}s",
                "attempt": ctx.attempt_seq,
                "max_retries": ctx.max_retries
            }
        else:
            # Max retries exceeded, treat as provider down
            return {
                "action": ErrorAction.FALLBACK.value,
                "should_circuit_break": True,
                "reason": f"Rate limit - max retries ({ctx.max_retries}) exceeded",
                "attempt": ctx.attempt_seq
            }
    
    async def _handle_timeout_error(self, error: Exception, ctx: RequestCtx) -> Dict[str, Any]:
        """
        FD 3.5: Timeout - same as RateLimit
        """
        if ctx.attempt_seq < ctx.max_retries:
            # Calculate exponential backoff: 1.5^n + jitter
            delay = (1.5 ** ctx.attempt_seq) + random.uniform(0, 1)
            
            return {
                "action": ErrorAction.RETRY.value,
                "retry_delay": delay,
                "should_circuit_break": True,  # Counts toward CB failures
                "reason": f"Timeout error, retrying in {delay:.1f}s",
                "attempt": ctx.attempt_seq,
                "max_retries": ctx.max_retries
            }
        else:
            # Max retries exceeded, treat as provider down
            return {
                "action": ErrorAction.FALLBACK.value,
                "should_circuit_break": True,
                "reason": f"Timeout - max retries ({ctx.max_retries}) exceeded",
                "attempt": ctx.attempt_seq
            }
    
    async def _handle_provider_down_error(self, error: Exception, ctx: RequestCtx) -> Dict[str, Any]:
        """
        FD 3.5: ProviderDown - mark attempt failed → invoke fallback, increments CB immediately
        """
        return {
            "action": ErrorAction.FALLBACK.value,
            "should_circuit_break": True,  # Increments CB immediately
            "reason": "Provider down - circuit breaker open",
            "provider": getattr(error, 'provider', 'unknown'),
            "immediate_fallback": True
        }
    
    async def _handle_fatal_error(self, error: Exception, ctx: RequestCtx) -> Dict[str, Any]:
        """
        FD 3.5: FatalError - abort request, propagate up
        """
        return {
            "action": ErrorAction.ABORT.value,
            "should_circuit_break": False,  # Don't count toward CB
            "reason": "Fatal error - corrupt request or 4xx from provider",
            "error_details": str(error)
        }
    
    async def _handle_unknown_error(self, error: Exception, ctx: RequestCtx) -> Dict[str, Any]:
        """
        Handle unknown errors - conservative approach
        """
        # For unknown errors, be conservative and treat as retryable
        if ctx.attempt_seq < ctx.max_retries:
            delay = (1.5 ** ctx.attempt_seq) + random.uniform(0, 1)
            
            return {
                "action": ErrorAction.RETRY.value,
                "retry_delay": delay,
                "should_circuit_break": True,  # Count toward CB to be safe
                "reason": f"Unknown error type, retrying in {delay:.1f}s",
                "error_type": type(error).__name__,
                "attempt": ctx.attempt_seq,
                "max_retries": ctx.max_retries
            }
        else:
            return {
                "action": ErrorAction.FALLBACK.value,
                "should_circuit_break": True,
                "reason": f"Unknown error - max retries ({ctx.max_retries}) exceeded",
                "error_type": type(error).__name__
            }
    
    def _classify_error(self, error: Exception) -> str:
        """
        Classify errors into FD 3.5 categories
        """
        if isinstance(error, RateLimitError):
            return "RateLimit"
        elif isinstance(error, (asyncio.TimeoutError, ProviderError)) and "timeout" in str(error).lower():
            return "Timeout"
        elif isinstance(error, ProviderDownError):
            return "ProviderDown"
        elif isinstance(error, (FatalError, ValueError)):
            return "FatalError"
        elif isinstance(error, ProviderError):
            # Analyze provider error details
            error_msg = str(error).lower()
            if "rate limit" in error_msg or "429" in error_msg:
                return "RateLimit"
            elif "timeout" in error_msg or "504" in error_msg:
                return "Timeout"
            elif any(term in error_msg for term in ["400", "401", "403", "404"]):
                return "FatalError"
            else:
                return "Timeout"  # Default for provider errors
        else:
            return "Unknown"
    
    def should_retry_with_backoff(self, error_result: Dict[str, Any]) -> bool:
        """Check if error result indicates retry with backoff"""
        return error_result.get("action") == ErrorAction.RETRY.value
    
    def should_invoke_fallback(self, error_result: Dict[str, Any]) -> bool:
        """Check if error result indicates fallback invocation"""
        return error_result.get("action") == ErrorAction.FALLBACK.value
    
    def should_abort_request(self, error_result: Dict[str, Any]) -> bool:
        """Check if error result indicates request abortion"""
        return error_result.get("action") == ErrorAction.ABORT.value
    
    def get_retry_delay(self, error_result: Dict[str, Any]) -> float:
        """Extract retry delay from error result"""
        return error_result.get("retry_delay", 0.0)
    
    def should_increment_circuit_breaker(self, error_result: Dict[str, Any]) -> bool:
        """Check if error should increment circuit breaker failure count"""
        return error_result.get("should_circuit_break", False)
    
    def get_error_statistics(self) -> Dict[str, Dict[str, int]]:
        """Get error handling statistics for monitoring"""
        return self.error_stats.copy()
    
    def reset_statistics(self):
        """Reset error statistics"""
        self._initialize_error_stats()
        logger.info("Error statistics reset")
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Get summary of error handling performance"""
        total_errors = sum(
            sum(actions.values()) for actions in self.error_stats.values()
        )
        
        if total_errors == 0:
            return {"total_errors": 0, "error_breakdown": {}}
        
        # Calculate error type percentages
        error_breakdown = {}
        for error_type, actions in self.error_stats.items():
            type_total = sum(actions.values())
            if type_total > 0:
                error_breakdown[error_type] = {
                    "count": type_total,
                    "percentage": (type_total / total_errors) * 100,
                    "actions": actions.copy()
                }
        
        return {
            "total_errors": total_errors,
            "error_breakdown": error_breakdown,
            "retry_rate": self._calculate_action_rate(ErrorAction.RETRY),
            "fallback_rate": self._calculate_action_rate(ErrorAction.FALLBACK),
            "abort_rate": self._calculate_action_rate(ErrorAction.ABORT)
        }
    
    def _calculate_action_rate(self, action: ErrorAction) -> float:
        """Calculate percentage rate for a specific action"""
        total_actions = sum(
            actions.get(action.value, 0) for actions in self.error_stats.values()
        )
        total_errors = sum(
            sum(actions.values()) for actions in self.error_stats.values()
        )
        
        if total_errors == 0:
            return 0.0
        
        return (total_actions / total_errors) * 100 