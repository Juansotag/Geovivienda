# Plan del Proyecto GeoVivienda

Este documento describe la arquitectura y el flujo de trabajo para el desarrollo de la aplicación GeoVivienda.

## 1. Adquisición y Transformación de Datos Geográficos
**Objetivo:** Crear una base sólida de información geoespacial de Bogotá utilizando mallas hexagonales.

*   **Fuentes de Datos:** Datos Abiertos de Bogotá (Gobierno).
*   **Formatos de Entrada:** Shapefiles (`.shp`), KML, y otros formatos vectoriales.
*   **Procesamiento:**
    *   Limpieza de datos y análisis exploratorio (EDA).
    *   Conversión de geometrías a sistema de índice espacial hexagonal **H3** (Uber).
    *   Integración de variables del entorno en cada hexágono.
*   **Resultado Esperado:** Un dataset base donde cada fila representa un hexágono y cada columna una característica geográfica o demográfica de esa zona.

## 2. Web Scraping de Oferta Inmobiliaria
**Objetivo:** Mantener una base de datos actualizada de apartamentos en arriendo.

*   **Herramienta:** Script de Python (`.py`) automatizado.
*   **Frecuencia:** Ejecución periódica (e.g., cada 24 horas o semanalmente).
*   **Lógica:**
    *   Extracción de información de portales inmobiliarios relevantes.
    *   **Validación de duplicados:** Asegurar que no se descarguen apartamentos ya existentes en la base de datos.
    *   Persistencia de datos históricos.

## 3. Integración y Lógica de Negocio
**Objetivo:** Cruzar la oferta inmobiliaria con las características del entorno.

*   **Entradas:** Rango de precios definido por el usuario (UI/UX).
*   **Proceso de Mapeo:**
    1.  Filtrar apartamentos dentro del rango de precios seleccionado.
    2.  Utilizar las coordenadas (Latitud/Longitud) de cada apartamento para ubicarlo en el hexágono H3 correspondiente.
    3.  **Herencia de Variables:** Asignar al apartamento las variables del entorno (ruido, seguridad, transporte, etc.) propias de su hexágono.
*   **Estructura de Datos Resultante:** Dataset consolidado de apartamentos enriquecidos con datos espaciales.

## 4. Visualización y Análisis (UI/UX)
**Objetivo:** Presentar insights sobre la distribución de la oferta.

*   **Interfaz:** Permitir al usuario seleccionar filtros (precio).
*   **Salida Gráfica:**
    *   Gráficas de distribución de las variables del entorno para los apartamentos filtrados.
    *   Comparativa de características según el precio.
