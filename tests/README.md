# Pruebas

Correr todo: `pytest` desde la raíz del proyecto.

## Qué cubre

- `test_filtros_duros.py` — los `_cumple_X()` de `busqueda.py` (antigüedad,
  comodidades indispensables, UPZ, municipios). Puros, sin DB ni red.
- `test_filtros_portal.py` — cómo se traducen los criterios de una
  búsqueda a los parámetros/URL de cada portal. Puros, sin red (no visita
  FincaRaíz/Metrocuadrado de verdad).
- `test_rutas_busqueda.py` — formularios y rutas de búsqueda vía
  `app.test_client()`. Estos SÍ tocan la base real de Railway (no hay
  Postgres local) porque no hay otra forma de probar persistencia, pero
  cada fixture crea sus propios datos descartables y los borra al
  terminar (`cliente_temporal`, `crear_busqueda` en `conftest.py`).

## Qué NO cubre (a propósito)

- Scraping real (Selenium contra FincaRaíz/Metrocuadrado) — lento y
  depende de que el sitio no haya cambiado su HTML. Si tocas
  `extractor_links.py`/`extractor_detalles.py`, verificar a mano con un
  script desechable contra el sitio real (ver ejemplos en el historial de
  git) o revisar directamente en el navegador la URL que se construye.
- Llamados reales a Claude (`normalizar_comodidades_llm`,
  `rankear_candidatos_llm`, `generar_reporte`) — cuestan tokens y son
  lentos. Si tocas esos prompts, correr un caso chico a mano primero.

## Si agregas una prueba nueva

Antes de escribir un script desechable para verificar un fix a mano (como
se hizo varias veces antes de que existiera este directorio), primero
revisa si cabe como un caso más en uno de estos archivos - así queda
disponible para la próxima vez en vez de perderse.
