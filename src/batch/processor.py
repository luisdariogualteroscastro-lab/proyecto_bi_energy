import os
import glob
import csv
import json
import re
from datetime import datetime, timedelta
import psycopg2
from psycopg2.extras import execute_values
from src.config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
from src.logger import setup_logger, log_event
from src.security.crypto import encrypt_pii, hash_value, mask_pii_text

logger = setup_logger("batch_pipeline")

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

def run_batch_pipeline():
    start_time = datetime.now()
    log_event(logger, "info", "PIPELINE_START", {"mensaje": "Iniciando pipeline batch de consumo energético"})

    # Métricas para dq_report.json
    dq_metrics = {
        "filas_leidas": 0,
        "duplicados_exactos": 0,
        "duplicados_conflictivos": 0,
        "registros_negativos": 0,
        "registros_nulos": 0,
        "registros_outlier": 0,
        "registros_mwh_convertidos": 0,
        "correcciones_tardias_aplicadas": 0,
        "horas_sin_lectura_valida_total": 0,
        "horas_sin_lectura_valida_por_frontera": {},
        "fronteras_huerfanas_facturacion": 0,
        "clientes_con_pii_en_texto_libre": 0
    }

    conn = get_db_connection()
    conn.autocommit = False
    cursor = conn.cursor()

    try:
        # 0. Inicializar esquema (ejecutar init.sql si fuera necesario)
        with open("sql/init.sql", "r", encoding="utf-8") as f:
            cursor.execute(f.read())
        conn.commit()

        # 1. Cargar maestros (clientes, fronteras, limites)
        # Clientes con sanitización de inyecciones SQL y manejo de multiline CSV
        clientes_path = "data/maestros/clientes.csv"
        fronteras_path = "data/maestros/fronteras.csv"
        limites_path = "data/maestros/limites_frontera.csv"

        # Leer clientes.csv robustamente (incluso con comillas anidadas o saltos de línea internos)
        clientes_data = []
        with open(clientes_path, "r", encoding="latin1") as f:
            reader = csv.reader(f)
            header = next(reader)
            for row in reader:
                # Si el row está fragmentado por saltos de línea dentro de comillas, csv.reader lo maneja bien si usamos el iterador correcto o un parser custom.
                # Como csv.reader maneja multiline campos citados estándar, veamos:
                if len(row) >= 10:
                    c_id = row[0].strip()
                    razon = row[1].strip()
                    nit = row[2].strip()
                    email = row[3].strip()
                    celular = row[4].strip()
                    direccion = row[5].strip()
                    ciudad = row[6].strip()
                    depto = row[7].strip()
                    rep = row[8].strip()
                    obs = row[9].strip()
                elif len(row) > 0:
                    # En caso de filas con campos incompletos o mal formateados
                    c_id = row[0] if len(row) > 0 else ""
                    razon = row[1] if len(row) > 1 else ""
                    nit = row[2] if len(row) > 2 else ""
                    email = row[3] if len(row) > 3 else ""
                    celular = row[4] if len(row) > 4 else ""
                    direccion = row[5] if len(row) > 5 else ""
                    ciudad = row[6] if len(row) > 6 else ""
                    depto = row[7] if len(row) > 7 else ""
                    rep = row[8] if len(row) > 8 else ""
                    obs = row[9] if len(row) > 9 else ""
                else:
                    continue

                # Sanitizar SQL injection en razon_social o campos (ej: DROP TABLE)
                razon = re.sub(r"[';]+.*DROP\s+TABLE.*", "", razon, flags=I:=re.IGNORECASE)
                
                # Detectar PII en texto libre (observaciones)
                has_pii_obs = bool(re.search(r'(@|3\d{9}|CC\s*\d+)', obs, flags=re.IGNORECASE))
                if has_pii_obs:
                    dq_metrics["clientes_con_pii_en_texto_libre"] += 1
                obs_masked = mask_pii_text(obs)

                clientes_data.append((
                    c_id,
                    razon,
                    encrypt_pii(nit),
                    hash_value(nit),
                    encrypt_pii(email),
                    encrypt_pii(celular),
                    direccion,
                    ciudad,
                    depto,
                    encrypt_pii(rep),
                    encrypt_pii(obs_masked)
                ))

        cursor.executemany("""
            INSERT INTO core.dim_cliente (cliente_id, razon_social, nit_encrypted, nit_hash, email_encrypted, celular_encrypted, direccion, ciudad, departamento, rep_legal_encrypted, observaciones_encrypted)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (cliente_id) DO UPDATE SET razon_social = EXCLUDED.razon_social;
        """, clientes_data)

        # Cargar fronteras.csv
        fronteras_data = []
        with open(fronteras_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                fronteras_data.append((
                    row["frontera_id"].strip(),
                    row["codigo_sic"].strip(),
                    row["cliente_id"].strip(),
                    row["mercado"].strip(),
                    row["operador_red"].strip(),
                    int(row["nivel_tension"]) if row["nivel_tension"].isdigit() else 1,
                    row["fecha_registro"].strip(),
                    row["estado"].strip()
                ))

        cursor.executemany("""
            INSERT INTO core.dim_frontera (frontera_id, codigo_sic, cliente_id, mercado, operador_red, nivel_tension, fecha_registro, estado)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (frontera_id) DO NOTHING;
        """, fronteras_data)
        conn.commit()

        # Diccionario de límites para validación de outliers si es necesario (o stream)
        limites_dict = {}
        with open(limites_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                limites_dict[row["frontera_id"].strip()] = {
                    "min": float(row["min_kwh"]),
                    "max": float(row["max_kwh"])
                }

        # 2. Descubrir y procesar archivos en data/consumos/ (orden lexicográfico)
        consumos_files = sorted(glob.glob("data/consumos/*.csv"))
        
        # Almacenaremos todas las lecturas válidas en memoria o estructuras para deduplicación global por (frontera_id, timestamp)
        # (frontera_id, timestamp) -> lista de tuplas (consumo_kwh, version_lectura, calidad_lectura, file_index)
        lecturas_map = {}

        for file_idx, filepath in enumerate(consumos_files):
            filename = os.path.basename(filepath)
            log_event(logger, "info", "PROCESS_CONSUMO_FILE", {"archivo": filename})
            
            # Detectar separador y formato leyendo primera línea
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                first_line = f.readline()
            
            sep = ";" if ";" in first_line else ","
            
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                reader = csv.reader(f, delimiter=sep)
                header = next(reader)
                
                for row in reader:
                    if not row or len(row) < 5:
                        continue
                    dq_metrics["filas_leidas"] += 1
                    
                    try:
                        frontera_id = row[0].strip()
                        raw_ts = row[1].strip()
                        
                        # Determinar columnas según header o estructura del archivo
                        # Archivo 2 (2026-02) tiene timestamp_utc
                        is_utc = "utc" in header[1].lower() or "z" in raw_ts.lower()
                        
                        # Manejo de valor y unidad
                        # Algunos archivos pueden tener columna 'unidad' (ej: consumos_2026-03.csv)
                        unidad = "kWh"
                        val_str = ""
                        version = 1
                        calidad = "OK"
                        
                        if len(row) >= 6 and ("mwh" in row[3].lower() or "kwh" in row[3].lower() or row[3] in ["kWh", "MWh"]):
                            unidad = row[3].strip()
                            val_str = row[2].strip()
                            version = int(row[4]) if row[4].isdigit() else 1
                            calidad = row[5].strip()
                        else:
                            val_str = row[2].strip()
                            version = int(row[3]) if row[3].isdigit() else 1
                            calidad = row[4].strip()

                        # Normalizar decimales (coma por punto si aplica, ej: '163,795')
                        val_str = val_str.replace(",", ".")
                        
                        if val_str == "" or val_str.lower() == "null" or val_str.lower() == "nan":
                            dq_metrics["registros_nulos"] += 1
                            cursor.execute(
                                "INSERT INTO cuarentena.registros_rechazados (origen_archivo, payload_crudo, motivo_rechazo) VALUES (%s, %s, %s)",
                                (filename, ",".join(row), "VALOR_NULO_O_VACIO")
                            )
                            continue
                        
                        kwh = float(val_str)
                        
                        # Convertir MWh a kWh si la unidad es MWh
                        if unidad.upper() == "MWh":
                            kwh = kwh * 1000.0
                            dq_metrics["registros_mwh_convertidos"] += 1

                        # Regla B4: Negativos u Outliers (> 1,000,000 kWh)
                        if kwh < 0:
                            dq_metrics["registros_negativos"] += 1
                            cursor.execute(
                                "INSERT INTO cuarentena.registros_rechazados (origen_archivo, payload_crudo, motivo_rechazo) VALUES (%s, %s, %s)",
                                (filename, ",".join(row), "VALOR_NEGATIVO")
                            )
                            continue
                        
                        if kwh > 1000000.0:
                            dq_metrics["registros_outlier"] += 1
                            cursor.execute(
                                "INSERT INTO cuarentena.registros_rechazados (origen_archivo, payload_crudo, motivo_rechazo) VALUES (%s, %s, %s)",
                                (filename, ",".join(row), "OUTLIER_FISICAMENTE_IMPOSIBLE")
                            )
                            continue

                        # Regla B1: Zona horaria (America/Bogota, UTC-5 fijo)
                        # Si viene en UTC, restar 5 horas
                        dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                        if is_utc or dt.tzinfo is not None:
                            # Convertir a naive UTC o restar offset
                            # Si tiene offset UTC, pasarlo a America/Bogota (UTC-5)
                            # O si el string tenía Z, dt está en UTC. Restamos 5 horas para pasarlo a local Colombia.
                            if is_utc or "Z" in raw_ts:
                                dt = dt.replace(tzinfo=None) - timedelta(hours=5)
                            else:
                                # Si tiene otro tzinfo
                                pass
                        ts_local = dt.replace(tzinfo=None) # Guardar como timestamp local de Colombia

                        # Detectar si es corrección tardía
                        if "correccion" in filename.lower() or version > 1:
                            dq_metrics["correcciones_tardias_aplicadas"] += 1

                        key = (frontera_id, ts_local)
                        if key not in lecturas_map:
                            lecturas_map[key] = []
                        lecturas_map[key].append((kwh, version, calidad, file_idx))

                    except Exception as e:
                        cursor.execute(
                            "INSERT INTO cuarentena.registros_rechazados (origen_archivo, payload_crudo, motivo_rechazo) VALUES (%s, %s, %s)",
                            (filename, ",".join(row), f"ERROR_PARSING: {str(e)}")
                        )

        # 3. Aplicar regla B3 de deduplicación:
        # Para una misma (frontera_id, timestamp) gana la lectura con mayor version_lectura.
        # Si empatan en versión, gana la última en orden de archivo (file_index mayor).
        final_lecturas = []
        for (frontera_id, ts_local), candidatas in lecturas_map.items():
            # Ordenar candidatas por version_lectura desc, file_idx desc
            candidatas.sort(key=lambda x: (x[1], x[3]), reverse=True)
            ganador = candidatas[0]
            
            # Contar duplicados descartados
            if len(candidatas) > 1:
                # Ver si las versiones eran iguales o distintas
                v_max = candidatas[0][1]
                v_second = candidatas[1][1]
                if v_max == v_second:
                    dq_metrics["duplicados_exactos"] += len(candidatas) - 1
                else:
                    dq_metrics["duplicados_conflictivos"] += len(candidatas) - 1

            final_lecturas.append((
                frontera_id,
                ts_local,
                ganador[0],
                ganador[1],
                ganador[2],
                hash_value(f"{frontera_id}|{ts_local}|{ganador[0]}")
            ))

        # Cargar lecturas válidas a PostgreSQL (Idempotente con UPSERT)
        if final_lecturas:
            execute_values(cursor, """
                INSERT INTO core.fact_consumo_horario (frontera_id, timestamp, consumo_kwh, version_lectura, calidad_lectura, hash_integridad)
                VALUES %s
                ON CONFLICT (frontera_id, timestamp) 
                DO UPDATE SET 
                    consumo_kwh = EXCLUDED.consumo_kwh,
                    version_lectura = EXCLUDED.version_lectura,
                    calidad_lectura = EXCLUDED.calidad_lectura,
                    hash_integridad = EXCLUDED.hash_integridad
                WHERE EXCLUDED.version_lectura >= core.fact_consumo_horario.version_lectura;
            """, final_lecturas)

        conn.commit()

        # 4. Procesar Facturación y detectar huérfanas (Regla B6)
        facturacion_files = glob.glob("data/facturacion/*.json")
        for fpath in facturacion_files:
            with open(fpath, "r", encoding="utf-8") as f:
                fact_doc = json.load(f)
                for factura in fact_doc.get("facturas", []):
                    f_id = factura.get("frontera_id")
                    # Verificar si existe en dim_frontera
                    cursor.execute("SELECT 1 FROM core.dim_frontera WHERE frontera_id = %s", (f_id,))
                    if not cursor.fetchone():
                        dq_metrics["fronteras_huerfanas_facturacion"] += 1
                        cursor.execute(
                            "INSERT INTO cuarentena.registros_rechazados (origen_archivo, payload_crudo, motivo_rechazo) VALUES (%s, %s, %s)",
                            (os.path.basename(fpath), json.dumps(factura), "FACTURA_HUERFANA_SIN_FRONTERA")
                        )

        conn.commit()

        # 5. Calcular Huecos (Regla B5) y estadísticas por frontera
        # Una hora sin lectura válida es un hueco. Calculamos el rango de horas esperado por frontera en los meses cargados o por cada frontera.
        cursor.execute("SELECT DISTINCT frontera_id FROM core.dim_frontera")
        fronteras = [r[0] for r in cursor.fetchall()]
        
        total_huecos = 0
        huecos_por_frontera = {}

        for f_id in fronteras:
            cursor.execute("""
                SELECT min(timestamp), max(timestamp) FROM core.fact_consumo_horario WHERE frontera_id = %s
            """, (f_id,))
            res = cursor.fetchone()
            if res and res[0] and res[1]:
                min_ts, max_ts = res[0], res[1]
                # Contar cuantas horas hay entre min_ts y max_ts (pasos de 1 hora)
                expected_hours = int((max_ts - min_ts).total_seconds() / 3600) + 1
                cursor.execute("""
                    SELECT count(*) FROM core.fact_consumo_horario WHERE frontera_id = %s
                """, (f_id,))
                actual_hours = cursor.fetchone()[0]
                huecos = max(0, expected_hours - actual_hours)
                if huecos > 0:
                    huecos_por_frontera[f_id] = huecos
                    total_huecos += huecos

        dq_metrics["horas_sin_lectura_valida_total"] = total_huecos
        dq_metrics["horas_sin_lectura_valida_por_frontera"] = huecos_por_frontera

        # 6. Generar salidas requeridas en out/
        os.makedirs("out", exist_ok=True)
        os.makedirs("logs", exist_ok=True)

        # out/consumo_mensual.csv
        cursor.execute("""
            SELECT frontera_id, to_char(timestamp, 'YYYY-MM') as mes, round(sum(consumo_kwh), 3), count(id)
            FROM core.fact_consumo_horario
            GROUP BY frontera_id, to_char(timestamp, 'YYYY-MM')
            ORDER BY frontera_id, mes;
        """)
        rows_mensual = cursor.fetchall()
        
        with open("out/consumo_mensual.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["frontera_id", "mes", "consumo_kwh", "horas_con_dato"])
            for r in rows_mensual:
                writer.writerow([r[0], r[1], f"{r[2]:.3f}", r[3]])

        # out/dq_report.json
        with open("out/dq_report.json", "w", encoding="utf-8") as f:
            json.dump(dq_metrics, f, indent=2, ensure_ascii=False)

        # out/metrics.json
        duration = (datetime.now() - start_time).total_seconds()
        metrics_doc = {
            "timestamp_corrida": datetime.now().isoformat(),
            "duracion_segundos": duration,
            "filas_leidas": dq_metrics["filas_leidas"],
            "filas_cargadas": len(final_lecturas),
            "filas_rechazadas": dq_metrics["registros_nulos"] + dq_metrics["registros_negativos"] + dq_metrics["registros_outlier"] + dq_metrics["fronteras_huerfanas_facturacion"]
        }
        with open("out/metrics.json", "w", encoding="utf-8") as f:
            json.dump(metrics_doc, f, indent=2, ensure_ascii=False)

        # Registrar en bitácora de auditoría (audit.log_ejecuciones)
        cursor.execute("""
            INSERT INTO audit.log_ejecuciones (usuario, etapa, filas_leidas, filas_cargadas, resultado)
            VALUES (%s, %s, %s, %s, %s)
        """, (DB_USER, "batch_pipeline", dq_metrics["filas_leidas"], len(final_lecturas), json.dumps(metrics_doc)))
        conn.commit()

        log_event(logger, "info", "PIPELINE_SUCCESS", {"mensaje": "Pipeline batch completado exitosamente", "metricas": metrics_doc})

    except Exception as e:
        conn.rollback()
        log_event(logger, "error", "PIPELINE_ERROR", {"error": str(e)})
        raise e
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    run_batch_pipeline()
