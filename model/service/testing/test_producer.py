"""
Тестовый продюсер событий для локальной проверки пайплайна модельного сервиса.

Генерирует три сценария:
  - объект 9999: реальное НСД (движение ДО + дверь + каскад люка + движение ПОСЛЕ +
                 поломки 3 дня назад → высокий nsd_event + высокий nsd_risk)
  - объект 8888: одиночное открытие двери без движения → низкий nsd_event (фильтр ложных)
  - объект 7777: всплеск тревог + рост температуры → высокий fire_risk

Плюс фоновая история за 40 дней для всех объектов (чтобы у моделей было что считать
в окнах 7/14/24/30 дней).

Запуск (при поднятых kafka+postgres и запущенном main.py):
    python test_producer.py
"""

import asyncio
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from aiokafka import AIOKafkaProducer

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ============================================================================
# НАСТРОЙКИ (должны совпадать с .env сервиса)
# ============================================================================
BOOTSTRAP = "localhost:29092"
INPUT_TOPIC = "sensor.events.v1"
NOW = datetime.now(timezone.utc).replace(microsecond=0)

# Список объектов, для которых строим историю
OBJECTS = [9999, 8888, 7777]


# ============================================================================
# ХЕЛПЕРЫ
# ============================================================================
def ev(obj, sensor_type, value, alarm, ts, system="Охранная подсистема"):
    """Фабрика события датчика в формате schemas.SensorEvent."""
    return {
        "schema_version": 1,
        "event_id": str(uuid.uuid4()),
        "object_id": obj,
        "channel_id": f"ch_{obj}_{sensor_type}",
        "sensor_type": sensor_type,
        "engineering_system": system,
        "value": value,
        "is_alarm": alarm,
        "timestamp": ts.isoformat(),
    }


def hour(ts, h, m=0):
    """Сбрасывает время на h:m указанного дня."""
    return ts.replace(hour=h, minute=m, second=0)


# ============================================================================
# СЦЕНАРИЙ 1: фон за 40 дней (окна риск-скоринга и пожарная базовая линия)
# ============================================================================
def build_history():
    msgs = []
    for day_offset in range(1, 41):
        day = NOW - timedelta(days=day_offset)

        for obj in OBJECTS:
            # Движение в рабочие часы (фон, не тревога)
            for h in (9, 10, 11, 14, 15, 16):
                msgs.append(ev(obj, "Датчик движения", "Обнаружено движение",
                               False, hour(day, h, 30)))
                msgs.append(ev(obj, "Датчик движения", "Движения нет",
                               False, hour(day, h, 45)))

            # Температура (норма ~20°C)
            for h in (8, 12, 18, 22):
                msgs.append(ev(obj, "Датчик температуры", "20.5",
                               False, hour(day, h), system="Пожарная подсистема"))

            # Редкие тревоги фона
            if day_offset % 3 == 0:
                msgs.append(ev(obj, "Датчик затопления", "Неисправен", True,
                               hour(day, 10, 15), system="Пожарная подсистема"))

    # --- Объекту 9999 специально: поломки 3-7 дней назад (сигнал уязвимости) ---
    for day_offset in range(3, 8):
        day = NOW - timedelta(days=day_offset)
        for h in range(9, 16):
            msgs.append(ev(9999, "Состояние насоса", "Неисправен", True,
                           hour(day, h)))
            if h % 2 == 0:
                msgs.append(ev(9999, "Состояние вентилятора", "Обесточен", True,
                               hour(day, h, 30)))

    # --- Объекту 9999: пара НСД неделю назад (сигнал near-repeat для риск-скоринга) ---
    day7 = NOW - timedelta(days=7)
    msgs.append(ev(9999, "КД Дверь", "Не замкнут", True, hour(day7, 2)))
    msgs.append(ev(9999, "Датчик движения", "Обнаружено движение", False,
                   hour(day7, 2, 3)))

    day5 = NOW - timedelta(days=5)
    msgs.append(ev(9999, "КД Люк", "Не замкнут", True, hour(day5, 3)))
    msgs.append(ev(9999, "Датчик движения", "Обнаружено движение", False,
                   hour(day5, 3, 2)))

    return msgs


