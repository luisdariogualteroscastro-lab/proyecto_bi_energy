# Runbook operativo — Plataforma de Datos Bia Energy

> Guía de operación para ingenieros de guardia (On-Call) a las 2 a.m.

## Cómo corre normalmente
- **Frecuencia:** Ejecución diaria batch (`make run`) y streaming continuo (`make stream`).
- **Duración esperada:** Batch completo menor a 120 segundos.
- **Artefactos generados:** `out/consumo_mensual.csv`, `out/dq_report.json`, `out/metrics.json`, `logs/pipeline.log`.

## Señales de que algo anda mal
| Síntoma | Dónde se ve | Causa probable |
|---|---|---|
| Pipeline termina con exit code != 0 | `logs/pipeline.log` / consola | Error de conexión a PostgreSQL, archivo corrupto sin estructurar o error de sintaxis en maestro |
| Cero filas procesadas o tasa de rechazo > 50% | `out/dq_report.json` | Cambio no anunciado en formato de origen o archivos vacíos |
| Alerta `FRONTERA_SIN_REPORTE` masiva | `out/alertas.json` / Kafka | Caída del broker Redpanda o fallo en fuente de telemetría |
| Conexión denegada con rol analista | Logs de Postgres / `make verificar` | Fallo en aplicación de permisos en DDL (`sql/init.sql`) |

## Procedimientos

### El pipeline falló a mitad de camino
- **¿Es seguro reintentar?:** Sí. El pipeline es **idempotente** gracias al uso de UPSERT (`ON CONFLICT DO UPDATE`) basado en versiones y llaves únicas `(frontera_id, timestamp)`.
- **Acción:**
  1. Revisar `logs/pipeline.log` para identificar la excepción exacta.
  2. Verificar estado de PostgreSQL: `docker-compose ps`.
  3. Reejecutar `make run`.

### Llegaron datos corregidos de un mes ya cerrado
- El pipeline absorbe automáticamente las correcciones si traen `version_lectura > 1` (ej. `consumos_2026-04_correccion.csv`). La regla de negocio actualiza el registro solo si la versión nueva es mayor o igual a la existente. No requiere intervención manual.

### La tasa de rechazo se disparó
1. Consultar la tabla de cuarentena: `SELECT * FROM cuarentena.registros_rechazados ORDER BY timestamp_rechazo DESC LIMIT 50;`.
2. Revisar `out/dq_report.json` para identificar si el fallo es por valores nulos, negativos, outliers o facturas huérfanas.
3. Si el proveedor envió datos con formato erróneo, reportar a operaciones de red sin alterar los datos ya consolidados.

### Sospecha de acceso indebido a PII
> **Primeros 15 minutos:**
1. **Qué NO hacés:** No borres contenedores ni reinicies servicios (destruye evidencia forense).
2. **Qué mirás:**
   - Consultar bitácora de auditoría: `SELECT * FROM audit.log_ejecuciones ORDER BY timestamp DESC LIMIT 20;`.
   - Verificar si el rol `analista` pudo leer tablas crudas (debería estar bloqueado por permisos).
3. **A quién avisás:** Escalar inmediatamente al equipo de Seguridad de la Información y Oficial de Protección de Datos (Ley 1581).

## Contactos y escalamiento
- **Data Platform Lead:** Ing. de Guardia (Slack: `#data-oncall`)
- **Seguridad / CISO:** `security@bia.energy`
