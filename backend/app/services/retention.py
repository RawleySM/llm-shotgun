"""
FD 9: Retention & Cleanup Service
Implements automated data retention, pruning, and WAL file rotation.
"""

import asyncio
import os
import shutil
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from pathlib import Path
from sqlalchemy import text, delete
from sqlalchemy.exc import SQLAlchemyError
from app.db.database import AsyncSessionLocal
from app.db.models import LLMTokenLog, LLMRequest, LLMAttempt
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class RetentionService:
    """Service to handle data retention, pruning, and cleanup operations"""
    
    def __init__(self):
        self.default_retention_days = 180
        self.wal_max_size_bytes = 100 * 1024 * 1024  # 100 MiB
        self.wal_file_path = Path("/app/data/tokens.wal")
        self.backup_dir = Path("/app/data/backups")
        self.last_prune_time: Optional[datetime] = None
        
        # Ensure directories exist
        self.wal_file_path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    async def run_weekly_prune(self, retention_days: Optional[int] = None) -> Dict[str, Any]:
        """
        FD 9.1: Weekly prune job - remove tokens older than retention period
        """
        retention_days = retention_days or self.default_retention_days
        cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
        
        logger.info(f"Starting weekly prune for data older than {cutoff_date}")
        
        results = {
            "status": "completed",
            "tokens_deleted": 0,
            "attempts_deleted": 0,
            "requests_deleted": 0,
            "cutoff_date": cutoff_date.isoformat(),
            "errors": []
        }
        
        try:
            async with AsyncSessionLocal() as session:
                # Start transaction
                async with session.begin():
                    # Delete old tokens
                    token_delete_result = await session.execute(
                        delete(LLMTokenLog).where(LLMTokenLog.ts < cutoff_date)
                    )
                    results["tokens_deleted"] = token_delete_result.rowcount
                    
                    # Delete old attempts (that no longer have tokens)
                    attempt_delete_query = text("""
                        DELETE FROM llm_attempts 
                        WHERE started_at < :cutoff_date
                        AND NOT EXISTS (
                            SELECT 1 FROM llm_token_log 
                            WHERE llm_token_log.request_id = llm_attempts.request_id 
                            AND llm_token_log.attempt_seq = llm_attempts.attempt_seq
                        )
                    """)
                    attempt_delete_result = await session.execute(
                        attempt_delete_query, {"cutoff_date": cutoff_date}
                    )
                    results["attempts_deleted"] = attempt_delete_result.rowcount
                    
                    # Delete old requests (that no longer have attempts)
                    request_delete_query = text("""
                        DELETE FROM llm_requests 
                        WHERE created_at < :cutoff_date
                        AND NOT EXISTS (
                            SELECT 1 FROM llm_attempts 
                            WHERE llm_attempts.request_id = llm_requests.request_id
                        )
                    """)
                    request_delete_result = await session.execute(
                        request_delete_query, {"cutoff_date": cutoff_date}
                    )
                    results["requests_deleted"] = request_delete_result.rowcount
                    
                    await session.commit()
                    
                self.last_prune_time = datetime.utcnow()
                logger.info(f"Weekly prune completed: {results['tokens_deleted']} tokens, "
                           f"{results['attempts_deleted']} attempts, {results['requests_deleted']} requests deleted")
                
        except SQLAlchemyError as e:
            error_msg = f"Database error during prune operation: {str(e)}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
            results["status"] = "failed"
        except Exception as e:
            error_msg = f"Unexpected error during prune operation: {str(e)}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
            results["status"] = "failed"
        
        return results
    
    def rotate_wal_file(self) -> Dict[str, Any]:
        """
        FD 9.2: Rotate WAL file when it exceeds maximum size
        """
        results = {
            "status": "completed",
            "rotation_performed": False,
            "old_file_size": 0,
            "backup_file": None,
            "errors": []
        }
        
        try:
            if not self.wal_file_path.exists():
                results["status"] = "no_file"
                return results
            
            file_size = self.wal_file_path.stat().st_size
            results["old_file_size"] = file_size
            
            if file_size > self.wal_max_size_bytes:
                # Create backup filename with timestamp
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                backup_filename = f"wal-{timestamp}.bak"
                backup_path = self.backup_dir / backup_filename
                
                # Move current WAL file to backup
                shutil.move(str(self.wal_file_path), str(backup_path))
                
                # Create new empty WAL file
                self.wal_file_path.touch()
                
                results["rotation_performed"] = True
                results["backup_file"] = str(backup_path)
                
                logger.info(f"WAL file rotated: {file_size} bytes -> {backup_filename}")
            
        except Exception as e:
            error_msg = f"Error rotating WAL file: {str(e)}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
            results["status"] = "failed"
        
        return results
    
    def cleanup_old_backups(self, keep_days: int = 30) -> Dict[str, Any]:
        """
        Clean up old backup files older than specified days
        """
        cutoff_date = datetime.utcnow() - timedelta(days=keep_days)
        
        results = {
            "status": "completed",
            "files_deleted": 0,
            "bytes_freed": 0,
            "errors": []
        }
        
        try:
            for backup_file in self.backup_dir.glob("wal-*.bak"):
                if backup_file.stat().st_mtime < cutoff_date.timestamp():
                    file_size = backup_file.stat().st_size
                    backup_file.unlink()
                    results["files_deleted"] += 1
                    results["bytes_freed"] += file_size
                    logger.debug(f"Deleted old backup: {backup_file.name}")
            
            if results["files_deleted"] > 0:
                logger.info(f"Cleaned up {results['files_deleted']} old backup files, "
                           f"freed {results['bytes_freed']} bytes")
            
        except Exception as e:
            error_msg = f"Error cleaning up old backups: {str(e)}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
            results["status"] = "failed"
        
        return results
    
    def get_wal_file_size(self) -> int:
        """Get current WAL file size in bytes"""
        try:
            if self.wal_file_path.exists():
                return self.wal_file_path.stat().st_size
            return 0
        except Exception:
            return 0
    
    async def get_retention_status(self) -> Dict[str, Any]:
        """Get current retention service status"""
        return {
            "last_prune_time": self.last_prune_time.isoformat() if self.last_prune_time else None,
            "retention_days": self.default_retention_days,
            "wal_file_size": self.get_wal_file_size(),
            "wal_max_size": self.wal_max_size_bytes,
            "backup_count": len(list(self.backup_dir.glob("wal-*.bak")))
        }


# Global instance
retention_service = RetentionService() 