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

# **Uso de FLS para archivos grandes**

Este documento explica paso a paso cómo actualizar un repositorio de Git que ya tienes clonado en tu computador local, independientemente del IDE que uses (por ejemplo Antigravity u otro editor). El proceso se hace usando Git.

## REQUISITOS PREVIOS
1. Tener Git instalado en tu computador.
2. Tener el repositorio ya clonado en tu máquina.
3. Tener acceso al repositorio remoto (GitHub, GitLab, Bitbucket, etc.).

## PASO 1: ABRIR LA CARPETA DEL PROYECTO
Abre la carpeta donde está tu proyecto:
- Puedes hacerlo desde tu IDE.
- O desde el explorador de archivos y luego abrir una terminal allí.

Es importante que la terminal esté ubicada en la raíz del repositorio (donde está la carpeta .git).

## PASO 2: VERIFICAR EL ESTADO DEL REPOSITORIO

En la terminal, ejecute:

git status

Este comando te indica:
- Si tienes archivos modificados.
- Si hay cambios sin guardar.
- Si tu rama está adelantada o atrasada respecto al repositorio remoto.

## **PASO 3: GUARDAR O DESCARTAR CAMBIOS LOCALES (SI EXISTEN)**
Si tienes cambios locales, tienes dos opciones:

A) Guardar los cambios (commit):
git add .
git commit -m "Mensaje descriptivo del cambio"

B) Descartar los cambios (¡cuidado!):
git checkout .

## **PASO 4: ACTUALIZAR EL REPOSITORIO DESDE EL REMOTO**

Para traer los cambios más recientes del repositorio remoto, ejecuta:

git pull origin main

Nota:
- Cambia 'main' por 'master' u otra rama si tu proyecto usa un nombre diferente.

Este comando:
- Descarga los cambios del repositorio remoto.
- Los integra automáticamente en tu copia local.

## **PASO 5: VERIFICAR QUE TODO ESTÉ ACTUALIZADO**

Vuelve a ejecutar:

git status

Si todo está bien, deberías ver un mensaje indicando que tu rama está actualizada.

## **PASO 6: USO DESDE EL IDE**

Una vez actualizado el repositorio:
- Reinicia el IDE si no ves los cambios.
- Verifica que los archivos nuevos o modificados aparezcan correctamente.
- Ejecuta nuevamente tu código si es necesario.

## **ERRORES COMUNES**

- Conflictos de merge: ocurren cuando Git no puede unir cambios automáticamente.
- Falta de permisos: asegúrate de tener acceso al repositorio remoto.
- Rama incorrecta: verifica en qué rama estás con:

git branch