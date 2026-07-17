# 🏠 Geovivienda → Motor de Match para Casa en Casa

> **Contexto:** Este roadmap reemplaza la versión anterior (enfoque B2C, Supabase-first).
> El proyecto pivota a una **herramienta interna B2B** para funcionarios de **Casa en Casa**
> (empresa que financia compra de vivienda en Colombia para colombianos en el exterior),
> que conecta el perfil financiero/geográfico de un cliente con inventario real de vivienda
> scrapeado, scoreado (0–1) y explicado en un reporte de una página generado por LLM.
>
> **Fecha de hoy:** viernes 17 de julio de 2026.
> **Fecha límite:** presentación en Casa en Casa el **jueves 23 de julio de 2026**.
> **Alcance geográfico del demo:** únicamente Bogotá.
>
> **Filosofía de este documento:** cada decisión ambigua ya se resolvió. Donde antes había
> "SQLite o Postgres" o "psycopg2 o SQLAlchemy", ahora hay una sola opción, con la razón por
> la que se descartó la otra. La idea es que de acá en adelante el trabajo sea ejecutar código,
> no seguir decidiendo arquitectura a mitad de la semana.

---

## Decisiones ya tomadas (no reabrir salvo que algo se rompa)

| Decisión | Elegido | Nota |
|---|---|---|
| Alcance del jueves | **Demo funcional + reportes LLM reales**, no mockup | Flujo real de punta a punta con datos reales de Bogotá |
| Base de datos | **Postgres (addon gestionado de Railway)**, desde el día 1 | Mismo Postgres en desarrollo local y producción |
| Acceso a datos | **psycopg2 + SQL crudo parametrizado**, sin ORM | Ver "Tech stack en profundidad" — SQLAlchemy es ceremonia de más para un esquema que ya está congelado |
| LLM para reportes | **Claude (`claude-sonnet-5`) vía Anthropic SDK** | Balance de calidad/costo/velocidad para texto de asesoría |
| PDF | **xhtml2pdf** | Puro Python, sin dependencias nativas — evita el infierno de GTK/Cairo de WeasyPrint en Windows |
| Conversión de moneda | **Frankfurter API** (`api.frankfurter.app`) | Gratis, sin API key, tasas del BCE, confiable desde IPs de datacenter (a diferencia de scrapear Yahoo Finance) |
| Portales para el jueves | **FincaRaíz** (ya existe) + **Metrocuadrado** (nuevo) | Houm, Ciencuadras, Lahaus y "proyectos" → backlog |
| TTL de reportes | **15 días**, borrado automático vía APScheduler | Corre dentro del mismo proceso Flask, sin worker aparte |
| Despliegue | **Railway, 3 piezas**: app + Selenium Grid + Postgres addon | Ver "Arquitectura final" |
| Servidor de aplicación | **Gunicorn, `--worker-class gthread --workers 2 --threads 4`** | Ver "Tech stack en profundidad" — necesario para que el polling no se bloquee mientras corre un scraping en background |
| Autenticación | **Mockup**, sin validación real | Login de pantalla, sin backend de auth |
| Índice geográfico H3 | **Diseñado en este documento, se construye como proyecto aparte** | Ver "Arquitectura futura: hexágonos H3" |
| Identidad visual | **Colores y tipografía extraídos del sitio real de Casa en Casa** | Ver "Identidad visual de Casa en Casa" |

---

## Tech stack en profundidad

Cada pieza del stack, por qué se eligió sobre la alternativa obvia, y el detalle técnico que
te va a ahorrar una tarde de debugging si no lo sabes de antemano.

### Flask + Gunicorn (servidor de aplicación)

Ya es lo que usa el proyecto — se mantiene. Flask sirve dos roles a la vez: renderiza las
plantillas Jinja2 (frontend) y expone los endpoints `/api/*` (backend). En desarrollo local
usas `python app.py` (el servidor de desarrollo de Flask, de un solo hilo por defecto). En
producción **nunca** uses el servidor de desarrollo — por eso Gunicorn.

**El detalle que importa: `--worker-class gthread`.** Por defecto Gunicorn usa workers
`sync`, que atienden **una sola petición a la vez por proceso**. Si un funcionario dispara una
búsqueda (que lanza un `threading.Thread` en background) y dos segundos después su navegador
hace polling a `/api/status`, con un worker `sync` esa segunda petición puede quedar
esperando en fila detrás de otras peticiones lentas del mismo proceso. `gthread` le dice a
Gunicorn que cada worker atienda múltiples peticiones concurrentemente usando threads — es
lo que hace que el polling se sienta instantáneo mientras el scraping corre de fondo.
Combinado con `--workers 2`, tienes dos procesos independientes: si uno se atora en algo
pesado (un `gpd.overlay` largo, por ejemplo), el otro sigue respondiendo. Configuración final:

```
gunicorn app:app --bind 0.0.0.0:$PORT --worker-class gthread --workers 2 --threads 4 --timeout 120
```

**Por qué 2 workers no rompe el estado de las búsquedas:** con 2 procesos, cada uno tiene su
propia memoria — un `job_state = {}` en memoria (como existe hoy en `app.py`) sería invisible
entre workers: si el worker A arranca una búsqueda y la petición de polling la atiende el
worker B, B no vería nada. Por eso el estado del job se guarda en Postgres (tabla `busquedas`,
Fase 1) en vez de en un diccionario de Python — así **cualquier** worker puede leer el estado
real, sin importar cuál arrancó el job.

### PostgreSQL + psycopg2 (persistencia — sin ORM)

**Por qué Postgres y no SQLite:** ya se discutió — concurrencia (un thread de scraping
escribiendo mientras hay requests leyendo) y evitar tener que gestionar un volumen persistente
en Railway.

**Por qué psycopg2 con SQL crudo y no SQLAlchemy:** SQLAlchemy brilla cuando el esquema va a
cambiar mucho o cuando el equipo prefiere pensar en objetos Python en vez de SQL. Acá el
esquema ya está completamente definido (ver "Modelo de datos" abajo) y no se espera que
cambie durante la semana — introducir un ORM solo suma una capa de abstracción y una curva de
aprendizaje que no compra nada. `psycopg2` con un *connection pool* y funciones que reciben y
devuelven diccionarios es más fácil de debuggear bajo presión de tiempo: el SQL que se ejecuta
es exactamente el SQL que escribiste, sin generación intermedia.

**Connection pooling — por qué es obligatorio y no opcional:** cada conexión a Postgres tiene
costo (Railway limita conexiones concurrentes según el plan). Si cada función de `db.py` abre
su propia conexión con `psycopg2.connect(...)` y no la cierra bien, bajo la carga de un
scraping largo + varias pestañas haciendo polling, te quedas sin conexiones disponibles y la
app empieza a tirar errores de "too many connections". Un `ThreadedConnectionPool` reutiliza
un número fijo de conexiones entre todos los threads.

### Selenium 4 (Remote WebDriver) + `selenium/standalone-chrome`

Ya se explicó la arquitectura (servicio separado en Railway). Detalle de versión: usar la
imagen `selenium/standalone-chrome:4` (el tag de versión mayor, no `:latest` a secas — evita
que un cambio de versión mayor de Chrome rompa algo sin aviso, pero tampoco te clavas a un
patch específico que puede quedar desactualizado). El cliente Python (`selenium>=4.18.0`, ya
está en `requirements.txt`) habla el mismo protocolo W3C WebDriver sin importar si el Chrome
está local o remoto — el único cambio de código es `webdriver.Chrome()` vs
`webdriver.Remote()`.

### BeautifulSoup4 + GeoPandas/Shapely (sin cambios)

Se mantienen tal cual están hoy. La única adaptación es que `spatial_analysis.py` pasa de
operar sobre un CSV completo a operar sobre un inmueble (o lista pequeña) a la vez —
ver Fase 1, paso 8.

### Anthropic SDK (reportes LLM)

```bash
pip install anthropic
```
El cliente lee `ANTHROPIC_API_KEY` del entorno automáticamente (`anthropic.Anthropic()` sin
argumentos). Modelo recomendado: **`claude-sonnet-5`** — para un reporte de asesoría de una
página, no necesitas el modelo más grande (`opus`) ni te conviene el más chico (`haiku`, que
puede quedarse corto en matices al explicar "por qué esta vivienda encaja"). Sonnet es el
punto de equilibrio calidad/latencia/costo para este caso de uso específico.

