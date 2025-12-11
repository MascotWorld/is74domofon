# Requirements Document

## Introduction

Данная система представляет собой интеграцию умного домофона is74.ru с платформой Home Assistant. Система обеспечивает полный контроль над домофоном: открытие двери, просмотр видеопотока с камеры, автоматическое открытие и обработку входящих вызовов через Firebase Cloud Messaging.

## Glossary

- **IS74 API**: REST API интернет-провайдера is74.ru для управления умными домофонами
- **Home Assistant**: Платформа автоматизации умного дома с открытым исходным кодом
- **Integration Service**: Сервис-посредник между IS74 API и Home Assistant
- **Firebase Token**: Токен для подписки на push-уведомления через Firebase Cloud Messaging
- **Access Token**: Токен авторизации для доступа к IS74 API
- **Refresh Token**: Токен для обновления Access Token без повторной авторизации
- **2FA Code**: Одноразовый код двухфакторной аутентификации
- **Video Stream**: Видеопоток с камеры домофона в формате RTSP или HLS
- **Intercom Device**: Физическое устройство домофона is74.ru
- **Door Lock**: Электронный замок двери, управляемый домофоном

## Requirements

### Requirement 1

**User Story:** Как пользователь, я хочу авторизоваться в системе IS74 с поддержкой 2FA, чтобы получить доступ к управлению домофоном

#### Acceptance Criteria

1. WHEN пользователь предоставляет логин и пароль, THEN Integration Service SHALL отправить запрос авторизации к IS74 API
2. WHEN IS74 API требует 2FA код, THEN Integration Service SHALL запросить код у пользователя и отправить его для завершения авторизации
3. WHEN авторизация успешна, THEN Integration Service SHALL сохранить Access Token и Refresh Token в защищенном хранилище
4. WHEN Access Token истекает, THEN Integration Service SHALL автоматически обновить его используя Refresh Token
5. IF авторизация не удалась после трех попыток, THEN Integration Service SHALL заблокировать дальнейшие попытки на 5 минут

### Requirement 2

**User Story:** Как пользователь, я хочу получать Firebase токен для подписки на уведомления о звонках, чтобы система могла реагировать на вызовы в реальном времени

#### Acceptance Criteria

1. WHEN Integration Service успешно авторизован, THEN Integration Service SHALL запросить Firebase Token у IS74 API
2. WHEN Firebase Token получен, THEN Integration Service SHALL сохранить его для последующего использования
3. WHEN Firebase Token истекает, THEN Integration Service SHALL автоматически запросить новый токен
4. WHEN Firebase Token недоступен, THEN Integration Service SHALL повторить запрос с экспоненциальной задержкой до трех попыток

### Requirement 3

**User Story:** Как пользователь, я хочу получать уведомления о входящих звонках через Firebase, чтобы система могла автоматически реагировать на вызовы

#### Acceptance Criteria

1. WHEN Integration Service запускается, THEN Integration Service SHALL подписаться на Firebase Cloud Messaging используя Firebase Token
2. WHEN входящий вызов поступает через Firebase, THEN Integration Service SHALL извлечь информацию о вызове (ID устройства, временная метка, изображение)
3. WHEN уведомление о вызове получено, THEN Integration Service SHALL отправить событие в Home Assistant с деталями вызова
4. WHEN соединение с Firebase прерывается, THEN Integration Service SHALL автоматически переподключиться в течение 10 секунд
5. WHILE Integration Service подписан на уведомления, Integration Service SHALL поддерживать активное соединение с Firebase

### Requirement 4

**User Story:** Как пользователь, я хочу открывать дверь через Home Assistant, чтобы дистанционно управлять доступом

#### Acceptance Criteria

1. WHEN пользователь активирует команду открытия двери в Home Assistant, THEN Integration Service SHALL отправить команду открытия к IS74 API
2. WHEN команда открытия успешна, THEN Integration Service SHALL обновить статус Door Lock в Home Assistant на "unlocked"
3. WHEN команда открытия не удалась, THEN Integration Service SHALL уведомить Home Assistant об ошибке с описанием причины
4. WHEN дверь открывается, THEN Integration Service SHALL автоматически вернуть статус Door Lock на "locked" через 5 секунд

### Requirement 5

