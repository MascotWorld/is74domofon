# IS74 Домофон

HACS-интеграция для Home Assistant для сервисов интернет-провайдера Интерсвязь, которая подключается к домофонам и камерам IS74 напрямую из `custom_components/is74_domofon`.

## Что умеет

- открывать дверь из Home Assistant
- показывать камеры домофона
- получать push-вызовы через Firebase Cloud Messaging
- генерировать событие `is74_domofon_incoming_call`

## Установка через HACS

1. В HACS откройте `Custom repositories`.
2. Добавьте репозиторий `https://github.com/MascotWorld/is74domofon` как `Integration`.
3. Установите `IS74 Домофон`.
4. Перезапустите Home Assistant.
5. Добавьте интеграцию через `Настройки -> Устройства и службы`.

## Настройка

1. Включите интеграцию.
2. Введите номер телефона без `+7`.
3. Если IS74 позвонит, введите 4 последние цифры номера, с которого поступил звонок. Если придёт SMS, введите код из SMS.
4. Push-слушатель FCM поддерживается интеграцией автоматически, включая обновление недельной Firebase-регистрации.

## Сервисы

- `is74_domofon.open_door`
- `is74_domofon.start_fcm`
- `is74_domofon.stop_fcm`

## События

- `is74_domofon_incoming_call`
- `is74_domofon_door_opened`

Автооткрытие теперь не встроено в интеграцию. Если нужно открывать дверь по звонку автоматически, это лучше делать обычной автоматизацией Home Assistant на событие `is74_domofon_incoming_call`.

Пример автоматизации для автооткрытия:

```yaml
alias: IS74 автооткрытие Ленина 1
mode: single
trigger:
  - platform: event
    event_type: is74_domofon_incoming_call
    event_data:
      device_id: "AA:BB:CC:DD:EE:FF"
action:
  - service: is74_domofon.open_door
    data:
      device_id: "AA:BB:CC:DD:EE:FF"
```

Если фильтровать по `device_id` неудобно, можно строить автоматизацию по другим полям события, например `address`, `entrance` или содержимому `data`.

## Камеры в Lovelace

Для live-view на дашборде нужен стандартный `stream` в Home Assistant. Обычно достаточно добавить в `configuration.yaml`:

```yaml
stream:
```

После перезапуска Home Assistant камера из этой интеграции лучше всего работает через `picture-entity` с `camera_view: live`:

```yaml
type: picture-entity
entity: camera.is74_domofon_lenina_1_parkovka
camera_view: live
show_name: true
show_state: false
```

Если нужна сетка камер:

```yaml
type: picture-glance
title: Домофон
camera_image: camera.is74_domofon_lenina_1_parkovka
camera_view: live
entities: []
```

Обычная `entities` карточка или некоторые минимальные tile-варианты часто показывают только snapshot, а не автозапуск live stream.
