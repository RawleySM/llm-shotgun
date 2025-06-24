from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.utils.logger import setup_logger
from app.routes.health import router as health_router
from app.routes.auth import router as auth_router
from app.routes.admin import router as admin_router
from app.db.database import init_db, engine
from app.config import get_settings

# Import FD services
from app.services.consistency import consistency_service
from app.services.shutdown import shutdown_service
from app.services.retention import retention_service
from app.services.backup import backup_service
from app.services.fallback import fallback_service  # FD 5
from app.services.metrics import metrics_service    # FD 6
from app.services.concurrency_safety import concurrency_safety_service  # FD 2
from app.services.circuit_breaker import circuit_breaker_service  # FD 2
from app.services.provider_semaphore import provider_semaphore_service  # FD 2
from app.services.token_generation_pipeline import token_generation_pipeline  # FD 3
from app.services.persistence_service import PersistenceService  # FD 4

settings = get_settings()
logger = setup_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for the FastAPI application.
    Handles startup and shutdown events with FD services integration.
    """
    # Startup
    logger.info("Starting application with FD services (FD 2, 3, 4, 5-11)")
    try:
        # FD 8.1: Setup signal handlers for graceful shutdown
        shutdown_service.setup_signal_handlers()
        
        # Initialize database
        await init_db()
        
        # FD 7: Run boot-time consistency check
        consistency_results = await consistency_service.run_boot_consistency_check()
        if consistency_results.get("errors"):
            logger.warning(f"Boot consistency check had issues: {consistency_results['errors']}")
        
        # FD 4: Initialize persistence service with WAL-Lite and replay loop
        logger.info("FD 4: Initializing persistence service")
        persistence_service = PersistenceService(
            wal_file_path="/app/data/tokens.wal",
            enable_replay_loop=True
        )
        
        # Start persistence service and WAL replay loop
        await persistence_service.start()
        
        # Store persistence service in app state for access by routes
        app.state.persistence_service = persistence_service
        
        # Validate persistence integrity
        persistence_validation = await persistence_service.validate_persistence_integrity()
        if not persistence_validation["valid"]:
            logger.warning(f"Persistence validation issues: {persistence_validation['issues']}")
        else:
            logger.info("FD 4: Persistence service validation passed")
        
        # FD 2: Initialize concurrency and provider safety services
        logger.info("FD 2: Circuit breakers and semaphores initialized")
        logger.info(f"Provider semaphore status: {provider_semaphore_service.get_all_semaphore_statuses()}")
        
        # FD 3: Initialize token generation pipeline with persistence service
        logger.info("FD 3: Connecting pipeline to persistence service")
        token_generation_pipeline.persistence_service = persistence_service
        
        pipeline_validation = await token_generation_pipeline.validate_pipeline_components()
        if not pipeline_validation["valid"]:
            logger.warning(f"Pipeline validation issues: {pipeline_validation['issues']}")
        else:
            logger.info("FD 3: Token generation pipeline validation passed")
        
        # FD 6: Initialize metrics collection
        logger.info("Initializing FD 6 metrics collection")
        # Add some mock data to demonstrate buffer functionality
        metrics_service.add_mock_buffer_item({"token": "test", "timestamp": "2025-01-06T00:00:00Z"})
        metrics_service.record_flush_duration(110.5)  # Example flush duration
        metrics_service.record_db_write()
        
        # FD 5: Log fallback queue initialization
        logger.info(f"FD 5 fallback queue initialized: {fallback_service.get_fallback_queue()}")
        
        # Register shutdown callbacks for services  
        shutdown_service.register_shutdown_callback(flush_buffers_on_shutdown)
        shutdown_service.register_shutdown_callback(stop_persistence_service_on_shutdown)
        shutdown_service.register_shutdown_callback(close_wal_files_on_shutdown)
        shutdown_service.register_shutdown_callback(cleanup_services_on_shutdown)
        
        # Log startup summary
        startup_summary = {
            "fd_2_providers": len(provider_semaphore_service.get_all_semaphore_statuses()),
            "fd_3_pipeline_valid": pipeline_validation["valid"],
            "fd_4_persistence_valid": persistence_validation["valid"],
            "fd_4_wal_replay_running": persistence_service.wal_replay.is_running,
            "fd_5_fallback_models": len(fallback_service.get_fallback_queue()),
            "fd_6_metrics_active": True
        }
        logger.info(f"Application started successfully with all FD services: {startup_summary}")
        yield
        
    except Exception as e:
        logger.error(f"Error during startup: {str(e)}")
        raise
    finally:
        # Cleanup - FD 8: Execute graceful shutdown sequence
        logger.info("Shutting down application")
        
        if shutdown_service.shutdown_initiated:
            shutdown_results = await shutdown_service.execute_shutdown_sequence()
            logger.info(f"Graceful shutdown completed: {shutdown_results}")
        
        await engine.dispose()


async def flush_buffers_on_shutdown():
    """FD 8.2: Flush in-memory buffers during shutdown"""
    logger.info("Flushing buffers during shutdown")
    
    # FD 3: No active buffers to flush since BufferManager is per-request
    # But we can reset pipeline statistics for clean restart
    pipeline_stats = token_generation_pipeline.get_pipeline_status()
    logger.info(f"FD 3 pipeline final stats: {pipeline_stats['statistics']}")
    
    # FD 6: Clear mock buffer and record final metrics
    metrics_service.clear_mock_buffer()
    metrics_service.record_flush_duration(0)  # Final flush


async def stop_persistence_service_on_shutdown():
    """FD 8.2: Stop persistence service and flush remaining data"""
    logger.info("Stopping persistence service during shutdown")
    
    try:
        # Get persistence service from app state
        persistence_service = getattr(app.state, 'persistence_service', None)
        if persistence_service:
            # Stop the WAL replay loop gracefully
            await persistence_service.stop()
            
            # Log final persistence statistics
            final_status = await persistence_service.get_persistence_status()
            logger.info(f"FD 4 final persistence stats: {final_status['statistics']}")
        else:
            logger.warning("Persistence service not found during shutdown")
            
    except Exception as e:
        logger.error(f"Error stopping persistence service: {str(e)}")


async def close_wal_files_on_shutdown():
    """FD 8.3: Close WAL files during shutdown"""
    logger.info("Closing WAL files during shutdown")
    
    try:
        # FD 4: Use persistence service WAL handler if available
        persistence_service = getattr(app.state, 'persistence_service', None)
        if persistence_service:
            wal_size = persistence_service.get_wal_file_size_bytes()
            if wal_size > 0:
                logger.info(f"WAL file size at shutdown: {wal_size} bytes")
                # File will be handled by WAL replay loop next startup
        
        # FD 9: Legacy WAL rotation (if still used)
        retention_service.rotate_wal_file()
        
    except Exception as e:
        logger.error(f"Error closing WAL files: {str(e)}")


async def cleanup_services_on_shutdown():
    """Additional service cleanup during shutdown"""
    logger.info("Cleaning up FD 2, 3, 5 & 6 services during shutdown")
    
    # FD 5: Reset fallback statistics for clean restart
    fallback_service.reset_statistics()
    
    # FD 3: Reset pipeline statistics for clean restart
    token_generation_pipeline.reset_statistics()
    
    logger.info("FD services cleanup completed")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=settings.APP_DESCRIPTION,
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health_router, prefix="/api")        # FD 6: Health & Metrics endpoints
app.include_router(auth_router, prefix="/api")
app.include_router(admin_router, prefix="/api/admin")   # FD 11: Administrative Controls + FD 2, 3, 5 management

logger.info("Application routes configured with all FD services (FD 2, 3, 5-11)")
