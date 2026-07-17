import requests

import db
from portales import buscar_portal, extraer_detalle
from extractor_links import configurar_driver
from spatial_analysis import enriquecer_inmueble


def filtrar_urls_nuevas(urls: list[str]) -> list[str]:
    """Consulta la tabla maestra y devuelve solo las URLs que nunca se han visto."""
    return [u for u in urls if db.buscar_anuncio_por_url(u) is None]


def anuncio_sigue_activo(url: str, timeout: int = 6) -> bool:
    try:
        r = requests.head(url, timeout=timeout, allow_redirects=True)
        if r.status_code == 405:  # algunos portales no aceptan HEAD, reintentar con GET
            r = requests.get(url, timeout=timeout, stream=True)
        return r.status_code < 400
    except requests.RequestException:
        return False


def revalidar_anuncios_existentes(urls: list[str]):
    """Marca como inactivos en la tabla maestra los anuncios que ya no existen."""
    for url in urls:
        if not anuncio_sigue_activo(url):
            db.marcar_inactivo(url)


def _portal_desde_url(url: str) -> str:
    if "metrocuadrado.com" in url:
        return "metrocuadrado"
    if "fincaraiz.com.co" in url:
        return "fincaraiz"
    raise ValueError(f"No se pudo determinar el portal para {url}")


def _filtros_desde_cliente(cliente: dict, portal: str, cantidad: int) -> dict:
    """Cada portal tiene una firma de busqueda distinta (nombres de parametro
    distintos), asi que no se puede pasar el mismo dict de filtros a los dos."""
    tipos = [cliente["tipo_vivienda"]]
    estado = "usados" if cliente.get("estado_deseado") == "usado" else "nuevos"
    ciudades = cliente.get("ciudades_interes") or ["bogota"]
    ciudad = ciudades[0] if isinstance(ciudades, list) else ciudades
    estratos = [cliente["estrato_objetivo"]] if cliente.get("estrato_objetivo") else None
    paginas = max(1, cantidad // 20)

    if portal == "fincaraiz":
        return {
            "paginas_a_extraer": paginas,
            "operacion": "venta",
            "tipos_inmueble": tipos,
            "ubicacion": f"{ciudad}/{ciudad}-dc" if ciudad == "bogota" else ciudad,
            "habitaciones": cliente.get("habitaciones_min"),
            "estado": estado,
            "precio_min": cliente.get("presupuesto_min"),
            "precio_max": cliente.get("presupuesto_max"),
            "estratos": estratos,
        }
    if portal == "metrocuadrado":
        return {
            "paginas_a_extraer": paginas,
            "operacion": "venta",
            "tipos_inmueble": tipos,
            "ciudad": ciudad,
            "habitaciones_min": cliente.get("habitaciones_min"),
            "precio_min": cliente.get("presupuesto_min"),
            "precio_max": cliente.get("presupuesto_max"),
            "estratos": estratos,
            "incluir_proyectos": True,
        }
    raise ValueError(f"Portal desconocido: {portal}")


def _normalizar_para_db(detalle: dict, geo: dict, portal: str) -> dict:
    """Traduce el dict en español-con-mayusculas de los extractores a las
    columnas en minuscula/snake_case de la tabla anuncios."""
    return {
        "url": detalle["URL"],
        "portal": portal,
        "codigo_portal": detalle.get("Codigo_FincaRaiz"),
        "tipo_inmueble": detalle.get("Tipo_Inmueble"),
        "estado": detalle.get("Estado"),
        "operacion": "venta",
        "precio_venta": detalle.get("Precio_Venta"),
        "administracion": detalle.get("Administracion"),
        "ubicacion_texto": detalle.get("Ubicacion"),
        "ciudad": "bogota",
        "estrato": detalle.get("Estrato"),
        "area_metros": detalle.get("Area_Metros"),
        "habitaciones": detalle.get("Habitaciones"),
        "banos": detalle.get("Banos"),
        "parqueaderos": detalle.get("Parqueaderos"),
        "antiguedad": detalle.get("Antiguedad"),
        "piso_nro": detalle.get("Piso_Nro"),
        "cantidad_pisos": detalle.get("Cantidad_Pisos"),
        "comodidades": detalle.get("Comodidades"),
        "descripcion": detalle.get("Descripcion"),
        "latitud": detalle.get("Latitud") or None,
        "longitud": detalle.get("Longitud") or None,
        "dist_sitp": geo.get("dist_sitp"),
        "dist_tm": geo.get("dist_tm"),
        "dist_ciclo": geo.get("dist_ciclo"),
        "estrato_promedio_200m": geo.get("estrato_promedio_200m"),
    }


def procesar_anuncio_nuevo(url: str) -> int:
    """Visita (si hace falta), extrae, enriquece geoespacialmente e inserta
    un anuncio nuevo en la tabla maestra. Devuelve el id insertado."""
    portal = _portal_desde_url(url)

    if portal == "fincaraiz":
        driver = configurar_driver()
        try:
            driver.get(url)
            html = driver.page_source
        finally:
            driver.quit()
    else:
        html = ""  # metrocuadrado ya tiene el detalle cacheado desde la busqueda

    detalle = extraer_detalle(portal, html, url)

    try:
        geo = enriquecer_inmueble(float(detalle["Latitud"]), float(detalle["Longitud"]))
    except (TypeError, ValueError):
        geo = {"dist_sitp": None, "dist_tm": None, "dist_ciclo": None, "estrato_promedio_200m": None}

    return db.insertar_anuncio(_normalizar_para_db(detalle, geo, portal))


def ejecutar_busqueda(cliente: dict, portales: list[str], cantidad: int, busqueda_id: int) -> list[dict]:
    """Pipeline completo: busca en los portales pedidos, deduplica contra la
    tabla maestra, revalida anuncios existentes, procesa los nuevos, y
    devuelve todos los anuncios activos encontrados."""
    todas_urls = []
    for portal in portales:
        filtros = _filtros_desde_cliente(cliente, portal, cantidad)
        urls = buscar_portal(portal, filtros)
        todas_urls.extend(urls)
        db.actualizar_busqueda_log(busqueda_id, f"{portal}: {len(urls)} anuncios encontrados", "ok")

    urls_existentes = [u for u in todas_urls if db.buscar_anuncio_por_url(u) is not None]
    revalidar_anuncios_existentes(urls_existentes)

    urls_nuevas = filtrar_urls_nuevas(todas_urls)
    db.actualizar_busqueda_log(busqueda_id, f"{len(urls_nuevas)} anuncios nuevos por procesar", "info")

    for url in urls_nuevas:
        try:
            procesar_anuncio_nuevo(url)
        except Exception as e:
            db.actualizar_busqueda_log(busqueda_id, f"Error procesando {url}: {e}", "error")

    resultados = []
    for url in todas_urls:
        a = db.buscar_anuncio_por_url(url)
        if a and a["activo"]:
            resultados.append(a)
    return resultados
