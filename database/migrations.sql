-- =============================================================================
-- MIGRACIONES HISTÓRICAS DE GEOVIVIENDA
-- =============================================================================
-- Este archivo contiene solo las migraciones aplicadas al schema base (schema.sql).
-- Cada bloque es idempotente (IF EXISTS / IF NOT EXISTS / DO $$ BEGIN/END $$).
-- Se aplica con: python init_db.py  (que ejecuta schema.sql + este archivo)
-- =============================================================================


-- ── Migración 001: Columnas nuevas en anuncios ────────────────────────────────
ALTER TABLE anuncios ADD COLUMN IF NOT EXISTS foto_url TEXT;
ALTER TABLE anuncios ADD COLUMN IF NOT EXISTS antiguedad_anios_min SMALLINT;
ALTER TABLE anuncios ADD COLUMN IF NOT EXISTS antiguedad_anios_max SMALLINT;
ALTER TABLE anuncios ADD COLUMN IF NOT EXISTS comodidades_normalizadas JSONB;
ALTER TABLE anuncios ADD COLUMN IF NOT EXISTS localidad TEXT;
ALTER TABLE anuncios ADD COLUMN IF NOT EXISTS upz TEXT;
ALTER TABLE anuncios ADD COLUMN IF NOT EXISTS municipio_geo TEXT;

CREATE INDEX IF NOT EXISTS idx_anuncios_localidad ON anuncios(localidad);
CREATE INDEX IF NOT EXISTS idx_anuncios_upz ON anuncios(upz);
CREATE INDEX IF NOT EXISTS idx_anuncios_municipio_geo ON anuncios(municipio_geo);


-- ── Migración 002: Columnas nuevas en hexagonos ───────────────────────────────
ALTER TABLE hexagonos ADD COLUMN IF NOT EXISTS dist_metro REAL;
ALTER TABLE hexagonos ADD COLUMN IF NOT EXISTS cobertura_parques REAL;
ALTER TABLE hexagonos ADD COLUMN IF NOT EXISTS cobertura_parques_500m REAL;
ALTER TABLE hexagonos ADD COLUMN IF NOT EXISTS pois_comercio INTEGER;
ALTER TABLE hexagonos ADD COLUMN IF NOT EXISTS pois_salud INTEGER;
ALTER TABLE hexagonos ADD COLUMN IF NOT EXISTS pois_educacion INTEGER;
ALTER TABLE hexagonos ADD COLUMN IF NOT EXISTS tasa_homicidios REAL;
ALTER TABLE hexagonos ADD COLUMN IF NOT EXISTS tasa_hurtos REAL;
ALTER TABLE hexagonos ADD COLUMN IF NOT EXISTS tasa_siniestralidad REAL;


-- ── Migración 003: busquedas — localidad (TEXT) -> upz (JSONB) ────────────────
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'busquedas' AND column_name = 'localidad') THEN
        ALTER TABLE busquedas DROP COLUMN localidad;
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'busquedas' AND column_name = 'upz' AND data_type <> 'jsonb') THEN
        ALTER TABLE busquedas ALTER COLUMN upz TYPE JSONB USING
            CASE WHEN upz IS NULL THEN '[]'::jsonb ELSE jsonb_build_array(upz) END;
        ALTER TABLE busquedas ALTER COLUMN upz SET DEFAULT '[]'::jsonb;
    END IF;
END $$;
ALTER TABLE busquedas ADD COLUMN IF NOT EXISTS upz JSONB DEFAULT '[]'::jsonb;


