import requests

import db
from portales import buscar_portal, extraer_detalle
from extractor_links import configurar_driver
from spatial_analysis import enriquecer_inmueble
from scoring import rankear_candidatos, top_n
from reportes import crear_y_guardar_reporte


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


def _slugify_municipio(nombre: str) -> str:
    if not nombre:
        return "bogota"
    n = nombre.strip().lower()
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "ñ": "n", "ü": "u"
    }
    for k, v in replacements.items():
        n = n.replace(k, v)
    # DIVIPOLA trae el nombre oficial de Bogota como "Bogota, D.C." (con
    # coma) - sin quitar la coma, el slug quedaba "bogota,-dc", que no
    # calzaba con el caso especial de abajo y rompia la URL en los dos
    # portales (esto causo el bug real: Metrocuadrado devolvia 0
    # resultados y FincaRaiz devolvia inmuebles de otras ciudades).
    n = n.replace(",", " ").replace(".", "")
    n = " ".join(n.split())
    if n in ("bogota", "bogota dc", "santafe de bogota", "santa fe de bogota"):
        return "bogota"
    return n.replace(" ", "-")


def _filtros_desde_cliente(cliente: dict, portal: str, cantidad: int) -> dict:
    """Cada portal tiene una firma de busqueda distinta (nombres de parametro
    distintos), asi que no se puede pasar el mismo dict de filtros a los dos."""
    tipos = [cliente["tipo_vivienda"]]
    estado = "usados" if cliente.get("estado_deseado") == "usado" else "nuevos"
    
    municipio = cliente.get("municipio_interes")
    ciudad = _slugify_municipio(municipio)
    
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


def _normalizar_para_db(detalle: dict, portal: str) -> dict:
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
        "foto_url": detalle.get("Foto_URL"),
        "latitud": detalle.get("Latitud") or None,
        "longitud": detalle.get("Longitud") or None,
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

    lat = None
    lng = None
    try:
        lat = float(detalle["Latitud"])
        lng = float(detalle["Longitud"])
        geo = enriquecer_inmueble(lat, lng)
    except (TypeError, ValueError, KeyError):
        geo = {"dist_sitp": None, "dist_tm": None, "dist_ciclo": None, "estrato_promedio_200m": None}

    h3_index = None
    if lat is not None and lng is not None:
        h3_index = f"hex_{int(lat*200)}_{int(lng*200)}"
        if not db.obtener_hexagono(h3_index):
            db.insertar_hexagono({
                "h3_index": h3_index,
                "dist_sitp": geo.get("dist_sitp"),
                "dist_tm": geo.get("dist_tm"),
                "dist_ciclo": geo.get("dist_ciclo"),
                "estrato_promedio_200m": geo.get("estrato_promedio_200m")
            })

    datos_anuncio = _normalizar_para_db(detalle, portal)
    datos_anuncio["h3_index"] = h3_index
    return db.insertar_anuncio(datos_anuncio)


def _fue_cancelada(busqueda_id: int) -> bool:
    b = db.obtener_busqueda(busqueda_id)
    return b is not None and b["status"] == "cancelando"


def ejecutar_busqueda(cliente: dict, portales: list[str], cantidad: int, busqueda_id: int) -> list[dict]:
    """Pipeline completo: busca en los portales pedidos, deduplica contra la
    tabla maestra, revalida anuncios existentes, procesa los nuevos, y
    devuelve todos los anuncios activos encontrados.

    Revisa la bandera de cancelacion entre cada portal y entre cada
    anuncio procesado - Python no puede matar un thread de forma segura
    a mitad de ejecucion, asi que la cancelacion es cooperativa: se
    detiene en el proximo punto seguro, no instantaneamente."""
    todas_urls = []
    for portal in portales:
        if _fue_cancelada(busqueda_id):
            db.actualizar_busqueda_log(busqueda_id, "Búsqueda cancelada por el usuario.", "info")
            return []
        filtros = _filtros_desde_cliente(cliente, portal, cantidad)
        urls = buscar_portal(portal, filtros)
        todas_urls.extend(urls)
        db.actualizar_busqueda_log(busqueda_id, f"{portal}: {len(urls)} anuncios encontrados", "ok")

    if _fue_cancelada(busqueda_id):
        db.actualizar_busqueda_log(busqueda_id, "Búsqueda cancelada por el usuario.", "info")
        return []

    urls_existentes = [u for u in todas_urls if db.buscar_anuncio_por_url(u) is not None]
    revalidar_anuncios_existentes(urls_existentes)

    urls_nuevas = filtrar_urls_nuevas(todas_urls)
    db.actualizar_busqueda_log(busqueda_id, f"{len(urls_nuevas)} anuncios nuevos por procesar", "info")

    for url in urls_nuevas:
        if _fue_cancelada(busqueda_id):
            db.actualizar_busqueda_log(busqueda_id, f"Búsqueda cancelada por el usuario ({len(todas_urls) - urls_nuevas.index(url)} anuncios sin procesar).", "info")
            break
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


def ejecutar_busqueda_completa(busqueda_id: int, top: int = 5):
    """Orquesta el flujo completo de un click en 'Buscar': scraping + dedup
    (ejecutar_busqueda), scoring de todos los candidatos, guarda el ranking
    en resultados_busqueda, y genera reportes con Claude solo para el top N."""
    try:
        busqueda_obj = db.obtener_busqueda(busqueda_id)
        if not busqueda_obj:
            raise ValueError(f"No se encontró la búsqueda con ID {busqueda_id}")
            
        cliente_id = busqueda_obj["cliente_id"]
        cliente = db.obtener_cliente(cliente_id)
        if not cliente:
            raise ValueError(f"No se encontró el cliente con ID {cliente_id}")
            
        portales = busqueda_obj["portales"]
        cantidad = busqueda_obj["cantidad_solicitada"]

        # Mezclar perfil de cliente y criterios para el reporte
        criterios_completos = {**cliente, **busqueda_obj, "id": cliente["id"]}

        candidatos = ejecutar_busqueda(busqueda_obj, portales, cantidad, busqueda_id)

        if _fue_cancelada(busqueda_id):
            db.finalizar_busqueda(busqueda_id, "cancelada")
            return

        db.actualizar_busqueda_log(busqueda_id, f"{len(candidatos)} anuncios activos encontrados", "ok")

        rankeados = rankear_candidatos(busqueda_obj, candidatos)
        mejores = top_n(rankeados, top)
        ids_top = {a["id"] for a in mejores}

        for a in rankeados:
            db.guardar_resultado_busqueda(busqueda_id, a["id"], a["score"], a["id"] in ids_top)

        db.actualizar_busqueda_log(busqueda_id, f"Generando reportes para el top {len(mejores)}...", "info")
        for a in mejores:
            if _fue_cancelada(busqueda_id):
                db.actualizar_busqueda_log(busqueda_id, "Búsqueda cancelada por el usuario (algunos reportes no se generaron).", "info")
                db.finalizar_busqueda(busqueda_id, "cancelada")
                return
            score = {"total": a["score"], "componentes": a["score_desglose"]}
            crear_y_guardar_reporte(criterios_completos, a, score)

        db.actualizar_busqueda_log(busqueda_id, "Busqueda completada", "ok")
        db.finalizar_busqueda(busqueda_id, "done")
    except Exception as e:
        db.actualizar_busqueda_log(busqueda_id, f"Error: {e}", "error")
        db.finalizar_busqueda(busqueda_id, "error")
