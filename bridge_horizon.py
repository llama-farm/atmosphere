#!/usr/bin/env python3
"""
Bridge: Register HORIZON with Atmosphere mesh via OpenAPI auto-discovery,
AND stream HORIZON events to mesh clients via push_event.
"""

import asyncio
import json
import logging
import sys

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("horizon-bridge")

sys.path.insert(0, ".")

from atmosphere.sdk.app import AtmosphereApp

HORIZON_URL = "http://localhost:8074"


async def stream_sse_events(app: AtmosphereApp):
    """Subscribe to HORIZON SSE and push events through the mesh."""
    logger.info("Connecting to HORIZON SSE stream...")
    
    while True:
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", f"{HORIZON_URL}/api/logs/stream") as response:
                    logger.info("✅ Connected to HORIZON SSE stream")
                    buffer = ""
                    async for chunk in response.aiter_text():
                        buffer += chunk
                        while "\n\n" in buffer:
                            event_str, buffer = buffer.split("\n\n", 1)
                            # Parse SSE format: "data: {...json...}"
                            for line in event_str.strip().split("\n"):
                                if line.startswith("data: "):
                                    try:
                                        event_data = json.loads(line[6:])
                                        event_type = event_data.get("type", "unknown")
                                        
                                        # Push through mesh to all connected clients
                                        await app.events.emit(event_type, event_data)
                                        logger.debug(f"Pushed event: {event_type}")
                                    except json.JSONDecodeError:
                                        pass
        except httpx.ReadTimeout:
            logger.warning("SSE stream timeout, reconnecting...")
        except httpx.ConnectError:
            logger.warning("HORIZON not available, retrying in 5s...")
        except Exception as e:
            logger.error(f"SSE stream error: {e}, retrying in 5s...")
        
        await asyncio.sleep(5)


async def main():
    app = AtmosphereApp(
        name="horizon",
        description="HORIZON: Disconnected Operations Intelligence Platform for AMC",
        mesh_url="http://localhost:11451",
        app_base_url=HORIZON_URL,
    )

    # Auto-discover all HORIZON endpoints from its OpenAPI spec
    count = await app.register_from_openapi(
        extra_keywords={
            "anomaly": ["alert", "fuel", "deviation", "threat", "critical", "weather"],
            "mission": ["callsign", "flight", "route", "cargo", "airlift"],
            "agent": ["plan", "recommend", "suggest", "action"],
            "voice": ["listen", "monitor", "audio", "speech"],
            "knowledge": ["rag", "document", "search", "question", "answer"],
            "osint": ["intel", "news", "external", "open-source"],
        },
        push_events={
            "anomaly": ["anomaly:detected", "anomaly:resolved"],
            "mission": ["mission:update"],
            "voice": ["voice:transcript", "voice:priority"],
            "agent": ["agent:action", "agent:hil", "agent:response"],
            "osint": ["osint:update", "osint:critical"],
        },
    )

    print(f"\n✅ Registered {count} capabilities from HORIZON OpenAPI spec")
    print(f"   Tools: {len(app.get_tools())} available")

    # Connect to mesh and stay alive
    await app.start()
    print(f"🌐 HORIZON bridge connected to mesh")

    # Start SSE event streaming in parallel
    sse_task = asyncio.create_task(stream_sse_events(app))
    print(f"📡 Streaming HORIZON events to mesh clients\n")

    # Keep alive
    try:
        await asyncio.gather(sse_task, asyncio.sleep(float('inf')))
    except KeyboardInterrupt:
        sse_task.cancel()
        await app.stop()
        print("Bridge stopped.")


if __name__ == "__main__":
    asyncio.run(main())
