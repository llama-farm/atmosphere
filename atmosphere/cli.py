"""
Atmosphere CLI - Command line interface for mesh networking.
"""

import asyncio
import json
import logging
import platform
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .config import Config, get_config, DEFAULT_DATA_DIR
from .mesh.node import Node, NodeIdentity, MeshIdentity
from .deployment.cli import model as model_commands

console = Console()


def setup_logging(verbose: bool = False):
    """Set up logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[logging.StreamHandler()]
    )


def run_async(coro):
    """Run an async function."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    else:
        return loop.run_until_complete(coro)


@click.group()
@click.option('-v', '--verbose', is_flag=True, help='Enable verbose output')
@click.pass_context
def main(ctx, verbose):
    """🌐 Atmosphere - The Internet of Intent"""
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose
    setup_logging(verbose)


@main.command()
@click.option('--name', '-n', help='Node name (defaults to hostname)')
@click.option('--data-dir', type=click.Path(), help='Data directory')
def init(name: Optional[str], data_dir: Optional[str]):
    """Initialize this node for the Atmosphere mesh."""
    
    data_path = Path(data_dir) if data_dir else DEFAULT_DATA_DIR
    config = Config(data_dir=data_path)
    
    console.print("\n[bold blue]🌐 Atmosphere Initialization[/bold blue]\n")
    
    # Check if already initialized
    if config.identity_path.exists():
        console.print("[yellow]⚠️  This node is already initialized.[/yellow]")
        console.print(f"   Data directory: {data_path}")
        
        identity = NodeIdentity.load(config.identity_path)
        console.print(f"   Node ID: [cyan]{identity.node_id}[/cyan]")
        console.print(f"   Name: {identity.name}")
        
        if not click.confirm("\nReinitialize? This will reset your identity."):
            return
    
    # Generate node identity
    node_name = name or platform.node() or "atmosphere-node"
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Generating node identity...", total=None)
        
        identity = NodeIdentity.generate(node_name)
        identity.save(config.identity_path)
        
        progress.update(task, description="Scanning for AI backends...")
        
        # Scan for backends
        backends = run_async(_scan_backends())
        
        from .config import BackendConfig
        for backend in backends:
            config.backends[backend['type']] = BackendConfig(
                type=backend['type'],
                host=backend['host'],
                port=backend['port'],
                models=[m['name'] for m in backend.get('models', [])],
                enabled=True
            )
        
        config.node_id = identity.node_id
        config.node_name = identity.name
        config.capabilities = []
        for backend in backends:
            config.capabilities.extend(backend['capabilities'])
        
        config.save()
        progress.update(task, description="Done!")
    
    # Show results
    console.print("\n[bold green]✓ Node initialized successfully![/bold green]\n")
    
    table = Table(show_header=False, box=None)
    table.add_column("Key", style="dim")
    table.add_column("Value")
    
    table.add_row("Node ID", f"[cyan]{identity.node_id}[/cyan]")
    table.add_row("Name", identity.name)
    table.add_row("Data Directory", str(data_path))
    
    console.print(table)
    
    if backends:
        console.print("\n[bold]Discovered Backends:[/bold]")
        for backend in backends:
            models = backend.get('models', [])
            console.print(f"  • {backend['type']}: [green]{len(models)} models[/green]")
            for model in models[:3]:
                model_name = model.get('name', str(model)) if isinstance(model, dict) else model
                console.print(f"    - {model_name}")
            if len(models) > 3:
                console.print(f"    ... and {len(models) - 3} more")
    else:
        console.print("\n[yellow]No AI backends found. Install Ollama:[/yellow]")
        console.print("  [dim]ollama pull llama3.2[/dim]")
        console.print("  [dim]ollama pull nomic-embed-text[/dim]")
    
    console.print("\n[dim]Next steps:[/dim]")
    console.print("  atmosphere serve       Start the API server")
    console.print("  atmosphere mesh create Create a new mesh")
    console.print("  atmosphere mesh join   Join an existing mesh")
    console.print()