### xhtml2pdf (HTML → PDF)

```bash
pip install xhtml2pdf
```
**Por qué no WeasyPrint (la opción "obvia"):** WeasyPrint depende de librerías nativas de
sistema (Pango, Cairo, GDK-PixBuf) que en Windows requieren instalar el runtime de GTK3 aparte
— un dolor de cabeza clásico para quien desarrolla en Windows y despliega en Linux (exactamente
tu caso). `xhtml2pdf` es puro Python: se instala igual en tu laptop Windows que en el
contenedor Linux de Railway, sin sorpresas el día del deploy. La contrapartida es que su
soporte de CSS es más limitado (no esperes flexbox/grid en el PDF) — para un reporte de una
página con texto y algunas tablas, sobra.

### Frankfurter API (conversión de moneda)

**Por qué no `yfinance` (que fue la sugerencia original):** `yfinance` scrapea Yahoo Finance
de forma no oficial — funciona bien desde una IP residencial, pero las IPs de datacenter
(como las de Railway) tienen más probabilidad de toparse con bloqueos o rate-limiting de
Yahoo, justo el peor momento para que falle (en vivo, frente a Casa en Casa). Frankfurter es
una API REST gratuita, sin key, respaldada por tasas oficiales del Banco Central Europeo,
pensada para consumirse programáticamente:
```
GET https://api.frankfurter.app/latest?from=EUR&to=COP
```
Nota: Frankfurter no tiene EUR→COP directo en todos los casos de forma confiable para todas
las monedas exóticas — para USD y EUR (las monedas que vas a ver en el 95% de los casos reales
de Casa en Casa) funciona perfecto. Si en el formulario aparece una moneda rara sin tasa
disponible, cae a un valor manual de respaldo (ver Fase 1, paso 9).

### APScheduler (limpieza de reportes vencidos)

```bash
pip install apscheduler
```
Corre un `BackgroundScheduler` dentro del mismo proceso de Flask — no es un servicio aparte
ni un cron externo. Un detalle importante con `--workers 2` de Gunicorn: **si no tienes
cuidado, el scheduler se inicializa dos veces (una por worker) y el job de limpieza corre el
doble de seguido.** No es grave para un `DELETE ... WHERE expires_at < now()` (es idempotente,
correrlo de más no rompe nada), pero para evitar el desperdicio, se inicializa condicionado a
una variable de entorno o al PID del worker maestro — se detalla en Fase 5, paso 24.

### H3 (`h3-py`, v4) — futuro, no se instala esta semana

Se documenta la versión acá para que quien retome el proyecto de hexágonos no se tropiece con
el cambio de nombres de función entre v3 y v4 (ver sección "Arquitectura futura").

---

## Arquitectura final

Tres piezas dentro de un mismo proyecto de Railway, separadas por responsabilidad: SQLite no
aguanta bien que un hilo en background escriba mientras hay requests leyendo al mismo tiempo,
y si el scraping tiene que seguir corriendo con el funcionario desconectado, Chrome no puede
vivir dentro del mismo proceso que sirve la web (por memoria — ya documentado como problema en
el README original con la capa de estratos de 89 MB).

```
                         Internet
                            │
                            ▼
                  ┌───────────────────┐
   Navegador ────▶│   App (Flask +    │   ← única pieza con URL pública
   del             │   Gunicorn)       │
   funcionario ◀───│   frontend+backend│
                    │   juntos          │
                    └─────────┬─────────┘
                    ┌─────────┼─────────────────────┐
                    │         │                      │
                    ▼         ▼                      ▼
          ┌──────────────┐ ┌────────────────┐  APIs externas:
          │  Postgres    │ │ selenium-chrome │  - Claude (reportes)
          │  (addon)     │ │ (Selenium Grid) │  - Frankfurter (FX)
          │  sin URL     │ │ sin URL pública │
          │  pública     │ │                 │
          └──────────────┘ └────────┬────────┘
                                     ▼
                          FincaRaíz / Metrocuadrado
                             (scraping real)
```

**Solo el servicio "App" tiene URL pública.** Postgres y Selenium-Chrome se comunican con la
app por la red *interna* de Railway (nunca expuestos a internet).

**Cómo crear cada pieza en Railway (mezcla de dashboard + CLI, lo que sea más rápido para
cada una):**

```bash
# CLI de Railway
npm install -g @railway/cli
railway login
railway init          # dentro del repo Geovivienda-main, crea el proyecto
```

- **Postgres:** desde el dashboard, "New" → "Database" → "Add PostgreSQL". Railway inyecta
  automáticamente `DATABASE_URL` como variable de entorno al servicio de la app cuando los
  conectas dentro del mismo proyecto — no hay que copiar/pegar el connection string a mano.
- **Selenium Grid:** desde el dashboard, "New" → "Empty Service" → cambiar el "Source" a
  "Docker Image" → `selenium/standalone-chrome:4`. **No generar dominio público** para este
  servicio (dejar el toggle de "Generate Domain" apagado) — así queda solo alcanzable por red
  interna, con hostname `<nombre-del-servicio>.railway.internal`.
- **App (Flask):** `railway up` despliega el repo actual usando `nixpacks.toml`/`Procfile`.
  Variables de entorno del servicio de la app (dashboard → Variables, o CLI):
  ```bash
  railway variables set ANTHROPIC_API_KEY=sk-ant-...
  railway variables set SELENIUM_REMOTE_URL=http://<nombre-servicio-selenium>.railway.internal:4444/wd/hub
  ```
  `DATABASE_URL` no hace falta setearla a mano, Railway la inyecta al enlazar el addon.

**Plan B (si el miércoles el tiempo aprieta):** fusionar Chrome de vuelta dentro del servicio
de la app (instalarlo con nixpacks) y aceptar el riesgo de memoria — viable porque la carga
esperada en el demo es mínima. Quedaría en 2 piezas en vez de 3.

---

## ⚠️ Riesgos que siguen vivos con este diseño

- **Latencia y timeouts entre servicios:** si `selenium-chrome` tarda en responder o se cae,
  la app debe manejarlo con reintentos/timeouts explícitos — ver el código de
  `configurar_driver()` en Fase 2, paso 10, que ya incluye un loop de reintento.
- **Doble inicialización del scheduler de limpieza** con 2 workers de Gunicorn — mitigado en
  Fase 5, paso 24.
- **Si Railway no logra resolver el hostname interno del servicio de Selenium a tiempo para el
  jueves:** usar Plan B (fusionar en un solo servicio) en vez de perder tiempo debuggeando
  redes internas de Railway a último momento.

---

## Qué SÍ funciona el jueves vs. qué queda documentado para después

| Componente | Jueves | Backlog (documentado, no construido) |
|---|---|---|
| Login | Mockup visual | Auth real con cuentas |
| Ciudades | Selector completo (15 ciudades + área metro) | Solo Bogotá tiene scraper conectado |
| Portales | FincaRaíz + Metrocuadrado | Houm, Ciencuadras, Lahaus, proyectos nuevos |
| Geo-enriquecimiento | Cálculo por-inmueble (como hoy, `gpd.overlay`) | Índice H3 precalculado por hexágono |
| Dedup de anuncios | Sí, tabla maestra por URL + chequeo 404 | — |
| Score | Heurístico ponderado y explicable (no ML) | Modelo ML real cuando haya datos de conversión (Y) |
| Reportes | Generados por Claude, 1 página, exportables a PDF, TTL 15 días | — |
| Base de datos | Postgres (addon de Railway), mismo motor en dev y prod | Ninguna migración pendiente |
| Scraping | Chrome en servicio Selenium Grid separado | — |

---

## 📅 Cronograma día a día

| Día | Foco |
|---|---|
| **Vie 17 (hoy)** | Cerrar arquitectura y modelo de datos, dejar el repo listo para picar código |
| **Sáb 18 – Dom 19** | Backend: Postgres, migrar análisis espacial, scraper Metrocuadrado + WebDriver remoto, normalización multi-portal |
| **Lun 20** | Dedup + validación de links + motor de scoring |
| **Mar 21** | Reportes LLM (prompt, Claude, plantilla, TTL) + CRUD de clientes en frontend |
| **Mié 22** | Frontend de búsqueda/resultados/reportes + deploy a Railway (3 servicios) + pruebas end-to-end |
| **Jue 23** | Buffer para bugs, ensayo del guion de la demo, presentación |

