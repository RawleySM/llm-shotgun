"""
FD 2.3: Provider Semaphore Service
Implements per-provider concurrency limits to avoid CPU/GPU thrash and vendor rate-limits.
"""

import asyncio
import os
from typing import Dict, Optional, AsyncContextManager
from contextlib import asynccontextmanager
from app.services.data_structures import DEFAULT_PROVIDER_CONFIGS, ProviderConfig
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class ProviderSemaphoreService:
    """
    FD 2.3: Provider semaphore management with environment variable overrides
    """
    
    def __init__(self):
        self.semaphores: Dict[str, asyncio.Semaphore] = {}
        self.provider_configs: Dict[str, ProviderConfig] = {}
        self._initialize_semaphores()
    
    def _initialize_semaphores(self):
        """
        Initialize semaphores for all providers with FSD 2.3 defaults
        and environment variable overrides
        """
        for provider_name, default_config in DEFAULT_PROVIDER_CONFIGS.items():
            # Check for environment variable override
            env_var_name = f"{provider_name.upper()}_CONCURRENCY"
            env_concurrency = os.getenv(env_var_name)
            
            if env_concurrency:
                try:
                    max_concurrency = int(env_concurrency)
                    logger.info(f"Using environment override for {provider_name}: {max_concurrency} "
                               f"(env var: {env_var_name})")
                except ValueError:
                    logger.warning(f"Invalid {env_var_name}={env_concurrency}, using default {default_config.max_concurrency}")
                    max_concurrency = default_config.max_concurrency
            else:
                max_concurrency = default_config.max_concurrency
            
            # Create provider config with potentially overridden concurrency
            self.provider_configs[provider_name] = ProviderConfig(
                name=provider_name,
                max_concurrency=max_concurrency,
                circuit_breaker_failure_threshold=default_config.circuit_breaker_failure_threshold,
                circuit_breaker_timeout_seconds=default_config.circuit_breaker_timeout_seconds,
                probe_timeout_seconds=default_config.probe_timeout_seconds
            )
            
            # Create semaphore
            self.semaphores[provider_name] = asyncio.Semaphore(max_concurrency)
            
            logger.info(f"Initialized semaphore for {provider_name}: max_concurrency={max_concurrency}")
    
    @asynccontextmanager
    async def acquire_semaphore(self, provider: str) -> AsyncContextManager[None]:
        """
        FD 2.7: Acquire semaphore for provider with context manager
        Usage: async with semaphore_service.acquire_semaphore(provider):
        """
        if provider not in self.semaphores:
            logger.error(f"Unknown provider {provider}, creating default semaphore")
            self.semaphores[provider] = asyncio.Semaphore(3)  # Default fallback
        
        semaphore = self.semaphores[provider]
        
        # Log when we're waiting for semaphore (helps debug concurrency issues)
        available = semaphore._value
        if available == 0:
            logger.debug(f"Waiting for semaphore for provider {provider} (all slots in use)")
        
        async with semaphore:
            logger.debug(f"Acquired semaphore for provider {provider}")
            try:
                yield
            finally:
                logger.debug(f"Released semaphore for provider {provider}")
    
    def get_semaphore_status(self, provider: str) -> Dict[str, int]:
        """Get current semaphore status for monitoring"""
        if provider not in self.semaphores:
            return {"available": 0, "max_concurrency": 0}
        
        semaphore = self.semaphores[provider]
        config = self.provider_configs.get(provider)
        
        return {
            "available": semaphore._value,
            "max_concurrency": config.max_concurrency if config else 0,
            "in_use": (config.max_concurrency if config else 0) - semaphore._value
        }
    
    def get_all_semaphore_statuses(self) -> Dict[str, Dict[str, int]]:
        """Get status for all provider semaphores"""
        return {
            provider: self.get_semaphore_status(provider)
            for provider in self.semaphores
        }
    
    def get_provider_config(self, provider: str) -> Optional[ProviderConfig]:
        """Get provider configuration"""
        return self.provider_configs.get(provider)
    
    def add_provider(self, provider_name: str, max_concurrency: int):
        """Dynamically add a new provider (useful for testing or extensions)"""
        config = ProviderConfig(
            name=provider_name,
            max_concurrency=max_concurrency
        )
        
        self.provider_configs[provider_name] = config
        self.semaphores[provider_name] = asyncio.Semaphore(max_concurrency)
        
        logger.info(f"Added new provider {provider_name} with max_concurrency={max_concurrency}")
    
    def update_concurrency_limit(self, provider: str, new_limit: int):
        """Update concurrency limit for a provider (requires restart to take effect)"""
        if provider in self.provider_configs:
            old_limit = self.provider_configs[provider].max_concurrency
            self.provider_configs[provider].max_concurrency = new_limit
            
            # Note: We don't recreate the semaphore here as it could break ongoing operations
            # This change would take effect on application restart
            logger.warning(f"Updated concurrency limit for {provider}: {old_limit} -> {new_limit} "
                         f"(requires restart to take effect)")
        else:
            logger.error(f"Cannot update concurrency limit for unknown provider {provider}")


# Global instance
provider_semaphore_service = ProviderSemaphoreService() 