async def _scan_backends():
    """Scan for AI backends."""
    from .discovery.scanner import Scanner
    
    scanner = Scanner()
    try:
        backends = await scanner.scan()
        return [b.to_dict() for b in backends]
    finally:
        await scanner.close()


@main.command()
@click.option('--host', '-h', default='0.0.0.0', help='Host to bind to')
@click.option('--port', '-p', default=11451, type=int, help='Port to bind to')
@click.option('--reload', is_flag=True, help='Enable auto-reload')
def serve(host: str, port: int, reload: bool):
    """Start the Atmosphere API server."""
    
    config = get_config()
    
    if not config.identity_path.exists():
        console.print("[red]Node not initialized. Run 'atmosphere init' first.[/red]")
        sys.exit(1)
    
    console.print(f"\n[bold blue]🌐 Starting Atmosphere Server[/bold blue]")
    console.print(f"   Listening on: http://{host}:{port}")
    console.print(f"   Press Ctrl+C to stop\n")
    
    from .api.server import run_server
    
    config.server.host = host
    config.server.port = port
    config.save()
    
    run_server(host=host, port=port, reload=reload)


@main.command()
def status():
    """Show node and mesh status."""
    
    config = get_config()
    
    if not config.identity_path.exists():
        console.print("[yellow]Node not initialized. Run 'atmosphere init' first.[/yellow]")
        return
    
    identity = NodeIdentity.load(config.identity_path)
    
    console.print("\n[bold]Node Status[/bold]")
    
    table = Table(show_header=False, box=None)
    table.add_column("Key", style="dim")
    table.add_column("Value")
    
    table.add_row("Node ID", f"[cyan]{identity.node_id}[/cyan]")
    table.add_row("Name", identity.name)
    table.add_row("Data Directory", str(config.data_dir))
    
    # Mesh info
    if config.mesh_path.exists():
        mesh = MeshIdentity.load(config.mesh_path)
        table.add_row("Mesh", f"[green]{mesh.name}[/green] ({mesh.mesh_id})")
        table.add_row("Role", "Founder" if mesh.can_issue_certificates() else "Member")
    else:
        table.add_row("Mesh", "[dim]Not joined[/dim]")
    
    # Capabilities
    if config.capabilities:
        table.add_row("Capabilities", ", ".join(config.capabilities))
    
    # Backends
    backend_status = []
    for name, backend in config.backends.items():
        enabled = backend.enabled if hasattr(backend, 'enabled') else backend.get('enabled', True)
        if enabled:
            backend_status.append(f"[green]{name}[/green]")
    if backend_status:
        table.add_row("Backends", " ".join(backend_status))
    
    console.print(table)
    console.print()


@main.group()
def mesh():
    """Mesh network management commands."""
    pass


