# Implementation Plan

- [x] 1. Set up project structure and dependencies
  - Create Python project with FastAPI, httpx, firebase-admin, cryptography, pytest, hypothesis
  - Set up directory structure: src/, tests/, config/
  - Configure pytest and hypothesis for testing
  - Create requirements.txt and setup.py
  - _Requirements: 10.4_

- [x] 2. Implement IS74 API Client
  - Create IS74ApiClient class with httpx for HTTP requests
  - Implement base URL configuration (https://td-crm.is74.ru)
  - Add User-Agent header: "4.12.0 com.intersvyaz.lk/1.30.1.2024040812"
  - Implement request/response logging with sensitive data masking
  - Add error handling and retry logic
  - _Requirements: 10.3_

- [ ] 3. Implement Config Manager with encryption
  - Write ConfigManager class with AES-256-GCM encryption/decryption methods
  - Implement secure credential storage and loading
  - Create configuration file schema (YAML)
  - _Requirements: 8.1, 8.2_

- [ ]* 3.1 Write property test for credential encryption
  - **Property 25: Credential encryption with AES-256**
  - **Validates: Requirements 8.1**

- [ ]* 3.2 Write property test for credential loading
  - **Property 26: Credential loading on startup**
  - **Validates: Requirements 8.2**

- [x] 4. Implement Auth Manager with phone-based authentication
  - Write AuthManager class using IS74ApiClient
  - Implement POST /api/auth/code - request SMS code
  - Implement POST /api/auth/verify - submit code and get authid/user_id
  - Implement POST /api/auth/token - get access token with authid/user_id
  - Implement token expiration checking and automatic refresh logic
  - Add rate limiting for failed authentication attempts (3 attempts, 5 minute lockout)
  - Store tokens (access_token, user_id, profile_id, expires_at)
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [ ]* 4.1 Write property test for authentication request
  - **Property 1: Authentication request is sent**
  - **Validates: Requirements 1.1**

- [ ]* 4.2 Write property test for 2FA workflow
  - **Property 2: 2FA workflow completion**
  - **Validates: Requirements 1.2**

- [ ]* 4.3 Write property test for token persistence
  - **Property 3: Token persistence after authentication**
  - **Validates: Requirements 1.3**

- [ ]* 4.4 Write property test for automatic token refresh
  - **Property 4: Automatic token refresh**
  - **Validates: Requirements 1.4**

- [ ]* 4.5 Write unit test for rate limiting
  - Test that exactly 3 failed attempts trigger 5 minute lockout
  - _Requirements: 1.5_

- [x] 5. Implement Firebase token management
  - Add GET /api/firebase/config method to AuthManager
  - Add POST /api/firebase/token method with device registration payload
  - Implement Firebase token storage and auto-refresh
  - Add retry logic with exponential backoff (up to 3 attempts)
  - _Requirements: 2.1, 2.2, 2.3, 2.4_

- [ ]* 5.1 Write property test for Firebase token request
  - **Property 5: Firebase token request after auth**
  - **Validates: Requirements 2.1**

- [ ]* 5.2 Write property test for Firebase token persistence
  - **Property 6: Firebase token persistence**
  - **Validates: Requirements 2.2**

- [ ]* 5.3 Write property test for Firebase token auto-refresh
  - **Property 7: Firebase token auto-refresh**
  - **Validates: Requirements 2.3**

- [ ]* 5.4 Write property test for exponential backoff retry
  - **Property 8: Firebase retry with exponential backoff**
  - **Validates: Requirements 2.4**

- [x] 6. Implement Firebase Listener
  - Write FirebaseListener class using firebase-messaging library (real-time push notifications)
  - Implement subscribe/unsubscribe methods with automatic credential management
  - Implement message handling and call event extraction
  - Add topic subscription/unsubscription support
  - Parse Firebase messages for call events (device_id, timestamp, snapshot_url)
  - _Requirements: 3.1, 3.2, 3.4_
  - _Note: Migrated from firebase-admin to firebase-messaging for direct push notification support_

- [ ]* 6.1 Write property test for Firebase subscription on startup
  - **Property 9: Firebase subscription on startup**
  - **Validates: Requirements 3.1**

- [ ]* 6.2 Write property test for call information extraction
  - **Property 10: Call information extraction**
  - **Validates: Requirements 3.2**

- [ ]* 6.3 Write unit test for reconnection timing
  - Test that reconnection happens within 10 seconds
  - _Requirements: 3.4_

- [x] 7. Implement Device Controller for intercom operations
  - Write DeviceController class using IS74ApiClient
  - Implement GET /api/intercoms - get list of intercom devices
  - Implement POST /api/open/{mac}/{relay_num} - open door command
  - Implement door lock status synchronization with Home Assistant
  - Add automatic lock status reset after 5 seconds
  - Add error handling and notification for failed commands
  - Parse device list response (MAC, relay_id, status, address, etc.)
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [ ]* 7.1 Write property test for door open command
  - **Property 12: Door open command transmission**
  - **Validates: Requirements 4.1**

- [ ]* 7.2 Write property test for door status sync
  - **Property 13: Door status synchronization on success**
  - **Validates: Requirements 4.2**

- [ ]* 7.3 Write property test for error notification
  - **Property 14: Error notification on door open failure**
  - **Validates: Requirements 4.3**

- [ ]* 7.4 Write unit test for lock status reset timing
  - Test that lock status returns to "locked" after exactly 5 seconds
  - _Requirements: 4.4_

- [x] 8. Implement Stream Handler for cameras
  - Write StreamHandler class using IS74ApiClient
  - Implement GET /api/cameras - get camera list with UUIDs
  - Implement video stream URL retrieval from camera list
  - Parse HLS stream URLs (cdn.cams.is74.ru with uuid and bearer token)
  - Implement stream format validation (HLS)
  - Add stream cleanup and resource management
  - Implement fallback placeholder image for unavailable streams
  - _Requirements: 5.1, 5.2, 5.4, 5.5_

- [ ]* 8.1 Write property test for video stream URL retrieval
  - **Property 15: Video stream URL retrieval**
  - **Validates: Requirements 5.1**

- [ ]* 8.2 Write property test for stream format compatibility
  - **Property 16: Stream format compatibility**
  - **Validates: Requirements 5.2**

- [ ]* 8.3 Write property test for stream cleanup
  - **Property 17: Stream cleanup on stop**
  - **Validates: Requirements 5.4**

- [ ]* 8.4 Write property test for fallback image
  - **Property 18: Fallback image on stream failure**
  - **Validates: Requirements 5.5**

- [ ] 9. Implement TeleVoIP integration for audio calls
  - Add GET /api/televoip/credentials method to get SIP credentials
  - Add GET /api/televoip/token method to get JWT token
  - Implement call acceptance command
  - Implement audio session establishment
  - Add call cleanup and resource management
  - _Requirements: 7.1, 7.2, 7.4_

- [ ]* 9.1 Write property test for call acceptance command
  - **Property 22: Call acceptance command transmission**
  - **Validates: Requirements 7.1**

- [ ]* 9.2 Write property test for audio session establishment
  - **Property 23: Audio session establishment**
  - **Validates: Requirements 7.2**

- [ ]* 9.3 Write property test for call cleanup
  - **Property 24: Call cleanup on termination**
  - **Validates: Requirements 7.4**

- [x] 10. Implement Event Manager
  - Write EventManager class for event logging and history
  - Implement Home Assistant notification method
  - Add event storage with timestamp
  - _Requirements: 9.3, 6.4_

- [ ]* 10.1 Write property test for call event forwarding
  - **Property 11: Call event forwarding to Home Assistant**
  - **Validates: Requirements 3.3**

- [ ]* 10.2 Write property test for event recording
  - **Property 28: Event recording with timestamp**
  - **Validates: Requirements 9.3**

- [ ]* 10.3 Write property test for auto-open event logging
  - **Property 21: Auto-open event logging**
  - **Validates: Requirements 6.4**

- [ ]* 10.4 Write unit test for history limit
  - Test that exactly 100 most recent events are returned
  - _Requirements: 9.4_

- [x] 11. Implement auto-open functionality
  - Add auto-open configuration to ConfigManager
  - Implement schedule-based conditional auto-open logic
  - Wire auto-open to Firebase call events
  - _Requirements: 6.1, 6.2, 6.3_

- [ ]* 11.1 Write property test for auto-open on call
  - **Property 19: Auto-open on call when enabled**
  - **Validates: Requirements 6.1**

- [ ]* 11.2 Write property test for conditional auto-open
  - **Property 20: Conditional auto-open based on schedule**
  - **Validates: Requirements 6.2, 6.3**

- [x] 12. Implement device status monitoring
  - Add device status tracking in DeviceController
  - Implement online/offline status reporting to Home Assistant
  - Add status update on connection loss with 30 second timeout
  - _Requirements: 9.1, 9.2_

- [ ]* 12.1 Write property test for online status reporting
  - **Property 27: Online status reporting**
  - **Validates: Requirements 9.1**

- [ ]* 12.2 Write unit test for offline status timing
  - Test that status updates to offline within 30 seconds
  - _Requirements: 9.2_

- [x] 13. Implement logging system
  - Configure Python logging with DEBUG, INFO, WARNING, ERROR levels
  - Add error logging with stack traces
  - Implement API request/response logging with sensitive data masking
  - Mask tokens, passwords, and phone numbers in logs
  - _Requirements: 10.1, 10.2, 10.3_

- [ ]* 13.1 Write property test for logging initialization
  - **Property 29: Logging system initialization**
  - **Validates: Requirements 10.1**

- [ ]* 13.2 Write property test for error logging
  - **Property 30: Error logging with stack trace**
  - **Validates: Requirements 10.2**

- [ ]* 13.3 Write property test for API logging with masking
  - **Property 31: API request logging with data masking**
  - **Validates: Requirements 10.3**

- [x] 14. Implement FastAPI REST API
  - Create FastAPI application with all endpoints
  - POST /auth/login - initiate phone authentication
  - POST /auth/verify - submit 2FA code
  - GET /devices - list intercom devices
  - POST /door/open - open door by device ID
  - GET /stream/video/{device_id} - get video stream URL
  - POST /call/accept - accept incoming call
  - GET /events - get event history
  - GET /status - service status
  - Add OpenAPI documentation generation
  - Implement request validation and error handling
  - Add CORS middleware for Home Assistant integration
  - _Requirements: 10.4_

- [ ]* 14.1 Write property test for OpenAPI documentation
  - **Property 32: OpenAPI documentation availability**
  - **Validates: Requirements 10.4**

- [ ] 15. Create Home Assistant custom integration
  - Create custom component structure (manifest.json, __init__.py, config_flow.py)
  - Implement lock entity for door control
  - Implement camera entity for video stream
  - Implement binary sensor entity for call detection
  - Implement switch entity for auto-open toggle
  - _Requirements: 4.1, 5.1, 3.3, 6.1_

- [ ]* 15.1 Write integration tests for Home Assistant entities
  - Test lock entity state changes
  - Test camera entity stream access
  - Test binary sensor call detection
  - Test switch entity auto-open control
  - _Requirements: 4.1, 5.1, 3.3, 6.1_

- [ ] 16. Wire all components together
  - Create main application entry point
  - Initialize all managers and controllers with IS74ApiClient
  - Set up FastAPI routes with dependency injection
  - Connect Firebase listener to event manager and device controller
  - Add graceful shutdown handling
  - _Requirements: All_

- [ ] 17. Create Docker deployment configuration
  - Write Dockerfile with Python 3.11+ and FFmpeg
  - Create docker-compose.yml with volume mounts and environment variables
  - Add health check endpoint
  - Create example configuration files
  - _Requirements: All_

- [ ]* 18. Write end-to-end integration tests
  - Test full authentication flow with phone code
  - Test call notification → auto-open flow
  - Test video stream request → playback flow
  - Test manual door open from Home Assistant
  - _Requirements: All_

- [ ] 19. Create documentation
  - Write README with installation instructions
  - Document API endpoints with real IS74 API details
  - Create Home Assistant configuration examples
  - Add troubleshooting guide
  - Document authentication flow (phone → code → authid → token)
  - _Requirements: 10.4_

- [ ] 20. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise

