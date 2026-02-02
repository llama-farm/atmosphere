"""
CLI commands for model deployment.

Integrates with the Atmosphere CLI to provide model management commands.
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from .registry import ModelRegistry, ModelManifest, LLAMAFARM_MODELS_DIR
from .packager import ModelPackager
from .distributor import ModelDistributor, DeploymentStrategy

console = Console()


def run_async(coro):
    """Run an async function."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        return loop.run_until_complete(coro)


@click.group()
def model():
    """Model deployment and management commands."""
    pass


@model.command('list')
@click.option('--mesh', is_flag=True, help='Show all models in the mesh')
@click.option('--available', is_flag=True, help='Show models available but not local')
@click.option('--type', '-t', 'model_type', help='Filter by model type')
@click.option('--capability', '-c', help='Filter by capability')
def list_models(mesh: bool, available: bool, model_type: str, capability: str):
    """List models."""
    
    registry = ModelRegistry()
    run_async(registry.load())
    
    if mesh:
        # Show all models in mesh
        mesh_models = registry.list_mesh()
        
        if not mesh_models:
            console.print("[yellow]No models discovered in mesh yet.[/yellow]")
            return
        
        console.print("\n[bold]Models in Mesh[/bold]\n")
        
        table = Table()
        table.add_column("Name", style="cyan")
        table.add_column("Versions")
        table.add_column("Nodes")
        table.add_column("First Seen")
        
        for info in mesh_models:
            versions = ", ".join(sorted(info.versions.keys(), reverse=True)[:3])
            if len(info.versions) > 3:
                versions += f" (+{len(info.versions) - 3})"
            
            node_count = len(info.get_nodes())
            first_seen = info.first_seen.strftime("%Y-%m-%d") if info.first_seen else "-"
            
            table.add_row(info.name, versions, str(node_count), first_seen)
        
        console.print(table)
    
    elif available:
        # Show models we don't have
        available_models = registry.list_available()
        
        if not available_models:
            console.print("[green]You have all available models![/green]")
            return
        
        console.print("\n[bold]Available Models (not local)[/bold]\n")
        
        table = Table()
        table.add_column("Name", style="cyan")
        table.add_column("Latest Version")
        table.add_column("Available From")
        
        for info in available_models:
            latest = info.latest_version() or "-"
            nodes = info.get_nodes(latest)
            source = f"{len(nodes)} node(s)"
            table.add_row(info.name, latest, source)
        
        console.print(table)
        console.print("\n[dim]Pull with: atmosphere model pull <name>[/dim]")
    
    else:
        # Show local models
        local = registry.list_local()
        
        if model_type:
            local = [e for e in local if e.manifest.type == model_type]
        if capability:
            local = [e for e in local if capability in e.manifest.capabilities]
        
        if not local:
            console.print("[yellow]No local models.[/yellow]")
            console.print("[dim]Import from LlamaFarm: atmosphere model import --llamafarm[/dim]")
            return
        
        console.print("\n[bold]Local Models[/bold]\n")
        
        table = Table()
        table.add_column("Name", style="cyan")
        table.add_column("Version")
        table.add_column("Type")
        table.add_column("Size")
        table.add_column("Capabilities")
        table.add_column("Loaded", justify="center")
        
        for entry in local:
            m = entry.manifest
            size = _format_size(m.size_bytes)
            caps = ", ".join(m.capabilities[:2])
            if len(m.capabilities) > 2:
                caps += "..."
            loaded = "[green]✓[/green]" if entry.loaded else "[dim]-[/dim]"
            
            table.add_row(m.name, m.version, m.type, size, caps, loaded)
        
        console.print(table)
        console.print(f"\n[dim]Total: {len(local)} models, {_format_size(sum(e.manifest.size_bytes for e in local))}[/dim]")