@mesh.command('create')
@click.option('--name', '-n', required=True, help='Mesh name')
@click.option('--threshold', '-t', default=1, type=int, help='Signing threshold')
@click.option('--shares', '-s', default=1, type=int, help='Total key shares')
@click.option('--endpoint', '-e', help='Public endpoint (auto-detected if not specified)')
def mesh_create(name: str, threshold: int, shares: int, endpoint: str):
    """Create a new mesh network."""
    
    config = get_config()
    
    if not config.identity_path.exists():
        console.print("[red]Node not initialized. Run 'atmosphere init' first.[/red]")
        sys.exit(1)
    
    if config.mesh_path.exists():
        console.print("[yellow]Already a member of a mesh. Leave first with 'atmosphere mesh leave'[/yellow]")
        return
    
    console.print(f"\n[bold blue]Creating mesh: {name}[/bold blue]\n")
    
    # Create mesh
    mesh = MeshIdentity.create(
        name=name,
        threshold=threshold,
        total_shares=shares
    )
    mesh.save(config.mesh_path)
    
    # Update config
    config.mesh.mesh_id = mesh.mesh_id
    config.mesh.mesh_name = mesh.name
    config.mesh.mesh_public_key = mesh.master_public_key
    config.mesh.role = "founder"
    config.save()
    
    # Generate join code with public endpoint discovery
    from .mesh.join import generate_join_code_with_discovery, generate_join_code
    from .mesh.network import gather_network_info
    
    identity = NodeIdentity.load(config.identity_path)
    
    # Discover network info
    async def get_endpoint():
        if endpoint:
            return endpoint
        
        console.print("[dim]Discovering public endpoint...[/dim]")
        info = await gather_network_info(config.server.port)
        
        if info.public_endpoint and info.public_endpoint.is_public:
            console.print(f"[green]✓ Public IP discovered: {info.public_endpoint}[/green]")
            return str(info.public_endpoint)
        else:
            console.print("[yellow]⚠ No public IP detected (behind NAT)[/yellow]")
            console.print("[dim]  Using local endpoint. For internet joins, use --endpoint[/dim]")
            return f"{info.local_ip}:{config.server.port}"
    
    detected_endpoint = run_async(get_endpoint())
    
    join_code = generate_join_code(
        mesh=mesh,
        endpoint=detected_endpoint
    )
    
    console.print("[bold green]✓ Mesh created successfully![/bold green]\n")
    
    table = Table(show_header=False, box=None)
    table.add_column("Key", style="dim")
    table.add_column("Value")
    
    table.add_row("Mesh ID", f"[cyan]{mesh.mesh_id}[/cyan]")
    table.add_row("Name", mesh.name)
    table.add_row("Role", "Founder")
    table.add_row("Join Code", f"[bold yellow]{join_code.code}[/bold yellow]")
    
    console.print(table)
    
    console.print("\n[dim]Share the join code with others to let them join.[/dim]")
    console.print("[dim]Or share the full code for programmatic joining:[/dim]")
    console.print(f"\n  [dim]{join_code.to_compact()[:60]}...[/dim]\n")


@mesh.command('join')
@click.argument('target')
def mesh_join(target: str):
    """Join an existing mesh network.
    
    TARGET can be:
    - A join code (XXXX-XXXX-XXXX)
    - An IP address or hostname
    - A base64 encoded join info
    """
    
    config = get_config()
    
    if not config.identity_path.exists():
        console.print("[red]Node not initialized. Run 'atmosphere init' first.[/red]")
        sys.exit(1)
    
    if config.mesh_path.exists():
        console.print("[yellow]Already a member of a mesh.[/yellow]")
        return
    
    identity = NodeIdentity.load(config.identity_path)
    
    console.print(f"\n[bold blue]Joining mesh...[/bold blue]\n")
    
    from .mesh.join import MeshJoin
    
    join = MeshJoin(identity)
    
    async def do_join():
        try:
            # Determine target type
            if target.count('-') == 2 and len(target) == 14:
                # Short join code
                return await join.join_by_code(target)
            elif target.count('.') >= 1 or ':' in target:
                # IP or hostname
                return await join.join_by_endpoint(target)
            else:
                # Try as compact code
                return await join.join_by_code(target)
        finally:
            await join.close()
    
    success, message, token = run_async(do_join())
    
    if success:
        console.print(f"[bold green]✓ {message}[/bold green]\n")
        
        # Save mesh info from token
        mesh_data = {
            "mesh_id": token.mesh_id,
            "name": token.mesh_name,
            "master_public_key": token.mesh_public_key,
            "threshold": 1,
            "total_shares": 1,
            "founding_members": [{
                "node_id": token.issuer_node_id,
                "public_key": token.issuer_public_key,
                "share_index": 1,
                "capabilities": [],
                "hardware_hash": "",
                "joined_at": token.issued_at
            }]
        }
        
        mesh = MeshIdentity.from_dict(mesh_data)
        mesh.save(config.mesh_path)
        
        # Save token
        with open(config.token_path, 'w') as f:
            json.dump(token.to_dict(), f, indent=2)
        
        config.mesh.mesh_id = token.mesh_id
        config.mesh.mesh_name = token.mesh_name
        config.mesh.role = "member"
        config.save()
        
        table = Table(show_header=False, box=None)
        table.add_column("Key", style="dim")
        table.add_column("Value")
        
        table.add_row("Mesh", f"[green]{token.mesh_name}[/green]")
        table.add_row("Mesh ID", token.mesh_id)
        table.add_row("Role", "Member")
        table.add_row("Token expires", f"{token.time_remaining // 3600}h")
        
        console.print(table)
    else:
        console.print(f"[red]✗ {message}[/red]")
        sys.exit(1)


