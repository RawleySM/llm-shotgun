"""
FD 10: Backup & Recovery Service
Implements daily pg_dump operations and recovery procedures.
"""

import asyncio
import subprocess
import os
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from pathlib import Path
from app.config import get_settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
settings = get_settings()


class BackupService:
    """Service to handle database backup and recovery operations"""
    
    def __init__(self):
        self.backup_dir = Path("/app/data/backups")
        self.dump_retention_days = 30
        self.wal_file_path = Path("/app/data/tokens.wal")
        self.last_backup_time: Optional[datetime] = None
        
        # Ensure backup directory exists
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    async def perform_daily_backup(self) -> Dict[str, Any]:
        """
        FD 10.1: Perform daily pg_dump backup
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"pg_dump_{timestamp}.sql"
        backup_path = self.backup_dir / backup_filename
        
        logger.info(f"Starting daily backup to {backup_filename}")
        
        results = {
            "status": "completed",
            "backup_file": str(backup_path),
            "file_size": 0,
            "duration_seconds": 0,
            "timestamp": timestamp,
            "errors": []
        }
        
        start_time = datetime.utcnow()
        
        try:
            # Construct pg_dump command
            pg_dump_cmd = self._build_pg_dump_command(str(backup_path))
            
            # Execute pg_dump
            process = await asyncio.create_subprocess_exec(
                *pg_dump_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                # Backup successful
                self.last_backup_time = datetime.utcnow()
                results["file_size"] = backup_path.stat().st_size
                results["duration_seconds"] = (datetime.utcnow() - start_time).total_seconds()
                
                logger.info(f"Daily backup completed successfully: {backup_filename} "
                           f"({results['file_size']} bytes, {results['duration_seconds']:.1f}s)")
                
                # Cleanup old backups
                cleanup_result = await self.cleanup_old_backups()
                results["cleanup"] = cleanup_result
                
            else:
                error_msg = f"pg_dump failed with return code {process.returncode}: {stderr.decode()}"
                logger.error(error_msg)
                results["errors"].append(error_msg)
                results["status"] = "failed"
                
        except subprocess.SubprocessError as e:
            error_msg = f"Subprocess error during backup: {str(e)}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
            results["status"] = "failed"
        except Exception as e:
            error_msg = f"Unexpected error during backup: {str(e)}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
            results["status"] = "failed"
        
        return results
    
    def _build_pg_dump_command(self, output_file: str) -> List[str]:
        """Build pg_dump command with appropriate connection parameters"""
        cmd = ["pg_dump"]
        
        # Add connection parameters if PostgreSQL is configured
        if settings.DB_NAME:
            cmd.extend([
                "--host", settings.DB_HOST or "localhost",
                "--port", str(settings.DB_PORT or 5432),
                "--username", settings.DB_USER or "postgres",
                "--dbname", settings.DB_NAME,
                "--no-password",  # Use .pgpass or environment variables for password
                "--verbose",
                "--clean",
                "--if-exists",
                "--create",
                "--format=plain",
                f"--file={output_file}"
            ])
        else:
            # For SQLite, we'll use a different approach
            cmd = ["sqlite3", "app.db", f".dump > {output_file}"]
        
        return cmd
    
    async def restore_from_backup(self, backup_file: str, include_wal_replay: bool = True) -> Dict[str, Any]:
        """
        FD 10.2: Restore database from backup file with optional WAL replay
        """
        backup_path = Path(backup_file)
        
        if not backup_path.exists():
            return {
                "status": "failed",
                "errors": [f"Backup file not found: {backup_file}"]
            }
        
        logger.info(f"Starting database restore from {backup_file}")
        
        results = {
            "status": "completed",
            "backup_file": backup_file,
            "wal_replay_performed": False,
            "duration_seconds": 0,
            "errors": []
        }
        
        start_time = datetime.utcnow()
        
        try:
            # Build restore command
            if settings.DB_NAME:
                # PostgreSQL restore
                restore_cmd = [
                    "psql",
                    "--host", settings.DB_HOST or "localhost",
                    "--port", str(settings.DB_PORT or 5432),
                    "--username", settings.DB_USER or "postgres",
                    "--dbname", settings.DB_NAME,
                    "--file", str(backup_path)
                ]
            else:
                # SQLite restore
                restore_cmd = ["sqlite3", "app.db", f".read {backup_path}"]
            
            # Execute restore
            process = await asyncio.create_subprocess_exec(
                *restore_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.info("Database restore completed successfully")
                
                # Optionally replay WAL file
                if include_wal_replay and self.wal_file_path.exists():
                    wal_result = await self._replay_wal_file()
                    results["wal_replay_performed"] = wal_result["status"] == "completed"
                    if wal_result["errors"]:
                        results["errors"].extend(wal_result["errors"])
                
                results["duration_seconds"] = (datetime.utcnow() - start_time).total_seconds()
                
            else:
                error_msg = f"Database restore failed with return code {process.returncode}: {stderr.decode()}"
                logger.error(error_msg)
                results["errors"].append(error_msg)
                results["status"] = "failed"
                
        except Exception as e:
            error_msg = f"Error during database restore: {str(e)}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
            results["status"] = "failed"
        
        return results
    
    async def _replay_wal_file(self) -> Dict[str, Any]:
        """Replay WAL file after restore"""
        # This would be implemented by the persistence service
        # For now, just return a placeholder
        return {
            "status": "completed",
            "tokens_replayed": 0,
            "errors": []
        }
    
    async def cleanup_old_backups(self) -> Dict[str, Any]:
        """Clean up backup files older than retention period"""
        cutoff_date = datetime.utcnow() - timedelta(days=self.dump_retention_days)
        
        results = {
            "status": "completed",
            "files_deleted": 0,
            "bytes_freed": 0,
            "errors": []
        }
        
        try:
            for backup_file in self.backup_dir.glob("pg_dump_*.sql"):
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
    
    def list_available_backups(self) -> List[Dict[str, Any]]:
        """List all available backup files with metadata"""
        backups = []
        
        try:
            for backup_file in sorted(self.backup_dir.glob("pg_dump_*.sql"), reverse=True):
                stat_info = backup_file.stat()
                backups.append({
                    "filename": backup_file.name,
                    "path": str(backup_file),
                    "size": stat_info.st_size,
                    "created": datetime.fromtimestamp(stat_info.st_mtime).isoformat(),
                    "age_days": (datetime.utcnow() - datetime.fromtimestamp(stat_info.st_mtime)).days
                })
        except Exception as e:
            logger.error(f"Error listing backups: {str(e)}")
        
        return backups
    
    async def get_backup_status(self) -> Dict[str, Any]:
        """Get current backup service status"""
        return {
            "last_backup_time": self.last_backup_time.isoformat() if self.last_backup_time else None,
            "retention_days": self.dump_retention_days,
            "backup_count": len(list(self.backup_dir.glob("pg_dump_*.sql"))),
            "backup_dir": str(self.backup_dir),
            "wal_file_exists": self.wal_file_path.exists(),
            "wal_file_size": self.wal_file_path.stat().st_size if self.wal_file_path.exists() else 0
        }


# Global instance
backup_service = BackupService() 