@model.command('info')
@click.argument('name')
@click.option('--versions', is_flag=True, help='Show all versions')
@click.option('--nodes', is_flag=True, help='Show which nodes have it')
def model_info(name: str, versions: bool, nodes: bool):
    """Show detailed information about a model."""
    
    registry = ModelRegistry()
    run_async(registry.load())
    
    # Try local first
    entry = registry.get_local(name)
    
    if entry:
        console.print(f"\n[bold]Model: {entry.manifest.name}[/bold]\n")
        
        table = Table(show_header=False, box=None)
        table.add_column("Key", style="dim")
        table.add_column("Value")
        
        m = entry.manifest
        table.add_row("Version", m.version)
        table.add_row("Type", m.type)
        table.add_row("Format", m.format)
        table.add_row("Size", _format_size(m.size_bytes))
        table.add_row("Checksum", m.checksum_sha256[:16] + "..." if m.checksum_sha256 else "-")
        table.add_row("Path", str(entry.path))
        table.add_row("Loaded", "[green]Yes[/green]" if entry.loaded else "No")
        table.add_row("Source", entry.source_node or "local")
        
        console.print(table)
        
        if m.capabilities:
            console.print(f"\n[bold]Capabilities:[/bold] {', '.join(m.capabilities)}")
        
        if m.requirements:
            console.print(f"\n[bold]Requirements:[/bold]")
            for req in m.requirements:
                console.print(f"  • {req}")
        
        if m.config:
            console.print(f"\n[bold]Config:[/bold]")
            for k, v in m.config.items():
                console.print(f"  • {k}: {v}")
    
    else:
        # Check mesh
        mesh_info = registry.get_mesh_model(name)
        
        if not mesh_info:
            console.print(f"[red]Model '{name}' not found locally or in mesh.[/red]")
            return
        
        console.print(f"\n[bold]Model: {name}[/bold] [yellow](not local)[/yellow]\n")
        console.print(f"[dim]Pull with: atmosphere model pull {name}[/dim]\n")
    
    # Show versions if requested
    if versions:
        mesh_info = registry.get_mesh_model(name)
        if mesh_info and mesh_info.versions:
            console.print("\n[bold]Available Versions:[/bold]")
            for ver, ver_nodes in sorted(mesh_info.versions.items(), reverse=True):
                console.print(f"  • {ver} - {len(ver_nodes)} node(s)")
    
    # Show nodes if requested
    if nodes:
        node_set = registry.find_nodes_with_model(name)
        if node_set:
            console.print("\n[bold]Available From Nodes:[/bold]")
            for node in sorted(node_set)[:10]:
                console.print(f"  • {node}")
            if len(node_set) > 10:
                console.print(f"  ... and {len(node_set) - 10} more")


@model.command('push')
@click.argument('name')
@click.argument('node', required=False)
@click.option('--role', '-r', help='Push to all nodes with this role')
@click.option('--all', '-a', 'push_all', is_flag=True, help='Push to all capable nodes')
@click.option('--version', '-v', help='Specific version to push')
def push_model(name: str, node: Optional[str], role: str, push_all: bool, version: str):
    """Push a model to specific node(s)."""
    
    if not node and not role and not push_all:
        console.print("[red]Specify a target: <node>, --role, or --all[/red]")
        return
    
    registry = ModelRegistry()
    packager = ModelPackager()
    distributor = ModelDistributor(
        node_id="local",  # TODO: Get from config
        registry=registry,
        packager=packager
    )
    
    run_async(registry.load())
    
    # Find model
    entry = registry.get_local(name, version)
    if not entry:
        console.print(f"[red]Model '{name}' not found locally.[/red]")
        return
    
    version = entry.manifest.version
    
    console.print(f"\n[bold]Pushing {name}:{version}[/bold]\n")
    
    # TODO: Actually push (needs network layer)
    console.print("[yellow]Push requires network layer - coming soon![/yellow]")
    console.print("[dim]Would push to: ", end="")
    
    if node:
        console.print(f"node {node}[/dim]")
    elif role:
        console.print(f"all {role} nodes[/dim]")
    else:
        console.print("all capable nodes[/dim]")


