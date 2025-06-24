"""
LLM Routes - Implements FSD Section 1: Prompt Intake & Validation
Main endpoint: POST /prompt
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.llm import PromptRequest, PromptResponse, PromptMetadata, ValidationError
from app.services.validation import validation_service
from app.db.database import get_db
from app.routes.auth import get_current_user
from app.db.models import User
from app.utils.logger import setup_logger

router = APIRouter(prefix="/llm", tags=["llm"])
logger = setup_logger(__name__)

@router.post("/prompt", response_model=PromptResponse)
async def submit_prompt(
    request: PromptRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> PromptResponse:
    """
    FSD 1.1: POST /prompt handler → coordinator
    
    Main endpoint for prompt submission with full validation pipeline:
    - 1.2: UTF-8 validation (via Pydantic + additional checks)
    - 1.3: Size enforcement (8k char limit)
    - 1.4: Auto-model selection if not provided
    - 1.5: Create request row in Postgres
    
    Returns:
        PromptResponse with request_id and streaming URL
    """
    try:
        # Log request for debugging
        logger.info(
            f"Prompt submission from user {current_user.id}: "
            f"length={len(request.prompt)}, "
            f"models_provided={request.models is not None}"
        )
        
        # FSD 1.1: Main validation coordinator
        validation_result = await validation_service.validate_and_process_prompt(
            request, db
        )
        
        request_id = validation_result["request_id"]
        selected_models = validation_result["validated_models"]
        
        # Build response
        response = PromptResponse(
            request_id=request_id,
            status="accepted",
            models_selected=[
                f"{model.provider.value}:{model.model.value}" 
                for model in selected_models
            ],
            stream_url=f"/api/llm/stream/{request_id}"
        )
        
        logger.info(
            f"Prompt accepted: {request_id}, "
            f"models: {response.models_selected}, "
            f"auto_selected: {validation_result['auto_selected']}"
        )
        
        return response
        
    except HTTPException:
        # Re-raise HTTP exceptions (validation errors)
        raise
    except Exception as e:
        logger.error(f"Unexpected error in prompt submission: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during prompt processing"
        )

@router.get("/request/{request_id}", response_model=PromptMetadata)
async def get_request_metadata(
    request_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> PromptMetadata:
    """
    Get metadata for a specific prompt request
    """
    try:
        from sqlalchemy import text
        
        query = text("""
            SELECT request_id, prompt, models_config, created_at, status,
                   (SELECT COUNT(*) FROM llm_token_log WHERE request_id = :request_id) as total_tokens
            FROM llm_requests 
            WHERE request_id = :request_id
        """)
        
        result = await db.execute(query, {"request_id": request_id})
        row = result.fetchone()
        
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Request {request_id} not found"
            )
        
        # Extract model names from config
        models_config = row.models_config or []
        model_names = [f"{m['provider']}:{m['model']}" for m in models_config]
        
        return PromptMetadata(
            request_id=row.request_id,
            prompt=row.prompt,
            models=model_names,
            created_at=row.created_at.isoformat(),
            status=row.status,
            total_tokens=row.total_tokens
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching request metadata {request_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error fetching request metadata"
        )

@router.post("/validate", response_model=dict)
async def validate_prompt_only(
    request: PromptRequest,
    current_user: User = Depends(get_current_user)
) -> dict:
    """
    Validate a prompt without submitting it for processing
    Useful for frontend validation feedback
    """
    try:
        # Run validation without database operations
        validation_service.validate_utf8(request.prompt)
        validation_service.enforce_size(request.prompt)
        
        # Get auto-selected models if none provided
        if request.models is None:
            auto_models = await validation_service.auto_select_models(request.prompt)
        else:
            auto_models = request.models
        
        # Return validation summary
        summary = validation_service.get_validation_summary(request)
        summary.update({
            "suggested_models": [
                f"{model.provider.value}:{model.model.value}" 
                for model in auto_models
            ],
            "validation_status": "passed"
        })
        
        return summary
        
    except HTTPException as e:
        return {
            "validation_status": "failed",
            "error": e.detail,
            "status_code": e.status_code
        }
    except Exception as e:
        logger.error(f"Validation error: {str(e)}")
        return {
            "validation_status": "failed",
            "error": "Internal validation error",
            "status_code": 500
        }

@router.exception_handler(HTTPException)
async def validation_exception_handler(request, exc: HTTPException):
    """
    Custom exception handler for validation errors
    Returns structured error response matching FSD requirements
    """
    if exc.status_code == status.HTTP_400_BAD_REQUEST:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "validation_failed",
                "message": exc.detail,
                "timestamp": str(datetime.utcnow()),
                "request_id": None
            }
        )
    
    # Re-raise other HTTP exceptions
    raise exc 