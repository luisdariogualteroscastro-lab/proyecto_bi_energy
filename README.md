# Bia Energy — Data Platform & Security Engineer Technical Test

**Candidato:** Dario  
**Módulo:** Plataforma de Datos, Ingesta Batch, Streaming, Calidad de Datos, Cifrado y Gobernanza (Ley 1581 / ISO 27001).

---

## 🚀 Cómo correr la solución (Contrato de Ejecución)

```bash
make setup      # Instala dependencias
make up         # Levanta infraestructura local (Postgres, MinIO, Redpanda)
make run        # Ejecuta pipeline batch completo (idempotente)
make run        # Segunda ejecución (prueba de idempotencia)
make stream     # Ejecuta consumidor de streaming y genera alertas
make test       # Corre suite de pruebas unitarias
make verificar  # Comprueba conectividad de roles y objetos declarados
make down       # Apaga infraestructura
```

---

## 📦 Qué se construyó

1. **Parte A — Ingesta y Modelado Batch:**
   - Ingesta dinámica y robusta de archivos maestros y heterogéneos de consumo (con soporte para comas, puntos y comas, conversión de MWh a kWh, y normalización de UTC a hora local Colombia `America/Bogota`).
   - Idempotencia garantizada mediante UPSERT en `core.fact_consumo_horario` basado en versión de lectura.
   - Zona de cuarentena activa (`cuarentena.registros_rechazados`) para nulos, negativos, outliers (> 1,000,000 kWh), facturas huérfanas y errores de parseo.

2. **Parte B — Calidad de Datos:**
   - Reglas B1 a B7 implementadas íntegramente (normalización horaria, unidades kWh, deduplicación por versión y orden lexicográfico, filtrado estricto, reporte de huecos y tratamiento de entradas hostiles en `clientes.csv`).

3. **Parte C — Seguridad, Privacidad y Gobernanza:**
   - Clasificación de datos en `data_classification.yaml`.
   - Cifrado simétrico AES-256-GCM a nivel de aplicación para PII (NIT, emails, celulares, representante legal) con hash SHA-256 para joins seguros.
   - Enmascaramiento automático de PII en texto libre (observaciones).
   - Menor privilegio en PostgreSQL con 3 roles (`rol_ingesta`, `rol_analista`, `rol_auditor`) y vistas analíticas aisladas (`analytics.v_consumo_diario`, `analytics.v_consumo_mensual`).
   - Bitácora append-only `audit.log_ejecuciones` protegida contra modificaciones mediante trigger SQL.
   - Auditoría de dependencias y mitigación de secretos heredados (`.env`).

4. **Parte D — Streaming:**
   - Consumidor Kafka/Redpanda con soporte de fallback a ndjson, detectando las 3 reglas de alerta exactas (`FRONTERA_SIN_REPORTE`, `CONSUMO_FUERA_DE_BANDA`, `LECTURA_RETROACTIVA`) con salida en `out/alertas.json`.

5. **Parte E y F — Observabilidad e IaC:**
   - Logs estructurados en JSON en `logs/pipeline.log` sin PII.
   - Métricas de ejecución en `out/metrics.json`.
   - `RUNBOOK.md` operativo para guardia nocturna.
   - Infraestructura como Código en Terraform (`infra/`) con bucket S3 cifrado con KMS, políticas y roles IAM.

---

## ✅ Qué NO se implementó (Declaración explícita)
- Todo el alcance principal y secundario requerido fue implementado al 100%. No hay elementos pendientes en `entrega.yaml`.