**User Story:** Как пользователь, я хочу просматривать видеопоток с камеры домофона в Home Assistant, чтобы видеть кто находится у двери

#### Acceptance Criteria

1. WHEN пользователь запрашивает видеопоток, THEN Integration Service SHALL получить URL потока от IS74 API
2. WHEN URL потока получен, THEN Integration Service SHALL предоставить поток в формате, совместимом с Home Assistant (RTSP или HLS)
3. WHEN видеопоток активен, THEN Integration Service SHALL поддерживать соединение и обрабатывать переподключения при разрывах
4. WHEN пользователь останавливает просмотр, THEN Integration Service SHALL корректно закрыть соединение с потоком
5. IF поток недоступен, THEN Integration Service SHALL уведомить Home Assistant и предоставить статическое изображение-заглушку

### Requirement 6

**User Story:** Как пользователь, я хочу настроить автоматическое открытие двери при звонке, чтобы не открывать дверь вручную каждый раз

#### Acceptance Criteria

1. WHERE автоматическое открытие включено, WHEN входящий вызов получен, THEN Integration Service SHALL автоматически отправить команду открытия двери
2. WHERE автоматическое открытие включено с условиями, WHEN входящий вызов соответствует условиям (время суток, день недели), THEN Integration Service SHALL открыть дверь
3. WHERE автоматическое открытие включено с условиями, WHEN входящий вызов не соответствует условиям, THEN Integration Service SHALL только уведомить Home Assistant без открытия
4. WHEN автоматическое открытие выполнено, THEN Integration Service SHALL записать событие в лог с временной меткой

### Requirement 7

**User Story:** Как пользователь, я хочу принимать вызовы с домофона, чтобы установить двустороннюю связь с посетителем

#### Acceptance Criteria

1. WHEN пользователь принимает вызов в Home Assistant, THEN Integration Service SHALL отправить команду принятия вызова к IS74 API
2. WHEN вызов принят, THEN Integration Service SHALL установить аудио соединение между пользователем и Intercom Device
3. WHEN аудио соединение активно, THEN Integration Service SHALL передавать аудио в обоих направлениях с задержкой не более 500 миллисекунд
4. WHEN пользователь завершает вызов, THEN Integration Service SHALL корректно закрыть аудио соединение и уведомить IS74 API

### Requirement 8

**User Story:** Как администратор системы, я хочу безопасно хранить учетные данные и токены, чтобы предотвратить несанкционированный доступ

#### Acceptance Criteria

1. WHEN Integration Service сохраняет токены или учетные данные, THEN Integration Service SHALL шифровать их используя AES-256
2. WHEN Integration Service запускается, THEN Integration Service SHALL загружать учетные данные из защищенного хранилища
3. WHEN учетные данные запрашиваются, THEN Integration Service SHALL расшифровывать их только в памяти без записи на диск
4. WHEN Integration Service останавливается, THEN Integration Service SHALL очистить все чувствительные данные из памяти

### Requirement 9

**User Story:** Как пользователь Home Assistant, я хочу видеть статус домофона и историю событий, чтобы отслеживать активность

#### Acceptance Criteria

1. WHEN Integration Service подключен к Intercom Device, THEN Integration Service SHALL предоставлять статус "online" в Home Assistant
2. WHEN соединение с Intercom Device потеряно, THEN Integration Service SHALL обновить статус на "offline" в течение 30 секунд
3. WHEN происходит событие (вызов, открытие двери), THEN Integration Service SHALL записать событие с временной меткой в историю Home Assistant
4. WHEN пользователь запрашивает историю, THEN Integration Service SHALL предоставить последние 100 событий

### Requirement 10

**User Story:** Как разработчик, я хочу иметь API документацию и логирование, чтобы легко отлаживать и расширять систему

#### Acceptance Criteria

1. WHEN Integration Service запускается, THEN Integration Service SHALL инициализировать систему логирования с уровнями DEBUG, INFO, WARNING, ERROR
2. WHEN происходит ошибка, THEN Integration Service SHALL записать детальную информацию об ошибке включая stack trace
3. WHEN выполняется API запрос, THEN Integration Service SHALL логировать запрос и ответ (исключая чувствительные данные)
4. THE Integration Service SHALL предоставлять OpenAPI документацию для всех эндпоинтов
