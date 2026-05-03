# 🏠 Geovivienda — Roadmap a producto de inversión

> **Contexto:** App de búsqueda de vivienda en Bogotá basada en geolocalización y calidad de ubicación.
> Stack: Flask + Pandas + Selenium (local) + Leaflet.js + Railway (deploy).
> Usuario objetivo: jóvenes profesionales y familias comprando vivienda en Bogotá.
> Meta: demo sólido para video de LinkedIn + presentación a inversionistas.

---

## Principio guía

El scraping corre **solo en local**. El servidor público (Railway) es de **solo lectura** — sin Selenium, sin Chrome, sin threads pesados. Los usuarios ven los datos que tú ya extrajiste.

```
Tu máquina local                  Railway (público)
────────────────                  ─────────────────
extractor_links.py   →  Supabase  ←  app.py (solo lectura)
extractor_detalles.py   PostgreSQL    └── /api/data
                        Storage       └── /api/geo → PMTiles
                        └── estratos.pmtiles
                        └── transmilenio.pmtiles
                        └── sitp.pmtiles
```

---

## 📅 Cronograma

| Semana | Fase | Objetivo |
|--------|------|----------|
| 1 | Infraestructura | Nada explota, datos persisten en la nube |
| 2 | UI/UX core | El demo se ve como producto terminado |
| 3 | Narrativa + video | Grabar demo, publicar en LinkedIn |

---

## ✅ Fase 1 — Infraestructura sólida

> **Meta:** Railway usa ~80 MB RAM, el mapa carga en segundos, los datos sobreviven deploys.

### 1.1 Migrar datos a Supabase PostgreSQL

**Crear la tabla en Supabase (SQL Editor):**
```sql
create table inmuebles (
  id bigint generated always as identity primary key,
  url text unique,
  codigo_fincaraiz text,
  tipo_inmueble text,
  estado text,
  precio_venta bigint,
  administracion numeric,
  ubicacion text,
  estrato int,
  area_metros numeric,
  area_construida numeric,
  area_privada numeric,
  habitaciones int,
  banos int,
  parqueaderos int,
  antiguedad text,
  piso_nro int,
  cantidad_pisos int,
  comodidades text,
  descripcion text,
  latitud numeric,
  longitud numeric,
  created_at timestamptz default now()
);
```

**Script local para migrar el CSV existente (`migrate_csv_to_supabase.py`):**
```python
import pandas as pd
from supabase import create_client

SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_KEY = "tu_service_role_key"  # service_role, no anon

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

df = pd.read_csv("dataset_fincaraiz.csv", sep=";", decimal=",", encoding="utf-8-sig")
df.columns = [c.lower() for c in df.columns]
df = df.where(pd.notnull(df), None)
records = df.to_dict(orient="records")

# Subir en lotes de 100
batch_size = 100
for i in range(0, len(records), batch_size):
    batch = records[i:i+batch_size]
    supabase.table("inmuebles").upsert(batch, on_conflict="url").execute()
    print(f"Subidos {min(i+batch_size, len(records))}/{len(records)}")

print("Migración completa.")
```

**Añadir a requirements.txt local (no al del servidor):**
```
supabase>=2.0.0
```

### 1.2 Modificar `app.py` para leer de Supabase

**Variables de entorno en Railway:**
```
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_KEY=tu_anon_key
```

**Cambios en `app.py`:**
```python
# Agregar al bloque de imports
from supabase import create_client

# Inicializar cliente (reemplaza CSV_PATH)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Ruta /api/data — reemplazar lógica de CSV por Supabase
@app.route('/api/data', methods=['GET'])
def get_data():
    response = supabase.table("inmuebles").select("*").execute()
    return jsonify(response.data)

# Ruta /api/delete_row
@app.route('/api/delete_row', methods=['POST'])
def delete_row():
    url = request.json.get('url')
    if not url:
        return jsonify({'status': 'error'})
    supabase.table("inmuebles").delete().eq("url", url).execute()
    return jsonify({'status': 'ok'})

# Ruta /api/clear
@app.route('/api/clear', methods=['POST'])
def clear_all():
    supabase.table("inmuebles").delete().neq("id", 0).execute()
    return jsonify({'status': 'ok'})
```

### 1.3 PMTiles en Supabase Storage