@mesh.command('leave')
@click.option('--yes', '-y', is_flag=True, help='Skip confirmation')
def mesh_leave(yes: bool):
    """Leave the current mesh."""
    
    config = get_config()
    
    if not config.mesh_path.exists():
        console.print("[yellow]Not a member of any mesh.[/yellow]")
        return
    
    mesh = MeshIdentity.load(config.mesh_path)
    
    if not yes:
        if not click.confirm(f"Leave mesh '{mesh.name}'?"):
            return
    
    # Remove mesh files
    config.mesh_path.unlink()
    if config.mesh_path.with_suffix('.secrets').exists():
        config.mesh_path.with_suffix('.secrets').unlink()
    if config.token_path.exists():
        config.token_path.unlink()
    
    config.mesh = type(config.mesh)()
    config.save()
    
    console.print(f"[green]✓ Left mesh: {mesh.name}[/green]")


@mesh.command('invite')
@click.option('--endpoint', '-e', help='Override public endpoint')
@click.option('--hours', '-h', default=24, type=int, help='Validity in hours')
@click.option('--compact', '-c', is_flag=True, help='Output compact code only')
def mesh_invite(endpoint: str, hours: int, compact: bool):
    """Generate an invite code for others to join the mesh."""
    
    config = get_config()
    
    if not config.mesh_path.exists():
        console.print("[red]Not a member of any mesh. Create one first.[/red]")
        sys.exit(1)
    
    mesh = MeshIdentity.load(config.mesh_path)
    
    if not mesh.can_issue_certificates():
        console.print("[yellow]Only founders can generate invite codes.[/yellow]")
        sys.exit(1)
    
    from .mesh.join import generate_join_code
    from .mesh.network import gather_network_info
    
    # Discover endpoint
    async def get_endpoint():
        if endpoint:
            return endpoint
        
        info = await gather_network_info(config.server.port)
        
        if info.public_endpoint and info.public_endpoint.is_public:
            return str(info.public_endpoint)
        else:
            # Fallback to local
            return f"{info.local_ip}:{config.server.port}"
    
    detected = run_async(get_endpoint())
    
    join_code = generate_join_code(
        mesh=mesh,
        endpoint=detected,
        validity_hours=hours,
    )
    
    if compact:
        console.print(join_code.to_compact())
        return
    
    console.print(f"\n[bold blue]Invite Code for {mesh.name}[/bold blue]\n")
    
    table = Table(show_header=False, box=None)
    table.add_column("Key", style="dim")
    table.add_column("Value")
    
    table.add_row("Mesh", mesh.name)
    table.add_row("Endpoint", f"[cyan]{detected}[/cyan]")
    table.add_row("Valid for", f"{hours} hours")
    table.add_row("Short Code", f"[bold yellow]{join_code.code}[/bold yellow]")
    
    console.print(table)
    
    console.print("\n[bold]Share this with others:[/bold]")
    console.print(Panel(
        f"[cyan]{join_code.to_compact()}[/cyan]",
        title="Invite Code (copy this)",
        border_style="blue"
    ))
    
    console.print("\n[dim]Others can join with:[/dim]")
    console.print(f"  atmosphere mesh join '<invite_code>'")
    console.print()


