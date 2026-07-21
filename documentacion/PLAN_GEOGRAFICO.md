# Plan de Integración Geográfica y Mapeo H3 (Geovivienda)

Este documento establece la arquitectura de datos geoespaciales, la taxonomía de **58 variables urbanas**, la procedencia documental de los datos y el algoritmo de cálculo e imputación para la malla hexagonal **Uber H3 (Resolución 9 Micro-Urbana)** en la plataforma **Geovivienda**.

---

## 1. Encuadre Territorial y Resolución H3

* **Capa Oficial de UPZs Urbanas**: Se utiliza la capa detallada **`geodata/upz.geojson`** (112 UPZs urbanas detalladas: Santa Bárbara, Los Cedros, Doce de Octubre, Los Alcázares, La Candelaria, Marruecos, Diana Turbay, Lucero, El Rincón, etc.) para eliminar cualquier sesgo de zonas de páramo/rurales y garantizar coincidencia **100% sin huecos** con el registro delictivo.
* **Exclusiones Espaciales**: Exclusión estricta de Sumapaz, UPR Río Tunjuelo, UPR Río Blanco y UPR Zona Norte.
* **Malla Hexagonal (Uber H3 - Resolución 9)**:
  * Diámetro aproximado por celda: **~300 metros** (área de ~0.1 $km^2$, radio de cobertura caminable ~150m).
  * Total de celdas en el casco urbano consolidado: **3,766 hexágonos urbanos**.
  * Cada celda H3 almacena sus coordenadas de centroide (`lat`, `lng`), sus geometrías de contorno y el diccionario completo de variables en bruto (`val_*`) y rankings percentiles en rango `0.00` a `1.00` (`rank_*`).

---

## 2. Matriz Completa de Variables (58 Indicadores + Categorías)

### Dimensión A: Transporte y Movilidad (Ponderación Global: 10%)

| Variable Métrica (`val_*`) | Variable Ranking (`rank_*`) | Documento / Archivo de Origen | Algoritmo y Método de Cálculo | Uso e Interpretación en Scoring |
| :--- | :--- | :--- | :--- | :--- |
| `val_dist_brt` (m) | `rank_dist_brt` | `geodata/transporte/brt.geojson`<br>`geodata/transporte/cable.geojson` | Distancia mínima (m) del centroide H3 a la estación más cercana de TransMilenio BRT o TransMiCable. | + Movilidad en transporte masivo de alta capacidad. |
| `val_brt_500m` | `rank_brt_500m` | `geodata/transporte/brt.geojson`<br>`geodata/transporte/cable.geojson` | Conteo de estaciones de TransMilenio BRT o TransMiCable en un radio buffer de 500m. | + Densidad de acceso a transporte masivo. |
| `val_dist_sitp` (m) | `rank_dist_sitp` | `geodata/transporte/bus.geojson` | Distancia euclidiana mínima del centroide H3 al paradero SITP más cercano. | + Conectividad local zonal. |
| `val_sitp_300m` | `rank_sitp_300m` | `geodata/transporte/bus.geojson` | Conteo de paraderos de bus SITP en un radio buffer de 300m. | + Cobertura caminable de bus urbano. |
| `val_dist_metro` (m) | `rank_dist_metro` | `geodata/transporte/ferreo.geojson` | Distancia mínima (m) del centroide H3 al trazado/estación de la Primera Línea del Metro (Proyección EPSG:6247). | + Valorización futura y transporte ferroviario. |
| `val_dist_ciclo` (m) | `rank_dist_ciclo` | `geodata/entorno/ambiente/ciclovia.geojson`<br>`static/geo/cicloalameda.geojson`<br>`static/geo/cliclorutas.geojson` | Distancia mínima (m) al segmento de ciclorruta o cicloalameda más cercano. | + Movilidad sostenible y ciclista. |

---

### Dimensión B: Seguridad Ciudadana, Tránsito y Policía (Ponderación Global: 25%)

