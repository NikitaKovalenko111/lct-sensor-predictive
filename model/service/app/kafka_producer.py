from aiokafka import AIOKafkaProducer
import json
from config import settings
from schemas import Prediction

async def create_producer():
    producer = AIOKafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap_servers,
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    return producer

async def send_prediction(producer: AIOKafkaProducer, prediction: Prediction):
    await producer.send_and_wait(
        settings.kafka_output_topic,
        value=prediction.dict()
    )