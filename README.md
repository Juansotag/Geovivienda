# 🏠 Geovivienda: Location, Location, Location

![Geovivienda Banner](file:///C:/Users/juansoag/.gemini/antigravity/brain/2aedf88a-7a6c-4a33-aa6b-f7040f953e75/geovivienda_banner_1777601205769.png)

> **"En el mercado inmobiliario, las tres cosas más importantes son: ubicación, ubicación y ubicación."**

A pesar de este mantra, la mayoría de las plataformas actuales en Colombia se limitan a mostrar el interior de una propiedad (habitaciones, baños, metros cuadrados) sin ofrecer un análisis sistemático y profundo de su entorno. **Geovivienda** nace para cambiar esto.

---

## 🎯 El Problema
Las herramientas tradicionales de búsqueda de inmuebles fallan al ignorar el contexto urbano. Un apartamento puede ser perfecto por dentro, pero ¿qué tan seguro es el barrio? ¿Qué tan conectado está con el transporte masivo? ¿Cuál es su estrato real en comparación con su precio?

## 🚀 La Solución
Geovivienda es un servicio inteligente que permite a los usuarios encontrar su próximo hogar basado no solo en las características del inmueble, sino en la **calidad de su ubicación**.

### Características Principales
- 🔍 **Scraping Avanzado**: Extracción automatizada de datos desde FincaRaíz utilizando Selenium (Headless) y BeautifulSoup.
- 📍 **Inteligencia Geoespacial**: Captura de coordenadas precisas (Latitud/Longitud) para análisis de proximidad.
- 🚍 **Conectividad**: Integración con capas GeoJSON de transporte (Transmilenio, SITP) para evaluar la movilidad.
- 📊 **Análisis Comparativo**: Procesamiento de datos con Pandas para normalizar precios, estratos y áreas.
- 💻 **Dashboard Interactivo**: Interfaz web moderna construida en Flask para visualizar y filtrar resultados en tiempo real.

---

## 🛠️ Stack Tecnológico

## 🛠️ Stack Tecnológico Detallado

| Componente | Tecnología | Rol |
| :--- | :--- | :--- |
| **Backend** | Python / Flask | Gestión de API, ruteo y lógica de negocio. |
| **Scraping** | Selenium (WebDriver) | Navegación automatizada y scroll dinámico en SPAs. |
| **Parsing** | BeautifulSoup4 | Extracción de datos desde el DOM estructurado. |
| **Data Engine** | Pandas / NumPy | Limpieza, normalización y transformación de datos CSV. |
| **Frontend** | Vanilla JS / Leaflet.js | Mapa interactivo, gestión de capas GeoJSON y filtrado dinámico. |
| **UI/UX** | CSS3 (Dark Mode) | Diseño moderno con estética de "dashboard" premium. |
| **Infraestructura** | Gunicorn / Nixpacks | Configuración de servidor de producción y despliegue. |

---

## 🖥️ Interfaz y Funcionalidad

La plataforma ofrece una experiencia centralizada para el análisis inmobiliario:

![Dashboard Geovivienda](file:///C:/Users/juansoag/.gemini/antigravity/brain/2aedf88a-7a6c-4a33-aa6b-f7040f953e75/geovivienda_main_1777601570432.png)

1.  **Panel de Búsqueda y Filtros**: Ubicado en el sidebar, permite definir la zona (slug de FincaRaíz), tipo de operación, presupuesto y filtros técnicos (estratos, habitaciones, baños).
2.  **Mapa Interactivo (Leaflet)**: Visualiza los inmuebles geolocalizados. Incluye un sistema de **Capas (Layers)** para superponer información crítica:
    - 🏙️ **Estratos**: Capa de polígonos con la clasificación socioeconómica de la ciudad.
    - 🚍 **Transporte**: Estaciones de Transmilenio, SITP, Metro, Cable y Ciclorrutas.
3.  **Inventario Geolocalizado**: Una tabla dinámica que muestra el precio total, precio por m² y ubicación exacta, permitiendo la eliminación o limpieza de datos.

---

## 💾 Persistencia y Escalabilidad

### Estado Actual
Actualmente, los datos extraídos de FincaRaíz se almacenan localmente en un archivo `dataset_fincaraiz.csv` estructurado con punto y coma (`;`) y decimales en coma (`,`) para compatibilidad directa con Excel.

### Plan de Evolución
El objetivo a corto plazo es migrar hacia una **base de datos relacional en la nube** (PostgreSQL/Supabase). Esto permitirá:
- **Datos Compartidos**: Evitar que cada usuario tenga que descargar la misma información repetidamente.
- **Consultas Eficientes**: Filtrado a nivel de base de datos para manejar volúmenes masivos de inmuebles.
- **Sincronización**: Actualización automática de precios y disponibilidad sin intervención manual.

---

## ⚠️ Retos y Limitaciones Conocidas

- **Peso de Capas GeoJSON**: La capa de **Estratos** es extremadamente pesada. Esto genera problemas de memoria en entornos de despliegue limitados como **Railway**, donde la aplicación puede cargar pero falla al renderizar capas pesadas o se queda en blanco por falta de recursos.
- **Anti-Scraping**: FincaRaíz utiliza técnicas de lazy-loading agresivas, lo que requiere tiempos de espera (`sleep`) y scroll progresivo para asegurar la captura de todos los enlaces.

---

## 🔮 Visión de Futuro
Este proyecto no es solo un buscador; es la base para una **red de agentes de IA** dedicados al sector inmobiliario. La documentación técnica generada aquí servirá para alimentar modelos que puedan pivotar hacia:
- Predicción de plusvalía basada en desarrollo urbano.
- Recomendaciones personalizadas por estilo de vida.
- Análisis de riesgo y seguridad por micro-sectores.

---
*Desarrollado con ❤️ para transformar la búsqueda de vivienda en Colombia.*