| Variable Métrica (`val_*`) | Variable Ranking (`rank_*`) | Documento / Archivo de Origen | Algoritmo y Método de Cálculo | Uso e Interpretación en Scoring |
| :--- | :--- | :--- | :--- | :--- |
| `val_hurtos_upz` | `rank_hurtos_upz` | `geodata/seguridad/crimen/hurto.csv`<br>*(cruzado con `geodata/upz.geojson`)* | Suma total de denuncias históricas por hurtos en la UPZ contenedora (100% de coincidencia urbana). | **- Penalización por criminalidad**: Menor número de casos = Mayor ranking (1.00 = Máxima seguridad). |
| `val_hurtos_personas` | `rank_hurtos_personas` | `geodata/seguridad/crimen/hurto.csv` | Total de casos de hurto a personas reportados en la UPZ. | **- Penalización por riesgo a transeúntes**. |
| `val_hurtos_comercios` | `rank_hurtos_comercios` | `geodata/seguridad/crimen/hurto.csv` | Total de casos de hurto a comercios reportados en la UPZ. | **- Penalización por riesgo comercial**. |
| `val_hurtos_residencias` | `rank_hurtos_residencias` | `geodata/seguridad/crimen/hurto.csv` | Total de casos de hurto a residencias reportados en la UPZ. | **- Penalización por riesgo residencial**. |
| `val_hurtos_vehiculos` | `rank_hurtos_vehiculos` | `geodata/seguridad/crimen/hurto.csv` | Total de casos de hurto a automotores y motocicletas reportados en la UPZ. | **- Penalización por riesgo vehicular**. |
| `val_siniestros_viales_300m` | `rank_siniestros_viales_300m` | `geodata/seguridad/crimen/siniestros.csv` | Conteo de accidentes de tránsito en un radio buffer de 300m alrededor del centroide. | **- Penalización por accidentalidad vial**. |
| `val_siniestros_graves_500m` | `rank_siniestros_graves_500m` | `geodata/seguridad/crimen/siniestros.csv` | Conteo de accidentes de tránsito con heridos o fallecidos en un radio buffer de 500m. | **- Penalización por severidad de riesgos viales**. |
| `val_dist_cai` (m) | `rank_dist_cai` | `geodata/seguridad/policia/centro_atencion_inmediata.geojson` | Distancia mínima (m) al CAI de policía más cercano. | + Percepción de presencia policial inmediata. |
| `val_dist_est_policia` (m) | `rank_dist_est_policia` | `geodata/seguridad/policia/estacion_policia.geojson` | Distancia mínima (m) a la Estación de Policía de la localidad. | + Cobertura institucional de policía. |
| `val_dist_equipamiento_justicia` (m) | `rank_dist_equipamiento_justicia` | `geodata/seguridad/policia/inspeccion_policia.geojson`<br>`geodata/seguridad/policia/sala_de_atencion.geojson`<br>`geodata/seguridad/policia/unidad_reaccion_inmediata.geojson` | Distancia mínima (m) a la URI, Inspección de Policía o Sala de Atención más cercana. | + Acceso a justicia y denuncia ciudadana. |

---

### Dimensión C: Estrato Socioeconómico y Valorización (Ponderación Global: 20%)

| Variable Métrica (`val_*`) | Variable Ranking (`rank_*`) | Documento / Archivo de Origen | Algoritmo y Método de Cálculo | Uso e Interpretación en Scoring |
| :--- | :--- | :--- | :--- | :--- |
| `estrato_promedio_200m` | `rank_estrato` | `static/geo/estratos.geojson` | Promedio del nivel de estrato socioeconómico (1.0 a 6.0) en un radio buffer de 200m. | **+ Beneficio a estratos altos**: Mayor estrato = Mayor ranking (1.00 = Estrato 6). |
| `val_avaluo_catastral_m2` ($COP/m^2$) | `rank_avaluo_catastral_m2` | `geodata/entorno/uso/avaluo_catastral_medio.geojson` | Promedio del avalúo catastral por $m^2$ de la manzana donde se ubica el centroide H3. | + Valorización comercial del entorno inmobiliario. |

