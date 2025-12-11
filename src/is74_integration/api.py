"""FastAPI REST API for IS74 Integration Service."""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import os
from typing import Optional

from .api_client import IS74ApiClient, IS74ApiError
from .auth_manager import AuthManager, AuthenticationError, RateLimitError, TokenSet
from .device_controller import DeviceController, DeviceControlError, Device, DoorLockStatus
from .stream_handler import StreamHandler, StreamError, VideoStream, Camera
from .event_manager import EventManager, Event, EventType

import logging
import sys

# Setup logging explicitly for console output
# This ensures Firebase logs are visible
log_level = os.getenv("LOG_LEVEL", "INFO").upper()

# Configure basic logging to console if not already configured
if not logging.root.handlers:
    # Use basicConfig for immediate console output
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        stream=sys.stdout,
        force=True
    )
    print(f"[API] Logging initialized with level: {log_level}")

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Set to INFO to see all logs


# Pydantic models for request/response validation

class LoginRequest(BaseModel):
    """Request model for phone authentication initiation."""
    phone: str = Field(..., description="Phone number (e.g., '9030896568')")


class VerifyRequest(BaseModel):
    """Request model for 2FA code verification."""
    phone: str = Field(..., description="Phone number")
    code: str = Field(..., description="SMS verification code")
    user_id: Optional[int] = Field(None, description="Optional user ID if multiple addresses available")


class LoginResponse(BaseModel):
    """Response model for successful authentication."""
    access_token: str
    user_id: int
    profile_id: int
    expires_at: str
    message: str = "Authentication successful"


class MessageResponse(BaseModel):
    """Generic message response."""
    message: str
    detail: Optional[str] = None


class DeviceResponse(BaseModel):
    """Response model for device information."""
    id: str
    name: str
    mac: str
    status: str
    is_online: bool
    address: Optional[str] = None
    entrance: Optional[str] = None
    flat: Optional[str] = None
    has_cameras: bool = False
    camera_count: int = 0


class DeviceListResponse(BaseModel):
    """Response model for device list."""
    devices: List[DeviceResponse]
    count: int


class DoorOpenRequest(BaseModel):
    """Request model for door open command."""
    device_id: str = Field(..., description="Device ID (MAC address)")
    relay_num: Optional[int] = Field(None, description="Optional relay number")


class DoorOpenResponse(BaseModel):
    """Response model for door open command."""
    success: bool
    device_id: str
    message: str
    timestamp: str


class VideoStreamResponse(BaseModel):
    """Response model for video stream."""
    camera_uuid: str
    stream_url: str
    format: str
    snapshot_url: Optional[str] = None
    is_available: bool


class CameraResponse(BaseModel):
    """Response model for camera information."""
    uuid: str
    name: str
    status: str
    is_online: bool
    has_stream: bool
    address: Optional[str] = None
    snapshot_url: Optional[str] = None


class CameraListResponse(BaseModel):
    """Response model for camera list."""
    cameras: List[CameraResponse]
    count: int


class CallAcceptRequest(BaseModel):
    """Request model for call acceptance."""
    call_id: str = Field(..., description="Call ID from Firebase notification")
    device_id: str = Field(..., description="Device ID")


class CallAcceptResponse(BaseModel):
    """Response model for call acceptance."""
    success: bool
    call_id: str
    message: str
    audio_url: Optional[str] = None


class EventResponse(BaseModel):
    """Response model for event."""
    id: str
    type: str
    device_id: str
    timestamp: str
    metadata: Dict[str, Any]


class EventHistoryResponse(BaseModel):
    """Response model for event history."""
    events: List[EventResponse]
    count: int


class ServiceStatus(BaseModel):
    """Response model for service status."""
    status: str
    authenticated: bool
    uptime_seconds: float
    version: str = "1.0.0"
    components: Dict[str, str]


# Global state
class AppState:
    """Application state container."""
    
    def __init__(self):
        self.api_client: Optional[IS74ApiClient] = None
        self.auth_manager: Optional[AuthManager] = None
        self.device_controller: Optional[DeviceController] = None
        self.stream_handler: Optional[StreamHandler] = None
        self.event_manager: Optional[EventManager] = None
        self.start_time: datetime = datetime.now()
        self.fcm_task: Optional[asyncio.Task] = None  # FCM listener task


