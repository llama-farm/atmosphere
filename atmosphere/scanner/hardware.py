"""
Hardware Detection Module

Detects cameras, microphones, and speakers.

IMPORTANT: Uses permission-safe methods (system_profiler) that don't require
TCC permissions. We detect hardware existence, not access capability.
"""

import json
import logging
import platform
import re
import subprocess
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class CameraInfo:
    """Information about a detected camera."""
    name: str
    unique_id: Optional[str] = None
    model_id: Optional[str] = None
    is_builtin: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "unique_id": self.unique_id,
            "model_id": self.model_id,
            "is_builtin": self.is_builtin,
        }


@dataclass
class MicrophoneInfo:
    """Information about a detected microphone."""
    name: str
    manufacturer: Optional[str] = None
    is_input: bool = True
    is_builtin: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "manufacturer": self.manufacturer,
            "is_input": self.is_input,
            "is_builtin": self.is_builtin,
        }


@dataclass
class SpeakerInfo:
    """Information about a detected speaker."""
    name: str
    manufacturer: Optional[str] = None
    is_builtin: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "manufacturer": self.manufacturer,
            "is_builtin": self.is_builtin,
        }


def detect_hardware() -> Dict[str, Any]:
    """
    Detect available hardware devices.
    
    Uses permission-safe methods that don't trigger TCC prompts.
    Returns dict with cameras, microphones, speakers lists.
    """
    system = platform.system()
    
    if system == "Darwin":
        return _detect_hardware_macos()
    elif system == "Linux":
        return _detect_hardware_linux()
    else:
        logger.warning(f"Hardware detection not supported on {system}")
        return {"cameras": [], "microphones": [], "speakers": []}


def _detect_hardware_macos() -> Dict[str, Any]:
    """
    Detect hardware on macOS using system_profiler.
    
    system_profiler doesn't require camera/mic permissions - it just
    lists hardware that exists. Actual ACCESS to devices requires TCC.
    """
    return {
        "cameras": _detect_cameras_macos(),
        "microphones": _detect_microphones_macos(),
        "speakers": _detect_speakers_macos(),
    }


