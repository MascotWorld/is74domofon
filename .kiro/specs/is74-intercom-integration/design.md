# Design Document

## Overview

Система интеграции домофона is74.ru с Home Assistant состоит из трех основных компонентов:

1. **Integration Service** - Python-сервис на базе FastAPI, который выступает посредником между IS74 API и Home Assistant
2. **Home Assistant Custom Component** - кастомная интеграция для Home Assistant, предоставляющая entities (lock, camera, sensor)
3. **Firebase Listener** - модуль для подписки на push-уведомления о звонках

Архитектура следует принципам разделения ответственности: аутентификация, управление устройствами, обработка медиа-потоков и интеграция с Home Assistant реализованы как отдельные модули.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Home Assistant                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │         Custom Integration Component                  │   │
│  │  - Lock Entity (door control)                        │   │
│  │  - Camera Entity (video stream)                      │   │
│  │  - Binary Sensor (call status)                       │   │
│  │  - Switch (auto-open)                                │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ WebSocket / REST API
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                   Integration Service (FastAPI)              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Auth Manager │  │ Device       │  │ Stream       │      │
│  │ - Login/2FA  │  │ Controller   │  │ Handler      │      │
│  │ - Token mgmt │  │ - Door open  │  │ - Video      │      │
│  │ - Refresh    │  │ - Call accept│  │ - Audio      │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Firebase     │  │ Event        │  │ Config       │      │
│  │ Listener     │  │ Manager      │  │ Manager      │      │
│  │ - Subscribe  │  │ - History    │  │ - Encryption │      │
│  │ - Handle msg │  │ - Logging    │  │ - Storage    │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└─────────────────────────────────────────────────────────────┘
                            │
                            │ HTTPS / Firebase
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    External Services                         │
│  ┌──────────────┐  ┌──────────────┐                         │
│  │ IS74 API     │  │ Firebase     │                         │
│  │ - Auth       │  │ Cloud        │                         │
│  │ - Device API │  │ Messaging    │                         │
│  │ - Stream URL │  │              │                         │
│  └──────────────┘  └──────────────┘                         │
└─────────────────────────────────────────────────────────────┘
```

## Components and Interfaces

### 1. Auth Manager

Отвечает за аутентификацию и управление токенами.

```python
class AuthManager:
    async def login(username: str, password: str) -> AuthResponse
    async def submit_2fa(session_id: str, code: str) -> TokenSet
    async def refresh_token(refresh_token: str) -> TokenSet
    async def get_firebase_token() -> str
    
class TokenSet:
    access_token: str
    refresh_token: str
    expires_at: datetime
    firebase_token: Optional[str]
```

### 2. Device Controller

Управляет устройствами домофона.

```python
class DeviceController:
    async def open_door(device_id: str) -> bool
    async def accept_call(call_id: str) -> CallSession
    async def get_devices() -> List[Device]
    async def get_device_status(device_id: str) -> DeviceStatus
    
class Device:
    id: str
    name: str
    type: str
    online: bool
    
class CallSession:
    id: str
    device_id: str
    audio_url: str
    started_at: datetime
```

### 3. Stream Handler

Обрабатывает видео и аудио потоки.

```python
class StreamHandler:
    async def get_video_stream_url(device_id: str) -> str
    async def proxy_video_stream(source_url: str) -> StreamResponse
    async def get_audio_stream(call_id: str) -> AudioStream
    async def send_audio(call_id: str, audio_data: bytes) -> bool
    
class AudioStream:
    url: str
    codec: str
    sample_rate: int
```

### 4. Firebase Listener

Подписывается на уведомления Firebase.

```python
class FirebaseListener:
    async def subscribe(firebase_token: str, callback: Callable) -> None
    async def unsubscribe() -> None
    async def handle_message(message: dict) -> CallEvent
    
class CallEvent:
    call_id: str
    device_id: str
    timestamp: datetime
    snapshot_url: Optional[str]
```

### 5. Event Manager

Управляет событиями и историей.

```python
class EventManager:
    async def log_event(event: Event) -> None
    async def get_history(limit: int = 100) -> List[Event]
    async def notify_home_assistant(event: Event) -> None
    
class Event:
    id: str
    type: EventType  # call, door_open, auto_open
    device_id: str
    timestamp: datetime
    metadata: dict
```

### 6. Config Manager

Управляет конфигурацией и безопасным хранением.

```python
class ConfigManager:
    async def save_credentials(username: str, password: str) -> None
    async def load_credentials() -> Tuple[str, str]
    async def save_tokens(tokens: TokenSet) -> None
    async def load_tokens() -> Optional[TokenSet]
    def encrypt(data: str) -> str
    def decrypt(data: str) -> str
```

### 7. Home Assistant Integration API

REST API для взаимодействия с Home Assistant.

```python
# FastAPI endpoints
POST   /api/auth/login          # Initial login
POST   /api/auth/2fa            # Submit 2FA code
GET    /api/devices             # List devices
POST   /api/door/open           # Open door
GET    /api/stream/video/{id}   # Get video stream
POST   /api/call/accept         # Accept call
GET    /api/events              # Get event history
GET    /api/status              # Service status
```

## Data Models

### Configuration Storage

```yaml
# config.yaml (encrypted)
is74:
  username: "encrypted_username"
  password: "encrypted_password"
  
tokens:
  access_token: "encrypted_token"
  refresh_token: "encrypted_token"
  firebase_token: "encrypted_token"
  expires_at: "2024-12-31T23:59:59"
  
settings:
  auto_open_enabled: false
  auto_open_schedule:
    - days: ["monday", "friday"]
      time_start: "08:00"
      time_end: "18:00"
  log_level: "INFO"
  stream_quality: "high"
```

### Event Storage

```json
{
  "events": [
    {
      "id": "evt_123",
      "type": "call",
      "device_id": "dev_456",
      "timestamp": "2024-12-09T10:30:00Z",
      "metadata": {
        "snapshot_url": "https://...",
        "auto_opened": false
      }
    }
  ]
}
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*


### Property 1: Authentication request is sent
*For any* valid username and password, calling the login method should result in an HTTP request being sent to the IS74 API
**Validates: Requirements 1.1**

### Property 2: 2FA workflow completion
*For any* authentication session requiring 2FA, submitting a valid 2FA code should complete the authentication and return tokens
**Validates: Requirements 1.2**

### Property 3: Token persistence after authentication
*For any* successful authentication, both access token and refresh token should be present in secure storage
**Validates: Requirements 1.3**

### Property 4: Automatic token refresh
*For any* expired access token, the system should automatically attempt to refresh it using the refresh token before making API requests
**Validates: Requirements 1.4**

### Property 5: Firebase token request after auth
*For any* successful authentication, the system should request a Firebase token from the IS74 API
**Validates: Requirements 2.1**

### Property 6: Firebase token persistence
*For any* received Firebase token, it should be stored in secure storage for subsequent use
**Validates: Requirements 2.2**

### Property 7: Firebase token auto-refresh
*For any* expired Firebase token, the system should automatically request a new token
**Validates: Requirements 2.3**

### Property 8: Firebase retry with exponential backoff
*For any* failed Firebase token request, the system should retry with exponentially increasing delays up to 3 attempts
**Validates: Requirements 2.4**

### Property 9: Firebase subscription on startup
*For any* service startup with valid Firebase token, the system should subscribe to Firebase Cloud Messaging
**Validates: Requirements 3.1**

### Property 10: Call information extraction
*For any* Firebase message containing a call notification, the system should extract device ID, timestamp, and snapshot URL
**Validates: Requirements 3.2**

### Property 11: Call event forwarding to Home Assistant
*For any* received call notification, the system should send an event to Home Assistant with call details
**Validates: Requirements 3.3**

### Property 12: Door open command transmission
*For any* door open request from Home Assistant, the system should send the corresponding command to IS74 API
**Validates: Requirements 4.1**

### Property 13: Door status synchronization on success
*For any* successful door open command, the door lock status in Home Assistant should be updated to "unlocked"
**Validates: Requirements 4.2**

### Property 14: Error notification on door open failure
*For any* failed door open command, Home Assistant should receive an error notification with the failure reason
**Validates: Requirements 4.3**

### Property 15: Video stream URL retrieval
*For any* video stream request, the system should obtain a valid stream URL from IS74 API
**Validates: Requirements 5.1**

### Property 16: Stream format compatibility
*For any* provided video stream, it should be in RTSP or HLS format compatible with Home Assistant
**Validates: Requirements 5.2**

### Property 17: Stream cleanup on stop
*For any* active video stream, stopping the stream should properly close the connection and release resources
**Validates: Requirements 5.4**

### Property 18: Fallback image on stream failure
*For any* unavailable video stream, the system should notify Home Assistant and provide a static placeholder image
**Validates: Requirements 5.5**

### Property 19: Auto-open on call when enabled
*For any* incoming call when auto-open is enabled, the system should automatically send a door open command
**Validates: Requirements 6.1**

