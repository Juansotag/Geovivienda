-- =============================================================================
-- SCHEMA BASE DE GEOVIVIENDA
-- =============================================================================
-- Este archivo define el estado ACTUAL y FINAL de todas las tablas.
-- Solo contiene CREATE TABLE IF NOT EXISTS con la estructura vigente.
--
-- Las migraciones históricas (ALTER TABLE, DO $$ ... END $$) están en
-- migrations.sql y se aplican DESPUÉS de este archivo con python init_db.py
-- =============================================================================


-- ── Hexágonos H3 (índice geoespacial a resolución 9) ─────────────────────────
CREATE TABLE IF NOT EXISTS hexagonos (
    h3_index TEXT PRIMARY KEY,
    -- Transporte
    dist_sitp REAL,
    dist_tm REAL,
    dist_ciclo REAL,
    dist_metro REAL,
    -- Estratos
    estrato_promedio_200m REAL,
    -- Parques / ambiente
    cobertura_parques REAL,
    cobertura_parques_500m REAL,
    -- POIs conteo
    pois_comercio INTEGER,
    pois_salud INTEGER,
    pois_educacion INTEGER,
    -- Seguridad
    tasa_homicidios REAL,
    tasa_hurtos REAL,
    tasa_siniestralidad REAL
);


-- ── Anuncios inmobiliarios (tabla maestra) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS anuncios (
    id BIGSERIAL PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    portal TEXT NOT NULL,                 -- 'fincaraiz' | 'metrocuadrado'
    codigo_portal TEXT,
    tipo_inmueble TEXT,
    estado TEXT,                          -- 'usado' | 'nuevo' | 'proyecto'
    operacion TEXT,                       -- 'venta'
    precio_venta BIGINT,
    administracion INTEGER,
    ubicacion_texto TEXT,
    ciudad TEXT,
    estrato SMALLINT,
    area_metros REAL,
    habitaciones SMALLINT,
    banos SMALLINT,
    parqueaderos SMALLINT,
    antiguedad TEXT,
    antiguedad_anios_min SMALLINT,        -- parseado de 'antiguedad' — ver busqueda._parsear_antiguedad
    antiguedad_anios_max SMALLINT,        -- NULL = sin límite superior ("más de N años")
    piso_nro SMALLINT,
    cantidad_pisos SMALLINT,
    comodidades TEXT,                     -- texto libre del portal
    comodidades_normalizadas JSONB,       -- lista canónica del catálogo cerrado (LLM). NULL = sin procesar
    descripcion TEXT,
    foto_url TEXT,
    latitud DOUBLE PRECISION,
    longitud DOUBLE PRECISION,
    h3_index TEXT REFERENCES hexagonos(h3_index),
    nivel_admin_1 TEXT,                   -- Localidad (Bogotá) / Comuna o Corregimiento (Cali)
    nivel_admin_2 TEXT,                   -- UPZ (Bogotá) / Barrio (Cali)
    municipio_geo TEXT,                   -- municipio geo-derivado (point-in-polygon)
    h3_data JSONB,                        -- snapshot de val_* y rank_* del hexágono H3 Res 9
    activo BOOLEAN DEFAULT TRUE,
    primera_vez_visto TIMESTAMPTZ DEFAULT now(),
    ultima_verificacion TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_anuncios_admin1       ON anuncios(nivel_admin_1);
CREATE INDEX IF NOT EXISTS idx_anuncios_admin2       ON anuncios(nivel_admin_2);
CREATE INDEX IF NOT EXISTS idx_anuncios_municipio_geo ON anuncios(municipio_geo);


-- ── Clientes ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS clientes (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    pais_residencia TEXT,
    ciudad_residencia TEXT,
    tipo_identificacion TEXT,
    numero_identificacion TEXT,
    ingreso_mensual REAL,
    ingreso_moneda TEXT,                  -- 'EUR' | 'USD' | 'COP'
    ingreso_mensual_cop REAL,
    ahorro_mensual REAL,
    ahorro_mensual_cop REAL,
    nacionalidad TEXT,
    anios_en_pais SMALLINT,
    tipo_permiso_residencia TEXT,
    creado_en TIMESTAMPTZ DEFAULT now()
);


-- ── Perfil del asesor ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS perfil (
    id SERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    correo TEXT NOT NULL,
    cargo TEXT NOT NULL
);


-- ── Búsquedas (criterios + estado del scraper) ────────────────────────────────
CREATE TABLE IF NOT EXISTS busquedas (
    id BIGSERIAL PRIMARY KEY,
    cliente_id BIGINT REFERENCES clientes(id) ON DELETE CASCADE,
    portales JSONB,                       -- ["fincaraiz","metrocuadrado"]
    cantidad_solicitada INTEGER,
    cantidad_exacta BOOLEAN DEFAULT FALSE,
    status TEXT DEFAULT 'idle',           -- idle | pendiente | running | cancelando | done | error
    log JSONB DEFAULT '[]'::jsonb,

    -- Criterios de vivienda
    municipios JSONB DEFAULT '[]'::jsonb, -- [{departamento, municipio, codigo}, ...]
    tipo_vivienda TEXT,
    estado_deseado TEXT,
    antiguedad_anios_min SMALLINT,
    antiguedad_anios_max SMALLINT,
    zona_deseada TEXT,
    habitaciones_min SMALLINT,
    habitaciones_exactas BOOLEAN DEFAULT FALSE,
    banos_min SMALLINT,
    banos_exactos BOOLEAN DEFAULT FALSE,
    estrato_objetivo JSONB DEFAULT '[]'::jsonb,
    presupuesto_min BIGINT,
    presupuesto_max BIGINT,
    uso_previsto JSONB DEFAULT '[]'::jsonb,
    comodidades_relevantes JSONB DEFAULT '[]'::jsonb,
    comodidades_indispensables JSONB DEFAULT '[]'::jsonb,
    sectores JSONB DEFAULT '[]'::jsonb,   -- Reemplaza a 'upz', aplica a cualquier nivel_admin_2
    area_metros_min REAL,
    area_metros_max REAL,
    pregunta_abierta TEXT,
    top_n SMALLINT DEFAULT 5,
    usar_normalizacion_llm BOOLEAN DEFAULT TRUE,

    creada_en TIMESTAMPTZ DEFAULT now(),
    terminada_en TIMESTAMPTZ
);


-- ── Resultados de búsqueda ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS resultados_busqueda (
    id BIGSERIAL PRIMARY KEY,
    busqueda_id BIGINT REFERENCES busquedas(id) ON DELETE CASCADE,
    anuncio_id BIGINT REFERENCES anuncios(id) ON DELETE CASCADE,
    score REAL,
    es_top BOOLEAN DEFAULT FALSE,
    sub_scores JSONB                      -- {s_seguridad, s_transporte, s_comercio, s_entorno_verde, s_estrato_valor}
);


-- ── Reportes IA ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reportes (
    id BIGSERIAL PRIMARY KEY,
    cliente_id BIGINT REFERENCES clientes(id) ON DELETE CASCADE,
    anuncio_id BIGINT REFERENCES anuncios(id) ON DELETE CASCADE,
    score REAL,
    contenido_html TEXT,
    generado_en TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ
);