def _detect_cameras_macos() -> List[CameraInfo]:
    """
    Detect cameras on macOS using system_profiler.
    
    NOTE: This does NOT require camera permission. It only lists
    hardware devices. To actually capture frames, TCC permission is needed.
    """
    cameras = []
    
    try:
        result = subprocess.run(
            ["/usr/sbin/system_profiler", "SPCameraDataType", "-json"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            logger.warning(f"system_profiler SPCameraDataType failed")
            return []
        
        data = json.loads(result.stdout)
        camera_data = data.get("SPCameraDataType", [])
        
        for camera in camera_data:
            name = camera.get("_name", "Unknown Camera")
            unique_id = camera.get("spcamera_unique-id")
            model_id = camera.get("spcamera_model-id")
            
            # Check if it's a built-in camera
            is_builtin = (
                "FaceTime" in name or 
                "Built-in" in name or
                "Internal" in name.lower()
            )
            
            cameras.append(CameraInfo(
                name=name,
                unique_id=unique_id,
                model_id=model_id,
                is_builtin=is_builtin,
            ))
        
        return cameras
        
    except subprocess.TimeoutExpired:
        logger.warning("Camera detection timed out")
        return []
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse camera data: {e}")
        return []
    except Exception as e:
        logger.warning(f"Camera detection failed: {e}")
        return []


def _detect_microphones_macos() -> List[MicrophoneInfo]:
    """
    Detect microphones on macOS using system_profiler.
    
    NOTE: This does NOT require microphone permission. It only lists
    hardware devices. To actually record audio, TCC permission is needed.
    """
    mics = []
    
    try:
        result = subprocess.run(
            ["/usr/sbin/system_profiler", "SPAudioDataType", "-json"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            logger.warning(f"system_profiler SPAudioDataType failed")
            return []
        
        data = json.loads(result.stdout)
        audio_data = data.get("SPAudioDataType", [])
        
        for device_group in audio_data:
            items = device_group.get("_items", [])
            
            for device in items:
                name = device.get("_name", "Unknown")
                manufacturer = device.get("coreaudio_device_manufacturer")
                
                # Check if this is an input device
                inputs = device.get("coreaudio_device_input", 0)
                if isinstance(inputs, str):
                    inputs = int(inputs) if inputs.isdigit() else 0
                
                if inputs > 0:
                    is_builtin = (
                        "Built-in" in name or 
                        "Internal" in name.lower() or
                        "MacBook" in name
                    )
                    
                    mics.append(MicrophoneInfo(
                        name=name,
                        manufacturer=manufacturer,
                        is_input=True,
                        is_builtin=is_builtin,
                    ))
        
        return mics
        
    except subprocess.TimeoutExpired:
        logger.warning("Microphone detection timed out")
        return []
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse audio data: {e}")
        return []
    except Exception as e:
        logger.warning(f"Microphone detection failed: {e}")
        return []


def _detect_speakers_macos() -> List[SpeakerInfo]:
    """Detect speakers on macOS using system_profiler."""
    speakers = []
    
    try:
        result = subprocess.run(
            ["/usr/sbin/system_profiler", "SPAudioDataType", "-json"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return []
        
        data = json.loads(result.stdout)
        audio_data = data.get("SPAudioDataType", [])
        
        for device_group in audio_data:
            items = device_group.get("_items", [])
            
            for device in items:
                name = device.get("_name", "Unknown")
                manufacturer = device.get("coreaudio_device_manufacturer")
                
                # Check if this is an output device
                outputs = device.get("coreaudio_device_output", 0)
                if isinstance(outputs, str):
                    outputs = int(outputs) if outputs.isdigit() else 0
                
                if outputs > 0:
                    is_builtin = (
                        "Built-in" in name or 
                        "Internal" in name.lower() or
                        "MacBook" in name
                    )
                    
                    speakers.append(SpeakerInfo(
                        name=name,
                        manufacturer=manufacturer,
                        is_builtin=is_builtin,
                    ))
        
        return speakers
        
    except Exception as e:
        logger.warning(f"Speaker detection failed: {e}")
        return []


def _detect_hardware_linux() -> Dict[str, Any]:
    """Detect hardware on Linux."""
    return {
        "cameras": _detect_cameras_linux(),
        "microphones": _detect_microphones_linux(),
        "speakers": _detect_speakers_linux(),
    }


def _detect_cameras_linux() -> List[CameraInfo]:
    """Detect cameras on Linux using v4l2-ctl."""
    cameras = []
    
    try:
        result = subprocess.run(
            ["v4l2-ctl", "--list-devices"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return []
        
        current_name = ""
        for line in result.stdout.split("\n"):
            line = line.strip()
            if line and not line.startswith("/"):
                current_name = line.rstrip(":")
            elif line.startswith("/dev/video"):
                cameras.append(CameraInfo(
                    name=current_name or line,
                    is_builtin="built" in current_name.lower(),
                ))
        
        return cameras
        
    except FileNotFoundError:
        logger.debug("v4l2-ctl not found, camera detection unavailable")
        return []
    except Exception as e:
        logger.warning(f"Linux camera detection failed: {e}")
        return []


def _detect_microphones_linux() -> List[MicrophoneInfo]:
    """Detect microphones on Linux using arecord."""
    mics = []
    
    try:
        result = subprocess.run(
            ["arecord", "-l"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return []
        
        for line in result.stdout.split("\n"):
            if "card" in line.lower():
                match = re.search(r'card \d+:.*\[(.+?)\]', line)
                if match:
                    name = match.group(1)
                    mics.append(MicrophoneInfo(
                        name=name,
                        is_input=True,
                    ))
        
        return mics
        
    except FileNotFoundError:
        logger.debug("arecord not found, microphone detection unavailable")
        return []
    except Exception as e:
        logger.warning(f"Linux microphone detection failed: {e}")
        return []


def _detect_speakers_linux() -> List[SpeakerInfo]:
    """Detect speakers on Linux using aplay."""
    speakers = []
    
    try:
        result = subprocess.run(
            ["aplay", "-l"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return []
        
        for line in result.stdout.split("\n"):
            if "card" in line.lower():
                match = re.search(r'card \d+:.*\[(.+?)\]', line)
                if match:
                    name = match.group(1)
                    speakers.append(SpeakerInfo(name=name))
        
        return speakers
        
    except FileNotFoundError:
        logger.debug("aplay not found, speaker detection unavailable")
        return []
    except Exception as e:
        logger.warning(f"Linux speaker detection failed: {e}")
        return []


def get_hardware_summary(hardware: Dict[str, Any]) -> str:
    """Generate a human-readable summary of detected hardware."""
    lines = []
    
    cameras = hardware.get("cameras", [])
    if cameras:
        lines.append("Cameras:")
        for c in cameras:
            prefix = "📷" if c.is_builtin else "🎥"
            lines.append(f"  {prefix} {c.name}")
    
    mics = hardware.get("microphones", [])
    if mics:
        lines.append("\nMicrophones:")
        for m in mics:
            prefix = "🎙️" if m.is_builtin else "🎤"
            lines.append(f"  {prefix} {m.name}")
    
    speakers = hardware.get("speakers", [])
    if speakers:
        lines.append("\nSpeakers:")
        for s in speakers:
            prefix = "🔊"
            lines.append(f"  {prefix} {s.name}")
    
    if not lines:
        return "No hardware detected"
    
    return "\n".join(lines)
