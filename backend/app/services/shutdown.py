"""
FD 8: Graceful Shutdown Service
Implements graceful shutdown handling with buffer flushing and connection cleanup.
"""

import asyncio
import signal
from typing import Dict, Any, Optional, List
from datetime import datetime
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class ShutdownService:
    """Service to handle graceful shutdown procedures"""
    
    def __init__(self):
        self.shutdown_initiated = False
        self.shutdown_callbacks: List[callable] = []
        self.accepting_requests = True
        self.shutdown_start_time: Optional[datetime] = None
    
    def register_shutdown_callback(self, callback: callable):
        """Register a callback to be executed during shutdown"""
        self.shutdown_callbacks.append(callback)
        logger.debug(f"Registered shutdown callback: {callback.__name__}")
    
    def is_accepting_requests(self) -> bool:
        """Check if the service is still accepting new requests"""
        return self.accepting_requests
    
    def initiate_shutdown(self):
        """
        FD 8.1: Initiate graceful shutdown sequence
        Stop accepting new requests
        """
        if self.shutdown_initiated:
            logger.warning("Shutdown already initiated")
            return
        
        self.shutdown_initiated = True
        self.accepting_requests = False
        self.shutdown_start_time = datetime.utcnow()
        logger.info("Graceful shutdown initiated - stopping acceptance of new requests")
    
    async def execute_shutdown_sequence(self) -> Dict[str, Any]:
        """
        FD 8.1, 8.2, 8.3: Execute complete graceful shutdown sequence
        Returns status of shutdown operations
        """
        if not self.shutdown_initiated:
            logger.warning("Shutdown sequence called but shutdown not initiated")
            return {"status": "not_initiated"}
        
        logger.info("Executing graceful shutdown sequence")
        
        results = {
            "status": "completed",
            "buffer_flushed": False,
            "wal_closed": False,
            "connections_closed": False,
            "callbacks_executed": 0,
            "errors": []
        }
        
        try:
            # Execute all registered shutdown callbacks
            for callback in self.shutdown_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback()
                    else:
                        callback()
                    results["callbacks_executed"] += 1
                    logger.debug(f"Executed shutdown callback: {callback.__name__}")
                except Exception as e:
                    error_msg = f"Error executing shutdown callback {callback.__name__}: {str(e)}"
                    logger.error(error_msg)
                    results["errors"].append(error_msg)
            
            # Wait a moment for any final operations
            await asyncio.sleep(0.5)
            
            logger.info("Graceful shutdown sequence completed")
            
        except Exception as e:
            error_msg = f"Error during shutdown sequence: {str(e)}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
            results["status"] = "failed"
        
        return results
    
    def setup_signal_handlers(self):
        """
        FD 8.1: Setup signal handlers for graceful shutdown
        """
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown")
            self.initiate_shutdown()
        
        # Register signal handlers
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
        
        logger.info("Signal handlers registered for graceful shutdown")
    
    def get_shutdown_status(self) -> Dict[str, Any]:
        """Get current shutdown status for monitoring"""
        return {
            "shutdown_initiated": self.shutdown_initiated,
            "accepting_requests": self.accepting_requests,
            "shutdown_start_time": self.shutdown_start_time.isoformat() if self.shutdown_start_time else None,
            "registered_callbacks": len(self.shutdown_callbacks)
        }


# Global instance
shutdown_service = ShutdownService() 