# Контур — frontend

React/TypeScript-клиент для сервиса предиктивного мониторинга инженерных коллекторов.

## Запуск

```bash
npm install
npm run dev
```

По умолчанию клиент подключён к backend через Vite proxy (`http://localhost:8080`). Для автономной разработки можно создать `.env.local` и включить mock-режим:

```dotenv
VITE_API_MODE=mock
VITE_API_URL=
VITE_API_TIMEOUT_MS=15000
VITE_ENABLE_INCIDENT_STREAM=false
```

Подключённые методы и порядок совместного запуска описаны в [BACKEND_INTEGRATION.md](./BACKEND_INTEGRATION.md).

## Демо-пользователи

- `dispatcher` / `DispatchPredict2026!`
- `analyst` / `AnalystPredict2026!`
- `admin` / `AdminPredict2026!`

Типы запросов и ответов синхронизированы с `backend/api/openapi.yaml`.
