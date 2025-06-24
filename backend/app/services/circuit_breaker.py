"""
FD 2.4 & 2.5: Circuit Breaker Service
Implements circuit breaker state machine and probe algorithm as specified in FSD.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, Set
from app.services.data_structures import (
    CircuitBreakerState, 
    CircuitBreakerStatus, 
    ProviderConfig,
    DEFAULT_PROVIDER_CONFIGS
)
from app.services.exceptions import ProviderDownError
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class CircuitBreakerService:
    """
    FD 2.4: Circuit Breaker State Machine Implementation
    CLOSED → OPEN → HALF-OPEN → CLOSED/OPEN
    """
    
    def __init__(self):
        self.circuit_breakers: Dict[str, CircuitBreakerStatus] = {}
        self.provider_configs: Dict[str, ProviderConfig] = DEFAULT_PROVIDER_CONFIGS.copy()
        self.probing_providers: Set[str] = set()  # Track ongoing probes
        
        # Initialize circuit breakers for all providers
        for provider in self.provider_configs:
            self.circuit_breakers[provider] = CircuitBreakerStatus(
                state=CircuitBreakerState.CLOSED,
                failure_count=0,
                last_failure_time=None,
                last_success_time=None,
                opened_at=None
            )
    
    def is_open(self, provider: str) -> bool:
        """
        FD 2.7: Check if circuit breaker is OPEN
        Returns True if provider should be rejected immediately
        """
        if provider not in self.circuit_breakers:
            logger.warning(f"Unknown provider {provider}, treating as CLOSED")
            return False
        
        cb_status = self.circuit_breakers[provider]
        
        if cb_status.state == CircuitBreakerState.OPEN:
            # Check if it's time to transition to HALF-OPEN
            if self._should_attempt_probe(provider):
                self._transition_to_half_open(provider)
                return False  # Allow the probe
            return True  # Still OPEN
        
        return False  # CLOSED or HALF-OPEN
    
    def should_count_failure(self, provider: str, exception: Exception) -> bool:
        """
        FD 2.6: Determine if error should count as circuit breaker failure
        """
        # Import here to avoid circular imports
        from app.services.exceptions import RateLimitError
        
        exception_type = type(exception).__name__
        
        # Count as failure: TimeoutError, RateLimitError
        if isinstance(exception, (asyncio.TimeoutError, RateLimitError)):
            return True
        
        # HTTP 429 (rate limit) counts as failure
        if hasattr(exception, 'status_code') and exception.status_code == 429:
            return True
        
        # HTTP timeouts and 5xx errors count as failures
        if hasattr(exception, 'status_code') and exception.status_code >= 500:
            return True
        
        # Connection errors count as failures
        if any(error_type in exception_type.lower() for error_type in [
            'connection', 'timeout', 'network', 'socket'
        ]):
            return True
        
        # ValueError and HTTP 4xx (except 429) don't count
        if isinstance(exception, ValueError):
            return False
        
        if hasattr(exception, 'status_code') and 400 <= exception.status_code < 500 and exception.status_code != 429:
            return False
        
        # Default: count as failure to be safe
        logger.warning(f"Unknown exception type {exception_type}, counting as failure")
        return True
    
    def record_failure(self, provider: str, exception: Exception):
        """
        Record a failure for the circuit breaker
        """
        if provider not in self.circuit_breakers:
            logger.warning(f"Recording failure for unknown provider {provider}")
            return
        
        if not self.should_count_failure(provider, exception):
            logger.debug(f"Not counting {type(exception).__name__} as failure for {provider}")
            return
        
        cb_status = self.circuit_breakers[provider]
        cb_status.failure_count += 1
        cb_status.last_failure_time = datetime.utcnow()
        cb_status.total_requests += 1
        
        logger.warning(f"Recorded failure for {provider}: {cb_status.failure_count} failures")
        
        # Check if we should trip the circuit breaker
        config = self.provider_configs[provider]
        if cb_status.failure_count >= config.circuit_breaker_failure_threshold:
            self._transition_to_open(provider)
    
    def record_success(self, provider: str):
        """
        Record a successful request
        """
        if provider not in self.circuit_breakers:
            logger.warning(f"Recording success for unknown provider {provider}")
            return
        
        cb_status = self.circuit_breakers[provider]
        cb_status.last_success_time = datetime.utcnow()
        cb_status.successful_requests += 1
        cb_status.total_requests += 1
        
        # Reset circuit breaker on success
        if cb_status.state in [CircuitBreakerState.HALF_OPEN, CircuitBreakerState.CLOSED]:
            self._transition_to_closed(provider)
    
    def _should_attempt_probe(self, provider: str) -> bool:
        """
        FD 2.4: Check if enough time has passed to attempt a probe
        """
        cb_status = self.circuit_breakers[provider]
        if not cb_status.opened_at:
            return False
        
        config = self.provider_configs[provider]
        timeout_period = timedelta(seconds=config.circuit_breaker_timeout_seconds)
        
        return datetime.utcnow() - cb_status.opened_at >= timeout_period
    
    def _transition_to_open(self, provider: str):
        """Transition circuit breaker to OPEN state"""
        cb_status = self.circuit_breakers[provider]
        cb_status.state = CircuitBreakerState.OPEN
        cb_status.opened_at = datetime.utcnow()
        
        logger.error(f"Circuit breaker OPENED for provider {provider} after {cb_status.failure_count} failures")
    
    def _transition_to_half_open(self, provider: str):
        """Transition circuit breaker to HALF-OPEN state"""
        cb_status = self.circuit_breakers[provider]
        cb_status.state = CircuitBreakerState.HALF_OPEN
        
        logger.info(f"Circuit breaker transitioned to HALF-OPEN for provider {provider}")
    
    def _transition_to_closed(self, provider: str):
        """Transition circuit breaker to CLOSED state"""
        cb_status = self.circuit_breakers[provider]
        cb_status.state = CircuitBreakerState.CLOSED
        cb_status.failure_count = 0
        cb_status.opened_at = None
        
        logger.info(f"Circuit breaker CLOSED for provider {provider}")
    
    async def probe_provider(self, provider: str) -> bool:
        """
        FD 2.5: Probe algorithm implementation
        Returns True if probe successful, False otherwise
        """
        if provider in self.probing_providers:
            # Another probe is already in progress
            return False
        
        self.probing_providers.add(provider)
        config = self.provider_configs[provider]
        
        try:
            logger.info(f"Probing provider {provider} (timeout: {config.probe_timeout_seconds}s)")
            
            # Simple completion call with timeout
            success = await self._simple_completion(provider, config.probe_timeout_seconds)
            
            if success:
                self.record_success(provider)
                logger.info(f"Probe successful for {provider}, circuit breaker CLOSED")
                return True
            else:
                # Probe failed, keep circuit breaker OPEN
                self._transition_to_open(provider)
                logger.warning(f"Probe failed for {provider}, circuit breaker remains OPEN")
                return False
                
        except Exception as e:
            logger.error(f"Probe error for {provider}: {str(e)}")
            self._transition_to_open(provider)
            return False
        finally:
            self.probing_providers.discard(provider)
    
    async def _simple_completion(self, provider: str, timeout: int) -> bool:
        """
        Simple completion call for probing
        This would integrate with actual provider SDKs in a full implementation
        """
        try:
            # Mock probe - in real implementation this would call provider API
            await asyncio.wait_for(
                asyncio.sleep(0.1),  # Simulate API call
                timeout=timeout
            )
            
            # Simulate occasional probe failures for testing
            import random
            return random.random() > 0.2  # 80% success rate for probes
            
        except asyncio.TimeoutError:
            logger.warning(f"Probe timeout for {provider}")
            return False
        except Exception as e:
            logger.error(f"Probe exception for {provider}: {str(e)}")
            return False
    
    def get_status(self, provider: str) -> Optional[CircuitBreakerStatus]:
        """Get current circuit breaker status for a provider"""
        return self.circuit_breakers.get(provider)
    
    def get_all_statuses(self) -> Dict[str, CircuitBreakerStatus]:
        """Get all circuit breaker statuses"""
        return self.circuit_breakers.copy()
    
    def reset_circuit_breaker(self, provider: str):
        """Manually reset a circuit breaker (admin function)"""
        if provider in self.circuit_breakers:
            self._transition_to_closed(provider)
            logger.info(f"Circuit breaker manually reset for {provider}")


# Global instance
circuit_breaker_service = CircuitBreakerService() 