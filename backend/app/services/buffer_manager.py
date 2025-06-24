"""
FD 3.2 & 3.3: BufferManager Module
Implements token buffering with state machine and flush contract as specified in FSD.
Updated for FD 4 integration with real persistence layer.
"""

import asyncio
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional, Callable, Awaitable, TYPE_CHECKING
from app.services.data_structures import Token
from app.services.persistence_exceptions import PersistenceDeferred, PersistenceError
from app.utils.logger import setup_logger

if TYPE_CHECKING:
    from app.services.persistence_service import PersistenceService

logger = setup_logger(__name__)


class BufferState(Enum):
    """FD 3.3: Buffer state machine states"""
    IDLE = "idle"           # No tokens buffered
    BUFFER = "buffer"       # Accumulating tokens, may accept more
    FLUSHING = "flushing"   # Buffer frozen, drain() persists batch, returns to IDLE


class BufferManager:
    """
    FD 3.2: BufferManager responsibility
    - Append tokens, signal flush_needed when size ≥ 16 or age ≥ 1 s
    - Expose drain() coroutine
    - Implement FD 3.3 state machine with condition variables for back-pressure
    """
    
    def __init__(self, 
                 batch_size: int = 16,
                 flush_timeout_seconds: float = 1.0,
                 persistence_service: Optional["PersistenceService"] = None):
        
        # FD 3.4: Flush contract parameters
        self.batch_size = batch_size  # flush_needed when size >= 16
        self.flush_timeout_seconds = flush_timeout_seconds  # flush_needed when age >= 1s
        
        # State machine (FD 3.3)
        self.state = BufferState.IDLE
        self.buffer: List[Token] = []
        self.first_token_time: Optional[datetime] = None
        
        # FD 3.4: Condition variable for back-pressure
        self._ready_condition = asyncio.Condition()
        
        # FD 4 integration: Real persistence service
        self.persistence_service = persistence_service
        
        # Metrics
        self.total_tokens_processed = 0
        self.total_flushes = 0
        self.successful_flushes = 0
        self.deferred_flushes = 0  # FD 4: WAL fallback events
        self.failed_flushes = 0
        self.last_flush_duration_ms: Optional[float] = None
        self.last_flush_time: Optional[datetime] = None
        self.last_flush_status: str = "none"  # "success", "deferred", "failed"
        
        logger.info(f"BufferManager initialized: batch_size={batch_size}, "
                   f"flush_timeout={flush_timeout_seconds}s, "
                   f"persistence={'enabled' if persistence_service else 'disabled'}")
    
    async def add(self, token: Token) -> None:
        """
        FD 3.2: Key function - add(token)
        FD 3.4: During FLUSHING, upstream pauses via condition variable
        """
        async with self._ready_condition:
            # FD 3.4: Back-pressure - wait if currently flushing
            while self.state == BufferState.FLUSHING:
                logger.debug(f"Buffer flushing, waiting... (token {token.index})")
                await self._ready_condition.wait()
            
            # Add token to buffer
            self.buffer.append(token)
            self.total_tokens_processed += 1
            
            # Track first token time for flush timeout
            if self.state == BufferState.IDLE:
                self.state = BufferState.BUFFER
                self.first_token_time = datetime.utcnow()
                logger.debug(f"Buffer state: IDLE → BUFFER (first token: {token.index})")
            
            logger.debug(f"Added token {token.index} to buffer (size: {len(self.buffer)})")
            
            # Check if flush is needed
            if self.flush_needed():
                logger.debug(f"Flush needed triggered (size: {len(self.buffer)}, "
                           f"age: {self._get_buffer_age_seconds():.2f}s)")
                # Don't flush here - let the pipeline call drain() explicitly
    
    def flush_needed(self) -> bool:
        """
        FD 3.4: Flush contract - triggers when len(buffer) >= 16 OR age >= 1s
        """
        if self.state != BufferState.BUFFER:
            return False
        
        # Size trigger: len(buffer) >= batch_size
        if len(self.buffer) >= self.batch_size:
            logger.debug(f"Flush needed: size trigger ({len(self.buffer)} >= {self.batch_size})")
            return True
        
        # Time trigger: age >= flush_timeout_seconds
        if self.first_token_time:
            age_seconds = self._get_buffer_age_seconds()
            if age_seconds >= self.flush_timeout_seconds:
                logger.debug(f"Flush needed: time trigger ({age_seconds:.2f}s >= {self.flush_timeout_seconds}s)")
                return True
        
        return False
    
    async def drain(self) -> List[Token]:
        """
        FD 3.2: Key function - drain() coroutine
        FD 3.3: BUFFER → FLUSHING → IDLE state transition
        FD 4: Integration with persistence service and WAL fallback handling
        """
        async with self._ready_condition:
            if self.state != BufferState.BUFFER:
                logger.debug(f"Drain called but state is {self.state.value}, no-op")
                return []
            
            # FD 3.3: BUFFER → FLUSHING
            self.state = BufferState.FLUSHING
            logger.debug(f"Buffer state: BUFFER → FLUSHING (draining {len(self.buffer)} tokens)")
            
            flush_start = datetime.utcnow()
            
            try:
                # Extract tokens to flush
                tokens_to_flush = self.buffer.copy()
                
                # FD 4: Persist tokens using real persistence service
                if self.persistence_service and tokens_to_flush:
                    await self.persistence_service.persist_batch(tokens_to_flush)
                    
                    # Success path
                    self.successful_flushes += 1
                    self.last_flush_status = "success"
                    logger.debug(f"Tokens successfully persisted to database")
                
                # Clear buffer and reset state
                self.buffer.clear()
                self.first_token_time = None
                
                # Update metrics
                self.total_flushes += 1
                flush_duration = datetime.utcnow() - flush_start
                self.last_flush_duration_ms = flush_duration.total_seconds() * 1000
                self.last_flush_time = datetime.utcnow()
                
                # FD 3.3: FLUSHING → IDLE
                self.state = BufferState.IDLE
                logger.info(f"Buffer flushed: {len(tokens_to_flush)} tokens "
                           f"({self.last_flush_duration_ms:.1f}ms, status: {self.last_flush_status})")
                
                # Notify waiting add() calls
                self._ready_condition.notify_all()
                
                return tokens_to_flush
                
            except PersistenceDeferred as e:
                # FD 4: WAL fallback occurred - this is actually success!
                # Tokens are safe in WAL file and will be replayed later
                
                # Clear buffer and reset state - tokens are safely persisted in WAL
                self.buffer.clear()
                self.first_token_time = None
                
                # Update metrics
                self.total_flushes += 1
                self.deferred_flushes += 1
                self.last_flush_status = "deferred"
                flush_duration = datetime.utcnow() - flush_start
                self.last_flush_duration_ms = flush_duration.total_seconds() * 1000
                self.last_flush_time = datetime.utcnow()
                
                # FD 3.3: FLUSHING → IDLE (WAL persistence is sufficient)
                self.state = BufferState.IDLE
                logger.warning(f"Buffer flushed to WAL: {len(tokens_to_flush)} tokens "
                              f"({self.last_flush_duration_ms:.1f}ms, deferred to {e.wal_file})")
                
                # Notify waiting add() calls
                self._ready_condition.notify_all()
                
                return tokens_to_flush
                
            except PersistenceError as e:
                # FD 4: Fatal persistence error - return to BUFFER state
                self.failed_flushes += 1
                self.last_flush_status = "failed"
                self.state = BufferState.BUFFER
                
                flush_duration = datetime.utcnow() - flush_start
                self.last_flush_duration_ms = flush_duration.total_seconds() * 1000
                
                logger.error(f"Buffer flush failed: {str(e)} "
                            f"({self.last_flush_duration_ms:.1f}ms)")
                self._ready_condition.notify_all()
                raise
                
            except Exception as e:
                # Unexpected error - return to BUFFER state
                self.failed_flushes += 1
                self.last_flush_status = "failed"
                self.state = BufferState.BUFFER
                
                flush_duration = datetime.utcnow() - flush_start
                self.last_flush_duration_ms = flush_duration.total_seconds() * 1000
                
                logger.error(f"Buffer flush failed with unexpected error: {str(e)} "
                            f"({self.last_flush_duration_ms:.1f}ms)")
                self._ready_condition.notify_all()
                raise
    
    async def wait_ready(self) -> None:
        """
        FD 3.4: Condition variable for upstream to wait during flushing
        Public interface for external callers to respect back-pressure
        """
        async with self._ready_condition:
            while self.state == BufferState.FLUSHING:
                await self._ready_condition.wait()
    
    async def force_flush(self) -> List[Token]:
        """
        Force flush buffer regardless of size/age (useful for shutdown)
        """
        if self.state == BufferState.BUFFER and self.buffer:
            logger.info(f"Force flushing {len(self.buffer)} tokens")
            return await self.drain()
        return []
    
    def get_buffer_status(self) -> dict:
        """Get current buffer status for monitoring"""
        return {
            "state": self.state.value,
            "buffer_size": len(self.buffer),
            "buffer_age_seconds": self._get_buffer_age_seconds(),
            "flush_needed": self.flush_needed(),
            "statistics": {
                "total_tokens_processed": self.total_tokens_processed,
                "total_flushes": self.total_flushes,
                "successful_flushes": self.successful_flushes,
                "deferred_flushes": self.deferred_flushes,
                "failed_flushes": self.failed_flushes,
                "success_rate": (self.successful_flushes / max(self.total_flushes, 1)) * 100,
                "deferral_rate": (self.deferred_flushes / max(self.total_flushes, 1)) * 100
            },
            "last_flush": {
                "duration_ms": self.last_flush_duration_ms,
                "time": self.last_flush_time.isoformat() if self.last_flush_time else None,
                "status": self.last_flush_status
            },
            "config": {
                "batch_size": self.batch_size,
                "flush_timeout_seconds": self.flush_timeout_seconds,
                "persistence_enabled": self.persistence_service is not None
            }
        }
    
    def _get_buffer_age_seconds(self) -> float:
        """Calculate buffer age in seconds"""
        if not self.first_token_time:
            return 0.0
        return (datetime.utcnow() - self.first_token_time).total_seconds()
    
    async def cleanup(self):
        """Cleanup method for graceful shutdown"""
        logger.info("BufferManager cleanup started")
        
        # Force flush any remaining tokens
        if self.state == BufferState.BUFFER and self.buffer:
            try:
                await self.force_flush()
                logger.info("Final buffer flush completed during cleanup")
            except Exception as e:
                logger.error(f"Error during cleanup flush: {str(e)}")
        
        # Wake up any waiting coroutines
        async with self._ready_condition:
            self._ready_condition.notify_all()
        
        logger.info("BufferManager cleanup completed")


 