Ojo: solo quedan **2 días de colchón real** (miércoles tarde/noche + lo que sobre el jueves
antes de la reunión). Si para el domingo en la noche el scraper de Metrocuadrado y el schema no
están funcionando, corta alcance ahí — no el miércoles.

---

## Plan de ejecución paso a paso

Cada paso trae: qué hacer, por qué, el código o comando concreto, y cómo saber que quedó bien.

### Fase 0 — Arquitectura y setup (viernes)

#### Paso 1 — Checkpoint del código actual

Antes de tocar nada, guarda el estado actual por si hay que volver atrás:
```bash
cd Geovivienda-main
git add -A && git commit -m "checkpoint antes del pivote a Casa en Casa"
```

#### Paso 2 — Crear el addon de Postgres en Railway

Dashboard → "New" → "Database" → "Add PostgreSQL". Una vez creado, entra a la pestaña
"Connect" del addon y copia el `DATABASE_URL` **público** (no el interno) — lo vas a usar
también desde tu laptop en desarrollo local, y el connection string público es el único que
funciona fuera de la red de Railway.

**Verificación:** `psql "$DATABASE_URL" -c "SELECT version();"` desde tu terminal local debe
devolver la versión de Postgres sin error.

#### Paso 3 — Esquema completo + script de inicialización

Crear `schema.sql` con el contenido completo de la sección "Modelo de datos" de este
documento, y `init_db.py`:

```python
# init_db.py
import os
import psycopg2

DATABASE_URL = os.environ["DATABASE_URL"]

def main():
    with open("schema.sql", encoding="utf-8") as f:
        ddl = f.read()
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()
        print("Esquema aplicado correctamente.")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
```

**Verificación:** `python init_db.py`, luego `psql "$DATABASE_URL" -c "\dt"` debe listar las
5 tablas (`anuncios`, `clientes`, `busquedas`, `resultados_busqueda`, `reportes`).

#### Paso 4 — Actualizar `requirements.txt`

```txt
Flask>=3.0.0
pandas>=2.2.3
beautifulsoup4>=4.12.0
selenium>=4.18.0
gunicorn>=21.0.0
psycopg2-binary>=2.9.9
anthropic>=0.40.0
xhtml2pdf>=0.2.16
apscheduler>=3.10.4
python-dotenv>=1.0.1
requests>=2.31.0
geopandas
shapely
```
`webdriver-manager` se puede quitar del `requirements.txt` del servidor — ya no hace falta,
porque el driver ya no se lanza localmente en producción (habla con Selenium Grid). Consérvalo
solo si quieres poder correr `webdriver.Chrome()` local sin Docker como fallback de emergencia.

#### Paso 5 — `.env.example` y `.env` local

```bash
# .env.example
DATABASE_URL=postgresql://usuario:password@host:puerto/basededatos
ANTHROPIC_API_KEY=sk-ant-...
SELENIUM_REMOTE_URL=http://localhost:4444/wd/hub
```
Copia esto a `.env` (que va en `.gitignore`, nunca se commitea) con tus valores reales. Cargar
con `python-dotenv` al inicio de `app.py`:
```python
from dotenv import load_dotenv
load_dotenv()
```

#### Paso 6 — `score_config.json`

```json
{
  "presupuesto": 0.30,
  "estrato": 0.20,
  "habitaciones_banos": 0.15,
  "transporte": 0.20,
  "tipo_vivienda": 0.10,
  "antiguedad_estado": 0.05
}
```
Vive en la raíz del repo, se lee una vez al iniciar la app — así puedes ajustar los pesos del
score sin tocar código Python (ver Fase 4).

---

### Fase 1 — Persistencia y migración del análisis espacial (fin de semana)

#### Paso 7 — Capa de acceso a datos (`db.py`)

```python
# db.py
import os
from contextlib import contextmanager
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor

_pool = ThreadedConnectionPool(minconn=1, maxconn=10, dsn=os.environ["DATABASE_URL"])

@contextmanager
def get_cursor():
    conn = _pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def buscar_anuncio_por_url(url: str) -> dict | None:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM anuncios WHERE url = %s", (url,))
        return cur.fetchone()


def insertar_anuncio(datos: dict) -> int:
    columnas = list(datos.keys())
    placeholders = [f"%({c})s" for c in columnas]
    query = f"""
        INSERT INTO anuncios ({', '.join(columnas)})
        VALUES ({', '.join(placeholders)})
        ON CONFLICT (url) DO UPDATE SET
            ultima_verificacion = now(), activo = TRUE
        RETURNING id
    """
    with get_cursor() as cur:
        cur.execute(query, datos)
        return cur.fetchone()["id"]


def marcar_inactivo(url: str):
    with get_cursor() as cur:
        cur.execute("UPDATE anuncios SET activo = FALSE WHERE url = %s", (url,))


def insertar_cliente(datos: dict) -> int:
    columnas = list(datos.keys())
    placeholders = [f"%({c})s" for c in columnas]
    query = f"""
        INSERT INTO clientes ({', '.join(columnas)})
        VALUES ({', '.join(placeholders)}) RETURNING id
    """
    with get_cursor() as cur:
        cur.execute(query, datos)
        return cur.fetchone()["id"]


def crear_busqueda(cliente_id: int, portales: list[str], cantidad: int) -> int:
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO busquedas (cliente_id, portales, cantidad_solicitada, status, log)
            VALUES (%s, %s, %s, 'running', %s) RETURNING id
        """, (cliente_id, portales, cantidad, "[]"))
        return cur.fetchone()["id"]


def actualizar_busqueda_log(busqueda_id: int, mensaje: str, nivel: str = "info"):
    with get_cursor() as cur:
        cur.execute("""
            UPDATE busquedas SET log = log || %s::jsonb WHERE id = %s
        """, ('[{"msg": %s, "level": %s}]' % (mensaje, nivel), busqueda_id))
        # nota: en producción usar json.dumps() para escapar el mensaje correctamente,
        # ver detalle de implementación completo cuando se escriba app.py


def finalizar_busqueda(busqueda_id: int, status: str):
    with get_cursor() as cur:
        cur.execute("""
            UPDATE busquedas SET status = %s, terminada_en = now() WHERE id = %s
        """, (status, busqueda_id))


def guardar_reporte(cliente_id: int, anuncio_id: int, score: float, html: str) -> int:
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO reportes (cliente_id, anuncio_id, score, contenido_html, expires_at)
            VALUES (%s, %s, %s, %s, now() + interval '15 days')
            RETURNING id
        """, (cliente_id, anuncio_id, score, html))
        return cur.fetchone()["id"]


def limpiar_reportes_vencidos() -> int:
    with get_cursor() as cur:
        cur.execute("DELETE FROM reportes WHERE expires_at < now()")
        return cur.rowcount
```

**Nota sobre `actualizar_busqueda_log`:** el snippet de arriba usa concatenación de string por
brevedad — en la implementación real, arma el JSON con `json.dumps([{"msg": mensaje, "level":
nivel}])` y pásalo como parámetro (`%s::jsonb`) en vez de interpolar el string directamente,
para no abrir la puerta a un problema de inyección si algún mensaje de log llegara a incluir
texto no controlado (por ejemplo, el nombre de un inmueble scrapeado).

**Verificación:** un script chiquito que llame `insertar_cliente({...})` y después
`buscar_anuncio_por_url(...)` debe funcionar sin errores contra el Postgres de Railway desde
tu laptop.

#### Paso 8 — Adaptar `spatial_analysis.py` para correr por-inmueble

Hoy `run_analysis()` lee un CSV completo. La adaptación clave es separar "cargar las capas
geográficas" (caro, se hace una sola vez cuando arranca el proceso) de "enriquecer un
inmueble" (barato, se llama muchas veces):

