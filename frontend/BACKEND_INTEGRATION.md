# Подготовка frontend к backend-интеграции

Frontend пока работает в `mock`-режиме и не обращается к backend. API-слой подготовлен по контракту `backend/api/openapi.yaml`.

## Что уже подготовлено

- единый HTTP-клиент с Bearer-токеном, таймаутом и обработкой JSON-ошибок backend;
- централизованные настройки окружения и хранилище токена;
- query-параметры без лишних `?` и пустых значений;
- методы `/auth/login`, `/auth/me`, health-check, прогнозов, инцидентов, объектов, каналов, телеметрии, пользователей и аудита;
- клиент SSE для `/api/v1/incidents/stream`, который не запускается до включения флага;
- чтение GeoJSON-геометрии объекта для размещения меток на Яндекс Карте;
- Vite proxy для локальной разработки.

## Переключение на backend позже

Создать `frontend/.env.local`:

```dotenv
VITE_API_MODE=live
VITE_API_URL=http://localhost:8080
VITE_API_TIMEOUT_MS=15000
VITE_ENABLE_INCIDENT_STREAM=false
VITE_ENABLE_USER_MUTATIONS=false
VITE_YANDEX_MAPS_API_KEY=
```

После запуска backend сначала проверить `/health/live`, `/health/ready` и `/api/v1/auth/login`. Затем включать страницы по одной. Поток инцидентов включать последним через `VITE_ENABLE_INCIDENT_STREAM=true`.

## Известное расхождение контракта

В OpenAPI сейчас отсутствуют операции изменения роли и удаления пользователя:

- `PATCH /api/v1/users/{user_id}`;
- `DELETE /api/v1/users/{user_id}`.

Поэтому в live-режиме эти действия заблокированы понятной ошибкой. После реализации endpoints на backend нужно выставить `VITE_ENABLE_USER_MUTATIONS=true`.

## Роли

В OpenAPI роль `manager` существует, но в текущем frontend не предлагается как тестовый аккаунт или создаваемая роль. Тип сохранён только для совместимости с backend-контрактом.
