# Geovivienda

## Descripción general

**Geovivienda** es un proyecto académico de analítica espacial y ciencia de datos cuyo objetivo es apoyar la toma de decisiones de usuarios individuales que buscan **arrendar un apartamento en Bogotá**, permitiéndoles explorar qué zonas ofrecen una **mejor calidad del entorno urbano** dado un **presupuesto mensual fijo**.

El proyecto integra datos de ofertas inmobiliarias obtenidas mediante *web scraping* con información territorial y urbana heterogénea (seguridad, transporte, servicios, espacio público, entre otros), utilizando **hexágonos H3** como unidad espacial común. A partir de esta integración, Geovivienda permite analizar y visualizar **trade-offs de localización** mediante distribuciones comparativas de variables de vivienda y entorno.

---

## Pregunta de investigación

> **¿En qué zonas de Bogotá puedo arrendar un apartamento maximizando la calidad del entorno urbano, dado un presupuesto mensual específico?**

El proyecto no busca recomendar una vivienda óptima ni construir un ranking automático, sino **describir y contextualizar** las alternativas reales disponibles para el usuario, facilitando una exploración informada del mercado.

---

## Usuario objetivo

* Usuario individual en búsqueda de apartamento en arriendo
* Interesado en comparar alternativas reales dentro de su presupuesto
* Proyecto orientado a fines académicos y de portafolio en *Machine Learning* y *Data Science*

---

## Alcance del proyecto (MVP)

* Ciudad: **Bogotá D.C.**
* Tipo de inmueble: **Apartamentos en arriendo**
* Fuente inmobiliaria: **Una única plataforma de bienes raíces**
* Actualización de datos: **Semanal**
* Enfoque: **Descriptivo y exploratorio**

No se incluyen modelos predictivos, sistemas de recomendación ni ponderaciones personalizadas de variables.

---

## Fuentes de datos

### 1. Datos inmobiliarios (web scraping)

Variables extraídas de la plataforma de bienes raíces:

* Precio de arriendo
* Área del apartamento (m²)
* Estrato socioeconómico (1–6)
* Número de habitaciones
* Número de baños
* Valor de la administración
* Variables dummy de características del inmueble, entre ellas:

  * Gas natural
  * Ascensor
  * Piso
  * Antigüedad
  * Otras amenidades disponibles
* Ubicación geográfica (latitud y longitud)

---

### 2. Datos del entorno urbano

Variables territoriales imputadas a cada inmueble a partir del hexágono H3 donde se ubica:

#### Transporte y movilidad

* Distancia a estación de TransMilenio
* Distancia a estación de metro
* Distancia a paraderos SITP
* Cercanía a ciclorutas

#### Educación

* Cercanía a colegios
* Puntaje promedio de las pruebas **SABER 11** de los colegios del entorno

#### Espacio público y equipamientos

* Cercanía a parques
* Cercanía a hospitales

#### Seguridad y riesgo

* Cercanía a CAI y estaciones de Policía
* Tasa promedio de accidentalidad vial en la zona

---

## Metodología

### Unidad espacial: Hexágonos H3

Se utilizan hexágonos H3 como unidad espacial estándar para:

* Integrar fuentes geográficas con distintas estructuras (puntos, polígonos, isocronas)
* Reducir la complejidad del *spatial join*
* Imputar características territoriales a cada apartamento mediante un único índice espacial

Cada apartamento es asignado a un hexágono H3, y hereda las variables agregadas del entorno correspondientes a dicho hexágono.

---

## Dataset analítico final

El resultado del procesamiento es un dataset a nivel de apartamento que contiene:

* Características propias del inmueble
* Variables del entorno urbano imputadas desde el hexágono H3

Este dataset constituye la base para el análisis exploratorio y la visualización.

---

## Análisis y visualización

Para un presupuesto mensual definido por el usuario:

* Se filtran los apartamentos dentro del rango de precio
* Se construyen **distribuciones comparativas** de variables clave, tanto del inmueble como del entorno

Ejemplos de visualizaciones:

* Distribución de metros cuadrados disponibles
* Distribución del número de habitaciones y baños
* Distribución de minutos a pie a estaciones de transporte público
* Distribución de indicadores de seguridad y accidentalidad
* Distribución de acceso a espacio verde y equipamientos

Adicionalmente, el usuario puede **seleccionar un apartamento específico** y observar su posición relativa dentro de cada distribución, permitiendo una comparación directa con el resto de las alternativas disponibles.

---

## Resultados esperados

* Comprensión clara de los trade-offs entre precio, localización y calidad del entorno
* Exploración informada del mercado inmobiliario dentro de un presupuesto realista
* Dataset y visualizaciones reproducibles para análisis urbano y espacial

---

## Tecnologías y herramientas

* Python
* Web scraping
* Pandas / GeoPandas
* H3
* Análisis espacial
* Visualización de datos (matplotlib / seaborn / herramientas interactivas)

---

## Limitaciones

* El proyecto no realiza recomendaciones automáticas
* No incorpora ponderaciones personalizadas de preferencias del usuario
* La calidad del análisis depende de la cobertura y actualización de las fuentes de datos

---

## Posibles extensiones futuras

* Incorporación de preferencias del usuario y ponderación de variables
* Clustering de zonas según perfiles urbanos
* Ranking de alternativas mediante métodos multicriterio
* Modelos predictivos de precios de arriendo
* Expansión a otras ciudades

---

**Geovivienda** busca demostrar cómo la integración de datos inmobiliarios y territoriales, combinada con analítica espacial, puede enriquecer la toma de decisiones urbanas desde un enfoque transparente e interpretable.