-- ── Migración 004: busquedas — columnas escalares -> JSONB ───────────────────
DO $$
BEGIN
    -- departamento_interes / municipio_interes / municipio_codigo -> municipios JSONB
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'busquedas' AND column_name = 'departamento_interes') THEN
        ALTER TABLE busquedas ADD COLUMN IF NOT EXISTS municipios JSONB DEFAULT '[]'::jsonb;
        UPDATE busquedas SET municipios = jsonb_build_array(
            jsonb_build_object('departamento', departamento_interes, 'municipio', municipio_interes, 'codigo', municipio_codigo)
        ) WHERE municipio_interes IS NOT NULL AND (municipios IS NULL OR municipios = '[]'::jsonb);
        ALTER TABLE busquedas DROP COLUMN departamento_interes;
        ALTER TABLE busquedas DROP COLUMN municipio_interes;
        ALTER TABLE busquedas DROP COLUMN municipio_codigo;
    END IF;

    -- uso_previsto TEXT -> JSONB
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'busquedas' AND column_name = 'uso_previsto' AND data_type <> 'jsonb') THEN
        ALTER TABLE busquedas ALTER COLUMN uso_previsto TYPE JSONB USING
            CASE WHEN uso_previsto IS NULL THEN '[]'::jsonb ELSE jsonb_build_array(uso_previsto) END;
        ALTER TABLE busquedas ALTER COLUMN uso_previsto SET DEFAULT '[]'::jsonb;
    END IF;

    -- estrato_objetivo TEXT -> JSONB
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'busquedas' AND column_name = 'estrato_objetivo' AND data_type <> 'jsonb') THEN
        ALTER TABLE busquedas ALTER COLUMN estrato_objetivo TYPE JSONB USING
            CASE WHEN estrato_objetivo IS NULL THEN '[]'::jsonb ELSE jsonb_build_array(estrato_objetivo) END;
        ALTER TABLE busquedas ALTER COLUMN estrato_objetivo SET DEFAULT '[]'::jsonb;
    END IF;
END $$;


-- ── Migración 005: antiguedad_deseada -> antiguedad_anios_min / max ───────────
-- ATENCION: este bloque hace TRUNCATE de resultados_busqueda, reportes, busquedas
-- y anuncios si la columna antigua todavia existe. Solo aplicable a instancias
-- de desarrollo sin datos reales de produccion.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'busquedas' AND column_name = 'antiguedad_deseada') THEN
        TRUNCATE TABLE reportes, resultados_busqueda, busquedas, anuncios RESTART IDENTITY CASCADE;
        ALTER TABLE busquedas DROP COLUMN antiguedad_deseada;
        ALTER TABLE busquedas ADD COLUMN IF NOT EXISTS antiguedad_anios_min SMALLINT;
        ALTER TABLE busquedas ADD COLUMN IF NOT EXISTS antiguedad_anios_max SMALLINT;
    END IF;

    -- comodidades (plano) -> comodidades_relevantes + comodidades_indispensables
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'busquedas' AND column_name = 'comodidades') THEN
        ALTER TABLE busquedas DROP COLUMN comodidades;
        ALTER TABLE busquedas ADD COLUMN IF NOT EXISTS comodidades_relevantes JSONB DEFAULT '[]'::jsonb;
        ALTER TABLE busquedas ADD COLUMN IF NOT EXISTS comodidades_indispensables JSONB DEFAULT '[]'::jsonb;
    END IF;
END $$;


-- ── Migración 006: scoring híbrido H3 ────────────────────────────────────────
ALTER TABLE busquedas ADD COLUMN IF NOT EXISTS cantidad_exacta BOOLEAN DEFAULT FALSE;
ALTER TABLE anuncios ADD COLUMN IF NOT EXISTS h3_data JSONB;
ALTER TABLE busquedas ADD COLUMN IF NOT EXISTS top_n SMALLINT DEFAULT 5;
ALTER TABLE busquedas ADD COLUMN IF NOT EXISTS usar_normalizacion_llm BOOLEAN DEFAULT TRUE;
ALTER TABLE resultados_busqueda ADD COLUMN IF NOT EXISTS sub_scores JSONB;


-- ── Migración 007: Fase 1 — rango de área en búsquedas ───────────────────────
ALTER TABLE busquedas ADD COLUMN IF NOT EXISTS area_metros_min REAL;
ALTER TABLE busquedas ADD COLUMN IF NOT EXISTS area_metros_max REAL;