@model.command('pull')
@click.argument('name')
@click.option('--version', '-v', help='Specific version to pull')
@click.option('--from', 'from_node', help='Pull from specific node')
@click.option('--capability', '-c', help='Pull all models with capability')
def pull_model(name: str, version: str, from_node: str, capability: str):
    """Pull a model from the mesh."""
    
    registry = ModelRegistry()
    run_async(registry.load())
    
    # Check if we already have it
    if registry.has_local(name, version):
        console.print(f"[yellow]Model '{name}' already exists locally.[/yellow]")
        return
    
    # Find in mesh
    mesh_info = registry.get_mesh_model(name)
    if not mesh_info:
        console.print(f"[red]Model '{name}' not found in mesh.[/red]")
        console.print("[dim]Run 'atmosphere model list --mesh' to see available models.[/dim]")
        return
    
    target_version = version or mesh_info.latest_version()
    nodes = mesh_info.get_nodes(target_version)
    
    if not nodes:
        console.print(f"[red]No nodes have {name}:{target_version}[/red]")
        return
    
    source = from_node or list(nodes)[0]
    
    console.print(f"\n[bold]Pulling {name}:{target_version} from {source}[/bold]\n")
    
    # TODO: Actually pull (needs network layer)
    console.print("[yellow]Pull requires network layer - coming soon![/yellow]")


@model.command('deploy')
@click.argument('name')
@click.option('--all', '-a', 'deploy_all', is_flag=True, help='Deploy to all capable nodes')
@click.option('--role', '-r', help='Deploy to nodes with this role')
@click.option('--version', '-v', help='Specific version to deploy')
def deploy_model(name: str, deploy_all: bool, role: str, version: str):
    """Deploy a model across the mesh."""
    
    if not deploy_all and not role:
        console.print("[red]Specify target: --all or --role[/red]")
        return
    
    registry = ModelRegistry()
    run_async(registry.load())
    
    entry = registry.get_local(name, version)
    if not entry:
        console.print(f"[red]Model '{name}' not found locally.[/red]")
        return
    
    console.print(f"\n[bold]Deploying {entry.manifest.name}:{entry.manifest.version}[/bold]\n")
    
    # TODO: Actually deploy
    console.print("[yellow]Deploy requires network layer - coming soon![/yellow]")


@model.command('import')
@click.argument('path', required=False)
@click.option('--name', '-n', help='Name for the model')
@click.option('--type', '-t', 'model_type', help='Model type (anomaly_detector, classifier, etc.)')
@click.option('--capability', '-c', 'capabilities', multiple=True, help='Add capability')
@click.option('--llamafarm', is_flag=True, help='Import from LlamaFarm models directory')
@click.option('--llamafarm-type', help='Filter LlamaFarm models by type (anomaly, classifier)')
def import_model(
    path: Optional[str],
    name: str,
    model_type: str,
    capabilities: tuple,
    llamafarm: bool,
    llamafarm_type: str
):
    """Import a model into the registry."""
    
    registry = ModelRegistry()
    run_async(registry.load())
    
    if llamafarm:
        # Scan and import from LlamaFarm
        console.print("\n[bold]Scanning LlamaFarm models...[/bold]\n")
        
        models = run_async(registry.scan_llamafarm(llamafarm_type))
        
        if not models:
            console.print("[yellow]No models found in ~/.llamafarm/models/[/yellow]")
            return
        
        console.print(f"Found {len(models)} model files:\n")
        
        for i, model_path in enumerate(models[:20]):
            rel_path = model_path.relative_to(LLAMAFARM_MODELS_DIR)
            size = _format_size(model_path.stat().st_size)
            console.print(f"  {i+1}. {rel_path} ({size})")
        
        if len(models) > 20:
            console.print(f"  ... and {len(models) - 20} more")
        
        console.print()
        
        if not click.confirm("Import all?"):
            return
        
        imported = 0
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            console=console
        ) as progress:
            task = progress.add_task("Importing...", total=len(models))
            
            for model_path in models:
                try:
                    rel_path = model_path.relative_to(LLAMAFARM_MODELS_DIR)
                    run_async(registry.import_from_llamafarm(
                        str(rel_path),
                        capabilities=list(capabilities) if capabilities else None
                    ))
                    imported += 1
                except Exception as e:
                    console.print(f"[red]Failed: {model_path.name}: {e}[/red]")
                
                progress.advance(task)
        
        console.print(f"\n[green]Imported {imported} models![/green]")
    
    elif path:
        # Import single file
        model_path = Path(path)
        
        if not model_path.exists():
            console.print(f"[red]File not found: {path}[/red]")
            return
        
        model_name = name or model_path.stem.replace("_", "-").lower()
        
        console.print(f"\n[bold]Importing {model_path.name}[/bold]\n")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Importing...", total=None)
            
            entry = run_async(registry.import_model(
                path=model_path,
                name=model_name,
                model_type=model_type or "unknown",
                capabilities=list(capabilities) if capabilities else None,
            ))
            
            progress.update(task, description="Done!")
        
        console.print(f"\n[green]✓ Imported as {entry.manifest.id}[/green]")
        console.print(f"  Path: {entry.path}")
        console.print(f"  Size: {_format_size(entry.manifest.size_bytes)}")
    
    else:
        console.print("[red]Specify a path or use --llamafarm[/red]")