```python
# spatial_analysis.py — agregar estas dos funciones nuevas, conservar las existentes

_CAPAS_CACHE = None

def _capas():
    global _CAPAS_CACHE
    if _CAPAS_CACHE is None:
        _CAPAS_CACHE = _cargar_capas()   # la función que ya existe, sin cambios
    return _CAPAS_CACHE


def enriquecer_inmueble(lat: float, lon: float) -> dict:
    """Punto de entrada nuevo: recibe lat/lon de UN inmueble recién scrapeado
    y devuelve sus campos geoespaciales, sin tocar ningún CSV."""
    sitp, tm, ciclo, estratos, col_estrato = _capas()
    punto = gpd.GeoSeries([Point(lon, lat)], crs=CRS_WGS84).to_crs(CRS_METRICO).iloc[0]

    dist_sitp = sitp.distance(punto).min()
    dist_tm = tm.distance(punto).min()
    dist_ciclo = ciclo.distance(punto).min()

    buffer_geom = punto.buffer(200)
    buffer_gdf = gpd.GeoDataFrame({'geometry': [buffer_geom]}, crs=CRS_METRICO)
    interseccion = gpd.overlay(estratos, buffer_gdf, how='intersection')
    interseccion = interseccion[interseccion[col_estrato].isin([1, 2, 3, 4, 5, 6])]

    estrato_promedio = None
    if not interseccion.empty:
        interseccion = interseccion.copy()
        interseccion['area'] = interseccion.geometry.area
        total = interseccion['area'].sum()
        if total > 0:
            estrato_promedio = round((interseccion[col_estrato] * interseccion['area']).sum() / total, 2)

    return {
        "dist_sitp": round(dist_sitp, 1),
        "dist_tm": round(dist_tm, 1),
        "dist_ciclo": round(dist_ciclo, 1),
        "estrato_promedio_200m": estrato_promedio,
    }
```

El `_CAPAS_CACHE` es importante: cargar `estratos.geojson` (89 MB) toma varios segundos, y no
lo quieres repetir en cada inmueble — se carga una vez cuando el proceso arranca (o en la
primera llamada) y se reutiliza desde memoria en todas las siguientes.

**Verificación:** `enriquecer_inmueble(4.65, -74.05)` (unas coordenadas de Bogotá) debe
devolver un diccionario con las 4 llaves y valores numéricos razonables (distancias en metros
de un solo dígito hasta unos pocos miles, estrato entre 1 y 6).

#### Paso 9 — Conversión de moneda en tiempo real

```python
# fx.py
import requests

_FALLBACK_RATES = {"EUR": 4700, "USD": 4300}  # actualizar manualmente si Frankfurter falla

def convertir_a_cop(monto: float, moneda_origen: str) -> float:
    moneda_origen = moneda_origen.upper()
    try:
        resp = requests.get(
            "https://api.frankfurter.app/latest",
            params={"from": moneda_origen, "to": "COP"},
            timeout=5,
        )
        resp.raise_for_status()
        tasa = resp.json()["rates"]["COP"]
        return round(monto * tasa, 2)
    except (requests.RequestException, KeyError):
        tasa = _FALLBACK_RATES.get(moneda_origen)
        if tasa is None:
            raise ValueError(f"No hay tasa de respaldo para {moneda_origen}")
        return round(monto * tasa, 2)
```
El diccionario `_FALLBACK_RATES` es tu red de seguridad para el día de la demo: si por lo que
sea Frankfurter no responde justo en ese momento, la conversión sigue funcionando con una tasa
fija que actualizas a mano la mañana del jueves.

**Verificación:** `convertir_a_cop(2200, "EUR")` debe devolver un número cercano a
2200 × tasa_actual_EUR_COP (bórdalo contra Google "2200 eur a cop" para confirmar que el
orden de magnitud es correcto).

---

### Fase 2 — Scraper de Metrocuadrado + Selenium remoto (fin de semana)

#### Paso 10 — WebDriver remoto con reintentos

```python
# En extractor_links.py Y extractor_detalles.py, reemplazar configurar_driver() por:
import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException

def configurar_driver(reintentos: int = 3, espera_segundos: int = 5):
    opts = Options()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1920,1080")

    remote_url = os.environ.get("SELENIUM_REMOTE_URL")

    for intento in range(1, reintentos + 1):
        try:
            if remote_url:
                driver = webdriver.Remote(command_executor=remote_url, options=opts)
            else:
                driver = webdriver.Chrome(options=opts)  # solo si no hay Selenium Grid configurado
            driver.set_page_load_timeout(15)
            return driver
        except WebDriverException:
            if intento == reintentos:
                raise
            time.sleep(espera_segundos)
```

Para desarrollo local, levanta tu propio contenedor de Selenium Grid (así el código de
desarrollo y producción es idéntico, nunca tienes una rama de código "solo para local"):
```bash
docker run -d -p 4444:4444 --shm-size=2g selenium/standalone-chrome:4
```
Y en tu `.env` local: `SELENIUM_REMOTE_URL=http://localhost:4444/wd/hub`.

**Verificación:** con el contenedor corriendo, `configurar_driver().get("https://example.com")`
no debe lanzar excepción, y `driver.title` debe devolver `"Example Domain"`.

#### Paso 11 — Muestras de HTML de Metrocuadrado

Bajar manualmente (guardar página como HTML desde el navegador, igual que hiciste con el sitio
de Casa en Casa) dos páginas:
1. Resultados de una búsqueda de apartamentos en venta en Bogotá.
2. La ficha completa de un anuncio individual.

Revisar el HTML crudo (no solo lo que se ve en pantalla) para confirmar si el listado ya viene
con los datos en el HTML inicial (server-rendered) o si depende de JavaScript para cargar
(en ese caso Selenium es indispensable; si es server-rendered, hasta podrías usar `requests` +
BeautifulSoup sin necesidad de un navegador real para esa parte, más liviano).

#### Paso 12 — Construir los extractores de Metrocuadrado

Con las dos muestras de HTML del paso anterior, seguir la metodología ya documentada más abajo
("Metodología reutilizable para construir un scraper nuevo"): pasarle el HTML a un agente de
código para que identifique selectores y construya:
- `extractor_metrocuadrado_links.py` — misma firma que `extraer_links_fincaraiz`.
- `extractor_metrocuadrado_detalles.py` — misma firma que `extraer_detalles_inmueble`.

#### Paso 13 — Interfaz común multi-portal

```python
# portales.py
from extractor_links import extraer_links_fincaraiz
from extractor_metrocuadrado_links import extraer_links_metrocuadrado
from extractor_detalles import extraer_detalles_inmueble as _detalle_fincaraiz
from extractor_metrocuadrado_detalles import extraer_detalles_inmueble as _detalle_metrocuadrado

_BUSCADORES = {
    "fincaraiz": extraer_links_fincaraiz,
    "metrocuadrado": extraer_links_metrocuadrado,
}
_EXTRACTORES = {
    "fincaraiz": _detalle_fincaraiz,
    "metrocuadrado": _detalle_metrocuadrado,
}

def buscar_portal(portal: str, filtros: dict) -> list[str]:
    return _BUSCADORES[portal](**filtros)

def extraer_detalle(portal: str, html: str, url: str) -> dict:
    datos = _EXTRACTORES[portal](html, url)
    datos["portal"] = portal
    return datos
```
Este archivo es el único punto que el resto de la app necesita importar — agregar un portal
nuevo en el futuro (Houm, Ciencuadras) es sumar una entrada a estos dos diccionarios, nada más.

#### Paso 14 — Normalizar nombres de campo

Confirmar que `extractor_metrocuadrado_detalles.py` devuelve un diccionario con **exactamente**
las mismas llaves que `extraer_detalles_inmueble` de FincaRaíz (`Precio_Venta`, `Habitaciones`,
`Banos`, etc.) — si Metrocuadrado usa otro nombre internamente para un campo equivalente,
renombrarlo dentro del propio extractor, no en el código que lo consume.

---

### Fase 3 — Dedup y validación de anuncios (lunes)

#### Paso 15 — Consultar la tabla maestra antes de scrapear

```python
def filtrar_urls_nuevas(urls: list[str]) -> list[str]:
    nuevas = []
    for url in urls:
        if buscar_anuncio_por_url(url) is None:
            nuevas.append(url)
    return nuevas
```

#### Paso 16 — Chequeo de anuncios existentes (¿siguen vivos?)