**Paso 1 — Instalar tippecanoe:**
```bash
# Mac
brew install tippecanoe

# Ubuntu / WSL
git clone https://github.com/felt/tippecanoe.git
cd tippecanoe && make && sudo make install
```

**Paso 2 — Convertir los GeoJSON:**
```bash
# Estratos (manzanas — zoom detallado)
tippecanoe -o estratos_bogota.pmtiles \
  --minimum-zoom=10 --maximum-zoom=16 \
  --layer=estratos \
  --no-tile-compression \
  estratos_bogota.geojson

# Transmilenio
tippecanoe -o transmilenio.pmtiles \
  --minimum-zoom=9 --maximum-zoom=16 \
  --layer=transmilenio \
  --no-tile-compression \
  estaciones_tm.geojson

# SITP
tippecanoe -o sitp.pmtiles \
  --minimum-zoom=11 --maximum-zoom=16 \
  --layer=sitp \
  --no-tile-compression \
  estaciones_sitp.geojson
```

**Paso 3 — Subir a Supabase Storage:**
1. Ir a **Storage → New bucket** → nombre: `geo-layers` → marcar **Public**
2. Subir los tres `.pmtiles`
3. La URL pública de cada archivo tendrá esta forma:
```
https://xxxx.supabase.co/storage/v1/object/public/geo-layers/estratos_bogota.pmtiles
```

**Paso 4 — Actualizar el frontend (`index.html`):**

Agregar librerías antes del cierre de `</head>`:
```html
<script src="https://unpkg.com/pmtiles@2.11.0/dist/pmtiles.js"></script>
<script src="https://unpkg.com/leaflet-pmtiles/dist/leaflet-pmtiles.min.js"></script>
```

Reemplazar la carga de capas geo en el JS:
```javascript
// Registrar el protocolo PMTiles una sola vez al iniciar el mapa
const protocol = new pmtiles.Protocol();
L.PMTiles.addProtocol(protocol);

// Capa de estratos
const estratosLayer = new L.PMTilesVectorLayer(
  'https://xxxx.supabase.co/storage/v1/object/public/geo-layers/estratos_bogota.pmtiles',
  {
    vectorTileLayerStyles: {
      estratos: function(properties) {
        const colores = {
          1: '#d73027', 2: '#f46d43', 3: '#fdae61',
          4: '#74add1', 5: '#4575b4', 6: '#313695'
        };
        return {
          fillColor: colores[properties.estrato] || '#aaaaaa',
          fillOpacity: 0.4,
          weight: 0.5,
          color: '#ffffff'
        };
      }
    }
  }
);

// Capa Transmilenio
const tmLayer = new L.PMTilesVectorLayer(
  'https://xxxx.supabase.co/storage/v1/object/public/geo-layers/transmilenio.pmtiles',
  { vectorTileLayerStyles: { transmilenio: { color: '#e63946', weight: 2 } } }
);

// Capa SITP
const sitpLayer = new L.PMTilesVectorLayer(
  'https://xxxx.supabase.co/storage/v1/object/public/geo-layers/sitp.pmtiles',
  { vectorTileLayerStyles: { sitp: { color: '#2a9d8f', weight: 1.5 } } }
);
```

### 1.4 Limpiar el servidor

**`requirements.txt` del servidor (Railway):**
```txt
Flask>=3.0.0
pandas>=2.2.3
supabase>=2.0.0
gunicorn>=21.0.0
```

Selenium, BeautifulSoup y webdriver-manager se quedan **solo en tu entorno local**.

**`nixpacks.toml` limpio:**
```toml
[start]
cmd = "gunicorn app:app --bind 0.0.0.0:$PORT"
```

Sin `[phases.setup]` — Railway ya no instala Chrome (ahorra ~300 MB del build y ~200 MB de RAM).

**Rutas a eliminar de `app.py` público:**
```python
# Eliminar completamente del servidor público:
from extractor_links import extraer_links_fincaraiz      # ← fuera
from extractor_detalles import procesar_lista_links      # ← fuera

@app.route('/api/scrape')     # ← fuera
@app.route('/api/status')     # ← fuera
@app.route('/api/reset')      # ← fuera
job_state = { ... }           # ← fuera
run_scrape_job()              # ← fuera

# Las rutas /api/geo también desaparecen —
# el frontend carga PMTiles directo desde Supabase Storage
@app.route('/api/geo/<path:filename>')  # ← fuera
@app.route('/api/geo/tm')              # ← fuera
@app.route('/api/geo/sitp')            # ← fuera
```

