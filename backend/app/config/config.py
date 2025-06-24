import os
from pathlib import Path
from functools import lru_cache
from typing import Optional, List
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    APP_VERSION: str = "1.0.0"
    APP_NAME: str = "FastAPI React Starter"
    APP_DESCRIPTION: str = "FastAPI React Starter Template"
    DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]
    API_PREFIX: str = "/api"

    # Database settings
    DB_NAME: Optional[str] = None
    DB_USER: Optional[str] = None
    DB_PASSWORD: Optional[str] = None
    DB_HOST: Optional[str] = None
    DB_PORT: Optional[int] = None
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_ECHO: bool = False
    DB_SSL_MODE: Optional[str] = None

    # JWT Settings
    SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "secret-key-for-development")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


BASE_DIR = Path(__file__).parent.parent

# Logging configuration
LOGGING_CONFIG = {
    "development": {
        "log_level": "DEBUG",
        "log_dir": BASE_DIR / "logs" / "dev",
    },
    "production": {
        "log_level": "INFO",
        "log_dir": BASE_DIR / "logs" / "prod",
    },
    "testing": {
        "log_level": "DEBUG",
        "log_dir": None,  # Console only
    },
}

ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
CURRENT_LOGGING_CONFIG = LOGGING_CONFIG[ENVIRONMENT]
