"""
FCM Push Listener для IS74 домофона.

Флоу:
1. initialize_fcm() - регистрация в FCM, сохранение fcm_creds.json, возврат device_id (android_id)
2. Авторизация (через auth_manager) с использованием device_id
3. start_push_service() - запуск FCM listener + регистрация пушей в бекендах
"""
import asyncio
import json
import logging
from pathlib import Path
from typing import Optional, Tuple

import aiohttp
from firebase_messaging import FcmPushClient, FcmRegisterConfig

# ---------- ЛОГИ ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("fcm-listener")

# Уменьшаем спам от firebase_messaging (переподключения - норма)
logging.getLogger("firebase_messaging").setLevel(logging.WARNING)

# ---------- ПУТИ ----------
CREDS_FILE = Path("config/fcm_creds.json")
TOKENS_FILE = Path("config/tokens.json")

# ---------- КОНСТАНТЫ ----------
FCM_PROJECT_NAME = "intersvyazlk"
FCM_APP_ID = "1:361180765175:android:9c0fafffa6c60062"
FCM_API_KEY = "AIzaSyCWGN-JHGm50OpAo3-2gR7l1kCQIEs7YO4"
FCM_PROJECT_NUMBER = "361180765175"
DEVICE_MODEL = "Google Pixel 10"

# Глобальный FCM клиент
_fcm_client: Optional[FcmPushClient] = None
_fcm_token: Optional[str] = None


# ============================================================================
# CALLBACKS
# ============================================================================

def on_notification(obj, notification, data_message):
    """Обработчик входящих пуш-уведомлений."""
    log.info("=" * 50)
    log.info("📞 ВХОДЯЩИЙ ВЫЗОВ / УВЕДОМЛЕНИЕ!")
    log.info(f"NOTIFICATION: {notification}")
    log.info(f"DATA: {data_message}")
    
    if obj:
        log.info(f"OBJ: {obj}")
        if hasattr(obj, '__dict__'):
            log.info(f"OBJ.__dict__: {obj.__dict__}")
    
    log.info("=" * 50)
    
    # TODO: Добавить логику автооткрытия двери


def on_credentials_updated(creds):
    """Сохраняем обновлённые credentials FCM."""
    try:
        CREDS_FILE.write_text(json.dumps(creds, indent=2))
        log.info("✓ FCM credentials сохранены")
    except Exception as e:
        log.error(f"Ошибка сохранения FCM credentials: {e}")


# ============================================================================
# ФАЙЛОВЫЕ ОПЕРАЦИИ
# ============================================================================

def load_fcm_credentials() -> Optional[dict]:
    """Загружаем сохранённые FCM credentials."""
    if CREDS_FILE.exists():
        try:
            return json.loads(CREDS_FILE.read_text())
        except Exception:
            log.warning("Не удалось загрузить FCM credentials")
    return None


def get_android_id_from_fcm_creds() -> Optional[str]:
    """Получаем android_id из fcm_creds.json -> gcm.android_id"""
    creds = load_fcm_credentials()
    if creds:
        android_id = creds.get("gcm", {}).get("android_id")
        if android_id:
            return str(android_id)
    return None


def load_tokens() -> Optional[dict]:
    """Загружаем tokens.json."""
    if TOKENS_FILE.exists():
        try:
            return json.loads(TOKENS_FILE.read_text())
        except Exception:
            pass
    return None


def save_tokens(data: dict) -> bool:
    """Сохраняем данные в tokens.json."""
    try:
        TOKENS_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKENS_FILE.write_text(json.dumps(data, indent=2))
        return True
    except Exception as e:
        log.error(f"Ошибка сохранения tokens.json: {e}")
        return False


def save_device_id(device_id: str) -> bool:
    """Сохраняем device_id в tokens.json (перед авторизацией)."""
    tokens = load_tokens() or {}
    tokens["device_id"] = device_id
    if save_tokens(tokens):
        log.info(f"✓ device_id сохранён: {device_id}")
        return True
    return False


