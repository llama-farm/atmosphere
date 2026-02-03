"""
Approval CLI - Interactive approval flow for owner consent.

Provides a beautiful terminal UI for configuring what capabilities
this node exposes to the mesh.
"""

import asyncio
import platform
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
from rich.text import Text
from rich import box

from .config import (
    get_config_path,
    load_config,
    save_config,
    config_exists,
    validate_config,
    get_exposure_summary,
)
from .models import (
    ApprovalConfig,
    MicrophoneMode,
    MeshAccessMode,
)

console = Console()


def _run_async(coro):
    """Run an async coroutine."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        return loop.run_until_complete(coro)


async def _scan_capabilities() -> Dict[str, Any]:
    """Scan for system capabilities using the scanner module."""
    from ..scanner import (
        detect_gpus,
        detect_models,
        detect_hardware,
    )
    
    gpus = detect_gpus()
    models = await detect_models()
    hardware = detect_hardware()
    
    return {
        "gpus": gpus,
        "models": models,
        "hardware": hardware,
    }


def _show_header():
    """Display the approval header."""
    console.print()
    console.print(Panel(
        "[bold white]🛡️  OWNER APPROVAL[/bold white]\n\n"
        "[dim]Configure what capabilities this node exposes to the mesh.\n"
        "Privacy-sensitive items are OFF by default.[/dim]",
        box=box.ROUNDED,
        border_style="blue",
        padding=(1, 2),
    ))
    console.print()


def _show_scan_results(capabilities: Dict[str, Any]):
    """Display what was found during scanning."""
    gpus = capabilities.get("gpus", [])
    models = capabilities.get("models", {})
    hardware = capabilities.get("hardware", {})
    
    # Count everything
    ollama_count = len(models.get("ollama", []))
    llamafarm_count = len(models.get("llamafarm", []))
    hf_count = len(models.get("huggingface", []))
    camera_count = len(hardware.get("cameras", []))
    mic_count = len(hardware.get("microphones", []))
    
    total = ollama_count + llamafarm_count + len(gpus) + camera_count + mic_count
    
    # Build summary table
    table = Table(
        title="[bold]Discovered Capabilities[/bold]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Category", style="cyan")
    table.add_column("Items", style="green")
    table.add_column("Details", style="dim")
    
    # Models
    if ollama_count > 0:
        model_names = [m.name for m in models.get("ollama", [])[:3]]
        details = ", ".join(model_names)
        if ollama_count > 3:
            details += f", ... (+{ollama_count - 3} more)"
        table.add_row("🧠 Ollama Models", str(ollama_count), details)
    
    if llamafarm_count > 0:
        table.add_row("📦 LlamaFarm", str(llamafarm_count), "Projects")
    
    if hf_count > 0:
        table.add_row("🤗 HuggingFace Cache", str(hf_count), "Local cache")
    
    # Hardware
    for gpu in gpus:
        mem_str = ""
        if gpu.memory_mb:
            mem_gb = gpu.memory_mb / 1024
            mem_str = f"{mem_gb:.0f}GB"
            if gpu.unified_memory:
                mem_str += " unified"
        table.add_row("🖥️ GPU", gpu.name, mem_str)
    
    # Sensors
    for cam in hardware.get("cameras", []):
        badge = "built-in" if cam.is_builtin else "external"
        table.add_row("📷 Camera", cam.name, badge)
    
    for mic in hardware.get("microphones", []):
        badge = "built-in" if mic.is_builtin else "external"
        table.add_row("🎤 Microphone", mic.name, badge)
    
    console.print(table)
    console.print()
    
    return total


def _show_current_config(config: ApprovalConfig):
    """Display the current configuration summary."""
    summary = get_exposure_summary(config)
    
    # Create two-column layout
    table = Table(box=box.ROUNDED, show_header=True, header_style="bold")
    table.add_column("✅ Exposed", style="green")
    table.add_column("🔒 Private", style="red")
    
    max_rows = max(len(summary["exposed"]), len(summary["private"]))
    for i in range(max_rows):
        exposed = summary["exposed"][i] if i < len(summary["exposed"]) else ""
        private = summary["private"][i] if i < len(summary["private"]) else ""
        table.add_row(exposed, private)
    
    console.print(table)
    
    # Show limits
    limits = summary["limits"]
    console.print(f"\n[dim]Rate limit: {limits['rate_limit']} • "
                  f"Auth required: {'Yes' if limits['auth_required'] else 'No'}[/dim]")


def _interactive_model_approval(
    config: ApprovalConfig,
    capabilities: Dict[str, Any]
) -> ApprovalConfig:
    """Interactive approval for models."""
    models = capabilities.get("models", {})
    ollama_models = models.get("ollama", [])
    
    console.print("\n[bold cyan]── 🧠 Language Models ──[/bold cyan]\n")
    
    if not ollama_models:
        console.print("[dim]No Ollama models found. Install with: ollama pull llama3.2[/dim]")
        config.exposure.models.ollama.enabled = False
        return config
    
    # Show models
    table = Table(box=box.SIMPLE)
    table.add_column("#", style="dim", width=3)
    table.add_column("Model", style="cyan")
    table.add_column("Size", style="green")
    table.add_column("Family", style="dim")
    
    for i, model in enumerate(ollama_models[:10], 1):
        size = f"{model.size_bytes / (1024**3):.1f}GB" if model.size_bytes else "-"
        family = model.family or "-"
        table.add_row(str(i), model.name, size, family)
    
    if len(ollama_models) > 10:
        table.add_row("...", f"+{len(ollama_models) - 10} more", "", "")
    
    console.print(table)
    console.print()
    
    # Ask about model exposure
    if Confirm.ask("[bold]Expose Ollama models to the mesh?[/bold]", default=True):
        config.exposure.models.ollama.enabled = True
        
        # Ask about filtering
        console.print("\n[dim]You can filter models with patterns (e.g., 'llama*' or '*:7b')[/dim]")
        
        filter_choice = Prompt.ask(
            "Model filtering",
            choices=["all", "select", "pattern"],
            default="all"
        )
        
        if filter_choice == "select":
            # Let user select specific models
            console.print("\n[dim]Enter model numbers to expose (comma-separated), or 'all':[/dim]")
            selection = Prompt.ask("Models", default="all")
            
            if selection.lower() != "all":
                try:
                    indices = [int(x.strip()) - 1 for x in selection.split(",")]
                    selected_names = [
                        ollama_models[i].name 
                        for i in indices 
                        if 0 <= i < len(ollama_models)
                    ]
                    config.exposure.models.ollama.allow = selected_names
                except (ValueError, IndexError):
                    console.print("[yellow]Invalid selection, allowing all models[/yellow]")
        
        elif filter_choice == "pattern":
            # Pattern-based filtering
            allow_pattern = Prompt.ask(
                "Allow pattern (e.g., 'llama*,qwen*')",
                default="*"
            )
            deny_pattern = Prompt.ask(
                "Deny pattern (e.g., '*70b*')",
                default=""
            )
            
            if allow_pattern and allow_pattern != "*":
                config.exposure.models.ollama.patterns.allow = [
                    p.strip() for p in allow_pattern.split(",") if p.strip()
                ]
            if deny_pattern:
                config.exposure.models.ollama.patterns.deny = [
                    p.strip() for p in deny_pattern.split(",") if p.strip()
                ]
    else:
        config.exposure.models.ollama.enabled = False
    
    return config


def _interactive_hardware_approval(
    config: ApprovalConfig,
    capabilities: Dict[str, Any]
) -> ApprovalConfig:
    """Interactive approval for hardware resources."""
    gpus = capabilities.get("gpus", [])
    
    console.print("\n[bold cyan]── 🖥️ Hardware Resources ──[/bold cyan]\n")
    
    # GPU
    if gpus:
        gpu = gpus[0]  # Primary GPU
        mem_str = ""
        if gpu.memory_mb:
            mem_gb = gpu.memory_mb / 1024
            mem_str = f" ({mem_gb:.0f}GB"
            if gpu.unified_memory:
                mem_str += " unified memory"
            mem_str += ")"
        
        console.print(f"[bold]GPU:[/bold] {gpu.name}{mem_str}")
        
        if Confirm.ask("Share GPU for inference?", default=True):
            config.exposure.hardware.gpu.enabled = True
            config.exposure.hardware.gpu.device = gpu.name
            
            # VRAM limit
            default_limit = 80
            limit = IntPrompt.ask(
                "Max VRAM usage %",
                default=default_limit,
            )
            config.exposure.hardware.gpu.limits.max_vram_percent = min(100, max(10, limit))
            
            # Concurrent jobs
            jobs = IntPrompt.ask(
                "Max concurrent GPU jobs",
                default=3,
            )
            config.exposure.hardware.gpu.limits.max_concurrent_jobs = max(1, jobs)
        else:
            config.exposure.hardware.gpu.enabled = False
    else:
        console.print("[dim]No GPU detected[/dim]")
        config.exposure.hardware.gpu.enabled = False
    
    # CPU
    console.print()
    import os
    cpu_count = os.cpu_count() or 4
    console.print(f"[bold]CPU:[/bold] {cpu_count} cores available")
    
    if Confirm.ask("Share CPU for inference?", default=True):
        config.exposure.hardware.cpu.enabled = True
        
        limit = IntPrompt.ask(
            "Max CPU usage %",
            default=50,
        )
        config.exposure.hardware.cpu.limits.max_percent = min(100, max(10, limit))
        
        max_cores = IntPrompt.ask(
            f"Max cores (out of {cpu_count})",
            default=min(cpu_count, 8),
        )
        config.exposure.hardware.cpu.limits.max_cores = min(cpu_count, max(1, max_cores))
    else:
        config.exposure.hardware.cpu.enabled = False
    
    return config


def _interactive_sensor_approval(
    config: ApprovalConfig,
    capabilities: Dict[str, Any]
) -> ApprovalConfig:
    """Interactive approval for privacy-sensitive sensors."""
    hardware = capabilities.get("hardware", {})
    cameras = hardware.get("cameras", [])
    microphones = hardware.get("microphones", [])
    
    console.print("\n[bold red]── 🔴 Privacy-Sensitive ──[/bold red]")
    console.print("[dim]These capabilities have privacy implications. OFF by default.[/dim]\n")
    
    # Camera
    if cameras:
        cam = cameras[0]
        console.print(f"[bold]Camera:[/bold] {cam.name}")
        console.print("[yellow]⚠️  Enabling camera allows mesh agents to capture images[/yellow]")
        
        if Confirm.ask("Enable camera access?", default=False):
            config.exposure.sensors.camera.enabled = True
            
            mode = Prompt.ask(
                "Camera mode",
                choices=["stills", "video"],
                default="stills"
            )
            from .models import CameraMode
            config.exposure.sensors.camera.settings.mode = CameraMode(mode)
        else:
            config.exposure.sensors.camera.enabled = False
    else:
        console.print("[dim]No camera detected[/dim]")
    
    console.print()
    
    # Microphone
    if microphones:
        mic = microphones[0]
        console.print(f"[bold]Microphone:[/bold] {mic.name}")
        
        console.print("""
