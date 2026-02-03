"""
Matter Integration CLI Commands.

Provides CLI commands for managing Matter devices and integration.
"""

import asyncio
import click
from typing import Optional
from pathlib import Path

from .models import MatterDeviceType, DeviceStatus
from .discovery import MatterDiscovery, DiscoveryConfig
from .mapping import DeviceMapper, MATTER_TO_ATMOSPHERE


def run_async(coro):
    """Run an async function in the event loop."""
    return asyncio.get_event_loop().run_until_complete(coro)


@click.group()
def matter():
    """Manage Matter/IoT device integration."""
    pass


@matter.command()
@click.option('--timeout', '-t', default=30, help='Discovery timeout in seconds')
def discover(timeout: int):
    """Discover commissionable Matter devices on the local network."""
    
    async def _discover():
        click.echo(f"🔍 Scanning for Matter devices (timeout={timeout}s)...")
        click.echo("   Looking for _matterc._udp.local and _matterd._udp.local...")
        click.echo()
        
        discovery = MatterDiscovery()
        await discovery.start()
        
        try:
            devices = await discovery.discover_commissionable(timeout=timeout)
            
            if not devices:
                click.echo("   No commissionable devices found.")
                click.echo()
                click.echo("💡 Tips:")
                click.echo("   • Put your device in pairing mode")
                click.echo("   • Check that your device supports Matter")
                click.echo("   • Ensure you're on the same network")
                return
            
            click.echo(f"Found {len(devices)} commissionable device(s):")
            click.echo()
            
            for device in devices:
                click.echo(f"   📱 {device.instance_name}")
                click.echo(f"      Discriminator: {device.discriminator}")
                click.echo(f"      Vendor ID: {device.vendor_id}")
                click.echo(f"      Product ID: {device.product_id}")
                click.echo(f"      Address: {device.host}:{device.port}")
                if device.pairing_hint:
                    click.echo(f"      Pairing Hint: {device.pairing_hint}")
                click.echo()
        
        finally:
            await discovery.stop()
    
    run_async(_discover())


@matter.command('list')
@click.option('--all', '-a', 'show_all', is_flag=True, help='Show all devices including offline')
def list_devices(show_all: bool):
    """List known Matter devices."""
    
    discovery = MatterDiscovery()
    
    if show_all:
        devices = discovery.get_all_devices()
    else:
        devices = discovery.get_online_devices()
    
    if not devices:
        click.echo("No Matter devices found.")
        click.echo()
        click.echo("💡 To add devices:")
        click.echo("   atmosphere matter commission <setup-code>")
        click.echo("   atmosphere matter add-mock --type dimmable_light --name 'Test Light'")
        return
    
    click.echo(f"{'ID':<6} {'Status':<10} {'Type':<20} {'Label':<20} {'Location':<15}")
    click.echo("-" * 75)
    
    for device in devices:
        device_type = device.primary_device_type
        type_name = device_type.name if device_type else "Unknown"
        
        status_icon = {
            DeviceStatus.ONLINE: "🟢",
            DeviceStatus.OFFLINE: "🔴",
            DeviceStatus.UNREACHABLE: "🟡",
            DeviceStatus.UNKNOWN: "⚪",
        }.get(device.status, "⚪")
        
        click.echo(
            f"{device.node_id:<6} {status_icon} {device.status.value:<7} "
            f"{type_name:<20} {device.display_name:<20} {device.location or '-':<15}"
        )


@matter.command()
@click.argument('device_id')
def status(device_id: str):
    """Show detailed status of a Matter device."""
    
    discovery = MatterDiscovery()
    
    # Try to parse as node ID
    try:
        node_id = int(device_id)
        device = discovery.get_device(node_id)
    except ValueError:
        device = discovery.get_device_by_label(device_id)
    
    if not device:
        click.echo(f"❌ Device not found: {device_id}")
        return
    
    status_icon = {
        DeviceStatus.ONLINE: "🟢",
        DeviceStatus.OFFLINE: "🔴",
        DeviceStatus.UNREACHABLE: "🟡",
        DeviceStatus.UNKNOWN: "⚪",
    }.get(device.status, "⚪")
    
    click.echo()
    click.echo(f"📱 {device.display_name}")
    click.echo(f"   {'─' * 40}")
    click.echo(f"   Node ID:       {device.node_id}")
    click.echo(f"   Status:        {status_icon} {device.status.value}")
    click.echo(f"   Vendor:        {device.vendor_name} (0x{device.vendor_id:04X})")
    click.echo(f"   Product:       {device.product_name} (0x{device.product_id:04X})")
    click.echo(f"   Serial:        {device.serial_number or 'N/A'}")
    click.echo(f"   Firmware:      {device.firmware_version}")
    click.echo(f"   Location:      {device.location or 'Not set'}")
    click.echo()
    
    click.echo("   Endpoints:")
    for ep in device.endpoints:
        if ep.endpoint_id == 0:
            continue  # Skip root
        
        click.echo(f"   └─ Endpoint {ep.endpoint_id}: {ep.device_type.name}")
        
        for cluster in ep.clusters:
            click.echo(f"      └─ {cluster.name} (0x{cluster.cluster_id:04X})")
            
            # Show key attributes
            for attr_name, attr_value in list(cluster.attributes.items())[:5]:
                click.echo(f"         • {attr_name}: {attr_value}")
    
    click.echo()
    
    # Show Atmosphere capability mapping
    mapper = DeviceMapper()
    capabilities = mapper.device_to_capabilities(device)
    
    if capabilities:
        click.echo("   Atmosphere Capabilities:")
        for cap in capabilities:
            click.echo(f"   └─ {cap.id}")
            click.echo(f"      Type: {cap.type.value}")
            click.echo(f"      Tools: {', '.join(t.name for t in cap.tools)}")
            click.echo(f"      Triggers: {', '.join(t.event for t in cap.triggers)}")


