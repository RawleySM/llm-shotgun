"""
FD 5: Fallback Handling Service
Implements fallback queue management and jitter application for LLM provider failures.
"""

import asyncio
import random
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class FallbackService:
    """Service to handle LLM provider fallback logic with jitter"""
    
    def __init__(self):
        # FD 5.1: Predefined fallback queue as specified in FSD
        self.fallback_queue = [
            "gpt-3.5-turbo",
            "claude-haiku", 
            "gemini-flash",
            "deepseek-chat"
        ]
        
        # Jitter configuration (FD 5.2)
        self.jitter_min_seconds = 1
        self.jitter_max_seconds = 3
        
        # Tracking for analytics
        self.fallback_attempts = {}
        self.fallback_successes = {}
    
    def get_fallback_queue(self) -> List[str]:
        """
        FD 5.1: Get the predefined fallback queue
        Returns the ordered list of fallback models
        """
        return self.fallback_queue.copy()
    
    async def apply_jitter(self, attempt_number: int = 1) -> float:
        """
        FD 5.2: Apply jitter (1-3 seconds) before fallback call
        Returns the actual delay applied
        """
        # Calculate jitter with optional exponential backoff for multiple attempts
        base_jitter = random.uniform(self.jitter_min_seconds, self.jitter_max_seconds)
        
        # Add slight exponential backoff for repeated attempts (max 2x)
        backoff_multiplier = min(1 + (attempt_number - 1) * 0.2, 2.0)
        total_delay = base_jitter * backoff_multiplier
        
        logger.debug(f"Applying jitter: {total_delay:.2f}s (attempt {attempt_number})")
        
        await asyncio.sleep(total_delay)
        
        return total_delay
    
    async def get_next_fallback_model(
        self, 
        failed_model: str, 
        attempted_models: List[str]
    ) -> Optional[str]:
        """
        Get the next fallback model based on the fallback queue
        Excludes already attempted models
        """
        available_models = [
            model for model in self.fallback_queue 
            if model not in attempted_models and model != failed_model
        ]
        
        if not available_models:
            logger.warning("No more fallback models available")
            return None
        
        next_model = available_models[0]
        logger.info(f"Selected fallback model: {next_model} (after {failed_model} failed)")
        
        return next_model
    
    async def handle_provider_failure(
        self,
        failed_provider: str,
        failed_model: str,
        error: Exception,
        request_id: str,
        attempted_models: List[str]
    ) -> Dict[str, Any]:
        """
        Handle provider failure and determine fallback strategy
        Returns fallback decision and metadata
        """
        logger.warning(f"Provider failure: {failed_provider}/{failed_model} - {str(error)}")
        
        # Record the failure for analytics
        failure_key = f"{failed_provider}/{failed_model}"
        self.fallback_attempts[failure_key] = self.fallback_attempts.get(failure_key, 0) + 1
        
        # Get next fallback model
        next_model = await self.get_next_fallback_model(failed_model, attempted_models)
        
        if next_model is None:
            return {
                "should_fallback": False,
                "fallback_model": None,
                "reason": "No more fallback models available",
                "jitter_applied": 0
            }
        
        # Apply jitter before fallback
        attempt_number = len(attempted_models) + 1
        jitter_delay = await self.apply_jitter(attempt_number)
        
        return {
            "should_fallback": True,
            "fallback_model": next_model,
            "jitter_applied": jitter_delay,
            "attempt_number": attempt_number,
            "reason": f"Fallback after {failed_model} failure"
        }
    
    def record_fallback_success(self, model: str, provider: str):
        """Record successful fallback for analytics"""
        success_key = f"{provider}/{model}"
        self.fallback_successes[success_key] = self.fallback_successes.get(success_key, 0) + 1
        logger.info(f"Fallback success recorded for {success_key}")
    
    def get_fallback_statistics(self) -> Dict[str, Any]:
        """Get fallback statistics for monitoring"""
        total_attempts = sum(self.fallback_attempts.values())
        total_successes = sum(self.fallback_successes.values())
        
        return {
            "total_fallback_attempts": total_attempts,
            "total_fallback_successes": total_successes,
            "success_rate": (total_successes / total_attempts * 100) if total_attempts > 0 else 0,
            "fallback_queue": self.fallback_queue,
            "attempts_by_model": self.fallback_attempts.copy(),
            "successes_by_model": self.fallback_successes.copy()
        }
    
    def reset_statistics(self):
        """Reset fallback statistics (useful for testing or periodic resets)"""
        self.fallback_attempts.clear()
        self.fallback_successes.clear()
        logger.info("Fallback statistics reset")


# Global instance
fallback_service = FallbackService() 