---

### Dimensión D: POIs, Servicios y Comercio (Ponderación Global: 15%)

| Variable Métrica (`val_*`) | Variable Ranking (`rank_*`) | Documento / Archivo de Origen | Algoritmo y Método de Cálculo | Uso e Interpretación en Scoring |
| :--- | :--- | :--- | :--- | :--- |
| `val_dist_d1_ara` (m) | `rank_dist_d1_ara` | `geodata/entorno/poi/supermercados_hard_discount.geojson` | Distancia mínima (m) a la tienda de descuento D1 o Ara más cercana. | + Conveniencia de abastecimiento cotidiano. |
| `val_conteo_hard_discount_500m` | `rank_conteo_hard_discount_500m` | `geodata/entorno/poi/supermercados_hard_discount.geojson` | Conteo de tiendas D1 y Ara en un radio buffer de 500m. | + Densidad de comercio de descuento. |
| `val_dist_supermercado_premium` (m) | `rank_dist_supermercado_premium` | `geodata/entorno/poi/pois_bogota_completo.geojson` | Distancia mínima (m) a supermercados Carulla, Éxito, Olímpica o Jumbo. | + Oferta de supermercados de formato grande/premium. |
| `val_dist_centro_comercial` (m) | `rank_dist_centro_comercial` | `geodata/entorno/poi/centros_comerciales.geojson` | Distancia mínima (m) a Malls o Centros Comerciales. | + Oferta de entretenimiento, banca y servicios. |
| `val_dist_hospital` (m) | `rank_dist_hospital` | `geodata/entorno/poi/salud_hospitales.geojson` | Distancia mínima (m) al hospital, clínica o centro de salud más cercano. | + Cobertura de emergencias y salud. |
| `val_hospitales_500m` | `rank_hospitales_500m` | `geodata/entorno/poi/salud_hospitales.geojson` | Conteo de centros de salud en un radio buffer de 500m. | + Densidad de servicios médicos. |
| `val_dist_colegio` (m) | `rank_dist_colegio` | `geodata/entorno/poi/educacion_colegios.geojson` | Distancia mínima (m) al colegio o universidad más cercana. | + Equipamiento educativo para familias. |
| `val_colegios_500m` | `rank_colegios_500m` | `geodata/entorno/poi/educacion_colegios.geojson` | Conteo de sedes educativas en un radio buffer de 500m. | + Densidad de oferta escolar. |

---

### Dimensión E: Entorno, Parques, Arbolado y Servicios Públicos (Ponderación Global: 25%)

| Variable Métrica (`val_*`) | Variable Ranking (`rank_*`) | Documento / Archivo de Origen | Algoritmo y Método de Cálculo | Uso e Interpretación en Scoring |
| :--- | :--- | :--- | :--- | :--- |
| `val_dist_parque` (m) | `rank_dist_parque` | `geodata/entorno/ambiente/parques.geojson` | Distancia mínima (m) al polígono de parque urbano más cercano (Proyección EPSG:6247). | **+ Zonas verdes**: Menor distancia = Mayor ranking (15% del score global). |
| `val_dist_recreacion_deporte` (m) | `rank_dist_recreacion_deporte` | `geodata/entorno/servicios_publicos/gimnasio.geojson`<br>`geodata/entorno/servicios_publicos/mobiliariodeportivo.geojson`<br>`geodata/entorno/servicios_publicos/parque_infantil.geojson` | Distancia mínima (m) a canchas sintéticas, gimnasios biosaludables o parques infantiles. | + Bienestar y recreación activa. |
| `val_arboles_300m` | `rank_arboles_300m` | `geodata/entorno/ambiente/arbolado_urbano.geojson` | Conteo de árboles censados por el Jardín Botánico en un radio buffer de 300m (10% del score global). | + Sombra, paisaje y calidad ambiental. |
| `val_dist_basura` (m) | `rank_dist_basura` | `geodata/entorno/servicios_publicos/puntos_criticos_arrojo_clandestino_residuos.geojson` | Distancia mínima (m) al punto crítico de arrojo clandestino de basuras/escombros. | **- Penalización por cercanía a focos de basura**. |
| `val_basuras_300m` | `rank_basuras_300m` | `geodata/entorno/servicios_publicos/puntos_criticos_arrojo_clandestino_residuos.geojson` | Conteo de puntos críticos de basuras en un radio buffer de 300m. | **- Penalización por desaseo ambiental local**. |

