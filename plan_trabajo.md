# Plan de Trabajo — Prueba Técnica Data Platform & Security Engineer

**Candidato:** Data Platform & Security Engineer (Mid)  
**Empresa:** Bia Energy · Equipo de Data  

---

## 🎯 Objetivo General
Desarrollar una plataforma de datos integral, segura e idempotente en Python y SQL para procesar datos batch y streaming de consumo energético, aplicando reglas rigurosas de calidad de datos, gobernanza (Ley 1581 / ISO 27001), cifrado de PII y menor privilegio en PostgreSQL.

---

## 🗓️ Fases de Ejecución

### Fase 0: Auditoría Inicial y Hardening de Configuración / Seguridad
- [ ] **Auditar scaffolding heredado:**
  - Eliminar secreto expuesto (`S3cr3t_H3r3d4d0`) de `config/pipeline.yaml` y sustituir por variables de entorno inyectadas.
  - Actualizar dependencias obsoletas en `requirements.txt`.
  - Configurar Docker Compose sin exponer contraseñas por defecto ni servicios innecesarios en claro.
- [ ] **Inspeccionar datos de entrada (`data/`):**
  - Analizar variaciones de encodings, separadores, unidades (kWh vs MWh), nombres de columnas e inyecciones/comillas en `clientes.csv`.

---

### Fase 1: Diseño de Base de Datos y Gobernanza de Datos (Parte C - 31 pts)
- [ ] **Definir `data_classification.yaml`:**
  - Etiquetar cada atributo en `Público`, `Interno`, `Confidencial`, `Restringido-PII`.
- [ ] **Crear Scripts DDL (`sql/init.sql` / `sql/roles.sql`):**
  - Configurar extensión `pgcrypto` o esquema de cifrado de PII en reposo.
  - Crear tablas analíticas (ej. `core.fact_consumo_horario`, `core.dim_cliente`, `core.dim_frontera`, `cuarentena.registros_rechazados`).
  - Crear bitácora append-only (`audit.log_ejecuciones`) con revocación explícita de `UPDATE` y `DELETE`.
  - Definir vista analítica `analytics.v_consumo_diario` sin PII en claro.
  - Crear y configurar los 3 roles de menor privilegio: `ingesta`, `analista`, y `auditor`.

---

### Fase 2: Pipeline Batch - Ingesta, Calidad y Carga (Partes A y B - 40 pts)
- [ ] **Módulo de Ingesta & Descubrimiento Dinámico:**
  - Descubrir automáticamente archivos en `data/consumos/`.
  - Soportar heterogeneidad de formatos (encodings, delimitadores, unidades, zonas horarias).
- [ ] **Motor de Calidad de Datos & Normalización:**
  - Normalizar timestamps a hora legal de Colombia (`America/Bogota`, UTC-5).
  - Convertir todas las lecturas a `kWh`.
  - Detectar y enmascarar PII en texto libre (`observaciones` en `clientes.csv`).
  - Sanitizar inyecciones SQL / campos hostiles.
  - Aplicar reglas de deduplicación (gana mayor `version_lectura`, empate por orden lexicográfico).
  - Manejo de relecturas/datos tardíos (`consumos_2026-04_correccion.csv`).
  - Filtrado de nulos, negativos y outliers (> 1,000,000 kWh) enviándolos a cuarentena.
- [ ] **Salidas Batch:**
  - `out/consumo_mensual.csv` (resumen mensual por frontera).
  - `out/dq_report.json` (métricas completas de calidad de datos).

---

### Fase 3: Pipeline Streaming & Alertas (Parte D - 9 pts)
- [ ] **Consumidor Kafka / Redpanda (`src/streaming/consumer.py`):**
  - Leer el tópico `mediciones.raw` alimentado por `producer.py`.
  - Detectar las 3 condiciones de alerta exactas:
    1. `FRONTERA_SIN_REPORTE` (3 intervalos consecutivos de 15 min sin reporte).
    2. `CONSUMO_FUERA_DE_BANDA` (kWh > `max_kwh` de `limites_frontera.csv`).
    3. `LECTURA_RETROACTIVA` (`ts_medicion` anterior a la última procesada).
  - Finalización autónoma al terminar el stream de eventos.
  - Salida: `out/alertas.json`.

---

### Fase 4: Observabilidad, Operación e Infraestructura IaC (Partes E y F - 13 pts)
- [ ] **Módulo de Observabilidad:**
  - Generar logs estructurados en JSON en `logs/pipeline.log` (verificar ausencia total de PII).
  - Generar métricas operativas de la corrida en `out/metrics.json`.
  - Redactar `RUNBOOK.md` con procedimiento operativo para fallas.
- [ ] **Infraestructura como Código (Terraform):**
  - Crear archivos `.tf` en `infra/` (S3 cifrado con KMS, políticas IAM, roles).
  - Validar mediante `terraform validate`.

---

### Fase 5: Pruebas, Verificación y Documentación (Partes G y H - 7 pts)
- [ ] **Automatización del Contrato (`Makefile`):**
  - Implementar targets: `setup`, `up`, `run`, `stream`, `test`, `down`, `clean`.
  - Completar `entrega.yaml` con credenciales efímeras y objetos creados.
  - Correr `make verificar` para asegurar conectividad de roles y objetos.
- [ ] **Suite de Pruebas Unitarias e Integración (`tests/`):**
  - Pruebas de idempotencia, calidad de datos, cifrado y permisos de roles.
- [ ] **Documentación Final:**
  - Llenar `THREAT_MODEL.md` (metodología STRIDE + ISO 27001).
  - Llenar `DECISIONS.md` (ADRs de arquitectura y modelo de datos).
  - Llenar `SECURITY.md` (política de seguridad).
  - Llenar `AI_USAGE.md` (herramientas, prompts, decisiones y error corregido a la IA).
  - Actualizar `README.md` principal con instrucciones de ejecución.

---

## 📌 Principales Riesgos y Puntos Eliminatorios a Prevenir
1. **PII en claro:** Asegurar que ningún log, salida en `out/` o vista para `analista` exponga datos personales.
2. **Secretos heredados:** Verificar que `S3cr3t_H3r3d4d0` haya sido removido al 100%.
3. **Inyección SQL:** Validar sanitización de strings en `clientes.csv` para evitar la caída de tablas.
4. **Falta de Idempotencia:** Garantizar que reejecutar `make run` produzca exactamente el mismo resultado sin duplicar.
