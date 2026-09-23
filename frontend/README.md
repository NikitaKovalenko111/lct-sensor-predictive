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
```

## Демо-пользователи

- `dispatcher` / `DispatchPredict2026!`
- `analyst` / `AnalystPredict2026!`
- `manager` / `ManagerPredict2026!`
- `admin` / `AdminPredict2026!`

Типы запросов и ответов синхронизированы с `backend/api/openapi.yaml`.
