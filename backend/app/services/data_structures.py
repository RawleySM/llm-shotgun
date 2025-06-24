"""
Data structures for FD 2: Concurrency & Provider Safety
Defines request context, provider configurations, and token structures.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum


class CircuitBreakerState(Enum):
    """Circuit breaker states as specified in FSD 2.4"""
    CLOSED = "closed"       # Normal operation
    OPEN = "open"          # Rejecting all calls  
    HALF_OPEN = "half_open" # Allowing probe calls


@dataclass
class RequestCtx:
    """Request context for FD 2.2 API signature"""
    request_id: str
    user_id: Optional[str] = None
    attempt_seq: int = 1
    max_retries: int = 3
    started_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderConfig:
    """Provider configuration for semaphores and circuit breakers"""
    name: str
    max_concurrency: int
    circuit_breaker_failure_threshold: int = 3
    circuit_breaker_timeout_seconds: int = 30
    probe_timeout_seconds: int = 5


@dataclass
class Token:
    """Token structure for streaming responses"""
    model_id: str
    text: str
    index: int
    timestamp: datetime = field(default_factory=datetime.utcnow)
    request_id: str = ""
    attempt_seq: int = 1


@dataclass
class CircuitBreakerStatus:
    """Current status of a circuit breaker"""
    state: CircuitBreakerState
    failure_count: int
    last_failure_time: Optional[datetime]
    last_success_time: Optional[datetime]
    opened_at: Optional[datetime]
    total_requests: int = 0
    successful_requests: int = 0


# FSD 2.3: Semaphore defaults for each provider
DEFAULT_PROVIDER_CONFIGS = {
    "openai": ProviderConfig(name="openai", max_concurrency=5),
    "anthropic": ProviderConfig(name="anthropic", max_concurrency=3),
    "google_ai": ProviderConfig(name="google_ai", max_concurrency=3),
    "deepseek": ProviderConfig(name="deepseek", max_concurrency=3),
    "cohere": ProviderConfig(name="cohere", max_concurrency=3),
} 