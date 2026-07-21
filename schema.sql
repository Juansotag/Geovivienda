-- Tabla de Hexágonos: Almacena información geoespacial calculada por índice H3
CREATE TABLE IF NOT EXISTS hexagonos (
    h3_index TEXT PRIMARY KEY,
    dist_sitp REAL,
    dist_tm REAL,
    dist_ciclo REAL,
    estrato_promedio_200m REAL,
    dist_metro REAL,
    cobertura_parques REAL,
    cobertura_parques_500m REAL,
    pois_comercio INTEGER,
    pois_salud INTEGER,
    pois_educacion INTEGER,
    tasa_homicidios REAL,
    tasa_hurtos REAL,
    tasa_siniestralidad REAL
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
    antiguedad_anios_min SMALLINT,        -- parseado de 'antiguedad' - ver busqueda.py _parsear_antiguedad
    antiguedad_anios_max SMALLINT,        -- NULL = sin limite superior ("mas de N anios")
    piso_nro SMALLINT,
    cantidad_pisos SMALLINT,
    comodidades TEXT,
    comodidades_normalizadas JSONB,       -- lista canonica del catalogo cerrado, calculada por LLM. NULL = aun no procesado
    descripcion TEXT,
    foto_url TEXT,                        -- solo Metrocuadrado la trae por ahora
    latitud DOUBLE PRECISION,
    longitud DOUBLE PRECISION,
    h3_index TEXT REFERENCES hexagonos(h3_index), -- Conexión a datos geoespaciales
    localidad TEXT,
    upz TEXT,
    municipio_geo TEXT,                   -- municipio geo-derivado (point-in-polygon), distinto de 'ciudad' que es texto fijo
    activo BOOLEAN DEFAULT TRUE,
    primera_vez_visto TIMESTAMPTZ DEFAULT now(),
    ultima_verificacion TIMESTAMPTZ DEFAULT now()
);

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

ALTER TABLE hexagonos ADD COLUMN IF NOT EXISTS dist_metro REAL;
ALTER TABLE hexagonos ADD COLUMN IF NOT EXISTS cobertura_parques REAL;
ALTER TABLE hexagonos ADD COLUMN IF NOT EXISTS cobertura_parques_500m REAL;
ALTER TABLE hexagonos ADD COLUMN IF NOT EXISTS pois_comercio INTEGER;
ALTER TABLE hexagonos ADD COLUMN IF NOT EXISTS pois_salud INTEGER;
ALTER TABLE hexagonos ADD COLUMN IF NOT EXISTS pois_educacion INTEGER;
ALTER TABLE hexagonos ADD COLUMN IF NOT EXISTS tasa_homicidios REAL;
ALTER TABLE hexagonos ADD COLUMN IF NOT EXISTS tasa_hurtos REAL;
ALTER TABLE hexagonos ADD COLUMN IF NOT EXISTS tasa_siniestralidad REAL;
-- NULL = todavia no se ha corrido el clasificador LLM contra este anuncio
-- (distinto de '[]', que significa "se corrio y no encontro ninguna
-- comodidad del catalogo") - la distincion permite saber a cuales
-- anuncios les falta normalizar sin volver a procesar los que ya se
-- normalizaron y dieron una lista vacia.

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
    cantidad_solicitada INTEGER,          -- tratada como MINIMO, no exacto, salvo que cantidad_exacta sea true
    cantidad_exacta BOOLEAN DEFAULT FALSE, -- si true, se trunca la lista final a cantidad_solicitada antes de scorear
    status TEXT DEFAULT 'idle',           -- idle | running | done | error
    log JSONB DEFAULT '[]'::jsonb,        -- logs de eventos del scraper
    
    -- Criterios de Vivienda (Mapeados desde clientes)
    municipios JSONB DEFAULT '[]'::jsonb, -- lista ordenada: [{"departamento":..,"municipio":..,"codigo":..}, ...]
    tipo_vivienda TEXT,
    estado_deseado TEXT,
    antiguedad_anios_min SMALLINT,        -- rango duro de antiguedad (anios), NULL = sin limite
    antiguedad_anios_max SMALLINT,
    zona_deseada TEXT,
    habitaciones_min SMALLINT,
    habitaciones_exactas BOOLEAN DEFAULT FALSE,
    banos_min SMALLINT,
    banos_exactos BOOLEAN DEFAULT FALSE,
    estrato_objetivo JSONB DEFAULT '[]'::jsonb,    -- lista de ints (multi-choice)
    presupuesto_min BIGINT,
    presupuesto_max BIGINT,
    uso_previsto JSONB DEFAULT '[]'::jsonb,        -- lista de strings (multi-choice)
    comodidades_relevantes JSONB DEFAULT '[]'::jsonb,      -- pesan en el score del LLM, no filtran
    comodidades_indispensables JSONB DEFAULT '[]'::jsonb,  -- filtro duro: el anuncio debe tenerlas TODAS
    upz JSONB DEFAULT '[]'::jsonb,        -- lista de nombres de UPZ (pueden ser de localidades distintas)
    pregunta_abierta TEXT,

    creada_en TIMESTAMPTZ DEFAULT now(),
    terminada_en TIMESTAMPTZ
);