app_state = AppState()


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for FastAPI application.
    
    Handles initialization and cleanup of resources.
    """
    # Startup
    logger.info("Starting IS74 Integration Service API")
    
    # Try to load device_id: priority fcm_creds.json -> tokens.json
    saved_device_id = None
    try:
        import json
        from pathlib import Path
        
        # 1. Сначала пробуем fcm_creds.json (android_id)
        fcm_creds_file = Path("config/fcm_creds.json")
        if fcm_creds_file.exists():
            with open(fcm_creds_file, 'r') as f:
                data = json.load(f)
                android_id = data.get("gcm", {}).get("android_id")
                if android_id:
                    saved_device_id = str(android_id)
                    logger.info(f"Using device_id from fcm_creds (android_id): {saved_device_id}")
        
        # 2. Fallback на tokens.json
        if not saved_device_id:
            token_file = Path("config/tokens.json")
            if token_file.exists():
                with open(token_file, 'r') as f:
                    data = json.load(f)
                    saved_device_id = data.get("device_id")
                    if saved_device_id:
                        logger.info(f"Using device_id from tokens.json: {saved_device_id}")
    except Exception as e:
        logger.debug(f"Could not load saved device_id: {e}")
    
    # Initialize components
    app_state.api_client = IS74ApiClient(device_id=saved_device_id)
    app_state.auth_manager = AuthManager(app_state.api_client)
    app_state.device_controller = DeviceController(app_state.api_client)
    app_state.stream_handler = StreamHandler(app_state.api_client)
    app_state.event_manager = EventManager()
    app_state.start_time = datetime.now()
    
    logger.info("All components initialized successfully")
    
    # Автозапуск FCM если уже настроен и авторизован
    try:
        from .callhook import load_fcm_credentials, is_authenticated, start_push_service
        
        fcm_creds = load_fcm_credentials()
        if fcm_creds and is_authenticated():
            logger.info("FCM настроен и пользователь авторизован - запускаем Push сервис...")
            app_state.fcm_task = asyncio.create_task(start_push_service())
            logger.info("Push сервис запущен в фоне")
        elif fcm_creds:
            logger.info("FCM настроен, но требуется авторизация")
        else:
            logger.info("FCM не настроен. Выполните POST /fcm/init")
    except Exception as e:
        logger.warning(f"Не удалось автозапустить FCM: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down IS74 Integration Service API")
    
    # Остановка FCM listener
    if app_state.fcm_task and not app_state.fcm_task.done():
        logger.info("Stopping FCM listener...")
        app_state.fcm_task.cancel()
        try:
            await app_state.fcm_task
        except asyncio.CancelledError:
            pass
        logger.info("FCM listener stopped")
    
    # Cleanup resources
    if app_state.device_controller:
        await app_state.device_controller.close()
    
    if app_state.stream_handler:
        await app_state.stream_handler.close()
    
    if app_state.api_client:
        await app_state.api_client.close()
    
    logger.info("Cleanup completed")


# Create FastAPI application
app = FastAPI(
    title="IS74 Integration Service API",
    description="REST API for IS74 intercom integration with Home Assistant",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)


# Add CORS middleware for Home Assistant integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to Home Assistant origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Mount static files
static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# Dependency injection helpers
def get_auth_manager() -> AuthManager:
    """Get AuthManager instance."""
    if not app_state.auth_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AuthManager not initialized"
        )
    return app_state.auth_manager


def get_device_controller() -> DeviceController:
    """Get DeviceController instance."""
    if not app_state.device_controller:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DeviceController not initialized"
        )
    return app_state.device_controller


def get_stream_handler() -> StreamHandler:
    """Get StreamHandler instance."""
    if not app_state.stream_handler:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="StreamHandler not initialized"
        )
    return app_state.stream_handler


def get_event_manager() -> EventManager:
    """Get EventManager instance."""
    if not app_state.event_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="EventManager not initialized"
        )
    return app_state.event_manager


def require_authentication(auth_manager: AuthManager = Depends(get_auth_manager)) -> AuthManager:
    """Dependency that requires authentication."""
    if not auth_manager.is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please login first."
        )
    return auth_manager


# API Endpoints

@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint - serves the web UI."""
    static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "static")
    index_path = os.path.join(static_dir, "index.html")
    
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    else:
        return """
        <html>
            <body>
                <h1>IS74 Integration Service API</h1>
                <p>Visit <a href="/docs">/docs</a> for API documentation</p>
            </body>
        </html>
        """


