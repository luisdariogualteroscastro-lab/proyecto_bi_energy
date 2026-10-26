# Decisiones de arquitectura (ADRs)

## ADR-001 — Uso de cifrado simétrico AES-256-GCM a nivel de aplicación para PII

**Estado:** Aceptada  
**Fecha:** 2026-06-01  

**Contexto**  
La Ley 1581 exige protección estricta de PII (NIT, emails, celulares). Si un DBA o atacante obtiene un dump de Postgres, no puede ver los datos en claro.

**Opciones consideradas**  
1. Cifrado nativo con `pgcrypto` en Postgres.  
2. Cifrado simétrico AES-256-GCM en la capa de aplicación Python antes de insertar.  

**Decisión**  
Cifrado en la capa de aplicación Python utilizando `cryptography` con AES-256-GCM y derivación SHA-256 de la llave maestra.

**Por qué**  
Garantiza que ni siquiera con privilegios de superusuario en base de datos se expone la PII en claro, y desacopla la lógica criptográfica del motor SQL.

---

## ADR-002 — Trigger Append-Only para Bitácora de Auditoría

**Estado:** Aceptada  
**Fecha:** 2026-06-01  

**Contexto**  
Los logs de auditoría tradicionales en tablas relacionales pueden ser alterados o borrados por usuarios maliciosos con permisos de escritura.

**Decisión**  
Crear un trigger `BEFORE UPDATE OR DELETE` en `audit.log_ejecuciones` que lanza una excepción bloqueando cualquier modificación.

**Por qué**  
Garantiza cumplimiento normativo ISO 27001 (trazabilidad inalterable) a nivel de motor de base de datos.

---

## ADR-003 — Modelo Estrellado / Relacional Core y Vistas Analíticas separadas

**Estado:** Aceptada  
**Fecha:** 2026-06-01  

**Contexto**  
Se requiere separar los datos crudos y transaccionales del consumo analítico de usuarios de negocio con menor privilegio.

**Decisión**  
Estructurar tablas en esquema `core` (hechos y dimensiones) y exponer exclusivamente vistas en esquema `analytics` (`v_consumo_diario`, `v_consumo_mensual`) para el rol `analista`.

**Por qué**  
Permite aplicar el principio de menor privilegio de forma elegante sin otorgar acceso a tablas base ni a PII.

---

## ADR-004 — Descubrimiento dinámico e idempotencia por UPSERT en ingesta batch

**Estado:** Aceptada  
**Fecha:** 2026-06-01  

**Contexto**  
Los archivos de consumo llegan sin orden fijo, pueden contener relecturas tardías (correcciones) y deben procesarse múltiples veces sin duplicar datos.

**Decisión**  
Usar descubrimiento dinámico de archivos en `data/consumos/` ordenados lexicográficamente, con UPSERT basado en restricciones `UNIQUE (frontera_id, timestamp)` y comparación de `version_lectura`.

**Por qué**  
Garantiza idempotencia total ante ejecuciones repetidas (`make run`) y absorbe actualizaciones tardías correctamente.