**Checklist Fase 1:**
- [ ] Tabla `inmuebles` creada en Supabase
- [ ] CSV migrado con `migrate_csv_to_supabase.py`
- [ ] `app.py` leyendo de Supabase
- [ ] Variables de entorno configuradas en Railway
- [ ] `.pmtiles` generados con tippecanoe
- [ ] `.pmtiles` subidos al bucket `geo-layers`
- [ ] Frontend cargando capas desde PMTiles
- [ ] `nixpacks.toml` sin Chrome
- [ ] `requirements.txt` del servidor adelgazado
- [ ] Deploy en Railway sin errores de memoria

---

## ✅ Fase 2 — UI/UX que enamora

> **Meta:** el demo se ve como un producto terminado. Un inversionista en los primeros 30 segundos entiende el valor.

### 2.1 Rediseño del sidebar de filtros
- Sliders visuales para precio y área (reemplazar inputs de texto)
- Chips seleccionables para estratos, habitaciones, baños
- Contador de resultados en tiempo real: *"127 inmuebles encontrados"*

### 2.2 Cards de inmueble mejoradas
- Popup al hacer clic en un pin: foto, precio/m², estrato, score de ubicación
- Botón directo a FincaRaíz
- Color del pin según rango de precio (verde = bajo, rojo = alto)

### 2.3 Score de ubicación ← *el diferenciador real*
Un número del 1 al 10 calculado por inmueble basado en:
- Distancia a estación de TransMilenio/Metro más cercana
- Estrato de la manzana
- (Futuro) índice de seguridad por UPZ

Este score es lo que **ninguna otra plataforma en Colombia muestra** y lo que un inversionista va a recordar del demo.

### 2.4 Vista comparativa
- Seleccionar 2–3 inmuebles con checkbox
- Tabla lado a lado: precio, m², precio/m², estrato, score, habitaciones

**Checklist Fase 2:**
- [ ] Sliders de precio y área
- [ ] Chips de filtro para estratos/habitaciones/baños
- [ ] Contador de resultados en tiempo real
- [ ] Popup mejorado con score de ubicación
- [ ] Colores de pin por rango de precio
- [ ] Vista comparativa de 2–3 inmuebles

---

## ✅ Fase 3 — Narrativa para inversión

> **Meta:** que el demo cuente una historia en 2 minutos, no solo muestre features.

### 3.1 Dataset rico antes del video
- Mínimo 300–500 inmuebles con coordenadas válidas
- Distribuidos en varios sectores de Bogotá (no solo un barrio)
- Sin nulos en precio, área y coordenadas

### 3.2 Guión del demo (caso de uso grabable)
> *"Soy profesional de 28 años. Busco apartamento de 2 habitaciones, estrato 3–4, cerca al metro, entre 250 y 400 millones."*
> En 4 clics el mapa muestra exactamente eso, con score de ubicación en cada pin.

Estructura del video:
1. **(0:00–0:15)** El problema — mostrar FincaRaíz y su falta de contexto urbano
2. **(0:15–0:45)** La solución — abrir Geovivienda, aplicar filtros, ver el mapa
3. **(0:45–1:15)** El diferenciador — hacer clic en un pin, mostrar el score de ubicación
4. **(1:15–1:30)** La visión — "esto es solo el comienzo"

### 3.3 Landing page mínima
Una página simple antes del mapa:
- Nombre + propuesta de valor en una línea
- Botón "Explorar mapa"
- Da credibilidad frente a servir directamente el dashboard

**Checklist Fase 3:**
- [ ] +300 inmuebles en BD con coordenadas limpias
- [ ] Guión del demo escrito y ensayado
- [ ] Landing page mínima
- [ ] Video grabado y editado
- [ ] Post de LinkedIn redactado

---

## 🔮 Backlog futuro (post-inversión)

- Autenticación de usuarios (guardar búsquedas favoritas)
- Predicción de plusvalía basada en desarrollo urbano cercano
- Índice de seguridad por micro-sector (datos SIEDCO)
- Comparación con precios históricos (¿está caro o barato?)
- Alertas por email cuando aparece un inmueble que cumple los filtros
- Migración a base de datos multi-ciudad (Medellín, Cali)
- API pública para agencias inmobiliarias

---

*Última actualización: Abril 2026*
