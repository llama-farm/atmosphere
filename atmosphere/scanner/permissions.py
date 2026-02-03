"""
Permission Handling Module

Checks macOS TCC (Transparency, Consent, and Control) permissions
and provides guidance for missing permissions.

CRITICAL: This module checks permission STATUS, not capability.
Hardware may exist but the app may lack permission to use it.
"""

import logging
import platform
import subprocess
from dataclasses import dataclass
from typing import Dict

logger = logging.getLogger(__name__)


@dataclass
class PermissionStatus:
    """Status of a TCC permission."""
    name: str
    can_detect: bool  # Can we detect hardware exists?
    can_access: bool  # Can we actually use the hardware?
    note: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "can_detect": self.can_detect,
            "can_access": self.can_access,
            "note": self.note,
        }


# Instructions for enabling permissions
PERMISSION_INSTRUCTIONS = {
    "camera": """
To grant camera access:
1. Open System Settings > Privacy & Security > Camera
2. Find this application and enable the toggle
3. Restart the application if needed

Note: Detection via system_profiler works without permission.
Actual camera capture requires TCC approval.
""",
    "microphone": """
To grant microphone access:
1. Open System Settings > Privacy & Security > Microphone
2. Find this application and enable the toggle
3. Restart the application if needed

Note: Detection via system_profiler works without permission.
Actual audio recording requires TCC approval.
""",
    "screen_recording": """
To grant screen recording access:
1. Open System Settings > Privacy & Security > Screen Recording
2. Find this application and enable the toggle
3. Restart the application (required)

Note: Screen recording permission cannot be requested programmatically.
""",
    "accessibility": """
To grant accessibility access:
1. Open System Settings > Privacy & Security > Accessibility
2. Find this application and enable the toggle
3. Restart may be required
""",
}


def check_permissions() -> Dict[str, PermissionStatus]:
    """
    Check TCC permissions status.
    
    Returns dict mapping permission name to PermissionStatus.
    
    NOTE: On macOS, we can DETECT hardware exists via system_profiler
    without TCC permissions. Actual ACCESS requires TCC approval.
    
    On Linux, permissions are generally handled at runtime.
    """
    system = platform.system()
    
    if system == "Darwin":
        return _check_macos_permissions()
    elif system == "Linux":
        return _check_linux_permissions()
    else:
        return {
            "camera": PermissionStatus("camera", True, True, "Unknown platform"),
            "microphone": PermissionStatus("microphone", True, True, "Unknown platform"),
            "screen_recording": PermissionStatus("screen_recording", True, True, "Unknown platform"),
        }


def _check_macos_permissions() -> Dict[str, PermissionStatus]:
    """Check macOS TCC permissions."""
    return {
        "camera": _check_camera_permission(),
        "microphone": _check_microphone_permission(),
        "screen_recording": _check_screen_recording_permission(),
        "accessibility": _check_accessibility_permission(),
    }


def _check_camera_permission() -> PermissionStatus:
    """
    Check camera permission status.
    
    system_profiler works without TCC - it lists hardware.
    Actual camera capture requires permission.
    """
    try:
        # Test that system_profiler works (no permission needed)
        result = subprocess.run(
            ["/usr/sbin/system_profiler", "SPCameraDataType", "-json"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        can_detect = result.returncode == 0
        
        return PermissionStatus(
            name="camera",
            can_detect=can_detect,
            can_access=False,  # Conservative - assume no access
            note="Hardware detection works. TCC permission required for capture."
        )
    except Exception as e:
        return PermissionStatus(
            name="camera",
            can_detect=False,
            can_access=False,
            note=str(e)
        )


def _check_microphone_permission() -> PermissionStatus:
    """Check microphone permission status."""
    try:
        result = subprocess.run(
            ["/usr/sbin/system_profiler", "SPAudioDataType", "-json"],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        can_detect = result.returncode == 0
        
        return PermissionStatus(
            name="microphone",
            can_detect=can_detect,
            can_access=False,
            note="Hardware detection works. TCC permission required for recording."
        )
    except Exception as e:
        return PermissionStatus(
            name="microphone",
            can_detect=False,
            can_access=False,
            note=str(e)
        )


def _check_screen_recording_permission() -> PermissionStatus:
    """
    Check screen recording permission.
    
    There's no clean way to check this without triggering a prompt.
    We assume not granted until explicitly tested.
    """
    return PermissionStatus(
        name="screen_recording",
        can_detect=True,
        can_access=False,
        note="Grant in System Settings > Privacy & Security > Screen Recording"
    )


def _check_accessibility_permission() -> PermissionStatus:
    """Check accessibility permission."""
    try:
        # This AppleScript checks accessibility without triggering dialog
        result = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to return (exists process 1)'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        has_permission = result.returncode == 0
        
        return PermissionStatus(
            name="accessibility",
            can_detect=True,
            can_access=has_permission,
            note="" if has_permission else "Enable in System Settings > Accessibility"
        )
    except Exception:
        return PermissionStatus(
            name="accessibility",
            can_detect=True,
            can_access=False,
            note="Could not check accessibility permission"
        )


def _check_linux_permissions() -> Dict[str, PermissionStatus]:
    """
    Check permissions on Linux.
    
    Linux generally uses group membership (video, audio) for device access.
    """
    import os
    import grp
    
    # Check video group for camera
    try:
        groups = [g.gr_name for g in grp.getgrall() if os.getlogin() in g.gr_mem]
        video_access = "video" in groups
        audio_access = "audio" in groups
    except Exception:
        video_access = True  # Assume access if we can't check
        audio_access = True
    
    return {
        "camera": PermissionStatus(
            name="camera",
            can_detect=True,
            can_access=video_access,
            note="" if video_access else "Add user to 'video' group: sudo usermod -aG video $USER"
        ),
        "microphone": PermissionStatus(
            name="microphone",
            can_detect=True,
            can_access=audio_access,
            note="" if audio_access else "Add user to 'audio' group: sudo usermod -aG audio $USER"
        ),
        "screen_recording": PermissionStatus(
            name="screen_recording",
            can_detect=True,
            can_access=True,
            note="Screen recording generally available on Linux"
        ),
    }


def get_permission_instructions(permission: str) -> str:
    """Get instructions for enabling a specific permission."""
    return PERMISSION_INSTRUCTIONS.get(permission, f"No instructions available for {permission}")


def print_permission_help(missing: list) -> str:
    """Generate help text for missing permissions."""
    if not missing:
        return ""
    
    lines = ["\n⚠️  Permission Notes", "=" * 40]
    
    for perm in missing:
        if perm in PERMISSION_INSTRUCTIONS:
            lines.append(f"\n{perm.upper()}:")
            lines.append(PERMISSION_INSTRUCTIONS[perm].strip())
    
    return "\n".join(lines)