@app.get("/api", response_model=MessageResponse)
async def api_root():
    """API root endpoint."""
    return MessageResponse(
        message="IS74 Integration Service API",
        detail="Visit /docs for API documentation"
    )


@app.post("/auth/login", response_model=MessageResponse, status_code=status.HTTP_202_ACCEPTED)
async def request_auth_code(
    request: LoginRequest,
    auth_manager: AuthManager = Depends(get_auth_manager)
):
    """
    Initiate phone authentication by requesting SMS code.
    
    This is step 1 of the authentication flow.
    After calling this endpoint, the user will receive an SMS code.
    Use the /auth/verify endpoint to complete authentication.
    """
    try:
        await auth_manager.request_auth_code(request.phone)
        
        logger.info(f"Auth code requested for phone")
        
        return MessageResponse(
            message="SMS code sent successfully",
            detail="Please check your phone for the verification code"
        )
        
    except RateLimitError as e:
        logger.warning(f"Rate limit exceeded: {e}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e),
            headers={"Retry-After": str(e.retry_after)}
        )
    except AuthenticationError as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error during auth code request: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@app.post("/auth/verify", response_model=LoginResponse)
async def verify_auth_code(
    request: VerifyRequest,
    auth_manager: AuthManager = Depends(get_auth_manager)
):
    """
    Submit 2FA code and complete authentication.
    
    This is step 2 of the authentication flow.
    After successful verification, you will receive an access token.
    """
    try:
        tokens = await auth_manager.login(request.phone, request.code, request.user_id)
        
        logger.info(f"User authenticated successfully: user_id={tokens.user_id}")
        
        return LoginResponse(
            access_token=tokens.access_token,
            user_id=tokens.user_id,
            profile_id=tokens.profile_id,
            expires_at=tokens.expires_at.isoformat()
        )
        
    except RateLimitError as e:
        logger.warning(f"Rate limit exceeded: {e}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e),
            headers={"Retry-After": str(e.retry_after)}
        )
    except AuthenticationError as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error during verification: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


# ============================================================================
# FCM / Push эндпоинты
# ============================================================================

