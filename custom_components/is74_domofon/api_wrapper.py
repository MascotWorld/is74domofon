"""API wrapper for IS74 Domofon - connects to IS74 API directly with FCM support."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path
from typing import Any, Callable, Optional

import aiohttp

_LOGGER = logging.getLogger(__name__)

# IS74 API base URL
IS74_API_URL = "https://api.is74.ru"
USER_AGENT = "4.12.0 com.intersvyaz.lk/1.30.1.2024040812"

# FCM Constants
FCM_PROJECT_NAME = "intersvyazlk"
FCM_APP_ID = "1:361180765175:android:9c0fafffa6c60062"
FCM_API_KEY = "AIzaSyCWGN-JHGm50OpAo3-2gR7l1kCQIEs7YO4"
FCM_PROJECT_NUMBER = "361180765175"
DEVICE_MODEL = "Google Pixel 10"

# Global session and state
_session: aiohttp.ClientSession | None = None
_device_id: str | None = None
_auth_id: str | None = None
_executor = ThreadPoolExecutor(max_workers=2)

# FCM state
_fcm_client = None
_fcm_token: str | None = None
_fcm_listener_running = False
_fcm_notification_callback: Callable | None = None


def get_config_path() -> Path:
    """Get config directory path."""
    paths = [
        Path("/config/is74_domofon"),  # HA Docker
        Path("/data/is74_domofon"),  # HA Add-on
        Path.home() / ".homeassistant" / "is74_domofon",  # HA Core
        Path("config"),  # Local development
    ]
    
    for path in paths:
        try:
            path.mkdir(parents=True, exist_ok=True)
            return path
        except Exception:
            continue
    
    return Path.home() / ".is74_domofon"


def _load_tokens_sync() -> dict | None:
    """Load tokens from config (sync version)."""
    tokens_file = get_config_path() / "tokens.json"
    if tokens_file.exists():
        try:
            return json.loads(tokens_file.read_text())
        except Exception as e:
            _LOGGER.error(f"Failed to load tokens: {e}")
    return None


def _save_tokens_sync(data: dict) -> bool:
    """Save tokens to config (sync version)."""
    try:
        config_path = get_config_path()
        config_path.mkdir(parents=True, exist_ok=True)
        tokens_file = config_path / "tokens.json"
        tokens_file.write_text(json.dumps(data, indent=2))
        _LOGGER.info(f"Tokens saved to {tokens_file}")
        return True
    except Exception as e:
        _LOGGER.error(f"Failed to save tokens: {e}")
        return False


def _load_fcm_creds_sync() -> dict | None:
    """Load FCM credentials (sync version)."""
    creds_file = get_config_path() / "fcm_creds.json"
    if creds_file.exists():
        try:
            return json.loads(creds_file.read_text())
        except Exception as e:
            _LOGGER.warning(f"Failed to load FCM credentials: {e}")
    return None


def _save_fcm_creds_sync(data: dict) -> bool:
    """Save FCM credentials (sync version)."""
    try:
        config_path = get_config_path()
        config_path.mkdir(parents=True, exist_ok=True)
        creds_file = config_path / "fcm_creds.json"
        creds_file.write_text(json.dumps(data, indent=2))
        _LOGGER.info("FCM credentials saved")
        return True
    except Exception as e:
        _LOGGER.error(f"Failed to save FCM credentials: {e}")
        return False


async def load_tokens() -> dict | None:
    """Load tokens from config (async version)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _load_tokens_sync)


async def save_tokens(data: dict) -> bool:
    """Save tokens to config (async version)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _save_tokens_sync, data)


async def load_fcm_creds() -> dict | None:
    """Load FCM credentials (async version)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _load_fcm_creds_sync)


