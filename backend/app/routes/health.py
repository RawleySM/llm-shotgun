from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from app.utils.logger import setup_logger
from app.services.metrics import metrics_service

router = APIRouter()
logger = setup_logger(__name__)


@router.get("/health", tags=["Health"])
async def health_check():
    """
    FD 6.2: Health endpoint with exact format as specified in FSD section 5.6
    Returns: providers, db_ok, buffer_len, last_flush_ms, wal_size_bytes, last_db_write
    """
    logger.info("Health check endpoint called (FD 6.2 format)")
    
    try:
        # Get health status in exact FSD format
        health_status = await metrics_service.get_health_status()
        
        return health_status
        
    except Exception as e:
        logger.error(f"Error in health check: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@router.get("/metrics", tags=["Health"])
async def metrics():
    """
    FD 6.3: Optional Prometheus-style metrics endpoint
    Returns buffer_len, wal_size_bytes, attempts_total as specified in FSD section 9
    """
    logger.info("Metrics endpoint called (FD 6.3 Prometheus format)")
    
    try:
        # Collect core metrics
        metrics_data = await metrics_service.collect_metrics()
        
        return metrics_data
        
    except Exception as e:
        logger.error(f"Error getting metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Metrics collection failed: {str(e)}")


@router.get("/metrics/prometheus", tags=["Health"], response_class=PlainTextResponse)
async def metrics_prometheus():
    """
    FD 6.3: Prometheus exposition format metrics
    Returns metrics in Prometheus text format
    """
    logger.info("Prometheus metrics endpoint called")
    
    try:
        # Collect metrics and format for Prometheus
        metrics_data = await metrics_service.collect_metrics()
        prometheus_text = metrics_service.format_prometheus_metrics(metrics_data)
        
        return prometheus_text
        
    except Exception as e:
        logger.error(f"Error getting Prometheus metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Prometheus metrics failed: {str(e)}")
