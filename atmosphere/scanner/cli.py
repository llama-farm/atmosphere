"""
Scanner CLI Module

Provides the `atmosphere scan` command for capability discovery.
"""

import asyncio
import json
import logging
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .gpu import detect_gpus, get_gpu_summary
from .models import detect_models, get_models_summary
from .hardware import detect_hardware, get_hardware_summary
from .services import detect_services, get_services_summary
from .permissions import check_permissions

console = Console()
logger = logging.getLogger(__name__)

# Suppress httpx info logs during scan
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


@click.command()
@click.option('--json', 'output_json', is_flag=True, help='Output as JSON')
@click.option('--gpu', 'scan_gpu', is_flag=True, help='Scan GPUs only')
@click.option('--models', 'scan_models', is_flag=True, help='Scan models only')
@click.option('--hardware', 'scan_hardware', is_flag=True, help='Scan hardware only')
@click.option('--services', 'scan_services', is_flag=True, help='Scan services only')
@click.option('--permissions', 'scan_perms', is_flag=True, help='Check permissions only')
@click.option('--ollama-host', default='localhost', help='Ollama host')
@click.option('--ollama-port', default=11434, type=int, help='Ollama port')
@click.option('--no-hf', is_flag=True, help='Skip HuggingFace cache scan')
@click.option('--gguf', is_flag=True, help='Also scan for GGUF files')
@click.pass_context
def scan(
    ctx,
    output_json: bool,
    scan_gpu: bool,
    scan_models: bool,
    scan_hardware: bool,
    scan_services: bool,
    scan_perms: bool,
    ollama_host: str,
    ollama_port: int,
    no_hf: bool,
    gguf: bool,
):
    """
    Scan system for available AI capabilities.
    
    Discovers GPUs, models, hardware devices, and running services.
    
    \b
    Examples:
      atmosphere scan              # Full scan
      atmosphere scan --json       # JSON output
      atmosphere scan --gpu        # GPUs only
      atmosphere scan --models     # Models only
      atmosphere scan --hardware   # Cameras, mics only
      atmosphere scan --services   # Running services only
    """
    # If no specific flags, scan everything
    scan_all = not any([scan_gpu, scan_models, scan_hardware, scan_services, scan_perms])
    
    results = {}
    
    if output_json:
        # Quiet mode for JSON output
        results = asyncio.run(_scan_all(
            scan_all or scan_gpu,
            scan_all or scan_models,
            scan_all or scan_hardware,
            scan_all or scan_services,
            scan_all or scan_perms,
            ollama_host,
            ollama_port,
            not no_hf,
            gguf,
        ))
        click.echo(json.dumps(results, indent=2, default=str))
    else:
        # Rich console output
        _scan_with_progress(
            scan_all or scan_gpu,
            scan_all or scan_models,
            scan_all or scan_hardware,
            scan_all or scan_services,
            scan_all or scan_perms,
            ollama_host,
            ollama_port,
            not no_hf,
            gguf,
        )


async def _scan_all(
    do_gpu: bool,
    do_models: bool,
    do_hardware: bool,
    do_services: bool,
    do_perms: bool,
    ollama_host: str,
    ollama_port: int,
    scan_hf: bool,
    scan_gguf: bool,
) -> dict:
    """Run all scans and return results dict."""
    results = {}
    
    if do_perms:
        perms = check_permissions()
        results["permissions"] = {k: v.to_dict() for k, v in perms.items()}
    
    if do_gpu:
        gpus = detect_gpus()
        results["gpus"] = [g.to_dict() for g in gpus]
    
    if do_models:
        models = await detect_models(
            ollama_host=ollama_host,
            ollama_port=ollama_port,
            scan_huggingface=scan_hf,
            scan_gguf=scan_gguf,
        )
        results["models"] = {
            source: [m.to_dict() for m in model_list]
            for source, model_list in models.items()
        }
    
    if do_hardware:
        hardware = detect_hardware()
        results["hardware"] = {
            "cameras": [c.to_dict() for c in hardware.get("cameras", [])],
            "microphones": [m.to_dict() for m in hardware.get("microphones", [])],
            "speakers": [s.to_dict() for s in hardware.get("speakers", [])],
        }
    
    if do_services:
        services = await detect_services()
        results["services"] = [s.to_dict() for s in services]
    
    return results


def _scan_with_progress(
    do_gpu: bool,
    do_models: bool,
    do_hardware: bool,
    do_services: bool,
    do_perms: bool,
    ollama_host: str,
    ollama_port: int,
    scan_hf: bool,
    scan_gguf: bool,
):
    """Run scans with rich progress display."""
    
    console.print()
    console.print(Panel.fit(
        "[bold blue]🔍 Atmosphere Capability Scanner[/bold blue]",
        border_style="blue"
    ))
    console.print()
    
    results = {}
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        
        # Permissions check
        if do_perms:
            task = progress.add_task("Checking permissions...", total=None)
            perms = check_permissions()
            results["permissions"] = perms
            progress.remove_task(task)
        
        # GPU scan
        if do_gpu:
            task = progress.add_task("Scanning GPUs...", total=None)
            gpus = detect_gpus()
            results["gpus"] = gpus
            progress.remove_task(task)
        
        # Model scan
        if do_models:
            task = progress.add_task("Scanning models...", total=None)
            models = asyncio.run(detect_models(
                ollama_host=ollama_host,
                ollama_port=ollama_port,
                scan_huggingface=scan_hf,
                scan_gguf=scan_gguf,
            ))
            results["models"] = models
            progress.remove_task(task)
        
        # Hardware scan
        if do_hardware:
            task = progress.add_task("Scanning hardware...", total=None)
            hardware = detect_hardware()
            results["hardware"] = hardware
            progress.remove_task(task)
        
        # Service scan
        if do_services:
            task = progress.add_task("Scanning services...", total=None)
            services = asyncio.run(detect_services())
            results["services"] = services
            progress.remove_task(task)
    
    # Display results
    _display_results(results)


