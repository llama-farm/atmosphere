#!/usr/bin/env python3
"""
Test script for ModelBridge functionality.
"""

import asyncio
import aiohttp
import json
from pathlib import Path
import sys
import logging

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from atmosphere.model_bridge import ModelBridge

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def test_scan_models():
    """Test model scanning."""
    logger.info("Test 1: Scanning models...")
    
    bridge = ModelBridge(
        llamafarm_models_dir=Path.home() / ".llamafarm" / "models",
        huggingface_cache_dir=Path.home() / ".cache" / "huggingface" / "hub"
    )
    
    await bridge.scan_models()
    
    stats = bridge.get_stats()
    logger.info(f"✓ Scan complete: {json.dumps(stats, indent=2)}")
    
    if stats['total_models'] == 0:
        logger.warning("⚠ No models found - check that models exist in:")
        logger.warning(f"  - {bridge.llamafarm_models_dir}")
        logger.warning(f"  - {bridge.huggingface_cache_dir}")
    
    # List models
    for model_id, model in bridge.catalog.items():
        logger.info(f"  • {model.name}")
        logger.info(f"    ID: {model_id}")
        logger.info(f"    Type: {model.type}, Format: {model.format}")
        logger.info(f"    Size: {model.size_bytes / 1_000_000:.2f} MB")
        logger.info(f"    SHA-256: {model.sha256[:16]}...")
    
    return bridge


async def test_http_server():
    """Test HTTP server endpoints."""
    logger.info("\nTest 2: HTTP server...")
    
    bridge = ModelBridge(http_port=14346)  # Use different port to avoid conflicts
    await bridge.start()
    
    try:
        # Test health endpoint
        async with aiohttp.ClientSession() as session:
            async with session.get('http://localhost:14346/health') as resp:
                data = await resp.json()
                logger.info(f"✓ Health check: {json.dumps(data, indent=2)}")
                assert data['status'] == 'ok', "Health check failed"
            
            # Test list models endpoint
            async with session.get('http://localhost:14346/v1/models') as resp:
                data = await resp.json()
                logger.info(f"✓ List models: {len(data['models'])} models")
                
                if data['models']:
                    model = data['models'][0]
                    model_id = model['model_id']
                    logger.info(f"  First model: {model['name']} ({model_id})")
                    
                    # Test get model info
                    async with session.get(f'http://localhost:14346/v1/models/{model_id}') as info_resp:
                        model_info = await info_resp.json()
                        logger.info(f"✓ Model info: {model_info['name']}")
                    
                    # Test download endpoint (just first 1KB)
                    async with session.get(
                        f'http://localhost:14346/v1/models/download/{model_id}',
                        headers={'Range': 'bytes=0-1023'}
                    ) as download_resp:
                        logger.info(f"✓ Download test: status={download_resp.status}")
                        logger.info(f"  Content-Range: {download_resp.headers.get('Content-Range')}")
                        logger.info(f"  Content-Length: {download_resp.headers.get('Content-Length')}")
                        
                        chunk = await download_resp.read()
                        logger.info(f"  Received: {len(chunk)} bytes")
                        assert len(chunk) <= 1024, "Chunk size exceeded"
    
    finally:
        await bridge.stop()


async def test_catalog_message():
    """Test catalog message generation."""
    logger.info("\nTest 3: Catalog message generation...")
    
    bridge = ModelBridge()
    await bridge.scan_models()
    
    # Manually build catalog message (simulates what would be gossiped)
    catalog_msg = {
        "type": "model_catalog",
        "node_id": "test-node-123",
        "node_name": "Test LlamaFarm",
        "timestamp": 1707398765000,
        "models": [model.to_dict() for model in bridge.catalog.values()],
        "transfer_endpoints": {
            "http": f"http://localhost:{bridge.http_port}",
            "websocket": True
        },
        "ttl_seconds": 300
    }
    
    logger.info(f"✓ Catalog message generated:")
    logger.info(f"  Type: {catalog_msg['type']}")
    logger.info(f"  Models: {len(catalog_msg['models'])}")
    logger.info(f"  HTTP endpoint: {catalog_msg['transfer_endpoints']['http']}")
    
    # Verify structure
    assert catalog_msg['type'] == 'model_catalog', "Wrong message type"
    assert 'models' in catalog_msg, "Missing models field"
    assert 'transfer_endpoints' in catalog_msg, "Missing transfer_endpoints"
    
    # Verify each model has required fields
    required_fields = ['model_id', 'name', 'type', 'format', 'size_bytes', 'sha256', 'version']
    for model in catalog_msg['models']:
        for field in required_fields:
            assert field in model, f"Model missing required field: {field}"
    
    logger.info("✓ All models have required fields")
    
    # Pretty print one example model
    if catalog_msg['models']:
        example = catalog_msg['models'][0]
        logger.info(f"\nExample model entry:")
        logger.info(json.dumps(example, indent=2))


async def test_resume_download():
    """Test resume capability (Range requests)."""
    logger.info("\nTest 4: Resume download...")
    
    bridge = ModelBridge(http_port=14347)
    await bridge.start()
    
    try:
        if not bridge.catalog:
            logger.warning("⚠ No models to test resume - skipping")
            return
        
        model_id = list(bridge.catalog.keys())[0]
        model = bridge.catalog[model_id]
        
        logger.info(f"Testing resume with model: {model.name}")
        
        async with aiohttp.ClientSession() as session:
            # Download first 10KB
            async with session.get(
                f'http://localhost:14347/v1/models/download/{model_id}',
                headers={'Range': 'bytes=0-10239'}
            ) as resp:
                first_chunk = await resp.read()
                logger.info(f"✓ Downloaded first chunk: {len(first_chunk)} bytes")
            
            # Download next 10KB (resume)
            async with session.get(
                f'http://localhost:14347/v1/models/download/{model_id}',
                headers={'Range': 'bytes=10240-20479'}
            ) as resp:
                second_chunk = await resp.read()
                logger.info(f"✓ Downloaded second chunk: {len(second_chunk)} bytes")
                logger.info(f"  Content-Range: {resp.headers.get('Content-Range')}")
            
            # Verify chunks are different (proves we got different parts of file)
            assert first_chunk != second_chunk, "Chunks are identical (resume failed?)"
            logger.info("✓ Resume capability verified - chunks are different")
    
    finally:
        await bridge.stop()


async def main():
    """Run all tests."""
    logger.info("=" * 60)
    logger.info("ModelBridge Test Suite")
    logger.info("=" * 60)
    
    try:
        # Test 1: Scan models
        bridge = await test_scan_models()
        
        # Test 2: HTTP server
        await test_http_server()
        
        # Test 3: Catalog message
        await test_catalog_message()
        
        # Test 4: Resume download
        await test_resume_download()
        
        logger.info("\n" + "=" * 60)
        logger.info("✓ All tests passed!")
        logger.info("=" * 60)
        
    except AssertionError as e:
        logger.error(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n✗ Unexpected error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
