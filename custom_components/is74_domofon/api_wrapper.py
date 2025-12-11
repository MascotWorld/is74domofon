"""API wrapper for IS74 Domofon - connects to IS74 API directly."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

# IS74 API base URL
IS74_API_URL = "https://api.is74.ru"
USER_AGENT = "4.12.0 com.intersvyaz.lk/1.30.1.2024040812"

# Global session
_session: aiohttp.ClientSession | None = None
_device_id: str | None = None


def get_config_path() -> Path:
    """Get config directory path."""
    config_dir = Path.home() / ".homeassistant" / "is74_domofon"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def load_tokens() -> dict | None:
    """Load tokens from config."""
    tokens_file = get_config_path() / "tokens.json"
    if tokens_file.exists():
        try:
            return json.loads(tokens_file.read_text())
        except Exception:
            pass
    return None


def save_tokens(data: dict) -> bool:
    """Save tokens to config."""
    try:
        tokens_file = get_config_path() / "tokens.json"
        tokens_file.write_text(json.dumps(data, indent=2))
        return True
    except Exception as e:
        _LOGGER.error(f"Failed to save tokens: {e}")
        return False


async def get_session() -> aiohttp.ClientSession:
    """Get or create aiohttp session."""
    global _session, _device_id
    
    if _session is None or _session.closed:
        # Generate device ID if not exists
        if _device_id is None:
            tokens = load_tokens()
            _device_id = tokens.get("device_id") if tokens else None
            if not _device_id:
                import uuid
                _device_id = uuid.uuid4().hex[:16]
        
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json; version=v2",
            "X-Device-Id": _device_id,
        }
        
        # Add auth token if exists
        tokens = load_tokens()
        if tokens and tokens.get("access_token"):
            headers["Authorization"] = f"Bearer {tokens['access_token']}"
        
        _session = aiohttp.ClientSession(headers=headers)
    
    return _session


async def request_auth_code(phone: str) -> dict:
    """Request SMS auth code."""
    global _device_id
    
    session = await get_session()
    
    # Generate device ID for this session
    import uuid
    _device_id = uuid.uuid4().hex[:16]
    
    url = f"{IS74_API_URL}/auth/request-code"
    data = {"phone": phone}
    
    async with session.post(url, json=data) as resp:
        if resp.status != 200:
            text = await resp.text()
            raise Exception(f"Failed to request code: {text}")
        
        result = await resp.json()
        
        # Save phone and device_id for verification
        save_tokens({"phone": phone, "device_id": _device_id})
        
        return result


async def verify_auth_code(phone: str, code: str) -> dict:
    """Verify SMS code and get access token."""
    session = await get_session()
    
    url = f"{IS74_API_URL}/auth/confirm-code"
    data = {"phone": phone, "code": code}
    
    async with session.post(url, json=data) as resp:
        if resp.status != 200:
            text = await resp.text()
            raise Exception(f"Failed to verify code: {text}")
        
        result = await resp.json()
        
        # Check if we need to select address
        if result.get("ADDRESSES"):
            # Multiple addresses - use first one
            addresses = result["ADDRESSES"]
            if addresses:
                user_id = addresses[0].get("USER_ID")
                profile_id = addresses[0].get("ID")
                
                # Select address
                select_url = f"{IS74_API_URL}/auth/select-profile"
                select_data = {"user_id": user_id, "profile_id": profile_id}
                
                async with session.post(select_url, json=select_data) as select_resp:
                    if select_resp.status == 200:
                        result = await select_resp.json()
        
        # Save tokens
        tokens = load_tokens() or {}
        tokens.update({
            "access_token": result.get("TOKEN") or result.get("access_token"),
            "user_id": result.get("USER_ID") or result.get("user_id"),
            "profile_id": result.get("PROFILE_ID") or result.get("profile_id"),
            "phone": phone,
        })
        save_tokens(tokens)
        
        # Update session with new token
        global _session
        _session = None  # Force recreate with new token
        
        return {"user_id": tokens.get("user_id"), "profile_id": tokens.get("profile_id")}


async def get_devices() -> list[dict[str, Any]]:
    """Get list of intercom devices."""
    session = await get_session()
    
    url = f"{IS74_API_URL}/domofon/relays"
    params = {"pagination": "1", "pageSize": "30", "page": "1", "isShared": "1"}
    
    async with session.get(url, params=params) as resp:
        if resp.status != 200:
            return []
        
        result = await resp.json()
        items = result if isinstance(result, list) else result.get("items", [])
        
        devices = []
        for item in items:
            mac = item.get("MAC_ADDR") or item.get("MAC") or item.get("id")
            if not mac:
                continue
            
            devices.append({
                "id": mac,
                "name": item.get("RELAY_TYPE") or item.get("ADDRESS") or "Домофон",
                "mac": mac,
                "status": "online" if item.get("STATUS_CODE") == "0" else "offline",
                "is_online": item.get("STATUS_CODE") == "0",
                "address": item.get("ADDRESS"),
                "entrance": item.get("ENTRANCE_UID"),
                "flat": item.get("FLAT"),
                "has_cameras": bool(item.get("CAMERAS")),
                "camera_count": len(item.get("CAMERAS", [])),
                "relay_id": item.get("RELAY_ID"),
            })
        
        return devices


async def get_cameras() -> list[dict[str, Any]]:
    """Get list of cameras."""
    session = await get_session()
    
    url = "https://cams.is74.ru/api/self-cams-with-group"
    
    async with session.get(url) as resp:
        if resp.status != 200:
            return []
        
        result = await resp.json()
        
        cameras = []
        if isinstance(result, list):
            for group in result:
                if isinstance(group, dict) and "cameras" in group:
                    for cam in group.get("cameras", []):
                        uuid = cam.get("UUID") or cam.get("uuid")
                        if not uuid:
                            continue
                        
                        # Get snapshot URL
                        media = cam.get("MEDIA", {})
                        snapshot_url = None
                        if isinstance(media, dict):
                            snapshot = media.get("SNAPSHOT", {})
                            if isinstance(snapshot, dict):
                                live = snapshot.get("LIVE", {})
                                if isinstance(live, dict):
                                    snapshot_url = live.get("LOSSY") or live.get("MAIN")
                        
                        cameras.append({
                            "uuid": str(uuid),
                            "name": cam.get("NAME") or cam.get("ADDRESS") or "Камера",
                            "status": "online" if cam.get("ACCESS", {}).get("LIVE", {}).get("STATUS") else "offline",
                            "is_online": bool(cam.get("ACCESS", {}).get("LIVE", {}).get("STATUS")),
                            "has_stream": bool(cam.get("HLS") or cam.get("REALTIME_HLS")),
                            "address": cam.get("ADDRESS"),
                            "snapshot_url": snapshot_url,
                        })
        
        return cameras


async def open_door(device_id: str) -> dict:
    """Open door."""
    session = await get_session()
    
    # First get device info to get relay_id
    devices = await get_devices()
    device = next((d for d in devices if d["id"] == device_id), None)
    
    if not device:
        raise Exception(f"Device not found: {device_id}")
    
    relay_id = device.get("relay_id")
    if not relay_id:
        raise Exception(f"No relay_id for device: {device_id}")
    
    url = f"{IS74_API_URL}/domofon/relays/{relay_id}/open"
    params = {"from": "app"}
    
    async with session.post(url, params=params, json={}) as resp:
        if resp.status not in (200, 201, 204):
            text = await resp.text()
            raise Exception(f"Failed to open door: {text}")
        
        return {"success": True}


async def get_video_stream(camera_uuid: str) -> dict:
    """Get video stream URL."""
    cameras = await get_cameras()
    camera = next((c for c in cameras if c["uuid"] == camera_uuid), None)
    
    if not camera:
        raise Exception(f"Camera not found: {camera_uuid}")
    
    # Get HLS URL from camera data
    session = await get_session()
    url = "https://cams.is74.ru/api/self-cams-with-group"
    
    async with session.get(url) as resp:
        if resp.status != 200:
            return {"is_available": False}
        
        result = await resp.json()
        
        for group in result if isinstance(result, list) else []:
            for cam in group.get("cameras", []) if isinstance(group, dict) else []:
                if str(cam.get("UUID") or cam.get("uuid")) == camera_uuid:
                    media = cam.get("MEDIA", {})
                    if isinstance(media, dict):
                        hls = media.get("HLS", {})
                        if isinstance(hls, dict):
                            live = hls.get("LIVE", {})
                            if isinstance(live, dict):
                                stream_url = live.get("LOW_LATENCY") or live.get("MAIN")
                                if stream_url:
                                    return {
                                        "camera_uuid": camera_uuid,
                                        "stream_url": stream_url,
                                        "format": "HLS",
                                        "is_available": True,
                                        "snapshot_url": camera.get("snapshot_url"),
                                    }
    
    return {"camera_uuid": camera_uuid, "is_available": False}


async def get_fcm_status() -> dict:
    """Get FCM status."""
    # For now, return basic status
    # Full FCM integration would require additional setup
    return {
        "fcm_initialized": False,
        "listener_running": False,
        "authenticated": bool(load_tokens() and load_tokens().get("access_token")),
    }


async def start_fcm() -> None:
    """Start FCM listener."""
    # FCM requires firebase-messaging library
    _LOGGER.info("FCM start requested - not implemented in embedded mode")


async def stop_fcm() -> None:
    """Stop FCM listener."""
    _LOGGER.info("FCM stop requested")

