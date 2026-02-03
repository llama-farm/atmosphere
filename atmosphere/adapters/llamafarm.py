"""
LlamaFarm Execution Adapter.

Provides direct execution interface to LlamaFarm for AI operations.
"""

import os
import aiohttp
from pathlib import Path
from typing import Optional, List, Dict, Any


class LlamaFarmDiscovery:
    """
    Discover LlamaFarm projects and models via API.
    
    By default, only returns the "discoverable" namespace - the subset
    of LlamaFarm capabilities that should be exposed to the mesh.
    """
    
    def __init__(
        self, 
        base_url: str = "http://localhost:14345",
        namespace: str = "discoverable"
    ):
        self.base_url = base_url
        self.namespace = namespace  # Filter to this namespace
    
    def discover_projects(self) -> list:
        """
        List projects from LlamaFarm API, filtered by namespace.
        
        Only returns projects in the configured namespace (default: "discoverable").
        This ensures Atmosphere only exposes what's meant for the mesh.
        """
        import requests
        
        try:
            # Query LlamaFarm API for projects
            response = requests.get(f"{self.base_url}/api/projects", timeout=5)
            if response.status_code != 200:
                return []
            
            all_projects = response.json()
            
            # Filter to only the specified namespace
            if self.namespace:
                # If namespace is set, only return that namespace's projects
                for project in all_projects:
                    if project.get("name") == self.namespace:
                        return [{
                            "name": project.get("name"),
                            "sub_projects": project.get("sub_projects", [])[:10],
                            "sub_project_count": len(project.get("sub_projects", []))
                        }]
                return []  # Namespace not found
            
            return all_projects
            
        except Exception as e:
            # Fallback: return empty if API not available
            return []
    
    def discover_models(self) -> dict:
        """
        List models from LlamaFarm API.
        
        Returns model counts by category, filtered to what's available
        for mesh operations.
        """
        import requests
        
        try:
            response = requests.get(f"{self.base_url}/v1/models", timeout=5)
            if response.status_code != 200:
                return {}
            
            models = response.json().get("data", [])
            
            # Group by category (prefix before /)
            categories = {}
            for model in models:
                model_id = model.get("id", "")
                category = model_id.split("/")[0] if "/" in model_id else "general"
                
                if category not in categories:
                    categories[category] = {"count": 0, "samples": []}
                
                categories[category]["count"] += 1
                if len(categories[category]["samples"]) < 3:
                    categories[category]["samples"].append(model_id)
            
            return categories
            
        except Exception:
            return {}
    
    def get_config(self) -> dict:
        """Get LlamaFarm config via API."""
        import requests
        
        try:
            response = requests.get(f"{self.base_url}/api/config", timeout=5)
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass
        return {}


class LlamaFarmExecutor:
    """Execute AI operations through LlamaFarm"""
    
    def __init__(self, base_url: str = "http://localhost:14345"):
        self.base_url = base_url
        self._session: Optional[aiohttp.ClientSession] = None
        self.discovery = LlamaFarmDiscovery()
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def health(self) -> dict:
        """Check LlamaFarm health"""
        session = await self._get_session()
        async with session.get(f"{self.base_url}/health") as resp:
            return await resp.json()
    
    async def list_models(self) -> List[dict]:
        """Get available models from LlamaFarm"""
        session = await self._get_session()
        async with session.get(f"{self.base_url}/v1/models") as resp:
            data = await resp.json()
            return data.get("data", [])
    
    async def chat(self, model: str, messages: List[dict], **kwargs) -> str:
        """Send chat completion request"""
        session = await self._get_session()
        payload = {
            "model": model,
            "messages": messages,
            **kwargs
        }
        async with session.post(f"{self.base_url}/v1/chat/completions", json=payload) as resp:
            data = await resp.json()
            return data["choices"][0]["message"]["content"]
    
    async def generate(self, model: str, prompt: str, **kwargs) -> str:
        """Simple generate (wraps chat)"""
        return await self.chat(model, [{"role": "user", "content": prompt}], **kwargs)
    
    async def embed(self, model: str, text: str) -> List[float]:
        """Get text embeddings"""
        session = await self._get_session()
        payload = {"model": model, "input": text}
        async with session.post(f"{self.base_url}/v1/embeddings", json=payload) as resp:
            data = await resp.json()
            return data["data"][0]["embedding"]
    
    # ============ ML Endpoints ============
    
    async def detect_anomaly(self, model: str, data: list) -> dict:
        """Detect anomalies using trained model"""
        session = await self._get_session()
        payload = {"model_name": model, "data": data}
        async with session.post(f"{self.base_url}/v1/ml/anomaly/detect", json=payload) as resp:
            return await resp.json()
    
    async def fit_anomaly_detector(self, model: str, data: list, **kwargs) -> dict:
        """Train a new anomaly detector"""
        session = await self._get_session()
        payload = {"model_name": model, "data": data, **kwargs}
        async with session.post(f"{self.base_url}/v1/ml/anomaly/fit", json=payload) as resp:
            return await resp.json()
    
    async def score_anomaly(self, model: str, data: list) -> dict:
        """Get anomaly scores for data"""
        session = await self._get_session()
        payload = {"model_name": model, "data": data}
        async with session.post(f"{self.base_url}/v1/ml/anomaly/score", json=payload) as resp:
            return await resp.json()
    
    async def list_anomaly_models(self) -> list:
        """List available anomaly detection models"""
        session = await self._get_session()
        async with session.get(f"{self.base_url}/v1/ml/anomaly/models") as resp:
            return await resp.json()
    
    async def classify(self, model: str, data: list) -> dict:
        """Classify data using trained model"""
        session = await self._get_session()
        payload = {"model_name": model, "data": data}
        async with session.post(f"{self.base_url}/v1/ml/classifier/predict", json=payload) as resp:
            return await resp.json()
    
    async def fit_classifier(self, model: str, X: list, y: list, **kwargs) -> dict:
        """Train a classifier"""
        session = await self._get_session()
        payload = {"model_name": model, "X": X, "y": y, **kwargs}
        async with session.post(f"{self.base_url}/v1/ml/classifier/fit", json=payload) as resp:
            return await resp.json()
    
    async def list_classifiers(self) -> list:
        """List available classifier models"""
        session = await self._get_session()
        async with session.get(f"{self.base_url}/v1/ml/classifier/models") as resp:
            return await resp.json()
    
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
