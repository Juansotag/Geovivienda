# Modificaciones Pendientes y Análisis de Viabilidad

> [!NOTE]
> Este documento contiene la evaluación detallada de cada requerimiento pendiente en términos de **Dificultad de Implementación**, **Consumo de Tokens (API de Claude)** y **Impacto en la Experiencia de Usuario (UX)**.

---

## 📋 1. Formulario de Búsquedas

### 🔹 Incluir rango de áreas ($m^2$ mínimo y máximo)
- **Descripción:** Agregar campos para definir límites de área privada/construida en la búsqueda.
- **Dificultad:** 🟢 **Baja** (Añadir inputs en `busqueda_form.html`, guardar en PostgreSQL y filtrar en `services/busqueda.py`).
- **Consumo de Tokens:** ⚪ **0 tokens** (Filtro numérico estricto realizado en backend Python/SQL).
- **Mejora de Experiencia (UX):** ⭐⭐⭐⭐ (Alto: El espacio disponible es un criterio fundamental en la decisión de compra).

---

## 🏢 2. Pestaña de Inmuebles

### 🔹 Eliminar el botón "Estandarizar comodidades"
- **Descripción:** Remover el botón de la interfaz por ser innecesario.
- **Dificultad:** 🟢 **Baja** (Eliminar elemento HTML/JS en `templates/inmuebles.html`).
- **Consumo de Tokens:** ⚪ **0 tokens**.
- **Mejora de Experiencia (UX):** ⭐⭐ (Medio: Limpia y simplifica la interfaz de usuario).

### 🔹 Filtros por Municipio/Departamento y Validación Dropdown de Localidad/UPZ (Bogotá)
- **Descripción:** Reemplazar texto libre por selectores jerárquicos estructurados con las localidades y UPZs reales de Bogotá.
- **Dificultad:** 🟡 **Media** (Crear selectores dinámicos en JS conectándose a las APIs existentes en `app.py`).
- **Consumo de Tokens:** ⚪ **0 tokens**.
- **Mejora de Experiencia (UX):** ⭐⭐⭐⭐⭐ (Crítico: Evita errores de escritura y agiliza el filtrado).

### 🔹 Visibilidad de botones "Eliminar propiedad" y "Perfil" en Vista de Tarjetas
- **Descripción:** Hacer visibles y accesibles las acciones principales cuando la lista se visualiza en formato de cards.
- **Dificultad:** 🟢 **Baja** (Ajuste de estilos CSS / layout Flexbox).
- **Consumo de Tokens:** ⚪ **0 tokens**.
- **Mejora de Experiencia (UX):** ⭐⭐⭐ (Medio: Restaura acciones rápidas directas).

### 🔹 Galería completa de fotos por propiedad
- **Descripción:** Permitir navegar todas las fotografías extraídas del inmueble (no solo la portada).
- **Dificultad:** 🟡 **Media** (El extractor ya guarda los URLs; se requiere implementar un carrusel/modal en el frontend).
- **Consumo de Tokens:** ⚪ **0 tokens**.
- **Mejora de Experiencia (UX):** ⭐⭐⭐⭐⭐ (Crítico: El aspecto visual es determinante para evaluar el inmueble).

### 🔹 Métrica de Costo por Metro Cuadrado ($\text{COP}/m^2$)
- **Descripción:** Mostrar el valor $/m^2$ en la tabla de resultados y en las tarjetas.
- **Dificultad:** 🟢 **Baja** (Cálculo simple `precio / area` en backend o filtro Jinja2).
- **Consumo de Tokens:** ⚪ **0 tokens**.
- **Mejora de Experiencia (UX):** ⭐⭐⭐⭐⭐ (Crítico: Métrica reina del sector inmobiliario para comparar precio de oportunidad).

### 🔹 Ordenamiento interactivo por columnas (Mayor a Menor) y persistencia en tarjetas
- **Descripción:** Permitir ordenar dinámicamente por precio, área, score, etc., manteniendo el orden si se cambia de tabla a tarjetas.
- **Dificultad:** 🟡 **Media** (Integración de DataTables o módulo JS de ordenamiento en memoria).
- **Consumo de Tokens:** ⚪ **0 tokens**.
- **Mejora de Experiencia (UX):** ⭐⭐⭐⭐ (Alto: Facilita encontrar las mejores opciones al instante).

---

## 🧮 3. Calculadora de Crédito Hipotecario (Perfil del Inmueble)

### 🔹 Simulador de Cuota Mensual e Ingreso Mínimo Requerido
- **Descripción:** Calculadora interactiva bajo las comodidades con precio bloqueado, cuota inicial por defecto (30%), plazo (10 años), tasa (11% EA), cuota mensual estimada e ingreso mínimo requerido (3x cuota), con selector de moneda (COP, USD, EUR, etc.).
- **Dificultad:** 🟢 **Baja** (Componente 100% JavaScript en cliente usando fórmulas de amortización matemática).
- **Consumo de Tokens:** ⚪ **0 tokens** (Cálculo financiero local en el navegador).
- **Mejora de Experiencia (UX):** ⭐⭐⭐⭐⭐ (Crítico: Brinda certeza financiera inmediata al cliente para saber si puede pagar la propiedad).

