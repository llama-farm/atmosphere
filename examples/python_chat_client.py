#!/usr/bin/env python3
"""
Simple Atmosphere chat client using the Platform API.

This example shows how to use Atmosphere as an AI backend for your app.
It connects to the local Atmosphere server and sends chat requests.

Usage:
    python3 python_chat_client.py

Requirements:
    pip install requests
"""

import requests
import json
from typing import List, Dict

# Atmosphere API base URL (local server)
BASE_URL = "http://localhost:11451"
API_URL = f"{BASE_URL}/api"


class AtmosphereClient:
    """Simple client for Atmosphere Platform API."""
    
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.session = requests.Session()
    
    def health_check(self) -> bool:
        """Check if Atmosphere server is running."""
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            return False
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "auto",
        temperature: float = 0.7,
        max_tokens: int = 1000
    ) -> Dict:
        """
        Send a chat completion request.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use (default: "auto" for best available)
            temperature: Sampling temperature (0.0 - 2.0)
            max_tokens: Maximum tokens to generate
        
        Returns:
            Response dict with 'choices', 'model', 'usage', etc.
        """
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        response = self.session.post(
            f"{self.api_url}/chat/completions",
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        return response.json()
    
    def route(self, intent: str) -> Dict:
        """
        Route an intent to the best capability (without executing).
        
        Args:
            intent: Natural language description of what to do
        
        Returns:
            Routing result with capability, score, etc.
        """
        payload = {"intent": intent}
        response = self.session.post(f"{self.api_url}/route", json=payload)
        response.raise_for_status()
        return response.json()
    
    def execute(self, intent: str, **kwargs) -> Dict:
        """
        Execute an intent on the mesh.
        
        Args:
            intent: What to do
            **kwargs: Additional arguments
        
        Returns:
            Execution result
        """
        payload = {
            "intent": intent,
            "kwargs": kwargs
        }
        response = self.session.post(f"{self.api_url}/execute", json=payload)
        response.raise_for_status()
        return response.json()
    
    def get_capabilities(self) -> List[Dict]:
        """Get all available capabilities."""
        response = self.session.get(f"{self.api_url}/capabilities")
        response.raise_for_status()
        return response.json()
    
    def get_mesh_status(self) -> Dict:
        """Get mesh network status."""
        response = self.session.get(f"{self.api_url}/mesh/status")
        response.raise_for_status()
        return response.json()
    
    def get_cost_metrics(self) -> Dict:
        """Get current cost metrics."""
        response = self.session.get(f"{self.api_url}/cost/current")
        response.raise_for_status()
        return response.json()


def print_mesh_info(client: AtmosphereClient):
    """Print mesh status and available capabilities."""
    print("\n" + "="*60)
    print("ATMOSPHERE MESH STATUS")
    print("="*60)
    
    # Mesh status
    status = client.get_mesh_status()
    print(f"Mesh: {status.get('mesh_name', 'N/A')} ({status.get('mesh_id', 'N/A')})")
    print(f"Nodes: {status.get('node_count', 0)}")
    print(f"Peers: {status.get('peer_count', 0)}")
    print(f"Is Founder: {status.get('is_founder', False)}")
    
    # Capabilities
    print("\nAvailable Capabilities:")
    caps = client.get_capabilities()
    for cap in caps[:10]:  # Show first 10
        print(f"  - {cap['label']}")
        if cap.get('description'):
            print(f"    {cap['description'][:80]}...")
    
    if len(caps) > 10:
        print(f"  ... and {len(caps) - 10} more")
    
    # Cost metrics
    print("\nCost Metrics:")
    costs = client.get_cost_metrics()
    power = costs.get('power', {})
    compute = costs.get('compute', {})
    print(f"  Battery: {power.get('battery_percent', 0):.1f}% (on_battery: {power.get('on_battery', False)})")
    print(f"  CPU Load: {compute.get('cpu_load', 0)*100:.1f}%")
    print(f"  Memory: {compute.get('memory_percent', 0):.1f}%")
    print(f"  Overall Cost: {costs.get('cost_multiplier', 0):.2f}")
    
    print("="*60 + "\n")


def chat_loop(client: AtmosphereClient):
    """Interactive chat loop."""
    print("Atmosphere Chat Client")
    print("Type 'quit' to exit, 'status' for mesh info\n")
    
    messages = []
    
    while True:
        try:
            user_input = input("You: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() == 'quit':
                print("Goodbye!")
                break
            
            if user_input.lower() == 'status':
                print_mesh_info(client)
                continue
            
            # Add user message
            messages.append({
                "role": "user",
                "content": user_input
            })
            
            # Send to Atmosphere
            print("AI: ", end="", flush=True)
            
            response = client.chat(messages)
            
            # Extract response
            choice = response['choices'][0]
            ai_message = choice['message']['content']
            
            print(ai_message)
            
            # Add assistant message to history
            messages.append({
                "role": "assistant",
                "content": ai_message
            })
            
            # Show metadata
            model = response.get('model', 'unknown')
            print(f"\n(via {model})\n")
            
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}")
            print("Continuing...\n")


def demo_routing(client: AtmosphereClient):
    """Demonstrate intent routing."""
    print("\n" + "="*60)
    print("ROUTING DEMO")
    print("="*60)
    
    intents = [
        "summarize this document",
        "generate an image of a sunset",
        "what's the weather like?",
        "solve this math problem: 2x + 5 = 13"
    ]
    
    for intent in intents:
        print(f"\nIntent: '{intent}'")
        result = client.route(intent)
        print(f"  → Capability: {result.get('capability', 'N/A')}")
        print(f"  → Score: {result.get('score', 0):.3f}")
        print(f"  → Action: {result.get('action', 'N/A')}")
    
    print("\n" + "="*60 + "\n")


def demo_openai_compat():
    """Demonstrate OpenAI SDK compatibility."""
    print("\n" + "="*60)
    print("OpenAI SDK COMPATIBILITY DEMO")
    print("="*60)
    
    try:
        from openai import OpenAI
        
        # Point OpenAI SDK to Atmosphere
        client = OpenAI(
            base_url="http://localhost:11451/v1",
            api_key="not-needed"  # Local mesh doesn't need auth
        )
        
        print("\nSending request via OpenAI SDK...")
        response = client.chat.completions.create(
            model="auto",
            messages=[
                {"role": "user", "content": "What is quantum entanglement? (brief answer)"}
            ]
        )
        
        print(f"\nAI: {response.choices[0].message.content}")
        print(f"(via {response.model})")
        
    except ImportError:
        print("\nOpenAI SDK not installed. Install with:")
        print("  pip install openai")
    except Exception as e:
        print(f"\nError: {e}")
    
    print("\n" + "="*60 + "\n")


def main():
    """Main entry point."""
    client = AtmosphereClient()
    
    # Check if server is running
    if not client.health_check():
        print("ERROR: Atmosphere server is not running!")
        print("Start the server with: atmosphere serve")
        return
    
    print("✓ Connected to Atmosphere")
    
    # Show mesh info
    print_mesh_info(client)
    
    # Demo routing
    demo_routing(client)
    
    # Demo OpenAI compatibility
    demo_openai_compat()
    
    # Interactive chat
    chat_loop(client)


if __name__ == "__main__":
    main()
