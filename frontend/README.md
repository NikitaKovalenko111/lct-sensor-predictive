# Контур — frontend

React/TypeScript-клиент для сервиса предиктивного мониторинга инженерных коллекторов.

## Запуск

```bash
npm install
npm run dev
```

По умолчанию клиент работает в mock-режиме и не требует запущенного бэкенда. Для подключения API создайте `.env.local`:

```dotenv
VITE_API_MODE=live
VITE_API_URL=http://localhost:8080
VITE_API_TIMEOUT_MS=15000
VITE_ENABLE_INCIDENT_STREAM=false
VITE_ENABLE_USER_MUTATIONS=false
```

До начала интеграции оставляйте `VITE_API_MODE=mock`. Подробный порядок подключения и известные расхождения контракта описаны в [BACKEND_INTEGRATION.md](./BACKEND_INTEGRATION.md).

## Демо-пользователи

- `dispatcher` / `DispatchPredict2026!`
- `analyst` / `AnalystPredict2026!`
- `admin` / `AdminPredict2026!`

Типы запросов и ответов синхронизированы с `backend/api/openapi.yaml`.