@mesh.command('status')
def mesh_status():
    """Show mesh status."""
    
    config = get_config()
    
    if not config.mesh_path.exists():
        console.print("[yellow]Not a member of any mesh.[/yellow]")
        console.print("[dim]Use 'atmosphere mesh create' or 'atmosphere mesh join'[/dim]")
        return
    
    mesh = MeshIdentity.load(config.mesh_path)
    
    console.print(f"\n[bold]Mesh: {mesh.name}[/bold]\n")
    
    table = Table(show_header=False, box=None)
    table.add_column("Key", style="dim")
    table.add_column("Value")
    
    table.add_row("Mesh ID", f"[cyan]{mesh.mesh_id}[/cyan]")
    table.add_row("Name", mesh.name)
    table.add_row("Role", "[green]Founder[/green]" if mesh.can_issue_certificates() else "Member")
    table.add_row("Threshold", f"{mesh.threshold}/{mesh.total_shares}")
    table.add_row("Founders", str(len(mesh.founding_members)))
    
    console.print(table)
    
    if mesh.founding_members:
        console.print("\n[bold]Founding Members:[/bold]")
        for f in mesh.founding_members:
            console.print(f"  • {f.node_id[:8]}... ({', '.join(f.capabilities)})")
    
    console.print()


# === Network Commands ===

@main.command('network')
def network_info():
    """Show network information and connectivity."""
    
    from .network import gather_network_info
    
    config = get_config()
    port = config.server.port
    
    console.print("\n[bold]Network Information[/bold]\n")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Discovering network...", total=None)
        
        info = run_async(gather_network_info(port))
        progress.update(task, description="Done!")
    
    table = Table(show_header=False, box=None)
    table.add_column("Key", style="dim")
    table.add_column("Value")
    
    table.add_row("Local IP", info.local_ip)
    table.add_row("Local Port", str(info.local_port))
    
    if info.public_endpoint:
        if info.public_endpoint.is_public:
            table.add_row("Public IP", f"[green]{info.public_endpoint.ip}[/green]")
            table.add_row("Public Port", str(info.public_endpoint.port))
        else:
            table.add_row("Public IP", f"[yellow]{info.public_endpoint.ip}[/yellow] (private range)")
    else:
        table.add_row("Public IP", "[red]Not detected[/red]")
    
    table.add_row("Behind NAT", "[yellow]Yes[/yellow]" if info.is_behind_nat else "[green]No[/green]")
    
    if info.is_publicly_reachable:
        table.add_row("Internet Reachable", "[green]Yes[/green]")
    else:
        table.add_row("Internet Reachable", "[yellow]Likely No[/yellow]")
    
    console.print(table)
    
    # Recommendations
    console.print("\n[bold]Connectivity Notes:[/bold]")
    
    if info.is_publicly_reachable:
        console.print("  [green]✓[/green] Your node appears to be publicly reachable.")
        console.print(f"    Share endpoint: [cyan]{info.best_endpoint}[/cyan]")
    else:
        console.print("  [yellow]![/yellow] Your node may not be reachable from the internet.")
        console.print("\n  [bold]Options for internet access:[/bold]")
        console.print("    1. [cyan]Port forward[/cyan] - Forward port 11451 on your router")
        console.print("    2. [cyan]Public server[/cyan] - Run on a VPS with public IP")
        console.print("    3. [cyan]Manual endpoint[/cyan] - Use --endpoint when creating mesh")
        console.print("    4. [cyan]Relay server[/cyan] - (coming soon)")
    
    console.print()


# === Agent Commands ===

@main.group()
def agent():
    """Agent management commands."""
    pass


