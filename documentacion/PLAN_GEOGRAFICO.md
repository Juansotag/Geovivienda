# Plan de Integración Geográfica y Mapeo H3 (Geovivienda)

Este documento establece la arquitectura de datos geoespaciales, la taxonomía de variables y la metodología de imputación espacial para construir la malla hexagonal **Uber H3 (Resolución 9 Micro-Urbana)** en la plataforma **Geovivienda**.

---

## 1. Definición Territorial Base y Encuadre H3

* **Capa Oficial de UPZs Urbanas**: Se utiliza la capa detallada **`geodata/upz.geojson`** (112 UPZs urbanas detalladas: Santa Bárbara, Los Cedros, Doce de Octubre, Los Alcázares, La Candelaria, Marruecos, Diana Turbay, Lucero, El Rincón, etc.) para eliminar cualquier sesgo de zonas de páramo/rurales y garantizar coincidencia **100% sin huecos** con el registro delictivo.
* **Exclusiones Espaciales**: Exclusión estricta de Sumapaz, UPR Río Tunjuelo, UPR Río Blanco y UPR Zona Norte.
* **Malla Hexagonal (Uber H3 - Resolución 9)**:
  * Diámetro aproximado por celda: **~300 metros** (área de ~0.1 $km^2$, radio de cobertura caminable ~150m).
  * Total de celdas en el casco urbano consolidado: **3,766 hexágonos urbanos**.
  * Cada celda H3 almacena sus coordenadas de centroide (`lat`, `lng`), sus geometrías de contorno y el diccionario completo de variables en bruto (`val_*`) y rankings percentiles en rango `0.00` a `1.00` (`rank_*`).

---

## 2. Taxonomía de Variables e Imputación H3

### Dimensión A: Transporte y Movilidad (Ponderación 10%)
- **`val_dist_brt` / `rank_dist_brt`**: Distancia mínima a estaciones de TransMilenio BRT o TransMiCable (capas `brt.geojson` y `cable.geojson` unificadas).
- **`val_brt_500m` / `rank_brt_500m`**: Conteo de estaciones BRT + TransMiCable en radio de 500m.
- **`val_dist_sitp` / `rank_dist_sitp`**: Distancia mínima (m) a paraderos zonales SITP.
- **`val_sitp_300m` / `rank_sitp_300m`**: Conteo de paraderos SITP a menos de 300m.
- **`val_dist_metro` / `rank_dist_metro`**: Distancia mínima (m) al trazado/estación de la Primera Línea del Metro (Proyección nativa EPSG:6247 corregida).
- **`val_dist_ciclo` / `rank_dist_ciclo`**: Distancia mínima a tramos de ciclovías.

### Dimensión B: Seguridad Ciudadana y Policía (Ponderación 25%)
- **`val_hurtos_upz` / `rank_hurtos_upz`**: Total de casos de hurtos históricos por UPZ (coincidencia 100% sin huecos). Menor delincuencia = Mayor ranking.
- **`val_hurtos_personas` / `rank_hurtos_personas`**: Casos de hurto a personas por UPZ.
- **`val_hurtos_comercios` / `rank_hurtos_comercios`**: Casos de hurto a comercios por UPZ.
- **`val_hurtos_residencias` / `rank_hurtos_residencias`**: Casos de hurto a residencias por UPZ.
- **`val_hurtos_vehiculos` / `rank_hurtos_vehiculos`**: Casos de hurto a automotores y motocicletas por UPZ.
- **`val_dist_cai` / `rank_dist_cai`**: Distancia a CAI de Policía más cercano.
- **`val_dist_est_policia` / `rank_dist_est_policia`**: Distancia a Estación de Policía.

### Dimensión C: Estrato Socioeconómico y Valorización (Ponderación 20%)
- **`estrato_promedio_200m` / `rank_estrato`**: Estrato promedio ponderado (1 a 6) en radio de 200m.
- **`val_avaluo_catastral_m2` / `rank_avaluo_catastral`**: Avalúo catastral medio por $m^2$ de la manzana contenedora.

### Dimensión D: Entorno, Parques, Arbolado y Servicios (Ponderación 30%)
- **`val_dist_parque` / `rank_dist_parque`**: Distancia mínima a parques urbanos (Proyección nativa EPSG:6247 corregida) (15%).
- **`val_arboles_300m` / `rank_arboles_300m`**: Conteo de árboles censados en buffer de 300m (10%).
- **`val_dist_d1_ara` / `rank_dist_d1_ara`**: Distancia a tiendas D1 o Ara (5%).
- **`val_dist_centro_comercial` / `rank_dist_centro_comercial`**: Distancia a Malls y Centros Comerciales (5%).
- **`val_dist_supermercado_premium` / `rank_dist_supermercado_premium`**: Distancia a Carulla, Éxito, Olímpica o Jumbo (5%).
- **`val_dist_hospital` / `rank_dist_hospital`**, **`val_dist_colegio` / `rank_dist_colegio`**: Cobertura de salud y educación.
- **`val_dist_basura` / `rank_dist_basura`**, **`val_basuras_300m` / `rank_basuras_300m`**: Puntos críticos de residuos.

### Dimensión E: Variables Ambientales y Clima
- **`val_pm25` / `rank_pm25`**: Concentración de material particulado PM2.5 ($\mu g/m^3$).
- **`val_temperatura` / `rank_temperatura`**: Temperatura promedio anual (°C).
- **`val_precipitacion` / `rank_precipitacion`**: Pluviometría acumulada anual (mm).

---

## 3. Fórmula de Scoring Global Sintético H3 (`score_h3_global`)

$$ \text{Score H3 Global} = (0.25 \times \text{rank\_hurtos\_upz}) + (0.20 \times \text{rank\_estrato}) + (0.15 \times \text{rank\_dist\_parque}) + (0.15 \times \text{Comercio}) + (0.10 \times \text{rank\_dist\_brt}) + (0.10 \times \text{rank\_arboles\_300m}) $$

Donde $\text{Comercio} = (0.33 \times \text{rank\_dist\_d1\_ara}) + (0.33 \times \text{rank\_dist\_centro\_comercial}) + (0.34 \times \text{rank\_dist\_supermercado\_premium})$.