@app.post("/fcm/init", response_model=MessageResponse)
async def init_fcm():
    """
    Инициализация FCM (Шаг 1 - до авторизации).
    
    - Регистрируется в FCM
    - Сохраняет fcm_creds.json
    - Возвращает device_id (android_id) для использования при авторизации
    """
    try:
        from .callhook import initialize_fcm
        
        device_id = await initialize_fcm()
        
        return MessageResponse(
            message=f"FCM инициализирован успешно. device_id: {device_id}"
        )
        
    except Exception as e:
        logger.error(f"FCM init error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.post("/fcm/start", response_model=MessageResponse)
async def start_push_service_endpoint():
    """
    Запуск Push сервиса (Шаг 3 - после авторизации).
    
    - Инициализирует FCM (если ещё не)
    - Регистрирует пуши в бекендах IS74
    - Запускает слушатель в фоне
    """
    try:
        from .callhook import is_authenticated, start_push_service as _start_push_service
        
        if not is_authenticated():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Требуется авторизация. Сначала выполните /auth/login и /auth/verify"
            )
        
        # Проверяем не запущен ли уже
        if app_state.fcm_task and not app_state.fcm_task.done():
            return MessageResponse(
                message="Push сервис уже запущен"
            )
        
        # Запускаем в фоне
        app_state.fcm_task = asyncio.create_task(_start_push_service())
        
        return MessageResponse(
            message="Push сервис запущен"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Push service start error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@app.get("/fcm/status")
async def get_fcm_status():
    """
    Получить статус FCM.
    """
    from .callhook import load_fcm_credentials, is_authenticated, get_device_id
    
    fcm_creds = load_fcm_credentials()
    
    # Статус listener
    listener_running = bool(app_state.fcm_task and not app_state.fcm_task.done())
    
    return {
        "fcm_initialized": fcm_creds is not None,
        "device_id": get_device_id(),
        "authenticated": is_authenticated(),
        "has_fcm_token": bool(fcm_creds and fcm_creds.get("gcm", {}).get("token")),
        "listener_running": listener_running,
    }


@app.post("/fcm/stop", response_model=MessageResponse)
async def stop_push_service():
    """
    Остановка Push сервиса.
    """
    if not app_state.fcm_task or app_state.fcm_task.done():
        return MessageResponse(message="Push сервис не запущен")
    
    app_state.fcm_task.cancel()
    try:
        await app_state.fcm_task
    except asyncio.CancelledError:
        pass
    
    return MessageResponse(message="Push сервис остановлен")


@app.get("/devices/{device_id}/cameras")
async def get_device_cameras(
    device_id: str,
    auth_manager: AuthManager = Depends(get_auth_manager),
    device_controller: DeviceController = Depends(get_device_controller),
    stream_handler: StreamHandler = Depends(get_stream_handler)
):
    """
    Get cameras associated with a specific device.
    
    Returns list of camera UUIDs and details for cameras at the same address/entrance.
    """
    if not auth_manager.is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please login first via /auth/login"
        )
    
    try:
        # Get device
        device = await device_controller.get_device_by_id(device_id)
        if not device:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Device not found: {device_id}"
            )
        
        # Get all cameras
        cameras = await stream_handler.get_cameras()
        
        # Filter cameras by address and entrance
        matching_cameras = []
        for camera in cameras:
            # Match by address and entrance
            if device.address and camera.address:
                if device.address in camera.address or camera.address in device.address:
                    if device.entrance and camera.entrance:
                        if device.entrance == camera.entrance:
                            matching_cameras.append(camera)
                    else:
                        matching_cameras.append(camera)
        
        return {
            "device_id": device_id,
            "cameras": [
                {
                    "uuid": cam.uuid,
                    "name": cam.name,
                    "status": cam.status,
                    "is_online": cam.is_online,
                    "has_stream": cam.has_stream
                }
                for cam in matching_cameras
            ],
            "count": len(matching_cameras)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting device cameras: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@app.get("/devices", response_model=DeviceListResponse)
async def list_devices(
    auth_manager: AuthManager = Depends(get_auth_manager),
    device_controller: DeviceController = Depends(get_device_controller)
):
    """
    List all intercom devices.
    
    Returns a list of all available intercom devices with their status.
    Uses stored authentication token from backend.
    """
    if not auth_manager.is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please login first via /auth/login"
        )
    
    try:
        devices = await device_controller.get_devices()
        
        device_responses = [
            DeviceResponse(
                id=device.id,
                name=device.name,
                mac=device.mac,
                status=device.status,
                is_online=device.is_online,
                address=device.address,
                entrance=device.entrance,
                flat=device.flat,
                has_cameras=device.has_cameras,
                camera_count=len(device.camera_uuids) if device.camera_uuids else 0
            )
            for device in devices
        ]
        
        logger.info(f"Retrieved {len(devices)} devices")
        
        return DeviceListResponse(
            devices=device_responses,
            count=len(device_responses)
        )
        
    except DeviceControlError as e:
        logger.error(f"Device control error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error listing devices: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@app.post("/door/open", response_model=DoorOpenResponse)
async def open_door(
    request: DoorOpenRequest,
    auth_manager: AuthManager = Depends(get_auth_manager),
    device_controller: DeviceController = Depends(get_device_controller),
    event_manager: EventManager = Depends(get_event_manager)
):
    """
    Open door by device ID.
    
    Sends a command to open the specified intercom door.
    The door will automatically lock again after 5 seconds.
    Uses stored authentication token from backend.
    """
    if not auth_manager.is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please login first via /auth/login"
        )
    
    try:
        success = await device_controller.open_door(request.device_id, request.relay_num)
        
        # Log event
        await event_manager.log_event(
            event_type=EventType.DOOR_OPEN,
            device_id=request.device_id,
            metadata={
                "relay_num": request.relay_num,
                "manual": True
            }
        )
        
        logger.info(f"Door opened successfully: device_id={request.device_id}")
        
        return DoorOpenResponse(
            success=success,
            device_id=request.device_id,
            message="Door opened successfully",
            timestamp=datetime.now().isoformat()
        )
        
    except DeviceControlError as e:
        logger.error(f"Failed to open door: {e}")
        
        # Determine appropriate status code
        if e.error_code == "DEVICE_NOT_FOUND":
            status_code = status.HTTP_404_NOT_FOUND
        elif e.error_code in ["503", "504"]:
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        else:
            status_code = status.HTTP_400_BAD_REQUEST
        
        raise HTTPException(
            status_code=status_code,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error opening door: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@app.get("/cameras", response_model=CameraListResponse)
async def list_cameras(
    auth_manager: AuthManager = Depends(get_auth_manager),
    stream_handler: StreamHandler = Depends(get_stream_handler)
):
    """
    List all cameras.
    
    Returns a list of all available cameras with their status.
    Uses stored authentication token from backend.
    """
    if not auth_manager.is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please login first via /auth/login"
        )
    
    try:
        cameras = await stream_handler.get_cameras()
        
        camera_responses = []
        for camera in cameras:
            # Get snapshot URL from camera raw_data
            snapshot_url = None
            if camera.raw_data:
                media = camera.raw_data.get("MEDIA", {})
                if isinstance(media, dict):
                    snapshot_media = media.get("SNAPSHOT", {})
                    if isinstance(snapshot_media, dict):
                        live_snapshot = snapshot_media.get("LIVE", {})
                        if isinstance(live_snapshot, dict):
                            snapshot_url = live_snapshot.get("LOSSY") or live_snapshot.get("MAIN")
            
            camera_responses.append(
                CameraResponse(
                    uuid=camera.uuid,
                    name=camera.name,
                    status=camera.status,
                    is_online=camera.is_online,
                    has_stream=camera.has_stream,
                    address=camera.address,
                    snapshot_url=snapshot_url
                )
            )
        
        logger.info(f"Retrieved {len(cameras)} cameras")
        
        return CameraListResponse(
            cameras=camera_responses,
            count=len(camera_responses)
        )
        
    except StreamError as e:
        logger.error(f"Stream error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error listing cameras: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@app.get("/stream/video/{device_id}", response_model=VideoStreamResponse)
async def get_video_stream(
    device_id: str,
    realtime: bool = True,
    auth_manager: AuthManager = Depends(get_auth_manager),
    stream_handler: StreamHandler = Depends(get_stream_handler),
    event_manager: EventManager = Depends(get_event_manager)
):
    """
    Get video stream URL for a camera.
    
    Returns the HLS stream URL for the specified camera with low latency by default.
    If the camera is unavailable, returns a placeholder image.
    Uses stored authentication token from backend.
    
    Args:
        device_id: Camera UUID
        realtime: Enable low latency mode (default: True)
    """
    if not auth_manager.is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please login first via /auth/login"
        )
    
    try:
        video_stream = await stream_handler.get_video_stream_url(device_id, realtime)
        
        # Log event if stream is available
        if video_stream.is_available:
            await event_manager.log_event(
                event_type=EventType.STREAM_STARTED,
                device_id=device_id,
                metadata={
                    "format": video_stream.format,
                    "realtime": realtime
                }
            )
        
        logger.info(f"Video stream URL retrieved: camera={device_id}, available={video_stream.is_available}")
        
        return VideoStreamResponse(
            camera_uuid=video_stream.camera_uuid,
            stream_url=video_stream.stream_url,
            format=video_stream.format,
            snapshot_url=video_stream.snapshot_url,
            is_available=video_stream.is_available
        )
        
    except StreamError as e:
        logger.error(f"Stream error: {e}")
        
        # Determine appropriate status code
        if e.error_code == "CAMERA_NOT_FOUND":
            status_code = status.HTTP_404_NOT_FOUND
        elif e.error_code == "NO_AUTH_TOKEN":
            status_code = status.HTTP_401_UNAUTHORIZED
        else:
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        
        raise HTTPException(
            status_code=status_code,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Unexpected error getting video stream: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@app.post("/call/accept", response_model=CallAcceptResponse)
async def accept_call(
    request: CallAcceptRequest,
    auth_manager: AuthManager = Depends(get_auth_manager),
    event_manager: EventManager = Depends(get_event_manager)
):
    """
    Accept incoming call.
    
    Accepts an incoming call from the intercom and establishes audio connection.
    Note: Full TeleVoIP integration is not yet implemented.
    Uses stored authentication token from backend.
    """
    if not auth_manager.is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please login first via /auth/login"
        )
    
    try:
        # Log event
        await event_manager.log_event(
            event_type=EventType.CALL_ACCEPTED,
            device_id=request.device_id,
            metadata={
                "call_id": request.call_id
            }
        )
        
        logger.info(f"Call accepted: call_id={request.call_id}, device_id={request.device_id}")
        
        # TODO: Implement full TeleVoIP integration (Task 9)
        # For now, return success response
        return CallAcceptResponse(
            success=True,
            call_id=request.call_id,
            message="Call acceptance recorded. Full TeleVoIP integration pending.",
            audio_url=None
        )
        
    except Exception as e:
        logger.error(f"Unexpected error accepting call: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@app.get("/events", response_model=EventHistoryResponse)
async def get_events(
    limit: int = 100,
    event_type: Optional[str] = None,
    device_id: Optional[str] = None,
    auth_manager: AuthManager = Depends(get_auth_manager),
    event_manager: EventManager = Depends(get_event_manager)
):
    """
    Get event history.
    
    Returns the most recent events, optionally filtered by type or device.
    Uses stored authentication token from backend.
    
    Args:
        limit: Maximum number of events to return (default: 100, max: 100)
        event_type: Optional filter by event type (call, door_open, auto_open, etc.)
        device_id: Optional filter by device ID
    """
    if not auth_manager.is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please login first via /auth/login"
        )
    
    try:
        # Enforce max limit
        limit = min(limit, 100)
        
        # Get events based on filters
        if event_type:
            try:
                event_type_enum = EventType(event_type)
                events = await event_manager.get_history_by_type(event_type_enum, limit)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid event type: {event_type}"
                )
        elif device_id:
            events = await event_manager.get_history_by_device(device_id, limit)
        else:
            events = await event_manager.get_history(limit)
        
        event_responses = [
            EventResponse(
                id=event.id,
                type=event.type.value,
                device_id=event.device_id,
                timestamp=event.timestamp.isoformat(),
                metadata=event.metadata
            )
            for event in events
        ]
        
        logger.info(f"Retrieved {len(events)} events (limit={limit})")
        
        return EventHistoryResponse(
            events=event_responses,
            count=len(event_responses)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error getting events: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


# ============================================================================
# Auto-Open эндпоинты
# ============================================================================

class AutoOpenRequest(BaseModel):
    """Request model for auto-open configuration."""
    enabled: bool = Field(..., description="Enable or disable auto-open")
    device_id: Optional[str] = Field(None, description="Optional device ID to configure")


class AutoOpenResponse(BaseModel):
    """Response model for auto-open status."""
    enabled: bool
    schedules: List[Dict[str, Any]] = []


# Global auto-open state (in production, this should be persisted)
_auto_open_enabled: bool = False


@app.get("/auto-open", response_model=AutoOpenResponse)
async def get_auto_open_status():
    """
    Get current auto-open configuration.
    """
    global _auto_open_enabled
    return AutoOpenResponse(enabled=_auto_open_enabled, schedules=[])


@app.post("/auto-open", response_model=AutoOpenResponse)
async def set_auto_open_status(request: AutoOpenRequest):
    """
    Set auto-open configuration.
    """
    global _auto_open_enabled
    _auto_open_enabled = request.enabled
    logger.info(f"Auto-open {'enabled' if request.enabled else 'disabled'}")
    return AutoOpenResponse(enabled=_auto_open_enabled, schedules=[])


@app.get("/events/stream")
async def stream_events(
    auth_manager: AuthManager = Depends(get_auth_manager),
    event_manager: EventManager = Depends(get_event_manager)
):
    """
    Stream events in real-time using Server-Sent Events (SSE).
    
    This endpoint streams new events as they occur, allowing the UI
    to display push notifications in real-time.
    """
    if not auth_manager.is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please login first via /auth/login"
        )
    
    from fastapi.responses import StreamingResponse
    import json
    
    async def event_generator():
        """Generate SSE events."""
        # Send initial connection message
        yield f"data: {json.dumps({'type': 'connected', 'message': 'Event stream connected'})}\n\n"
        
        # Track last seen event
        last_event_count = 0
        
        try:
            while True:
                # Get recent events
                events = await event_manager.get_history(limit=10)
                
                # Check if there are new events
                if len(events) > last_event_count:
                    # Send new events
                    for event in events[:len(events) - last_event_count]:
                        event_data = {
                            'type': 'event',
                            'event': {
                                'id': event.id,
                                'type': event.type.value,
                                'device_id': event.device_id,
                                'timestamp': event.timestamp.isoformat(),
                                'metadata': event.metadata
                            }
                        }
                        yield f"data: {json.dumps(event_data)}\n\n"
                    
                    last_event_count = len(events)
                
                # Wait before checking again
                await asyncio.sleep(1)
                
        except asyncio.CancelledError:
            logger.info("Event stream cancelled")
            yield f"data: {json.dumps({'type': 'disconnected', 'message': 'Event stream disconnected'})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.get("/status", response_model=ServiceStatus)