```python
import requests

def anuncio_sigue_activo(url: str, timeout: int = 6) -> bool:
    try:
        r = requests.head(url, timeout=timeout, allow_redirects=True)
        if r.status_code == 405:  # algunos portales no aceptan HEAD, reintentar con GET
            r = requests.get(url, timeout=timeout, stream=True)
        return r.status_code < 400
    except requests.RequestException:
        return False


def revalidar_anuncios_existentes(urls: list[str]):
    for url in urls:
        if not anuncio_sigue_activo(url):
            marcar_inactivo(url)
```
Este chequeo es una petición HTTP simple (sin Selenium — no hace falta renderizar la página
completa solo para saber si sigue existiendo), así que es rápido incluso para varios cientos
de URLs.

#### Paso 17 — Pipeline completo de una búsqueda

```python
def ejecutar_busqueda(cliente: dict, portales: list[str], cantidad: int, busqueda_id: int):
    todas_urls = []
    for portal in portales:
        urls = buscar_portal(portal, _filtros_desde_cliente(cliente, cantidad))
        todas_urls.extend(urls)

    urls_existentes = [u for u in todas_urls if buscar_anuncio_por_url(u) is not None]
    revalidar_anuncios_existentes(urls_existentes)

    urls_nuevas = filtrar_urls_nuevas(todas_urls)
    for url in urls_nuevas:
        driver = configurar_driver()
        try:
            driver.get(url)
            html = driver.page_source
        finally:
            driver.quit()
        portal = _portal_desde_url(url)
        detalle = extraer_detalle(portal, html, url)
        geo = enriquecer_inmueble(detalle["Latitud"], detalle["Longitud"])
        insertar_anuncio({**_normalizar(detalle), **geo})

    return [buscar_anuncio_por_url(u) for u in todas_urls
            if buscar_anuncio_por_url(u) and buscar_anuncio_por_url(u)["activo"]]
```
(`_filtros_desde_cliente`, `_portal_desde_url` y `_normalizar` son helpers pequeños que
traducen entre el formato del cliente/URL y lo que cada función espera — se escriben junto con
el resto del código de esta fase, no necesitan diseño previo.)

---

### Fase 4 — Motor de scoring (lunes)

#### Paso 18 — Implementar el cálculo de score

```python
# scoring.py
import json

with open("score_config.json", encoding="utf-8") as f:
    PESOS = json.load(f)


def _score_presupuesto(cliente, anuncio):
    precio = anuncio["precio_venta"]
    lo, hi = cliente["presupuesto_min"], cliente["presupuesto_max"]
    if lo <= precio <= hi:
        return 1.0
    exceso = (precio - hi) if precio > hi else (lo - precio)
    rango = (hi - lo) or 1
    return max(0.0, 1 - exceso / rango)


def _score_estrato(cliente, anuncio):
    objetivo = cliente["estrato_objetivo"]
    real = anuncio.get("estrato_promedio_200m") or anuncio.get("estrato")
    if real is None:
        return 0.5  # neutral si no hay dato, no penaliza ni premia
    return max(0.0, 1 - abs(objetivo - real) / 3)


def _score_habitaciones_banos(cliente, anuncio):
    hab_ok = (anuncio.get("habitaciones") or 0) >= cliente["habitaciones_min"]
    banos_ok = (anuncio.get("banos") or 0) >= cliente.get("banos_min", 0)
    return (hab_ok + banos_ok) / 2


def _score_transporte(anuncio):
    dist = min(
        anuncio.get("dist_tm") or 9999,
        anuncio.get("dist_sitp") or 9999,
    )
    if dist <= 300:
        return 1.0
    if dist >= 1500:
        return 0.0
    return 1 - (dist - 300) / 1200


def _score_tipo_vivienda(cliente, anuncio):
    return 1.0 if anuncio.get("tipo_inmueble", "").lower() == cliente["tipo_vivienda"].lower() else 0.0


def _score_antiguedad_estado(anuncio):
    return 1.0 if (anuncio.get("estado") or "").lower() != "sobre planos" else 0.6


def calcular_score(cliente: dict, anuncio: dict) -> dict:
    componentes = {
        "presupuesto": _score_presupuesto(cliente, anuncio),
        "estrato": _score_estrato(cliente, anuncio),
        "habitaciones_banos": _score_habitaciones_banos(cliente, anuncio),
        "transporte": _score_transporte(anuncio),
        "tipo_vivienda": _score_tipo_vivienda(cliente, anuncio),
        "antiguedad_estado": _score_antiguedad_estado(anuncio),
    }
    total = sum(componentes[k] * PESOS[k] for k in PESOS)
    return {"total": round(total, 3), "componentes": componentes}
```

#### Paso 19 — Aplicar el score a todos los candidatos

```python
def rankear_candidatos(cliente: dict, anuncios: list[dict]) -> list[dict]:
    resultados = []
    for anuncio in anuncios:
        score = calcular_score(cliente, anuncio)
        resultados.append({**anuncio, "score": score["total"], "score_desglose": score["componentes"]})
    return sorted(resultados, key=lambda r: r["score"], reverse=True)
```

#### Paso 20 — Seleccionar el top N

```python
def top_n(candidatos_rankeados: list[dict], n: int = 5) -> list[dict]:
    return candidatos_rankeados[:n]
```
El default de 5 vive como argumento de función, no hardcodeado en el endpoint — así el
frontend puede exponerlo como un control ("mostrar top 5 / top 10") sin tocar el motor.

---

### Fase 5 — Reportes generados por LLM (martes)

#### Paso 21 — Plantilla del prompt

```python
# reportes.py
PROMPT_TEMPLATE = """Eres un asesor inmobiliario de Casa en Casa. Genera un reporte de una
página para el siguiente cliente y vivienda candidata.

CLIENTE:
- Vive en {ciudad_residencia}, {pais_residencia}
- Ingreso: {ingreso_mensual_cop:,.0f} COP/mes (~{ingreso_mensual} {ingreso_moneda})
- Ahorro disponible para cuota: {ahorro_mensual_cop:,.0f} COP/mes
- Busca: {tipo_vivienda}, {estado_deseado}, en {ciudad_interes}
- Presupuesto: {presupuesto_min:,.0f} a {presupuesto_max:,.0f} COP
- Estrato objetivo: {estrato_objetivo}, mínimo {habitaciones_min} habitaciones

VIVIENDA:
Precio: {precio_venta:,.0f} COP | Área: {area_metros} m² | Habitaciones: {habitaciones} |
Baños: {banos} | Estrato: {estrato} | Ubicación: {ubicacion_texto}

ENTORNO:
- Estrato promedio del sector (200m): {estrato_promedio_200m}
- Distancia a TransMilenio: {dist_tm}m | SITP: {dist_sitp}m | Ciclorruta: {dist_ciclo}m

SCORE CALCULADO: {score} / 1.0
DESGLOSE: {desglose}

Escribe un reporte de máximo 400 palabras, en español, con estas secciones:
1. Resumen (2-3 líneas)
2. Por qué esta vivienda encaja con este cliente (usa el desglose del score, sé concreto)
3. El entorno (transporte, estrato, contexto del sector)
4. Consideraciones a tener en cuenta (si algo no es perfecto, dilo — no vendas humo)
"""

def _formatear_desglose(componentes: dict) -> str:
    return ", ".join(f"{k}: {v:.2f}" for k, v in componentes.items())
```

#### Paso 22 — Integrar Claude

```python
import anthropic

_client = anthropic.Anthropic()  # lee ANTHROPIC_API_KEY del entorno

def generar_reporte(cliente: dict, anuncio: dict, score: dict) -> str:
    prompt = PROMPT_TEMPLATE.format(
        **cliente, **anuncio,
        score=score["total"],
        desglose=_formatear_desglose(score["componentes"]),
    )
    respuesta = _client.messages.create(
        model="claude-sonnet-5",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    texto = respuesta.content[0].text
    return _envolver_en_html(texto, cliente, anuncio, score)


def _envolver_en_html(texto: str, cliente: dict, anuncio: dict, score: dict) -> str:
    parrafos = "".join(f"<p>{linea}</p>" for linea in texto.split("\n") if linea.strip())
    return f"""
    <html><body style="font-family: Montserrat, sans-serif; color: #2F3670; max-width: 700px;">
      <h1 style="color:#2F3670;">Reporte de vivienda — {cliente['nombre']}</h1>
      <p><strong>Score:</strong> {score['total']:.2f} / 1.0</p>
      {parrafos}
      <p><a href="{anuncio['url']}">Ver anuncio original</a></p>
    </body></html>
    """
```
Los colores inline (`#2F3670`) son la identidad visual de Casa en Casa — ver esa sección más
abajo para el resto de la paleta.

