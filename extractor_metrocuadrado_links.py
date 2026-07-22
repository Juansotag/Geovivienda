import json
import re
import time

from extractor_links import configurar_driver

# Modulo de funciones para extraer links (y datos completos) de Metrocuadrado.
#
# A diferencia de FincaRaiz, la pagina de resultados de Metrocuadrado (Next.js)
# trae el detalle COMPLETO de cada inmueble embebido como JSON en el HTML inicial
# (precio, area, habitaciones, banos, estrato, barrio, descripcion, comodidades y
# coordenadas propias). No hace falta visitar cada ficha individual como en
# FincaRaiz: se carga la pagina de resultados UNA sola vez y se cachea el
# registro completo de cada inmueble, para que extractor_metrocuadrado_detalles.py
# lo reutilice sin una segunda peticion.
#
# Confirmado en vivo: NO funciona con requests.get() sin navegador (los datos se
# cargan del lado del cliente), asi que Selenium sigue siendo necesario aqui.
#
# Limitacion conocida: no hay evidencia verificada de la sintaxis de filtros por
# querystring de Metrocuadrado (precio, habitaciones, estrato) mas alla de
# ciudad/tipo/operacion en el path. Por eso el filtrado por presupuesto,
# habitaciones, banos y estrato se hace en Python DESPUES de traer los
# resultados, no por URL.

_CACHE: dict[str, dict] = {}


def construir_url_metrocuadrado(operacion="venta", tipo_inmueble="apartamento", ciudad="bogota"):
    mapa_tipos = {
        "apartamento": "apartamentos",
        "apartamentos": "apartamentos",
        "casa": "casas",
        "casas": "casas",
    }
    tipo_url = mapa_tipos.get(tipo_inmueble.lower().strip(), tipo_inmueble.lower().strip())

    operacion = operacion.lower().strip()
    if operacion not in ("venta", "arriendo"):
        operacion = "venta"

    ciudad_url = ciudad.lower().strip().replace(" ", "-")
    return f"https://www.metrocuadrado.com/{tipo_url}/{operacion}/{ciudad_url}/"


def _extraer_texto_next(html: str) -> str:
    """Decodifica y concatena los fragmentos de self.__next_f.push([1,"..."])."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', html, re.S)
    texto = ""
    for c in chunks:
        try:
            texto += json.loads(c)
        except (json.JSONDecodeError, ValueError):
            continue
    return texto


def _extraer_array_balanceado(texto: str, marcador: str) -> list:
    """Parsea un array JSON balanceando corchetes/llaves a partir de 'marcador':["""
    idx = texto.find(marcador)
    if idx == -1:
        return []
    start = texto.find("[", idx)
    if start == -1:
        return []

    depth = 0
    in_string = False
    escape = False
    end = None
    for i in range(start, len(texto)):
        ch = texto[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end is None:
        return []
    try:
        return json.loads(texto[start:end])
    except json.JSONDecodeError:
        return []


def _parse_resultados(html: str) -> list[dict]:
    texto = _extraer_texto_next(html)
    return _extraer_array_balanceado(texto, '"initialResults"') or _extraer_array_balanceado(texto, '"results":[')


def extraer_links_metrocuadrado(
    paginas_a_extraer=1,
    operacion="venta",
    tipos_inmueble=None,
    ciudad="bogota",
    habitaciones_min=None,
    banos_min=None,
    precio_min=None,
    precio_max=None,
    estratos=None,
    incluir_proyectos=True,
):
    """
    Extrae (y cachea en memoria) los inmuebles de una busqueda en Metrocuadrado.
    Devuelve la lista de URLs completas, igual que extraer_links_fincaraiz.
    """
    tipo = (tipos_inmueble or ["apartamento"])[0]
    url_base = construir_url_metrocuadrado(operacion, tipo, ciudad)
    print(f"URL base Metrocuadrado: {url_base}")

    driver = configurar_driver()
    todos_los_registros = []
    try:
        for pagina in range(paginas_a_extraer):
            url_actual = url_base if pagina == 0 else f"{url_base}?from={pagina * 24}"
            try:
                driver.get(url_actual)
            except Exception:
                try:
                    driver.execute_script("window.stop();")
                except Exception:
                    pass
            time.sleep(3)  # esperar hidratacion de Next.js (los datos cargan del lado del cliente)
            html = driver.page_source
            registros_pagina = _parse_resultados(html)
            if not registros_pagina:
                print(f"Pagina {pagina + 1}: sin resultados nuevos, deteniendo paginacion.")
                break
            todos_los_registros.extend(registros_pagina)
            print(f"Pagina {pagina + 1}: {len(registros_pagina)} inmuebles encontrados.")
    finally:
        driver.quit()

    urls = []
    vistos = set()
    for r in todos_los_registros:
        link = r.get("link")
        if not link or link in vistos:
            continue
        vistos.add(link)

        if not incluir_proyectos and link.startswith("/proyecto"):
            continue
        if precio_min and (r.get("mvalorventa") or 0) < precio_min:
            continue
        if precio_max and (r.get("mvalorventa") or 0) > precio_max:
            continue
        if habitaciones_min and int(r.get("mnrocuartos") or 0) < habitaciones_min:
            continue
        if banos_min and int(r.get("mnrobanos") or 0) < banos_min:
            continue
        if estratos and r.get("estrato") not in estratos:
            continue

        full_url = "https://www.metrocuadrado.com" + link
        _CACHE[full_url] = r
        urls.append(full_url)

    print(f"Total inmuebles despues de filtros: {len(urls)}")
    return urls