def is_authenticated() -> bool:
    """Проверяем есть ли access_token в tokens.json."""
    tokens = load_tokens()
    return bool(tokens and tokens.get("access_token"))


# ============================================================================
# ИНИЦИАЛИЗАЦИЯ FCM (ШАГ 1 - ДО АВТОРИЗАЦИИ)
# ============================================================================

async def initialize_fcm() -> str:
    """
    Шаг 1: Инициализация FCM.
    
    - Регистрируемся в FCM (если ещё не зарегистрированы)
    - Сохраняем fcm_creds.json
    - Сохраняем device_id (android_id) в tokens.json
    
    Returns:
        device_id (android_id) для использования при авторизации
    """
    global _fcm_client, _fcm_token
    
    log.info("=" * 60)
    log.info("📱 Инициализация FCM...")
    log.info("=" * 60)
    
    # Загружаем существующие credentials
    creds = load_fcm_credentials()
    
    # Конфигурация FCM
    fcm_config = FcmRegisterConfig(
        FCM_PROJECT_NAME,
        FCM_APP_ID,
        FCM_API_KEY,
        FCM_PROJECT_NUMBER
    )
    
    # Создаём FCM клиент
    _fcm_client = FcmPushClient(
        on_notification,
        fcm_config,
        creds,
        on_credentials_updated
    )
    
    # Регистрация в FCM
    log.info("📝 Регистрация в FCM...")
    _fcm_token = await _fcm_client.checkin_or_register()
    log.info(f"✓ FCM TOKEN: {_fcm_token}")
    
    # Получаем android_id как device_id
    device_id = get_android_id_from_fcm_creds()
    if not device_id:
        raise RuntimeError("Не удалось получить android_id из FCM credentials")
    
    # Сохраняем device_id в tokens.json
    save_device_id(device_id)
    
    log.info(f"✓ device_id (android_id): {device_id}")
    log.info("=" * 60)
    
    return device_id


def get_device_id() -> Optional[str]:
    """Получаем device_id (сначала из fcm_creds, потом из tokens)."""
    device_id = get_android_id_from_fcm_creds()
    if device_id:
        return device_id
    
    tokens = load_tokens()
    if tokens:
        return tokens.get("device_id")
    
    return None


# ============================================================================
# РЕГИСТРАЦИЯ ПУШЕЙ В БЕКЕНДАХ (ШАГ 3 - ПОСЛЕ АВТОРИЗАЦИИ)
# ============================================================================

