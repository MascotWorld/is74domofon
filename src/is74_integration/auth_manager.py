"""Authentication manager for IS74 API with phone-based authentication."""

import uuid
import json
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict

from .api_client import IS74ApiClient, IS74ApiError

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)


@dataclass
class TokenSet:
    """Container for authentication tokens and metadata."""
    
    access_token: str
    user_id: int
    profile_id: int
    expires_at: datetime
    authid: Optional[str] = None
    firebase_token: Optional[str] = None
    firebase_expires_at: Optional[datetime] = None
    device_id: Optional[str] = None
    phone: Optional[str] = None  # Номер телефона для FCM регистрации
    
    def is_expired(self) -> bool:
        """Check if access token is expired."""
        return datetime.now() >= self.expires_at
    
    def expires_soon(self, threshold_seconds: int = 300) -> bool:
        """Check if token expires within threshold seconds."""
        return datetime.now() >= (self.expires_at - timedelta(seconds=threshold_seconds))
    
    def is_firebase_token_expired(self) -> bool:
        """Check if Firebase token is expired."""
        if not self.firebase_token or not self.firebase_expires_at:
            return True
        return datetime.now() >= self.firebase_expires_at
    
    def firebase_token_expires_soon(self, threshold_seconds: int = 300) -> bool:
        """Check if Firebase token expires within threshold seconds."""
        if not self.firebase_token or not self.firebase_expires_at:
            return True
        return datetime.now() >= (self.firebase_expires_at - timedelta(seconds=threshold_seconds))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "access_token": self.access_token,
            "user_id": self.user_id,
            "profile_id": self.profile_id,
            "expires_at": self.expires_at.isoformat(),
            "authid": self.authid,
            "firebase_token": self.firebase_token,
            "firebase_expires_at": self.firebase_expires_at.isoformat() if self.firebase_expires_at else None,
            "device_id": self.device_id,
            "phone": self.phone
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TokenSet":
        """Create TokenSet from dictionary."""
        return cls(
            access_token=data["access_token"],
            user_id=data["user_id"],
            profile_id=data["profile_id"],
            expires_at=datetime.fromisoformat(data["expires_at"]),
            authid=data.get("authid"),
            firebase_token=data.get("firebase_token"),
            firebase_expires_at=datetime.fromisoformat(data["firebase_expires_at"]) if data.get("firebase_expires_at") else None,
            device_id=data.get("device_id"),
            phone=data.get("phone")
        )


class AuthenticationError(Exception):
    """Exception raised for authentication failures."""
    pass


class RateLimitError(AuthenticationError):
    """Exception raised when rate limit is exceeded."""
    
    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after


