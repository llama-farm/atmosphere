#!/usr/bin/env python3
"""
Test client for Atmosphere Relay Server

Usage:
    # Terminal 1: Start server
    python server.py
    
    # Terminal 2: Run as Mac (LLM provider)
    python test_client.py --node-id mac-1 --capabilities llm,chat --mesh test-mesh
    
    # Terminal 3: Run as Android (LLM requester)
    python test_client.py --node-id android-1 --mesh test-mesh --request-llm "What is 2+2?"
"""

import asyncio
import argparse
import json
import sys
from datetime import datetime

try:
    import websockets
except ImportError:
    print("Install websockets: pip install websockets")
    sys.exit(1)


async def run_client(
    relay_url: str,
    node_id: str,
    mesh_id: str,
    capabilities: list,
    request_llm: str | None = None,
    interactive: bool = True,
):
    """Run a test client that connects to the relay."""
    
    uri = f"{relay_url}/relay/{mesh_id}"
    print(f"[{node_id}] Connecting to {uri}...")
    
    async with websockets.connect(uri) as ws:
        # Register with relay
        await ws.send(json.dumps({
            "type": "register",
            "node_id": node_id,
            "token": "test-token",
            "capabilities": capabilities,
            "name": f"Test Client {node_id}",
        }))
        print(f"[{node_id}] Registered with capabilities: {capabilities}")
        
        # Handle incoming messages
        async def receive_loop():
            try:
                while True:
                    msg = await ws.recv()
                    data = json.loads(msg)
                    msg_type = data.get("type")
                    
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    
                    if msg_type == "peers":
                        peers = data.get("peers", [])
                        print(f"[{timestamp}] Current peers: {[p.get('node_id', p) for p in peers]}")
                    
                    elif msg_type == "peer_joined":
                        print(f"[{timestamp}] Peer joined: {data.get('node_id')} with {data.get('capabilities')}")
                    
                    elif msg_type == "peer_left":
                        print(f"[{timestamp}] Peer left: {data.get('node_id')}")
                    
                    elif msg_type == "message":
                        print(f"[{timestamp}] Message from {data.get('from')}: {data.get('payload')}")
                    
                    elif msg_type == "llm_request":
                        # We're an LLM provider - respond!
                        request_id = data.get("request_id")
                        prompt = data.get("prompt")
                        from_node = data.get("from")
                        print(f"[{timestamp}] LLM request from {from_node}: {prompt}")
                        
                        if "llm" in capabilities or "chat" in capabilities:
                            # Simulate LLM response
                            response = f"Mock LLM response to: '{prompt}' - The answer is 42!"
                            await ws.send(json.dumps({
                                "type": "llm_response",
                                "target": from_node,
                                "request_id": request_id,
                                "response": response,
                            }))
                            print(f"[{timestamp}] Sent LLM response to {from_node}")
                    
                    elif msg_type == "llm_response":
                        print(f"[{timestamp}] LLM response: {data.get('response')}")
                    
                    elif msg_type == "pong":
                        pass  # Ignore pongs
                    
                    elif msg_type == "error":
                        print(f"[{timestamp}] Error: {data.get('message')}")
                    
                    else:
                        print(f"[{timestamp}] Unknown message: {data}")
            
            except websockets.exceptions.ConnectionClosed:
                print(f"[{node_id}] Connection closed")
        
        # Start receive loop
        receive_task = asyncio.create_task(receive_loop())
        
        # If we have an LLM request, send it after a brief delay
        if request_llm:
            await asyncio.sleep(1)  # Wait for peers to be received
            print(f"[{node_id}] Sending LLM request: {request_llm}")
            await ws.send(json.dumps({
                "type": "llm_request",
                "request_id": "test-req-1",
                "prompt": request_llm,
            }))
        
        # Interactive mode - allow sending messages
        if interactive:
            async def input_loop():
                print("\nCommands:")
                print("  b <message>  - Broadcast message")
                print("  d <node> <msg> - Direct message")
                print("  l <prompt>   - LLM request")
                print("  q            - Quit")
                print()
                
                while True:
                    try:
                        line = await asyncio.get_event_loop().run_in_executor(
                            None, sys.stdin.readline
                        )
                        line = line.strip()
                        
                        if not line:
                            continue
                        
                        if line == "q":
                            break
                        
                        if line.startswith("b "):
                            msg = line[2:]
                            await ws.send(json.dumps({
                                "type": "broadcast",
                                "payload": {"message": msg}
                            }))
                            print(f"Broadcast sent: {msg}")
                        
                        elif line.startswith("d "):
                            parts = line[2:].split(" ", 1)
                            if len(parts) == 2:
                                target, msg = parts
                                await ws.send(json.dumps({
                                    "type": "direct",
                                    "target": target,
                                    "payload": {"message": msg}
                                }))
                                print(f"Direct message sent to {target}")
                        
                        elif line.startswith("l "):
                            prompt = line[2:]
                            await ws.send(json.dumps({
                                "type": "llm_request",
                                "request_id": f"req-{datetime.now().timestamp()}",
                                "prompt": prompt
                            }))
                            print(f"LLM request sent: {prompt}")
                        
                    except Exception as e:
                        print(f"Error: {e}")
            
            input_task = asyncio.create_task(input_loop())
            
            # Wait for either task to complete
            done, pending = await asyncio.wait(
                [receive_task, input_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            
            for task in pending:
                task.cancel()
        else:
            # Non-interactive - just wait for messages
            await receive_task


def main():
    parser = argparse.ArgumentParser(description="Atmosphere Relay Test Client")
    parser.add_argument("--url", default="ws://localhost:8765", help="Relay server URL")
    parser.add_argument("--node-id", default="test-node", help="Node ID")
    parser.add_argument("--mesh", default="test-mesh", help="Mesh ID")
    parser.add_argument("--capabilities", default="", help="Comma-separated capabilities")
    parser.add_argument("--request-llm", help="Send an LLM request")
    parser.add_argument("--no-interactive", action="store_true", help="Disable interactive mode")
    
    args = parser.parse_args()
    
    capabilities = [c.strip() for c in args.capabilities.split(",") if c.strip()]
    
    asyncio.run(run_client(
        relay_url=args.url,
        node_id=args.node_id,
        mesh_id=args.mesh,
        capabilities=capabilities,
        request_llm=args.request_llm,
        interactive=not args.no_interactive,
    ))


if __name__ == "__main__":
    main()
