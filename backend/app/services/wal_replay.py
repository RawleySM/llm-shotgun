"""
FD 4.5: WAL Replay Service
Implements background WAL replay loop as specified in FSD.
"""

import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
from app.services.data_structures import Token
from app.services.wal_handler import WALHandler
from app.services.database_operations import DatabaseOperations
from app.services.persistence_exceptions import (
    WALReplayError, 
    DatabaseUnavailableError,
    WALCorruptionError
)
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class WALReplayService:
    """
    FD 4.5: WAL Replay Loop Implementation
    - Background task that runs every 10 seconds
    - Checks if database is available
    - Replays WAL file contents to database
    - Truncates WAL file after successful replay
    """
    
    def __init__(self, 
                 wal_handler: WALHandler,
                 database_ops: DatabaseOperations,
                 replay_interval_seconds: int = 10,
                 batch_size: int = 16):
        
        self.wal_handler = wal_handler
        self.database_ops = database_ops
        self.replay_interval_seconds = replay_interval_seconds
        self.batch_size = batch_size
        
        # Replay state
        self.is_running = False
        self.replay_task: Optional[asyncio.Task] = None
        
        # Statistics
        self.total_replay_attempts = 0
        self.successful_replays = 0
        self.failed_replays = 0
        self.total_tokens_replayed = 0
        self.last_replay_time: Optional[datetime] = None
        self.last_error: Optional[str] = None
        
        logger.info(f"WAL replay service initialized (interval: {replay_interval_seconds}s, "
                   f"batch_size: {batch_size})")
    
    async def start_replay_loop(self) -> None:
        """
        Start the background WAL replay loop
        """
        if self.is_running:
            logger.warning("WAL replay loop is already running")
            return
        
        self.is_running = True
        self.replay_task = asyncio.create_task(self._replay_loop())
        logger.info("WAL replay loop started")
    
    async def stop_replay_loop(self) -> None:
        """
        Stop the background WAL replay loop gracefully
        """
        if not self.is_running:
            return
        
        self.is_running = False
        
        if self.replay_task:
            self.replay_task.cancel()
            try:
                await self.replay_task
            except asyncio.CancelledError:
                pass
            self.replay_task = None
        
        logger.info("WAL replay loop stopped")
    
    async def _replay_loop(self) -> None:
        """
        FD 4.5: Main replay loop implementation
        while True:
            if db_is_up():
                for line in read_lines('tokens.wal'):
                    batch.append(json.loads(line))
                    if len(batch) == 16:
                        await pg_copy(batch); batch.clear()
                truncate_file('tokens.wal')
            await asyncio.sleep(10)
        """
        logger.info("WAL replay loop started")
        
        while self.is_running:
            try:
                await self._perform_replay_cycle()
                
            except asyncio.CancelledError:
                logger.info("WAL replay loop cancelled")
                break
            except Exception as e:
                logger.error(f"Unexpected error in replay loop: {str(e)}")
                self.failed_replays += 1
                self.last_error = str(e)
            
            # FD 4.5: await asyncio.sleep(10)
            try:
                await asyncio.sleep(self.replay_interval_seconds)
            except asyncio.CancelledError:
                break
        
        logger.info("WAL replay loop ended")
    
    async def _perform_replay_cycle(self) -> None:
        """
        FD 4.5: Single replay cycle implementation
        """
        self.total_replay_attempts += 1
        
        # FD 4.5: if db_is_up():
        db_available = await self.database_ops.test_database_connection()
        
        if not db_available:
            logger.debug("Database not available, skipping replay cycle")
            return
        
        # Check if WAL file has content to replay
        wal_size = self.wal_handler.get_file_size_bytes()
        if wal_size == 0:
            logger.debug("WAL file empty, nothing to replay")
            return
        
        logger.info(f"Starting WAL replay cycle (WAL size: {wal_size} bytes)")
        
        try:
            tokens_replayed = await self._replay_wal_file()
            
            if tokens_replayed > 0:
                # FD 4.5: truncate_file('tokens.wal')
                await self.wal_handler.truncate_file()
                
                self.successful_replays += 1
                self.total_tokens_replayed += tokens_replayed
                self.last_replay_time = datetime.utcnow()
                
                logger.info(f"WAL replay successful: {tokens_replayed} tokens replayed")
            else:
                logger.debug("No tokens to replay")
                
        except DatabaseUnavailableError as e:
            logger.warning(f"Database became unavailable during replay: {str(e)}")
            self.failed_replays += 1
            self.last_error = str(e)
        except WALCorruptionError as e:
            logger.error(f"WAL corruption detected during replay: {str(e)}")
            self.failed_replays += 1
            self.last_error = str(e)
            # Don't truncate corrupted WAL file - manual intervention needed
        except Exception as e:
            logger.error(f"Replay cycle failed: {str(e)}")
            self.failed_replays += 1
            self.last_error = str(e)
    
    async def _replay_wal_file(self) -> int:
        """
        FD 4.5: Replay WAL file contents to database
        Returns number of tokens replayed
        """
        batch: List[Token] = []
        total_tokens = 0
        line_number = 0
        
        try:
            # FD 4.5: for line in read_lines('tokens.wal'):
            async for line in self.wal_handler.read_lines():
                line_number += 1
                
                try:
                    # Parse WAL line to Token
                    token = await self.wal_handler.parse_wal_line(line)
                    batch.append(token)
                    
                    # FD 4.5: if len(batch) == 16: await pg_copy(batch); batch.clear()
                    if len(batch) >= self.batch_size:
                        await self._flush_batch(batch)
                        total_tokens += len(batch)
                        batch.clear()
                        
                except WALCorruptionError as e:
                    raise WALReplayError(line_number, line[:100], e.original_error)
                except Exception as e:
                    raise WALReplayError(line_number, line[:100], e)
            
            # Flush any remaining tokens in batch
            if batch:
                await self._flush_batch(batch)
                total_tokens += len(batch)
            
            return total_tokens
            
        except WALReplayError:
            raise  # Re-raise WAL-specific errors
        except Exception as e:
            logger.error(f"Error reading WAL file at line {line_number}: {str(e)}")
            raise
    
    async def _flush_batch(self, batch: List[Token]) -> None:
        """
        Flush a batch of tokens to database using pg_copy
        """
        if not batch:
            return
        
        try:
            await self.database_ops.pg_copy_batch(batch)
            logger.debug(f"Replayed batch of {len(batch)} tokens to database")
            
        except DatabaseUnavailableError:
            raise  # Let replay cycle handle database unavailability
        except Exception as e:
            logger.error(f"Error flushing replay batch: {str(e)}")
            raise DatabaseUnavailableError("replay_flush", e)
    
    async def manual_replay(self) -> Dict[str, Any]:
        """
        Manually trigger a WAL replay cycle (for testing/admin)
        Returns replay results
        """
        logger.info("Manual WAL replay triggered")
        
        start_time = datetime.utcnow()
        
        try:
            # Check database availability
            db_available = await self.database_ops.test_database_connection()
            if not db_available:
                return {
                    "status": "failed",
                    "error": "Database not available",
                    "tokens_replayed": 0
                }
            
            # Check WAL file size
            wal_size_before = self.wal_handler.get_file_size_bytes()
            
            if wal_size_before == 0:
                return {
                    "status": "success",
                    "message": "WAL file empty, nothing to replay",
                    "tokens_replayed": 0,
                    "wal_size_before": 0,
                    "wal_size_after": 0
                }
            
            # Perform replay
            tokens_replayed = await self._replay_wal_file()
            
            # Truncate WAL file if successful
            if tokens_replayed > 0:
                await self.wal_handler.truncate_file()
            
            wal_size_after = self.wal_handler.get_file_size_bytes()
            elapsed_time = (datetime.utcnow() - start_time).total_seconds()
            
            return {
                "status": "success",
                "tokens_replayed": tokens_replayed,
                "wal_size_before": wal_size_before,
                "wal_size_after": wal_size_after,
                "elapsed_time_seconds": elapsed_time
            }
            
        except Exception as e:
            elapsed_time = (datetime.utcnow() - start_time).total_seconds()
            
            return {
                "status": "failed",
                "error": str(e),
                "error_type": type(e).__name__,
                "tokens_replayed": 0,
                "elapsed_time_seconds": elapsed_time
            }
    
    def get_replay_status(self) -> Dict[str, Any]:
        """Get comprehensive replay service status"""
        return {
            "running": self.is_running,
            "configuration": {
                "replay_interval_seconds": self.replay_interval_seconds,
                "batch_size": self.batch_size
            },
            "statistics": {
                "total_replay_attempts": self.total_replay_attempts,
                "successful_replays": self.successful_replays,
                "failed_replays": self.failed_replays,
                "success_rate": (self.successful_replays / max(self.total_replay_attempts, 1)) * 100,
                "total_tokens_replayed": self.total_tokens_replayed,
                "last_replay_time": self.last_replay_time.isoformat() if self.last_replay_time else None,
                "last_error": self.last_error
            },
            "current_state": {
                "wal_file_size_bytes": self.wal_handler.get_file_size_bytes(),
                "database_available": None  # Would be set by async call
            }
        }
    
    async def get_detailed_status(self) -> Dict[str, Any]:
        """Get detailed status including live database check"""
        status = self.get_replay_status()
        
        # Add live database availability check
        status["current_state"]["database_available"] = await self.database_ops.test_database_connection()
        
        # Add WAL file validation
        wal_validation = await self.wal_handler.validate_wal_file()
        status["wal_validation"] = wal_validation
        
        return status
    
    def reset_statistics(self) -> None:
        """Reset replay statistics"""
        self.total_replay_attempts = 0
        self.successful_replays = 0
        self.failed_replays = 0
        self.total_tokens_replayed = 0
        self.last_replay_time = None
        self.last_error = None
        
        logger.info("WAL replay statistics reset")
    
    async def validate_replay_integrity(self) -> Dict[str, Any]:
        """
        Validate that WAL replay is working correctly
        Checks for consistency between WAL file and database
        """
        validation_result = {
            "valid": True,
            "issues": []
        }
        
        try:
            # Check if database schema is valid
            schema_validation = await self.database_ops.validate_database_schema()
            if not schema_validation["valid"]:
                validation_result["valid"] = False
                validation_result["issues"].extend(schema_validation["issues"])
            
            # Check WAL file integrity
            wal_validation = await self.wal_handler.validate_wal_file()
            if not wal_validation["valid"]:
                validation_result["valid"] = False
                validation_result["issues"].extend([
                    f"WAL file issue: {issue}" for issue in wal_validation["issues"]
                ])
            
            # Check if replay service is running when it should be
            if not self.is_running:
                validation_result["issues"].append("WAL replay service is not running")
            
            # Check for stale WAL file (hasn't been replayed in too long)
            wal_size = self.wal_handler.get_file_size_bytes()
            if wal_size > 0 and self.last_replay_time:
                time_since_replay = (datetime.utcnow() - self.last_replay_time).total_seconds()
                if time_since_replay > 300:  # 5 minutes
                    validation_result["issues"].append(
                        f"WAL file not replayed in {time_since_replay:.0f} seconds (size: {wal_size} bytes)"
                    )
            
        except Exception as e:
            validation_result["valid"] = False
            validation_result["issues"].append(f"Validation error: {str(e)}")
        
        return validation_result 