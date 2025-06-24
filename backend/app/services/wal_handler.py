"""
FD 4.1 & 4.4: WAL File Handler
Implements WAL-Lite file format and write operations with rotation as specified in FSD.
"""

import json
import os
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Iterator, Dict, Any, Optional
from app.services.data_structures import Token
from app.services.persistence_exceptions import WALError, DiskFullError, WALCorruptionError
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class WALHandler:
    """
    FD 4.1 & 4.4: WAL-Lite file handler
    - One JSON per line file format
    - File rotation at 100 MiB
    - UTF-8 encoding with newline escaping
    """
    
    def __init__(self, 
                 wal_file_path: str = "/app/data/tokens.wal",
                 max_file_size_bytes: int = 100 * 1024 * 1024,  # 100 MiB
                 buffer_size: int = 1048576):  # 1 MiB buffer as per FSD
        
        self.wal_file_path = Path(wal_file_path)
        self.max_file_size_bytes = max_file_size_bytes
        self.buffer_size = buffer_size
        
        # Ensure WAL directory exists
        self.wal_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # WAL statistics
        self.total_writes = 0
        self.total_tokens_written = 0
        self.total_rotations = 0
        self.last_write_time: Optional[datetime] = None
        
        logger.info(f"WAL handler initialized: {self.wal_file_path} (max size: {self.max_file_size_bytes} bytes)")
    
    async def write_batch(self, tokens: List[Token]) -> None:
        """
        FD 4.4: Write token batch to WAL file
        - One JSON per line format
        - File rotation at 100 MiB threshold
        - UTF-8 encoding with buffering
        """
        if not tokens:
            return
        
        logger.debug(f"Writing batch of {len(tokens)} tokens to WAL")
        
        try:
            # Check if rotation is needed before writing
            await self._check_and_rotate_if_needed()
            
            # FD 4.1: Convert tokens to JSON lines
            json_lines = []
            for token in tokens:
                json_data = self._token_to_wal_format(token)
                json_line = json.dumps(json_data, separators=(',', ':'), ensure_ascii=False)
                json_lines.append(json_line)
            
            # FD 4.4: Write with specified buffering
            await self._write_lines_to_file(json_lines)
            
            # Update statistics
            self.total_writes += 1
            self.total_tokens_written += len(tokens)
            self.last_write_time = datetime.utcnow()
            
            logger.debug(f"Successfully wrote {len(tokens)} tokens to WAL")
            
        except OSError as e:
            if "No space left on device" in str(e) or e.errno == 28:  # ENOSPC
                raise DiskFullError(str(self.wal_file_path), e)
            else:
                raise WALError("write", e, str(self.wal_file_path))
        except Exception as e:
            raise WALError("write", e, str(self.wal_file_path))
    
    def _token_to_wal_format(self, token: Token) -> Dict[str, Any]:
        """
        FD 4.1: Convert Token to WAL JSON format
        Fields: request_id, attempt_seq, token_index, model_id, token_text, iso_ts
        Short field names to minimize file size
        """
        # FD 4.1: Escape newlines in token text
        escaped_text = token.text.replace('\n', ' ').replace('\r', ' ')
        
        return {
            "r": token.request_id,
            "a": token.attempt_seq,
            "i": token.index,
            "m": token.model_id,
            "t": escaped_text,
            "ts": token.timestamp.isoformat()
        }
    
    def _wal_format_to_token(self, wal_data: Dict[str, Any]) -> Token:
        """Convert WAL JSON format back to Token object"""
        return Token(
            model_id=wal_data["m"],
            text=wal_data["t"],
            index=wal_data["i"],
            timestamp=datetime.fromisoformat(wal_data["ts"]),
            request_id=wal_data["r"],
            attempt_seq=wal_data["a"]
        )
    
    async def _write_lines_to_file(self, json_lines: List[str]) -> None:
        """Write JSON lines to WAL file with proper buffering"""
        def _write_sync():
            with open(self.wal_file_path, 'a', encoding='utf-8', buffering=self.buffer_size) as f:
                for line in json_lines:
                    f.write(line + '\n')
                f.flush()  # Ensure data is written to disk
        
        # Run file I/O in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _write_sync)
    
    async def _check_and_rotate_if_needed(self) -> None:
        """
        FD 4.4: Check file size and rotate if >= 100 MiB
        Rotation: close and rename to wal-YYYYMMDDHHMM.bak
        """
        try:
            if not self.wal_file_path.exists():
                return
            
            file_size = self.wal_file_path.stat().st_size
            
            if file_size >= self.max_file_size_bytes:
                await self._rotate_wal_file()
                
        except OSError as e:
            logger.warning(f"Error checking WAL file size: {str(e)}")
    
    async def _rotate_wal_file(self) -> None:
        """
        FD 4.4: Rotate WAL file by renaming to wal-YYYYMMDDHHMM.bak
        """
        if not self.wal_file_path.exists():
            return
        
        try:
            # Generate backup filename with timestamp
            timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
            backup_name = f"wal-{timestamp}.bak"
            backup_path = self.wal_file_path.parent / backup_name
            
            def _rotate_sync():
                # Rename current WAL file to backup
                self.wal_file_path.rename(backup_path)
            
            # Run file operation in thread pool
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _rotate_sync)
            
            self.total_rotations += 1
            file_size = backup_path.stat().st_size
            
            logger.info(f"WAL file rotated: {backup_name} ({file_size} bytes)")
            
        except OSError as e:
            raise WALError("rotate", e, str(self.wal_file_path))
    
    async def read_lines(self) -> Iterator[str]:
        """
        FD 4.5: Read lines from WAL file for replay
        Returns iterator of JSON line strings
        """
        if not self.wal_file_path.exists():
            return
        
        try:
            def _read_sync():
                lines = []
                with open(self.wal_file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line:  # Skip empty lines
                            lines.append(line)
                return lines
            
            # Run file I/O in thread pool
            loop = asyncio.get_event_loop()
            lines = await loop.run_in_executor(None, _read_sync)
            
            for line in lines:
                yield line
                
        except OSError as e:
            raise WALError("read", e, str(self.wal_file_path))
    
    async def parse_wal_line(self, line: str) -> Token:
        """
        Parse a single WAL line into a Token object
        Validates JSON format and required fields
        """
        try:
            data = json.loads(line)
            
            # Validate required fields (FD 4.1)
            required_fields = {"r", "a", "i", "m", "t", "ts"}
            if not all(field in data for field in required_fields):
                missing = required_fields - set(data.keys())
                raise WALCorruptionError(str(self.wal_file_path), f"Missing fields: {missing}")
            
            return self._wal_format_to_token(data)
            
        except json.JSONDecodeError as e:
            raise WALCorruptionError(str(self.wal_file_path), f"Invalid JSON: {str(e)}")
        except KeyError as e:
            raise WALCorruptionError(str(self.wal_file_path), f"Missing field: {str(e)}")
        except Exception as e:
            raise WALCorruptionError(str(self.wal_file_path), f"Parse error: {str(e)}")
    
    async def truncate_file(self) -> None:
        """
        FD 4.5: Truncate WAL file after successful replay
        """
        try:
            def _truncate_sync():
                if self.wal_file_path.exists():
                    self.wal_file_path.unlink()  # Delete file (equivalent to truncation)
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _truncate_sync)
            
            logger.info("WAL file truncated after successful replay")
            
        except OSError as e:
            raise WALError("truncate", e, str(self.wal_file_path))
    
    def get_file_size_bytes(self) -> int:
        """Get current WAL file size in bytes"""
        try:
            if self.wal_file_path.exists():
                return self.wal_file_path.stat().st_size
            return 0
        except OSError:
            return 0
    
    def get_wal_status(self) -> Dict[str, Any]:
        """Get comprehensive WAL status for monitoring"""
        return {
            "file_path": str(self.wal_file_path),
            "file_exists": self.wal_file_path.exists(),
            "file_size_bytes": self.get_file_size_bytes(),
            "max_file_size_bytes": self.max_file_size_bytes,
            "buffer_size": self.buffer_size,
            "statistics": {
                "total_writes": self.total_writes,
                "total_tokens_written": self.total_tokens_written,
                "total_rotations": self.total_rotations,
                "last_write_time": self.last_write_time.isoformat() if self.last_write_time else None
            }
        }
    
    async def validate_wal_file(self) -> Dict[str, Any]:
        """
        Validate WAL file integrity
        Returns validation results with any issues found
        """
        validation_result = {
            "valid": True,
            "line_count": 0,
            "token_count": 0,
            "issues": []
        }
        
        if not self.wal_file_path.exists():
            return validation_result
        
        try:
            line_number = 0
            async for line in self.read_lines():
                line_number += 1
                try:
                    token = await self.parse_wal_line(line)
                    validation_result["token_count"] += 1
                except WALCorruptionError as e:
                    validation_result["valid"] = False
                    validation_result["issues"].append({
                        "line": line_number,
                        "error": str(e),
                        "content": line[:100] + "..." if len(line) > 100 else line
                    })
            
            validation_result["line_count"] = line_number
            
        except Exception as e:
            validation_result["valid"] = False
            validation_result["issues"].append({
                "error": f"File read error: {str(e)}"
            })
        
        return validation_result
    
    async def cleanup_old_backups(self, max_age_days: int = 7) -> List[str]:
        """
        Clean up old WAL backup files
        Returns list of deleted backup files
        """
        deleted_files = []
        backup_pattern = "wal-*.bak"
        cutoff_time = datetime.utcnow().timestamp() - (max_age_days * 24 * 3600)
        
        try:
            backup_dir = self.wal_file_path.parent
            for backup_file in backup_dir.glob(backup_pattern):
                try:
                    if backup_file.stat().st_mtime < cutoff_time:
                        backup_file.unlink()
                        deleted_files.append(backup_file.name)
                        logger.info(f"Deleted old WAL backup: {backup_file.name}")
                except OSError as e:
                    logger.warning(f"Failed to delete backup {backup_file.name}: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Error cleaning up WAL backups: {str(e)}")
        
        return deleted_files 