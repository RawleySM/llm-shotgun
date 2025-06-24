"""
LLM Demo Service
Demonstrates integration of FD 5 (Fallback Handling) and FD 6 (Metrics Collection)
in a simulated LLM token generation pipeline.
"""

import asyncio
import random
import time
from typing import Dict, Any, List, Optional
from datetime import datetime
from app.services.fallback import fallback_service
from app.services.metrics import metrics_service
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class LLMDemoService:
    """Demo service showing FD 5 and FD 6 integration"""
    
    def __init__(self):
        self.provider_failure_rates = {
            "openai": 0.1,      # 10% failure rate
            "anthropic": 0.15,  # 15% failure rate  
            "google": 0.2,      # 20% failure rate
            "deepseek": 0.25,   # 25% failure rate
            "cohere": 0.3       # 30% failure rate
        }
    
    async def simulate_llm_request(self, prompt: str, preferred_model: str = "gpt-4") -> Dict[str, Any]:
        """
        Simulate an LLM request with FD 5 fallback handling and FD 6 metrics collection
        """
        request_id = f"req_{int(time.time() * 1000)}"
        logger.info(f"Starting LLM request simulation: {request_id}")
        
        start_time = time.time()
        attempted_models = []
        current_model = preferred_model
        
        # Track metrics for FD 6
        tokens_generated = 0
        
        while current_model and len(attempted_models) < 4:  # Max 4 attempts
            attempted_models.append(current_model)
            provider = self._get_provider_for_model(current_model)
            
            logger.info(f"Attempting {provider}/{current_model} (attempt {len(attempted_models)})")
            
            try:
                # Simulate token generation with potential failure
                result = await self._simulate_provider_call(provider, current_model, prompt)
                
                if result["success"]:
                    # Success! Record metrics and return
                    tokens_generated = result["tokens_generated"]
                    duration_ms = (time.time() - start_time) * 1000
                    
                    # FD 6: Update metrics
                    metrics_service.record_flush_duration(duration_ms)
                    metrics_service.record_db_write()
                    for _ in range(tokens_generated):
                        metrics_service.add_mock_buffer_item(f"token_{tokens_generated}")
                    
                    # FD 5: Record successful fallback (if this wasn't the first attempt)
                    if len(attempted_models) > 1:
                        fallback_service.record_fallback_success(current_model, provider)
                    
                    return {
                        "request_id": request_id,
                        "success": True,
                        "final_model": current_model,
                        "final_provider": provider,
                        "attempts": len(attempted_models),
                        "tokens_generated": tokens_generated,
                        "duration_ms": duration_ms,
                        "attempted_models": attempted_models
                    }
                
            except Exception as e:
                # Provider failed - use FD 5 fallback handling
                logger.warning(f"Provider {provider}/{current_model} failed: {str(e)}")
                
                fallback_result = await fallback_service.handle_provider_failure(
                    failed_provider=provider,
                    failed_model=current_model,
                    error=e,
                    request_id=request_id,
                    attempted_models=attempted_models
                )
                
                if fallback_result["should_fallback"]:
                    current_model = fallback_result["fallback_model"]
                    logger.info(f"Falling back to {current_model} after {fallback_result['jitter_applied']:.2f}s jitter")
                else:
                    # No more fallbacks available
                    logger.error("All fallback options exhausted")
                    break
        
        # All attempts failed
        duration_ms = (time.time() - start_time) * 1000
        return {
            "request_id": request_id,
            "success": False,
            "final_model": None,
            "final_provider": None,
            "attempts": len(attempted_models),
            "tokens_generated": 0,
            "duration_ms": duration_ms,
            "attempted_models": attempted_models,
            "error": "All providers failed"
        }
    
    async def _simulate_provider_call(self, provider: str, model: str, prompt: str) -> Dict[str, Any]:
        """Simulate a call to an LLM provider"""
        # Simulate network delay
        await asyncio.sleep(random.uniform(0.5, 2.0))
        
        # Check if this provider/model should fail
        failure_rate = self.provider_failure_rates.get(provider, 0.2)
        if random.random() < failure_rate:
            # Simulate different types of failures
            failure_types = [
                "Connection timeout",
                "Rate limit exceeded", 
                "Authentication failed",
                "Model temporarily unavailable"
            ]
            raise Exception(random.choice(failure_types))
        
        # Success! Generate mock tokens
        tokens_generated = random.randint(10, 50)
        
        # Simulate token streaming with buffer updates
        for i in range(tokens_generated):
            if i % 5 == 0:  # Update buffer length every 5 tokens
                metrics_service.update_buffer_length(i)
            await asyncio.sleep(0.01)  # Small delay between tokens
        
        return {
            "success": True,
            "tokens_generated": tokens_generated,
            "model_used": model,
            "provider_used": provider
        }
    
    def _get_provider_for_model(self, model: str) -> str:
        """Map model names to providers"""
        model_to_provider = {
            "gpt-4": "openai",
            "gpt-3.5-turbo": "openai", 
            "claude-3-opus": "anthropic",
            "claude-haiku": "anthropic",
            "gemini-pro": "google",
            "gemini-flash": "google", 
            "deepseek-chat": "deepseek",
            "command-r": "cohere"
        }
        return model_to_provider.get(model, "openai")
    
    async def run_demo_scenarios(self) -> List[Dict[str, Any]]:
        """Run multiple demo scenarios to showcase FD 5 and FD 6"""
        scenarios = [
            {"prompt": "Hello, world!", "model": "gpt-4"},
            {"prompt": "Explain quantum computing", "model": "claude-3-opus"},  
            {"prompt": "Write a Python function", "model": "gemini-pro"},
            {"prompt": "Summarize this text", "model": "deepseek-chat"},
            {"prompt": "Generate a creative story", "model": "command-r"}
        ]
        
        results = []
        
        for i, scenario in enumerate(scenarios):
            logger.info(f"Running demo scenario {i+1}/{len(scenarios)}")
            result = await self.simulate_llm_request(scenario["prompt"], scenario["model"])
            results.append(result)
            
            # Small delay between scenarios
            await asyncio.sleep(1)
        
        return results
    
    async def get_demo_summary(self) -> Dict[str, Any]:
        """Get summary of demo results with FD 5 and FD 6 metrics"""
        fallback_stats = fallback_service.get_fallback_statistics()
        metrics = await metrics_service.collect_metrics()
        
        return {
            "demo_summary": {
                "fallback_statistics": fallback_stats,
                "current_metrics": metrics,
                "demo_timestamp": datetime.utcnow().isoformat()
            }
        }


# Global instance
llm_demo_service = LLMDemoService() 