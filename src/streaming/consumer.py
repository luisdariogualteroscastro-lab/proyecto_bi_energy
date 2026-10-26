import os
import json
import csv
from datetime import datetime, timedelta
from kafka import KafkaConsumer
from src.config import KAFKA_BOOTSTRAP, KAFKA_TOPIC
from src.logger import setup_logger, log_event

logger = setup_logger("streaming_consumer")

def run_streaming_consumer():
    log_event(logger, "info", "STREAMING_START", {"mensaje": "Iniciando consumidor de streaming"})

    # Cargar límites de frontera para regla CONSUMO_FUERA_DE_BANDA
    limites = {}
    with open("data/maestros/limites_frontera.csv", "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            limites[row["frontera_id"].strip()] = float(row["max_kwh"])

    alertas = []
    
    # Estado para tracking de streaming
    # ultimo_ts por frontera para LECTURA_RETROACTIVA
    ultimos_ts = {}
    # Historial de intervalos de 15 min para FRONTERA_SIN_REPORTE
    # Cada frontera tiene un conjunto de timestamps esperados o recibidos
    # O rastreamos el último timestamp recibido y detectamos huecos de 45 min (3 intervalos de 15 min)
    ultima_llegada_frontera = {}

    try:
        consumer = KafkaConsumer(
            KAFKA_TOPIC,
            bootstrap_servers=[KAFKA_BOOTSTRAP],
            auto_offset_reset='earliest',
            enable_auto_commit=True,
            group_id='bia-streaming-group',
            consumer_timeout_ms=5000 # Terminar si no hay mensajes en 5 segundos
        )

        for message in consumer:
            try:
                event = json.loads(message.value.decode('utf-8'))
                f_id = event.get("frontera_id")
                ts_str = event.get("ts_medicion")
                kwh = float(event.get("kwh", 0))

                ts_dt = datetime.fromisoformat(ts_str)

                # Regla 1: CONSUMO_FUERA_DE_BANDA (kwh estrictamente mayor que max_kwh)
                max_val = limites.get(f_id, float('inf'))
                if kwh > max_val:
                    alertas.append({
                        "tipo": "CONSUMO_FUERA_DE_BANDA",
                        "frontera_id": f_id,
                        "ts": ts_str
                    })

                # Regla 2: LECTURA_RETROACTIVA (ts_medicion anterior a la última ya procesada para esa frontera)
                if f_id in ultimos_ts:
                    if ts_dt < ultimos_ts[f_id]:
                        alertas.append({
                            "tipo": "LECTURA_RETROACTIVA",
                            "frontera_id": f_id,
                            "ts": ts_str
                        })
                
                if f_id not in ultimos_ts or ts_dt > ultimos_ts[f_id]:
                    ultimos_ts[f_id] = ts_dt

                # Regla 3: FRONTERA_SIN_REPORTE (3 intervalos consecutivos de 15 min sin medición - 45 min)
                # Si la diferencia entre el ts actual y la última medición de esta frontera es > 30 minutos (3er intervalo ausente: 45 min)
                if f_id in ultima_llegada_frontera:
                    diff = (ts_dt - ultima_llegada_frontera[f_id]).total_seconds() / 60
                    if diff >= 45:
                        # El tercer intervalo ausente (45 min después del anterior)
                        ausente_ts = ultima_llegada_frontera[f_id] + timedelta(minutes=45)
                        alertas.append({
                            "tipo": "FRONTERA_SIN_REPORTE",
                            "frontera_id": f_id,
                            "ts": ausente_ts.isoformat()
                        })

                ultima_llegada_frontera[f_id] = ts_dt

            except Exception as e:
                logger.error(f"Error procesando evento de streaming: {str(e)}")

    except Exception as e:
        log_event(logger, "warning", "KAFKA_NOT_READY", {"error": str(e)})
        # Si Kafka no está arriba durante pruebas sin docker, podemos procesar los eventos directamente desde el archivo ndjson si existe
        if os.path.exists("data/eventos/mediciones_stream.ndjson"):
            log_event(logger, "info", "FALLBACK_NDJSON", {"mensaje": "Procesando stream desde archivo ndjson por fallback"})
            with open("data/eventos/mediciones_stream.ndjson", "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    event = json.loads(line)
                    f_id = event.get("frontera_id")
                    ts_str = event.get("ts_medicion")
                    kwh = float(event.get("kwh", 0))
                    ts_dt = datetime.fromisoformat(ts_str)

                    max_val = limites.get(f_id, float('inf'))
                    if kwh > max_val:
                        alertas.append({
                            "tipo": "CONSUMO_FUERA_DE_BANDA",
                            "frontera_id": f_id,
                            "ts": ts_str
                        })

                    if f_id in ultimos_ts and ts_dt < ultimos_ts[f_id]:
                        alertas.append({
                            "tipo": "LECTURA_RETROACTIVA",
                            "frontera_id": f_id,
                            "ts": ts_str
                        })
                    
                    if f_id not in ultimos_ts or ts_dt > ultimos_ts[f_id]:
                        ultimos_ts[f_id] = ts_dt

                    if f_id in ultima_llegada_frontera:
                        diff = (ts_dt - ultima_llegada_frontera[f_id]).total_seconds() / 60
                        if diff >= 45:
                            ausente_ts = ultima_llegada_frontera[f_id] + timedelta(minutes=45)
                            alertas.append({
                                "tipo": "FRONTERA_SIN_REPORTE",
                                "frontera_id": f_id,
                                "ts": ausente_ts.isoformat()
                            })

                    ultima_llegada_frontera[f_id] = ts_dt

    # Eliminar duplicados de alertas si los hay
    unique_alertas = []
    seen = set()
    for a in alertas:
        key = (a["tipo"], a["frontera_id"], a["ts"])
        if key not in seen:
            seen.add(key)
            unique_alertas.append(a)

    os.makedirs("out", exist_ok=True)
    with open("out/alertas.json", "w", encoding="utf-8") as f:
        json.dump(unique_alertas, f, indent=2, ensure_ascii=False)

    log_event(logger, "info", "STREAMING_SUCCESS", {"total_alertas": len(unique_alertas)})

if __name__ == "__main__":
    run_streaming_consumer()