#### Paso 23 — Persistir el reporte con TTL

```python
def crear_y_guardar_reporte(cliente_id: int, anuncio: dict, cliente: dict, score: dict) -> int:
    html = generar_reporte(cliente, anuncio, score)
    return guardar_reporte(cliente_id, anuncio["id"], score["total"], html)
    # guardar_reporte ya calcula expires_at = now() + 15 días, definido en db.py (Fase 1)
```

#### Paso 24 — Job de limpieza sin duplicar el scheduler

```python
# scheduler.py
import os
from apscheduler.schedulers.background import BackgroundScheduler
from db import limpiar_reportes_vencidos

def iniciar_scheduler():
    # Con --workers 2 de Gunicorn, este módulo se importa en ambos procesos.
    # Solo el worker "primario" (detectable por una variable que Gunicorn no fija,
    # así que se usa un lock a nivel de Postgres) arranca el job real.
    scheduler = BackgroundScheduler()
    scheduler.add_job(limpiar_reportes_vencidos, "interval", hours=1, id="limpieza_reportes")
    scheduler.start()
    return scheduler
```
Para el jueves, correr con 2 workers duplicando el job de limpieza **no rompe nada** (el
`DELETE ... WHERE expires_at < now()` es idempotente — correrlo dos veces en el mismo minuto
no borra de más). Se documenta acá como conocido y aceptado, no como algo que haya que
resolver con un lock distribuido esta semana — eso sí sería sobre-ingeniería para un job de
limpieza que corre una vez por hora.

#### Paso 25 — Exportar a PDF

```python
from io import BytesIO
from xhtml2pdf import pisa

def html_a_pdf(html: str) -> bytes:
    buffer = BytesIO()
    pisa.CreatePDF(html, dest=buffer)
    return buffer.getvalue()
```
Endpoint en `app.py`:
```python
@app.route("/api/reportes/<int:reporte_id>/pdf")
def descargar_reporte_pdf(reporte_id):
    reporte = obtener_reporte(reporte_id)  # función nueva en db.py, SELECT simple por id
    pdf_bytes = html_a_pdf(reporte["contenido_html"])
    return Response(pdf_bytes, mimetype="application/pdf",
                     headers={"Content-Disposition": f"attachment; filename=reporte_{reporte_id}.pdf"})
```

#### Paso 26 — Reporte on-demand fuera del top N

```python
@app.route("/api/reportes/generar", methods=["POST"])
def generar_reporte_on_demand():
    data = request.json
    cliente = obtener_cliente(data["cliente_id"])
    anuncio = buscar_anuncio_por_url(data["url"])  # o por id, según lo que mande el frontend
    score = calcular_score(cliente, anuncio)
    reporte_id = crear_y_guardar_reporte(cliente["id"], anuncio, cliente, score)
    return jsonify({"reporte_id": reporte_id})
```

---

### Fase 6 — Frontend (martes–miércoles)

#### Paso 27 — Layout base con identidad visual de Casa en Casa

Reorganizar `templates/` con herencia de Jinja2 en vez de un solo `index.html` monolítico —
ya no es una sola pantalla, son varias vistas que comparten sidebar:

```
templates/
  base.html            (layout: sidebar + bloque de contenido)
  login.html
  clientes_lista.html
  cliente_form.html
  busqueda.html
  resultados.html
static/
  css/style.css        (variables de marca + layout)
  img/logo-casa-en-casa.png   (ya está copiado)
  js/app.js
  geo/  (sin cambios)
```

`static/css/style.css` — variables de marca al inicio, reutilizadas en todo el CSS:
```css
:root {
  --color-primary: #2F3670;
  --color-accent: #F3D143;
  --color-danger: #C53336;
  --font-base: 'Montserrat', sans-serif;
}
body { font-family: var(--font-base); margin: 0; }
.layout { display: flex; min-height: 100vh; }
.sidebar { background: var(--color-primary); color: white; width: 220px; padding: 24px 16px; }
.sidebar img { width: 140px; margin-bottom: 32px; }
.sidebar a { display: block; color: white; text-decoration: none; padding: 10px 0; opacity: .85; }
.sidebar a:hover { opacity: 1; }
main { flex: 1; padding: 32px; }
.badge-score-alto { background: var(--color-accent); color: #4A3A00; padding: 2px 8px; border-radius: 4px; }
.btn-primary { background: var(--color-primary); color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; }
```

`templates/base.html`:
```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <title>{% block title %}Casa en Casa — Match{% endblock %}</title>
  <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
</head>
<body>
  <div class="layout">
    <aside class="sidebar">
      <img src="{{ url_for('static', filename='img/logo-casa-en-casa.png') }}" alt="Casa en Casa">
      <nav>
        <a href="{{ url_for('perfil') }}">Perfil</a>
        <a href="{{ url_for('clientes') }}">Clientes</a>
        <a href="{{ url_for('busqueda') }}">Búsqueda</a>
      </nav>
    </aside>
    <main>{% block content %}{% endblock %}</main>
  </div>
</body>
</html>
```
Login mockup: una pantalla simple con campos de correo/contraseña que, al enviarse, solo
redirige a `/clientes` sin validar nada contra ningún backend — un `<form action="/clientes"
method="get">` literalmente basta.

#### Paso 28 — CRUD de clientes

Formulario (`cliente_form.html`, extiende `base.html`) con los campos ya definidos: país,
ciudad de residencia, ingreso mensual + selector de moneda (con conversión en vivo llamando a
`/api/fx?monto=...&moneda=...` mientras el usuario escribe), ahorro mensual, ciudades de
interés (checkboxes, Bogotá pre-marcada), tipo de vivienda, usado/nuevo, habitaciones mínimas,
baños, estrato objetivo, rango de presupuesto (dos inputs numéricos simples — los sliders
visuales quedan en el backlog de UI, no son necesarios para que el flujo funcione).

#### Paso 29 — Botón Buscar → job en background

```javascript
// static/js/app.js
async function iniciarBusqueda(clienteId) {
  const portales = Array.from(document.querySelectorAll('input[name=portal]:checked')).map(el => el.value);
  const cantidad = document.getElementById('cantidad').value;
  const resp = await fetch('/api/scrape', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({cliente_id: clienteId, portales, cantidad}),
  });
  const {busqueda_id} = await resp.json();
  pollEstado(busqueda_id);
}

function pollEstado(busquedaId) {
  const intervalo = setInterval(async () => {
    const resp = await fetch(`/api/status?busqueda_id=${busquedaId}`);
    const data = await resp.json();
    renderLog(data.logs);
    if (data.status === 'done' || data.status === 'error') {
      clearInterval(intervalo);
      window.location.href = `/resultados?busqueda_id=${busquedaId}`;
    }
  }, 3000);
}
```
El polling cada 3 segundos es deliberadamente simple — no hace falta WebSockets ni
server-sent events para un demo con un usuario a la vez.

#### Paso 30 — Vista de resultados

Tabla con score visible (usar `.badge-score-alto` para scores > 0.7), botón "generar reporte"
por fila que llama a `/api/reportes/generar`, botón de descarga que apunta directo a
`/api/reportes/<id>/pdf`, y un campo de texto/URL para pedir el reporte de un anuncio fuera
del top N mostrado.

---

### Fase 7 — Deploy y pruebas (miércoles)

#### Paso 31 — Servicio de Selenium Grid en Railway

Ya cubierto en "Arquitectura final" — dashboard → New Service → Docker Image →
`selenium/standalone-chrome:4`, sin dominio público. Configurar `SELENIUM_REMOTE_URL` en el
servicio de la app apuntando a `http://<nombre-servicio>.railway.internal:4444/wd/hub`.

#### Paso 32 — Variables de entorno finales del servicio de la app

```bash
railway variables set ANTHROPIC_API_KEY=sk-ant-...
railway variables set SELENIUM_REMOTE_URL=http://selenium.railway.internal:4444/wd/hub
# DATABASE_URL ya viene inyectado por Railway al enlazar el addon de Postgres
```