[dim]Microphone access modes:[/dim]
  [cyan]1.[/cyan] disabled      - No audio access
  [cyan]2.[/cyan] transcription - Audio → text locally (recommended)
  [cyan]3.[/cyan] full          - Raw audio can be streamed
""")
        
        mode_choice = Prompt.ask(
            "Microphone mode",
            choices=["1", "2", "3", "disabled", "transcription", "full"],
            default="1"
        )
        
        mode_map = {
            "1": MicrophoneMode.DISABLED,
            "disabled": MicrophoneMode.DISABLED,
            "2": MicrophoneMode.TRANSCRIPTION,
            "transcription": MicrophoneMode.TRANSCRIPTION,
            "3": MicrophoneMode.FULL,
            "full": MicrophoneMode.FULL,
        }
        
        mode = mode_map.get(mode_choice, MicrophoneMode.DISABLED)
        config.exposure.sensors.microphone.enabled = mode != MicrophoneMode.DISABLED
        config.exposure.sensors.microphone.mode = mode
        
        if mode == MicrophoneMode.TRANSCRIPTION:
            console.print("[green]✓ Transcription mode: Audio → text locally, raw audio never leaves[/green]")
        elif mode == MicrophoneMode.FULL:
            console.print("[yellow]⚠️  Full mode: Raw audio can be streamed to mesh[/yellow]")
    else:
        console.print("[dim]No microphone detected[/dim]")
    
    console.print()
    
    # Screen capture
    console.print("[bold]Screen Capture[/bold]")
    console.print("[yellow]⚠️  Screen capture exposes your desktop to mesh agents[/yellow]")
    
    if Confirm.ask("Enable screen capture?", default=False):
        config.exposure.sensors.screen.enabled = True
    else:
        config.exposure.sensors.screen.enabled = False
    
    console.print()
    
    # Location
    console.print("[bold]Location[/bold]")
    if Confirm.ask("Share device location?", default=False):
        config.exposure.sensors.location = True
    else:
        config.exposure.sensors.location = False
    
    return config


def _interactive_access_approval(config: ApprovalConfig) -> ApprovalConfig:
    """Interactive approval for access control settings."""
    console.print("\n[bold cyan]── 🔐 Access Control ──[/bold cyan]\n")
    
    # Authentication
    if Confirm.ask("Require authentication for capability access?", default=True):
        config.access.auth.require = True
        config.access.auth.allow_anonymous = False
    else:
        config.access.auth.require = False
        if Confirm.ask("Allow anonymous queries?", default=False):
            config.access.auth.allow_anonymous = True
    
    # Rate limiting
    console.print()
    rate_limit = IntPrompt.ask(
        "Max requests per minute (global)",
        default=60,
    )
    config.access.rate_limits.global_limits.requests_per_minute = max(1, rate_limit)
    
    return config


def _apply_quick_defaults(config: ApprovalConfig, capabilities: Dict[str, Any]) -> ApprovalConfig:
    """Apply safe defaults without interaction."""
    gpus = capabilities.get("gpus", [])
    
    # Models - enable all
    config.exposure.models.ollama.enabled = True
    config.exposure.models.llamafarm.enabled = True
    
    # Hardware - enable with limits
    if gpus:
        config.exposure.hardware.gpu.enabled = True
        config.exposure.hardware.gpu.device = gpus[0].name
        config.exposure.hardware.gpu.limits.max_vram_percent = 80
        config.exposure.hardware.gpu.limits.max_concurrent_jobs = 3
    
    config.exposure.hardware.cpu.enabled = True
    config.exposure.hardware.cpu.limits.max_percent = 50
    
    # Sensors - all OFF (privacy-sensitive)
    config.exposure.sensors.camera.enabled = False
    config.exposure.sensors.microphone.enabled = False
    config.exposure.sensors.screen.enabled = False
    config.exposure.sensors.location = False
    
    # Access control
    config.access.auth.require = True
    config.access.auth.allow_anonymous = False
    config.access.rate_limits.global_limits.requests_per_minute = 60
    
    return config


@click.command('approve')
@click.option('--interactive/--no-interactive', default=True,
              help='Run in interactive mode (default) or just show current config')
@click.option('--quick', is_flag=True,
              help='Apply safe defaults without prompts')
@click.option('--show', is_flag=True,
              help='Show current configuration and exit')
@click.option('--reset', is_flag=True,
              help='Reset to defaults')
@click.pass_context
def approve(ctx, interactive: bool, quick: bool, show: bool, reset: bool):
    """Configure what capabilities to expose to the mesh.
    
    This command helps you decide what your node shares with the Atmosphere mesh.
    Privacy-sensitive items (camera, microphone, screen) are OFF by default.
    
    Examples:
    
      atmosphere approve              # Interactive setup
      atmosphere approve --quick      # Safe defaults, no prompts
      atmosphere approve --show       # View current config
    """
    
    # Show current config only
    if show:
        config = load_config()
        if config is None:
            console.print("[yellow]No configuration found. Run 'atmosphere approve' to create one.[/yellow]")
            return
        
        console.print("\n[bold]Current Configuration[/bold]\n")
        _show_current_config(config)
        
        # Show warnings
        warnings = validate_config(config)
        if warnings:
            console.print("\n[bold yellow]Warnings:[/bold yellow]")
            for w in warnings:
                console.print(f"  • {w}")
        
        console.print(f"\n[dim]Config file: {get_config_path()}[/dim]\n")
        return
    
    # Load or create config
    if reset or not config_exists():
        config = ApprovalConfig.with_safe_defaults(platform.node())
    else:
        config = load_config() or ApprovalConfig.with_safe_defaults(platform.node())
    
    # Set node name if not set
    if not config.node.name:
        config.node.name = platform.node()
    
    _show_header()
    
    # Scan for capabilities
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("🔍 Scanning capabilities...", total=None)
        
        try:
            capabilities = _run_async(_scan_capabilities())
        except Exception as e:
            console.print(f"[red]Scan error: {e}[/red]")
            capabilities = {"gpus": [], "models": {}, "hardware": {}}
    
    # Show what was found
    total_caps = _show_scan_results(capabilities)
    
    if total_caps == 0:
        console.print("[yellow]No capabilities found. Install Ollama to get started:[/yellow]")
        console.print("  [dim]ollama pull llama3.2[/dim]\n")
    
    # Quick mode - just apply defaults
    if quick:
        config = _apply_quick_defaults(config, capabilities)
        
        # Show summary
        console.print("[bold]Applying safe defaults...[/bold]\n")
        _show_current_config(config)
        
        # Save
        path = save_config(config)
        console.print(f"\n[green]✅ Configuration saved to {path}[/green]\n")
        return
    
    # Non-interactive - just show current config
    if not interactive:
        console.print("[bold]Current Configuration[/bold]\n")
        _show_current_config(config)
        console.print(f"\n[dim]Config file: {get_config_path()}[/dim]")
        console.print("[dim]Use --interactive or no flag to modify.[/dim]\n")
        return
    
    # Interactive approval flow
    try:
        config = _interactive_model_approval(config, capabilities)
        config = _interactive_hardware_approval(config, capabilities)
        config = _interactive_sensor_approval(config, capabilities)
        config = _interactive_access_approval(config)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Aborted. No changes saved.[/yellow]\n")
        return
    
    # Show final summary
    console.print("\n" + "─" * 50 + "\n")
    console.print("[bold]📋 Configuration Summary[/bold]\n")
    _show_current_config(config)
    
    # Validate
    warnings = validate_config(config)
    if warnings:
        console.print("\n[bold yellow]Warnings:[/bold yellow]")
        for w in warnings:
            console.print(f"  • {w}")
    
    # Confirm and save
    console.print()
    if Confirm.ask("[bold]Save this configuration?[/bold]", default=True):
        path = save_config(config)
        console.print(f"\n[green]✅ Configuration saved![/green]")
        console.print(f"   [dim]{path}[/dim]\n")
        
        console.print("[dim]Next steps:[/dim]")
        console.print("  atmosphere serve       Start the API server")
        console.print("  atmosphere mesh join   Join a mesh")
        console.print("  atmosphere approve --show   View this config\n")
    else:
        console.print("\n[yellow]Configuration not saved.[/yellow]\n")
