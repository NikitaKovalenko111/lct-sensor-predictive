# Интеграция frontend с backend

Frontend подключён к API из `backend/api/openapi.yaml`. Без переменных окружения используется live-режим, запросы `/api` и `/health` в локальной разработке проксируются Vite на `http://localhost:8083`.

## Подключённые возможности

- вход через `/api/v1/auth/login` и проверка сохранённой сессии через `/api/v1/auth/me`;
- автоматический выход при ответе `401`;
- прогнозы, инциденты, объекты, каналы и события датчиков;
- создание, назначение, подтверждение и закрытие инцидентов;
- защищённый SSE-поток инцидентов с Bearer-токеном и переподключением;
- список пользователей, создание пользователей, смена роли и удаление;
- журнал аудита и проверки `/health/live`, `/health/ready`;
- геометрия объектов backend используется для меток на Яндекс Карте.

## Локальный запуск

Запустить backend из каталога `backend`:

```bash
docker compose --profile mock --profile demo up --build
```

Затем запустить frontend:

```bash
npm run dev
```

Docker Compose создаёт тестовые аккаунты `admin`, `dispatcher` и `analyst`, совпадающие с данными на экране входа. Bootstrap-пароли предназначены только для локального запуска и должны быть заменены в рабочем окружении.

## Переменные frontend

```dotenv
VITE_API_MODE=live
VITE_API_URL=
VITE_API_TIMEOUT_MS=15000
VITE_ENABLE_INCIDENT_STREAM=true
VITE_YANDEX_MAPS_API_KEY=
```

`VITE_API_URL` можно задать для отдельного API-домена. Пустое значение использует текущий origin и локальный Vite proxy. Для автономной вёрстки установите `VITE_API_MODE=mock` и `VITE_ENABLE_INCIDENT_STREAM=false`.

Роль `manager` остаётся частью backend-контракта, но не предлагается как тестовая или создаваемая роль в текущем интерфейсе.