---

### Dimensión F: Variables Ambientales y Climatología

| Variable Métrica (`val_*`) | Variable Ranking (`rank_*`) | Documento / Archivo de Origen | Algoritmo y Método de Cálculo | Uso e Interpretación en Scoring |
| :--- | :--- | :--- | :--- | :--- |
| `val_pm25` ($\mu g/m^3$) | `rank_pm25` | `geodata/entorno/ambiente/pm25_promedio_anual_2024.geojson` | Concentración media anual de material particulado PM2.5 en la celda H3. | **- Contaminación del aire**: Menor PM2.5 = Mayor ranking. |
| `val_temperatura` (°C) | `rank_temperatura` | `geodata/entorno/ambiente/temperatura_promedio_2024.geojson` | Temperatura promedio anual (°C) imputada por el polígono térmico. | Caracterización de microclima e isla de calor. |
| `val_precipitacion` (mm) | `rank_precipitacion` | `geodata/entorno/ambiente/precipitacion_acumulada_2024.geojson` | Pluviometría acumulada anual (mm) en la zona. | Caracterización climatológica de pluviosidad. |

---

### Dimensión G: Identificadores y Normativa POT

| Variable | Tipo de Dato | Documento / Archivo de Origen | Algoritmo y Método de Cálculo | Uso e Interpretación |
| :--- | :--- | :--- | :--- | :--- |
| `h3_index` | Texto | Sistema H3 | Código alfanumérico único de la celda Uber H3 Resolución 9. | Identificador espacial único. |
| `localidad` | Texto | `static/geo/localidad.geojson` | Nombre de la localidad contenedora del centroide H3 (Point-in-Polygon). | Agregación administrativa municipal. |
| `upz` | Texto | `geodata/upz.geojson` | Nombre de la UPZ detallada contenedora del centroide H3 (Point-in-Polygon). | Delimitación urbana delictiva y normativa. |
| `uso_suelo_predominante` | Texto | `geodata/entorno/uso/uso_suelo_manzana.geojson` | Uso de suelo predominante en la manzana (Residencial, Comercial, Dotacional, Mixto). | Compatibilidad de entorno residencial. |
| `area_actividad_pot` | Texto | `geodata/areaactividad/AreaActividad.shp` | Tratamiento urbanístico asignado por el Plan de Ordenamiento Territorial (POT). | Vocación urbanística de desarrollo. |

---

## 3. Fórmula del Score Sintético H3 Global (`score_h3_global`)

Para primar los barrios de **estratos altos con baja criminalidad, parques, comercio, transporte de alta capacidad y arbolado**, la fórmula sintética ponderada se calcula como:

$$ \text{Score H3 Global} = (0.25 \times \text{rank\_hurtos\_upz}) + (0.20 \times \text{rank\_estrato}) + (0.15 \times \text{rank\_dist\_parque}) + (0.15 \times \text{Comercio}) + (0.10 \times \text{rank\_dist\_brt}) + (0.10 \times \text{rank\_arboles\_300m}) $$

Donde la sub-componente de Comercio es:

$$ \text{Comercio} = (0.33 \times \text{rank\_dist\_d1\_ara}) + (0.33 \times \text{rank\_dist\_centro\_comercial}) + (0.34 \times \text{rank\_dist\_supermercado\_premium}) $$
