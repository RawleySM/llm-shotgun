from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text, Index
from sqlalchemy.sql import func
from .database import Base
from passlib.context import CryptContext
import secrets


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False)
    username = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user")  # Roles: "user", "admin", "moderator"
    is_superuser = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    email_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    reset_token = Column(String, unique=True, nullable=True)

    def verify_password(self, password: str) -> bool:
        """Check if a plain password matches the hashed password."""
        return pwd_context.verify(password, self.hashed_password)

    def set_password(self, password: str):
        """Hash and store a password."""
        self.hashed_password = pwd_context.hash(password)

    def generate_reset_token(self):
        """Generate a secure reset token."""
        self.reset_token = secrets.token_urlsafe(32)

    def clear_reset_token(self):
        """Clear password reset token after use."""
        self.reset_token = None


class LLMRequest(Base):
    """Table to store LLM request metadata"""
    __tablename__ = "llm_requests"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String, unique=True, nullable=False, index=True)
    prompt = Column(Text, nullable=False)
    models = Column(String, nullable=False)  # JSON string of model list
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=func.now())
    status = Column(String, default="pending")  # pending, completed, failed


class LLMAttempt(Base):
    """Table to store individual LLM provider attempts"""
    __tablename__ = "llm_attempts"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String, ForeignKey("llm_requests.request_id"), nullable=False, index=True)
    attempt_seq = Column(Integer, nullable=False)
    provider = Column(String, nullable=False)
    model = Column(String, nullable=False)
    status = Column(String, default="pending")  # pending, streaming, completed, failed
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, default=func.now())
    completed_at = Column(DateTime, nullable=True)
    
    __table_args__ = (
        Index('idx_request_attempt', 'request_id', 'attempt_seq'),
    )


class LLMTokenLog(Base):
    """Table to store streaming tokens for the token persistence system"""
    __tablename__ = "llm_token_log"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String, ForeignKey("llm_requests.request_id"), nullable=False, index=True)
    attempt_seq = Column(Integer, nullable=False)
    token_index = Column(Integer, nullable=False)
    token_text = Column(Text, nullable=False)
    ts = Column(DateTime, default=func.now(), index=True)  # Index for pruning performance
    
    __table_args__ = (
        Index('idx_request_attempt_token', 'request_id', 'attempt_seq', 'token_index'),
        Index('idx_ts', 'ts'),  # For retention cleanup
    )


class ProviderStatus(Base):
    """Table to track provider circuit breaker status"""
    __tablename__ = "provider_status"

    id = Column(Integer, primary_key=True, index=True)
    provider_name = Column(String, unique=True, nullable=False, index=True)
    status = Column(String, default="closed")  # closed, open, half-open
    failure_count = Column(Integer, default=0)
    last_failure = Column(DateTime, nullable=True)
    last_success = Column(DateTime, nullable=True)
    enabled = Column(Boolean, default=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