async def crm_auth_lk(
    session: aiohttp.ClientSession,
    access_token: str,
    device_id: str,
    profile_id: int,
    user_id: int,
) -> str:
    """Получаем JWT для td-crm."""
    url = "https://td-crm.is74.ru/api/auth-lk"
    headers = {
        "Authorization": "Bearer",
        "Platform": "Android",
        "User-Agent": "4.12.0 com.intersvyaz.lk/1.30.1.2024040812",
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
        log.info(f"✓ JWT для td-crm получен")
        return jwt


async def crm_register_device(
    session: aiohttp.ClientSession,
    crm_jwt: str,
    fcm_token: str,
    device_id: str,
    profile_id: int,
    user_id: int,
) -> None:
    """Регистрируем устройство в td-crm (PUT)."""
    url = "https://td-crm.is74.ru/api/user-device"
    headers = {
        "Authorization": f"Bearer {crm_jwt}",
        "Platform": "Android",
        "User-Agent": "4.12.0 com.intersvyaz.lk/1.30.1.2024040812",
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
        log.info("✓ Устройство зарегистрировано в td-crm")


async def register_push_token(fcm_token: str) -> bool:
    """
    Регистрируем FCM токен в бекендах IS74.
    
    Требует: авторизация уже выполнена (есть access_token в tokens.json)
    """
    tokens = load_tokens()
    if not tokens or not tokens.get("access_token"):
        raise RuntimeError("Требуется авторизация (нет access_token)")
    
    access_token = tokens["access_token"]
    profile_id = tokens.get("profile_id")
    user_id = tokens.get("user_id")
    device_id = get_device_id()
    phone = tokens.get("phone")
    
    if not all([profile_id, user_id, device_id]):
        raise RuntimeError("Неполные данные авторизации")
    
    log.info("=" * 50)
    log.info("📤 Регистрация пушей в бекендах...")
    log.info(f"  device_id: {device_id}")
    log.info(f"  phone: {phone}")
    log.info(f"  fcm_token: {fcm_token[:40]}...")
    log.info("=" * 50)
    
    async with aiohttp.ClientSession() as session:
        # 1. Получаем JWT для td-crm
        crm_jwt = await crm_auth_lk(
            session,
            access_token=access_token,
            device_id=device_id,
            profile_id=profile_id,
            user_id=user_id,
        )
        
        # 2. Регистрируем устройство в td-crm
        await crm_register_device(
            session,
            crm_jwt=crm_jwt,
            fcm_token=fcm_token,
            device_id=device_id,
            profile_id=profile_id,
            user_id=user_id,
        )
    
    log.info("✓ Пуши зарегистрированы!")
    return True


# ============================================================================
# ЗАПУСК PUSH СЕРВИСА (ШАГ 3 - ПОСЛЕ АВТОРИЗАЦИИ)
# ============================================================================

async def start_push_service() -> None:
    """
    Шаг 3: Запуск Push сервиса (после авторизации).
    
    - Инициализирует FCM если ещё не инициализирован
    - Регистрирует пуши в бекендах IS74
    - Запускает слушатель
    """
    global _fcm_client, _fcm_token
    
    # Проверяем авторизацию
    if not is_authenticated():
        raise RuntimeError("Требуется авторизация перед запуском Push сервиса")
    
    log.info("=" * 60)
    log.info("🚀 Запуск Push сервиса...")
    log.info("=" * 60)
    
    # Если FCM ещё не инициализирован - инициализируем
    if not _fcm_client or not _fcm_token:
        await initialize_fcm()
    
    # Регистрируем пуши в бекендах
    try:
        await register_push_token(_fcm_token)
    except Exception as e:
        log.error(f"❌ Ошибка регистрации пушей: {e}")
        log.warning("Продолжаем - пуши могут не приходить")
    
    # Запускаем слушатель
    log.info("👂 Запуск слушателя...")
    await _fcm_client.start()
    log.info("✓ Push сервис запущен! Ожидаем входящие вызовы...")
    
    # Бесконечный цикл
    try:
        while True:
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        log.info("Push сервис остановлен")
        raise


# ============================================================================
# ПОЛНЫЙ ФЛОУ (ДЛЯ УЖЕ АВТОРИЗОВАННЫХ)
# ============================================================================

async def run_fcm_listener():
    """
    Полный запуск для уже авторизованных пользователей.
    
    1. Инициализация FCM
    2. Регистрация пушей
    3. Запуск слушателя
    """
    log.info("=" * 60)
    log.info("🏠 IS74 Домофон - FCM Listener")
    log.info("=" * 60)
    
    # Проверяем авторизацию
    if not is_authenticated():
        log.error("❌ Требуется авторизация!")
        log.info("Выполните авторизацию через API: POST /auth/login, POST /auth/verify")
        return
    
    # Запускаем push сервис
    await start_push_service()


# ============================================================================
# УТИЛИТЫ
# ============================================================================

async def test_fcm_init():
    """Тест инициализации FCM (без авторизации)."""
    device_id = await initialize_fcm()
    log.info(f"FCM инициализирован, device_id: {device_id}")
    log.info("Теперь выполните авторизацию и запустите start_push_service()")


if __name__ == "__main__":
    asyncio.run(run_fcm_listener())