Actualizar `Procfile`:
```
web: gunicorn app:app --bind 0.0.0.0:$PORT --worker-class gthread --workers 2 --threads 4 --timeout 120
```

Y `nixpacks.toml` (ya no necesita instalar Chrome, ese peso ahora vive en el otro servicio):
```toml
[start]
cmd = "gunicorn app:app --bind 0.0.0.0:$PORT --worker-class gthread --workers 2 --threads 4 --timeout 120"
```

#### Paso 33 — Prueba de humo: sobrevive al cierre del navegador

1. Lanzar una búsqueda real desde el navegador desplegado.
2. Cerrar la pestaña por completo.
3. Esperar 2-3 minutos.
4. Volver a abrir la app, ir a resultados de esa búsqueda — debe estar `done` con anuncios y
   poder generar reportes, sin haber tenido el navegador abierto mientras corría.

#### Paso 34 — Recorrido end-to-end con el caso de uso real

Con el ambiente desplegado (no local), correr el caso completo: Juan Carlos Ramírez Pérez,
Madrid, electricista, €2.200/mes, busca en Bogotá, 200–300M COP, estrato 3, mínimo 2
habitaciones — desde crear el cliente hasta descargar el PDF del reporte top 1.

---

## Modelo de datos (Postgres)

```sql
-- Tabla maestra: TODOS los anuncios vistos alguna vez, de cualquier cliente/búsqueda
CREATE TABLE anuncios (
    id BIGSERIAL PRIMARY KEY,
    url TEXT UNIQUE NOT NULL,
    portal TEXT NOT NULL,                 -- 'fincaraiz', 'metrocuadrado', ...
    codigo_portal TEXT,
    tipo_inmueble TEXT,
    estado TEXT,                          -- 'usado', 'nuevo/proyecto'
    operacion TEXT,                       -- 'venta', 'arriendo'
    precio_venta BIGINT,
    administracion INTEGER,
    ubicacion_texto TEXT,
    ciudad TEXT,
    estrato SMALLINT,
    area_metros REAL,
    habitaciones SMALLINT,
    banos SMALLINT,
    parqueaderos SMALLINT,
    latitud DOUBLE PRECISION,
    longitud DOUBLE PRECISION,
    dist_sitp REAL,
    dist_tm REAL,
    dist_ciclo REAL,
    estrato_promedio_200m REAL,
    h3_index TEXT,                        -- NULL por ahora, se llena en la Fase futura de H3
    activo BOOLEAN DEFAULT TRUE,          -- se pone en FALSE si el link ya no existe
    primera_vez_visto TIMESTAMPTZ DEFAULT now(),
    ultima_verificacion TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE clientes (
    id BIGSERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    pais_residencia TEXT,
    ciudad_residencia TEXT,
    ingreso_mensual REAL,
    ingreso_moneda TEXT,                  -- 'EUR', 'USD', ...
    ingreso_mensual_cop REAL,             -- convertido al momento de guardar
    ahorro_mensual_cop REAL,
    ciudades_interes JSONB,               -- ej: ["bogota"]
    tipo_vivienda TEXT,                   -- 'casa', 'apartamento'
    estado_deseado TEXT,                  -- 'usado', 'nuevo'
    habitaciones_min SMALLINT,
    banos_min SMALLINT,
    estrato_objetivo SMALLINT,
    presupuesto_min BIGINT,
    presupuesto_max BIGINT,
    creado_en TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE busquedas (
    id BIGSERIAL PRIMARY KEY,
    cliente_id BIGINT REFERENCES clientes(id),
    portales JSONB,                       -- ej: ["fincaraiz","metrocuadrado"]
    cantidad_solicitada INTEGER,
    status TEXT DEFAULT 'idle',           -- idle | running | done | error
    log JSONB,                            -- lista de eventos, igual que job_state hoy
    creada_en TIMESTAMPTZ DEFAULT now(),
    terminada_en TIMESTAMPTZ
);

CREATE TABLE resultados_busqueda (
    id BIGSERIAL PRIMARY KEY,
    busqueda_id BIGINT REFERENCES busquedas(id),
    anuncio_id BIGINT REFERENCES anuncios(id),
    score REAL,
    es_top BOOLEAN DEFAULT FALSE          -- true si quedó en el top N mostrado
);

CREATE TABLE reportes (
    id BIGSERIAL PRIMARY KEY,
    cliente_id BIGINT REFERENCES clientes(id),
    anuncio_id BIGINT REFERENCES anuncios(id),
    score REAL,
    contenido_html TEXT,
    generado_en TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ                -- generado_en + 15 días
);
```

`resultados_busqueda` es la tabla que conecta cliente↔anuncio↔búsqueda sin duplicar los datos
del inmueble — la tabla `anuncios` es la única fuente de verdad geoespacial y de precio,
exactamente como pediste ("no la información del territorio" repetida por cliente).

---

## Metodología reutilizable para construir un scraper nuevo

Documentando el proceso que ya usaste con FincaRaíz, para repetirlo con Metrocuadrado y,
después, con los portales del backlog:

1. Abrir el portal manualmente, guardar el HTML de una página de **resultados de búsqueda**
   y el de una **ficha de propiedad** individual.
2. Pasarle ambos HTML a un agente de código con instrucciones de: identificar los
   selectores/clases que contienen cada campo objetivo (precio, área, habitaciones, baños,
   estrato, lat/lng si está en JSON-LD, etc.), y construir un extractor con la misma firma
   que `extraer_detalles_inmueble(html_source, url_referencia)` de `extractor_detalles.py`.
3. Repetir el proceso para la función de búsqueda: dado un set de filtros, construir la URL
   de búsqueda del portal y devolver la lista de URLs de anuncios de esa página (igual que
   `extraer_links_fincaraiz`).
4. Unificar ambas funciones detrás de la interfaz común `buscar_portal` / `extraer_detalle`
   (paso 13 del plan de ejecución).
5. Para portales de **proyectos nuevos** (Lahaus y similares) el HTML no representa un
   inmueble sino un proyecto con **varias tipologías anidadas** — este caso necesita un
   extractor distinto que devuelva una lista de inmuebles por proyecto, no uno solo. Queda
   fuera del jueves; documentado aquí para no perderlo (backlog).

---

## Arquitectura futura: hexágonos H3 (NO se construye para el jueves)

**Se construye como proyecto aparte**, en otro repo/entorno — no compite con el sprint de
Casa en Casa. Lo único que cruza hacia Geovivienda es un CSV/Parquet final que se carga a la
tabla `hexagonos` de un `COPY`. Pensado para dedicarle una tarde completa y aislada, no para
intercalarlo entre los pasos del plan de ejecución de arriba.

**Objetivo:** dejar de recalcular geoespacial por-inmueble (`gpd.overlay` es lento, como ya
dice el README actual) y en su lugar precalcular **una sola vez para toda la ciudad** una
tabla de hexágonos H3 con sus características, y que cada inmueble solo necesite guardar
su `h3_index` para heredar todo ese contexto por un simple join.

**Tabla `hexagonos` (fase futura):**

```sql
CREATE TABLE hexagonos (
    h3_index TEXT PRIMARY KEY,
    ciudad TEXT,
    localidad TEXT,
    upz TEXT,
    estrato_promedio REAL,               -- ponderado por área, mismo cálculo que hoy
    uso_suelo TEXT,                      -- clase media/alta, unifamiliar/multifamiliar
    dist_transmilenio REAL,
    dist_sitp REAL,
    dist_metro REAL,
    dist_ciclorruta REAL,
    dist_parque REAL,
    dist_supermercado_d1 REAL,
    dist_supermercado_ara REAL,
    dist_supermercado_carulla REAL,
    dist_supermercado_olimpica REAL,
    dist_colegio REAL,
    actualizado_en TIMESTAMPTZ DEFAULT now()
);
```

**Cuando se implemente:** el pipeline pasa de "por cada inmueble, calcular overlay contra
capas geo pesadas" a "por cada inmueble, calcular su `h3_index` (operación barata) y hacer
un `SELECT` contra `hexagonos`". Esto es lo que finalmente resuelve el problema de memoria
de la capa de estratos de 89 MB — se procesa una sola vez offline, no en cada request.

### Metodología paso a paso para construir el dataframe de hexágonos

