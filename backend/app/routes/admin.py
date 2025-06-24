"""
Administrative Routes
Implements FD 11 administrative endpoints for system management.
"""

from fastapi import APIRouter, HTTPException, Path, Body
from typing import Dict, Any, Optional
from app.utils.logger import setup_logger
from app.services.admin import admin_service
from app.services.retention import retention_service
from app.services.backup import backup_service
from app.services.fallback import fallback_service
from app.services.llm_demo import llm_demo_service
from app.services.concurrency_safety import concurrency_safety_service
from app.services.circuit_breaker import circuit_breaker_service
from app.services.provider_semaphore import provider_semaphore_service
from app.services.data_structures import RequestCtx
from app.services.token_generation_pipeline import token_generation_pipeline
from app.services.persistence_service import PersistenceService
from app.services.token_builder import TokenBuilder
from app.services.buffer_manager import BufferManager
from app.services.error_router import ErrorRouter
from app.services.provider_adaptor import ProviderAdaptor

router = APIRouter()
logger = setup_logger(__name__)


@router.get("/requests/{request_id}", tags=["Admin"])
async def get_request_metadata(
    request_id: str = Path(..., description="The request ID to retrieve metadata for")
):
    """
    FD 11.2: Get metadata and token stream information for a specific request
    """
    logger.info(f"Request metadata endpoint called for request_id: {request_id}")
    
    try:
        metadata = await admin_service.get_request_metadata(request_id)
        
        if metadata is None:
            raise HTTPException(status_code=404, detail=f"Request {request_id} not found")
        
        return metadata
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting request metadata: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get request metadata: {str(e)}")


