"""
FD 11: Administrative Controls Service
Implements administrative endpoints for health checks, request monitoring, and provider controls.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text
from sqlalchemy.exc import SQLAlchemyError
from app.db.database import AsyncSessionLocal
from app.db.models import LLMRequest, LLMAttempt, LLMTokenLog, ProviderStatus
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class AdminService:
    """Service to handle administrative operations and monitoring"""
    
    def __init__(self):
        self.metrics_cache = {}
        self.cache_ttl = 60  # seconds
        self.last_cache_update = None
    
    async def get_enhanced_health_status(self) -> Dict[str, Any]:
        """
        FD 11.1: Enhanced health endpoint with comprehensive system status
        """
        from app.services.consistency import consistency_service
        from app.services.retention import retention_service
        from app.services.backup import backup_service
        from app.services.shutdown import shutdown_service
        
        logger.debug("Collecting enhanced health status")
        
        try:
            # Get current timestamp
            current_time = datetime.utcnow()
            
            # Get provider statuses
            providers_status = await self._get_providers_status()
            
            # Get database connectivity
            db_ok = await self._check_database_connectivity()
            
            # Get system metrics
            metrics = await self._get_system_metrics()
            
            # Compile comprehensive health status
            health_status = {
                "status": "healthy",
                "timestamp": current_time.isoformat(),
                "providers": providers_status,
                "database": {
                    "connected": db_ok,
                    "last_check": current_time.isoformat()
                },
                "metrics": metrics,
                "services": {
                    "consistency": await consistency_service.get_consistency_status(),
                    "retention": await retention_service.get_retention_status(),
                    "backup": await backup_service.get_backup_status(),
                    "shutdown": shutdown_service.get_shutdown_status()
                }
            }
            
            # Determine overall health status
            if not db_ok or any(status == "error" for status in providers_status.values()):
                health_status["status"] = "degraded"
            
            if shutdown_service.shutdown_initiated:
                health_status["status"] = "shutting_down"
            
            return health_status
            
        except Exception as e:
            logger.error(f"Error collecting health status: {str(e)}")
            return {
                "status": "error",
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e)
            }
    
    async def get_request_metadata(self, request_id: str) -> Optional[Dict[str, Any]]:
        """
        FD 11.2: Get metadata and token stream information for a specific request
        """
        try:
            async with AsyncSessionLocal() as session:
                # Get request details
                request_query = select(LLMRequest).where(LLMRequest.request_id == request_id)
                request_result = await session.execute(request_query)
                request = request_result.scalar_one_or_none()
                
                if not request:
                    return None
                
                # Get attempts for this request
                attempts_query = select(LLMAttempt).where(LLMAttempt.request_id == request_id)
                attempts_result = await session.execute(attempts_query)
                attempts = attempts_result.scalars().all()
                
                # Get token counts per attempt
                token_counts_query = select(
                    LLMTokenLog.attempt_seq,
                    func.count(LLMTokenLog.id).label('token_count'),
                    func.min(LLMTokenLog.ts).label('first_token'),
                    func.max(LLMTokenLog.ts).label('last_token')
                ).where(
                    LLMTokenLog.request_id == request_id
                ).group_by(LLMTokenLog.attempt_seq)
                
                token_counts_result = await session.execute(token_counts_query)
                token_counts = {row.attempt_seq: {
                    'count': row.token_count,
                    'first_token': row.first_token.isoformat() if row.first_token else None,
                    'last_token': row.last_token.isoformat() if row.last_token else None
                } for row in token_counts_result}
                
                # Compile metadata
                metadata = {
                    "request_id": request.request_id,
                    "prompt": request.prompt[:200] + "..." if len(request.prompt) > 200 else request.prompt,
                    "models": request.models,
                    "status": request.status,
                    "created_at": request.created_at.isoformat(),
                    "user_id": request.user_id,
                    "attempts": []
                }
                
                for attempt in attempts:
                    attempt_data = {
                        "attempt_seq": attempt.attempt_seq,
                        "provider": attempt.provider,
                        "model": attempt.model,
                        "status": attempt.status,
                        "started_at": attempt.started_at.isoformat(),
                        "completed_at": attempt.completed_at.isoformat() if attempt.completed_at else None,
                        "error_message": attempt.error_message,
                        "tokens": token_counts.get(attempt.attempt_seq, {'count': 0})
                    }
                    metadata["attempts"].append(attempt_data)
                
                return metadata
                
        except SQLAlchemyError as e:
            logger.error(f"Database error getting request metadata: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error getting request metadata: {str(e)}")
            return None
    
    async def toggle_provider_status(self, provider_name: str, action: str) -> Dict[str, Any]:
        """
        FD 11.3: Enable or disable a specific provider
        """
        if action not in ["enable", "disable"]:
            return {
                "status": "error",
                "error": "Action must be 'enable' or 'disable'"
            }
        
        enabled = action == "enable"
        
        try:
            async with AsyncSessionLocal() as session:
                # Get or create provider status
                provider_query = select(ProviderStatus).where(ProviderStatus.provider_name == provider_name)
                result = await session.execute(provider_query)
                provider_status = result.scalar_one_or_none()
                
                if not provider_status:
                    provider_status = ProviderStatus(
                        provider_name=provider_name,
                        enabled=enabled,
                        status="closed"
                    )
                    session.add(provider_status)
                else:
                    provider_status.enabled = enabled
                    provider_status.updated_at = datetime.utcnow()
                
                await session.commit()
                
                logger.info(f"Provider {provider_name} {action}d successfully")
                
                return {
                    "status": "success",
                    "provider": provider_name,
                    "action": action,
                    "enabled": enabled,
                    "updated_at": datetime.utcnow().isoformat()
                }
                
        except SQLAlchemyError as e:
            error_msg = f"Database error toggling provider status: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "error",
                "error": error_msg
            }
        except Exception as e:
            error_msg = f"Error toggling provider status: {str(e)}"
            logger.error(error_msg)
            return {
                "status": "error",
                "error": error_msg
            }
    
    async def get_system_metrics(self) -> Dict[str, Any]:
        """Get comprehensive system metrics for monitoring"""
        # Check cache first
        if (self.last_cache_update and 
            (datetime.utcnow() - self.last_cache_update).total_seconds() < self.cache_ttl):
            return self.metrics_cache
        
        metrics = await self._get_system_metrics()
        
        # Update cache
        self.metrics_cache = metrics
        self.last_cache_update = datetime.utcnow()
        
        return metrics
    
    async def _get_system_metrics(self) -> Dict[str, Any]:
        """Internal method to collect system metrics"""
        try:
            async with AsyncSessionLocal() as session:
                # Request statistics
                request_stats_query = text("""
                    SELECT 
                        COUNT(*) as total_requests,
                        COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '24 hours') as requests_24h,
                        COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 hour') as requests_1h,
                        COUNT(*) FILTER (WHERE status = 'completed') as completed_requests,
                        COUNT(*) FILTER (WHERE status = 'failed') as failed_requests
                    FROM llm_requests
                """)
                
                # For SQLite compatibility, use a simpler query
                if not hasattr(session.get_bind().dialect, 'name') or session.get_bind().dialect.name == 'sqlite':
                    request_stats_query = text("""
                        SELECT 
                            COUNT(*) as total_requests,
                            COUNT(CASE WHEN datetime(created_at) > datetime('now', '-24 hours') THEN 1 END) as requests_24h,
                            COUNT(CASE WHEN datetime(created_at) > datetime('now', '-1 hour') THEN 1 END) as requests_1h,
                            COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed_requests,
                            COUNT(CASE WHEN status = 'failed' THEN 1 END) as failed_requests
                        FROM llm_requests
                    """)
                
                request_stats = await session.execute(request_stats_query)
                request_row = request_stats.fetchone()
                
                # Token statistics
                token_stats_query = select(func.count(LLMTokenLog.id)).select_from(LLMTokenLog)
                token_count_result = await session.execute(token_stats_query)
                total_tokens = token_count_result.scalar()
                
                # Provider statistics
                provider_stats_query = select(
                    LLMAttempt.provider,
                    func.count(LLMAttempt.id).label('attempt_count'),
                    func.avg(
                        func.extract('epoch', LLMAttempt.completed_at - LLMAttempt.started_at)
                    ).label('avg_duration')
                ).where(
                    LLMAttempt.completed_at.isnot(None)
                ).group_by(LLMAttempt.provider)
                
                provider_stats_result = await session.execute(provider_stats_query)
                provider_stats = {
                    row.provider: {
                        'attempt_count': row.attempt_count,
                        'avg_duration_seconds': float(row.avg_duration) if row.avg_duration else 0
                    }
                    for row in provider_stats_result
                }
                
                return {
                    "requests": {
                        "total": request_row.total_requests if request_row else 0,
                        "last_24h": request_row.requests_24h if request_row else 0,
                        "last_1h": request_row.requests_1h if request_row else 0,
                        "completed": request_row.completed_requests if request_row else 0,
                        "failed": request_row.failed_requests if request_row else 0
                    },
                    "tokens": {
                        "total": total_tokens or 0
                    },
                    "providers": provider_stats
                }
                
        except Exception as e:
            logger.error(f"Error collecting system metrics: {str(e)}")
            return {
                "requests": {"error": str(e)},
                "tokens": {"error": str(e)},
                "providers": {"error": str(e)}
            }
    
    async def _get_providers_status(self) -> Dict[str, str]:
        """Get status of all providers"""
        try:
            async with AsyncSessionLocal() as session:
                provider_query = select(ProviderStatus)
                result = await session.execute(provider_query)
                providers = result.scalars().all()
                
                status_map = {}
                for provider in providers:
                    if not provider.enabled:
                        status_map[provider.provider_name] = "disabled"
                    else:
                        status_map[provider.provider_name] = provider.status
                
                # Add default providers if not in database
                default_providers = ["openai", "anthropic", "google", "deepseek", "cohere"]
                for provider_name in default_providers:
                    if provider_name not in status_map:
                        status_map[provider_name] = "closed"  # Default to closed circuit breaker
                
                return status_map
                
        except Exception as e:
            logger.error(f"Error getting provider status: {str(e)}")
            return {"error": str(e)}
    
    async def _check_database_connectivity(self) -> bool:
        """Check if database is reachable"""
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error(f"Database connectivity check failed: {str(e)}")
            return False


# Global instance
admin_service = AdminService() 