def _display_results(results: dict):
    """Display scan results in a nice format."""
    
    # GPUs
    gpus = results.get("gpus", [])
    if gpus:
        console.print("[bold cyan]GPUs:[/bold cyan]")
        for gpu in gpus:
            # Build info string
            parts = [f"[green]{gpu.name}[/green]"]
            
            if gpu.metal_version:
                parts.append(f"Metal {gpu.metal_version}")
            elif gpu.cuda_version:
                parts.append(f"CUDA {gpu.cuda_version}")
            
            if gpu.cores:
                parts.append(f"{gpu.cores} cores")
            
            if gpu.memory_mb:
                mem_gb = gpu.memory_mb / 1024
                if gpu.unified_memory:
                    parts.append(f"{mem_gb:.0f}GB unified")
                else:
                    parts.append(f"{mem_gb:.0f}GB VRAM")
            
            console.print(f"  ✓ {' - '.join(parts)}")
        console.print()
    
    # Models
    models = results.get("models", {})
    if models:
        console.print("[bold cyan]Models:[/bold cyan]")
        
        # Ollama
        ollama = models.get("ollama", [])
        if ollama:
            console.print(f"  [yellow]Ollama ({len(ollama)} models):[/yellow]")
            for m in sorted(ollama, key=lambda x: x.size_bytes, reverse=True)[:5]:
                size = _format_size(m.size_bytes)
                console.print(f"    ✓ {m.name} ({size})")
            if len(ollama) > 5:
                console.print(f"    [dim]... and {len(ollama) - 5} more[/dim]")
        
        # LlamaFarm
        llamafarm = models.get("llamafarm", [])
        if llamafarm:
            console.print(f"  [yellow]LlamaFarm ({len(llamafarm)} models):[/yellow]")
            for m in llamafarm[:3]:
                console.print(f"    ✓ {m.name}")
        
        # HuggingFace
        hf = models.get("huggingface", [])
        if hf:
            total = sum(m.size_bytes for m in hf)
            console.print(f"  [yellow]HuggingFace Cache ({len(hf)} models, {_format_size(total)}):[/yellow]")
            for m in sorted(hf, key=lambda x: x.size_bytes, reverse=True)[:3]:
                console.print(f"    ✓ {m.name} ({_format_size(m.size_bytes)})")
            if len(hf) > 3:
                console.print(f"    [dim]... and {len(hf) - 3} more[/dim]")
        
        # GGUF
        gguf = models.get("gguf", [])
        if gguf:
            console.print(f"  [yellow]GGUF Files ({len(gguf)}):[/yellow]")
            for m in gguf[:3]:
                console.print(f"    ✓ {m.name} ({_format_size(m.size_bytes)})")
        
        console.print()
    
    # Hardware
    hardware = results.get("hardware", {})
    cameras = hardware.get("cameras", [])
    mics = hardware.get("microphones", [])
    speakers = hardware.get("speakers", [])
    
    if cameras or mics or speakers:
        console.print("[bold cyan]Hardware:[/bold cyan]")
        
        for cam in cameras:
            prefix = "📷" if cam.is_builtin else "🎥"
            console.print(f"  {prefix} {cam.name}")
        
        for mic in mics:
            prefix = "🎙️" if mic.is_builtin else "🎤"
            console.print(f"  {prefix} {mic.name}")
        
        for spk in speakers:
            console.print(f"  🔊 {spk.name}")
        
        console.print()
    
    # Services
    services = results.get("services", [])
    if services:
        console.print("[bold cyan]Services:[/bold cyan]")
        for svc in sorted(services, key=lambda s: s.port):
            status = "[green]✓[/green]" if svc.healthy else "[yellow]?[/yellow]"
            
            details = []
            if svc.version:
                details.append(f"v{svc.version}")
            if svc.details:
                if "model_count" in svc.details:
                    details.append(f"{svc.details['model_count']} models")
            
            detail_str = f" [dim]({', '.join(details)})[/dim]" if details else ""
            console.print(f"  {status} {svc.name}: {svc.endpoint}{detail_str}")
        console.print()
    
    # Permissions (show warnings only)
    perms = results.get("permissions", {})
    warnings = []
    for name, perm in perms.items():
        if not perm.can_detect:
            warnings.append(f"Cannot detect {name} hardware")
    
    if warnings:
        console.print("[yellow]⚠️  Permission Notes:[/yellow]")
        for w in warnings:
            console.print(f"  • {w}")
        console.print()


def _format_size(size_bytes: int) -> str:
    """Format bytes to human-readable size."""
    if size_bytes == 0:
        return "0B"
    
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}PB"
