#!/usr/bin/env python3
"""
Atmosphere Project Discovery Parser

Scans LlamaFarm projects and extracts structured metadata using the
config-parser model. Saves results to ~/.llamafarm/atmosphere/projects/

Usage:
    python parse_projects.py [--projects-dir ~/.llamafarm/projects]
    python parse_projects.py --single /path/to/llamafarm.yaml
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import httpx
import yaml


# LlamaFarm API endpoint for the discovery project
LLAMAFARM_BASE = os.getenv("LLAMAFARM_URL", "http://localhost:14345")
ATMOSPHERE_NAMESPACE = "atmosphere"
ATMOSPHERE_PROJECT = "discovery"
PARSER_MODEL = "config-parser"

# Output directory
ATMOSPHERE_DIR = Path.home() / ".llamafarm" / "atmosphere" / "projects"


def parse_config_with_llm(config_content: str, config_path: str) -> Optional[dict]:
    """Send a config to the LLM parser and get structured metadata."""
    
    url = f"{LLAMAFARM_BASE}/v1/projects/{ATMOSPHERE_NAMESPACE}/{ATMOSPHERE_PROJECT}/chat/completions"
    
    payload = {
        "model": PARSER_MODEL,
        "messages": [
            {
                "role": "user",
                "content": f"Parse this LlamaFarm configuration and extract project metadata:\n\n```yaml\n{config_content}\n```"
            }
        ],
        "temperature": 0.1,
        "max_tokens": 2048
    }
    
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # Parse the JSON response
            # Handle potential markdown code blocks
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
            
            metadata = json.loads(content.strip())
            
            # Add source info
            metadata["source_path"] = config_path
            metadata["parsed_at"] = datetime.now(timezone.utc).isoformat()
            metadata["nodes"] = [os.uname().nodename]  # Current node
            
            return metadata
            
    except httpx.HTTPError as e:
        print(f"  ❌ HTTP error: {e}", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"  ❌ JSON parse error: {e}", file=sys.stderr)
        print(f"  Raw content: {content[:200]}...", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  ❌ Error: {e}", file=sys.stderr)
        return None


def parse_config_fallback(config_path: Path) -> Optional[dict]:
    """Fallback parser when LLM is unavailable - extracts basic info."""
    
    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
        
        if not config:
            return None
            
        namespace = config.get("namespace", "default")
        name = config.get("name", config_path.parent.name)
        
        # Extract models
        models = []
        runtime = config.get("runtime", {})
        for model in runtime.get("models", []):
            if isinstance(model, dict) and "name" in model:
                models.append(model["name"])
        
        # Detect capabilities
        capabilities = ["chat"]
        if config.get("rag", {}).get("databases"):
            capabilities.append("rag")
        if any(m.get("tools") for m in runtime.get("models", []) if isinstance(m, dict)):
            capabilities.append("tools")
        if any(m.get("instructor_mode") for m in runtime.get("models", []) if isinstance(m, dict)):
            capabilities.append("structured")
        
        # Extract domain from prompts and config name
        domain = "general"
        topics = []
        description = f"LlamaFarm project: {namespace}/{name}"
        
        prompts = config.get("prompts", [])
        if prompts and isinstance(prompts[0], dict):
            messages = prompts[0].get("messages", [])
            for msg in messages:
                if msg.get("role") == "system":
                    content = msg.get("content", "").lower()
                    description = msg.get("content", "")[:200]  # First 200 chars
                    
                    # Simple domain detection with keywords
                    if "llama" in content or "alpaca" in content or "camelid" in content:
                        domain = "animals/camelids"
                        topics.extend(["llama", "alpaca", "camelid", "fiber", "husbandry"])
                    elif "fishing" in content or "fish" in content:
                        domain = "fishing"
                        topics.extend(["fishing", "fish", "tackle"])
                    elif "medical" in content or "health" in content or "doctor" in content:
                        domain = "healthcare"
                        topics.extend(["medical", "health", "diagnosis"])
                    elif "legal" in content or "law" in content:
                        domain = "legal"
                        topics.extend(["legal", "law", "contracts"])
                    elif "finance" in content or "money" in content or "trading" in content:
                        domain = "finance"
                        topics.extend(["finance", "money", "trading"])
                    elif "code" in content or "programming" in content or "developer" in content:
                        domain = "coding"
                        topics.extend(["code", "programming", "software"])
                    elif "discovery" in content or "config" in content or "parse" in content:
                        domain = "infrastructure"
                        topics.extend(["discovery", "config", "parsing"])
                    break
        
        # Also check name for hints
        name_lower = name.lower()
        if "llama" in name_lower and domain == "general":
            domain = "animals/camelids"
            topics.extend(["llama", "alpaca", "camelid"])
        elif "config" in name_lower or "discovery" in name_lower:
            domain = "infrastructure"
        
        return {
            "namespace": namespace,
            "name": name,
            "models": models or ["default"],
            "domain": domain,
            "capabilities": capabilities,
            "complexity": "rag-enabled" if "rag" in capabilities else "simple",
            "rag_summary": None,
            "topics": list(set(topics)),
            "description": description,
            "source_path": str(config_path),
            "parsed_at": datetime.now(timezone.utc).isoformat(),
            "nodes": [os.uname().nodename]
        }
        
    except Exception as e:
        print(f"  ❌ Fallback parse error: {e}", file=sys.stderr)
        return None


def save_project_metadata(metadata: dict) -> Path:
    """Save parsed project metadata to the atmosphere directory."""
    
    ATMOSPHERE_DIR.mkdir(parents=True, exist_ok=True)
    
    namespace = metadata.get("namespace", "default")
    name = metadata.get("name", "unknown")
    
    # Create namespace subdirectory
    namespace_dir = ATMOSPHERE_DIR / namespace
    namespace_dir.mkdir(exist_ok=True)
    
    # Save as JSON
    output_path = namespace_dir / f"{name}.json"
    with open(output_path, "w") as f:
        json.dump(metadata, f, indent=2)
    
    return output_path


def find_llamafarm_configs(projects_dir: Path) -> list[Path]:
    """Recursively find all llamafarm.yaml files."""
    
    configs = []
    
    for yaml_path in projects_dir.rglob("llamafarm.yaml"):
        # Skip test directories with numeric suffixes
        parent_name = yaml_path.parent.name
        if any(x in parent_name for x in ["test-bootstrap-", "test-gateway-", "test-tools-"]):
            continue
        configs.append(yaml_path)
    
    return configs


def main():
    parser = argparse.ArgumentParser(description="Parse LlamaFarm projects for Atmosphere")
    parser.add_argument(
        "--projects-dir",
        type=Path,
        default=Path.home() / ".llamafarm" / "projects",
        help="Directory containing LlamaFarm projects"
    )
    parser.add_argument(
        "--single",
        type=Path,
        help="Parse a single llamafarm.yaml file"
    )
    parser.add_argument(
        "--fallback",
        action="store_true",
        help="Use fallback parser (no LLM required)"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ATMOSPHERE_DIR,
        help="Output directory for parsed metadata"
    )
    
    args = parser.parse_args()
    
    output_dir = args.output_dir
    
    # Update save function to use the configured output directory
    def save_project(metadata: dict) -> Path:
        """Save parsed project metadata to the atmosphere directory."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        namespace = metadata.get("namespace", "default")
        name = metadata.get("name", "unknown")
        
        # Create namespace subdirectory
        namespace_dir = output_dir / namespace
        namespace_dir.mkdir(exist_ok=True)
        
        # Save as JSON
        out_path = namespace_dir / f"{name}.json"
        with open(out_path, "w") as f:
            json.dump(metadata, f, indent=2)
        
        return out_path
    
    if args.single:
        configs = [args.single]
    else:
        configs = find_llamafarm_configs(args.projects_dir)
    
    print(f"🔍 Found {len(configs)} LlamaFarm configs to parse")
    print(f"📁 Output directory: {output_dir}")
    print()
    
    success = 0
    failed = 0
    
    for config_path in configs:
        print(f"📄 Parsing: {config_path}")
        
        # Read config
        try:
            with open(config_path) as f:
                config_content = f.read()
        except Exception as e:
            print(f"  ❌ Could not read: {e}")
            failed += 1
            continue
        
        # Parse with LLM or fallback
        if args.fallback:
            metadata = parse_config_fallback(config_path)
        else:
            metadata = parse_config_with_llm(config_content, str(config_path))
            if not metadata:
                print("  ⚠️  LLM parse failed, trying fallback...")
                metadata = parse_config_fallback(config_path)
        
        if metadata:
            output_path = save_project(metadata)
            print(f"  ✅ Saved: {output_path}")
            print(f"     Domain: {metadata.get('domain')} | Capabilities: {metadata.get('capabilities')}")
            success += 1
        else:
            print(f"  ❌ Failed to parse")
            failed += 1
    
    print()
    print(f"✅ Parsed: {success}")
    print(f"❌ Failed: {failed}")
    
    # Also save an index file
    index_path = output_dir / "index.json"
    index = {
        "parsed_at": datetime.now(timezone.utc).isoformat(),
        "total_projects": success,
        "node": os.uname().nodename,
        "projects": []
    }
    
    for json_file in output_dir.rglob("*.json"):
        if json_file.name != "index.json":
            try:
                with open(json_file) as f:
                    proj = json.load(f)
                    index["projects"].append({
                        "namespace": proj.get("namespace"),
                        "name": proj.get("name"),
                        "domain": proj.get("domain"),
                        "capabilities": proj.get("capabilities"),
                        "path": str(json_file.relative_to(output_dir))
                    })
            except Exception:
                pass
    
    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)
    
    print(f"📇 Index saved: {index_path}")


if __name__ == "__main__":
    main()