### Property 20: Conditional auto-open based on schedule
*For any* incoming call when auto-open is enabled with schedule conditions, the door should open only if the call time matches the schedule (day of week and time range)
**Validates: Requirements 6.2, 6.3**

### Property 21: Auto-open event logging
*For any* executed auto-open action, an event with timestamp should be recorded in the log
**Validates: Requirements 6.4**

### Property 22: Call acceptance command transmission
*For any* call acceptance request from Home Assistant, the system should send the accept command to IS74 API
**Validates: Requirements 7.1**

### Property 23: Audio session establishment
*For any* accepted call, the system should create a CallSession with audio connection details
**Validates: Requirements 7.2**

### Property 24: Call cleanup on termination
*For any* active call, terminating the call should close the audio connection and notify IS74 API
**Validates: Requirements 7.4**

### Property 25: Credential encryption with AES-256
*For any* saved credentials or tokens, they should be encrypted using AES-256 before storage
**Validates: Requirements 8.1**

### Property 26: Credential loading on startup
*For any* service startup, credentials should be loaded from secure storage during initialization
**Validates: Requirements 8.2**

### Property 27: Online status reporting
*For any* successful connection to an Intercom Device, the status in Home Assistant should be "online"
**Validates: Requirements 9.1**

### Property 28: Event recording with timestamp
*For any* system event (call, door open, etc.), an entry with timestamp should be added to Home Assistant history
**Validates: Requirements 9.3**

### Property 29: Logging system initialization
*For any* service startup, the logging system should be initialized with DEBUG, INFO, WARNING, and ERROR levels
**Validates: Requirements 10.1**

### Property 30: Error logging with stack trace
*For any* error occurrence, the log should contain detailed error information including the stack trace
**Validates: Requirements 10.2**

### Property 31: API request logging with data masking
*For any* API request, the request and response should be logged with sensitive data (passwords, tokens) masked
**Validates: Requirements 10.3**

### Property 32: OpenAPI documentation availability
*For any* service deployment, OpenAPI documentation should be available and include all API endpoints
**Validates: Requirements 10.4**

## Error Handling

### Authentication Errors

- **Invalid Credentials**: Return 401 with clear error message
- **2FA Required**: Return 202 with session_id for 2FA submission
- **2FA Invalid**: Return 401 with remaining attempts count
- **Rate Limited**: Return 429 with retry-after header (5 minutes after 3 failed attempts)
- **Token Expired**: Automatically attempt refresh, return 401 if refresh fails

### Device Control Errors

- **Device Offline**: Return 503 with device status information
- **Command Timeout**: Retry once, then return 504 with timeout details
- **Unauthorized Device**: Return 403 with device access information
- **Invalid Command**: Return 400 with validation error details

### Stream Errors

- **Stream Unavailable**: Return placeholder image and 503 status
- **Stream Timeout**: Attempt reconnection, return 504 after 3 failed attempts
- **Unsupported Format**: Convert stream format or return 415 with supported formats
- **Bandwidth Issues**: Reduce stream quality automatically

### Firebase Errors

- **Connection Lost**: Automatically reconnect with exponential backoff (1s, 2s, 4s, 8s, max 60s)
- **Invalid Token**: Request new Firebase token and resubscribe
- **Message Parse Error**: Log error and skip message, continue listening
- **Subscription Failed**: Retry subscription up to 3 times with 5s delay

### Storage Errors

- **Encryption Failed**: Log critical error and refuse to save unencrypted data
- **Decryption Failed**: Clear corrupted data and request re-authentication
- **Storage Full**: Log error and attempt cleanup of old events (keep last 1000)
- **Permission Denied**: Log critical error and notify user through Home Assistant

## Testing Strategy

### Unit Testing

Используем **pytest** для unit тестов. Unit тесты покрывают:

- Конкретные примеры корректного поведения компонентов
- Edge cases (пустые входные данные, граничные значения)
- Специфические сценарии обработки ошибок
- Интеграционные точки между модулями

Примеры unit тестов:
- Тест на блокировку после ровно 3 неудачных попыток авторизации (Requirements 1.5)
- Тест на переподключение к Firebase в течение 10 секунд (Requirements 3.4)
- Тест на автоматический возврат статуса замка через 5 секунд (Requirements 4.4)
- Тест на возврат ровно 100 последних событий (Requirements 9.4)
- Тест на обновление статуса на offline в течение 30 секунд (Requirements 9.2)

### Property-Based Testing

