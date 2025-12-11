"""Embedded API server for IS74 Domofon integration."""
from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from aiohttp import web

_LOGGER = logging.getLogger(__name__)

# Global state
_server_runner: web.AppRunner | None = None
_auto_open_enabled = False
_executor = ThreadPoolExecutor(max_workers=2)


async def setup_server(hass, port: int = 8099) -> bool:
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


async def is_authenticated() -> bool:
    """Check if authenticated."""
    from .api_wrapper import load_tokens
    tokens = await load_tokens()
    return bool(tokens and tokens.get("access_token"))


# Route handlers

async def handle_root(request: web.Request) -> web.Response:
    """Handle root request."""
    authenticated = await is_authenticated()
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>IS74 Домофон</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * {{ box-sizing: border-box; }}
            body {{ font-family: system-ui, -apple-system, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px; background: #1a1a2e; color: #eee; min-height: 100vh; }}
            h1 {{ color: #e94560; text-align: center; margin-bottom: 30px; }}
            .card {{ background: #16213e; padding: 24px; border-radius: 16px; margin: 20px 0; }}
            input {{ width: 100%; padding: 14px; margin: 10px 0; border: 2px solid #0f3460; border-radius: 10px; background: #1a1a2e; color: #fff; font-size: 16px; }}
            input:focus {{ outline: none; border-color: #e94560; }}
            button {{ background: linear-gradient(135deg, #e94560, #c81e45); color: white; padding: 14px 24px; border: none; border-radius: 10px; cursor: pointer; width: 100%; font-size: 16px; font-weight: 600; margin-top: 10px; }}
            button:hover {{ background: linear-gradient(135deg, #c81e45, #a01535); }}
            button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
            .status {{ padding: 12px 16px; border-radius: 10px; margin: 15px 0; text-align: center; font-weight: 500; }}
            .status.ok {{ background: rgba(74, 222, 128, 0.15); color: #4ade80; border: 1px solid rgba(74, 222, 128, 0.3); }}
            .status.error {{ background: rgba(248, 113, 113, 0.15); color: #f87171; border: 1px solid rgba(248, 113, 113, 0.3); }}
            .status.info {{ background: rgba(59, 130, 246, 0.15); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.3); }}
            #result {{ margin-top: 15px; padding: 12px; border-radius: 8px; display: none; }}
            .hidden {{ display: none !important; }}
            .loading {{ opacity: 0.7; pointer-events: none; }}
            h3 {{ margin: 0 0 20px; color: #fff; }}
        </style>
    </head>
    <body>
        <h1>🏠 IS74 Домофон</h1>
        
        <div class="card">
            <h3>Статус</h3>
            <div id="auth-status" class="status {'ok' if authenticated else 'error'}">
                {'✓ Авторизован' if authenticated else '✗ Требуется авторизация'}
            </div>
        </div>
        
        <div id="auth-form" class="card {'hidden' if authenticated else ''}">
            <h3>Авторизация</h3>
            <input type="tel" id="phone" placeholder="Номер телефона (без +7)" inputmode="numeric" />
            <button onclick="requestCode()" id="btn-request">Запросить код</button>
            
            <div id="code-section" class="hidden" style="margin-top: 20px;">
                <input type="text" id="code" placeholder="Код из SMS" inputmode="numeric" maxlength="6" />
                <button onclick="verifyCode()" id="btn-verify">Подтвердить</button>
            </div>
            
            <div id="result"></div>
        </div>
        
        <div id="control-panel" class="card {'hidden' if not authenticated else ''}">
            <h3>Управление</h3>
            <div class="status info">Используйте карточку в Home Assistant</div>
            <button onclick="location.reload()" style="margin-top: 20px; background: #0f3460;">🔄 Обновить статус</button>
        </div>
        
        <script>
            function showResult(msg, isError) {{
                const el = document.getElementById('result');
                el.style.display = 'block';
                el.className = 'status ' + (isError ? 'error' : 'ok');
                el.textContent = msg;
            }}
            
            async function requestCode() {{
                const phone = document.getElementById('phone').value.trim();
                if (!phone) {{ showResult('Введите номер телефона', true); return; }}
                
                const btn = document.getElementById('btn-request');
                btn.disabled = true;
                btn.textContent = 'Отправка...';
                
                try {{
                    const res = await fetch('/auth/login', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{phone}})
                    }});
                    const data = await res.json();
                    
                    if (res.ok) {{
                        showResult('✓ SMS код отправлен', false);
                        document.getElementById('code-section').classList.remove('hidden');
                        document.getElementById('code').focus();
                    }} else {{
                        showResult(data.error || data.detail || 'Ошибка', true);
                    }}
                }} catch(e) {{
                    showResult('Ошибка: ' + e.message, true);
                }}
                
                btn.disabled = false;
                btn.textContent = 'Запросить код';
            }}
            
            async function verifyCode() {{
                const phone = document.getElementById('phone').value.trim();
                const code = document.getElementById('code').value.trim();
                if (!code) {{ showResult('Введите код из SMS', true); return; }}
                
                const btn = document.getElementById('btn-verify');
                btn.disabled = true;
                btn.textContent = 'Проверка...';
                
                try {{
                    const res = await fetch('/auth/verify', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{phone, code}})
                    }});
                    const data = await res.json();
                    
                    if (res.ok) {{
                        showResult('✓ Авторизация успешна!', false);
                        setTimeout(() => location.reload(), 1500);
                    }} else {{
                        showResult(data.error || data.detail || 'Неверный код', true);
                    }}
                }} catch(e) {{
                    showResult('Ошибка: ' + e.message, true);
                }}
                
                btn.disabled = false;
                btn.textContent = 'Подтвердить';
            }}
            
            // Submit on Enter
            document.getElementById('phone').addEventListener('keypress', e => {{ if (e.key === 'Enter') requestCode(); }});
            document.getElementById('code').addEventListener('keypress', e => {{ if (e.key === 'Enter') verifyCode(); }});
        </script>
    </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")


async def handle_status(request: web.Request) -> web.Response:
    """Handle status request."""
    authenticated = await is_authenticated()
    return web.json_response({
        "status": "running",
        "authenticated": authenticated,
        "version": "1.0.0",
    })


async def handle_devices(request: web.Request) -> web.Response:
    """Handle devices request."""
    if not await is_authenticated():
        return web.json_response({"error": "Not authenticated"}, status=401)
    
    try:
        from .api_wrapper import get_devices
        devices = await get_devices()
        return web.json_response({"devices": devices, "count": len(devices)})
    except Exception as e:
        _LOGGER.error(f"Error getting devices: {e}")
        return web.json_response({"devices": [], "count": 0})


async def handle_cameras(request: web.Request) -> web.Response:
    """Handle cameras request."""
    if not await is_authenticated():
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
    if not await is_authenticated():
        return web.json_response({"error": "Not authenticated"}, status=401)
    
    try:
        data = await request.json()
        device_id = data.get("device_id")
        
        from .api_wrapper import open_door
        await open_door(device_id)
        
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
        authenticated = await is_authenticated()
        return web.json_response({
            "fcm_initialized": False,
            "listener_running": False,
            "authenticated": authenticated
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
        phone = data.get("phone", "").strip()
        
        if not phone:
            return web.json_response({"error": "Phone number required"}, status=400)
        
        from .api_wrapper import request_auth_code
        await request_auth_code(phone)
        
        return web.json_response({"message": "SMS код отправлен"})
    except Exception as e:
        _LOGGER.error(f"Auth login error: {e}")
        return web.json_response({"error": str(e)}, status=400)


async def handle_auth_verify(request: web.Request) -> web.Response:
    """Handle auth verify request."""
    try:
        data = await request.json()
        phone = data.get("phone", "").strip()
        code = data.get("code", "").strip()
        
        if not phone or not code:
            return web.json_response({"error": "Phone and code required"}, status=400)
        
        from .api_wrapper import verify_auth_code
        result = await verify_auth_code(phone, code)
        
        return web.json_response({"message": "Авторизация успешна", **result})
    except Exception as e:
        _LOGGER.error(f"Auth verify error: {e}")
        return web.json_response({"error": str(e)}, status=401)


async def handle_stream(request: web.Request) -> web.Response:
    """Handle video stream request."""
    camera_id = request.match_info["camera_id"]
    
    try:
        from .api_wrapper import get_video_stream
        stream = await get_video_stream(camera_id)
        return web.json_response(stream)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)
