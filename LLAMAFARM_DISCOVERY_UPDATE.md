# LlamaFarm Discovery Update - Complete

## Problem Solved
The Integration UI was showing only generic Ollama models without discovering the real LlamaFarm project structure and specialized models.

## Changes Made

### 1. Enhanced LlamaFarm Adapter (`atmosphere/adapters/llamafarm.py`)
Added `LlamaFarmDiscovery` class with three key methods:

```python
class LlamaFarmDiscovery:
    """Discover LlamaFarm projects and specialized models"""
    
    LLAMAFARM_HOME = Path.home() / ".llamafarm"
    
    def discover_projects(self) -> list:
        """List all projects with their sub-projects"""
        # Discovers all projects in ~/.llamafarm/projects/
        # Returns name, path, sub_projects (first 10), sub_project_count
    
    def discover_models(self) -> dict:
        """List all specialized models by category"""
        # Discovers models in ~/.llamafarm/models/
        # Returns count and samples for each category
    
    def get_config(self) -> dict:
        """Load LlamaFarm config from config.yaml"""
```

### 2. Updated `/v1/integrations` API Endpoint (`atmosphere/api/routes.py`)
Enhanced the endpoint to return rich LlamaFarm structure:

```json
{
  "llamafarm": {
    "status": "healthy",
    "config": {...},
    "projects": [
      {
        "name": "default",
        "sub_projects": ["commoditybrain", "elder-care-demo", ...],
        "sub_project_count": 114
      }
    ],
    "specialized_models": {
      "anomaly": {"count": 802, "samples": [...]},
      "classifier": {"count": 190, "samples": [...]},
      "router": {"count": 7, "samples": [...]}
    },
    "ollama_models": ["model1", "model2", ...],
    "ollama_model_count": 53,
    "total_model_count": 1082,
    "capabilities": ["chat", "embeddings", "completions", "classification", "anomaly-detection", "routing"]
  }
}
```

### 3. Updated Integration UI (`ui/src/components/IntegrationPanel.jsx`)
Added three new sections for LlamaFarm:

1. **Projects Section** - Shows all projects with expandable sub-project lists
2. **Specialized Models Section** - Displays model categories (anomaly, classifier, router, drift) with counts and samples
3. **Ollama Models Section** - Separate section for raw LLM models

Features:
- Projects displayed in a grid with sub-project counts
- Specialized models shown as cards with category-specific icons and colors
- Hover effects and visual polish
- Maintains backward compatibility with non-LlamaFarm integrations

### 4. Enhanced Styling (`ui/src/components/IntegrationPanel.css`)
Added comprehensive styles:

- `.llamafarm-projects` - Projects grid layout
- `.project-card` - Individual project display with hover effects
- `.llamafarm-specialized` - Specialized models section
- `.specialized-card` - Category cards with color-coded styling:
  - Anomaly: Orange gradient (🔍)
  - Classifier: Green gradient (🏷️)
  - Router: Indigo gradient (🔀)
  - Drift: Pink gradient (📊)
- Responsive design that adapts to different screen sizes
- LlamaFarm cards span 2 columns on larger screens

## Discovered Structure

### Projects: 55
Examples:
- **default**: 114 sub-projects (commoditybrain, elder-care-demo, equipment-monitor-demo, etc.)
- **edge**: Edge computing projects
- **needle**: Needle-specific projects
- **moltbot**: Moltbot workspace

### Specialized Models: 15 Categories
- **anomaly**: 802 models (Isolation Forest, Local Outlier Factor, etc.)
- **classifier**: 190 models (Decision Trees, Random Forests, etc.)
- **router**: 7 routing models
- **drift**: Drift detection models
- **timeseries**: 2 models
- And more...

### Ollama Models: 53
Standard LLM models accessible via Ollama API

### Total: 1,082 Models

## Testing

### Test the API:
```bash
curl http://localhost:8000/v1/integrations | python3 -m json.tool
```

### Test Discovery Directly:
```bash
cd ~/clawd/projects/atmosphere
source .venv/bin/activate
python -c "
from atmosphere.adapters.llamafarm import LlamaFarmDiscovery
disc = LlamaFarmDiscovery()
print('Projects:', len(disc.discover_projects()))
print('Models:', {k: v['count'] for k, v in disc.discover_models().items()})
"
```

### View the UI:
Open browser to: `http://localhost:11451`
Navigate to the Integrations panel

## Server Management

### Restart Atmosphere:
```bash
# Kill existing server
pkill -f "uvicorn atmosphere"

# Start new server
cd ~/clawd/projects/atmosphere
source .venv/bin/activate
uvicorn atmosphere.api.server:create_app --factory --port 8000 --host 127.0.0.1
```

### UI is on port 11451:
The Vite dev server runs on port 11451 (configured in `vite.config.js`)

## Result
The Integration UI now properly reflects the rich LlamaFarm ecosystem:
- ✅ Discovers all 55 projects with sub-project counts
- ✅ Shows 802 anomaly detectors, 190 classifiers, 7 routers, etc.
- ✅ Separates Ollama models from specialized models
- ✅ Beautiful, color-coded cards for each category
- ✅ Maintains backward compatibility with other backends
- ✅ Responsive design that works on all screen sizes

This is a **rich AI ecosystem**, not just basic Ollama models! 🚀
