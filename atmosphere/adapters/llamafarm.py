"""
LlamaFarm Execution Adapter.

Provides direct execution interface to LlamaFarm for AI operations.
"""

import os
import aiohttp
from pathlib import Path
from typing import Optional, List, Dict, Any


class LlamaFarmDiscovery:
    """Discover LlamaFarm projects and specialized models"""
    
    LLAMAFARM_HOME = Path.home() / ".llamafarm"
    
    def discover_projects(self) -> list:
        """List all projects with their sub-projects"""
        projects_dir = self.LLAMAFARM_HOME / "projects"
        if not projects_dir.exists():
            return []
        
        projects = []
        for project in projects_dir.iterdir():
            if project.is_dir() and not project.name.startswith('.'):
                try:
                    sub_projects = [p.name for p in project.iterdir() if p.is_dir() and not p.name.startswith('.')]
                    projects.append({
                        "name": project.name,
                        "path": str(project),
                        "sub_projects": sub_projects[:10],  # First 10
                        "sub_project_count": len(sub_projects)
                    })
                except PermissionError:
                    continue
        return projects
    
    def discover_models(self) -> dict:
        """List all specialized models by category"""
        models_dir = self.LLAMAFARM_HOME / "models"
        if not models_dir.exists():
            return {}
        
        categories = {}
        for category in models_dir.iterdir():
            if category.is_dir() and not category.name.startswith('.'):
                try:
                    models = [m.name for m in category.iterdir() if not m.name.startswith('.')]
                    categories[category.name] = {
                        "count": len(models),
                        "samples": models[:5]  # First 5
                    }
                except PermissionError:
                    continue
        return categories
    
    def get_config(self) -> dict:
        """Load LlamaFarm config"""
        config_path = self.LLAMAFARM_HOME / "config.yaml"
        if config_path.exists():
            try:
                import yaml
                return yaml.safe_load(config_path.read_text())
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