@agent.command('list')
@click.option('--all', '-a', 'show_all', is_flag=True, help='Show all agents including remote')
def agent_list(show_all: bool):
    """List agents."""
    
    config = get_config()
    
    if not config.identity_path.exists():
        console.print("[red]Node not initialized. Run 'atmosphere init' first.[/red]")
        sys.exit(1)
    
    from .agents.registry import AgentRegistry
    from .agents.loader import load_agents_into_registry, BUILTIN_AGENTS
    
    # Create registry
    identity = NodeIdentity.load(config.identity_path)
    registry_path = config.data_dir / "agent_registry.json"
    
    if registry_path.exists():
        registry = AgentRegistry.load(registry_path, identity.node_id)
    else:
        registry = AgentRegistry(node_id=identity.node_id)
    
    # Register built-in agents
    for name, factory in BUILTIN_AGENTS.items():
        registry.register_factory(name, factory)
    
    # Load specs from agents directory
    agents_dir = Path(__file__).parent.parent.parent / "agents"
    if agents_dir.exists():
        load_agents_into_registry(agents_dir, registry)
    
    console.print("\n[bold]Agents[/bold]\n")
    
    # Local agents
    local = registry.list_local()
    if local:
        table = Table(title="Running Agents")
        table.add_column("ID", style="cyan")
        table.add_column("Type")
        table.add_column("State", style="green")
        table.add_column("Uptime")
        
        for agent in local:
            stats = agent.stats()
            uptime = f"{int(stats['uptime_sec'])}s" if stats['uptime_sec'] > 0 else "-"
            table.add_row(
                agent.id[:16],
                agent.agent_type,
                stats['state'],
                uptime
            )
        
        console.print(table)
    else:
        console.print("[dim]No running agents[/dim]")
    
    # Sleeping agents
    sleeping = registry.list_sleeping()
    if sleeping:
        console.print(f"\n[dim]Sleeping: {', '.join(sleeping[:5])}{'...' if len(sleeping) > 5 else ''}[/dim]")
    
    # Available types
    types = registry.list_types()
    if types:
        console.print(f"\n[bold]Available Types:[/bold] {', '.join(sorted(types))}")
    
    if show_all:
        remote = [info for info in registry.list_all() if info.node_id != identity.node_id]
        if remote:
            console.print(f"\n[bold]Remote Agents:[/bold]")
            for info in remote[:10]:
                console.print(f"  • {info.id[:12]}... ({info.agent_type}) on {info.node_id[:8]}...")
    
    console.print()


@agent.command('spawn')
@click.argument('agent_type')
@click.option('--intent', '-i', help='Initial intent to send')
@click.option('--args', '-a', help='JSON args for intent')
def agent_spawn(agent_type: str, intent: str, args: str):
    """Spawn a new agent."""
    
    config = get_config()
    
    if not config.identity_path.exists():
        console.print("[red]Node not initialized.[/red]")
        sys.exit(1)
    
    from .agents.registry import AgentRegistry
    from .agents.loader import load_agents_into_registry, BUILTIN_AGENTS
    
    identity = NodeIdentity.load(config.identity_path)
    registry_path = config.data_dir / "agent_registry.json"
    
    if registry_path.exists():
        registry = AgentRegistry.load(registry_path, identity.node_id)
    else:
        registry = AgentRegistry(node_id=identity.node_id)
    
    # Register built-in agents
    for name, factory in BUILTIN_AGENTS.items():
        registry.register_factory(name, factory)
    
    # Load specs
    agents_dir = Path(__file__).parent.parent.parent / "agents"
    if agents_dir.exists():
        load_agents_into_registry(agents_dir, registry)
    
    # Parse args
    intent_args = {}
    if args:
        intent_args = json.loads(args)
    
    async def do_spawn():
        agent_id = await registry.spawn(
            agent_type=agent_type,
            initial_intent=intent,
            args=intent_args if intent else None,
        )
        return agent_id, registry.get(agent_id)
    
    try:
        agent_id, agent = run_async(do_spawn())
        
        console.print(f"\n[bold green]✓ Agent spawned[/bold green]")
        console.print(f"  ID: [cyan]{agent_id}[/cyan]")
        console.print(f"  Type: {agent.agent_type}")
        console.print(f"  State: {agent.state.value}")
        
        if intent:
            console.print(f"  Initial intent: {intent}")
        
        # Save registry
        registry.save(registry_path)
        
        console.print("\n[dim]Note: Agent will stop when CLI exits. Use 'atmosphere serve' for persistent agents.[/dim]\n")
        
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        console.print(f"\nAvailable types: {', '.join(registry.list_types())}")
        sys.exit(1)


