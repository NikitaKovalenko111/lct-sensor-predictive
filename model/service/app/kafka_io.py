import json
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from .config import settings

async def create_consumer() -> AIOKafkaConsumer:
    c = AIOKafkaConsumer(
        settings.kafka_input_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        auto_offset_reset="earliest",
    )
    await c.start()
    return c

async def create_producer() -> AIOKafkaProducer:
    p = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
    )
    await p.start()
    return p

async def publish_prediction(producer: AIOKafkaProducer, prediction) -> None:
    await producer.send_and_wait(
        settings.kafka_output_topic,
        prediction.model_dump(mode="json"),
        key=str(prediction.object_id).encode("utf-8"),
    )
