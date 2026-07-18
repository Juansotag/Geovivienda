-- Tabla de Hexágonos: Almacena información geoespacial calculada por índice H3
CREATE TABLE IF NOT EXISTS hexagonos (
    h3_index TEXT PRIMARY KEY,
    dist_sitp REAL,
    dist_tm REAL,
    dist_ciclo REAL,
    estrato_promedio_200m REAL
);

-- Tabla maestra: Anuncios inmobiliarios capturados
CREATE TABLE IF NOT EXISTS anuncios (
    id BIGSERIAL PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    portal TEXT NOT NULL,                 -- 'fincaraiz', 'metrocuadrado'
    codigo_portal TEXT,
    tipo_inmueble TEXT,
    estado TEXT,                          -- 'usado', 'nuevo/proyecto'
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
    piso_nro SMALLINT,
    cantidad_pisos SMALLINT,
    comodidades TEXT,
    descripcion TEXT,
    latitud DOUBLE PRECISION,
    longitud DOUBLE PRECISION,
    h3_index TEXT REFERENCES hexagonos(h3_index), -- Conexión a datos geoespaciales
    activo BOOLEAN DEFAULT TRUE,
    primera_vez_visto TIMESTAMPTZ DEFAULT now(),
    ultima_verificacion TIMESTAMPTZ DEFAULT now()
);

-- Tabla de Clientes: Información personal y financiera
CREATE TABLE IF NOT EXISTS clientes (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    pais_residencia TEXT,
    ciudad_residencia TEXT,
    tipo_identificacion TEXT,
    numero_identificacion TEXT,
    ingreso_mensual REAL,
    ingreso_moneda TEXT,                  -- 'EUR', 'USD', 'COP'
    ingreso_mensual_cop REAL,
    ahorro_mensual REAL,
    ahorro_mensual_cop REAL,
    creado_en TIMESTAMPTZ DEFAULT now()
);

-- Tabla de Perfil del Asesor
CREATE TABLE IF NOT EXISTS perfil (
    id SERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    correo TEXT NOT NULL,
    cargo TEXT NOT NULL
);

-- Tabla de Búsquedas: Almacena criterios de vivienda y estado del scraper por ejecución
CREATE TABLE IF NOT EXISTS busquedas (
    id BIGSERIAL PRIMARY KEY,
    cliente_id BIGINT REFERENCES clientes(id) ON DELETE CASCADE,
    portales JSONB,                       -- ej: ["fincaraiz","metrocuadrado"]
    cantidad_solicitada INTEGER,
    status TEXT DEFAULT 'idle',           -- idle | running | done | error
    log JSONB DEFAULT '[]'::jsonb,        -- logs de eventos del scraper
    
    -- Criterios de Vivienda (Mapeados desde clientes)
    departamento_interes TEXT,
    municipio_interes TEXT,
    municipio_codigo TEXT,
    tipo_vivienda TEXT,
    estado_deseado TEXT,
    antiguedad_deseada TEXT,
    zona_deseada TEXT,
    habitaciones_min SMALLINT,
    habitaciones_exactas BOOLEAN DEFAULT FALSE,
    banos_min SMALLINT,
    banos_exactos BOOLEAN DEFAULT FALSE,
    estrato_objetivo SMALLINT,
    presupuesto_min BIGINT,
    presupuesto_max BIGINT,
    uso_previsto TEXT,
    comodidades JSONB,
    pregunta_abierta TEXT,
    
    creada_en TIMESTAMPTZ DEFAULT now(),
    terminada_en TIMESTAMPTZ
);

-- Tabla de Resultados de Búsquedas (Matches)
CREATE TABLE IF NOT EXISTS resultados_busqueda (
    id BIGSERIAL PRIMARY KEY,
    busqueda_id BIGINT REFERENCES busquedas(id) ON DELETE CASCADE,
    anuncio_id BIGINT REFERENCES anuncios(id) ON DELETE CASCADE,
    score REAL,
    es_top BOOLEAN DEFAULT FALSE
);

-- Tabla de Reportes IA
CREATE TABLE IF NOT EXISTS reportes (
    id BIGSERIAL PRIMARY KEY,
    cliente_id BIGINT REFERENCES clientes(id) ON DELETE CASCADE,
    anuncio_id BIGINT REFERENCES anuncios(id) ON DELETE CASCADE,
    score REAL,
    contenido_html TEXT,
    generado_en TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ
);