---

## 👤 4. Pestaña de Clientes

### 🔹 Ampliar perfil de cliente (Años en país, tipo de permiso/visa, lista extendida de países ONU/territorios y geocodificación de Ciudad)
- **Descripción:** Capturar información migratoria/residencia de clientes internacionales y validar ciudades reales con coordenadas.
- **Dificultad:** 🟡 **Media** (Actualizar schema `clientes`, ampliar formulario y conectar API de geocodificación para ciudades).
- **Consumo de Tokens:** 🟡 **Bajo** (Se envían un par de líneas adicionales de contexto en el prompt de Claude Sonnet).
- **Mejora de Experiencia (UX):** ⭐⭐⭐⭐ (Alto: Perfilamiento preciso para colombianos en el exterior y compradores internacionales).

---

## 🗺️ 5. Mapa del Entorno (GIS Interactivo)

### 🔹 Control de Capas Avanzado (Inmuebles, Hexágonos H3 con Tooltip/POIs y Puntos de Interés por categoría)
- **Descripción:** Permitir ocultar/mostrar filtros en un panel lateral limpio y explorar hexágonos H3 con métricas detalladas y POIs (colegios, hospitales, supermercados) al hacer clic.
- **Dificultad:** 🔴 **Alta** (Refactorización importante de Leaflet.js para manejo de eventos, tooltips reactivos y capas geográficas).
- **Consumo de Tokens:** ⚪ **0 tokens** (Los datos geográficos ya están pre-calculados en archivos GeoJSON).
- **Mejora de Experiencia (UX):** ⭐⭐⭐⭐⭐ (Efecto WOW / Nivel Profesional: Permite analizar la calidad del barrio visualmente).

### 🔹 Integración de Mapa Base de Google Maps
- **Descripción:** Cambiar la capa base del mapa por las baldosas de Google Maps.
- **Dificultad:** 🟡 **Media** (Configuración de capa tile de Google Maps en Leaflet o SDK oficial).
- **Consumo de Tokens (Anthropic):** ⚪ **0 tokens**.
- **Costo Económico Externo:** ⚠️ Google exige tarjeta de crédito y otorga $200 USD/mes gratis (~28,000 cargas). Si se supera, genera cobro en USD. *Alternativa 100% gratuita:* CartoDB Positron / Mapbox.
- **Mejora de Experiencia (UX):** ⭐⭐⭐ (Medio-Alto: Aporta familiaridad visual).

---

## 🤖 6. Perfil del Inmueble & Chatbot del Asesor

### 🔹 Convertir el Análisis del Asesor en un Chatbot Interactivo
- **Descripción:** Transformar el texto estático de análisis en una ventana de chat interactiva donde el usuario puede hacerle preguntas en vivo a la IA sobre la propiedad o el sector.
- **Dificultad:** 🔴 **Alta** (Crear endpoint `/api/inmuebles/<id>/chat`, administrar historial de mensajes en sesión/DB e interfaz flotante de chat).
- **Consumo de Tokens:** 🔴 **Alto** (Cada pregunta del usuario re-envía el historial de la conversación y la ficha técnica del inmueble a Claude Sonnet).
- **Mejora de Experiencia (UX):** ⭐⭐⭐⭐⭐ (Revolucionario: Permite despejar dudas específicas sobre el inmueble en tiempo real).

---

## 📊 Cuadro Resumen de Priorización Recomendada

| Función | Dificultad | Consumo Tokens | Impacto UX | Prioridad Recomendada |
| :--- | :---: | :---: | :---: | :---: |
| **Métrica $/m² y Galería de Fotos** | 🟢 Baja / 🟡 Media | 0 tokens | ⭐⭐⭐⭐⭐ | 🚀 **Fase 1 (Inmediata)** |
| **Calculadora de Crédito Hipotecario** | 🟢 Baja | 0 tokens | ⭐⭐⭐⭐⭐ | 🚀 **Fase 1 (Inmediata)** |
| **Campos de Área min/max en Búsqueda** | 🟢 Baja | 0 tokens | ⭐⭐⭐⭐ | 🚀 **Fase 1 (Inmediata)** |
| **Dropdowns Localidad/UPZ y Ordenamiento** | 🟡 Media | 0 tokens | ⭐⭐⭐⭐⭐ | 🚀 **Fase 1 (Inmediata)** |
| **Perfil Ampliado de Clientes + Países** | 🟡 Media | Bajo | ⭐⭐⭐⭐ | 🔷 **Fase 2** |
| **Mapa del Entorno (Capas H3 + POIs)** | 🔴 Alta | 0 tokens | ⭐⭐⭐⭐⭐ | 🔷 **Fase 2** |
| **Chatbot del Asesor IA** | 🔴 Alta | Alto | ⭐⭐⭐⭐⭐ | 🔶 **Fase 3** |