@matter.command()
@click.argument('setup_code')
@click.option('--name', '-n', help='Friendly name for the device')
@click.option('--location', '-l', help='Room or area location')
def commission(setup_code: str, name: Optional[str], location: Optional[str]):
    """Commission a new Matter device."""
    
    async def _commission():
        click.echo(f"🔗 Commissioning device...")
        click.echo(f"   Setup code: {setup_code[:10]}...")
        click.echo()
        
        discovery = MatterDiscovery()
        
        try:
            device = await discovery.commission_device(
                setup_code=setup_code,
                label=name,
                location=location,
            )
            
            click.echo(f"✅ Successfully commissioned: {device.display_name}")
            click.echo(f"   Node ID: {device.node_id}")
            click.echo(f"   Type: {device.primary_device_type.name if device.primary_device_type else 'Unknown'}")
            click.echo()
            click.echo("   The device is now part of your Atmosphere mesh.")
            
        except Exception as e:
            click.echo(f"❌ Commissioning failed: {e}")
    
    run_async(_commission())


@matter.command()
@click.argument('device_id')
@click.option('--force', '-f', is_flag=True, help='Skip confirmation')
def remove(device_id: str, force: bool):
    """Remove a Matter device from the fabric."""
    
    discovery = MatterDiscovery()
    
    # Find device
    try:
        node_id = int(device_id)
        device = discovery.get_device(node_id)
    except ValueError:
        device = discovery.get_device_by_label(device_id)
    
    if not device:
        click.echo(f"❌ Device not found: {device_id}")
        return
    
    if not force:
        click.confirm(
            f"Remove {device.display_name} (node {device.node_id})? This cannot be undone.",
            abort=True,
        )
    
    async def _remove():
        success = await discovery.decommission_device(device.node_id)
        
        if success:
            click.echo(f"✅ Removed: {device.display_name}")
        else:
            click.echo(f"❌ Failed to remove device")
    
    run_async(_remove())


@matter.command()
@click.argument('device_id')
@click.option('--name', '-n', help='New friendly name')
@click.option('--location', '-l', help='Room or area location')
def rename(device_id: str, name: Optional[str], location: Optional[str]):
    """Rename a Matter device or update its location."""
    
    discovery = MatterDiscovery()
    
    # Find device
    try:
        node_id = int(device_id)
    except ValueError:
        device = discovery.get_device_by_label(device_id)
        if device:
            node_id = device.node_id
        else:
            click.echo(f"❌ Device not found: {device_id}")
            return
    
    if not name and not location:
        click.echo("❌ Specify --name or --location (or both)")
        return
    
    async def _rename():
        device = await discovery.update_device_label(node_id, name or "", location)
        
        if device:
            click.echo(f"✅ Updated: {device.display_name}")
            if name:
                click.echo(f"   Name: {name}")
            if location:
                click.echo(f"   Location: {location}")
        else:
            click.echo(f"❌ Device not found: {device_id}")
    
    run_async(_rename())


@matter.command('add-mock')
@click.option('--type', '-t', 'device_type', required=True, 
              type=click.Choice([dt.name.lower() for dt in MatterDeviceType]),
              help='Device type to mock')
@click.option('--name', '-n', required=True, help='Device name')
@click.option('--location', '-l', help='Room or area')
def add_mock(device_type: str, name: str, location: Optional[str]):
    """Add a mock device for testing (no real hardware)."""
    
    # Convert string to enum
    device_type_enum = MatterDeviceType[device_type.upper()]
    
    discovery = MatterDiscovery()
    device = discovery.add_mock_device(
        device_type=device_type_enum,
        label=name,
        location=location,
    )
    
    click.echo(f"✅ Added mock device: {device.display_name}")
    click.echo(f"   Node ID: {device.node_id}")
    click.echo(f"   Type: {device_type_enum.name}")
    if location:
        click.echo(f"   Location: {location}")
    click.echo()
    click.echo("   This device can be used for testing without real hardware.")


