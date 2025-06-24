"""
FD 3.2: TokenBuilder Module
Converts raw token text → Token dataclass with incremental index.
"""

from datetime import datetime
from typing import Optional
from app.services.data_structures import Token
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class TokenBuilder:
    """
    FD 3.2: TokenBuilder responsibility - Convert raw token text → Token dataclass
    Maintains incremental index per attempt and ensures monotonic ordering.
    """
    
    def __init__(self, request_id: str, attempt_seq: int, model_id: str):
        self.request_id = request_id
        self.attempt_seq = attempt_seq
        self.model_id = model_id
        self.current_index = 0
        self.total_tokens_built = 0
        
        logger.debug(f"TokenBuilder initialized for request {request_id}, attempt {attempt_seq}, model {model_id}")
    
    def build(self, raw_token: str) -> Token:
        """
        FD 3.2: Key function - build(raw_str)
        Convert raw token string to Token dataclass with incremental index
        """
        if not isinstance(raw_token, str):
            raise ValueError(f"Expected string token, got {type(raw_token)}: {raw_token}")
        
        # Build token with strictly monotonically increasing index
        token = Token(
            model_id=self.model_id,
            text=raw_token,
            index=self.current_index,
            timestamp=datetime.utcnow(),
            request_id=self.request_id,
            attempt_seq=self.attempt_seq
        )
        
        # Increment index for next token (strictly monotonic)
        self.current_index += 1
        self.total_tokens_built += 1
        
        logger.debug(f"Built token {token.index}: '{raw_token[:20]}{'...' if len(raw_token) > 20 else ''}' "
                    f"(request: {self.request_id})")
        
        return token
    
    def get_current_index(self) -> int:
        """Get the current token index (next token will have this index)"""
        return self.current_index
    
    def get_total_built(self) -> int:
        """Get total number of tokens built so far"""
        return self.total_tokens_built
    
    def reset_index(self, start_index: int = 0):
        """Reset the token index (useful for retries or new attempts)"""
        old_index = self.current_index
        self.current_index = start_index
        logger.info(f"TokenBuilder index reset from {old_index} to {start_index} "
                   f"(request: {self.request_id})")
    
    def create_builder_for_retry(self, new_attempt_seq: int) -> 'TokenBuilder':
        """Create a new TokenBuilder for a retry attempt"""
        return TokenBuilder(
            request_id=self.request_id,
            attempt_seq=new_attempt_seq,
            model_id=self.model_id
        )
    
    def validate_token_sequence(self, tokens: list[Token]) -> bool:
        """
        Validate that a sequence of tokens has strictly monotonic indices
        Useful for testing and debugging
        """
        if not tokens:
            return True
        
        for i, token in enumerate(tokens):
            if token.index != i:
                logger.error(f"Token sequence validation failed: expected index {i}, got {token.index}")
                return False
        
        logger.debug(f"Token sequence validation passed for {len(tokens)} tokens")
        return True
    
    def get_builder_info(self) -> dict:
        """Get builder status information for monitoring"""
        return {
            "request_id": self.request_id,
            "attempt_seq": self.attempt_seq,
            "model_id": self.model_id,
            "current_index": self.current_index,
            "total_tokens_built": self.total_tokens_built
        } 