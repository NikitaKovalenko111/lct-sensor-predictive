from aiokafka import AIOKafkaConsumer
import json
from config import settings
from schemas import SensorEvent

async def create_consumer():
    consumer = AIOKafkaConsumer(
        settings.kafka_input_topic,
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id=settings.kafka_consumer_group,
        value_deserializer=lambda m: json.loads(m.decode('utf-8'))
    )
    return consumer