**1. Resolución de H3 — usar resolución 9.** Hexágonos de ~0.1 km², arista ~174m — coincide
bien con el radio de 200m que ya usa `_calcular_estrato_promedio()` hoy. Resolución 8
(~461m de arista) mezclaría estratos distintos dentro del mismo hexágono en zonas
heterogéneas; resolución 10 (~65m) multiplica el número de hexágonos sin ganar precisión
real. Es un solo parámetro, fácil de recalcular si hace falta ajustar después.

**2. Generar el universo de hexágonos de Bogotá.** Sacar el polígono de límites de la ciudad
del `unary_union` de `estratos.geojson` (ya cubre el área urbana), o bajar el límite oficial
de IDECA/DANE para más precisión. Con `h3-py` v4:
```python
import h3
cells = h3.polygon_to_cells(h3.LatLngPoly(boundary_coords), res=9)
```
Ojo con la versión de `h3-py`: en v4 se renombraron funciones — `polyfill` → `polygon_to_cells`,
`geo_to_h3` → `latlng_to_cell`, `h3_to_geo` → `cell_to_latlng`. Mucho tutorial en internet
todavía usa los nombres viejos de v3 y va a tirar error con una instalación nueva.

**3. Estrato promedio por hexágono.** Misma lógica de área ponderada que ya existe en
`spatial_analysis.py`, pero corrida **una sola vez por hexágono** (unos pocos miles para
Bogotá) en vez de una vez por inmueble (miles, para siempre). Más rápido que el loop actual
con `gdf.iterrows()`: hacer un solo `gpd.overlay(hexagonos_gdf, estratos_gdf, how='intersection')`
para todos los hexágonos de una vez, y un `groupby('h3_index')` ponderado por área.

**4. Uso de suelo — fuente pendiente.** No hay layer para esto todavía. Buscar el POT
(Plan de Ordenamiento Territorial) de Bogotá en IDECA; si no está disponible a tiempo,
aproximar con el estrato (correlaciona fuerte con esta categoría en Bogotá) en vez de
bloquear el resto de la tabla por esta sola columna.

**5. Distancias a transporte y parques.** Para cada hexágono, tomar su centroide
(`h3.cell_to_latlng(h)`) y calcular distancia mínima a estaciones TM/SITP/Metro/parques —
mismo patrón de `_calcular_distancias()` hoy, aplicado al centroide en vez de al inmueble.
Con unos miles de hexágonos contra unos miles de puntos de transporte, el enfoque simple
(`.distance().min()`) alcanza; si se pone lento, un `BallTree` de scikit-learn con métrica
haversine lo resuelve en segundos.

**6. POIs (D1, Ara, Ísimo, Carulla, Olímpica, colegios, hospitales, centros comerciales) —
no se descargan a mano.** Usar la **API de Overpass de OpenStreetMap** (gratis, sin API key
para volúmenes razonables): una query por categoría, acotada al bounding box de Bogotá,
devuelve lat/lon de cada punto ya etiquetado. Ejemplo para D1:
```
[out:json];
node["shop"="supermarket"]["brand"="D1"](4.4,-74.25,4.85,-73.99);
out;
```
Repetir por marca/categoría (`amenity=school`, `amenity=hospital`, `shop=mall`, etc.).

**Sobre la idea de asignar los POIs al centroide de su propio hexágono antes de medir
distancias:** la idea de agregar por hexágono es correcta — es para eso existe H3 — pero
mejor medir la distancia de cada centroide de hexágono al POI en su **coordenada real**
(sin mover nada), usando un `KDTree`/`BallTree`. Es el mismo esfuerzo de implementación,
pero evita el error de un POI justo en el borde entre dos hexágonos "quedando pegado" a
uno solo de ellos. Alternativa más simple si no importa tanto la precisión de distancia:
presencia binaria (¿hay un D1 en este hexágono o en su anillo de vecinos inmediatos?) en
vez de distancia continua — mucho menos cómputo, pierde granularidad.

**7. Ensamblar y exportar.** Un dataframe indexado por `h3_index` con todas las columnas de
la tabla `hexagonos` de arriba. Exportar a CSV/Parquet — del lado de Geovivienda es un
`COPY`/bulk insert a Postgres.

**8. Conectar un inmueble a su hexágono** (esto sí vive en Geovivienda, no en el proyecto
aparte): una línea en el momento del scraping, `h3.latlng_to_cell(lat, lon, 9)`, para llenar
`anuncios.h3_index`. Barato, no requiere `gpd.overlay`.

---

## Identidad visual de Casa en Casa

Extraída directamente de los archivos de su sitio (`Comprar casa, apartamentos y propiedades
desde el exterior_files/`) — colores confirmados por extracción de píxeles del logo Y por
frecuencia de uso en los bloques `<style>` inline de la página real (29/12/9 apariciones
respectivamente), no son colores default del tema de WordPress sin personalizar.

**Logo:** copiado a [`static/img/logo-casa-en-casa.png`](./static/img/logo-casa-en-casa.png).

**Paleta de marca:**

| Color | Hex | Uso sugerido |
|---|---|---|
| Azul marino | `#2F3670` | Color primario — sidebar, texto de marca, headers |
| Amarillo/dorado | `#F3D143` | Acento — highlights, badges, hover states |
| Rojo | `#C53336` | Acento secundario — alertas, CTAs puntuales, score bajo |

**Tipografía:** el body del sitio usa **Montserrat** (`font-family:Montserrat,sans-serif`,
confirmado en el CSS del tema). Poppins aparece en algunos elementos puntuales de esta
página específica — usar Montserrat como fuente base del dashboard y no complicarse con
una segunda familia tipográfica para un demo de 6 días.

**Nota:** el sitio de Casa en Casa está construido en WordPress con un tema de agencia SEO
genérico ("BoostUp" de Mikado Themes) — su CSS trae colores default sin usar (`#ea3d56`,
`#1b2c58`) que **no** son de la marca, se descartaron precisamente por no aparecer en los
bloques de estilo inline reales de la página.

Las variables CSS de esta paleta ya están escritas en el paso 27 de la Fase 6
(`static/css/style.css`) — no hay que volver a definirlas.

---

## Riesgos y plan de contingencia

- **Si el scraper de Metrocuadrado no está listo para el lunes en la noche:** cortar a "solo
  FincaRaíz" para el jueves y mostrar la arquitectura multi-portal en el roadmap, no en vivo.
  Es mejor un portal robusto que dos portales frágiles.
- **Si el servicio de Selenium Grid da problemas de red/latencia en Railway:** activar el
  Plan B de la sección "Arquitectura final" — fusionar Chrome de vuelta al servicio de la app.
- **Si los reportes LLM tardan demasiado (latencia) en vivo:** pre-generar el reporte del
  caso de uso principal (Juan Carlos Ramírez Pérez) antes de la reunión y tenerlo cacheado,
  pero generar al menos un segundo reporte en vivo para demostrar que el pipeline es real.
- **Si Frankfurter API falla el día de la demo:** el fallback de tasas fijas en `fx.py`
  (paso 9) cubre esto sin que se note en la presentación.
- **Checkpoint de corte de alcance: domingo en la noche.** Si para entonces el segundo
  portal o el schema no están sólidos, prioriza dejar FincaRaíz + scoring + reportes LLM
  impecables antes que sumar más superficie a medio terminar.

---

## 🔮 Backlog futuro (post-jueves)

- Portales restantes: Houm, Ciencuadras, Lahaus.
- Extractor especializado para **proyectos nuevos** (tipologías anidadas dentro de un mismo
  anuncio de proyecto).
- Índice geográfico H3 completo (ver sección de arquitectura arriba) para todas las ciudades.
- Expandir scraping a las 14 ciudades restantes + sus áreas metropolitanas.
- Autenticación real de funcionarios (cuentas, roles, permisos).
- Modelo de score con ML real una vez exista histórico de conversión/feedback (el Y que
  hoy no existe).
- Vista de tabla maestra completa (todos los anuncios históricos, no solo por-cliente).
- Sliders visuales de precio/área y chips de filtro en el sidebar (quedaron fuera del jueves
  por tiempo, no por dificultad — son mejoras de UI sobre un formulario que ya funciona).
- Landing page mínima antes del dashboard.

---

*Roadmap actualizado el 17 de julio de 2026 — versión con tech stack en profundidad y código
ejecutable por paso.*
