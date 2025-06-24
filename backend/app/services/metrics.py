"""
FD 6: Health & Metrics Service
Implements metrics collection (buffer_len, wal_size, flush_ms) and health endpoint formatting.
"""

import time
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.db.database import AsyncSessionLocal
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class MetricsService:
    """Service to collect and format system metrics as specified in FD 6"""
    
    def __init__(self):
        self.wal_file_path = Path("/app/data/tokens.wal")
        self.last_flush_duration_ms: Optional[float] = None
        self.last_db_write_time: Optional[datetime] = None
        self.buffer_length: int = 0
        self.attempts_total: int = 0
        
        # Mock buffer for demonstration (would be replaced by actual token buffer)
        self._mock_buffer = []
    
    async def collect_metrics(self) -> Dict[str, Any]:
        """
        FD 6.1: Collect core metrics - buffer_len, wal_size, flush_ms
        Returns the metrics as specified in the FSD
        """
        logger.debug("Collecting core metrics for FD 6.1")
        
        try:
            # Get buffer length (from in-memory token buffer)
            buffer_len = await self._get_buffer_length()
            
            # Get WAL file size in bytes
            wal_size_bytes = self._get_wal_size_bytes()
            
            # Get last flush duration in milliseconds
            last_flush_ms = self._get_last_flush_duration_ms()
            
            # Get last DB write timestamp
            last_db_write = await self._get_last_db_write_time()
            
            # Get total attempts count
            attempts_total = await self._get_attempts_total()
            
            metrics = {
                "buffer_len": buffer_len,
                "wal_size_bytes": wal_size_bytes,
                "last_flush_ms": last_flush_ms,
                "last_db_write": last_db_write,
                "attempts_total": attempts_total,
                "collection_timestamp": datetime.utcnow().isoformat()
            }
            
            logger.debug(f"Metrics collected: {metrics}")
            return metrics
            
        except Exception as e:
            logger.error(f"Error collecting metrics: {str(e)}")
            return {
                "buffer_len": 0,
                "wal_size_bytes": 0,
                "last_flush_ms": 0,
                "last_db_write": None,
                "attempts_total": 0,
                "collection_timestamp": datetime.utcnow().isoformat(),
                "error": str(e)
            }
    
    async def get_health_status(self) -> Dict[str, Any]:
        """
        FD 6.2: Format health endpoint as specified in FSD section 5.6
        Returns exact format: providers, db_ok, buffer_len, last_flush_ms, wal_size_bytes, last_db_write
        """
        logger.debug("Collecting health status for FD 6.2")
        
        # Get core metrics
        metrics = await self.collect_metrics()
        
        # Get provider circuit breaker status (FD 2 integration)
        providers_status = await self._get_providers_circuit_breaker_status()
        
        # Check database connectivity
        db_ok = await self._check_database_ok()
        
        # Format response exactly as specified in FSD section 5.6
        health_response = {
            "providers": providers_status,
            "db_ok": db_ok,
            "buffer_len": metrics.get("buffer_len", 0),
            "last_flush_ms": metrics.get("last_flush_ms", 0),
            "wal_size_bytes": metrics.get("wal_size_bytes", 0),
            "last_db_write": metrics.get("last_db_write")
        }
        
        return health_response
    
    def format_prometheus_metrics(self, metrics: Dict[str, Any]) -> str:
        """
        FD 6.3: Optional Prometheus formatter for metrics endpoint
        Formats metrics in Prometheus exposition format
        """
        logger.debug("Formatting metrics for Prometheus")
        
        timestamp = int(time.time() * 1000)  # Prometheus timestamp in milliseconds
        
        prometheus_output = []
        
        # Core metrics as specified in FSD section 9
        prometheus_output.extend([
            "# HELP llm_buffer_len Current length of in-memory token buffer",
            "# TYPE llm_buffer_len gauge",
            f"llm_buffer_len {metrics.get('buffer_len', 0)} {timestamp}",
            "",
            "# HELP llm_wal_size_bytes Size of WAL file in bytes", 
            "# TYPE llm_wal_size_bytes gauge",
            f"llm_wal_size_bytes {metrics.get('wal_size_bytes', 0)} {timestamp}",
            "",
            "# HELP llm_attempts_total Total number of LLM provider attempts",
            "# TYPE llm_attempts_total counter", 
            f"llm_attempts_total {metrics.get('attempts_total', 0)} {timestamp}",
            "",
            "# HELP llm_last_flush_duration_ms Duration of last buffer flush in milliseconds",
            "# TYPE llm_last_flush_duration_ms gauge",
            f"llm_last_flush_duration_ms {metrics.get('last_flush_ms', 0)} {timestamp}",
            ""
        ])
        
        return "\n".join(prometheus_output)
    
    async def _get_buffer_length(self) -> int:
        """Get current in-memory buffer length"""
        # FD 4: Try to get from persistence service if available
        try:
            # Import here to avoid circular imports at startup
            from app.main import app
            persistence_service = getattr(app.state, 'persistence_service', None)
            
            if persistence_service:
                # Buffer manager is per-request, so we can't get current length
                # Return 0 for now (would need request-specific buffer access)
                return 0
            else:
                # Fallback to mock data
                return len(self._mock_buffer)
                
        except Exception as e:
            logger.debug(f"Using mock buffer length: {str(e)}")
            return len(self._mock_buffer)
    
    def _get_wal_size_bytes(self) -> int:
        """Get WAL file size in bytes from FD 4 persistence service"""
        try:
            # FD 4: Try to get from persistence service first
            from app.main import app
            persistence_service = getattr(app.state, 'persistence_service', None)
            
            if persistence_service:
                return persistence_service.get_wal_file_size_bytes()
            else:
                # Fallback to direct file check
                if self.wal_file_path.exists():
                    return self.wal_file_path.stat().st_size
                return 0
                
        except Exception as e:
            logger.error(f"Error getting WAL file size: {str(e)}")
            return 0
    
    def _get_last_flush_duration_ms(self) -> float:
        """Get last flush duration in milliseconds from FD 4 persistence service"""
        try:
            # FD 4: Try to get from persistence service first
            from app.main import app
            persistence_service = getattr(app.state, 'persistence_service', None)
            
            if persistence_service:
                # Get duration from persistence service stats (would need async version)
                return self.last_flush_duration_ms or 0
            else:
                return self.last_flush_duration_ms or 0
                
        except Exception as e:
            logger.debug(f"Using fallback flush duration: {str(e)}")
            return self.last_flush_duration_ms or 0
    
    async def _get_last_db_write_time(self) -> Optional[str]:
        """Get timestamp of last database write from FD 4 persistence service"""
        try:
            # FD 4: Try to get from persistence service first
            from app.main import app
            persistence_service = getattr(app.state, 'persistence_service', None)
            
            if persistence_service:
                return persistence_service.get_last_db_write_time()
            
        except Exception as e:
            logger.debug(f"Error getting last DB write from persistence service: {str(e)}")
        
        # Fallback: direct database query
        try:
            async with AsyncSessionLocal() as session:
                # Get most recent token log entry
                query = text("""
                    SELECT MAX(ts) as last_write 
                    FROM llm_token_log
                """)
                result = await session.execute(query)
                row = result.fetchone()
                
                if row and row.last_write:
                    return row.last_write.isoformat()
                    
        except SQLAlchemyError as e:
            logger.error(f"Error getting last DB write time: {str(e)}")
        
        return None
    
    async def _get_attempts_total(self) -> int:
        """Get total number of attempts"""
        try:
            async with AsyncSessionLocal() as session:
                query = text("SELECT COUNT(*) as total FROM llm_attempts")
                result = await session.execute(query)
                row = result.fetchone()
                return row.total if row else 0
        except SQLAlchemyError as e:
            logger.error(f"Error getting attempts total: {str(e)}")
            return 0
    
    async def _get_providers_circuit_breaker_status(self) -> Dict[str, str]:
        """
        FD 2 Integration: Get provider circuit breaker status for health endpoint
        Returns provider states as per FSD section 5.6 format
        """
        try:
            # Import here to avoid circular imports
            from app.services.circuit_breaker import circuit_breaker_service
            
            providers_status = {}
            
            # Get status for all known providers
            for provider in ["openai", "anthropic", "google_ai", "deepseek", "cohere"]:
                cb_status = circuit_breaker_service.get_status(provider)
                
                if cb_status:
                    # Map circuit breaker states to FSD health format
                    state_mapping = {
                        "closed": "closed",
                        "open": "open", 
                        "half_open": "half-open"
                    }
                    providers_status[provider] = state_mapping.get(cb_status.state.value, "closed")
                else:
                    providers_status[provider] = "closed"  # Default state
            
            return providers_status
            
        except Exception as e:
            logger.error(f"Error getting provider circuit breaker status: {str(e)}")
            # Return default closed state for all providers
            return {
                "openai": "closed",
                "anthropic": "closed", 
                "google_ai": "closed",
                "deepseek": "closed",
                "cohere": "closed"
            }
    
    async def _check_database_ok(self) -> bool:
        """Check if database is accessible"""
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"Database connectivity check failed: {str(e)}")
            return False
    
    # Methods to update metrics from other services
    
    def update_buffer_length(self, length: int):
        """Update buffer length metric"""
        self.buffer_length = length
        logger.debug(f"Buffer length updated to: {length}")
    
    def record_flush_duration(self, duration_ms: float):
        """Record flush duration in milliseconds"""
        self.last_flush_duration_ms = duration_ms
        logger.debug(f"Flush duration recorded: {duration_ms}ms")
    
    def record_db_write(self):
        """Record database write timestamp"""
        self.last_db_write_time = datetime.utcnow()
        logger.debug(f"DB write recorded at: {self.last_db_write_time}")
    
    def add_mock_buffer_item(self, item: Any):
        """Add item to mock buffer (for testing)"""
        self._mock_buffer.append(item)
    
    def clear_mock_buffer(self):
        """Clear mock buffer (for testing)"""
        self._mock_buffer.clear()


# Global instance
metrics_service = MetricsService() 