async def get_status(
    auth_manager: AuthManager = Depends(get_auth_manager)
):
    """
    Get service status.
    
    Returns the current status of the integration service and its components.
    Also checks and refreshes Firebase token if needed.
    """
    try:
        uptime = (datetime.now() - app_state.start_time).total_seconds()
        
        components = {
            "api_client": "initialized" if app_state.api_client else "not_initialized",
            "auth_manager": "initialized" if app_state.auth_manager else "not_initialized",
            "device_controller": "initialized" if app_state.device_controller else "not_initialized",
            "stream_handler": "initialized" if app_state.stream_handler else "not_initialized",
            "event_manager": "initialized" if app_state.event_manager else "not_initialized"
        }
        
        # Check and refresh Firebase token if authenticated
        if auth_manager and auth_manager.is_authenticated():
            tokens = auth_manager.get_tokens()
            
            # Check if Firebase token exists and if it needs refresh
            if tokens:
                if not tokens.firebase_token:
                    # No Firebase token - get one
                    logger.info("No Firebase token found, requesting new one")
                    try:
                        import uuid
                        firebase_instance_id = str(uuid.uuid4())
                        firebase_instance_token = str(uuid.uuid4())
                        
                        await auth_manager.get_firebase_token(
                            firebase_instance_id=firebase_instance_id,
                            firebase_instance_token=firebase_instance_token
                        )
                        logger.info("Firebase token obtained successfully")
                    except Exception as e:
                        logger.warning(f"Failed to get Firebase token (non-critical): {e}")
                
                elif tokens.firebase_token_expires_soon(threshold_seconds=86400):  # 24 hours
                    # Firebase token expires soon - refresh it
                    logger.info("Firebase token expires soon, refreshing")
                    try:
                        import uuid
                        firebase_instance_id = str(uuid.uuid4())
                        firebase_instance_token = str(uuid.uuid4())
                        
                        await auth_manager.refresh_firebase_token_if_needed(
                            firebase_instance_id=firebase_instance_id,
                            firebase_instance_token=firebase_instance_token
                        )
                        logger.info("Firebase token refreshed successfully")
                    except Exception as e:
                        logger.warning(f"Failed to refresh Firebase token (non-critical): {e}")
        
        return ServiceStatus(
            status="running",
            authenticated=auth_manager.is_authenticated() if auth_manager else False,
            uptime_seconds=uptime,
            components=components
        )
        
    except Exception as e:
        logger.error(f"Error getting status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


# Error handlers

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """Custom HTTP exception handler."""
    logger.warning(f"HTTP {exc.status_code}: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=exc.headers
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    """General exception handler for unhandled exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"}
    )


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "is74_integration.api:app",
        host="0.0.0.0",
        port=10777,
        reload=True,
        log_level="info"
    )
