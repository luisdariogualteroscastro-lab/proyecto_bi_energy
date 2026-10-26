-- ===========================================================================
-- DDL Principal - Bia Energy Data Platform
-- ===========================================================================

-- Habilitar extensión pgcrypto para cifrado en reposo
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Crear esquemas
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS cuarentena;
CREATE SCHEMA IF NOT EXISTS audit;
CREATE SCHEMA IF NOT EXISTS analytics;

-- ---------------------------------------------------------------------------
-- 1. Tablas Core y Dimensiones
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS core.dim_cliente (
    cliente_id VARCHAR(50) PRIMARY KEY,
    razon_social VARCHAR(255) NOT NULL,
    nit_encrypted TEXT NOT NULL,                -- Cifrado (Restringido-PII)
    nit_hash VARCHAR(64),                       -- Hash para joins/busquedas sin descifrar
    email_encrypted TEXT,                       -- Cifrado (Restringido-PII)
    celular_encrypted TEXT,                     -- Cifrado (Restringido-PII)
    direccion TEXT,
    ciudad VARCHAR(100),
    departamento VARCHAR(100),
    rep_legal_encrypted TEXT,                   -- Cifrado (Restringido-PII)
    observaciones_encrypted TEXT,               -- Cifrado con PII enmascarada
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS core.dim_frontera (
    frontera_id VARCHAR(50) PRIMARY KEY,
    codigo_sic VARCHAR(50) NOT NULL,
    cliente_id VARCHAR(50) REFERENCES core.dim_cliente(cliente_id),
    mercado VARCHAR(50),
    operador_red VARCHAR(50),
    nivel_tension INT,
    fecha_registro DATE,
    estado VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS core.fact_consumo_horario (
    id SERIAL PRIMARY KEY,
    frontera_id VARCHAR(50) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    consumo_kwh NUMERIC(12, 3) NOT NULL,
    version_lectura INT NOT NULL DEFAULT 1,
    calidad_lectura VARCHAR(50) NOT NULL,
    hash_integridad VARCHAR(64),
    loaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_frontera_timestamp UNIQUE (frontera_id, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_consumo_frontera_ts ON core.fact_consumo_horario(frontera_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_consumo_version ON core.fact_consumo_horario(frontera_id, timestamp, version_lectura);

-- ---------------------------------------------------------------------------
-- 2. Cuarentena
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS cuarentena.registros_rechazados (
    id SERIAL PRIMARY KEY,
    origen_archivo VARCHAR(255) NOT NULL,
    payload_crudo TEXT NOT NULL,
    motivo_rechazo TEXT NOT NULL,
    timestamp_rechazo TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- 3. Bitácora de Auditoría (Append-Only)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS audit.log_ejecuciones (
    id SERIAL PRIMARY KEY,
    usuario VARCHAR(100) NOT NULL,
    etapa VARCHAR(100) NOT NULL,
    filas_leidas INT DEFAULT 0,
    filas_cargadas INT DEFAULT 0,
    resultado JSONB,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Función y trigger para prohibir UPDATE y DELETE en audit.log_ejecuciones
CREATE OR REPLACE FUNCTION audit.fn_prevent_modifications()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'La tabla audit.log_ejecuciones es append-only. No se permiten UPDATE ni DELETE.';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_prevent_audit_mods ON audit.log_ejecuciones;
CREATE TRIGGER trg_prevent_audit_mods
    BEFORE UPDATE OR DELETE ON audit.log_ejecuciones
    FOR EACH ROW EXECUTE FUNCTION audit.fn_prevent_modifications();

-- ---------------------------------------------------------------------------
-- 4. Vistas Analíticas (para rol analista - sin PII)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW analytics.v_consumo_diario AS
SELECT
    f.frontera_id,
    f.codigo_sic,
    f.mercado,
    f.operador_red,
    date_trunc('day', c.timestamp) AS fecha,
    sum(c.consumo_kwh) AS consumo_total_kwh,
    count(c.id) AS lecturas_validas
FROM core.fact_consumo_horario c
JOIN core.dim_frontera f ON c.frontera_id = f.frontera_id
GROUP BY f.frontera_id, f.codigo_sic, f.mercado, f.operador_red, date_trunc('day', c.timestamp);

CREATE OR REPLACE VIEW analytics.v_consumo_mensual AS
SELECT
    f.frontera_id,
    to_char(c.timestamp AT TIME ZONE 'America/Bogota', 'YYYY-MM') AS mes,
    round(sum(c.consumo_kwh), 3) AS consumo_kwh,
    count(c.id) AS horas_con_dato
FROM core.fact_consumo_horario c
JOIN core.dim_frontera f ON c.frontera_id = f.frontera_id
GROUP BY f.frontera_id, to_char(c.timestamp AT TIME ZONE 'America/Bogota', 'YYYY-MM');

-- ---------------------------------------------------------------------------
-- 5. Roles y Permisos (Menor Privilegio - C4)
-- ---------------------------------------------------------------------------

DO $$
DECLARE
    ingesta_user TEXT := current_setting('env.PG_ROL_INGESTA_USER', true);
    ingesta_pass TEXT := current_setting('env.PG_ROL_INGESTA_PASSWORD', true);
    analista_user TEXT := current_setting('env.PG_ROL_ANALISTA_USER', true);
    analista_pass TEXT := current_setting('env.PG_ROL_ANALISTA_PASSWORD', true);
    auditor_user TEXT := current_setting('env.PG_ROL_AUDITOR_USER', true);
    auditor_pass TEXT := current_setting('env.PG_ROL_AUDITOR_PASSWORD', true);
BEGIN
    -- Si no existen las variables de sesión, usar valores por defecto seguros
    IF ingesta_user IS NULL OR ingesta_user = '' THEN ingesta_user := 'rol_ingesta'; END IF;
    IF ingesta_pass IS NULL OR ingesta_pass = '' THEN ingesta_pass := 'rol_ingesta_pass'; END IF;
    IF analista_user IS NULL OR analista_user = '' THEN analista_user := 'rol_analista'; END IF;
    IF analista_pass IS NULL OR analista_pass = '' THEN analista_pass := 'rol_analista_pass'; END IF;
    IF auditor_user IS NULL OR auditor_user = '' THEN auditor_user := 'rol_auditor'; END IF;
    IF auditor_pass IS NULL OR auditor_pass = '' THEN auditor_pass := 'rol_auditor_pass'; END IF;

    -- Crear roles si no existen
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = ingesta_user) THEN
        EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', ingesta_user, ingesta_pass);
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = analista_user) THEN
        EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', analista_user, analista_pass);
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = auditor_user) THEN
        EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', auditor_user, auditor_pass);
    END IF;
END
$$;

-- Otorgar permisos mínimos por rol
-- Rol INGESTA: escribe en core y cuarentena, inserta en audit
GRANT USAGE ON SCHEMA core, cuarentena, audit TO rol_ingesta;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA core, cuarentena TO rol_ingesta;
GRANT INSERT, SELECT ON TABLE audit.log_ejecuciones TO rol_ingesta;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA core, cuarentena, audit TO rol_ingesta;

-- Rol ANALISTA: solo lee vistas analíticas en schema analytics. Sin acceso a tablas base ni PII. No escribe nada.
GRANT USAGE ON SCHEMA analytics TO rol_analista;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO rol_analista;

-- Rol AUDITOR: lee la bitácora de auditoría y cuarentena. Sin PII.
GRANT USAGE ON SCHEMA audit, cuarentena TO rol_auditor;
GRANT SELECT ON TABLE audit.log_ejecuciones TO rol_auditor;
GRANT SELECT ON ALL TABLES IN SCHEMA cuarentena TO rol_auditor;