class AuthManager:
    """
    Manages authentication with IS74 API using phone-based authentication.
    
    Implements three-step authentication flow:
    1. Request SMS code with phone number
    2. Verify code and get authid/user_id
    3. Get access token with authid/user_id
    
    Features:
    - Automatic token refresh
    - Rate limiting (3 attempts, 5 minute lockout)
    - Token persistence
    """
    
    MAX_FAILED_ATTEMPTS = 3
    LOCKOUT_DURATION_SECONDS = 300  # 5 minutes
    DEFAULT_TOKEN_FILE = "config/tokens.json"
    
    def __init__(self, api_client: IS74ApiClient, token_file: Optional[str] = None):
        """
        Initialize AuthManager.
        
        Args:
            api_client: IS74ApiClient instance for making API requests
            token_file: Optional path to token storage file (default: config/tokens.json)
        """
        self.api_client = api_client
        self.tokens: Optional[TokenSet] = None
        self._failed_attempts = 0
        self._lockout_until: Optional[datetime] = None
        self._auth_id: Optional[str] = None
        self._token_file = token_file or self.DEFAULT_TOKEN_FILE
        
        logger.info(f"AuthManager initialized with device_id={self.api_client.get_device_id()}")
        
        # Try to load saved tokens
        self.load_tokens()
    
    def _check_rate_limit(self) -> None:
        """
        Check if rate limit is active.
        
        Raises:
            RateLimitError: If currently in lockout period
        """
        if self._lockout_until and datetime.now() < self._lockout_until:
            remaining = int((self._lockout_until - datetime.now()).total_seconds())
            raise RateLimitError(
                f"Too many failed authentication attempts. Try again in {remaining} seconds.",
                retry_after=remaining
            )
    
    def _record_failed_attempt(self) -> None:
        """Record a failed authentication attempt and apply rate limiting if needed."""
        self._failed_attempts += 1
        logger.warning(f"Failed authentication attempt {self._failed_attempts}/{self.MAX_FAILED_ATTEMPTS}")
        
        if self._failed_attempts >= self.MAX_FAILED_ATTEMPTS:
            self._lockout_until = datetime.now() + timedelta(seconds=self.LOCKOUT_DURATION_SECONDS)
            logger.warning(f"Rate limit triggered. Locked out until {self._lockout_until}")
    
    def _reset_failed_attempts(self) -> None:
        """Reset failed attempt counter after successful authentication."""
        self._failed_attempts = 0
        self._lockout_until = None
        logger.debug("Failed attempt counter reset")
    
    async def request_auth_code(self, phone: str) -> bool:
        """
        Request SMS authentication code.
        
        Args:
            phone: Phone number (e.g., "9XXXXXXXXX")
        
        Returns:
            True if code was sent successfully
        
        Raises:
            RateLimitError: If rate limit is active
            AuthenticationError: If request fails
        """
        self._check_rate_limit()
        
        try:
            device_id = self.api_client.get_device_id()
            logger.info(f"Requesting auth code for phone with device_id={device_id}")
            response = await self.api_client.post(
                "/mobile/auth/get-confirm",
                json={
                    "deviceId": device_id,
                    "phone": phone
                }
            )
            
            # Store authId from response if present
            if isinstance(response, dict) and "authId" in response:
                self._auth_id = response["authId"]
                logger.info(f"Received authId: {self._auth_id}")
            
            logger.info("Auth code requested successfully")
            return True
            
        except IS74ApiError as e:
            logger.error(f"Failed to request auth code: {e}")
            self._record_failed_attempt()
            raise AuthenticationError(f"Failed to request auth code: {e}") from e
    
    async def verify_code(self, phone: str, code: str) -> Dict[str, Any]:
        """
        Verify SMS code and get authid/user_id.
        
        Args:
            phone: Phone number
            code: SMS verification code
        
        Returns:
            Dictionary containing authId and addresses list with USER_ID and ADDRESS
        
        Raises:
            RateLimitError: If rate limit is active
            AuthenticationError: If verification fails
        """
        self._check_rate_limit()
        
        try:
            logger.info("Verifying auth code")
            
            # Use authId from get-confirm response, or empty string if not available
            auth_id = self._auth_id or ""
            
            # Send as raw body (application/x-www-form-urlencoded format)
            body = f"phone={phone}&confirmCode={code}&authId"
            
            response = await self.api_client.post(
                "/mobile/auth/check-confirm",
                content=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            # Store authId from response for get-token call
            if isinstance(response, dict) and "authId" in response:
                self._auth_id = response["authId"]
                logger.info(f"Updated authId from check-confirm: {self._auth_id}")
            
            logger.info("Auth code verified successfully")
            return response
            
        except IS74ApiError as e:
            logger.error(f"Failed to verify auth code: {e}")
            self._record_failed_attempt()
            raise AuthenticationError(f"Failed to verify auth code: {e}") from e
    
    async def get_access_token(self, authid: str, user_id: int) -> TokenSet:
        """
        Get access token using authid and user_id.
        
        Args:
            authid: Authentication ID from verify_code response
            user_id: User ID from verify_code response
        
        Returns:
            TokenSet with access token and metadata
        
        Raises:
            RateLimitError: If rate limit is active
            AuthenticationError: If token request fails
        """
        self._check_rate_limit()
        
        try:
            logger.info("Requesting access token")
            
            # Send as form data (application/x-www-form-urlencoded)
            form_data = {
                "authId": authid,
                "userId": str(user_id),
                "uniqueDeviceId": self.api_client.get_device_id()
            }
            
            response = await self.api_client.post(
                "/mobile/auth/get-token",
                data=form_data  # Use 'data' instead of 'json' for form encoding
            )
            
            # Parse response
            # Expected format:
            # {
            #   "USER_ID": 16551914,
            #   "PROFILE_ID": 75376,
            #   "TOKEN": "66893c9d9171b546caf539a6cb2676db",
            #   "ACCESS_BEGIN": "2025-12-09 19:26:54",
            #   "ACCESS_END": "2026-12-09 19:26:54",
            #   ...
            # }
            
            access_token = response.get("TOKEN")
            user_id_response = response.get("USER_ID")
            profile_id = response.get("PROFILE_ID")
            access_end = response.get("ACCESS_END")
            
            if not all([access_token, user_id_response, profile_id, access_end]):
                raise AuthenticationError("Invalid token response: missing required fields")
            
            # Parse expiration time
            try:
                expires_at = datetime.strptime(access_end, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                # Fallback: set expiration to 1 year from now
                logger.warning(f"Could not parse ACCESS_END: {access_end}, using 1 year default")
                expires_at = datetime.now() + timedelta(days=365)
            
            # Create token set
            tokens = TokenSet(
                access_token=access_token,
                user_id=user_id_response,
                profile_id=profile_id,
                expires_at=expires_at,
                authid=authid,
                device_id=self.api_client.get_device_id()
            )
            
            # Store tokens and set in API client
            self.tokens = tokens
            self.api_client.set_auth_token(access_token)
            
            # Reset failed attempts on success
            self._reset_failed_attempts()
            
            # Save tokens to file
            self.save_tokens()
            
            logger.info(f"Access token obtained, expires at {expires_at}")
            return tokens
            
        except IS74ApiError as e:
            logger.error(f"Failed to get access token: {e}")
            self._record_failed_attempt()
            raise AuthenticationError(f"Failed to get access token: {e}") from e
    
    async def login(self, phone: str, code: str, user_id: Optional[int] = None) -> TokenSet:
        """
        Complete authentication flow: verify code and get token.
        
        This is a convenience method that combines verify_code and get_access_token.
        If user_id is not provided and multiple addresses are returned, uses the first one.
        
        Args:
            phone: Phone number
            code: SMS verification code
            user_id: Optional user_id to use (if multiple addresses available)
        
        Returns:
            TokenSet with access token and metadata
        
        Raises:
            RateLimitError: If rate limit is active
            AuthenticationError: If authentication fails
        """
        # Verify code
        verify_response = await self.verify_code(phone, code)
        
        # Extract authId and user_id from response
        # Expected format: {"authId": "...", "addresses": [{"USER_ID": "...", "ADDRESS": "..."}]}
        if not isinstance(verify_response, dict):
            raise AuthenticationError("Invalid verify response format: expected dictionary")
        
        authid = verify_response.get("authId")
        addresses = verify_response.get("addresses", [])
        
        if not authid:
            raise AuthenticationError("Invalid verify response: missing authId")
        
        if not addresses or len(addresses) == 0:
            raise AuthenticationError("No addresses found in verify response")
        
        # Select user_id
        if user_id is not None:
            # Find matching address by USER_ID
            entry = next((addr for addr in addresses if int(addr.get("USER_ID", 0)) == user_id), None)
            if not entry:
                raise AuthenticationError(f"No address found for user_id {user_id}")
            selected_user_id = int(entry["USER_ID"])
        else:
            # Use first address
            selected_user_id = int(addresses[0]["USER_ID"])
        
        logger.info(f"Selected user_id: {selected_user_id} from {len(addresses)} addresses")
        
        # Get access token
        tokens = await self.get_access_token(authid, selected_user_id)
        
        # Сохраняем номер телефона для FCM регистрации
        tokens.phone = phone
        self.save_tokens()
        
        # Get Firebase token for push notifications
        try:
            logger.info("Requesting Firebase token for push notifications")
            # Generate Firebase instance ID and token
            import uuid
            firebase_instance_id = str(uuid.uuid4())
            firebase_instance_token = str(uuid.uuid4())
            
            await self.get_firebase_token(
                firebase_instance_id=firebase_instance_id,
                firebase_instance_token=firebase_instance_token
            )
            logger.info("Firebase token obtained successfully")
        except Exception as e:
            # Don't fail login if Firebase token fails
            logger.warning(f"Failed to get Firebase token (non-critical): {e}")
        
        return tokens
    
    async def start_firebase_listener_if_needed(self, firebase_listener) -> bool:
        """
        Start Firebase listener if authenticated and not already running.
        
        Args:
            firebase_listener: FirebaseListener instance
        
        Returns:
            True if listener was started, False otherwise
        """
        if not self.is_authenticated():
            logger.debug("Not authenticated, cannot start Firebase listener")
            return False
        
        if firebase_listener and firebase_listener.is_running():
            logger.debug("Firebase listener already running")
            return False
        
        tokens = self.get_tokens()
        if not tokens or not tokens.firebase_token:
            logger.warning("No Firebase token available")
            return False
        
        try:
            await firebase_listener.start(
                fcm_token=tokens.firebase_token,
                sender_id="361180765175",
                app_id="1:361180765175:android:9c0fafffa6c60062"
            )
            logger.info("Firebase listener started successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to start Firebase listener: {e}", exc_info=True)
            return False
    
    async def refresh_token_if_needed(self) -> bool:
        """
        Check if token needs refresh and refresh if necessary.
        
        Returns:
            True if token was refreshed, False if refresh not needed
        
        Raises:
            AuthenticationError: If no tokens available or refresh fails
        """
        if not self.tokens:
            raise AuthenticationError("No tokens available to refresh")
        
        if not self.tokens.expires_soon():
            logger.debug("Token does not need refresh yet")
            return False
        
        logger.info("Token expires soon, refreshing...")
        
        # For IS74 API, we need to re-authenticate with authid/user_id
        # The API doesn't have a traditional refresh token endpoint
        if not self.tokens.authid:
            raise AuthenticationError("Cannot refresh token: authid not available")
        
        try:
            new_tokens = await self.get_access_token(
                self.tokens.authid,
                self.tokens.user_id
            )
            logger.info("Token refreshed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
            raise AuthenticationError(f"Failed to refresh token: {e}") from e
    
    def get_tokens(self) -> Optional[TokenSet]:
        """
        Get current token set.
        
        Returns:
            Current TokenSet or None if not authenticated
        """
        return self.tokens
    
    def set_tokens(self, tokens: TokenSet, save: bool = True) -> None:
        """
        Set token set (e.g., loaded from storage).
        
        Args:
            tokens: TokenSet to set
            save: Whether to save tokens to file (default: True)
        """
        self.tokens = tokens
        self.api_client.set_auth_token(tokens.access_token)
        
        if save:
            self.save_tokens()
        
        logger.info(f"Tokens set, expires at {tokens.expires_at}")
    
    def is_authenticated(self) -> bool:
        """
        Check if currently authenticated with valid token.
        
        Returns:
            True if authenticated and token not expired
        """
        return self.tokens is not None and not self.tokens.is_expired()
    
    def clear_tokens(self) -> None:
        """Clear stored tokens and authentication state."""
        self.tokens = None
        self.api_client.clear_auth_token()
        self.delete_saved_tokens()
        logger.info("Tokens cleared")
    
    async def get_firebase_config(self) -> Dict[str, Any]:
        """
        Get Firebase configuration from IS74 API.
        
        Returns:
            Dictionary containing Firebase configuration (groups, lawStatus, profileRole)
        
        Raises:
            AuthenticationError: If not authenticated or request fails
        """
        if not self.is_authenticated():
            raise AuthenticationError("Must be authenticated to get Firebase config")
        
        try:
            logger.info("Requesting Firebase config")
            response = await self.api_client.get("/mobile/config/get-firebase-config")
            logger.info("Firebase config retrieved successfully")
            return response
            
        except IS74ApiError as e:
            logger.error(f"Failed to get Firebase config: {e}")
            raise AuthenticationError(f"Failed to get Firebase config: {e}") from e
    
    async def get_firebase_token(
        self,
        firebase_instance_id: str,
        firebase_instance_token: str,
        device_info: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Get Firebase token for push notifications with retry logic.
        
        Implements exponential backoff retry (up to 3 attempts) as per Requirements 2.4.
        
        Args:
            firebase_instance_id: Firebase app instance ID
            firebase_instance_token: Firebase app instance token
            device_info: Optional device information for analytics
        
        Returns:
            Firebase token string
        
        Raises:
            AuthenticationError: If not authenticated or all retry attempts fail
        """
        if not self.is_authenticated():
            raise AuthenticationError("Must be authenticated to get Firebase token")
        
        # Build device registration payload
        payload = {
            "appVersion": "1.30.1-GMS-b3c075fbb",
            "firstOpenTime": datetime.now().isoformat() + "Z",
            "timeZone": "GMT",
            "appInstanceIdToken": firebase_instance_token,
            "languageCode": "en-US",
            "appBuild": "2024040812",
            "appInstanceId": firebase_instance_id,
            "countryCode": "US",
            "analyticsUserProperties": {
                "first_install_time": datetime.now().strftime("%Y-%m-%d"),
                "app_version": "1.30.1",
                "profile_id": str(self.tokens.profile_id),
                "build_number": "2024040812",
                "profile_role_id": "1",
                "abonent_id": str(self.tokens.user_id),
                "lawStatus": "fizik",
            },
            "appId": "1:361180765175:android:9c0fafffa6c60062",
            "platformVersion": "28",
            "sdkVersion": "21.5.0",
            "packageName": "com.intersvyaz.lk"
        }
        
        # Merge custom device info if provided
        if device_info:
            payload["analyticsUserProperties"].update(device_info)
        
        # Retry logic with exponential backoff (up to 3 attempts)
        max_attempts = 3
        base_delay = 1  # Start with 1 second
        
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"Requesting Firebase token (attempt {attempt}/{max_attempts})")
                
                # For IS74 integration, we use the firebase_instance_token as the FCM token
                # The actual Firebase registration happens on the client side (mobile app)
                # Here we just store the token for later use with Firebase listener
                firebase_token = firebase_instance_token
                
                logger.debug(f"Using Firebase instance token as FCM token")
                
                # Store Firebase token in TokenSet
                if self.tokens:
                    self.tokens.firebase_token = firebase_token
                    # Firebase tokens typically expire after 90 days
                    self.tokens.firebase_expires_at = datetime.now() + timedelta(days=90)
                    logger.info(f"Storing Firebase token: {firebase_token[:20]}... (expires: {self.tokens.firebase_expires_at})")
                    # Save updated tokens
                    saved = self.save_tokens()
                    if saved:
                        logger.info("Firebase token saved to file successfully")
                    else:
                        logger.warning("Failed to save Firebase token to file")
                
                logger.info("Firebase token obtained successfully")
                return firebase_token
                
            except IS74ApiError as e:
                logger.warning(f"Firebase token request failed (attempt {attempt}/{max_attempts}): {e}")
                
                # If this was the last attempt, raise the error
                if attempt == max_attempts:
                    logger.error("All Firebase token retry attempts failed")
                    raise AuthenticationError(f"Failed to get Firebase token after {max_attempts} attempts: {e}") from e
                
                # Calculate exponential backoff delay: 1s, 2s, 4s
                delay = base_delay * (2 ** (attempt - 1))
                logger.info(f"Retrying in {delay} seconds...")
                
                # Wait before retrying
                import asyncio
                await asyncio.sleep(delay)
        
        # This should never be reached due to the raise in the loop
        raise AuthenticationError("Failed to get Firebase token")
    
    async def refresh_firebase_token_if_needed(
        self,
        firebase_instance_id: str,
        firebase_instance_token: str,
        device_info: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Check if Firebase token needs refresh and refresh if necessary.
        
        Args:
            firebase_instance_id: Firebase app instance ID
            firebase_instance_token: Firebase app instance token
            device_info: Optional device information for analytics
        
        Returns:
            True if token was refreshed, False if refresh not needed
        
        Raises:
            AuthenticationError: If not authenticated or refresh fails
        """
        if not self.tokens:
            raise AuthenticationError("No tokens available")
        
        if not self.tokens.firebase_token_expires_soon():
            logger.debug("Firebase token does not need refresh yet")
            return False
        
        logger.info("Firebase token expires soon, refreshing...")
        
        try:
            await self.get_firebase_token(
                firebase_instance_id,
                firebase_instance_token,
                device_info
            )
            logger.info("Firebase token refreshed successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to refresh Firebase token: {e}")
            raise AuthenticationError(f"Failed to refresh Firebase token: {e}") from e
    
    def save_tokens(self) -> bool:
        """
        Save tokens to file for persistence across restarts.
        
        Returns:
            True if tokens were saved successfully, False otherwise
        """
        if not self.tokens:
            logger.debug("No tokens to save")
            return False
        
        try:
            # Create directory if it doesn't exist
            token_path = Path(self._token_file)
            token_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Save tokens to file
            with open(token_path, 'w') as f:
                json.dump(self.tokens.to_dict(), f, indent=2)
            
            logger.info(f"Tokens saved to {self._token_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save tokens: {e}", exc_info=True)
            return False
    
    def load_tokens(self) -> bool:
        """
        Load tokens from file.
        
        Returns:
            True if tokens were loaded successfully, False otherwise
        """
        try:
            token_path = Path(self._token_file)
            
            if not token_path.exists():
                logger.debug(f"Token file not found: {self._token_file}")
                return False
            
            # Load tokens from file
            with open(token_path, 'r') as f:
                data = json.load(f)
            
            # Create TokenSet from data
            tokens = TokenSet.from_dict(data)
            
            # If tokens have a device_id, update API client to use it
            if tokens.device_id and tokens.device_id != self.api_client.get_device_id():
                logger.info(f"Updating API client to use saved device_id: {tokens.device_id}")
                self.api_client._device_id = tokens.device_id
                self.api_client.client.headers["X-Device-Id"] = tokens.device_id
            
            # Check if tokens are expired
            if tokens.is_expired():
                logger.warning("Loaded tokens are expired")
                # Try to refresh if we have authid
                if tokens.authid:
                    logger.info("Will attempt to refresh expired tokens")
                    self.tokens = tokens
                    # Note: Actual refresh needs to be done asynchronously by caller
                else:
                    logger.warning("Cannot refresh expired tokens without authid")
                    return False
            else:
                # Set tokens and update API client (without saving again)
                self.set_tokens(tokens, save=False)
                logger.info(f"Tokens loaded from {self._token_file}, expires at {tokens.expires_at}")
                return True
            
        except Exception as e:
            logger.error(f"Failed to load tokens: {e}", exc_info=True)
            return False
    
    def delete_saved_tokens(self) -> bool:
        """
        Delete saved tokens file.
        
        Returns:
            True if file was deleted, False otherwise
        """
        try:
            token_path = Path(self._token_file)
            
            if token_path.exists():
                token_path.unlink()
                logger.info(f"Deleted token file: {self._token_file}")
                return True
            else:
                logger.debug(f"Token file does not exist: {self._token_file}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to delete token file: {e}", exc_info=True)
            return False