# ============================================================================
# СЦЕНАРИЙ 2: активные сценарии "сегодня"
# ============================================================================
def build_scenarios():
    msgs = []

    # --- 9999: реальное НСД ---
    # Движение в течение 30 минут ДО (нарушитель идёт по тоннелю)
    t0 = NOW - timedelta(minutes=45)
    for m_offset in (28, 22, 16, 10, 6, 3):
        msgs.append(ev(9999, "Датчик движения", "Обнаружено движение",
                       False, t0 - timedelta(minutes=m_offset)))

    # Триггер: открытие двери
    msgs.append(ev(9999, "КД Дверь", "Не замкнут", True, t0))

    # Каскад: через 2 минуты открывается люк (внутри окна cascade_openings_10min)
    msgs.append(ev(9999, "КД Люк", "Не замкнут", True,
                   t0 + timedelta(minutes=2)))

    # Движение ПОСЛЕ (подтверждение, что кто-то реально зашёл)
    for m_offset in (4, 6, 8):
        msgs.append(ev(9999, "Датчик движения", "Обнаружено движение",
                       False, t0 + timedelta(minutes=m_offset)))

    # --- 8888: одиночное открытие двери без движения (ложная тревога) ---
    # Например, дверь хлопнула от сквозняка или забыли закрыть
    msgs.append(ev(8888, "КД Дверь", "Не замкнут", True,
                   NOW - timedelta(minutes=45)))
    # Никакого движения ни ДО ни ПОСЛЕ
    msgs.append(ev(8888, "КД Дверь", "Норма", False,
                   NOW - timedelta(minutes=44)))

    # --- 7777: эскалация пожара за последние 6 часов ---
    for hours_ago in range(6, 0, -1):
        ts = NOW - timedelta(hours=hours_ago)
        # Рост температуры: 25 → 45°C
        temp = 25 + (6 - hours_ago) * 4
        msgs.append(ev(7777, "Датчик температуры", str(temp), False, ts,
                       system="Пожарная подсистема"))

        # Рост тревог: 3 в час-6, 5 в час-5, ..., 13 в час-1
        alarm_count = 3 + 2 * (6 - hours_ago)
        for i in range(alarm_count):
            msgs.append(ev(7777, "Датчик затопления", "Неисправен", True,
                           ts + timedelta(minutes=i * 4),
                           system="Пожарная подсистема"))
            msgs.append(ev(7777, "Ручной извещатель", "Неисправен", True,
                           ts + timedelta(minutes=i * 4 + 2),
                           system="Пожарная подсистема"))

    # --- 9999: плановые работы (снято с охраны) — должно быть отфильтровано ---
    # Добавим событие снятия с охраны ПЕРЕД одним из старых открытий
    # (на самом деле это уже в истории, но добавим ещё одно свежее для наглядности)
    # Для этого сценария просто проверим, что модель правильно отличает.
    # Не добавляем — сценарий 9999 уже "чистое" НСД без снятия с охраны.

    return msgs


# ============================================================================
# MAIN
# ============================================================================
async def main():
    producer = AIOKafkaProducer(
        bootstrap_servers=BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
    )
    await producer.start()

    history = build_history()
    scenarios = build_scenarios()
    all_msgs = history + scenarios

    print(f"📤 Отправляем {len(history)} фоновых + {len(scenarios)} сценарных "
          f"= {len(all_msgs)} событий в {INPUT_TOPIC}")

    sent = 0
    for m in all_msgs:
        await producer.send_and_wait(INPUT_TOPIC, m)
        sent += 1
        if sent % 500 == 0:
            print(f"   ...{sent}/{len(all_msgs)}")

    await producer.stop()

    print(f"✅ Отправлено {sent} событий")
    print()
    print("🔍 Ожидаемые результаты в логах main.py:")
    print("   • Через ~15 сек (или 10 мин event-time) после ingest:")
    print("     - NSD event pred: obj=9999 score=0.8.. alert=True   (реальное НСД)")
    print("     - NSD event pred: obj=8888 score=0.1.. alert=False  (ложная тревога)")
    print()
    print("   • Плановый цикл (раз в минуту в тесте):")
    print("     - Periodic: obj=9999 fire=... nsd_risk=0.2..")
    print("     - Periodic: obj=7777 fire=0.3.. nsd_risk=...")
    print("     - Periodic: obj=8888 fire=low nsd_risk=low")
    print()
    print("🌐 Kafka-топики: sensor.events.v1 / predictions.v1")


if __name__ == "__main__":
    asyncio.run(main())
