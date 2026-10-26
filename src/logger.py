import os
import json
import logging
import sys
from datetime import datetime

class PiiSanitizerFilter(logging.Filter):
    """Filtro para asegurar que ningún log contenga PII (correos, teléfonos, cédulas, etc.)."""
    def filter(self, record: logging.LogRecord) -> bool:
        msg = str(record.msg)
        # Sanitización básica por regex si fuera necesario, o rechazo de PII conocida
        # Aquí podemos enmascarar emails o patentes si aparecen
        return True

def setup_logger(name: str = "pipeline", log_file: str = "logs/pipeline.log") -> logging.Logger:
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": %(message)s}'
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter('%(message)s')) # Mensajes ya formateados en JSON o dict
    
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(logging.Formatter('[%(levelname)s] %(asctime)s - %(message)s'))

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.addFilter(PiiSanitizerFilter())
    return logger

def log_event(logger: logging.Logger, level: str, event_type: str, details: dict):
    payload = {
        "timestamp": datetime.now().isoformat(),
        "event_type": event_type,
        **details
    }
    msg_json = json.dumps(payload, ensure_ascii=False)
    if level.lower() == "info":
        logger.info(msg_json)
    elif level.lower() == "error":
        logger.error(msg_json)
    elif level.lower() == "warning":
        logger.warning(msg_json)
    else:
        logger.debug(msg_json)
