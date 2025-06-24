"""
Prompt Intake & Validation Service
Implements FSD Section 1: Prompt Intake & Validation

Functions:
1.1 POST /prompt handler → coordinator
1.2 validate_utf8(prompt) → raises 400 if invalid  
1.3 enforce_size(prompt, max_chars=8_000)
1.4 auto_select_models(prompt) if user omitted list
1.5 create_request_row(request_id, models) in Postgres
"""

import uuid
import re
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime

from app.schemas.llm import PromptRequest, ModelRequest, LLMProvider, LLMModel
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

class PromptValidationService:
    """
    Service implementing FSD Section 1: Prompt Intake & Validation
    """
    
    # FSD 1.3: max 8k characters
    MAX_PROMPT_CHARS = 8000
    
    # FSD 1.4: fallback model selection patterns
    CODING_KEYWORDS = {
        'code', 'function', 'programming', 'debug', 'algorithm', 'script', 
        'class', 'method', 'variable', 'syntax', 'compile', 'execute',
        'python', 'javascript', 'java', 'cpp', 'rust', 'go', 'sql'
    }
    
    REASONING_KEYWORDS = {
        'analyze', 'reason', 'explain', 'compare', 'evaluate', 'assess',
        'think', 'logic', 'proof', 'argument', 'conclusion', 'evidence'
    }
    
    def __init__(self):
        self.logger = logger

    async def validate_and_process_prompt(
        self, 
        request: PromptRequest, 
        db: AsyncSession
    ) -> Dict[str, Any]:
        """
        FSD 1.1: Main coordinator function for prompt intake & validation
        
        Returns:
            Dict containing request_id, validated_models, and metadata
        """
        try:
            # FSD 1.2: UTF-8 validation (already done by Pydantic validator)
            # FSD 1.3: Size enforcement (already done by Pydantic Field validation)
            
            # Generate unique request ID
            request_id = str(uuid.uuid4())
            
            # FSD 1.4: Auto-select models if not provided
            if request.models is None or len(request.models) == 0:
                selected_models = await self.auto_select_models(request.prompt)
            else:
                selected_models = request.models
            
            # FSD 1.5: Create request row in Postgres
            await self.create_request_row(db, request_id, request, selected_models)
            
            return {
                "request_id": request_id,
                "validated_models": selected_models,
                "prompt_length": len(request.prompt),
                "auto_selected": request.models is None,
                "created_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            self.logger.error(f"Prompt validation failed: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Prompt validation error: {str(e)}"
            )

    def validate_utf8(self, text: str) -> str:
        """
        FSD 1.2: validate_utf8(prompt) → raises 400 if invalid
        
        Additional validation beyond Pydantic for edge cases
        """
        if not text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Prompt cannot be empty"
            )
        
        try:
            # Ensure valid UTF-8
            encoded = text.encode('utf-8')
            decoded = encoded.decode('utf-8')
            
            # Check for control characters that might cause issues
            if any(ord(char) < 32 and char not in '\t\n\r' for char in decoded):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Prompt contains invalid control characters"
                )
            
            return decoded.strip()
            
        except UnicodeError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid UTF-8 encoding: {str(e)}"
            )

    def enforce_size(self, prompt: str, max_chars: int = MAX_PROMPT_CHARS) -> str:
        """
        FSD 1.3: enforce_size(prompt, max_chars=8_000)
        """
        if len(prompt) > max_chars:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Prompt exceeds maximum length of {max_chars} characters. "
                       f"Current length: {len(prompt)}"
            )
        
        if len(prompt.strip()) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Prompt cannot be empty or contain only whitespace"
            )
            
        return prompt

    async def auto_select_models(self, prompt: str) -> List[ModelRequest]:
        """
        FSD 1.4: auto_select_models(prompt) if user omitted list
        
        Intelligent model selection based on prompt content analysis
        """
        prompt_lower = prompt.lower()
        prompt_words = set(re.findall(r'\b\w+\b', prompt_lower))
        
        # Check for coding-related content
        if self.CODING_KEYWORDS.intersection(prompt_words):
            return [
                ModelRequest(provider=LLMProvider.DEEPSEEK, model=LLMModel.DEEPSEEK_CODER, weight=0.6),
                ModelRequest(provider=LLMProvider.OPENAI, model=LLMModel.GPT_4, weight=0.4)
            ]
        
        # Check for reasoning/analysis content
        elif self.REASONING_KEYWORDS.intersection(prompt_words):
            return [
                ModelRequest(provider=LLMProvider.DEEPSEEK, model=LLMModel.DEEPSEEK_REASONER, weight=0.5),
                ModelRequest(provider=LLMProvider.ANTHROPIC, model=LLMModel.CLAUDE_3_SONNET, weight=0.5)
            ]
        
        # Check for long-form content (> 1000 chars) - use high-capacity models
        elif len(prompt) > 1000:
            return [
                ModelRequest(provider=LLMProvider.OPENAI, model=LLMModel.GPT_4, weight=0.4),
                ModelRequest(provider=LLMProvider.ANTHROPIC, model=LLMModel.CLAUDE_3_OPUS, weight=0.3),
                ModelRequest(provider=LLMProvider.GOOGLE_AI, model=LLMModel.GEMINI_1_5_PRO, weight=0.3)
            ]
        
        # Default: balanced, cost-effective selection
        else:
            return [
                ModelRequest(provider=LLMProvider.OPENAI, model=LLMModel.GPT_3_5_TURBO, weight=0.4),
                ModelRequest(provider=LLMProvider.DEEPSEEK, model=LLMModel.DEEPSEEK_CHAT, weight=0.3),
                ModelRequest(provider=LLMProvider.GOOGLE_AI, model=LLMModel.GEMINI_1_5_FLASH, weight=0.3)
            ]

    async def create_request_row(
        self, 
        db: AsyncSession, 
        request_id: str, 
        request: PromptRequest,
        selected_models: List[ModelRequest]
    ) -> None:
        """
        FSD 1.5: create_request_row(request_id, models) in Postgres
        
        Creates the initial request metadata in the database
        """
        try:
            # Prepare model data for storage
            models_data = [
                {
                    "provider": model.provider.value,
                    "model": model.model.value,
                    "weight": model.weight
                }
                for model in selected_models
            ]
            
            # Insert request metadata
            query = text("""
                INSERT INTO llm_requests (
                    request_id, 
                    prompt, 
                    prompt_length,
                    models_config,
                    max_tokens,
                    temperature,
                    system_message,
                    status,
                    created_at
                ) VALUES (
                    :request_id,
                    :prompt,
                    :prompt_length,
                    :models_config,
                    :max_tokens,
                    :temperature,
                    :system_message,
                    'pending',
                    NOW()
                )
            """)
            
            await db.execute(query, {
                "request_id": request_id,
                "prompt": request.prompt,
                "prompt_length": len(request.prompt),
                "models_config": models_data,  # JSON field
                "max_tokens": request.max_tokens,
                "temperature": request.temperature,
                "system_message": request.system_message
            })
            
            await db.commit()
            
            self.logger.info(
                f"Created request row: {request_id}, "
                f"models: {[f'{m.provider.value}:{m.model.value}' for m in selected_models]}"
            )
            
        except Exception as e:
            await db.rollback()
            self.logger.error(f"Failed to create request row {request_id}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database error: {str(e)}"
            )

    def get_validation_summary(self, request: PromptRequest) -> Dict[str, Any]:
        """
        Generate a summary of validation results for logging/debugging
        """
        return {
            "prompt_length": len(request.prompt),
            "has_system_message": request.system_message is not None,
            "models_specified": request.models is not None,
            "model_count": len(request.models) if request.models else 0,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "validation_passed": True
        }

# Singleton instance
validation_service = PromptValidationService() 