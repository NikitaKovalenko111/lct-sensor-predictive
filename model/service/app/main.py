import asyncio
import logging
from datetime import datetime
from kafka_consumer import create_consumer
from kafka_producer import create_producer, send_prediction
from feature_engine import FeatureEngine
from predictor import Predictor
from db import save_event, SensorEventDB
from schemas import SensorEvent
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ModelService:
    def __init__(self):
        self.feature_engine = FeatureEngine()
        self.predictor = Predictor()
        self.objects_to_predict = set()  # Объекты, для которых нужен прогноз
    
    async def process_event(self, event_data: dict):
        """Обрабатывает одно событие датчика."""
        try:
            event = SensorEvent(**event_data)
            
            # Сохраняем в БД
            db_event = SensorEventDB(
                event_id=event.event_id,
                object_id=event.object_id,
                sensor_type=event.sensor_type,
                value=event.value,
                is_alarm=event.is_alarm,
                timestamp=event.timestamp
            )
            save_event(db_event)
            
            # Помечаем объект для прогноза
            self.objects_to_predict.add(event.object_id)
            
        except Exception as e:
            logger.error(f"Ошибка обработки события: {e}")
    
    async def run_predictions(self, producer):
        """Периодически делает прогнозы для накопленных объектов."""
        while True:
            await asyncio.sleep(settings.prediction_interval)
            
            if not self.objects_to_predict:
                continue
            
            logger.info(f"Делаем прогнозы для {len(self.objects_to_predict)} объектов")
            
            for object_id in list(self.objects_to_predict):
                try:
                    timestamp = datetime.utcnow()
                    
                    # Вычисляем фичи
                    features = self.feature_engine.get_all_features(object_id, timestamp)
                    
                    # Делаем 3 прогноза
                    fire_pred = self.predictor.predict_fire_risk(features)
                    nsd_risk_pred = self.predictor.predict_nsd_risk(features)
                    
                    # Отправляем в Kafka
                    await send_prediction(producer, fire_pred)
                    await send_prediction(producer, nsd_risk_pred)
                    
                    logger.info(
                        f"Object {object_id}: fire={fire_pred.risk_score:.3f}, "
                        f"nsd_risk={nsd_risk_pred.risk_score:.3f}"
                    )
                    
                except Exception as e:
                    logger.error(f"Ошибка прогноза для объекта {object_id}: {e}")
            
            self.objects_to_predict.clear()
    
    async def run(self):
        """Главный цикл сервиса."""
        consumer = await create_consumer()
        producer = await create_producer()
        
        await consumer.start()
        await producer.start()
        
        # Запускаем задачу прогнозов в фоне
        prediction_task = asyncio.create_task(self.run_predictions(producer))
        
        try:
            async for msg in consumer:
                await self.process_event(msg.value)
        finally:
            prediction_task.cancel()
            await consumer.stop()
            await producer.stop()

if __name__ == "__main__":
    service = ModelService()
    asyncio.run(service.run())