@router.post("/providers/{provider_name}/enable", tags=["Admin"])
async def enable_provider(
    provider_name: str = Path(..., description="The provider name to enable")
):
    """
    FD 11.3: Enable a specific provider
    """
    logger.info(f"Enable provider endpoint called for provider: {provider_name}")
    
    try:
        result = await admin_service.toggle_provider_status(provider_name, "enable")
        
        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result.get("error"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error enabling provider: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to enable provider: {str(e)}")


@router.post("/providers/{provider_name}/disable", tags=["Admin"])
async def disable_provider(
    provider_name: str = Path(..., description="The provider name to disable")
):
    """
    FD 11.3: Disable a specific provider
    """
    logger.info(f"Disable provider endpoint called for provider: {provider_name}")
    
    try:
        result = await admin_service.toggle_provider_status(provider_name, "disable")
        
        if result.get("status") == "error":
            raise HTTPException(status_code=400, detail=result.get("error"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disabling provider: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to disable provider: {str(e)}")


@router.get("/providers/status", tags=["Provider Safety"])
async def get_provider_status():
    """
    FD 2: Get comprehensive provider status including circuit breakers and semaphores
    """
    logger.info("Provider status endpoint called")
    
    try:
        status = await concurrency_safety_service.get_provider_status()
        return {"providers": status}
        
    except Exception as e:
        logger.error(f"Error getting provider status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get provider status: {str(e)}")


@router.post("/providers/{provider_name}/reset", tags=["Provider Safety"])
async def reset_provider_circuit_breaker(
    provider_name: str = Path(..., description="The provider name to reset")
):
    """
    FD 2: Reset circuit breaker for a specific provider
    """
    logger.info(f"Reset circuit breaker endpoint called for provider: {provider_name}")
    
    try:
        await concurrency_safety_service.reset_provider(provider_name)
        return {
            "status": "success",
            "provider": provider_name,
            "message": f"Circuit breaker reset for {provider_name}"
        }
        
    except Exception as e:
        logger.error(f"Error resetting provider {provider_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to reset provider: {str(e)}")


@router.post("/providers/{provider_name}/probe", tags=["Provider Safety"])
async def probe_provider(
    provider_name: str = Path(..., description="The provider name to probe")
):
    """
    FD 2.5: Manually trigger provider probe to test if it's back online
    """
    logger.info(f"Manual probe endpoint called for provider: {provider_name}")
    
    try:
        success = await concurrency_safety_service.probe_provider(provider_name)
        return {
            "status": "success" if success else "failed",
            "provider": provider_name,
            "probe_result": success,
            "message": f"Probe {'successful' if success else 'failed'} for {provider_name}"
        }
        
    except Exception as e:
        logger.error(f"Error probing provider {provider_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to probe provider: {str(e)}")


@router.get("/providers/{provider_name}/semaphore", tags=["Provider Safety"])
async def get_provider_semaphore_status(
    provider_name: str = Path(..., description="The provider name to check")
):
    """
    FD 2.3: Get semaphore status for a specific provider
    """
    logger.info(f"Semaphore status endpoint called for provider: {provider_name}")
    
    try:
        status = provider_semaphore_service.get_semaphore_status(provider_name)
        config = provider_semaphore_service.get_provider_config(provider_name)
        
        return {
            "provider": provider_name,
            "semaphore": status,
            "config": {
                "max_concurrency": config.max_concurrency if config else 0,
                "can_override_via_env": f"{provider_name.upper()}_CONCURRENCY"
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting semaphore status for {provider_name}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get semaphore status: {str(e)}")


@router.post("/providers/test-call", tags=["Provider Safety"])
async def test_provider_call(
    model: str = Body(..., description="The model to test"),
    prompt: str = Body("Hello, world!", description="Test prompt"),
    request_id: str = Body(None, description="Optional request ID")
):
    """
    FD 2.2: Test the call_model API with a specific model
    """
    logger.info(f"Test provider call for model: {model}")
    
    try:
        import uuid
        from datetime import datetime
        
        # Create request context
        ctx = RequestCtx(
            request_id=request_id or f"test_{uuid.uuid4().hex[:8]}",
            user_id="test_user",
            attempt_seq=1,
            max_retries=3
        )
        
        tokens = []
        async for token in concurrency_safety_service.call_model(model, prompt, ctx):
            tokens.append(token)
            if len(tokens) > 50:  # Limit for testing
                break
        
        provider = concurrency_safety_service.get_provider_for_model(model)
        
        return {
            "status": "success",
            "model": model,
            "provider": provider,
            "request_id": ctx.request_id,
            "tokens_received": len(tokens),
            "sample_tokens": tokens[:10],  # First 10 tokens
            "full_response": "".join(tokens)
        }
        
    except Exception as e:
        logger.error(f"Error testing provider call: {str(e)}")
        return {
            "status": "failed",
            "model": model,
            "error": str(e),
            "error_type": type(e).__name__
        }


@router.get("/pipeline/status", tags=["Token Generation Pipeline"])
async def get_pipeline_status():
    """
    FD 3: Get comprehensive token generation pipeline status
    """
    logger.info("Pipeline status endpoint called")
    
    try:
        status = token_generation_pipeline.get_pipeline_status()
        return status
        
    except Exception as e:
        logger.error(f"Error getting pipeline status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get pipeline status: {str(e)}")


@router.post("/pipeline/test-generation", tags=["Token Generation Pipeline"])
async def test_token_generation(
    model: str = Body(..., description="The model to test"),
    prompt: str = Body("Hello, world!", description="Test prompt"),
    request_id: str = Body(None, description="Optional request ID"),
    collect_all_tokens: bool = Body(True, description="Whether to collect all tokens for response")
):
    """
    FD 3.1: Test the generate_tokens API with full pipeline
    """
    logger.info(f"Test token generation for model: {model}")
    
    try:
        import uuid
        
        # Create request context
        ctx = RequestCtx(
            request_id=request_id or f"pipeline_test_{uuid.uuid4().hex[:8]}",
            user_id="test_user",
            attempt_seq=1,
            max_retries=3
        )
        
        tokens = []
        start_time = asyncio.get_event_loop().time()
        
        async for token in token_generation_pipeline.generate_tokens(model, prompt, ctx):
            tokens.append({
                "index": token.index,
                "text": token.text,
                "timestamp": token.timestamp.isoformat(),
                "model_id": token.model_id
            })
            
            if not collect_all_tokens and len(tokens) >= 20:  # Limit for response size
                break
        
        elapsed_time = asyncio.get_event_loop().time() - start_time
        
        return {
            "status": "success",
            "model": model,
            "request_id": ctx.request_id,
            "tokens_generated": len(tokens),
            "elapsed_time_seconds": elapsed_time,
            "tokens": tokens,
            "full_response": "".join([t["text"] for t in tokens]),
            "pipeline_stats": token_generation_pipeline.get_pipeline_status()["statistics"]
        }
        
    except Exception as e:
        logger.error(f"Error testing token generation: {str(e)}")
        return {
            "status": "failed",
            "model": model,
            "error": str(e),
            "error_type": type(e).__name__
        }


@router.post("/pipeline/test-with-retries", tags=["Token Generation Pipeline"])
async def test_generation_with_retries(
    model: str = Body(..., description="The model to test"),
    prompt: str = Body("Hello, world!", description="Test prompt"),
    max_attempts: int = Body(3, description="Maximum retry attempts"),
    request_id: str = Body(None, description="Optional request ID")
):
    """
    FD 3.5: Test generation with error handling and retry logic
    """
    logger.info(f"Test generation with retries for model: {model}")
    
    try:
        import uuid
        
        # Create request context
        ctx = RequestCtx(
            request_id=request_id or f"retry_test_{uuid.uuid4().hex[:8]}",
            user_id="test_user",
            attempt_seq=1,
            max_retries=max_attempts
        )
        
        tokens = []
        start_time = asyncio.get_event_loop().time()
        
        async for token in token_generation_pipeline.simulate_generation_with_retries(
            model, prompt, ctx, max_attempts
        ):
            tokens.append({
                "index": token.index,
                "text": token.text,
                "timestamp": token.timestamp.isoformat(),
                "model_id": token.model_id
            })
            
            if len(tokens) >= 30:  # Limit for testing
                break
        
        elapsed_time = asyncio.get_event_loop().time() - start_time
        
        return {
            "status": "success",
            "model": model,
            "request_id": ctx.request_id,
            "max_attempts": max_attempts,
            "final_attempt": ctx.attempt_seq,
            "tokens_generated": len(tokens),
            "elapsed_time_seconds": elapsed_time,
            "tokens": tokens,
            "full_response": "".join([t["text"] for t in tokens]),
            "error_stats": token_generation_pipeline.error_router.get_error_summary()
        }
        
    except Exception as e:
        logger.error(f"Error testing generation with retries: {str(e)}")
        return {
            "status": "failed",
            "model": model,
            "error": str(e),
            "error_type": type(e).__name__,
            "final_attempt": ctx.attempt_seq if 'ctx' in locals() else 0
        }


@router.get("/pipeline/modules/status", tags=["Token Generation Pipeline"])
async def get_pipeline_modules_status():
    """
    FD 3.2: Get status of all pipeline modules (ProviderAdaptor, TokenBuilder, etc.)
    """
    logger.info("Pipeline modules status endpoint called")
    
    try:
        # Get provider adaptor info
        provider_adaptor = ProviderAdaptor()
        provider_info = provider_adaptor.get_all_providers_info()
        provider_validation = provider_adaptor.validate_model_provider_mapping()
        
        # Get error router stats
        error_router = ErrorRouter()
        error_stats = error_router.get_error_summary()
        
        # Get pipeline validation
        pipeline_validation = await token_generation_pipeline.validate_pipeline_components()
        
        return {
            "provider_adaptor": {
                "providers": provider_info,
                "validation": provider_validation
            },
            "error_router": {
                "statistics": error_stats
            },
            "buffer_manager": {
                "config": token_generation_pipeline.buffer_config
            },
            "pipeline_validation": pipeline_validation
        }
        
    except Exception as e:
        logger.error(f"Error getting pipeline modules status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get modules status: {str(e)}")


@router.post("/pipeline/reset-statistics", tags=["Token Generation Pipeline"])
async def reset_pipeline_statistics():
    """
    FD 3: Reset token generation pipeline statistics
    """
    logger.info("Reset pipeline statistics endpoint called")
    
    try:
        token_generation_pipeline.reset_statistics()
        return {
            "status": "success",
            "message": "Pipeline statistics reset successfully"
        }
        
    except Exception as e:
        logger.error(f"Error resetting pipeline statistics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to reset statistics: {str(e)}")


@router.post("/pipeline/validate", tags=["Token Generation Pipeline"])
async def validate_pipeline():
    """
    FD 3: Validate all pipeline components and configuration
    """
    logger.info("Pipeline validation endpoint called")
    
    try:
        validation_result = await token_generation_pipeline.validate_pipeline_components()
        
        if not validation_result["valid"]:
            return {
                "status": "validation_failed",
                "validation": validation_result
            }
        
        return {
            "status": "valid",
            "validation": validation_result
        }
        
    except Exception as e:
        logger.error(f"Error validating pipeline: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to validate pipeline: {str(e)}")


@router.get("/fallback/queue", tags=["Admin"])
async def get_fallback_queue():
    """
    FD 5.1: Get the current fallback queue configuration
    """
    logger.info("Fallback queue endpoint called")
    
    try:
        queue = fallback_service.get_fallback_queue()
        return {
            "fallback_queue": queue,
            "jitter_range": {
                "min_seconds": fallback_service.jitter_min_seconds,
                "max_seconds": fallback_service.jitter_max_seconds
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting fallback queue: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get fallback queue: {str(e)}")


@router.get("/fallback/statistics", tags=["Admin"])
async def get_fallback_statistics():
    """
    FD 5: Get fallback statistics and performance metrics
    """
    logger.info("Fallback statistics endpoint called")
    
    try:
        stats = fallback_service.get_fallback_statistics()
        return stats
        
    except Exception as e:
        logger.error(f"Error getting fallback statistics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get fallback statistics: {str(e)}")


@router.post("/fallback/reset-statistics", tags=["Admin"])
async def reset_fallback_statistics():
    """
    FD 5: Reset fallback statistics (useful for testing or periodic resets)
    """
    logger.info("Reset fallback statistics endpoint called")
    
    try:
        fallback_service.reset_statistics()
        return {"status": "success", "message": "Fallback statistics reset successfully"}
        
    except Exception as e:
        logger.error(f"Error resetting fallback statistics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to reset fallback statistics: {str(e)}")


@router.post("/demo/run-single", tags=["Demo"])
async def run_single_demo(
    prompt: str = Body(..., description="The prompt to send to the LLM"),
    model: str = Body("gpt-4", description="The preferred model to start with")
):
    """
    Demo: Run a single LLM request simulation showing FD 5 and FD 6 in action
    """
    logger.info(f"Single demo request: {model} with prompt: {prompt[:50]}...")
    
    try:
        result = await llm_demo_service.simulate_llm_request(prompt, model)
        return result
        
    except Exception as e:
        logger.error(f"Error running single demo: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Demo failed: {str(e)}")


@router.post("/demo/run-scenarios", tags=["Demo"])
async def run_demo_scenarios():
    """
    Demo: Run multiple LLM request scenarios to showcase FD 5 and FD 6
    """
    logger.info("Running full demo scenarios")
    
    try:
        results = await llm_demo_service.run_demo_scenarios()
        summary = await llm_demo_service.get_demo_summary()
        
        return {
            "demo_results": results,
            "summary": summary
        }
        
    except Exception as e:
        logger.error(f"Error running demo scenarios: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Demo scenarios failed: {str(e)}")


@router.get("/demo/summary", tags=["Demo"])
async def get_demo_summary():
    """
    Demo: Get current FD 5 and FD 6 statistics and metrics
    """
    logger.info("Demo summary endpoint called")
    
    try:
        summary = await llm_demo_service.get_demo_summary()
        return summary
        
    except Exception as e:
        logger.error(f"Error getting demo summary: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get demo summary: {str(e)}")


@router.post("/maintenance/prune", tags=["Admin"])
async def run_manual_prune(
    retention_days: Optional[int] = Body(None, description="Number of days to retain data (default: 180)")
):
    """
    FD 9.1: Manually trigger data pruning operation
    """
    logger.info(f"Manual prune operation triggered with retention_days: {retention_days}")
    
    try:
        result = await retention_service.run_weekly_prune(retention_days)
        
        if result.get("status") == "failed":
            raise HTTPException(status_code=500, detail=f"Prune operation failed: {result.get('errors')}")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during manual prune: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Manual prune failed: {str(e)}")


@router.post("/maintenance/backup", tags=["Admin"])
async def run_manual_backup():
    """
    FD 10.1: Manually trigger backup operation
    """
    logger.info("Manual backup operation triggered")
    
    try:
        result = await backup_service.perform_daily_backup()
        
        if result.get("status") == "failed":
            raise HTTPException(status_code=500, detail=f"Backup operation failed: {result.get('errors')}")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during manual backup: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Manual backup failed: {str(e)}")


@router.get("/maintenance/backups", tags=["Admin"])
async def list_backups():
    """
    FD 10: List available backup files
    """
    logger.info("List backups endpoint called")
    
    try:
        backups = backup_service.list_available_backups()
        return {"backups": backups}
        
    except Exception as e:
        logger.error(f"Error listing backups: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to list backups: {str(e)}")


@router.post("/maintenance/restore/{backup_filename}", tags=["Admin"])
async def restore_from_backup(
    backup_filename: str = Path(..., description="The backup filename to restore from"),
    include_wal_replay: bool = Body(True, description="Whether to include WAL replay after restore")
):
    """
    FD 10.2: Restore database from backup file
    """
    logger.info(f"Restore operation triggered for backup: {backup_filename}")
    
    try:
        # Construct full backup path
        backup_path = f"/app/data/backups/{backup_filename}"
        
        result = await backup_service.restore_from_backup(backup_path, include_wal_replay)
        
        if result.get("status") == "failed":
            raise HTTPException(status_code=500, detail=f"Restore operation failed: {result.get('errors')}")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during restore: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Restore failed: {str(e)}")


@router.get("/system/status", tags=["Admin"])
async def get_system_status():
    """
    Get comprehensive system status including all services
    """
    logger.info("System status endpoint called")
    
    try:
        from app.services.consistency import consistency_service
        from app.services.retention import retention_service
        from app.services.backup import backup_service
        from app.services.shutdown import shutdown_service
        from app.services.metrics import metrics_service
        
        status = {
            "consistency": await consistency_service.get_consistency_status(),
            "retention": await retention_service.get_retention_status(),
            "backup": await backup_service.get_backup_status(),
            "shutdown": shutdown_service.get_shutdown_status(),
            "metrics": await metrics_service.collect_metrics(),
            "fallback": fallback_service.get_fallback_statistics(),
            "providers": await concurrency_safety_service.get_provider_status(),
            "token_pipeline": token_generation_pipeline.get_pipeline_status()
        }
        
        return status
        
    except Exception as e:
        logger.error(f"Error getting system status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get system status: {str(e)}")


# =============================================================================
# FD 4: Persistence Layer Admin Routes
# =============================================================================

@router.get("/persistence/status", tags=["Persistence"])
async def get_persistence_status():
    """Get comprehensive persistence service status"""
    try:
        # Get persistence service from app state
        from app.main import app
        persistence_service = getattr(app.state, 'persistence_service', None)
        if not persistence_service:
            return {"error": "Persistence service not available"}
        
        status = await persistence_service.get_persistence_status()
        return {"persistence_status": status}
    except Exception as e:
        logger.error(f"Persistence status error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Status retrieval failed: {str(e)}")


@router.post("/persistence/test", tags=["Persistence"])
async def test_persistence(token_count: int = Body(5, description="Number of test tokens to persist")):
    """Test persistence with mock tokens"""
    try:
        from app.main import app
        persistence_service = getattr(app.state, 'persistence_service', None)
        if not persistence_service:
            raise HTTPException(status_code=503, detail="Persistence service not available")
        
        result = await persistence_service.manual_persist_test(token_count)
        return {"test_result": result}
    except Exception as e:
        logger.error(f"Persistence test error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Test failed: {str(e)}")


@router.post("/persistence/wal/replay", tags=["Persistence"])
async def force_wal_replay():
    """Force immediate WAL replay"""
    try:
        from app.main import app
        persistence_service = getattr(app.state, 'persistence_service', None)
        if not persistence_service:
            raise HTTPException(status_code=503, detail="Persistence service not available")
        
        result = await persistence_service.force_wal_replay()
        return {"replay_result": result}
    except Exception as e:
        logger.error(f"WAL replay error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Replay failed: {str(e)}")


@router.get("/persistence/wal/status", tags=["Persistence"])
async def get_wal_status():
    """Get WAL file status and statistics"""
    try:
        from app.main import app
        persistence_service = getattr(app.state, 'persistence_service', None)
        if not persistence_service:
            raise HTTPException(status_code=503, detail="Persistence service not available")
        
        wal_status = persistence_service.wal_handler.get_wal_status()
        return {"wal_status": wal_status}
    except Exception as e:
        logger.error(f"WAL status error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Status retrieval failed: {str(e)}")


@router.post("/persistence/wal/validate", tags=["Persistence"])
async def validate_wal_file():
    """Validate WAL file integrity"""
    try:
        from app.main import app
        persistence_service = getattr(app.state, 'persistence_service', None)
        if not persistence_service:
            raise HTTPException(status_code=503, detail="Persistence service not available")
        
        validation_result = await persistence_service.wal_handler.validate_wal_file()
        return {"wal_validation": validation_result}
    except Exception as e:
        logger.error(f"WAL validation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@router.get("/persistence/database/status", tags=["Persistence"])
async def get_database_status():
    """Get database operations status"""
    try:
        from app.main import app
        persistence_service = getattr(app.state, 'persistence_service', None)
        if not persistence_service:
            raise HTTPException(status_code=503, detail="Persistence service not available")
        
        db_status = persistence_service.database_ops.get_database_status()
        db_available = await persistence_service.database_ops.test_database_connection()
        
        return {
            "database_status": db_status,
            "database_available": db_available
        }
    except Exception as e:
        logger.error(f"Database status error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Status retrieval failed: {str(e)}")


@router.post("/persistence/database/validate", tags=["Persistence"])
async def validate_database_schema():
    """Validate database schema for persistence"""
    try:
        from app.main import app
        persistence_service = getattr(app.state, 'persistence_service', None)
        if not persistence_service:
            raise HTTPException(status_code=503, detail="Persistence service not available")
        
        validation_result = await persistence_service.database_ops.validate_database_schema()
        return {"schema_validation": validation_result}
    except Exception as e:
        logger.error(f"Schema validation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@router.get("/persistence/replay/status", tags=["Persistence"])
async def get_replay_status():
    """Get WAL replay service status"""
    try:
        from app.main import app
        persistence_service = getattr(app.state, 'persistence_service', None)
        if not persistence_service:
            raise HTTPException(status_code=503, detail="Persistence service not available")
        
        replay_status = await persistence_service.wal_replay.get_detailed_status()
        return {"replay_status": replay_status}
    except Exception as e:
        logger.error(f"Replay status error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Status retrieval failed: {str(e)}")


@router.post("/persistence/statistics/reset", tags=["Persistence"])
async def reset_persistence_statistics():
    """Reset all persistence statistics"""
    try:
        from app.main import app
        persistence_service = getattr(app.state, 'persistence_service', None)
        if not persistence_service:
            raise HTTPException(status_code=503, detail="Persistence service not available")
        
        persistence_service.reset_statistics()
        return {"message": "Persistence statistics reset successfully"}
    except Exception as e:
        logger.error(f"Statistics reset error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Reset failed: {str(e)}")


@router.post("/persistence/wal/cleanup", tags=["Persistence"])
async def cleanup_wal_backups(max_age_days: int = Body(7, description="Maximum age in days for WAL backup files")):
    """Clean up old WAL backup files"""
    try:
        from app.main import app
        persistence_service = getattr(app.state, 'persistence_service', None)
        if not persistence_service:
            raise HTTPException(status_code=503, detail="Persistence service not available")
        
        deleted_files = await persistence_service.cleanup_old_wal_backups(max_age_days)
        return {
            "message": f"Cleaned up {len(deleted_files)} old WAL backup files",
            "deleted_files": deleted_files
        }
    except Exception as e:
        logger.error(f"WAL cleanup error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")


@router.post("/persistence/validate", tags=["Persistence"])
async def validate_persistence_integrity():
    """Comprehensive validation of persistence layer integrity"""
    try:
        from app.main import app
        persistence_service = getattr(app.state, 'persistence_service', None)
        if not persistence_service:
            raise HTTPException(status_code=503, detail="Persistence service not available")
        
        validation_result = await persistence_service.validate_persistence_integrity()
        return {"persistence_validation": validation_result}
    except Exception as e:
        logger.error(f"Persistence validation error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}") 