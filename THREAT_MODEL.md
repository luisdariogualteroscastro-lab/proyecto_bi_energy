# Modelo de amenazas — Bia Energy Data Platform

## 1. Alcance y diagrama de flujo de datos
Fuentes de datos crudos (Archivos CSV/JSON en MinIO/Local y Stream Redpanda) 
  ↓ (Infiltración de fronteras / Carga batch / Consumo streaming)
Pipeline Python (Validación DQ, normalización horaria, cifrado AES-256-GCM)
  ↓
PostgreSQL (Tablas `core`, `cuarentena`, `audit`, vistas `analytics`) 
  ↓
Salidas (`out/`, Vistas para analistas)

## 2. Activos y clasificación
| Activo | Dónde vive | Clasificación | Impacto si se compromete |
|---|---|---|---|
| NIT, email y celular de clientes | `core.dim_cliente` (cifrado) | Restringido-PII | Multas Ley 1581, fuga de datos personales |
| Consumo horario de fronteras | `core.fact_consumo_horario` | Confidencial | Pérdida de ventaja comercial, facturación errónea |
| Bitácora de ejecución | `audit.log_ejecuciones` | Interno | Pérdida de trazabilidad operativa |

## 3. Amenazas (STRIDE)
| # | Componente | STRIDE | Amenaza concreta | Probabilidad | Impacto | Control implementado | ¿Implementado? | ISO 27001:2022 Anexo A |
|---|---|---|---|---|---|---|---|---|
| T1 | Ingesta de Clientes | Tampering | Inyección SQL vía nombres de clientes maliciosos (`clientes.csv`) | M | A | Sanitización de strings y uso de parámetros bound en SQL | Sí | A.8.28 |
| T2 | Base de Datos Postgres | Elevation of Privilege | Rol analista escalando privilegios para leer tablas base con PII | B | A | Restricción estricta de GRANTs a vistas analíticas sin PII y sin acceso a tablas core | Sí | A.9.4 |
| T3 | Almacenamiento Postgres | Information Disclosure | Robo de dump de base de datos exponiendo NITs y contactos | M | A | Cifrado AES-256-GCM a nivel de aplicación (pgcrypto / pgcrypto app layer) | Sí | A.8.24 |
| T4 | Bitácora Audit | Tampering | Modificación o borrado de registros de auditoría por atacante con privilegios | B | A | Trigger que prohíbe explícitamente `UPDATE` y `DELETE` en `audit.log_ejecuciones` | Sí | A.8.15 |
| T5 | Pipeline Consumos | Denial of Service | Envío de archivos de consumo masivos corruptos o truncados | M | M | Rechazo controlado a cuarentena sin corromper datos históricos cargados | Sí | A.8.6 |
| T6 | Stream Redpanda | Spoofing | Inyección de telemetría falsa de fronteras | M | M | Validación estricta contra `limites_frontera.csv` y reglas de streaming | Sí | A.8.20 |
| T7 | Configuración | Information Disclosure | Exposición de secretos y credenciales en reposo | M | A | Parametrización total vía variables de entorno (`.env`) y remoción de hardcoded keys | Sí | A.5.17 |
| T8 | Consumo Batch | Repudiation | Desconocimiento de quién ejecutó corridas o modificó estados | B | M | Registro obligatorio append-only en `audit.log_ejecuciones` con usuario y métricas | Sí | A.8.15 |

## 4. Riesgos aceptados
- Se acepta la ausencia de cifrado TLS en la red local de desarrollo Docker entre componentes, ya que es un entorno aislado no productivo (en producción se impone TLS mTLS).

## 5. Qué haría distinto con más tiempo / en producción real
- Desplegar sobre Kubernetes con ArgoCD y Airflow administrando dependencias DAG complejas.
- Implementar HashiCorp Vault para gestión dinámica de secretos en lugar de variables de entorno estáticas.
