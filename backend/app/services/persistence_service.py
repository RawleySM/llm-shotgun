"""
FD 4.2: Persistence Service - Main Implementation
Implements batch persistence algorithm with WAL-Lite fallback as specified in FSD.
"""

import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable
from app.services.data_structures import Token
from app.services.wal_handler import WALHandler
from app.services.database_operations import DatabaseOperations
from app.services.wal_replay import WALReplayService
from app.services.persistence_exceptions import (
    PersistenceDeferred,
    DatabaseUnavailableError,
    DiskFullError,
    PersistenceError
)
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class PersistenceService:
    """
    FD 4.2: Main persistence service implementing batch persistence algorithm
    
    async def persist_batch(batch: list[Token]):
        try:
            await pg_copy(batch)
        except (asyncpg.PostgresError, OSError) as e:
            wal_write(batch)
            raise PersistenceDeferred(e)
    """
    
    def __init__(self, 
                 wal_file_path: str = "/app/data/tokens.wal",
                 enable_replay_loop: bool = True):
        
        # Initialize components
        self.wal_handler = WALHandler(wal_file_path=wal_file_path)
        self.database_ops = DatabaseOperations()
        self.wal_replay = WALReplayService(
            wal_handler=self.wal_handler,
            database_ops=self.database_ops
        )
        
        self.enable_replay_loop = enable_replay_loop
        
        # Persistence statistics
        self.total_persist_calls = 0
        self.successful_database_writes = 0
        self.wal_fallback_writes = 0
        self.failed_persists = 0
        self.last_persist_time: Optional[datetime] = None
        self.last_db_write_time: Optional[datetime] = None
        
        # Callback for persistence events (used by buffer manager)
        self.persistence_callbacks: List[Callable[[str, Dict[str, Any]], None]] = []
        
        logger.info(f"Persistence service initialized (WAL: {wal_file_path}, "
                   f"replay_enabled: {enable_replay_loop})")
    
    async def start(self) -> None:
        """
        Start the persistence service and WAL replay loop
        """
        if self.enable_replay_loop:
            await self.wal_replay.start_replay_loop()
            logger.info("Persistence service started with WAL replay loop")
        else:
            logger.info("Persistence service started without replay loop")
    
    async def stop(self) -> None:
        """
        Stop the persistence service gracefully
        """
        if self.enable_replay_loop:
            await self.wal_replay.stop_replay_loop()
        logger.info("Persistence service stopped")
    
    async def persist_batch(self, tokens: List[Token]) -> None:
        """
        FD 4.2: Main batch persistence algorithm implementation
        
        async def persist_batch(batch: list[Token]):
            try:
                await pg_copy(batch)
            except (asyncpg.PostgresError, OSError) as e:
                wal_write(batch)
                raise PersistenceDeferred(e)
        """
        if not tokens:
            logger.debug("Empty token batch, nothing to persist")
            return
        
        self.total_persist_calls += 1
        start_time = datetime.utcnow()
        
        logger.debug(f"Persisting batch of {len(tokens)} tokens")
        
        try:
            # FD 4.2: try await pg_copy(batch)
            await self.database_ops.pg_copy_batch(tokens)
            
            # Success - update statistics
            self.successful_database_writes += 1
            self.last_persist_time = datetime.utcnow()
            self.last_db_write_time = datetime.utcnow()
            
            elapsed_ms = int((self.last_persist_time - start_time).total_seconds() * 1000)
            
            logger.debug(f"Successfully persisted {len(tokens)} tokens to database ({elapsed_ms}ms)")
            
            # Notify callbacks of successful persistence
            self._notify_callbacks("database_write_success", {
                "token_count": len(tokens),
                "elapsed_ms": elapsed_ms
            })
            
        except DatabaseUnavailableError as e:
            # FD 4.2: except (asyncpg.PostgresError, OSError) as e: wal_write(batch)
            try:
                await self.wal_handler.write_batch(tokens)
                
                self.wal_fallback_writes += 1
                self.last_persist_time = datetime.utcnow()
                
                logger.warning(f"Database unavailable, wrote {len(tokens)} tokens to WAL: {str(e.original_error)}")
                
                # Notify callbacks of WAL fallback
                self._notify_callbacks("wal_fallback", {
                    "token_count": len(tokens),
                    "original_error": str(e.original_error)
                })
                
                # FD 4.2: raise PersistenceDeferred(e)
                raise PersistenceDeferred(e.original_error, self.wal_handler.wal_file_path.name)
                
            except DiskFullError as disk_error:
                # Fatal error - can't write to either database or WAL
                self.failed_persists += 1
                logger.critical(f"FATAL: Cannot persist tokens - both database and disk unavailable")
                
                self._notify_callbacks("persistence_failure", {
                    "token_count": len(tokens),
                    "database_error": str(e.original_error),
                    "disk_error": str(disk_error)
                })
                
                raise PersistenceError(f"Persistence failure: database unavailable and disk full")
                
            except Exception as wal_error:
                # WAL write failed for other reasons
                self.failed_persists += 1
                logger.error(f"Failed to write to both database and WAL: db={str(e)}, wal={str(wal_error)}")
                
                self._notify_callbacks("persistence_failure", {
                    "token_count": len(tokens),
                    "database_error": str(e.original_error),
                    "wal_error": str(wal_error)
                })
                
                raise PersistenceError(f"Persistence failure: {str(wal_error)}")
                
        except Exception as e:
            # Unexpected error during database write
            self.failed_persists += 1
            logger.error(f"Unexpected persistence error: {str(e)}")
            
            self._notify_callbacks("persistence_error", {
                "token_count": len(tokens),
                "error": str(e),
                "error_type": type(e).__name__
            })
            
            raise PersistenceError(f"Unexpected persistence error: {str(e)}")
    
    def register_callback(self, callback: Callable[[str, Dict[str, Any]], None]) -> None:
        """
        Register a callback for persistence events
        Used by buffer manager to track persistence status
        """
        self.persistence_callbacks.append(callback)
        logger.debug("Persistence callback registered")
    
    def _notify_callbacks(self, event_type: str, event_data: Dict[str, Any]) -> None:
        """Notify all registered callbacks of persistence events"""
        for callback in self.persistence_callbacks:
            try:
                callback(event_type, event_data)
            except Exception as e:
                logger.error(f"Error in persistence callback: {str(e)}")
    
    async def manual_persist_test(self, token_count: int = 5) -> Dict[str, Any]:
        """
        Test persistence with a batch of mock tokens
        Returns detailed results for debugging
        """
        logger.info(f"Manual persistence test with {token_count} tokens")
        
        # Generate test tokens
        test_tokens = []
        base_time = datetime.utcnow()
        
        for i in range(token_count):
            token = Token(
                model_id="test-model",
                text=f"test_token_{i}",
                index=i,
                timestamp=base_time,
                request_id="test_request_id",
                attempt_seq=1
            )
            test_tokens.append(token)
        
        start_time = datetime.utcnow()
        
        try:
            await self.persist_batch(test_tokens)
            
            elapsed_time = (datetime.utcnow() - start_time).total_seconds()
            
            return {
                "status": "success",
                "persistence_method": "database",
                "token_count": token_count,
                "elapsed_time_seconds": elapsed_time
            }
            
        except PersistenceDeferred as e:
            elapsed_time = (datetime.utcnow() - start_time).total_seconds()
            
            return {
                "status": "deferred",
                "persistence_method": "wal",
                "token_count": token_count,
                "elapsed_time_seconds": elapsed_time,
                "original_error": str(e.original_error),
                "wal_file": e.wal_file
            }
            
        except Exception as e:
            elapsed_time = (datetime.utcnow() - start_time).total_seconds()
            
            return {
                "status": "failed",
                "token_count": token_count,
                "elapsed_time_seconds": elapsed_time,
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    async def get_persistence_status(self) -> Dict[str, Any]:
        """Get comprehensive persistence service status"""
        
        # Get component statuses
        wal_status = self.wal_handler.get_wal_status()
        db_status = self.database_ops.get_database_status()
        replay_status = await self.wal_replay.get_detailed_status()
        
        # Test database connectivity
        db_available = await self.database_ops.test_database_connection()
        
        # Calculate derived metrics
        total_operations = max(self.total_persist_calls, 1)
        success_rate = (self.successful_database_writes / total_operations) * 100
        fallback_rate = (self.wal_fallback_writes / total_operations) * 100
        
        return {
            "service_info": {
                "wal_file_path": str(self.wal_handler.wal_file_path),
                "replay_loop_enabled": self.enable_replay_loop
            },
            "current_status": {
                "database_available": db_available,
                "replay_running": self.wal_replay.is_running,
                "wal_file_size_bytes": self.wal_handler.get_file_size_bytes(),
                "last_db_write_time": self.last_db_write_time.isoformat() if self.last_db_write_time else None
            },
            "statistics": {
                "total_persist_calls": self.total_persist_calls,
                "successful_database_writes": self.successful_database_writes,
                "wal_fallback_writes": self.wal_fallback_writes,
                "failed_persists": self.failed_persists,
                "success_rate_percent": success_rate,
                "fallback_rate_percent": fallback_rate,
                "last_persist_time": self.last_persist_time.isoformat() if self.last_persist_time else None
            },
            "components": {
                "wal_handler": wal_status,
                "database_operations": db_status,
                "wal_replay": replay_status
            }
        }
    
    async def validate_persistence_integrity(self) -> Dict[str, Any]:
        """
        Comprehensive validation of persistence layer integrity
        """
        validation_result = {
            "valid": True,
            "issues": [],
            "component_validations": {}
        }
        
        try:
            # Validate WAL handler
            wal_validation = await self.wal_handler.validate_wal_file()
            validation_result["component_validations"]["wal_handler"] = wal_validation
            
            if not wal_validation["valid"]:
                validation_result["valid"] = False
                validation_result["issues"].extend([
                    f"WAL validation: {issue}" for issue in wal_validation["issues"]
                ])
            
            # Validate database schema
            db_validation = await self.database_ops.validate_database_schema()
            validation_result["component_validations"]["database"] = db_validation
            
            if not db_validation["valid"]:
                validation_result["valid"] = False
                validation_result["issues"].extend([
                    f"Database validation: {issue}" for issue in db_validation["issues"]
                ])
            
            # Validate replay service
            replay_validation = await self.wal_replay.validate_replay_integrity()
            validation_result["component_validations"]["wal_replay"] = replay_validation
            
            if not replay_validation["valid"]:
                validation_result["valid"] = False
                validation_result["issues"].extend([
                    f"Replay validation: {issue}" for issue in replay_validation["issues"]
                ])
            
            # Check service configuration
            if self.enable_replay_loop and not self.wal_replay.is_running:
                validation_result["valid"] = False
                validation_result["issues"].append("Replay loop enabled but not running")
            
            # Check for high failure rates
            if self.total_persist_calls > 10:
                failure_rate = (self.failed_persists / self.total_persist_calls) * 100
                if failure_rate > 10:  # More than 10% failures
                    validation_result["issues"].append(
                        f"High persistence failure rate: {failure_rate:.1f}%"
                    )
            
        except Exception as e:
            validation_result["valid"] = False
            validation_result["issues"].append(f"Validation error: {str(e)}")
        
        return validation_result
    
    def reset_statistics(self) -> None:
        """Reset all persistence statistics"""
        self.total_persist_calls = 0
        self.successful_database_writes = 0
        self.wal_fallback_writes = 0
        self.failed_persists = 0
        self.last_persist_time = None
        self.last_db_write_time = None
        
        # Reset component statistics
        self.wal_replay.reset_statistics()
        
        logger.info("Persistence service statistics reset")
    
    async def force_wal_replay(self) -> Dict[str, Any]:
        """
        Force immediate WAL replay (admin function)
        """
        logger.info("Forcing WAL replay")
        return await self.wal_replay.manual_replay()
    
    async def cleanup_old_wal_backups(self, max_age_days: int = 7) -> List[str]:
        """
        Clean up old WAL backup files
        """
        logger.info(f"Cleaning up WAL backups older than {max_age_days} days")
        return await self.wal_handler.cleanup_old_backups(max_age_days)
    
    def get_wal_file_size_bytes(self) -> int:
        """Get current WAL file size (for health endpoint)"""
        return self.wal_handler.get_file_size_bytes()
    
    def get_last_db_write_time(self) -> Optional[str]:
        """Get last database write time (for health endpoint)"""
        return self.last_db_write_time.isoformat() if self.last_db_write_time else None 