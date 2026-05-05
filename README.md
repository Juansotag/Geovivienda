# 🏠 Geovivienda: Location, Location, Location

> **"En el mercado inmobiliario, las tres cosas más importantes son: ubicación, ubicación y ubicación."**

A pesar de este mantra, la mayoría de las plataformas actuales en Colombia se limitan a mostrar el interior de una propiedad —habitaciones, baños, metros cuadrados— sin ofrecer un análisis sistemático y profundo de su entorno. **Geovivienda** nace para cambiar esto.

---

## El Problema

Las herramientas tradicionales de búsqueda de inmuebles fallan al ignorar el contexto urbano. Un apartamento puede ser perfecto por dentro, pero ¿qué tan seguro es el barrio? ¿Qué tan conectado está con el transporte masivo? ¿Cuál es su estrato real en comparación con el precio?

## La Solución

Geovivienda es un servicio de inteligencia inmobiliaria que permite encontrar el próximo hogar basado no solo en las características del inmueble, sino en la **calidad objetiva de su ubicación**.

### Características Principales

- **Scraping Avanzado**: Extracción automatizada de datos desde FincaRaíz con Selenium (Headless) y BeautifulSoup.
- **Inteligencia Geoespacial**: Captura de coordenadas precisas (Latitud/Longitud) y enriquecimiento con datos de contexto urbano mediante GeoPandas.
- **Análisis Espacial Integrado**: Cálculo automático de distancia al transporte (Transmilenio, SITP, Ciclorrutas) y estrato socioeconómico promedio ponderado por área en un radio de 200 m.
- **Capas GIS Interactivas**: Visualización de estratos, estaciones de TransMilenio, SITP, Metro, Cable y Ciclorrutas sobre el mapa.
- **Dashboard Interactivo**: Interfaz web moderna construida en Flask y Leaflet.js con filtros en tiempo real.

---

## Stack Tecnológico

| Componente | Tecnología | Rol |
| :--- | :--- | :--- |
| **Backend** | Python / Flask | API REST, ruteo y lógica de negocio |
| **Scraping** | Selenium (WebDriver) | Navegación automatizada en SPAs con scroll dinámico |
| **Parsing** | BeautifulSoup4 | Extracción de datos del DOM estructurado |
| **Data Engine** | Pandas / NumPy | Limpieza, normalización y transformación de datos |
| **Análisis Espacial** | GeoPandas / Shapely | Cálculo de distancias y superposición de capas GIS |
| **Frontend** | Vanilla JS / Leaflet.js | Mapa interactivo, capas GeoJSON y filtrado dinámico |
| **UI/UX** | CSS3 (Light Mode) | Diseño moderno tipo dashboard premium |
| **Infraestructura** | Gunicorn / Nixpacks | Servidor de producción y despliegue en Railway |

---

## Arquitectura

```
Tu máquina local                      Servidor público (Railway)
────────────────                      ─────────────────────────
extractor_links.py   →  CSV Raw  →    app.py (solo lectura)
extractor_detalles.py               └── /api/data  → frontend
spatial_analysis.py  →  CSV Enriquecido
                         └── dist_sitp
                         └── dist_tm
                         └── dist_ciclo
                         └── estrato_promedio_200m
```

> El scraping y el análisis espacial corren **solo en local**. El servidor público sirve los datos ya procesados.

---

## Pipeline de Datos

```
FincaRaíz (web)
    │
    ▼
extractor_links.py      → Lista de URLs de propiedades
    │
    ▼
extractor_detalles.py   → dataset_fincaraiz.csv
    │                     (precio, área, habitaciones, lat/lng, ...)
    ▼
spatial_analysis.py     → dataset_enriquecido.csv
    │                     + dist_sitp  (metros)
    │                     + dist_tm    (metros)
    │                     + dist_ciclo (metros)
    │                     + estrato_promedio_200m
    ▼
app.py / Flask API      → /api/data → frontend
```

### Campos del Dataset Enriquecido

| Campo | Descripción |
| :--- | :--- |
| `URL` | Enlace a la ficha en FincaRaíz |
| `Precio_Venta` | Precio total en COP |
| `Area_Metros` | Área total en m² |
| `Habitaciones` | Número de habitaciones |
| `Banos` | Número de baños |
| `Parqueaderos` | Número de parqueaderos |
| `Estrato` | Estrato declarado en el aviso |
| `Latitud` / `Longitud` | Coordenadas geográficas |
| `dist_sitp` | Distancia en metros a la estación SITP más cercana |
| `dist_tm` | Distancia en metros a la estación Transmilenio más cercana |
| `dist_ciclo` | Distancia en metros a la ciclorruta más cercana |
| `estrato_promedio_200m` | Estrato promedio ponderado por área en radio de 200 m |

---

## Instalación y Uso Local

### Requisitos Previos

- Python 3.10+
- Google Chrome instalado (para Selenium)
- Conda o virtualenv recomendado

### Setup

