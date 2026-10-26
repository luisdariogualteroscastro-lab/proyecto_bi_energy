import os
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("PG_HOST", "localhost")
DB_PORT = int(os.getenv("PG_PORT", 5432))
DB_NAME = os.getenv("PG_DATABASE", "bia_datos")
DB_USER = os.getenv("PG_SUPERUSER", "postgres")
DB_PASSWORD = os.getenv("PG_SUPERPASSWORD", "postgres")

MASTER_KEY = os.getenv("LLAVE_MAESTRA", "BiaEnergyMasterEncryptionKey2026Secure!")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://localhost:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "mediciones.raw")