async def save_fcm_creds(data: dict) -> bool:
    """Save FCM credentials (async version)."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _save_fcm_creds_sync, data)


def get_android_id_from_fcm_creds() -> str | None:
    """Get android_id from FCM credentials."""
    creds = _load_fcm_creds_sync()
    if creds:
        android_id = creds.get("gcm", {}).get("android_id")
        if android_id:
            return str(android_id)
    return None


async def get_session() -> aiohttp.ClientSession:
    """Get or create aiohttp session."""
    global _session, _device_id
    
    if _session is None or _session.closed:
        # Generate device ID if not exists
        if _device_id is None:
            tokens = await load_tokens()
            _device_id = tokens.get("device_id") if tokens else None
            if not _device_id:
                # Try to get from FCM creds
                _device_id = get_android_id_from_fcm_creds()
            if not _device_id:
                _device_id = uuid.uuid4().hex[:16]
                _LOGGER.info(f"Generated new device_id: {_device_id}")
        
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json; version=v2",
            "X-Device-Id": _device_id,
        }
        
        # Add auth token if exists
        tokens = await load_tokens()
        if tokens and tokens.get("access_token"):
            headers["Authorization"] = f"Bearer {tokens['access_token']}"
        
        _session = aiohttp.ClientSession(headers=headers)
    
    return _session


async def request_auth_code(phone: str) -> dict:
    """Request SMS auth code."""
    global _device_id, _auth_id, _session
    
    # Generate new device ID for auth flow
    _device_id = uuid.uuid4().hex[:16]
    _LOGGER.info(f"Using device_id for auth: {_device_id}")
    
    # Close existing session to use new device_id
    if _session and not _session.closed:
        await _session.close()
        _session = None
    
    session = await get_session()
    
    # Correct endpoint: /mobile/auth/get-confirm
    url = f"{IS74_API_URL}/mobile/auth/get-confirm"
    data = {
        "deviceId": _device_id,
        "phone": phone
    }
    
    _LOGGER.info(f"Requesting auth code from {url}")
    
    async with session.post(url, json=data) as resp:
        text = await resp.text()
        _LOGGER.info(f"Auth response status: {resp.status}, body: {text[:500]}")
        
        if resp.status != 200:
            raise Exception(f"Failed to request code: {text}")
        
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            raise Exception(f"Invalid JSON response: {text}")
        
        # Store authId from response
        if isinstance(result, dict) and "authId" in result:
            _auth_id = result["authId"]
            _LOGGER.info(f"Received authId: {_auth_id}")
        
        # Save phone and device_id
        await save_tokens({"phone": phone, "device_id": _device_id})
        
        return result


async def verify_auth_code(phone: str, code: str) -> dict:
    """Verify SMS code and get access token."""
    global _auth_id, _session, _device_id
    
    session = await get_session()
    
    # Step 1: Check confirm code
    url = f"{IS74_API_URL}/mobile/auth/check-confirm"
    
    # Send as form-urlencoded
    body = f"phone={phone}&confirmCode={code}&authId"
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    _LOGGER.info(f"Verifying code at {url}")
    
    async with session.post(url, data=body, headers=headers) as resp:
        text = await resp.text()
        _LOGGER.info(f"Check-confirm response: {resp.status}, body: {text[:500]}")
        
        if resp.status != 200:
            raise Exception(f"Failed to verify code: {text}")
        
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            raise Exception(f"Invalid JSON response: {text}")
        
        # Get authId and addresses
        auth_id = result.get("authId")
        addresses = result.get("addresses", [])
        
        if not auth_id:
            raise Exception("No authId in response")
        
        if not addresses:
            raise Exception("No addresses in response")
        
        # Use first address
        user_id = int(addresses[0].get("USER_ID", 0))
        
        if not user_id:
            raise Exception("No USER_ID in address")
        
        _LOGGER.info(f"Got authId: {auth_id}, user_id: {user_id}")
        
        # Step 2: Get access token
        token_url = f"{IS74_API_URL}/mobile/auth/get-token"
        token_data = {
            "authId": auth_id,
            "userId": str(user_id),
            "uniqueDeviceId": _device_id
        }
        
        _LOGGER.info(f"Getting token from {token_url}")
        
        async with session.post(token_url, data=token_data, headers=headers) as token_resp:
            token_text = await token_resp.text()
            _LOGGER.info(f"Get-token response: {token_resp.status}, body: {token_text[:500]}")
            
            if token_resp.status != 200:
                raise Exception(f"Failed to get token: {token_text}")
            
            try:
                token_result = json.loads(token_text)
            except json.JSONDecodeError:
                raise Exception(f"Invalid token JSON: {token_text}")
            
            # Save tokens
            tokens = await load_tokens() or {}
            tokens.update({
                "access_token": token_result.get("TOKEN"),
                "user_id": token_result.get("USER_ID"),
                "profile_id": token_result.get("PROFILE_ID"),
                "phone": phone,
                "device_id": _device_id,
                "authId": auth_id,
            })
            await save_tokens(tokens)
            
            # Reset session to use new token
            if _session and not _session.closed:
                await _session.close()
                _session = None
            
            _LOGGER.info("Authentication successful!")
            
            return {
                "user_id": tokens.get("user_id"),
                "profile_id": tokens.get("profile_id")
            }


async def get_devices() -> list[dict[str, Any]]:
    """Get list of intercom devices."""
    session = await get_session()
    
    url = f"{IS74_API_URL}/domofon/relays"
    params = {"pagination": "1", "pageSize": "30", "page": "1", "isShared": "1"}
    
    async with session.get(url, params=params) as resp:
        if resp.status == 401:
            _LOGGER.warning("Not authenticated")
            return []
        
        if resp.status != 200:
            _LOGGER.error(f"Failed to get devices: {resp.status}")
            return []
        
        result = await resp.json()
        items = result if isinstance(result, list) else result.get("items", [])
        
        # If empty, try isShared=0
        if not items:
            params["isShared"] = "0"
            params["mainFirst"] = "1"
            async with session.get(url, params=params) as resp2:
                if resp2.status == 200:
                    result2 = await resp2.json()
                    items = result2 if isinstance(result2, list) else result2.get("items", [])
        
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
                        cam_uuid = cam.get("UUID") or cam.get("uuid")
                        if not cam_uuid:
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
                            "uuid": str(cam_uuid),
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
                                    # Get snapshot URL
                                    snapshot = media.get("SNAPSHOT", {})
                                    snapshot_url = None
                                    if isinstance(snapshot, dict):
                                        live_snap = snapshot.get("LIVE", {})
                                        if isinstance(live_snap, dict):
                                            snapshot_url = live_snap.get("LOSSY") or live_snap.get("MAIN")
                                    
                                    return {
                                        "camera_uuid": camera_uuid,
                                        "stream_url": stream_url,
                                        "format": "HLS",
                                        "is_available": True,
                                        "snapshot_url": snapshot_url,
                                    }
    
    return {"camera_uuid": camera_uuid, "is_available": False}


# ============================================================================
# FCM FUNCTIONS
# ============================================================================

def set_fcm_notification_callback(callback: Callable | None) -> None:
    """Set callback for FCM notifications."""
    global _fcm_notification_callback
    _fcm_notification_callback = callback
    _LOGGER.info(f"FCM notification callback {'set' if callback else 'cleared'}")


def _on_fcm_notification(obj, notification, data_message):
    """Handle incoming FCM push notification."""
    _LOGGER.info("=" * 50)
    _LOGGER.info("📞 ВХОДЯЩИЙ ВЫЗОВ / УВЕДОМЛЕНИЕ!")
    _LOGGER.info(f"NOTIFICATION: {notification}")
    _LOGGER.info(f"DATA: {data_message}")
    _LOGGER.info("=" * 50)
    
    # Call the callback if set
    if _fcm_notification_callback:
        try:
            # Extract call data
            call_data = {
                "notification": notification,
                "data": data_message,
            }
            
            # Try to extract device info from notification
            if data_message:
                if isinstance(data_message, dict):
                    call_data["device_id"] = data_message.get("deviceId") or data_message.get("device_id")
                    call_data["relay_id"] = data_message.get("relayId") or data_message.get("relay_id")
                    call_data["address"] = data_message.get("address")
                    call_data["entrance"] = data_message.get("entrance")
            
            _fcm_notification_callback(call_data)
        except Exception as e:
            _LOGGER.error(f"Error in FCM notification callback: {e}")


def _on_fcm_credentials_updated(creds):
    """Save updated FCM credentials."""
    _save_fcm_creds_sync(creds)
    _LOGGER.info("✓ FCM credentials saved")


async def initialize_fcm() -> str:
    """
    Initialize FCM.
    
    - Registers with FCM (if not already registered)
    - Saves fcm_creds.json
    - Returns device_id (android_id) for use in authorization
    """
    global _fcm_client, _fcm_token
    
    try:
        from firebase_messaging import FcmPushClient, FcmRegisterConfig
    except ImportError:
        _LOGGER.error("firebase-messaging package not installed. Run: pip install firebase-messaging")
        raise RuntimeError("firebase-messaging package not installed")
    
    _LOGGER.info("=" * 60)
    _LOGGER.info("📱 Initializing FCM...")
    _LOGGER.info("=" * 60)
    
    # Load existing credentials
    creds = await load_fcm_creds()
    
    # FCM configuration
    fcm_config = FcmRegisterConfig(
        FCM_PROJECT_NAME,
        FCM_APP_ID,
        FCM_API_KEY,
        FCM_PROJECT_NUMBER
    )
    
    # Create FCM client
    _fcm_client = FcmPushClient(
        _on_fcm_notification,
        fcm_config,
        creds,
        _on_fcm_credentials_updated
    )
    
    # Register with FCM
    _LOGGER.info("📝 Registering with FCM...")
    _fcm_token = await _fcm_client.checkin_or_register()
    _LOGGER.info(f"✓ FCM TOKEN: {_fcm_token[:50]}...")
    
    # Get android_id as device_id
    device_id = get_android_id_from_fcm_creds()
    if not device_id:
        raise RuntimeError("Failed to get android_id from FCM credentials")
    
    # Save device_id in tokens.json
    tokens = await load_tokens() or {}
    tokens["device_id"] = device_id
    await save_tokens(tokens)
    
    _LOGGER.info(f"✓ device_id (android_id): {device_id}")
    _LOGGER.info("=" * 60)
    
    return device_id


async def _crm_auth_lk(
    session: aiohttp.ClientSession,
    access_token: str,
    device_id: str,
    profile_id: int,
    user_id: int,
) -> str:
    """Get JWT for td-crm."""
    url = "https://td-crm.is74.ru/api/auth-lk"
    headers = {
        "Authorization": "Bearer",
        "Platform": "Android",
        "User-Agent": USER_AGENT,
        "X-Api-Profile-Id": str(profile_id),
        "X-Api-Source": "com.intersvyaz.lk",
        "X-Api-User-Id": str(user_id),
        "X-App-version": "1.30.1",
        "X-Device-Id": device_id,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    form_data = f"token={access_token}&buyerId=1"
    
    async with session.post(url, headers=headers, data=form_data) as resp:
        text = await resp.text()
        if resp.status != 200:
            raise RuntimeError(f"auth-lk failed {resp.status}: {text}")
        payload = json.loads(text)
        jwt = payload.get("TOKEN")
        if not jwt:
            raise RuntimeError(f"auth-lk response has no TOKEN: {payload}")
        _LOGGER.info("✓ JWT for td-crm obtained")
        return jwt


async def _crm_register_device(
    session: aiohttp.ClientSession,
    crm_jwt: str,
    fcm_token: str,
    device_id: str,
    profile_id: int,
    user_id: int,
) -> None:
    """Register device in td-crm."""
    url = "https://td-crm.is74.ru/api/user-device"
    headers = {
        "Authorization": f"Bearer {crm_jwt}",
        "Platform": "Android",
        "User-Agent": USER_AGENT,
        "X-Api-Profile-Id": str(profile_id),
        "X-Api-Source": "com.intersvyaz.lk",
        "X-Api-User-Id": str(user_id),
        "X-App-version": "1.30.1",
        "X-Device-Id": device_id,
        "Content-Type": "application/json; charset=UTF-8",
        "Accept": "application/json",
    }
    body = {
        "alertType": "push",
        "appId": "com.intersvyaz.lk",
        "deviceId": device_id,
        "deviceName": DEVICE_MODEL,
        "platform": "google",
        "pushToken": fcm_token,
        "sendingPush": True,
    }
    
    async with session.put(url, headers=headers, json=body) as resp:
        if resp.status not in (200, 201, 204):
            text = await resp.text()
            raise RuntimeError(f"user-device failed {resp.status}: {text}")
        _LOGGER.info("✓ Device registered in td-crm")


async def register_push_token(fcm_token: str) -> bool:
    """
    Register FCM token with IS74 backends.
    
    Requires: authentication already completed (access_token in tokens.json)
    """
    tokens = await load_tokens()
    if not tokens or not tokens.get("access_token"):
        raise RuntimeError("Authentication required (no access_token)")
    
    access_token = tokens["access_token"]
    profile_id = tokens.get("profile_id")
    user_id = tokens.get("user_id")
    device_id = tokens.get("device_id") or get_android_id_from_fcm_creds()
    phone = tokens.get("phone")
    
    if not all([profile_id, user_id, device_id]):
        raise RuntimeError("Incomplete authentication data")
    
    _LOGGER.info("=" * 50)
    _LOGGER.info("📤 Registering push with backends...")
    _LOGGER.info(f"  device_id: {device_id}")
    _LOGGER.info(f"  phone: {phone}")
    _LOGGER.info(f"  fcm_token: {fcm_token[:40]}...")
    _LOGGER.info("=" * 50)
    
    async with aiohttp.ClientSession() as session:
        # 1. Get JWT for td-crm
        crm_jwt = await _crm_auth_lk(
            session,
            access_token=access_token,
            device_id=device_id,
            profile_id=profile_id,
            user_id=user_id,
        )
        
        # 2. Register device in td-crm
        await _crm_register_device(
            session,
            crm_jwt=crm_jwt,
            fcm_token=fcm_token,
            device_id=device_id,
            profile_id=profile_id,
            user_id=user_id,
        )
    
    _LOGGER.info("✓ Push registered!")
    return True


async def get_fcm_status() -> dict:
    """Get FCM status."""
    global _fcm_client, _fcm_token, _fcm_listener_running
    
    tokens = await load_tokens()
    fcm_creds = await load_fcm_creds()
    
    return {
        "fcm_initialized": _fcm_client is not None,
        "fcm_token": _fcm_token[:40] + "..." if _fcm_token else None,
        "listener_running": _fcm_listener_running,
        "authenticated": bool(tokens and tokens.get("access_token")),
        "has_fcm_creds": fcm_creds is not None,
        "device_id": tokens.get("device_id") if tokens else None,
    }


async def start_fcm() -> dict:
    """Start FCM push service."""
    global _fcm_client, _fcm_token, _fcm_listener_running
    
    # Check authentication
    tokens = await load_tokens()
    if not tokens or not tokens.get("access_token"):
        raise RuntimeError("Authentication required before starting FCM")
    
    _LOGGER.info("=" * 60)
    _LOGGER.info("🚀 Starting FCM service...")
    _LOGGER.info("=" * 60)
    
    # Initialize FCM if not done yet
    if not _fcm_client or not _fcm_token:
        await initialize_fcm()
    
    # Register push with backends
    try:
        await register_push_token(_fcm_token)
    except Exception as e:
        _LOGGER.error(f"❌ Error registering push: {e}")
        _LOGGER.warning("Continuing - push notifications may not arrive")
    
    # Start listener
    _LOGGER.info("👂 Starting listener...")
    await _fcm_client.start()
    _fcm_listener_running = True
    _LOGGER.info("✓ FCM service started! Waiting for incoming calls...")
    
    return {"message": "FCM started", "status": "running"}


async def stop_fcm() -> dict:
    """Stop FCM push service."""
    global _fcm_client, _fcm_listener_running
    
    _LOGGER.info("Stopping FCM service...")
    
    if _fcm_client:
        try:
            await _fcm_client.stop()
        except Exception as e:
            _LOGGER.warning(f"Error stopping FCM client: {e}")
    
    _fcm_listener_running = False
    _LOGGER.info("FCM service stopped")
    
    return {"message": "FCM stopped", "status": "stopped"}