@model.command('status')
@click.argument('name', required=False)
def model_status(name: Optional[str]):
    """Show deployment status."""
    
    registry = ModelRegistry()
    run_async(registry.load())
    
    stats = registry.stats()
    
    console.print("\n[bold]Model Deployment Status[/bold]\n")
    
    table = Table(show_header=False, box=None)
    table.add_column("Metric", style="dim")
    table.add_column("Value")
    
    table.add_row("Local Models", str(stats["local_models"]))
    table.add_row("Mesh Models", str(stats["mesh_models"]))
    table.add_row("Total Size", _format_size(stats["total_size_bytes"]))
    table.add_row("Loaded", str(stats["loaded_count"]))
    
    console.print(table)
    
    if stats["by_type"]:
        console.print("\n[bold]By Type:[/bold]")
        for t, count in stats["by_type"].items():
            console.print(f"  • {t}: {count}")
    
    if stats["by_capability"]:
        console.print("\n[bold]By Capability:[/bold]")
        for cap, count in stats["by_capability"].items():
            console.print(f"  • {cap}: {count}")
    
    console.print()


@model.command('remove')
@click.argument('name')
@click.option('--version', '-v', help='Specific version to remove')
@click.option('--delete', is_flag=True, help='Also delete the model file')
@click.option('--force', '-f', is_flag=True, help='Skip confirmation')
def remove_model(name: str, version: str, delete: bool, force: bool):
    """Remove a model from the registry."""
    
    registry = ModelRegistry()
    run_async(registry.load())
    
    entry = registry.get_local(name, version)
    if not entry:
        console.print(f"[red]Model '{name}' not found.[/red]")
        return
    
    console.print(f"\n[bold]Remove {entry.manifest.id}[/bold]")
    console.print(f"  Path: {entry.path}")
    console.print(f"  Size: {_format_size(entry.manifest.size_bytes)}")
    
    if delete:
        console.print("  [yellow]File will be deleted![/yellow]")
    
    if not force:
        if not click.confirm("\nProceed?"):
            return
    
    success = run_async(registry.unregister_local(
        name, entry.manifest.version, delete_file=delete
    ))
    
    if success:
        console.print(f"\n[green]✓ Removed {entry.manifest.id}[/green]")
    else:
        console.print("[red]Failed to remove model.[/red]")


def _format_size(size_bytes: int) -> str:
    """Format byte size for display."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


# Function to register with main CLI
def register_commands(cli):
    """Register model commands with the main CLI."""
    cli.add_command(model)
