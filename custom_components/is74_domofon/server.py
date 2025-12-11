"""Embedded API server for IS74 Domofon integration."""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any
from aiohttp import web

_LOGGER = logging.getLogger(__name__)

# Global state
_server_runner: web.AppRunner | None = None
_api_client = None
_auth_manager = None
_auto_open_enabled = False


async def setup_server(hass, port: int = 8000) -> bool:
    """Set up the embedded API server."""
    global _server_runner
    
    if _server_runner is not None:
        _LOGGER.warning("Server already running")
        return True
    
    app = web.Application()
    
    # Add routes
    app.router.add_get("/", handle_root)
    app.router.add_get("/status", handle_status)
    app.router.add_get("/devices", handle_devices)
    app.router.add_get("/cameras", handle_cameras)
    app.router.add_post("/door/open", handle_open_door)
    app.router.add_get("/auto-open", handle_get_auto_open)
    app.router.add_post("/auto-open", handle_set_auto_open)
    app.router.add_get("/fcm/status", handle_fcm_status)
    app.router.add_post("/fcm/start", handle_fcm_start)
    app.router.add_post("/fcm/stop", handle_fcm_stop)
    app.router.add_post("/auth/login", handle_auth_login)
    app.router.add_post("/auth/verify", handle_auth_verify)
    app.router.add_get("/stream/video/{camera_id}", handle_stream)
    
    # Store hass reference
    app["hass"] = hass
    
    # Add CORS middleware
    app.middlewares.append(cors_middleware)
    
    _server_runner = web.AppRunner(app)
    await _server_runner.setup()
    
    site = web.TCPSite(_server_runner, "0.0.0.0", port)
    await site.start()
    
    _LOGGER.info(f"IS74 Domofon API server started on port {port}")
    return True


async def stop_server() -> None:
    """Stop the embedded API server."""
    global _server_runner
    
    if _server_runner is not None:
        await _server_runner.cleanup()
        _server_runner = None
        _LOGGER.info("IS74 Domofon API server stopped")


@web.middleware
async def cors_middleware(request: web.Request, handler):
    """Add CORS headers to all responses."""
    if request.method == "OPTIONS":
        response = web.Response()
    else:
        try:
            response = await handler(request)
        except web.HTTPException as ex:
            response = ex
    
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    return response


def get_config_path() -> Path:
    """Get config directory path."""
    # Use HA config directory
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


def is_authenticated() -> bool:
    """Check if authenticated."""
    tokens = load_tokens()
    return bool(tokens and tokens.get("access_token"))


# Route handlers

