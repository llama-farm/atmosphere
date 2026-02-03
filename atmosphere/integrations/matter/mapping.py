"""
Matter Device → Atmosphere Capability Mapping.

Maps Matter device types and clusters to Atmosphere capabilities, tools, and triggers.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple

from atmosphere.capabilities.registry import (
    Capability,
    CapabilityType,
    Tool,
    Trigger,
)
from .models import (
    MatterDevice,
    MatterDeviceType,
    MatterEndpoint,
    ClusterType,
)


@dataclass
class CapabilityMapping:
    """Mapping from Matter device type to Atmosphere capability."""
    capability_type: CapabilityType
    tools: List[str]
    triggers: List[str]
    description: str = ""


@dataclass
class ToolDefinition:
    """Definition of a tool with full schema."""
    name: str
    description: str
    parameters: Dict[str, Any]
    returns: Dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    security_sensitive: bool = False


@dataclass
class TriggerDefinition:
    """Definition of a trigger with full schema."""
    event: str
    description: str
    intent_template: str
    payload_schema: Dict[str, Any]
    priority: str = "normal"
    route_hint: Optional[str] = None


# =============================================================================
# TOOL DEFINITIONS
# =============================================================================

TOOL_DEFINITIONS: Dict[str, ToolDefinition] = {
    # --- Lighting Tools ---
    "light_on": ToolDefinition(
        name="light_on",
        description="Turn on a light",
        parameters={
            "device_id": {"type": "string", "required": True, "description": "Device identifier"},
            "brightness": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Brightness percentage (optional)"},
            "transition_ms": {"type": "integer", "minimum": 0, "description": "Transition time in milliseconds"},
        },
        returns={"type": "object", "properties": {"success": {"type": "boolean"}}},
    ),
    "light_off": ToolDefinition(
        name="light_off",
        description="Turn off a light",
        parameters={
            "device_id": {"type": "string", "required": True, "description": "Device identifier"},
            "transition_ms": {"type": "integer", "minimum": 0, "description": "Transition time in milliseconds"},
        },
        returns={"type": "object", "properties": {"success": {"type": "boolean"}}},
    ),
    "light_toggle": ToolDefinition(
        name="light_toggle",
        description="Toggle a light on/off",
        parameters={
            "device_id": {"type": "string", "required": True, "description": "Device identifier"},
        },
        returns={"type": "object", "properties": {"success": {"type": "boolean"}, "state": {"type": "boolean"}}},
    ),
    "light_set_brightness": ToolDefinition(
        name="light_set_brightness",
        description="Set light brightness level",
        parameters={
            "device_id": {"type": "string", "required": True},
            "brightness": {"type": "integer", "required": True, "minimum": 0, "maximum": 100, "description": "Brightness percentage (0-100)"},
            "transition_ms": {"type": "integer", "minimum": 0},
        },
        returns={"type": "object", "properties": {"success": {"type": "boolean"}}},
    ),
    "light_set_color_temp": ToolDefinition(
        name="light_set_color_temp",
        description="Set light color temperature",
        parameters={
            "device_id": {"type": "string", "required": True},
            "kelvin": {"type": "integer", "required": True, "minimum": 2000, "maximum": 6500, "description": "Color temperature in Kelvin"},
            "transition_ms": {"type": "integer", "minimum": 0},
        },
        returns={"type": "object", "properties": {"success": {"type": "boolean"}}},
    ),
    "light_set_color": ToolDefinition(
        name="light_set_color",
        description="Set light color using RGB, HSV, or color name",
        parameters={
            "device_id": {"type": "string", "required": True},
            "color": {
                "oneOf": [
                    {"type": "object", "properties": {"r": {"type": "integer"}, "g": {"type": "integer"}, "b": {"type": "integer"}}},
                    {"type": "object", "properties": {"h": {"type": "integer"}, "s": {"type": "integer"}, "v": {"type": "integer"}}},
                    {"type": "string", "description": "Color name like 'red', 'warm white', 'ocean blue'"},
                ],
            },
            "transition_ms": {"type": "integer", "minimum": 0},
        },
        returns={"type": "object", "properties": {"success": {"type": "boolean"}}},
    ),
    "light_get_state": ToolDefinition(
        name="light_get_state",
        description="Get current light state",
        parameters={
            "device_id": {"type": "string", "required": True},
        },
        returns={
            "type": "object",
            "properties": {
                "on": {"type": "boolean"},
                "brightness": {"type": "integer"},
                "color_temp_kelvin": {"type": "integer"},
                "color_rgb": {"type": "object"},
            },
        },
    ),
    
    # --- Outlet/Plug Tools ---
    "outlet_on": ToolDefinition(
        name="outlet_on",
        description="Turn on an outlet/plug",
        parameters={"device_id": {"type": "string", "required": True}},
        returns={"type": "object", "properties": {"success": {"type": "boolean"}}},
    ),
    "outlet_off": ToolDefinition(
        name="outlet_off",
        description="Turn off an outlet/plug",
        parameters={"device_id": {"type": "string", "required": True}},
        returns={"type": "object", "properties": {"success": {"type": "boolean"}}},
    ),
    "outlet_toggle": ToolDefinition(
        name="outlet_toggle",
        description="Toggle an outlet/plug on/off",
        parameters={"device_id": {"type": "string", "required": True}},
        returns={"type": "object", "properties": {"success": {"type": "boolean"}, "state": {"type": "boolean"}}},
    ),
    "outlet_get_state": ToolDefinition(
        name="outlet_get_state",
        description="Get current outlet state",
        parameters={"device_id": {"type": "string", "required": True}},
        returns={"type": "object", "properties": {"on": {"type": "boolean"}}},
    ),
    
    # --- Lock Tools ---
    "lock_door": ToolDefinition(
        name="lock_door",
        description="Lock a door",
        parameters={
            "device_id": {"type": "string", "required": True},
            "pin_code": {"type": "string", "description": "Optional PIN for audit trail"},
        },
        returns={"type": "object", "properties": {"success": {"type": "boolean"}, "lock_state": {"type": "string"}}},
    ),
    "unlock_door": ToolDefinition(
        name="unlock_door",
        description="Unlock a door - requires explicit confirmation for security",
        parameters={
            "device_id": {"type": "string", "required": True},
            "pin_code": {"type": "string", "description": "PIN code (may be required by device)"},
        },
        returns={"type": "object", "properties": {"success": {"type": "boolean"}, "lock_state": {"type": "string"}}},
        requires_confirmation=True,
        security_sensitive=True,
    ),
    "lock_get_state": ToolDefinition(
        name="lock_get_state",
        description="Get current lock state",
        parameters={"device_id": {"type": "string", "required": True}},
        returns={
            "type": "object",
            "properties": {
                "lock_state": {"type": "string", "enum": ["locked", "unlocked", "not_fully_locked"]},
                "door_state": {"type": "string", "enum": ["open", "closed", "jammed"]},
                "battery_percent": {"type": "integer"},
            },
        },
    ),
    
    # --- Thermostat Tools ---
    "hvac_set_temperature": ToolDefinition(
        name="hvac_set_temperature",
        description="Set thermostat target temperature",
        parameters={
            "device_id": {"type": "string", "required": True},
            "temperature": {"type": "number", "required": True, "description": "Target temperature"},
            "unit": {"type": "string", "enum": ["celsius", "fahrenheit"], "default": "fahrenheit"},
            "mode": {"type": "string", "enum": ["heat", "cool", "auto"], "description": "HVAC mode (optional)"},
        },
        returns={"type": "object", "properties": {"success": {"type": "boolean"}}},
    ),
    "hvac_get_state": ToolDefinition(
        name="hvac_get_state",
        description="Get current thermostat state",
        parameters={"device_id": {"type": "string", "required": True}},
        returns={
            "type": "object",
            "properties": {
                "current_temp": {"type": "number"},
                "target_temp": {"type": "number"},
                "mode": {"type": "string"},
                "humidity": {"type": "number"},
                "running": {"type": "boolean"},
            },
        },
    ),
    "hvac_set_mode": ToolDefinition(
        name="hvac_set_mode",
        description="Set thermostat mode",
        parameters={
            "device_id": {"type": "string", "required": True},
            "mode": {"type": "string", "required": True, "enum": ["off", "heat", "cool", "auto", "fan_only"]},
        },
        returns={"type": "object", "properties": {"success": {"type": "boolean"}}},
    ),
    
    # --- Sensor Tools ---
    "sensor_get_reading": ToolDefinition(
        name="sensor_get_reading",
        description="Get current sensor reading",
        parameters={"device_id": {"type": "string", "required": True}},
        returns={
            "type": "object",
            "properties": {
                "value": {"type": "number"},
                "unit": {"type": "string"},
                "timestamp": {"type": "number"},
            },
        },
    ),
    "sensor_get_contact_state": ToolDefinition(
        name="sensor_get_contact_state",
        description="Get contact sensor state (open/closed)",
        parameters={"device_id": {"type": "string", "required": True}},
        returns={
            "type": "object",
            "properties": {
                "is_open": {"type": "boolean"},
                "last_changed": {"type": "number"},
            },
        },
    ),
    "sensor_get_occupancy": ToolDefinition(
        name="sensor_get_occupancy",
        description="Get occupancy/motion sensor state",
        parameters={"device_id": {"type": "string", "required": True}},
        returns={
            "type": "object",
            "properties": {
                "occupied": {"type": "boolean"},
                "last_motion": {"type": "number"},
            },
        },
    ),
    
    # --- Fan Tools ---
    "fan_on": ToolDefinition(
        name="fan_on",
        description="Turn on a fan",
        parameters={
            "device_id": {"type": "string", "required": True},
            "speed": {"type": "integer", "minimum": 0, "maximum": 100, "description": "Fan speed percentage"},
        },
        returns={"type": "object", "properties": {"success": {"type": "boolean"}}},
    ),
    "fan_off": ToolDefinition(
        name="fan_off",
        description="Turn off a fan",
        parameters={"device_id": {"type": "string", "required": True}},
        returns={"type": "object", "properties": {"success": {"type": "boolean"}}},
    ),
    "fan_set_speed": ToolDefinition(
        name="fan_set_speed",
        description="Set fan speed",
        parameters={
            "device_id": {"type": "string", "required": True},
            "speed": {"type": "integer", "required": True, "minimum": 0, "maximum": 100},
        },
        returns={"type": "object", "properties": {"success": {"type": "boolean"}}},
    ),
    
    # --- Window Covering Tools ---
    "cover_open": ToolDefinition(
        name="cover_open",
        description="Open blinds/shades/curtains",
        parameters={"device_id": {"type": "string", "required": True}},
        returns={"type": "object", "properties": {"success": {"type": "boolean"}}},
    ),
    "cover_close": ToolDefinition(
        name="cover_close",
        description="Close blinds/shades/curtains",
        parameters={"device_id": {"type": "string", "required": True}},
        returns={"type": "object", "properties": {"success": {"type": "boolean"}}},
    ),
    "cover_set_position": ToolDefinition(
        name="cover_set_position",
        description="Set blinds/shades position",
        parameters={
            "device_id": {"type": "string", "required": True},
            "position": {"type": "integer", "required": True, "minimum": 0, "maximum": 100, "description": "Position percentage (0=closed, 100=open)"},
        },
        returns={"type": "object", "properties": {"success": {"type": "boolean"}}},
    ),
    "cover_stop": ToolDefinition(
        name="cover_stop",
        description="Stop blinds/shades movement",
        parameters={"device_id": {"type": "string", "required": True}},
        returns={"type": "object", "properties": {"success": {"type": "boolean"}}},
    ),
    
    # --- Vacuum Tools ---
    "vacuum_start": ToolDefinition(
        name="vacuum_start",
        description="Start robot vacuum cleaning",
        parameters={
            "device_id": {"type": "string", "required": True},
            "mode": {"type": "string", "enum": ["auto", "spot", "edge"], "description": "Cleaning mode"},
        },
        returns={"type": "object", "properties": {"success": {"type": "boolean"}}},
    ),
    "vacuum_stop": ToolDefinition(
        name="vacuum_stop",
        description="Stop robot vacuum",
        parameters={"device_id": {"type": "string", "required": True}},
        returns={"type": "object", "properties": {"success": {"type": "boolean"}}},
    ),
    "vacuum_return_home": ToolDefinition(
        name="vacuum_return_home",
        description="Send robot vacuum back to dock",
        parameters={"device_id": {"type": "string", "required": True}},
        returns={"type": "object", "properties": {"success": {"type": "boolean"}}},
    ),
    "vacuum_get_status": ToolDefinition(
        name="vacuum_get_status",
        description="Get robot vacuum status",
        parameters={"device_id": {"type": "string", "required": True}},
        returns={
            "type": "object",
            "properties": {
                "state": {"type": "string"},
                "battery_percent": {"type": "integer"},
                "error": {"type": "string"},
            },
        },
    ),
}


# =============================================================================
# TRIGGER DEFINITIONS
# =============================================================================

TRIGGER_DEFINITIONS: Dict[str, TriggerDefinition] = {
    # --- Light Triggers ---
    "light_state_changed": TriggerDefinition(
        event="light_state_changed",
        description="Light turned on or off",
        intent_template="Light {device_name} turned {state}",
        payload_schema={
            "device_id": {"type": "string"},
            "device_name": {"type": "string"},
            "state": {"type": "string", "enum": ["on", "off"]},
            "brightness": {"type": "integer"},
        },
    ),
    "light_brightness_changed": TriggerDefinition(
        event="light_brightness_changed",
        description="Light brightness level changed",
        intent_template="Light {device_name} brightness changed to {brightness}%",
        payload_schema={
            "device_id": {"type": "string"},
            "device_name": {"type": "string"},
            "brightness": {"type": "integer"},
        },
    ),
    
    # --- Lock Triggers ---
    "door_locked": TriggerDefinition(
        event="door_locked",
        description="Door was locked",
        intent_template="{device_name} was locked",
        payload_schema={
            "device_id": {"type": "string"},
            "device_name": {"type": "string"},
            "method": {"type": "string", "enum": ["manual", "keypad", "remote", "auto"]},
            "user_id": {"type": "string"},
        },
        route_hint="security/*",
    ),
    "door_unlocked": TriggerDefinition(
        event="door_unlocked",
        description="Door was unlocked",
        intent_template="{device_name} was unlocked via {method}",
        payload_schema={
            "device_id": {"type": "string"},
            "device_name": {"type": "string"},
            "method": {"type": "string"},
            "user_id": {"type": "string"},
        },
        priority="high",
        route_hint="security/*",
    ),
    "lock_tamper_detected": TriggerDefinition(
        event="lock_tamper_detected",
        description="Lock tamper or forced entry detected",
        intent_template="ALERT: Tamper detected on {device_name}",
        payload_schema={
            "device_id": {"type": "string"},
            "device_name": {"type": "string"},
            "alarm_type": {"type": "string"},
        },
        priority="critical",
        route_hint="security/*",
    ),
    "door_opened": TriggerDefinition(
        event="door_opened",
        description="Door was opened",
        intent_template="{device_name} opened",
        payload_schema={
            "device_id": {"type": "string"},
            "device_name": {"type": "string"},
        },
    ),
    "door_closed": TriggerDefinition(
        event="door_closed",
        description="Door was closed",
        intent_template="{device_name} closed",
        payload_schema={
            "device_id": {"type": "string"},
            "device_name": {"type": "string"},
        },
    ),
    
    # --- Motion/Occupancy Triggers ---
    "motion_detected": TriggerDefinition(
        event="motion_detected",
        description="Motion detected by sensor",
        intent_template="Motion detected at {location}",
        payload_schema={
            "device_id": {"type": "string"},
            "device_name": {"type": "string"},
            "location": {"type": "string"},
        },
    ),
    "motion_cleared": TriggerDefinition(
        event="motion_cleared",
        description="Motion sensor cleared (no motion)",
        intent_template="Motion cleared at {location}",
        payload_schema={
            "device_id": {"type": "string"},
            "device_name": {"type": "string"},
            "location": {"type": "string"},
        },
    ),
    
    # --- Contact Sensor Triggers ---
    "contact_opened": TriggerDefinition(
        event="contact_opened",
        description="Contact sensor opened (door/window)",
        intent_template="{device_name} was opened",
        payload_schema={
            "device_id": {"type": "string"},
            "device_name": {"type": "string"},
        },
    ),
    "contact_closed": TriggerDefinition(
        event="contact_closed",
        description="Contact sensor closed",
        intent_template="{device_name} was closed",
        payload_schema={
            "device_id": {"type": "string"},
            "device_name": {"type": "string"},
        },
    ),
    
    # --- Temperature Triggers ---
    "temperature_threshold_exceeded": TriggerDefinition(
        event="temperature_threshold_exceeded",
        description="Temperature exceeded configured threshold",
        intent_template="Temperature at {location} is {temperature}°{unit} ({direction} threshold)",
        payload_schema={
            "device_id": {"type": "string"},
            "location": {"type": "string"},
            "temperature": {"type": "number"},
            "unit": {"type": "string"},
            "threshold": {"type": "number"},
            "direction": {"type": "string", "enum": ["above", "below"]},
        },
        priority="high",
    ),
    
    # --- HVAC Triggers ---
    "hvac_mode_changed": TriggerDefinition(
        event="hvac_mode_changed",
        description="Thermostat mode changed",
        intent_template="Thermostat {device_name} mode changed to {mode}",
        payload_schema={
            "device_id": {"type": "string"},
            "device_name": {"type": "string"},
            "mode": {"type": "string"},
            "previous_mode": {"type": "string"},
        },
    ),
    "hvac_target_reached": TriggerDefinition(
        event="hvac_target_reached",
        description="Target temperature reached",
        intent_template="Target temperature reached at {location}",
        payload_schema={
            "device_id": {"type": "string"},
            "location": {"type": "string"},
            "temperature": {"type": "number"},
        },
    ),
    
    # --- Cover Triggers ---
    "cover_position_changed": TriggerDefinition(
        event="cover_position_changed",
        description="Blinds/shades position changed",
        intent_template="{device_name} moved to {position}%",
        payload_schema={
            "device_id": {"type": "string"},
            "device_name": {"type": "string"},
            "position": {"type": "integer"},
        },
    ),
    
    # --- Vacuum Triggers ---
    "vacuum_cleaning_complete": TriggerDefinition(
        event="vacuum_cleaning_complete",
        description="Robot vacuum finished cleaning",
        intent_template="{device_name} finished cleaning",
        payload_schema={
            "device_id": {"type": "string"},
            "device_name": {"type": "string"},
            "area_cleaned": {"type": "number"},
            "duration_minutes": {"type": "integer"},
        },
    ),
    "vacuum_error": TriggerDefinition(
        event="vacuum_error",
        description="Robot vacuum encountered an error",
        intent_template="{device_name} error: {error}",
        payload_schema={
            "device_id": {"type": "string"},
            "device_name": {"type": "string"},
            "error": {"type": "string"},
            "error_code": {"type": "integer"},
        },
        priority="high",
    ),
    "vacuum_stuck": TriggerDefinition(
        event="vacuum_stuck",
        description="Robot vacuum is stuck",
        intent_template="{device_name} is stuck and needs help",
        payload_schema={
            "device_id": {"type": "string"},
            "device_name": {"type": "string"},
            "location": {"type": "string"},
        },
        priority="high",
    ),
}


# =============================================================================
# DEVICE TYPE → CAPABILITY MAPPING
# =============================================================================

MATTER_TO_ATMOSPHERE: Dict[MatterDeviceType, CapabilityMapping] = {
    # --- Lighting ---
    MatterDeviceType.ON_OFF_LIGHT: CapabilityMapping(
        capability_type=CapabilityType.IOT_LIGHT,
        tools=["light_on", "light_off", "light_toggle", "light_get_state"],
        triggers=["light_state_changed"],
        description="Simple on/off light control",
    ),
    MatterDeviceType.DIMMABLE_LIGHT: CapabilityMapping(
        capability_type=CapabilityType.IOT_LIGHT,
        tools=["light_on", "light_off", "light_toggle", "light_set_brightness", "light_get_state"],
        triggers=["light_state_changed", "light_brightness_changed"],
        description="Dimmable light with brightness control",
    ),
    MatterDeviceType.COLOR_TEMP_LIGHT: CapabilityMapping(
        capability_type=CapabilityType.IOT_LIGHT,
        tools=["light_on", "light_off", "light_toggle", "light_set_brightness", "light_set_color_temp", "light_get_state"],
        triggers=["light_state_changed", "light_brightness_changed"],
        description="Light with color temperature control (warm/cool white)",
    ),
    MatterDeviceType.EXTENDED_COLOR_LIGHT: CapabilityMapping(
        capability_type=CapabilityType.IOT_LIGHT,
        tools=["light_on", "light_off", "light_toggle", "light_set_brightness", "light_set_color_temp", "light_set_color", "light_get_state"],
        triggers=["light_state_changed", "light_brightness_changed"],
        description="Full color RGB/HSV light",
    ),
    
    # --- Plugs & Outlets ---
    MatterDeviceType.ON_OFF_PLUG: CapabilityMapping(
        capability_type=CapabilityType.IOT_SWITCH,
        tools=["outlet_on", "outlet_off", "outlet_toggle", "outlet_get_state"],
        triggers=["light_state_changed"],  # Reuse, state is on/off
        description="Smart plug with on/off control",
    ),
    MatterDeviceType.DIMMABLE_PLUG: CapabilityMapping(
        capability_type=CapabilityType.IOT_SWITCH,
        tools=["outlet_on", "outlet_off", "outlet_toggle", "outlet_get_state", "light_set_brightness"],
        triggers=["light_state_changed", "light_brightness_changed"],
        description="Dimmable smart plug",
    ),
    
    # --- Security ---
    MatterDeviceType.DOOR_LOCK: CapabilityMapping(
        capability_type=CapabilityType.IOT_LOCK,
        tools=["lock_door", "unlock_door", "lock_get_state"],
        triggers=["door_locked", "door_unlocked", "lock_tamper_detected", "door_opened", "door_closed"],
        description="Smart door lock with security controls",
    ),
    MatterDeviceType.CONTACT_SENSOR: CapabilityMapping(
        capability_type=CapabilityType.SENSOR_MOTION,  # Reuse for binary sensors
        tools=["sensor_get_contact_state"],
        triggers=["contact_opened", "contact_closed"],
        description="Door/window contact sensor",
    ),
    MatterDeviceType.OCCUPANCY_SENSOR: CapabilityMapping(
        capability_type=CapabilityType.SENSOR_MOTION,
        tools=["sensor_get_occupancy"],
        triggers=["motion_detected", "motion_cleared"],
        description="Motion/occupancy sensor",
    ),
    
    # --- Climate ---
    MatterDeviceType.THERMOSTAT: CapabilityMapping(
        capability_type=CapabilityType.IOT_HVAC,
        tools=["hvac_set_temperature", "hvac_get_state", "hvac_set_mode"],
        triggers=["hvac_mode_changed", "hvac_target_reached"],
        description="Smart thermostat for HVAC control",
    ),
    MatterDeviceType.TEMPERATURE_SENSOR: CapabilityMapping(
        capability_type=CapabilityType.SENSOR_TEMPERATURE,
        tools=["sensor_get_reading"],
        triggers=["temperature_threshold_exceeded"],
        description="Temperature sensor",
    ),
    MatterDeviceType.HUMIDITY_SENSOR: CapabilityMapping(
        capability_type=CapabilityType.SENSOR_TEMPERATURE,  # Group with temp
        tools=["sensor_get_reading"],
        triggers=["temperature_threshold_exceeded"],  # Reuse threshold trigger
        description="Humidity sensor",
    ),
    MatterDeviceType.FAN: CapabilityMapping(
        capability_type=CapabilityType.IOT_HVAC,
        tools=["fan_on", "fan_off", "fan_set_speed"],
        triggers=["light_state_changed"],  # On/off state
        description="Fan with speed control",
    ),
    MatterDeviceType.AIR_PURIFIER: CapabilityMapping(
        capability_type=CapabilityType.IOT_HVAC,
        tools=["fan_on", "fan_off", "fan_set_speed"],
        triggers=["light_state_changed"],
        description="Air purifier",
    ),
    
    # --- Window Coverings ---
    MatterDeviceType.WINDOW_COVERING: CapabilityMapping(
        capability_type=CapabilityType.IOT_SWITCH,  # No dedicated blinds type yet
        tools=["cover_open", "cover_close", "cover_set_position", "cover_stop"],
        triggers=["cover_position_changed"],
        description="Blinds, shades, or curtains",
    ),
    
    # --- Appliances ---
    MatterDeviceType.ROBOT_VACUUM: CapabilityMapping(
        capability_type=CapabilityType.IOT_SWITCH,  # No dedicated vacuum type
        tools=["vacuum_start", "vacuum_stop", "vacuum_return_home", "vacuum_get_status"],
        triggers=["vacuum_cleaning_complete", "vacuum_error", "vacuum_stuck"],
        description="Robot vacuum cleaner",
    ),
}


class DeviceMapper:
    """
    Maps Matter devices to Atmosphere capabilities.
    
    Handles the translation between Matter device/cluster model
    and Atmosphere's capability/tool/trigger model.
    """
    
    def __init__(self, node_id: str = "matter"):
        self.node_id = node_id
    
    def device_to_capabilities(self, device: MatterDevice) -> List[Capability]:
        """
        Convert a Matter device to Atmosphere capabilities.
        
        A single device may produce multiple capabilities if it has
        multiple endpoints with different device types.
        """
        capabilities = []
        
        for endpoint in device.endpoints:
            if endpoint.endpoint_id == 0:
                continue  # Skip root endpoint
            
            mapping = MATTER_TO_ATMOSPHERE.get(endpoint.device_type)
            if not mapping:
                continue
            
            # Generate capability ID
            cap_id = f"matter:{device.node_id}:ep{endpoint.endpoint_id}:{endpoint.device_type.name.lower()}"
            
            # Build tools
            tools = []
            for tool_name in mapping.tools:
                tool_def = TOOL_DEFINITIONS.get(tool_name)
                if tool_def:
                    tools.append(Tool(
                        name=tool_name,
                        description=tool_def.description,
                        parameters=tool_def.parameters,
                        returns=tool_def.returns,
                    ))
            
            # Build triggers
            triggers = []
            for trigger_name in mapping.triggers:
                trigger_def = TRIGGER_DEFINITIONS.get(trigger_name)
                if trigger_def:
                    triggers.append(Trigger(
                        event=trigger_name,
                        description=trigger_def.description,
                        intent_template=trigger_def.intent_template,
                        payload_schema=trigger_def.payload_schema,
                        route_hint=trigger_def.route_hint,
                        priority=trigger_def.priority,
                    ))
            
            # Create capability
            capability = Capability(
                id=cap_id,
                node_id=self.node_id,
                type=mapping.capability_type,
                tools=tools,
                triggers=triggers,
                metadata={
                    "matter_node_id": device.node_id,
                    "matter_endpoint": endpoint.endpoint_id,
                    "matter_device_type": endpoint.device_type.name,
                    "vendor": device.vendor_name,
                    "product": device.product_name,
                    "label": device.label,
                    "location": device.location,
                    "description": mapping.description,
                },
                status="online" if device.status.value == "online" else "offline",
            )
            
            capabilities.append(capability)
        
        return capabilities
    
    def tool_to_matter_command(
        self,
        tool_name: str,
        device: MatterDevice,
        endpoint: MatterEndpoint,
        params: Dict[str, Any],
    ) -> Tuple[ClusterType, str, Dict[str, Any]]:
        """
        Map a tool call to a Matter cluster command.
        
        Returns:
            Tuple of (cluster_id, command_name, command_args)
        """
        # Lighting tools
        if tool_name in ("light_on", "outlet_on", "fan_on"):
            return (ClusterType.ON_OFF, "On", {})
        
        if tool_name in ("light_off", "outlet_off", "fan_off"):
            return (ClusterType.ON_OFF, "Off", {})
        
        if tool_name in ("light_toggle", "outlet_toggle"):
            return (ClusterType.ON_OFF, "Toggle", {})
        
        if tool_name == "light_set_brightness":
            # Convert 0-100 to 0-254
            level = int((params.get("brightness", 100) / 100) * 254)
            transition = params.get("transition_ms", 0) // 100  # Matter uses 100ms units
            return (ClusterType.LEVEL_CONTROL, "MoveToLevel", {
                "level": level,
                "transitionTime": transition,
            })
        
        if tool_name == "light_set_color_temp":
            # Convert Kelvin to Mireds (1,000,000 / K)
            kelvin = params.get("kelvin", 4000)
            mireds = int(1_000_000 / kelvin)
            transition = params.get("transition_ms", 0) // 100
            return (ClusterType.COLOR_CONTROL, "MoveToColorTemperature", {
                "colorTemperatureMireds": mireds,
                "transitionTime": transition,
            })
        
        if tool_name == "light_set_color":
            color = params.get("color", {})
            transition = params.get("transition_ms", 0) // 100
            
            if isinstance(color, dict):
                if "h" in color:
                    # HSV mode
                    return (ClusterType.COLOR_CONTROL, "MoveToHueAndSaturation", {
                        "hue": color.get("h", 0),
                        "saturation": color.get("s", 100),
                        "transitionTime": transition,
                    })
                elif "r" in color:
                    # RGB → approximate xy conversion would go here
                    # For simplicity, we'll need the bridge to handle this
                    return (ClusterType.COLOR_CONTROL, "MoveToColor", {
                        "colorX": 0,  # Needs proper conversion
                        "colorY": 0,
                        "transitionTime": transition,
                    })
            
            # Default fallback
            return (ClusterType.COLOR_CONTROL, "MoveToHueAndSaturation", {
                "hue": 0,
                "saturation": 100,
                "transitionTime": transition,
            })
        
        # Lock tools
        if tool_name == "lock_door":
            return (ClusterType.DOOR_LOCK, "LockDoor", {
                "PINCode": params.get("pin_code"),
            })
        
        if tool_name == "unlock_door":
            return (ClusterType.DOOR_LOCK, "UnlockDoor", {
                "PINCode": params.get("pin_code"),
            })
        
        # Thermostat tools
        if tool_name == "hvac_set_temperature":
            temp = params.get("temperature", 72)
            unit = params.get("unit", "fahrenheit")
            
            # Convert to centidegrees Celsius
            if unit == "fahrenheit":
                temp_c = (temp - 32) * 5 / 9
            else:
                temp_c = temp
            
            centidegrees = int(temp_c * 100)
            
            mode = params.get("mode")
            if mode == "heat":
                return (ClusterType.THERMOSTAT, "SetpointRaiseLower", {
                    "mode": 0,  # Heat
                    "amount": centidegrees,
                })
            elif mode == "cool":
                return (ClusterType.THERMOSTAT, "SetpointRaiseLower", {
                    "mode": 1,  # Cool
                    "amount": centidegrees,
                })
            else:
                return (ClusterType.THERMOSTAT, "SetpointRaiseLower", {
                    "mode": 2,  # Both
                    "amount": centidegrees,
                })
        
        # Window covering tools
        if tool_name == "cover_open":
            return (ClusterType.WINDOW_COVERING, "UpOrOpen", {})
        
        if tool_name == "cover_close":
            return (ClusterType.WINDOW_COVERING, "DownOrClose", {})
        
        if tool_name == "cover_stop":
            return (ClusterType.WINDOW_COVERING, "StopMotion", {})
        
        if tool_name == "cover_set_position":
            position = params.get("position", 50)
            return (ClusterType.WINDOW_COVERING, "GoToLiftPercentage", {
                "liftPercent100thsValue": position * 100,
            })
        
        # Fan tools
        if tool_name == "fan_set_speed":
            speed = params.get("speed", 50)
            return (ClusterType.FAN_CONTROL, "Step", {
                "direction": 0,  # Increase
                "wrap": True,
                "lowestOff": False,
            })
        
        # Fallback - unknown tool
        raise ValueError(f"Unknown tool: {tool_name}")
    
    def matter_event_to_trigger(
        self,
        device: MatterDevice,
        cluster_id: ClusterType,
        attribute: str,
        old_value: Any,
        new_value: Any,
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Map a Matter attribute change to an Atmosphere trigger.
        
        Returns:
            Tuple of (trigger_event, payload) or None if not mapped
        """
        device_name = device.display_name
        device_id = device.unique_id
        location = device.location or "unknown"
        
        # On/Off cluster changes
        if cluster_id == ClusterType.ON_OFF and attribute == "onOff":
            state = "on" if new_value else "off"
            return ("light_state_changed", {
                "device_id": device_id,
                "device_name": device_name,
                "state": state,
            })
        
        # Level control changes
        if cluster_id == ClusterType.LEVEL_CONTROL and attribute == "currentLevel":
            brightness = int((new_value / 254) * 100)
            return ("light_brightness_changed", {
                "device_id": device_id,
                "device_name": device_name,
                "brightness": brightness,
            })
        
        # Door lock state changes
        if cluster_id == ClusterType.DOOR_LOCK:
            if attribute == "lockState":
                if new_value == 1:  # Locked
                    return ("door_locked", {
                        "device_id": device_id,
                        "device_name": device_name,
                        "method": "unknown",
                    })
                elif new_value == 2:  # Unlocked
                    return ("door_unlocked", {
                        "device_id": device_id,
                        "device_name": device_name,
                        "method": "unknown",
                    })
            
            if attribute == "doorState":
                if new_value == 0:  # Open
                    return ("door_opened", {
                        "device_id": device_id,
                        "device_name": device_name,
                    })
                elif new_value == 1:  # Closed
                    return ("door_closed", {
                        "device_id": device_id,
                        "device_name": device_name,
                    })
        
        # Occupancy changes
        if cluster_id == ClusterType.OCCUPANCY_SENSING and attribute == "occupancy":
            if new_value:
                return ("motion_detected", {
                    "device_id": device_id,
                    "device_name": device_name,
                    "location": location,
                })
            else:
                return ("motion_cleared", {
                    "device_id": device_id,
                    "device_name": device_name,
                    "location": location,
                })
        
        # Boolean state (contact sensor)
        if cluster_id == ClusterType.BOOLEAN_STATE and attribute == "stateValue":
            if new_value:
                return ("contact_opened", {
                    "device_id": device_id,
                    "device_name": device_name,
                })
            else:
                return ("contact_closed", {
                    "device_id": device_id,
                    "device_name": device_name,
                })
        
        # Temperature measurement
        if cluster_id == ClusterType.TEMPERATURE_MEASUREMENT and attribute == "measuredValue":
            # new_value is in centidegrees Celsius
            temp_c = new_value / 100
            temp_f = (temp_c * 9 / 5) + 32
            # Trigger threshold check would need configuration
            # For now, we don't emit threshold triggers automatically
            return None
        
        return None


# Convenience function for getting tool metadata
def get_tool_metadata(tool_name: str) -> Optional[Dict[str, Any]]:
    """Get metadata for a tool (confirmation requirements, security flags)."""
    tool_def = TOOL_DEFINITIONS.get(tool_name)
    if not tool_def:
        return None
    
    return {
        "requires_confirmation": tool_def.requires_confirmation,
        "security_sensitive": tool_def.security_sensitive,
    }
