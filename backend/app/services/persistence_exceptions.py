"""
FD 4: Persistence Layer Exceptions
Custom exceptions for WAL-Lite fallback and database persistence errors.
"""

from typing import Optional


class PersistenceError(Exception):
    """Base exception for persistence layer errors"""
    pass


class PersistenceDeferred(PersistenceError):
    """
    FD 4.2: Raised when batch persistence fails and is deferred to WAL-Lite
    Indicates tokens were written to WAL file for later replay
    """
    
    def __init__(self, original_error: Exception, wal_file: str = "tokens.wal"):
        self.original_error = original_error
        self.wal_file = wal_file
        super().__init__(f"Persistence deferred to {wal_file}: {str(original_error)}")


class WALError(PersistenceError):
    """Error in WAL file operations"""
    
    def __init__(self, operation: str, error: Exception, wal_file: str = "tokens.wal"):
        self.operation = operation
        self.original_error = error
        self.wal_file = wal_file
        super().__init__(f"WAL {operation} error in {wal_file}: {str(error)}")


class WALReplayError(PersistenceError):
    """Error during WAL replay operations"""
    
    def __init__(self, line_number: int, line_content: str, error: Exception):
        self.line_number = line_number
        self.line_content = line_content
        self.original_error = error
        super().__init__(f"WAL replay error at line {line_number}: {str(error)}")


class DatabaseUnavailableError(PersistenceError):
    """Database is not available for operations"""
    
    def __init__(self, operation: str, error: Exception):
        self.operation = operation
        self.original_error = error
        super().__init__(f"Database unavailable for {operation}: {str(error)}")


class DiskFullError(PersistenceError):
    """Disk space exhausted - fatal error"""
    
    def __init__(self, path: str, error: Exception):
        self.path = path
        self.original_error = error
        super().__init__(f"Disk full at {path}: {str(error)}")


class WALCorruptionError(PersistenceError):
    """WAL file corruption detected"""
    
    def __init__(self, wal_file: str, details: str):
        self.wal_file = wal_file
        self.details = details
        super().__init__(f"WAL corruption in {wal_file}: {details}") 