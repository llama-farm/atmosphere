"""
Cost CLI - Command line interface for cost model.

Displays current node cost factors and helps debug routing decisions.
"""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from .collector import get_cost_collector
from .model import (
    WorkRequest,
    compute_node_cost,
    power_cost_multiplier,
    compute_load_multiplier,
    network_cost_multiplier,
)

console = Console()


@click.command('cost')
@click.option('--json', 'as_json', is_flag=True, help='Output as JSON')
def cost(as_json: bool):
    """Show this node's cost factors for routing decisions."""
    
    collector = get_cost_collector()
    factors = collector.collect()
    
    if as_json:
        import json
        click.echo(json.dumps(factors.to_dict(), indent=2))
        return
    
    # Header
    console.print()
    console.print(Panel(
        f"[bold cyan]{factors.node_id}[/bold cyan]",
        title="🔄 Node Cost Factors",
        subtitle="Lower cost = better routing target"
    ))
    console.print()
    
    # Power State Table
    power_table = Table(title="⚡ Power State", show_header=True, header_style="bold")
    power_table.add_column("Factor")
    power_table.add_column("Value")
    power_table.add_column("Impact")
    
    battery_icon = "🔋" if factors.on_battery else "🔌"
    battery_status = f"{battery_icon} {'On Battery' if factors.on_battery else 'Plugged In'}"
    power_mult = power_cost_multiplier(factors.on_battery, factors.battery_percent)
    
    if factors.on_battery:
        if factors.battery_percent < 20:
            color = "red"
        elif factors.battery_percent < 50:
            color = "yellow"
        else:
            color = "green"
    else:
        color = "green"
    
    power_table.add_row(
        "Power Source",
        battery_status,
        f"[{color}]{power_mult:.1f}x cost[/{color}]"
    )
    power_table.add_row(
        "Battery Level",
        f"{factors.battery_percent:.0f}%",
        ""
    )
    console.print(power_table)
    console.print()
    
    # Compute Load Table
    compute_table = Table(title="💻 Compute Load", show_header=True, header_style="bold")
    compute_table.add_column("Factor")
    compute_table.add_column("Value")
    compute_table.add_column("Impact")
    
    # CPU
    cpu_pct = factors.cpu_load * 100
    if cpu_pct > 75:
        cpu_color = "red"
    elif cpu_pct > 50:
        cpu_color = "yellow"
    else:
        cpu_color = "green"
    
    compute_table.add_row(
        "CPU Load",
        f"[{cpu_color}]{cpu_pct:.0f}%[/{cpu_color}]",
        _get_cpu_impact(factors.cpu_load)
    )
    
    # GPU
    gpu_note = " (estimated)" if factors.gpu_estimated else ""
    if factors.gpu_load > 50:
        gpu_color = "red"
    elif factors.gpu_load > 25:
        gpu_color = "yellow"
    else:
        gpu_color = "green"
    
    compute_table.add_row(
        "GPU Load",
        f"[{gpu_color}]{factors.gpu_load:.0f}%{gpu_note}[/{gpu_color}]",
        _get_gpu_impact(factors.gpu_load)
    )
    
    # Memory
    if factors.memory_percent > 90:
        mem_color = "red"
    elif factors.memory_percent > 80:
        mem_color = "yellow"
    else:
        mem_color = "green"
    
    compute_table.add_row(
        "Memory",
        f"[{mem_color}]{factors.memory_percent:.0f}%[/{mem_color}] ({factors.memory_available_gb:.1f} GB free)",
        _get_memory_impact(factors.memory_percent)
    )
    
    console.print(compute_table)
    console.print()
    
    # Network Table
    network_table = Table(title="🌐 Network", show_header=True, header_style="bold")
    network_table.add_column("Factor")
    network_table.add_column("Value")
    network_table.add_column("Impact")
    
    metered_text = "[yellow]📱 Metered[/yellow]" if factors.is_metered else "[green]🏠 Unmetered[/green]"
    network_mult = network_cost_multiplier(factors.bandwidth_mbps, factors.is_metered, "general")
    
    network_table.add_row(
        "Connection Type",
        metered_text,
        f"{network_mult:.1f}x cost" if factors.is_metered else "1.0x cost"
    )
    
    bw_text = f"{factors.bandwidth_mbps:.0f} Mbps" if factors.bandwidth_mbps else "Unknown"
    network_table.add_row(
        "Bandwidth",
        bw_text,
        ""
    )
    
    console.print(network_table)
    console.print()
    
    # Overall Cost Summary
    summary_table = Table(title="📊 Overall Cost Score", show_header=True, header_style="bold")
    summary_table.add_column("Work Type")
    summary_table.add_column("Cost")
    summary_table.add_column("Rating")
    
    for work_type in ["general", "inference", "embedding", "rag"]:
        work = WorkRequest(work_type=work_type)
        cost_score = compute_node_cost(factors, work)
        
        if cost_score <= 1.5:
            rating = "[green]🟢 Excellent[/green]"
        elif cost_score <= 3.0:
            rating = "[yellow]🟡 Moderate[/yellow]"
        else:
            rating = "[red]🔴 High[/red]"
        
        summary_table.add_row(
            work_type.capitalize(),
            f"{cost_score:.2f}",
            rating
        )
    
    console.print(summary_table)
    console.print()
    
    # Tips
    if factors.on_battery and factors.battery_percent < 50:
        console.print("[yellow]💡 Tip: Plug in to reduce routing cost and preserve battery.[/yellow]")
    if factors.is_metered:
        console.print("[yellow]💡 Tip: Switch to Wi-Fi to reduce network cost.[/yellow]")
    if factors.cpu_load > 0.75:
        console.print("[yellow]💡 Tip: High CPU load increases cost. Close unused apps.[/yellow]")
    
    console.print()


def _get_cpu_impact(cpu_load: float) -> str:
    """Get CPU impact description."""
    if cpu_load > 0.75:
        return "[red]2.0x cost[/red]"
    elif cpu_load > 0.50:
        return "[yellow]1.6x cost[/yellow]"
    elif cpu_load > 0.25:
        return "[dim]1.3x cost[/dim]"
    else:
        return "[green]1.0x cost[/green]"


def _get_gpu_impact(gpu_load: float) -> str:
    """Get GPU impact description (for inference work)."""
    if gpu_load > 50:
        return "[red]2.0x cost (inference)[/red]"
    elif gpu_load > 25:
        return "[yellow]1.5x cost (inference)[/yellow]"
    else:
        return "[green]1.0x cost[/green]"


def _get_memory_impact(memory_percent: float) -> str:
    """Get memory impact description."""
    if memory_percent > 90:
        return "[red]2.5x cost[/red]"
    elif memory_percent > 80:
        return "[yellow]1.5x cost[/yellow]"
    else:
        return "[green]1.0x cost[/green]"
