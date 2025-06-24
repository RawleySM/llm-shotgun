"""
FD 7: Boot-up & Consistency Service
Implements boot-time consistency checks for token gaps and schema migrations.
"""

import asyncio
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, select
from sqlalchemy.exc import SQLAlchemyError
from app.db.database import AsyncSessionLocal, engine
from app.db.models import LLMTokenLog
from app.utils.logger import setup_logger
import subprocess
import os

logger = setup_logger(__name__)


class ConsistencyService:
    """Service to handle boot-time consistency checks and schema migrations"""
    
    def __init__(self):
        self.token_gaps_detected = False
        self.last_consistency_check = None
    
    async def run_boot_consistency_check(self) -> Dict[str, Any]:
        """
        FD 7.1, 7.2, 7.3: Run complete boot-time consistency check
        Returns status including schema migrations, token gaps, and WAL replay
        """
        logger.info("Starting boot-time consistency check")
        
        results = {
            "schema_migrations": False,
            "token_gaps_detected": False,
            "wal_replay_started": False,
            "errors": []
        }
        
        try:
            # 7.1: Run schema migrations (Alembic)
            migration_result = await self.run_schema_migrations()
            results["schema_migrations"] = migration_result
            
            # 7.2: Detect token gaps
            gaps = await self.detect_token_gaps()
            if gaps:
                self.token_gaps_detected = True
                results["token_gaps_detected"] = True
                logger.warning(f"Token gaps detected: {len(gaps)} instances")
                for gap in gaps[:5]:  # Log first 5 gaps
                    logger.warning(f"Gap in request_id: {gap['request_id']}, attempt_seq: {gap['attempt_seq']}")
            
            # 7.3: Start WAL replay loop (this will be handled by the persistence service)
            results["wal_replay_started"] = True
            
            logger.info("Boot-time consistency check completed successfully")
            
        except Exception as e:
            error_msg = f"Error during boot-time consistency check: {str(e)}"
            logger.error(error_msg)
            results["errors"].append(error_msg)
        
        return results
    
    async def run_schema_migrations(self) -> bool:
        """
        FD 7.1: Run schema migrations using Alembic
        """
        try:
            logger.info("Running schema migrations")
            
            # Run alembic upgrade head
            result = subprocess.run(
                ["alembic", "upgrade", "head"],
                cwd="/app",  # Assuming we're in the backend directory
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                logger.info("Schema migrations completed successfully")
                return True
            else:
                logger.error(f"Schema migration failed: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            logger.error("Schema migration timed out")
            return False
        except Exception as e:
            logger.error(f"Error running schema migrations: {str(e)}")
            return False
    
    async def detect_token_gaps(self) -> List[Dict[str, Any]]:
        """
        FD 7.2: Detect token gaps using SQL window query
        Returns list of detected gaps
        """
        gap_query = text("""
            SELECT request_id, attempt_seq, token_index, prev_token_index
            FROM (
              SELECT request_id, attempt_seq, token_index,
                     lag(token_index) OVER (PARTITION BY request_id, attempt_seq ORDER BY token_index) AS prev_token_index
              FROM llm_token_log
            ) q
            WHERE prev_token_index IS NOT NULL AND token_index <> prev_token_index + 1
            LIMIT 10
        """)
        
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(gap_query)
                gaps = []
                
                for row in result:
                    gaps.append({
                        "request_id": row.request_id,
                        "attempt_seq": row.attempt_seq,
                        "token_index": row.token_index,
                        "prev_token_index": row.prev_token_index
                    })
                
                return gaps
                
        except SQLAlchemyError as e:
            logger.error(f"Error detecting token gaps: {str(e)}")
            return []
    
    def has_token_gaps(self) -> bool:
        """Return whether token gaps were detected during boot"""
        return self.token_gaps_detected
    
    async def get_consistency_status(self) -> Dict[str, Any]:
        """Get current consistency status for health endpoint"""
        return {
            "token_gaps_detected": self.token_gaps_detected,
            "last_consistency_check": self.last_consistency_check
        }


# Global instance
consistency_service = ConsistencyService() 