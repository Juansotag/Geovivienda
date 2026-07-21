# Estado de Geovivienda

> Este archivo es la fuente única de verdad del estado del proyecto. Se
> actualiza al final de cada sesión de trabajo grande (no en cada commit
> chico). Objetivo: que una sesión nueva de IA (o una persona) entienda el
> panorama sin tener que releer 15 archivos.

## Qué es

App Flask para los asesores de Casa en Casa: buscan inmuebles en FincaRaíz
y Metrocuadrado según los criterios de un cliente que vive en el exterior,
Claude puntúa y filtra los candidatos, y se generan reportes en PDF.

## Cómo correr en local

```
python app.py
```

Config en `.env` (copiar de `.env.example`):
- `DATABASE_URL` — Postgres real en Railway (no hay Postgres local, se
  usa siempre la base remota, incluso en desarrollo).
- `ANTHROPIC_API_KEY`
- `SELENIUM_REMOTE_URL` — **dejar comentado en local** salvo que tengas un
  contenedor Docker de Selenium Grid corriendo (`docker run -d -p 4444:4444
  --shm-size=2g selenium/standalone-chrome:4`). Si está seteado y no hay
  nada escuchando en ese puerto, el scraper falla con un error de conexión
  rechazada. Sin la variable, Selenium lanza Chrome directamente en la
  máquina (usa Selenium Manager para bajar el chromedriver solo).
- Migraciones de esquema: `python init_db.py` (aplica `schema.sql` contra
  la base de Railway, es idempotente).

Correr una búsqueda real en local es lento (normal, no es un bug): cada
inmueble nuevo lanza un Chrome headless propio para su página de detalle
(secuencial, no en paralelo), y hay dos llamados a Claude por búsqueda
(normalizar comodidades + rankear candidatos). Unos minutos para una
búsqueda con 15-25 inmuebles nuevos es esperable en local. En producción
(Railway con Selenium Grid dedicado) es más rápido.

## Arquitectura (módulos principales)

- `app.py` — rutas Flask. Ver lista completa de endpoints con
  `grep '@app.route' app.py`.
- `db.py` — capa de acceso a datos, SQL crudo con psycopg2. Patrón
  `_preparar_datos()`: castea listas/dicts de Python a JSONB con
  `::jsonb` explícito en el SQL (psycopg2 los adaptaría a array nativo de
  Postgres si no).
- `busqueda.py` — el corazón del scraping y filtrado:
  - `ejecutar_busqueda_completa()` — orquesta todo el flujo de un click en
    "Buscar" (scraping → normalizar comodidades → rankear con LLM →
    guardar resultados). Corre en un thread de background.
  - `ejecutar_busqueda_multi_municipio()` — reparte la cantidad pedida
    entre los municipios de la búsqueda (round-robin con reintentos si
    algún municipio no da abasto).
  - `_filtros_desde_cliente()` — traduce los criterios de la búsqueda a
    los parámetros de cada portal (la firma de filtros de FincaRaíz y
    Metrocuadrado es distinta).
  - `_cumple_filtros_duros()` — filtros que DESCARTAN un anuncio (no solo
    penalizan el score): antigüedad, comodidades indispensables, UPZ,
    municipios. Cada `_cumple_X()` sigue el mismo patrón: si el dato no
    está disponible, no descarta (fail-open).
  - `normalizar_comodidades_llm()` — un solo llamado a Claude por batch
    de anuncios nuevos para mapear texto libre de comodidades al catálogo
    cerrado (`CATALOGO_COMODIDADES`).
- `scoring.py` — dos rutas de scoring en paralelo:
  - `calcular_score()` / `rankear_candidatos()` — versión basada en
    reglas (no LLM), usada por el botón "Recalcular score" de un inmueble
    editado a mano.
  - `calcular_scores_llm()` / `rankear_candidatos_llm()` — la que
    realmente usa `ejecutar_busqueda_completa()`, un solo llamado batch a
    Claude para toda la búsqueda.
- `reportes.py` — genera el reporte individual de un inmueble con Claude,
  lo persiste con TTL de 15 días, exporta a PDF (xhtml2pdf).
- `spatial_analysis.py` — GeoPandas, todo reproyectado a `EPSG:3116`
  (planar, Bogotá). `_capas()` cachea las capas geográficas en memoria
  (localidades, UPZ, municipios Bogotá+Cundinamarca, transporte,
  estratos) y el mapeo UPZ→localidad (join espacial por centroide, no
  viene como columna nativa).
