"""Stream handler for IS74 camera video streams."""

from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from urllib.parse import urlencode

from .api_client import IS74ApiClient, IS74ApiError

import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.WARNING)


@dataclass
class Camera:
    """Represents a camera device."""
    
    uuid: str
    name: str
    status: str  # online/offline
    has_stream: bool
    address: Optional[str] = None
    building_id: Optional[int] = None
    entrance: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None
    
    @property
    def is_online(self) -> bool:
        """Check if camera is online."""
        return self.status.lower() == "online"


@dataclass
class VideoStream:
    """Represents a video stream."""
    
    camera_uuid: str
    stream_url: str
    format: str  # HLS, RTSP, etc.
    snapshot_url: Optional[str] = None
    is_available: bool = True
    
    def is_hls(self) -> bool:
        """Check if stream is HLS format."""
        return self.format.upper() == "HLS"


class StreamError(Exception):
    """Exception raised for stream handling failures."""
    
    def __init__(self, message: str, camera_uuid: Optional[str] = None, error_code: Optional[str] = None):
        self.message = message
        self.camera_uuid = camera_uuid
        self.error_code = error_code
        super().__init__(self.message)


class StreamHandler:
    """
    Handles video streams from IS74 cameras.
    
    Features:
    - Get list of cameras with UUIDs
    - Retrieve video stream URLs (HLS format)
    - Parse HLS stream URLs from cdn.cams.is74.ru
    - Stream format validation
    - Stream cleanup and resource management
    - Fallback placeholder image for unavailable streams
    """
    
    # CDN base URL for camera streams
    CDN_BASE_URL = "https://cdn.cams.is74.ru"
    
    # Placeholder image URL for unavailable streams
    PLACEHOLDER_IMAGE_URL = "data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjQwIiBoZWlnaHQ9IjQ4MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iNjQwIiBoZWlnaHQ9IjQ4MCIgZmlsbD0iIzMzMyIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMjQiIGZpbGw9IiNmZmYiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGR5PSIuM2VtIj5DYW1lcmEgVW5hdmFpbGFibGU8L3RleHQ+PC9zdmc+"
    
    def __init__(self, api_client: IS74ApiClient):
        """
        Initialize StreamHandler.
        
        Args:
            api_client: IS74ApiClient instance for making API requests
        """
        self.api_client = api_client
        self._active_streams: Dict[str, VideoStream] = {}
        
        logger.info("StreamHandler initialized")
    
    async def get_cameras(self) -> List[Camera]:
        """
        Get list of cameras with UUIDs.
        
        Implements GET /api/cameras endpoint.
        
        Returns:
            List of Camera objects
        
        Raises:
            StreamError: If request fails
        """
        try:
            logger.info("Fetching camera list")
            # Use the correct camera API endpoint from Postman collection
            # Note: The API client base URL is api.is74.ru, but cameras are on cams.is74.ru
            # We need to use the full URL for camera endpoints
            response = await self.api_client.get("https://cams.is74.ru/api/self-cams-with-group")
            
            # Log raw response for debugging
            import json
            logger.info(f"Raw camera API response: {json.dumps(response, indent=2, default=str)[:2000]}")
            
            logger.info(f"Camera API response type: {type(response)}")
            if isinstance(response, dict):
                logger.info(f"Camera API response keys: {list(response.keys())}")
                # Log first level of structure
                for key, value in response.items():
                    if isinstance(value, list):
                        logger.info(f"  {key}: list with {len(value)} items")
                        if len(value) > 0:
                            logger.info(f"    First item type: {type(value[0])}")
                            if isinstance(value[0], dict):
                                logger.info(f"    First item keys: {list(value[0].keys())}")
                    elif isinstance(value, dict):
                        logger.info(f"  {key}: dict with keys {list(value.keys())[:5]}")
                    else:
                        logger.info(f"  {key}: {type(value).__name__}")
            
            # Parse response into Camera objects
            cameras = []
            
            # Response is a list of groups, each containing cameras
            if isinstance(response, list):
                # Iterate through groups and extract cameras
                for group in response:
                    if isinstance(group, dict) and "cameras" in group:
                        group_cameras = group.get("cameras", [])
                        logger.info(f"Found {len(group_cameras)} cameras in group '{group.get('groupName', 'Unknown')}'")
                        
                        for camera_item in group_cameras:
                            camera = self._parse_camera(camera_item)
                            if camera.uuid:
                                cameras.append(camera)
                            else:
                                logger.warning(f"Skipping camera without UUID: {camera_item}")
                
                logger.info(f"Total cameras found: {len(cameras)}")
                return cameras
            
            # Fallback: old format (flat list or dict with cameras key)
            elif isinstance(response, dict):
                camera_list = (response.get("cameras") or 
                              response.get("items") or 
                              response.get("data") or 
                              [])
            else:
                camera_list = []
            
            logger.info(f"Found {len(camera_list)} cameras in response (fallback parsing)")
            
            for item in camera_list:
                camera = self._parse_camera(item)
                if not camera.uuid:
                    logger.warning(f"Skipping camera without UUID: {item}")
                    continue
                cameras.append(camera)
            
            logger.info(f"Retrieved {len(cameras)} cameras")
            return cameras
            
        except IS74ApiError as e:
            logger.error(f"Failed to get camera list: {e}")
            raise StreamError(f"Failed to get camera list: {e}") from e
    
    def _parse_camera(self, item: Dict[str, Any]) -> Camera:
        """
        Parse camera data from API response.
        
        Args:
            item: Camera data dictionary from API
            
        Returns:
            Camera object
        """
        # Extract camera information - try various field name formats
        uuid = (item.get("UUID") or 
               item.get("uuid") or 
               item.get("ID") or
               item.get("id") or 
               item.get("cam_id"))
        
        name = (item.get("NAME") or 
               item.get("name") or 
               item.get("title") or 
               item.get("address") or 
               item.get("ADDRESS") or 
               "Unknown Camera")
        
        # Check online status from ACCESS.LIVE.STATUS
        access = item.get("ACCESS", {})
        live_access = access.get("LIVE", {}) if isinstance(access, dict) else {}
        live_status = live_access.get("STATUS") if isinstance(live_access, dict) else None
        
        # Also check other status fields
        is_online = item.get("IS_ONLINE") or item.get("is_online") or item.get("isOnline")
        
        if live_status is not None:
            # ACCESS.LIVE.STATUS is the authoritative source
            status = "online" if live_status else "offline"
        elif is_online is not None:
            status = "online" if is_online else "offline"
        else:
            status_text = item.get("STATUS_TEXT") or item.get("status") or item.get("STATUS")
            if status_text == "OK" or status_text == "online":
                status = "online"
            else:
                status = status_text or "unknown"
        
        # Check if camera has stream capability
        # Camera has stream if it has HLS or REALTIME_HLS URLs
        has_hls = bool(item.get("HLS") or item.get("REALTIME_HLS"))
        has_stream = bool(
            has_hls or
            item.get("HAS_STREAM") or
            item.get("has_stream") or 
            item.get("hasStream") or 
            item.get("STREAM_URL") or
            item.get("stream_url")
        )
        
        address = item.get("ADDRESS") or item.get("address")
        building_id = item.get("BUILDING_ID") or item.get("building_id") or item.get("buildingId")
        entrance = item.get("ENTRANCE") or item.get("entrance") or item.get("PORCH")
        
        # Convert UUID to string if it's not already
        if uuid is not None:
            uuid = str(uuid)
        
        return Camera(
            uuid=uuid,
            name=name,
            status=status,
            has_stream=has_stream,
            address=address,
            building_id=building_id,
            entrance=entrance,
            raw_data=item
        )
    
    async def get_camera_by_uuid(self, camera_uuid: str) -> Optional[Camera]:
        """
        Get camera by UUID.
        
        Args:
            camera_uuid: Camera UUID
        
        Returns:
            Camera object or None if not found
        """
        cameras = await self.get_cameras()
        return next((c for c in cameras if c.uuid == camera_uuid), None)
    
    def _build_hls_stream_url(self, camera: Camera, access_token: str, realtime: bool = True) -> str:
        """
        Build HLS stream URL for camera using data from API response.
        
        Args:
            camera: Camera object with raw_data
            access_token: Access token for authentication (not used, URLs already include token)
            realtime: Enable low latency mode (default: True)
        
        Returns:
            HLS stream URL
        """
        # Try to get direct HLS URL from camera raw_data MEDIA object
        raw_data = camera.raw_data or {}
        media = raw_data.get("MEDIA", {})
        
        if isinstance(media, dict):
            hls_media = media.get("HLS", {})
            if isinstance(hls_media, dict):
                live_hls = hls_media.get("LIVE", {})
                if isinstance(live_hls, dict):
                    # Prefer LOW_LATENCY for better real-time experience
                    if realtime:
                        direct_url = live_hls.get("LOW_LATENCY") or live_hls.get("MAIN")
                    else:
                        direct_url = live_hls.get("MAIN")
                    
                    if direct_url:
                        logger.debug(f"Using direct HLS URL from MEDIA object (realtime={realtime}): {direct_url[:100]}...")
                        return direct_url
        
        # Fallback: try old format with relative paths
        if realtime:
            hls_path = raw_data.get("REALTIME_HLS") or raw_data.get("HLS")
        else:
            hls_path = raw_data.get("HLS")
        
        if hls_path:
            # Build full URL with authentication
            params = {
                "uuid": camera.uuid,
                "token": f"bearer-{access_token}"
            }
            query_string = urlencode(params)
            hls_path = hls_path.lstrip("/")
            url = f"{self.CDN_BASE_URL}/{hls_path}?{query_string}"
            logger.debug(f"Using fallback HLS URL with relative path: {url[:100]}...")
            return url
        
        # Last resort: build URL manually
        params = {
            "uuid": camera.uuid,
            "token": f"bearer-{access_token}"
        }
        
        if realtime:
            params["realtime"] = "1"
        
        query_string = urlencode(params)
        url = f"{self.CDN_BASE_URL}/hls/playlists/multivariant.m3u8?{query_string}"
        logger.debug(f"Using manually constructed HLS URL: {url[:100]}...")
        
        return url
    
    def _build_snapshot_url(self, camera: Camera, access_token: str, lossy: bool = False) -> str:
        """
        Build snapshot URL for camera.
        
        Args:
            camera: Camera object with raw_data
            access_token: Access token for authentication (not used, URLs already include token)
            lossy: Use lossy compression
        
        Returns:
            Snapshot URL
        """
        # Try to get direct snapshot URL from camera raw_data MEDIA object
        raw_data = camera.raw_data or {}
        media = raw_data.get("MEDIA", {})
        
        if isinstance(media, dict):
            snapshot_media = media.get("SNAPSHOT", {})
            if isinstance(snapshot_media, dict):
                live_snapshot = snapshot_media.get("LIVE", {})
                if isinstance(live_snapshot, dict):
                    # Use LOSSY or MAIN based on parameter
                    if lossy:
                        direct_url = live_snapshot.get("LOSSY") or live_snapshot.get("MAIN")
                    else:
                        direct_url = live_snapshot.get("MAIN")
                    
                    if direct_url:
                        logger.debug(f"Using direct snapshot URL from MEDIA object: {direct_url[:100]}...")
                        return direct_url
        
        # Fallback: build URL manually
        params = {
            "uuid": camera.uuid,
            "token": f"bearer-{access_token}"
        }
        
        if lossy:
            params["lossy"] = "1"
        
        query_string = urlencode(params)
        url = f"{self.CDN_BASE_URL}/snapshot?{query_string}"
        logger.debug(f"Using manually constructed snapshot URL: {url[:100]}...")
        
        return url
    
    def _validate_stream_format(self, stream_url: str) -> bool:
        """
        Validate that stream is in HLS format.
        
        Args:
            stream_url: Stream URL to validate
        
        Returns:
            True if stream is HLS format
        """
        # Check if URL contains HLS indicators
        hls_indicators = [
            ".m3u8",
            "/hls/",
            "multivariant.m3u8"
        ]
        
        return any(indicator in stream_url.lower() for indicator in hls_indicators)
    
    async def get_video_stream_url(
        self,
        camera_uuid: str,
        realtime: bool = True
    ) -> VideoStream:
        """
        Get video stream URL for camera.
        
        Implements Requirements:
        - 5.1: Video stream URL retrieval
        - 5.2: Stream format compatibility (HLS)
        - 5.5: Fallback placeholder image for unavailable streams
        
        Args:
            camera_uuid: Camera UUID
            realtime: Enable low latency mode
        
        Returns:
            VideoStream object with stream URL and metadata
        
        Raises:
            StreamError: If camera not found or stream unavailable
        """
        try:
            logger.info(f"Getting video stream URL for camera {camera_uuid}")
            
            # Get camera info
            camera = await self.get_camera_by_uuid(camera_uuid)
            if not camera:
                error_msg = f"Camera not found: {camera_uuid}"
                logger.error(error_msg)
                raise StreamError(error_msg, camera_uuid=camera_uuid, error_code="CAMERA_NOT_FOUND")
            
            # Check if camera has stream capability
            if not camera.has_stream:
                logger.warning(f"Camera {camera_uuid} does not have stream capability")
                # Return placeholder
                return VideoStream(
                    camera_uuid=camera_uuid,
                    stream_url=self.PLACEHOLDER_IMAGE_URL,
                    format="IMAGE",
                    snapshot_url=self.PLACEHOLDER_IMAGE_URL,
                    is_available=False
                )
            
            # Check if camera is online
            if not camera.is_online:
                logger.warning(f"Camera {camera_uuid} is offline")
                # Return placeholder
                return VideoStream(
                    camera_uuid=camera_uuid,
                    stream_url=self.PLACEHOLDER_IMAGE_URL,
                    format="IMAGE",
                    snapshot_url=self.PLACEHOLDER_IMAGE_URL,
                    is_available=False
                )
            
            # Get access token from API client
            auth_header = self.api_client.client.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                error_msg = "No access token available"
                logger.error(error_msg)
                raise StreamError(error_msg, camera_uuid=camera_uuid, error_code="NO_AUTH_TOKEN")
            
            access_token = auth_header.replace("Bearer ", "")
            
            # Build HLS stream URL using camera data
            stream_url = self._build_hls_stream_url(camera, access_token, realtime)
            
            # Validate stream format (Requirement 5.2)
            if not self._validate_stream_format(stream_url):
                error_msg = f"Invalid stream format for camera {camera_uuid}"
                logger.error(error_msg)
                raise StreamError(error_msg, camera_uuid=camera_uuid, error_code="INVALID_FORMAT")
            
            # Build snapshot URL
            snapshot_url = self._build_snapshot_url(camera, access_token)
            
            # Create VideoStream object
            video_stream = VideoStream(
                camera_uuid=camera_uuid,
                stream_url=stream_url,
                format="HLS",
                snapshot_url=snapshot_url,
                is_available=True
            )
            
            # Track active stream
            self._active_streams[camera_uuid] = video_stream
            
            logger.info(f"Video stream URL retrieved for camera {camera_uuid}")
            return video_stream
            
        except StreamError:
            raise
        except Exception as e:
            error_msg = f"Unexpected error getting video stream for camera {camera_uuid}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise StreamError(error_msg, camera_uuid=camera_uuid, error_code="UNEXPECTED_ERROR") from e
    
    async def get_snapshot_url(self, camera_uuid: str, lossy: bool = False) -> str:
        """
        Get snapshot URL for camera.
        
        Args:
            camera_uuid: Camera UUID
            lossy: Use lossy compression
        
        Returns:
            Snapshot URL or placeholder if unavailable
        """
        try:
            # Get camera info
            camera = await self.get_camera_by_uuid(camera_uuid)
            if not camera or not camera.is_online:
                logger.warning(f"Camera {camera_uuid} unavailable, returning placeholder")
                return self.PLACEHOLDER_IMAGE_URL
            
            # Get access token
            auth_header = self.api_client.client.headers.get("Authorization", "")
            if not auth_header.startswith("Bearer "):
                logger.warning("No access token available, returning placeholder")
                return self.PLACEHOLDER_IMAGE_URL
            
            access_token = auth_header.replace("Bearer ", "")
            
            # Build snapshot URL
            snapshot_url = self._build_snapshot_url(camera, access_token, lossy)
            
            logger.info(f"Snapshot URL retrieved for camera {camera_uuid}")
            return snapshot_url
            
        except Exception as e:
            logger.error(f"Error getting snapshot URL for camera {camera_uuid}: {e}")
            return self.PLACEHOLDER_IMAGE_URL
    
    def stop_stream(self, camera_uuid: str) -> bool:
        """
        Stop video stream and cleanup resources.
        
        Implements Requirement 5.4: Stream cleanup on stop.
        
        Args:
            camera_uuid: Camera UUID
        
        Returns:
            True if stream was stopped, False if no active stream
        """
        if camera_uuid in self._active_streams:
            logger.info(f"Stopping stream for camera {camera_uuid}")
            del self._active_streams[camera_uuid]
            return True
        
        logger.debug(f"No active stream found for camera {camera_uuid}")
        return False
    
    def get_active_streams(self) -> List[VideoStream]:
        """
        Get list of currently active streams.
        
        Returns:
            List of active VideoStream objects
        """
        return list(self._active_streams.values())
    
    def stop_all_streams(self) -> int:
        """
        Stop all active streams and cleanup resources.
        
        Returns:
            Number of streams stopped
        """
        count = len(self._active_streams)
        if count > 0:
            logger.info(f"Stopping {count} active streams")
            self._active_streams.clear()
        return count
    
    async def close(self) -> None:
        """Cleanup resources."""
        self.stop_all_streams()
        logger.info("StreamHandler closed")