async def handle_root(request: web.Request) -> web.Response:
    """Handle root request."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>IS74 Домофон</title>
        <meta charset="utf-8">
        <style>
            body { font-family: system-ui; max-width: 600px; margin: 50px auto; padding: 20px; background: #1a1a2e; color: #eee; }
            h1 { color: #e94560; }
            .card { background: #16213e; padding: 20px; border-radius: 12px; margin: 20px 0; }
            input { width: 100%; padding: 12px; margin: 8px 0; border: none; border-radius: 8px; box-sizing: border-box; }
            button { background: #e94560; color: white; padding: 12px 24px; border: none; border-radius: 8px; cursor: pointer; width: 100%; font-size: 16px; }
            button:hover { background: #c81e45; }
            .status { padding: 10px; border-radius: 8px; margin: 10px 0; }
            .status.ok { background: rgba(74, 222, 128, 0.2); color: #4ade80; }
            .status.error { background: rgba(248, 113, 113, 0.2); color: #f87171; }
            #result { margin-top: 20px; }
        </style>
    </head>
    <body>
        <h1>🏠 IS74 Домофон</h1>
        <div id="status-box" class="card">
            <h3>Статус</h3>
            <div id="auth-status" class="status">Проверка...</div>
        </div>
        
        <div id="auth-form" class="card" style="display:none;">
            <h3>Авторизация</h3>
            <input type="tel" id="phone" placeholder="Номер телефона (без +7)" />
            <button onclick="requestCode()">Запросить код</button>
            <div id="code-form" style="display:none; margin-top: 20px;">
                <input type="text" id="code" placeholder="Код из SMS" />
                <button onclick="verifyCode()">Подтвердить</button>
            </div>
            <div id="result"></div>
        </div>
        
        <div id="control-panel" class="card" style="display:none;">
            <h3>Управление</h3>
            <p>Используйте карточку в Home Assistant для управления домофоном.</p>
            <button onclick="location.reload()">Обновить статус</button>
        </div>
        
        <script>
            async function checkStatus() {
                try {
                    const res = await fetch('/status');
                    const data = await res.json();
                    const statusEl = document.getElementById('auth-status');
                    
                    if (data.authenticated) {
                        statusEl.className = 'status ok';
                        statusEl.textContent = '✓ Авторизован';
                        document.getElementById('auth-form').style.display = 'none';
                        document.getElementById('control-panel').style.display = 'block';
                    } else {
                        statusEl.className = 'status error';
                        statusEl.textContent = '✗ Требуется авторизация';
                        document.getElementById('auth-form').style.display = 'block';
                        document.getElementById('control-panel').style.display = 'none';
                    }
                } catch(e) {
                    document.getElementById('auth-status').textContent = 'Ошибка: ' + e.message;
                }
            }
            
            async function requestCode() {
                const phone = document.getElementById('phone').value;
                const res = await fetch('/auth/login', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({phone})
                });
                const data = await res.json();
                document.getElementById('result').textContent = data.message || data.detail;
                if (res.ok) {
                    document.getElementById('code-form').style.display = 'block';
                }
            }
            
            async function verifyCode() {
                const phone = document.getElementById('phone').value;
                const code = document.getElementById('code').value;
                const res = await fetch('/auth/verify', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({phone, code})
                });
                const data = await res.json();
                document.getElementById('result').textContent = data.message || data.detail || 'Успешно!';
                if (res.ok) {
                    setTimeout(() => location.reload(), 1000);
                }
            }
            
            checkStatus();
        </script>
    </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")


async def handle_status(request: web.Request) -> web.Response:
    """Handle status request."""
    return web.json_response({
        "status": "running",
        "authenticated": is_authenticated(),
        "version": "1.0.0",
    })


async def handle_devices(request: web.Request) -> web.Response:
    """Handle devices request."""
    if not is_authenticated():
        return web.json_response({"error": "Not authenticated"}, status=401)
    
    # Import and use the API client
    try:
        from .api_wrapper import get_devices
        devices = await get_devices()
        return web.json_response({"devices": devices, "count": len(devices)})
    except Exception as e:
        _LOGGER.error(f"Error getting devices: {e}")
        return web.json_response({"devices": [], "count": 0})


async def handle_cameras(request: web.Request) -> web.Response:
    """Handle cameras request."""
    if not is_authenticated():
        return web.json_response({"error": "Not authenticated"}, status=401)
    
    try:
        from .api_wrapper import get_cameras
        cameras = await get_cameras()
        return web.json_response({"cameras": cameras, "count": len(cameras)})
    except Exception as e:
        _LOGGER.error(f"Error getting cameras: {e}")
        return web.json_response({"cameras": [], "count": 0})


async def handle_open_door(request: web.Request) -> web.Response:
    """Handle open door request."""
    if not is_authenticated():
        return web.json_response({"error": "Not authenticated"}, status=401)
    
    try:
        data = await request.json()
        device_id = data.get("device_id")
        
        from .api_wrapper import open_door
        result = await open_door(device_id)
        
        return web.json_response({
            "success": True,
            "device_id": device_id,
            "message": "Door opened"
        })
    except Exception as e:
        _LOGGER.error(f"Error opening door: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def handle_get_auto_open(request: web.Request) -> web.Response:
    """Handle get auto-open status."""
    global _auto_open_enabled
    return web.json_response({"enabled": _auto_open_enabled, "schedules": []})


async def handle_set_auto_open(request: web.Request) -> web.Response:
    """Handle set auto-open status."""
    global _auto_open_enabled
    data = await request.json()
    _auto_open_enabled = data.get("enabled", False)
    return web.json_response({"enabled": _auto_open_enabled, "schedules": []})


async def handle_fcm_status(request: web.Request) -> web.Response:
    """Handle FCM status request."""
    try:
        from .api_wrapper import get_fcm_status
        status = await get_fcm_status()
        return web.json_response(status)
    except Exception:
        return web.json_response({
            "fcm_initialized": False,
            "listener_running": False,
            "authenticated": is_authenticated()
        })


async def handle_fcm_start(request: web.Request) -> web.Response:
    """Handle FCM start request."""
    try:
        from .api_wrapper import start_fcm
        await start_fcm()
        return web.json_response({"message": "FCM started"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_fcm_stop(request: web.Request) -> web.Response:
    """Handle FCM stop request."""
    try:
        from .api_wrapper import stop_fcm
        await stop_fcm()
        return web.json_response({"message": "FCM stopped"})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_auth_login(request: web.Request) -> web.Response:
    """Handle auth login request."""
    try:
        data = await request.json()
        phone = data.get("phone")
        
        from .api_wrapper import request_auth_code
        await request_auth_code(phone)
        
        return web.json_response({"message": "SMS код отправлен"})
    except Exception as e:
        _LOGGER.error(f"Auth login error: {e}")
        return web.json_response({"detail": str(e)}, status=400)


async def handle_auth_verify(request: web.Request) -> web.Response:
    """Handle auth verify request."""
    try:
        data = await request.json()
        phone = data.get("phone")
        code = data.get("code")
        
        from .api_wrapper import verify_auth_code
        result = await verify_auth_code(phone, code)
        
        return web.json_response({"message": "Авторизация успешна", **result})
    except Exception as e:
        _LOGGER.error(f"Auth verify error: {e}")
        return web.json_response({"detail": str(e)}, status=401)


async def handle_stream(request: web.Request) -> web.Response:
    """Handle video stream request."""
    camera_id = request.match_info["camera_id"]
    
    try:
        from .api_wrapper import get_video_stream
        stream = await get_video_stream(camera_id)
        return web.json_response(stream)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