- `extractor_links.py` / `extractor_detalles.py` — scraping de FincaRaíz
  con Selenium (`configurar_driver()` decide Grid remoto vs Chrome local
  según `SELENIUM_REMOTE_URL`).
- `extractor_metrocuadrado_links.py` / `extractor_metrocuadrado_detalles.py`
  — Metrocuadrado, sin Selenium (los datos cargan del lado del servidor).
- `portales.py` — interfaz común (`buscar_portal`, `extraer_detalle`) para
  que `busqueda.py` no tenga que saber qué portal es cuál.

## Convenciones importantes

- **JSONB en criterios de búsqueda**: `municipios`, `upz`,
  `comodidades_relevantes`, `comodidades_indispensables`, `estrato_objetivo`,
  `uso_previsto` son todos listas. `municipios` es la única que define
  *dónde scrapear* (le llega a los portales); `upz` es un filtro duro
  post-scrapeo (geopandas, no existe como parámetro de búsqueda en los
  portales) que puede combinar UPZ de localidades distintas.
- **Filtro duro vs. penalización LLM**: si un criterio se puede pasar
  literalmente a la URL del portal como "mínimo" (ej. Metrocuadrado sí
  soporta `habitaciones_min`), se pasa. Si el portal lo trata como
  coincidencia EXACTA en vez de mínimo (FincaRaíz con habitaciones/baños,
  confirmado en vivo — ver git log), NO se pasa a la URL: se deja que el
  prompt del LLM penalice el descuadre al puntuar. Antes de agregar un
  filtro nuevo al URL builder de un portal, verificar en el sitio real si
  es realmente "mínimo" o "exacto".
- **Nunca** `git add` los geojson nacionales grandes —
  `static/geo/municipios.geojson` (237MB, el archivo nacional original)
  se queda sin trackear a propósito. El que sí está en git es
  `static/geo/municipios_cundinamarca.geojson` (17.8MB, recortado a
  Bogotá+Cundinamarca con solo las columnas necesarias).

## Datos reservados para features futuras (no borrar, no están conectados todavía)

Ningún archivo `.py` referencia hoy estas carpetas/archivos, pero es
intencional — quedaron guardados para construir las dimensiones de
"Seguridad" y "Entorno y Servicios" que describe `PLAN_GEOGRAFICO.md`
(H3, POIs, criminalidad, accesibilidad), que todavía no se implementaron.
Si una revisión futura los marca como "huérfanos", no es un hallazgo
nuevo — ya se evaluó y el usuario confirmó que se van a usar.

- `geodata/entorno/` (~952MB), `geodata/seguridad/` (~41MB),
  `geodata/areaactividad/` (~4.6MB), `geodata/transporte/` (~4.3MB),
  `geodata/indice_accesibilidad_servicios.xlsx`.
- `PLAN_GEOGRAFICO.md` — la propuesta que describe qué hacer con estos
  datos. Su sección sobre selección de Localidad→UPZ en cascada está
  desactualizada (esta sesión se reemplazó por el checkbox múltiple de
  UPZ independiente de localidad) — el resto (H3, seguridad, entorno)
  sigue vigente como diseño a futuro.

## Problemas conocidos (no arreglar sin confirmar con el usuario primero)

- **Backfill de comodidades** (`/inmuebles/estandarizar-comodidades`):
  procesa 0 de N anuncios pendientes en batches grandes (~40+). Sospecha:
  `max_tokens=4000` en `normalizar_comodidades_llm()` insuficiente para la
  respuesta JSON de un batch grande, causa un parseo fallido que cae en el
  `except Exception: return {}` silencioso. No diagnosticado a fondo
  todavía — no toca este mismo límite en el batch normal (~13-25 anuncios
  por búsqueda), solo en el backfill masivo.
- **Indispensables sin restringir al catálogo**: el picker de comodidades
  "Indispensables" en el formulario de búsqueda acepta texto libre; debería
  restringirse al `CATALOGO_COMODIDADES` cerrado (Relevantes sí puede
  quedar libre).

## Cómo verificar cambios rápido

1. `pytest` — pruebas de humo en `tests/` (ver README ahí mismo).
2. Para flujos que pytest no cubre (UI, scraping en vivo), usar
   `app.test_client()` con `TESTING=True` en un script desechable en vez
   de levantar el servidor completo — es más rápido y no requiere Selenium.
