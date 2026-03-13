"""API wrapper for IS74 Domofon - connects to IS74 API directly with FCM support."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

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


def _normalize_phone(phone: str) -> str:
    """Normalize phone number to the 10-digit format expected by IS74."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 11 and digits[0] in {"7", "8"}:
        return digits[1:]
    return digits


def _build_public_headers(device_id: str) -> dict[str, str]:
    """Build headers for unauthenticated mobile endpoints."""
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/json; version=v2",
        "X-Device-Id": device_id,
    }


def get_config_path() -> Path:
    """Get config directory path."""
    paths = [
        Path("/config/is74_domofon"),  # Home Assistant OS / Container
        Path.home() / ".homeassistant" / "is74_domofon",  # Home Assistant Core
    ]
    
    for path in paths:
        try:
            path.mkdir(parents=True, exist_ok=True)
            return path
        except Exception:
            continue
    
    return Path.home() / ".is74_domofon"


def _utcnow_iso() -> str:
    """Return current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


async def _persist_fcm_metadata(fcm_token: str | None = None) -> None:
    """Persist the latest FCM metadata alongside auth tokens."""
    tokens = await load_tokens() or {}
    fcm_creds = await load_fcm_creds() or {}
    installation = fcm_creds.get("fcm", {}).get("installation", {})

    if fcm_token:
        tokens["fcm_token"] = fcm_token
        tokens["fcm_token_updated_at"] = _utcnow_iso()

    expires_in = installation.get("expires_in")
    if expires_in is not None:
        tokens["fcm_installation_expires_in"] = expires_in

    registration_name = fcm_creds.get("fcm", {}).get("registration", {}).get("name")
    if registration_name:
        tokens["fcm_registration_name"] = registration_name

    await save_tokens(tokens)


def _normalize_accounts(tokens: dict | None) -> list[dict]:
    """Return stored account list with backward-compatible fallback."""
    if not tokens:
        return []

    accounts = tokens.get("accounts")
    if isinstance(accounts, list) and accounts:
        return [account for account in accounts if account.get("access_token")]

    if tokens.get("access_token") and tokens.get("user_id") and tokens.get("profile_id"):
        return [
            {
                "user_id": tokens.get("user_id"),
                "profile_id": tokens.get("profile_id"),
                "access_token": tokens.get("access_token"),
                "address": tokens.get("address"),
                "is_primary": True,
            }
        ]

    return []


def _build_auth_headers(access_token: str, device_id: str) -> dict[str, str]:
    """Build request headers for a specific account token."""
    return {
        "User-Agent": USER_AGENT,
        "Accept": "application/json; version=v2",
        "X-Device-Id": device_id,
        "Authorization": f"Bearer {access_token}",
    }


async def _fetch_relays_for_account(account: dict, device_id: str) -> list[dict]:
    """Fetch relay list for a single account."""
    headers = _build_auth_headers(account["access_token"], device_id)
    url = f"{IS74_API_URL}/domofon/relays"

    async with aiohttp.ClientSession(headers=headers) as session:
        params = {"pagination": "1", "pageSize": "30", "page": "1", "isShared": "1"}

        async with session.get(url, params=params) as resp:
            if resp.status == 401:
                _LOGGER.warning("Not authenticated for user_id=%s", account.get("user_id"))
                return []

            if resp.status != 200:
                _LOGGER.error(
                    "Failed to get devices for user_id=%s: %s",
                    account.get("user_id"),
                    resp.status,
                )
                return []

            result = await resp.json()
            items = result if isinstance(result, list) else result.get("items", [])

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

        devices.append(
            {
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
                "account_user_id": account.get("user_id"),
                "account_address": account.get("address"),
                "profile_id": account.get("profile_id"),
            }
        )

    return devices


async def _fetch_cameras_for_account(account: dict, device_id: str) -> list[dict]:
    """Fetch cameras for a single account."""
    headers = _build_auth_headers(account["access_token"], device_id)
    url = "https://cams.is74.ru/api/self-cams-with-group"

    async with aiohttp.ClientSession(headers=headers) as session:
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

                    media = cam.get("MEDIA", {})
                    snapshot_url = None
                    if isinstance(media, dict):
                        snapshot = media.get("SNAPSHOT", {})
                        if isinstance(snapshot, dict):
                            live = snapshot.get("LIVE", {})
                            if isinstance(live, dict):
                                snapshot_url = live.get("LOSSY") or live.get("MAIN")

                    cameras.append(
                        {
                            "uuid": str(cam_uuid),
                            "name": cam.get("NAME") or cam.get("ADDRESS") or "Камера",
                            "status": (
                                "online"
                                if cam.get("ACCESS", {}).get("LIVE", {}).get("STATUS")
                                else "offline"
                            ),
                            "is_online": bool(cam.get("ACCESS", {}).get("LIVE", {}).get("STATUS")),
                            "has_stream": bool(cam.get("HLS") or cam.get("REALTIME_HLS")),
                            "address": cam.get("ADDRESS"),
                            "snapshot_url": snapshot_url,
                            "account_user_id": account.get("user_id"),
                            "account_address": account.get("address"),
                            "profile_id": account.get("profile_id"),
                        }
                    )

    return cameras


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
    """Request a login confirmation code or phone call."""
    global _device_id, _auth_id, _session
    phone = _normalize_phone(phone)

    # Generate new device ID for auth flow
    _device_id = uuid.uuid4().hex[:16]
    _LOGGER.info(f"Using device_id for auth: {_device_id}")

    # Close existing session to use new device_id
    if _session and not _session.closed:
        await _session.close()
        _session = None

    # Correct endpoint: /mobile/auth/get-confirm
    url = f"{IS74_API_URL}/mobile/auth/get-confirm"
    data = {
        "deviceId": _device_id,
        "phone": phone
    }

    _LOGGER.info(f"Requesting auth code from {url}")

    async with aiohttp.ClientSession(headers=_build_public_headers(_device_id)) as session:
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

    # Save auth context without dropping existing tokens
    tokens = await load_tokens() or {}
    tokens.update(
        {
            "phone": phone,
            "device_id": _device_id,
            "authId": _auth_id,
            "confirmType": result.get("confirmType"),
            "confirmMessage": result.get("message"),
        }
    )
    await save_tokens(tokens)

    return result


async def verify_auth_code(phone: str, code: str) -> dict:
    """Verify the confirmation code and get access tokens."""
    global _auth_id, _session, _device_id
    phone = _normalize_phone(phone)
    tokens = await load_tokens() or {}
    auth_id = _auth_id or tokens.get("authId")
    auth_device_id = _device_id or tokens.get("device_id")

    if not auth_id:
        raise Exception("No authId available for verification")
    if not auth_device_id:
        raise Exception("No device_id available for verification")

    # Step 1: Check confirm code
    url = f"{IS74_API_URL}/mobile/auth/check-confirm"

    headers = {
        **_build_public_headers(auth_device_id),
        "Content-Type": "application/x-www-form-urlencoded",
    }

    _LOGGER.info(f"Verifying code at {url}")

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post(
            url,
            data={"phone": phone, "confirmCode": code, "authId": auth_id},
        ) as resp:
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

        accounts: list[dict[str, Any]] = []
        token_url = f"{IS74_API_URL}/mobile/auth/get-token"

        for index, address_info in enumerate(addresses):
            user_id = int(address_info.get("USER_ID", 0))
            if not user_id:
                _LOGGER.warning("Skipping address without USER_ID: %s", address_info)
                continue

            token_data = {
                "authId": auth_id,
                "userId": str(user_id),
                "uniqueDeviceId": auth_device_id,
            }

            _LOGGER.info("Getting token for user_id=%s from %s", user_id, token_url)

            async with session.post(token_url, data=token_data) as token_resp:
                token_text = await token_resp.text()
                _LOGGER.info(
                    "Get-token response for user_id=%s: %s, body: %s",
                    user_id,
                    token_resp.status,
                    token_text[:500],
                )

                if token_resp.status != 200:
                    raise Exception(f"Failed to get token for user_id={user_id}: {token_text}")

                try:
                    token_result = json.loads(token_text)
                except json.JSONDecodeError:
                    raise Exception(f"Invalid token JSON: {token_text}")

            accounts.append(
                {
                    "user_id": token_result.get("USER_ID"),
                    "profile_id": token_result.get("PROFILE_ID"),
                    "access_token": token_result.get("TOKEN"),
                    "address": address_info.get("ADDRESS"),
                    "is_primary": index == 0,
                }
            )

        if not accounts:
            raise Exception("No usable accounts returned by get-token")

        primary = accounts[0]
        tokens.update(
            {
                "access_token": primary.get("access_token"),
                "user_id": primary.get("user_id"),
                "profile_id": primary.get("profile_id"),
                "phone": phone,
                "device_id": auth_device_id,
                "authId": auth_id,
                "address": primary.get("address"),
                "accounts": accounts,
                "confirmType": None,
                "confirmMessage": None,
            }
        )
        await save_tokens(tokens)

        _auth_id = auth_id
        _device_id = auth_device_id

        if _session and not _session.closed:
            await _session.close()
            _session = None

        _LOGGER.info("Authentication successful! Loaded %s account(s)", len(accounts))

        return {
            "user_id": primary.get("user_id"),
            "profile_id": primary.get("profile_id"),
            "accounts": [
                {
                    "user_id": account.get("user_id"),
                    "profile_id": account.get("profile_id"),
                    "address": account.get("address"),
                    "is_primary": account.get("is_primary", False),
                }
                for account in accounts
            ],
        }


async def get_devices() -> list[dict[str, Any]]:
    """Get list of intercom devices."""
    tokens = await load_tokens()
    accounts = _normalize_accounts(tokens)
    device_id = tokens.get("device_id") if tokens else get_android_id_from_fcm_creds()
    if not accounts or not device_id:
        return []

    devices_by_id: dict[str, dict[str, Any]] = {}
    for account in accounts:
        for device in await _fetch_relays_for_account(account, device_id):
            devices_by_id.setdefault(device["id"], device)

    return list(devices_by_id.values())


async def get_cameras() -> list[dict[str, Any]]:
    """Get list of cameras."""
    tokens = await load_tokens()
    accounts = _normalize_accounts(tokens)
    device_id = tokens.get("device_id") if tokens else get_android_id_from_fcm_creds()
    if not accounts or not device_id:
        return []

    cameras_by_uuid: dict[str, dict[str, Any]] = {}
    for account in accounts:
        for camera in await _fetch_cameras_for_account(account, device_id):
            cameras_by_uuid.setdefault(camera["uuid"], camera)

    return list(cameras_by_uuid.values())


async def open_door(device_id: str) -> dict:
    """Open door."""
    devices = await get_devices()
    device = next((d for d in devices if d["id"] == device_id), None)

    if not device:
        raise Exception(f"Device not found: {device_id}")

    relay_id = device.get("relay_id")
    if not relay_id:
        raise Exception(f"No relay_id for device: {device_id}")

    tokens = await load_tokens()
    accounts = _normalize_accounts(tokens)
    session_device_id = tokens.get("device_id") if tokens else get_android_id_from_fcm_creds()
    account = next(
        (item for item in accounts if item.get("user_id") == device.get("account_user_id")),
        accounts[0] if accounts else None,
    )
    if not account or not session_device_id:
        raise Exception("No matching account found for device")

    url = f"{IS74_API_URL}/domofon/relays/{relay_id}/open"
    params = {"from": "app"}

    async with aiohttp.ClientSession(
        headers=_build_auth_headers(account["access_token"], session_device_id)
    ) as session:
        async with session.post(url, params=params, json={}) as resp:
            if resp.status not in (200, 201, 204):
                text = await resp.text()
                raise Exception(f"Failed to open door: {text}")

            return {"success": True}


async def get_video_stream(camera_uuid: str) -> dict:
    """Get video stream URL."""
    cameras = await get_cameras()
    camera = next((item for item in cameras if item["uuid"] == camera_uuid), None)
    if not camera:
        return {"camera_uuid": camera_uuid, "is_available": False}

    tokens = await load_tokens()
    accounts = _normalize_accounts(tokens)
    session_device_id = tokens.get("device_id") if tokens else get_android_id_from_fcm_creds()
    account = next(
        (item for item in accounts if item.get("user_id") == camera.get("account_user_id")),
        accounts[0] if accounts else None,
    )
    if not account or not session_device_id:
        return {"camera_uuid": camera_uuid, "is_available": False}

    url = "https://cams.is74.ru/api/self-cams-with-group"
    async with aiohttp.ClientSession(
        headers=_build_auth_headers(account["access_token"], session_device_id)
    ) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return {"camera_uuid": camera_uuid, "is_available": False}

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
    await _persist_fcm_metadata(_fcm_token)
    
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
    
    accounts = _normalize_accounts(tokens)
    device_id = tokens.get("device_id") or get_android_id_from_fcm_creds()
    phone = tokens.get("phone")

    if not accounts or not device_id:
        raise RuntimeError("Incomplete authentication data")
    
    _LOGGER.info("=" * 50)
    _LOGGER.info("📤 Registering push with backends...")
    _LOGGER.info(f"  device_id: {device_id}")
    _LOGGER.info(f"  phone: {phone}")
    _LOGGER.info(f"  fcm_token: {fcm_token[:40]}...")
    _LOGGER.info("=" * 50)
    
    async with aiohttp.ClientSession() as session:
        for account in accounts:
            profile_id = account.get("profile_id")
            user_id = account.get("user_id")
            access_token = account.get("access_token")
            if not all([profile_id, user_id, access_token]):
                _LOGGER.warning("Skipping incomplete account during push registration: %s", account)
                continue

            crm_jwt = await _crm_auth_lk(
                session,
                access_token=access_token,
                device_id=device_id,
                profile_id=profile_id,
                user_id=user_id,
            )

            await _crm_register_device(
                session,
                crm_jwt=crm_jwt,
                fcm_token=fcm_token,
                device_id=device_id,
                profile_id=profile_id,
                user_id=user_id,
            )

    tokens["fcm_backend_registered_at"] = _utcnow_iso()
    tokens["fcm_token"] = fcm_token
    await save_tokens(tokens)

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
        "has_fcm_token": bool(_fcm_token or fcm_creds and fcm_creds.get("gcm", {}).get("token")),
        "listener_running": _fcm_listener_running,
        "authenticated": bool(tokens and tokens.get("access_token")),
        "has_fcm_creds": fcm_creds is not None,
        "device_id": tokens.get("device_id") if tokens else None,
        "account_count": len(_normalize_accounts(tokens)),
        "fcm_token_updated_at": tokens.get("fcm_token_updated_at") if tokens else None,
        "fcm_backend_registered_at": tokens.get("fcm_backend_registered_at") if tokens else None,
        "fcm_installation_expires_in": tokens.get("fcm_installation_expires_in") if tokens else None,
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


async def refresh_fcm_registration(force_restart_listener: bool = False) -> dict:
    """Refresh Firebase installation and backend registration before the 7-day token expires."""
    global _fcm_client, _fcm_token, _fcm_listener_running

    tokens = await load_tokens()
    if not tokens or not tokens.get("access_token"):
        raise RuntimeError("Authentication required before refreshing FCM")

    was_running = _fcm_listener_running

    if _fcm_client and was_running:
        _LOGGER.info("Stopping FCM listener before registration refresh")
        try:
            await _fcm_client.stop()
        except Exception as err:
            _LOGGER.warning(f"Failed to stop FCM listener cleanly: {err}")
        _fcm_listener_running = False

    await initialize_fcm()
    await register_push_token(_fcm_token)

    if was_running or force_restart_listener:
        _LOGGER.info("Restarting FCM listener after registration refresh")
        await _fcm_client.start()
        _fcm_listener_running = True

    return {
        "message": "FCM registration refreshed",
        "status": "running" if _fcm_listener_running else "ready",
    }


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
