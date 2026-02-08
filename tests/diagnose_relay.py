#!/usr/bin/env python3
"""
Relay Connection Diagnostic Tool

Checks the actual connection status to the relay server.
"""

import asyncio
import json
import aiohttp
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def check_relay_health():
    """Check if relay server is responding."""
    relay_url = "https://atmosphere-relay-production.up.railway.app"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{relay_url}/health", timeout=10.0) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"✅ Relay server is healthy")
                    logger.info(f"  - Meshes: {data.get('meshes', 0)}")
                    logger.info(f"  - Connections: {data.get('connections', 0)}")
                    logger.info(f"  - Registered meshes: {data.get('registered_meshes', 0)}")
                    logger.info(f"  - Uptime: {data.get('uptime_seconds', 0):.2f}s")
                    return data
                else:
                    logger.error(f"❌ Relay server returned status {resp.status}")
                    return None
    except Exception as e:
        logger.error(f"❌ Failed to connect to relay: {e}")
        return None


async def check_local_server():
    """Check if local Atmosphere server is running."""
    local_url = "http://localhost:11451"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{local_url}/api/mesh/status", timeout=5.0) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    logger.info(f"✅ Local server is running")
                    logger.info(f"  - Mesh: {data.get('mesh_name')} ({data.get('mesh_id')})")
                    logger.info(f"  - Peer count: {data.get('peer_count', 0)}")
                    logger.info(f"  - Capabilities: {len(data.get('capabilities', []))}")
                    return data
                else:
                    logger.error(f"❌ Local server returned status {resp.status}")
                    return None
    except Exception as e:
        logger.error(f"❌ Failed to connect to local server: {e}")
        return None


async def check_relay_connection():
    """Check if Mac is actually connected to relay by inspecting the relay's connections."""
    relay_health = await check_relay_health()
    
    if relay_health:
        connections = relay_health.get('connections', 0)
        if connections == 0:
            logger.warning("⚠️  Relay shows 0 active connections")
            logger.warning("    This means the Mac server is NOT maintaining a WebSocket connection to the relay")
            logger.warning("    Even though the mesh may be registered, no live connection exists")
            return False
        else:
            logger.info(f"✅ Relay has {connections} active connection(s)")
            return True
    
    return False


async def main():
    logger.info("=" * 60)
    logger.info("ATMOSPHERE RELAY CONNECTION DIAGNOSTIC")
    logger.info("=" * 60)
    
    logger.info("\n--- Checking Relay Server ---")
    relay_ok = await check_relay_health()
    
    logger.info("\n--- Checking Local Server ---")
    local_ok = await check_local_server()
    
    logger.info("\n--- Checking Relay Connection ---")
    connected = await check_relay_connection()
    
    logger.info("\n" + "=" * 60)
    logger.info("DIAGNOSTIC SUMMARY")
    logger.info("=" * 60)
    
    if relay_ok and local_ok:
        if connected:
            logger.info("✅ Everything looks good! Relay connection is active.")
        else:
            logger.warning("⚠️  ISSUE: Local server is running but NOT connected to relay")
            logger.warning("    Possible causes:")
            logger.warning("    1. Relay connection task failed to start")
            logger.warning("    2. WebSocket connection was dropped and not reconnected")
            logger.warning("    3. Authentication/token issue preventing connection")
            logger.warning("    4. Network connectivity problem")
            logger.warning("\n    Next steps:")
            logger.warning("    - Check server logs for relay connection errors")
            logger.warning("    - Verify relay_url in ~/.atmosphere/config.json")
            logger.warning("    - Restart the Atmosphere server")
    else:
        if not relay_ok:
            logger.error("❌ Cannot reach relay server")
        if not local_ok:
            logger.error("❌ Local Atmosphere server is not running")


if __name__ == "__main__":
    asyncio.run(main())
