"""
Atmosphere Menu Bar App.

Native macOS menu bar application that:
- Shows Atmosphere status in the menu bar
- Runs the API server in background
- Provides quick access to common actions
- Auto-updates with mesh status
"""

import rumps
import threading
import webbrowser
import subprocess
import json
import os
from pathlib import Path
from typing import Optional
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("/tmp/atmosphere-menubar.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("atmosphere.menubar")


class AtmosphereMenuBar(rumps.App):
    """
    Atmosphere menu bar application.
    
    Provides a native macOS menu bar interface for controlling
    and monitoring the Atmosphere mesh API server.
    """
    
    def __init__(self):
        # Get icon path (relative to this file's location)
        icon_path = self._get_icon_path()
        
        # Use title "☁️" if no icon found (ensures menu is clickable)
        super().__init__(
            "☁️",  # Emoji fallback ensures visibility
            icon=icon_path if icon_path and Path(icon_path).exists() else None,
            template=True,  # Makes icon work with dark/light mode
            quit_button=None  # We'll add our own
        )
        
        # If icon loaded, clear the title so only icon shows
        if icon_path and Path(icon_path).exists():
            self.title = None
        
        self.server_thread: Optional[threading.Thread] = None
        self.server_running = False
        self.mesh_info = {}
        self.api_port = 11451
        
        # Create menu items - use strings for simpler items
        self.status_item = rumps.MenuItem("● Starting...")
        self.mesh_item = rumps.MenuItem("Mesh: Discovering...")
        self.models_item = rumps.MenuItem("Models: Scanning...")
        
        # Build menu using @rumps.clicked decorator pattern
        self.menu = [
            self.status_item,
            self.mesh_item, 
            self.models_item,
            None,  # Separator
            "Open Dashboard",
            "View API Docs",
            "View Capabilities",
            None,
            "Copy API URL",
            "Copy cURL",
            None,
            "View Logs",
            "Open Config",
            None,
            "Quit Atmosphere",
        ]
        
        logger.info("AtmosphereMenuBar initialized")
    
    def _get_icon_path(self) -> Optional[str]:
        """Get the path to the menu bar icon."""
        # Try multiple locations
        locations = [
            Path(__file__).parent.parent / "assets" / "icon.png",
            Path(__file__).parent.parent / "assets" / "menubar-icon.png",
            Path.home() / ".atmosphere" / "icon.png",
        ]
        
        for path in locations:
            if path.exists():
                return str(path)
        
        return None
    
    def start_server(self) -> bool:
        """Start the API server in a background thread."""
        if self.server_running:
            logger.warning("Server already running")
            return True
        
        def run_server():
            try:
                # Import here to avoid circular imports
                from atmosphere.api.server import create_app
                import uvicorn
                
                logger.info(f"Starting API server on port {self.api_port}")
                app = create_app()
                
                config = uvicorn.Config(
                    app,
                    host="127.0.0.1",
                    port=self.api_port,
                    log_level="warning",
                    access_log=False
                )
                server = uvicorn.Server(config)
                server.run()
                
            except Exception as e:
                logger.error(f"Server error: {e}")
                self.server_running = False
                rumps.notification(
                    title="Atmosphere Error",
                    subtitle="Server Failed",
                    message=str(e)[:100]
                )
        
        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        self.server_running = True
        
        # Wait a moment for server to start
        import time
        time.sleep(1.5)
        
        # Update status
        self._update_status_active()
        
        logger.info("Server thread started")
        return True
    
    def _update_status_active(self):
        """Update menu to show active status."""
        self.status_item.title = f"● Running on localhost:{self.api_port}"
        
        # Show notification
        rumps.notification(
            title="Atmosphere",
            subtitle="Server Started",
            message=f"API available at http://localhost:{self.api_port}"
        )
    
    @rumps.timer(5)  # Update every 5 seconds
    def update_mesh_status(self, _):
        """Periodically update mesh status in the menu."""
        if not self.server_running:
            return
        
        try:
            import urllib.request
            import json
            
            # Fetch status from API
            url = f"http://localhost:{self.api_port}/api/status"
            with urllib.request.urlopen(url, timeout=2) as response:
                data = json.loads(response.read().decode())
            
            # Update mesh info
            peers = data.get("peers", 0)
            mesh_name = data.get("mesh_name", "Local")
            
            if mesh_name and mesh_name != "None":
                self.mesh_item.title = f"Mesh: {mesh_name} ({peers} peers)"
            else:
                self.mesh_item.title = f"Mesh: Local only ({peers} peers)"
            
            # Update models
            capabilities = data.get("capabilities", [])
            if capabilities:
                self.models_item.title = f"Capabilities: {', '.join(capabilities[:3])}"
                if len(capabilities) > 3:
                    self.models_item.title += f" +{len(capabilities) - 3}"
            else:
                self.models_item.title = "Capabilities: None detected"
            
            self.mesh_info = data
            
        except Exception as e:
            # Server might not be ready yet
            logger.debug(f"Status update failed: {e}")
    
    @rumps.clicked("Open Dashboard")
    def open_dashboard(self, _):
        """Open the web dashboard."""
        webbrowser.open(f"http://localhost:{self.api_port}")
    
    @rumps.clicked("View API Docs")
    def view_api_docs(self, _):
        """Open the API documentation."""
        webbrowser.open(f"http://localhost:{self.api_port}/docs")
    
    @rumps.clicked("View Capabilities")
    def view_capabilities(self, _):
        """Open the capabilities endpoint."""
        webbrowser.open(f"http://localhost:{self.api_port}/api/capabilities")
    
    @rumps.clicked("Copy API URL")
    def copy_api_url(self, _):
        """Copy the API URL to clipboard."""
        url = f"http://localhost:{self.api_port}"
        subprocess.run(["pbcopy"], input=url.encode(), check=True)
        rumps.notification(
            title="Atmosphere",
            subtitle="",
            message="API URL copied to clipboard"
        )
    
    @rumps.clicked("Copy cURL")
    def copy_curl(self, _):
        """Copy a sample cURL command to clipboard."""
        curl_cmd = f'''curl http://localhost:{self.api_port}/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{{"model": "auto", "messages": [{{"role": "user", "content": "Hello!"}}]}}'
'''
        subprocess.run(["pbcopy"], input=curl_cmd.encode(), check=True)
        rumps.notification(
            title="Atmosphere",
            subtitle="",
            message="cURL command copied to clipboard"
        )
    
    @rumps.clicked("View Logs")
    def view_logs(self, _):
        """Open the log file in Console.app."""
        log_file = "/tmp/atmosphere.log"
        if not Path(log_file).exists():
            log_file = "/tmp/atmosphere-menubar.log"
        
        subprocess.run(["open", "-a", "Console", log_file])
    
    @rumps.clicked("Open Config")
    def open_config(self, _):
        """Open the config file or directory."""
        config_dir = Path.home() / ".atmosphere"
        config_file = config_dir / "config.json"
        
        if config_file.exists():
            subprocess.run(["open", str(config_file)])
        elif config_dir.exists():
            subprocess.run(["open", str(config_dir)])
        else:
            rumps.notification(
                title="Atmosphere",
                subtitle="Config Not Found",
                message="Run 'atmosphere init' first"
            )
    
    @rumps.clicked("Quit Atmosphere")
    def quit_app(self, _):
        """Quit the application."""
        logger.info("Quitting Atmosphere")
        rumps.quit_application()


def main():
    """Main entry point for the menu bar app."""
    logger.info("Starting Atmosphere Menu Bar App")
    
    # Check if node is initialized
    config_path = Path.home() / ".atmosphere" / "identity.json"
    if not config_path.exists():
        # Show alert and offer to initialize
        response = rumps.alert(
            title="Atmosphere Not Initialized",
            message="Would you like to initialize Atmosphere now?\n\nThis will scan for AI backends and set up your node.",
            ok="Initialize",
            cancel="Quit"
        )
        
        if response == 1:  # OK clicked
            # Run atmosphere init
            result = subprocess.run(
                ["atmosphere", "init"],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                rumps.alert(
                    title="Initialization Failed",
                    message=f"Failed to initialize: {result.stderr[:200]}"
                )
                return
        else:
            return
    
    app = AtmosphereMenuBar()
    
    # Start the server
    app.start_server()
    
    # Run the app
    app.run()


if __name__ == "__main__":
    main()