-- localidad era un solo valor (TEXT) - se reemplaza por upz como lista,
-- que puede combinar UPZ de localidades distintas en una sola busqueda
-- (la localidad era demasiado restrictiva: obligaba a que todas las UPZ
-- pedidas fueran de la MISMA localidad, cuando en la practica un cliente
-- puede querer 2 UPZ vecinas de una localidad + 1 de otra).
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

-- Migracion desde el esquema anterior (columnas escalares -> JSONB). Segura de
-- re-ejecutar: cada bloque solo actua si la columna todavia tiene el tipo viejo.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'busquedas' AND column_name = 'departamento_interes') THEN
        ALTER TABLE busquedas ADD COLUMN IF NOT EXISTS municipios JSONB DEFAULT '[]'::jsonb;
        UPDATE busquedas SET municipios = jsonb_build_array(
            jsonb_build_object('departamento', departamento_interes, 'municipio', municipio_interes, 'codigo', municipio_codigo)
        ) WHERE municipio_interes IS NOT NULL AND (municipios IS NULL OR municipios = '[]'::jsonb);
        ALTER TABLE busquedas DROP COLUMN departamento_interes;
        ALTER TABLE busquedas DROP COLUMN municipio_interes;
        ALTER TABLE busquedas DROP COLUMN municipio_codigo;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'busquedas' AND column_name = 'uso_previsto' AND data_type <> 'jsonb') THEN
        ALTER TABLE busquedas ALTER COLUMN uso_previsto TYPE JSONB USING
            CASE WHEN uso_previsto IS NULL THEN '[]'::jsonb ELSE jsonb_build_array(uso_previsto) END;
        ALTER TABLE busquedas ALTER COLUMN uso_previsto SET DEFAULT '[]'::jsonb;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'busquedas' AND column_name = 'antiguedad_deseada' AND data_type <> 'jsonb') THEN
        ALTER TABLE busquedas ALTER COLUMN antiguedad_deseada TYPE JSONB USING
            CASE WHEN antiguedad_deseada IS NULL THEN '[]'::jsonb ELSE jsonb_build_array(antiguedad_deseada) END;
        ALTER TABLE busquedas ALTER COLUMN antiguedad_deseada SET DEFAULT '[]'::jsonb;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'busquedas' AND column_name = 'estrato_objetivo' AND data_type <> 'jsonb') THEN
        ALTER TABLE busquedas ALTER COLUMN estrato_objetivo TYPE JSONB USING
            CASE WHEN estrato_objetivo IS NULL THEN '[]'::jsonb ELSE jsonb_build_array(estrato_objetivo) END;
        ALTER TABLE busquedas ALTER COLUMN estrato_objetivo SET DEFAULT '[]'::jsonb;
    END IF;

    -- antiguedad_deseada (categorias de texto, no comparables entre portales) ->
    -- antiguedad_anios_min/max (rango numerico, filtro duro exacto). No hay
    -- traduccion automatica razonable de las categorias viejas, asi que se
    -- vacian los datos de busqueda/resultados que dependian del esquema
    -- anterior (autorizado explicitamente, no hay clientes en produccion
    -- afectados por este cambio de criterios).
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'busquedas' AND column_name = 'antiguedad_deseada') THEN
        TRUNCATE TABLE reportes, resultados_busqueda, busquedas, anuncios RESTART IDENTITY CASCADE;
        ALTER TABLE busquedas DROP COLUMN antiguedad_deseada;
        ALTER TABLE busquedas ADD COLUMN IF NOT EXISTS antiguedad_anios_min SMALLINT;
        ALTER TABLE busquedas ADD COLUMN IF NOT EXISTS antiguedad_anios_max SMALLINT;
    END IF;

    -- comodidades (una sola lista plana) -> comodidades_relevantes (soft,
    -- pesa en el score) + comodidades_indispensables (filtro duro, AND).
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'busquedas' AND column_name = 'comodidades') THEN
        ALTER TABLE busquedas DROP COLUMN comodidades;
        ALTER TABLE busquedas ADD COLUMN IF NOT EXISTS comodidades_relevantes JSONB DEFAULT '[]'::jsonb;
        ALTER TABLE busquedas ADD COLUMN IF NOT EXISTS comodidades_indispensables JSONB DEFAULT '[]'::jsonb;
    END IF;
END $$;

ALTER TABLE busquedas ADD COLUMN IF NOT EXISTS cantidad_exacta BOOLEAN DEFAULT FALSE;

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