@agent.command('types')
def agent_types():
    """List available agent types."""
    
    config = get_config()
    
    from .agents.registry import AgentRegistry
    from .agents.loader import load_agents_into_registry, BUILTIN_AGENTS
    
    identity = NodeIdentity.load(config.identity_path)
    registry = AgentRegistry(node_id=identity.node_id)
    
    # Register built-in agents
    for name, factory in BUILTIN_AGENTS.items():
        registry.register_factory(name, factory)
    
    # Load specs
    agents_dir = Path(__file__).parent.parent.parent / "agents"
    if agents_dir.exists():
        load_agents_into_registry(agents_dir, registry)
    
    console.print("\n[bold]Agent Types[/bold]\n")
    
    # Built-in
    console.print("[bold]Built-in:[/bold]")
    for name in sorted(BUILTIN_AGENTS.keys()):
        factory = BUILTIN_AGENTS[name]
        doc = factory.__doc__ or "No description"
        console.print(f"  [cyan]{name}[/cyan] - {doc.strip().split(chr(10))[0]}")
    
    # From specs
    specs_loaded = False
    for type_id in registry.list_types():
        if type_id not in BUILTIN_AGENTS:
            if not specs_loaded:
                console.print("\n[bold]From Specs:[/bold]")
                specs_loaded = True
            
            spec = registry.get_spec(type_id)
            if spec:
                desc = spec.description.strip().split('\n')[0][:60]
                console.print(f"  [cyan]{type_id}[/cyan] - {desc}")
    
    console.print()


@agent.command('invoke')
@click.argument('agent_id')
@click.argument('intent')
@click.option('--args', '-a', help='JSON args for intent')
def agent_invoke(agent_id: str, intent: str, args: str):
    """Send an intent to an agent."""
    
    config = get_config()
    
    from .agents.registry import AgentRegistry
    from .agents.base import AgentMessage
    
    identity = NodeIdentity.load(config.identity_path)
    registry_path = config.data_dir / "agent_registry.json"
    
    if not registry_path.exists():
        console.print("[red]No agents registered. Spawn one first.[/red]")
        sys.exit(1)
    
    registry = AgentRegistry.load(registry_path, identity.node_id)
    
    agent = registry.get(agent_id)
    if not agent:
        # Try partial match
        for a in registry.list_local():
            if a.id.startswith(agent_id):
                agent = a
                break
    
    if not agent:
        console.print(f"[red]Agent not found: {agent_id}[/red]")
        sys.exit(1)
    
    intent_args = json.loads(args) if args else {}
    
    async def do_invoke():
        if not agent.is_running:
            await agent.start()
        
        result = await agent.handle_intent(intent, intent_args)
        return result
    
    try:
        result = run_async(do_invoke())
        console.print(f"\n[bold green]✓ Intent handled[/bold green]\n")
        console.print(json.dumps(result, indent=2, default=str))
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


# === Tool Commands ===

@main.group()
def tool():
    """Tool management commands."""
    pass