Используем **Hypothesis** для property-based тестов. Property тесты проверяют универсальные свойства на множестве входных данных.

**Конфигурация:**
- Минимум 100 итераций для каждого property теста
- Каждый property тест должен быть помечен комментарием в формате: `# Feature: is74-intercom-integration, Property {N}: {property_text}`
- Каждое correctness property из design документа реализуется ОДНИМ property-based тестом

**Стратегия генерации данных:**
- Генерация случайных учетных данных (username, password)
- Генерация случайных токенов (access, refresh, firebase)
- Генерация случайных Firebase сообщений с различными структурами
- Генерация случайных временных меток и расписаний для auto-open
- Генерация случайных device_id и call_id

**Примеры property тестов:**
- Property 1: Для любых валидных учетных данных должен отправляться запрос к API
- Property 10: Для любого Firebase сообщения с вызовом должны извлекаться все обязательные поля
- Property 20: Для любого времени вызова, auto-open должен срабатывать только если время попадает в расписание
- Property 25: Для любых сохраняемых данных они должны быть зашифрованы AES-256

### Integration Testing

- Тестирование взаимодействия с mock IS74 API
- Тестирование взаимодействия с mock Firebase
- Тестирование полного flow: авторизация → получение токенов → подписка → обработка вызова
- Тестирование Home Assistant integration через WebSocket

### Test Utilities

```python
# test_helpers.py
class MockIS74API:
    """Mock IS74 API для тестирования"""
    def setup_auth_response(success: bool, require_2fa: bool)
    def setup_device_response(devices: List[Device])
    def setup_stream_url(url: str)

class MockFirebase:
    """Mock Firebase для тестирования"""
    def send_call_notification(device_id: str, timestamp: datetime)
    def simulate_disconnect()

@pytest.fixture
def auth_manager():
    """Fixture для AuthManager с mock API"""
    return AuthManager(api_client=MockIS74API())

@pytest.fixture
def config_manager(tmp_path):
    """Fixture для ConfigManager с временным хранилищем"""
    return ConfigManager(storage_path=tmp_path)
```

## Implementation Notes

### Technology Stack

- **Backend Framework**: FastAPI 0.104+ (async support, OpenAPI auto-generation)
- **HTTP Client**: httpx (async HTTP requests)
- **Firebase**: firebase-messaging 0.3+ (real-time push notifications without Admin SDK)
- **Video Processing**: FFmpeg (stream conversion), python-ffmpeg wrapper
- **Encryption**: cryptography library (AES-256-GCM)
- **Testing**: pytest, pytest-asyncio, Hypothesis
- **Home Assistant**: Custom integration using homeassistant core APIs

### Security Considerations

1. **Credential Storage**: Use AES-256-GCM with key derived from system-specific salt
2. **Token Transmission**: Always use HTTPS for API communication
3. **Memory Safety**: Clear sensitive data from memory after use (use `memset` via ctypes)
4. **Input Validation**: Validate all inputs from Home Assistant and IS74 API
5. **Rate Limiting**: Implement rate limiting for API requests to prevent abuse

### Performance Considerations

1. **Async Operations**: Use asyncio for all I/O operations to prevent blocking
2. **Connection Pooling**: Reuse HTTP connections to IS74 API
3. **Stream Buffering**: Buffer video stream to handle network jitter
4. **Event Queue**: Use asyncio.Queue for event processing to prevent backpressure
5. **Caching**: Cache device list and status for 30 seconds to reduce API calls

### Deployment

```yaml
# docker-compose.yml
version: '3.8'
services:
  is74-integration:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./config:/app/config
      - ./data:/app/data
    environment:
      - LOG_LEVEL=INFO
      - ENCRYPTION_KEY=${ENCRYPTION_KEY}
    restart: unless-stopped
```

### Home Assistant Configuration

```yaml
# configuration.yaml
is74_intercom:
  host: "http://localhost:8000"
  scan_interval: 30
  
lock:
  - platform: is74_intercom
    name: "Front Door"
    
camera:
  - platform: is74_intercom
    name: "Intercom Camera"
    
binary_sensor:
  - platform: is74_intercom
    name: "Doorbell"
    device_class: occupancy
```

## Future Enhancements

1. **Multiple Devices**: Support for multiple intercom devices
2. **Video Recording**: Automatic recording of calls to local storage
3. **Face Recognition**: Integration with face recognition for auto-open
4. **Mobile App**: Companion mobile app for notifications
5. **Voice Assistant**: Integration with Alexa/Google Assistant
6. **Analytics**: Dashboard with call statistics and patterns
