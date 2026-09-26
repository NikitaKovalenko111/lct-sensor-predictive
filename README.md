# Контур — предиктивный мониторинг

Единый контур прогнозирования рисков инженерной инфраструктуры:

- React/Vite frontend;
- Go backend с REST API, PostgreSQL, Kafka, RBAC, аудитом и SSE;
- Python ML-сервис для пожароопасности, НСД и отказов оборудования.

## Быстрый запуск

Для проверки интерфейса и backend без ML-артефактов:

```bash
cd backend
docker compose --profile mock --profile demo up --build
```

Полный запуск с реальными моделями:

```bash
cd backend
docker compose --profile model --profile demo up --build
```

Не включайте профили `mock` и `model` одновременно: оба сервиса публикуют
прогнозы в один топик.

После запуска доступны:

- frontend: <http://localhost:3000>;
- backend API: <http://localhost:8083>;
- Swagger UI: <http://localhost:8081>;
- ML API: <http://localhost:8000> (только профиль `model`);
- Kafka для локальных инструментов: `localhost:29092`;
- PostgreSQL: `localhost:5433`.

## Артефакты моделей

Артефакты не хранятся в Git. Для профиля `model` должны существовать:

```text
model/models/fire_risk/saved/fire_risk_model.joblib
model/models/fire_risk/saved/fire_risk_threshold.joblib
model/models/fire_risk/saved/fire_risk_features.joblib
model/models/unac/saved/nsd_model_clean.joblib
model/models/unac/saved/nsd_features_clean.joblib
model/models/unac/saved/nsd_threshold_clean.joblib
model/models/unac/saved/nsd_risk_model.joblib
model/models/unac/saved/nsd_risk_threshold.joblib
model/models/unac/saved/nsd_risk_features.joblib
model/models/fault_risk/saved/fault_model.joblib
model/models/fault_risk/saved/fault_threshold.joblib
model/models/fault_risk/saved/fault_features.joblib
```

Каталог `model/models` монтируется в ML-контейнер только для чтения.

## Поток данных

```text
frontend -> Go API -> POST /predict -> Python ML
                                      |
sensor events -> Kafka -> Python ML --+-> predictions.v1
       |                                      |
       +-> backend telemetry worker           v
                                        backend worker
                                              |
                                      PostgreSQL + incidents
                                              |
                                         REST API + SSE
```

HTTP-ответ даёт frontend результат сразу. Та же версия прогноза со стабильным
`prediction_id` публикуется в Kafka, после чего backend идемпотентно сохраняет
её и при необходимости создаёт инцидент.

Подробности модулей находятся в [backend/README.md](backend/README.md),
[frontend/README.md](frontend/README.md) и
[backend/docs/model-integration.md](backend/docs/model-integration.md).