@tool.command('list')
@click.option('--category', '-c', help='Filter by category')
def tool_list(category: str):
    """List available tools."""
    
    from .tools.registry import ToolRegistry
    from .tools.core import register_core_tools
    
    config = get_config()
    identity = NodeIdentity.load(config.identity_path)
    
    registry = ToolRegistry(node_id=identity.node_id)
    register_core_tools(registry)
    
    console.print("\n[bold]Tools[/bold]\n")
    
    tools = registry.list_all()
    
    if category:
        tools = [t for t in tools if t.category == category]
    
    if not tools:
        console.print("[dim]No tools found[/dim]")
        return
    
    table = Table()
    table.add_column("Name", style="cyan")
    table.add_column("Category")
    table.add_column("Description")
    
    for t in sorted(tools, key=lambda x: x.full_name):
        desc = t.description[:50] + "..." if len(t.description) > 50 else t.description
        table.add_row(t.full_name, t.category, desc)
    
    console.print(table)
    console.print()


@tool.command('info')
@click.argument('tool_name')
def tool_info(tool_name: str):
    """Show detailed information about a tool."""
    
    from .tools.registry import ToolRegistry
    from .tools.core import register_core_tools
    
    config = get_config()
    identity = NodeIdentity.load(config.identity_path)
    
    registry = ToolRegistry(node_id=identity.node_id)
    register_core_tools(registry)
    
    t = registry.get(tool_name)
    if not t:
        console.print(f"[red]Tool not found: {tool_name}[/red]")
        sys.exit(1)
    
    console.print(f"\n[bold]{t.full_name}[/bold]\n")
    
    table = Table(show_header=False, box=None)
    table.add_column("Key", style="dim")
    table.add_column("Value")
    
    table.add_row("Name", t.name)
    table.add_row("Namespace", t.spec.namespace)
    table.add_row("Version", t.spec.version)
    table.add_row("Category", t.spec.category)
    table.add_row("Description", t.spec.description)
    
    console.print(table)
    
    if t.spec.parameters:
        console.print("\n[bold]Parameters:[/bold]")
        for p in t.spec.parameters:
            req = "[required]" if p.required else "[optional]"
            console.print(f"  [cyan]{p.name}[/cyan] ({p.type}) {req}")
            if p.description:
                console.print(f"    {p.description}")
    
    if t.spec.permissions_required:
        console.print(f"\n[bold]Permissions:[/bold] {', '.join(t.spec.permissions_required)}")
    
    console.print()


@tool.command('run')
@click.argument('tool_name')
@click.option('--params', '-p', help='JSON parameters')
@click.option('--param', '-P', multiple=True, help='Key=value parameter (repeatable)')
def tool_run(tool_name: str, params: str, param: tuple):
    """Execute a tool."""
    
    from .tools.registry import ToolRegistry
    from .tools.executor import ToolExecutor
    from .tools.base import ToolContext
    from .tools.core import register_core_tools
    
    config = get_config()
    identity = NodeIdentity.load(config.identity_path)
    
    registry = ToolRegistry(node_id=identity.node_id)
    register_core_tools(registry)
    
    executor = ToolExecutor(registry)
    
    # Parse parameters
    tool_params = {}
    
    if params:
        tool_params = json.loads(params)
    
    # Add key=value params
    for p in param:
        if '=' in p:
            key, value = p.split('=', 1)
            # Try to parse as JSON, fall back to string
            try:
                tool_params[key] = json.loads(value)
            except json.JSONDecodeError:
                tool_params[key] = value
    
    # Create context with full permissions for CLI
    context = ToolContext(
        node_id=identity.node_id,
        permissions=["*"],  # Full permissions for CLI
    )
    
    async def do_run():
        return await executor.execute(tool_name, tool_params, context)
    
    result = run_async(do_run())
    
    if result.success:
        console.print(f"\n[bold green]✓ Tool executed[/bold green] ({result.duration_ms:.1f}ms)\n")
        console.print(json.dumps(result.result, indent=2, default=str))
    else:
        console.print(f"\n[bold red]✗ Tool failed[/bold red]")
        console.print(f"  Error: {result.error}")
        console.print(f"  Code: {result.error_code}")
        sys.exit(1)


# Add model commands
main.add_command(model_commands)


if __name__ == '__main__':
    main()