@matter.command('capabilities')
def show_capabilities():
    """Show supported Matter device types and their Atmosphere mappings."""
    
    click.echo()
    click.echo("Supported Matter Device Types → Atmosphere Capabilities")
    click.echo("=" * 70)
    click.echo()
    
    categories = {
        "Lighting": [
            MatterDeviceType.ON_OFF_LIGHT,
            MatterDeviceType.DIMMABLE_LIGHT,
            MatterDeviceType.COLOR_TEMP_LIGHT,
            MatterDeviceType.EXTENDED_COLOR_LIGHT,
        ],
        "Plugs & Outlets": [
            MatterDeviceType.ON_OFF_PLUG,
            MatterDeviceType.DIMMABLE_PLUG,
        ],
        "Security": [
            MatterDeviceType.DOOR_LOCK,
            MatterDeviceType.CONTACT_SENSOR,
            MatterDeviceType.OCCUPANCY_SENSOR,
        ],
        "Climate": [
            MatterDeviceType.THERMOSTAT,
            MatterDeviceType.TEMPERATURE_SENSOR,
            MatterDeviceType.HUMIDITY_SENSOR,
            MatterDeviceType.FAN,
            MatterDeviceType.AIR_PURIFIER,
        ],
        "Window Coverings": [
            MatterDeviceType.WINDOW_COVERING,
        ],
        "Appliances": [
            MatterDeviceType.ROBOT_VACUUM,
        ],
    }
    
    for category, types in categories.items():
        click.echo(f"📁 {category}")
        click.echo()
        
        for dt in types:
            mapping = MATTER_TO_ATMOSPHERE.get(dt)
            if not mapping:
                continue
            
            click.echo(f"   {dt.name}")
            click.echo(f"   ├─ Capability: {mapping.capability_type.value}")
            click.echo(f"   ├─ Tools: {', '.join(mapping.tools[:4])}")
            if len(mapping.tools) > 4:
                click.echo(f"   │          +{len(mapping.tools) - 4} more")
            click.echo(f"   └─ Triggers: {', '.join(mapping.triggers[:3])}")
            if len(mapping.triggers) > 3:
                click.echo(f"              +{len(mapping.triggers) - 3} more")
            click.echo()


@matter.command()
@click.argument('device_id')
@click.argument('command')
@click.option('--arg', '-a', multiple=True, help='Command arguments (key=value)')
def execute(device_id: str, command: str, arg: tuple):
    """Execute a command on a Matter device (for testing)."""
    
    # Parse arguments
    args = {}
    for a in arg:
        if '=' in a:
            key, value = a.split('=', 1)
            # Try to parse as number or bool
            try:
                value = int(value)
            except ValueError:
                try:
                    value = float(value)
                except ValueError:
                    if value.lower() in ('true', 'false'):
                        value = value.lower() == 'true'
            args[key] = value
    
    discovery = MatterDiscovery()
    
    # Find device
    try:
        node_id = int(device_id)
        device = discovery.get_device(node_id)
    except ValueError:
        device = discovery.get_device_by_label(device_id)
    
    if not device:
        click.echo(f"❌ Device not found: {device_id}")
        return
    
    click.echo(f"🔧 Executing {command} on {device.display_name}...")
    if args:
        click.echo(f"   Arguments: {args}")
    
    # In a real implementation, this would call the bridge
    click.echo()
    click.echo("   [STUB] Command execution requires matter.js bridge")
    click.echo("   The bridge is not yet implemented for MVP.")


@matter.group()
def bridge():
    """Manage the matter.js bridge process."""
    pass


@bridge.command()
def status():
    """Show matter.js bridge status."""
    
    click.echo()
    click.echo("Matter Bridge Status")
    click.echo("─" * 30)
    click.echo()
    click.echo("   State:    🟡 Not Implemented")
    click.echo("   Port:     5580 (default)")
    click.echo()
    click.echo("   The matter.js bridge provides real Matter protocol support.")
    click.echo("   For MVP, Matter commands are simulated.")
    click.echo()
    click.echo("   See MATTER_INTEGRATION.md for implementation details.")


@bridge.command()
def start():
    """Start the matter.js bridge."""
    click.echo("🚀 Starting matter.js bridge...")
    click.echo()
    click.echo("   [STUB] Bridge startup requires matter.js Node.js package")
    click.echo("   Run: cd atmosphere/integrations/matter/node_bridge && npm install")


@bridge.command()
def stop():
    """Stop the matter.js bridge."""
    click.echo("🛑 Stopping matter.js bridge...")
    click.echo()
    click.echo("   [STUB] No bridge process running")


# Register with main CLI
def register_cli(cli):
    """Register Matter commands with the main CLI."""
    cli.add_command(matter)