```bash
# 1. Clonar el repositorio
git clone https://github.com/tu-usuario/Geovivienda.git
cd Geovivienda

# 2. Crear entorno virtual
conda create -n geovivienda python=3.11 -y
conda activate geovivienda

# 3. Instalar dependencias Python
pip install -r requirements.txt

# 4. Instalar GeoPandas (con dependencias espaciales)
conda install geopandas -c conda-forge -y
```

> **Nota:** GeoPandas requiere GDAL, Fiona y Shapely. Instalarla con `conda-forge` es la forma más confiable en Windows.

### Ejecutar el Scraping

```bash
# El frontend de la app gestiona el scraping desde el sidebar.
# Para correrlo manualmente desde Python:
python extractor_links.py    # Extrae URLs
python extractor_detalles.py # Extrae detalles y guarda dataset_fincaraiz.csv
python spatial_analysis.py   # Enriquece con datos espaciales
```

### Levantar el Servidor

```bash
python app.py
# → http://localhost:5000
```

---

## Interfaz y Funcionalidad

La plataforma ofrece una experiencia centralizada para el análisis inmobiliario:

1. **Panel de Filtros (Sidebar)**: Define zona (slug de FincaRaíz), tipo de operación, presupuesto, estratos, habitaciones, baños y comodidades.
2. **Mapa Interactivo (Leaflet)**: Visualiza los inmuebles geolocalizados con capas superponibles:
   - **Estratos**: Polígonos con clasificación socioeconómica de la ciudad.
   - **Transmilenio / SITP / Metro / Cable**: Estaciones de transporte masivo.
   - **Ciclorrutas**: Red de ciclovías.
3. **Inventario Geolocalizado**: Tabla dinámica con precio total, precio por m² y ubicación exacta.
4. **Log de Scraping en Tiempo Real**: Visualización del progreso del rastreo vía polling a `/api/status`.

---

## Persistencia

### Estado Actual
Los datos se almacenan localmente en:
- `dataset_fincaraiz.csv` — datos crudos extraídos de FincaRaíz.
- `dataset_enriquecido.csv` — datos con análisis espacial integrado.

Formato: separador `;`, decimales `,` (compatible con Excel en español).

### Evolución Planificada
Migración a **PostgreSQL en Supabase** para:
- Datos compartidos entre usuarios sin re-descarga.
- Consultas eficientes sobre volúmenes masivos.
- Sincronización automática de precios y disponibilidad.

---

## Retos y Limitaciones Conocidas

- **Peso de Capas GeoJSON**: La capa de Estratos es muy pesada y puede causar problemas de memoria en entornos de despliegue con recursos limitados (Railway free tier). La solución a largo plazo es convertir a PMTiles.
- **Anti-Scraping**: FincaRaíz usa lazy-loading agresivo. El extractor aplica scroll progresivo y tiempos de espera para garantizar la captura completa.
- **Análisis Espacial Lento**: El cálculo de estrato promedio con `gpd.overlay` por propiedad es costoso. Para datasets grandes (+500 inmuebles) puede tardar varios minutos.

---

## Roadmap

| Fase | Meta |
|------|------|
| **Fase 1** — Infraestructura | Migrar a Supabase PostgreSQL + PMTiles en Storage |
| **Fase 2** — UI/UX | Score de ubicación, sliders, vista comparativa, popups ricos |
| **Fase 3** — Demo para inversión | 300+ inmuebles, landing page, video LinkedIn |
| **Futuro** | Predicción de plusvalía, índice de seguridad, alertas por email, multi-ciudad |

Ver [`geovivienda_roadmap.md`](./geovivienda_roadmap.md) para el plan técnico detallado.

---

## Estructura del Repositorio

```
Geovivienda/
├── app.py                   # Servidor Flask y API REST
├── extractor_links.py       # Módulo de extracción de URLs (Selenium)
├── extractor_detalles.py    # Módulo de extracción de detalles (BS4)
├── spatial_analysis.py      # Pipeline de análisis espacial (GeoPandas)
├── dataset_fincaraiz.csv    # Dataset crudo (generado localmente)
├── dataset_enriquecido.csv  # Dataset enriquecido (generado localmente)
├── requirements.txt         # Dependencias del servidor
├── Procfile                 # Configuración de Gunicorn
├── nixpacks.toml            # Configuración de despliegue en Railway
├── static/
│   ├── script.js            # Lógica del frontend (Leaflet, filtros, API)
│   ├── style.css            # Estilos del dashboard
│   └── geo/                 # Capas GeoJSON (estratos, transporte, ciclorrutas)
├── templates/
│   └── index.html           # Plantilla principal del dashboard
└── geovivienda_roadmap.md   # Roadmap técnico detallado
```

---

## Visión de Futuro

Este proyecto no es solo un buscador; es la base para una **red de agentes de IA** dedicados al sector inmobiliario. La infraestructura de datos espaciales generada aquí servirá para:

- Predicción de plusvalía basada en desarrollo urbano cercano.
- Recomendaciones personalizadas por estilo de vida.
- Análisis de riesgo y seguridad por micro-sector (datos SIEDCO).
- Comparación con precios históricos.
- API pública para agencias inmobiliarias.

---

*Desarrollado para transformar la búsqueda de vivienda en Colombia.*
