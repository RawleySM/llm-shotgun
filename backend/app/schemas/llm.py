from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any, Union
from enum import Enum
import re

class LLMProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE_AI = "google_ai"
    DEEPSEEK = "deepseek"
    COHERE = "cohere"

class LLMModel(str, Enum):
    # OpenAI Models
    GPT_4 = "gpt-4"
    GPT_4_TURBO = "gpt-4-turbo"
    GPT_3_5_TURBO = "gpt-3.5-turbo"
    
    # Anthropic Models
    CLAUDE_3_OPUS = "claude-3-opus-20240229"
    CLAUDE_3_SONNET = "claude-3-sonnet-20240229"
    CLAUDE_3_HAIKU = "claude-3-haiku-20240307"
    
    # Google Models
    GEMINI_1_5_PRO = "gemini-1.5-pro"
    GEMINI_1_5_FLASH = "gemini-1.5-flash"
    
    # DeepSeek Models
    DEEPSEEK_CHAT = "deepseek-chat"
    DEEPSEEK_CODER = "deepseek-coder"
    DEEPSEEK_REASONER = "deepseek-reasoner"
    
    # Cohere Models
    COHERE_COMMAND_R = "command-r"
    COHERE_COMMAND_R_PLUS = "command-r-plus"

class ModelRequest(BaseModel):
    provider: LLMProvider
    model: LLMModel
    weight: float = Field(default=1.0, ge=0.0, le=1.0, description="Weight for load balancing")

class PromptRequest(BaseModel):
    """
    Main prompt request schema with FSD-compliant validation
    Implements: 1.2 validate_utf8, 1.3 enforce_size, 1.4 auto_select_models
    """
    prompt: str = Field(
        ..., 
        min_length=1,
        max_length=8000,  # FSD requirement: max 8k characters
        description="The main prompt to send to LLM"
    )
    models: Optional[List[ModelRequest]] = Field(
        default=None, 
        description="List of models to use. If None, auto-selection will be applied"
    )
    max_tokens: Optional[int] = Field(default=None, ge=1, le=8192)
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    system_message: Optional[str] = Field(default=None, max_length=2000)

    @validator('prompt')
    def validate_utf8_prompt(cls, v):
        """FSD 1.2: validate_utf8(prompt) → raises 400 if invalid"""
        if not isinstance(v, str):
            raise ValueError("Prompt must be a string")
        
        try:
            # Ensure it's valid UTF-8 by encoding/decoding
            v.encode('utf-8').decode('utf-8')
        except UnicodeError:
            raise ValueError("Prompt must be valid UTF-8 text")
        
        # Additional validation: check for null bytes which can cause issues
        if '\x00' in v:
            raise ValueError("Prompt cannot contain null bytes")
            
        return v.strip()  # Remove leading/trailing whitespace

    @validator('system_message')
    def validate_utf8_system_message(cls, v):
        """Validate system message is UTF-8 if provided"""
        if v is not None:
            try:
                v.encode('utf-8').decode('utf-8')
            except UnicodeError:
                raise ValueError("System message must be valid UTF-8 text")
            
            if '\x00' in v:
                raise ValueError("System message cannot contain null bytes")
                
            return v.strip()
        return v

    @validator('models')
    def validate_models_list(cls, v):
        """Validate models list if provided"""
        if v is not None:
            if len(v) == 0:
                raise ValueError("Models list cannot be empty if provided")
            if len(v) > 5:  # Reasonable limit to prevent abuse
                raise ValueError("Cannot specify more than 5 models")
        return v

class TokenResponse(BaseModel):
    """Single token response"""
    token: str
    token_index: int
    provider: str
    model: str
    timestamp: str

class PromptResponse(BaseModel):
    """Response for prompt submission"""
    request_id: str = Field(..., description="Unique request identifier")
    status: str = Field(..., description="Request status")
    models_selected: List[str] = Field(..., description="Models that will be used")
    stream_url: str = Field(..., description="SSE endpoint for streaming tokens")

class PromptMetadata(BaseModel):
    """Metadata about a prompt request"""
    request_id: str
    prompt: str
    models: List[str]
    created_at: str
    status: str
    total_tokens: Optional[int] = None

class ValidationError(BaseModel):
    """Standardized validation error response"""
    error: str
    field: str
    value: Any
    message: str

class HealthStatus(BaseModel):
    """Health check response matching FSD requirements"""
    providers: Dict[str, str]  # provider -> status (open/closed/half-open)
    db_ok: bool
    buffer_len: int
    last_flush_ms: Optional[int]
    wal_size_bytes: int
    last_db_write: Optional[str]
    token_gap: Optional[bool] = False  # From boot-time consistency check 