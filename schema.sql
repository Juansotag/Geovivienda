-- Tabla maestra: TODOS los anuncios vistos alguna vez, de cualquier cliente/búsqueda
CREATE TABLE IF NOT EXISTS anuncios (
    id BIGSERIAL PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    portal TEXT NOT NULL,                 -- 'fincaraiz', 'metrocuadrado', ...
    codigo_portal TEXT,
    tipo_inmueble TEXT,
    estado TEXT,                          -- 'usado', 'nuevo/proyecto'
    operacion TEXT,                       -- 'venta', 'arriendo'
    precio_venta BIGINT,
    administracion INTEGER,
    ubicacion_texto TEXT,
    ciudad TEXT,
    estrato SMALLINT,
    area_metros REAL,
    habitaciones SMALLINT,
    banos SMALLINT,
    parqueaderos SMALLINT,
    latitud DOUBLE PRECISION,
    longitud DOUBLE PRECISION,
    dist_sitp REAL,
    dist_tm REAL,
    dist_ciclo REAL,
    estrato_promedio_200m REAL,
    h3_index TEXT,                        -- NULL por ahora, se llena en la Fase futura de H3
    activo BOOLEAN DEFAULT TRUE,          -- se pone en FALSE si el link ya no existe
    primera_vez_visto TIMESTAMPTZ DEFAULT now(),
    ultima_verificacion TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS clientes (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    pais_residencia TEXT,
    ciudad_residencia TEXT,
    ingreso_mensual REAL,
    ingreso_moneda TEXT,                  -- 'EUR', 'USD', ...
    ingreso_mensual_cop REAL,             -- convertido al momento de guardar
    ahorro_mensual_cop REAL,
    ciudades_interes JSONB,               -- ej: ["bogota"]
    tipo_vivienda TEXT,                   -- 'casa', 'apartamento'
    estado_deseado TEXT,                  -- 'usado', 'nuevo'
    habitaciones_min SMALLINT,
    banos_min SMALLINT,
    estrato_objetivo SMALLINT,
    presupuesto_min BIGINT,
    presupuesto_max BIGINT,
    creado_en TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS busquedas (
    id BIGSERIAL PRIMARY KEY,
    cliente_id BIGINT REFERENCES clientes(id),
    portales JSONB,                       -- ej: ["fincaraiz","metrocuadrado"]
    cantidad_solicitada INTEGER,
    status TEXT DEFAULT 'idle',           -- idle | running | done | error
    log JSONB DEFAULT '[]'::jsonb,        -- lista de eventos, igual que job_state hoy
    creada_en TIMESTAMPTZ DEFAULT now(),
    terminada_en TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS resultados_busqueda (
    id BIGSERIAL PRIMARY KEY,
    busqueda_id BIGINT REFERENCES busquedas(id),
    anuncio_id BIGINT REFERENCES anuncios(id),
    score REAL,
    es_top BOOLEAN DEFAULT FALSE          -- true si quedó en el top N mostrado
);

CREATE TABLE IF NOT EXISTS reportes (
    id BIGSERIAL PRIMARY KEY,
    cliente_id BIGINT REFERENCES clientes(id),
    anuncio_id BIGINT REFERENCES anuncios(id),
    score REAL,
    contenido_html TEXT,
    generado_en TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ                -- generado_en + 15 días
);
