import requests

import db
from portales import buscar_portal, extraer_detalle
from extractor_links import configurar_driver
from spatial_analysis import enriquecer_inmueble
from scoring import rankear_candidatos_llm, top_n


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


def _filtros_desde_cliente(busqueda: dict, portal: str, cantidad: int, municipio_nombre: str) -> dict:
    """Cada portal tiene una firma de busqueda distinta (nombres de parametro
    distintos), asi que no se puede pasar el mismo dict de filtros a los dos.
    El municipio se recibe explicito (no desde busqueda["municipio_interes"])
    porque una busqueda ahora puede cubrir varios municipios a la vez - ver
    ejecutar_busqueda_multi_municipio."""
    tipos = [busqueda["tipo_vivienda"]]
    estado = "usados" if busqueda.get("estado_deseado") == "usado" else "nuevos"

    ciudad = _slugify_municipio(municipio_nombre)

    # estrato_objetivo ya es una lista (multi-choice) - ambos portales
    # aceptan una lista de estratos nativamente.
    estratos = busqueda.get("estrato_objetivo") or None
    paginas = max(1, cantidad // 20)

    if portal == "fincaraiz":
        return {
            "paginas_a_extraer": paginas,
            "operacion": "venta",
            "tipos_inmueble": tipos,
            "ubicacion": f"{ciudad}/{ciudad}-dc" if ciudad == "bogota" else ciudad,
            "habitaciones": busqueda.get("habitaciones_min"),
            "estado": estado,
            "precio_min": busqueda.get("presupuesto_min"),
            "precio_max": busqueda.get("presupuesto_max"),
            "estratos": estratos,
        }
    if portal == "metrocuadrado":
        return {
            "paginas_a_extraer": paginas,
            "operacion": "venta",
            "tipos_inmueble": tipos,
            "ciudad": ciudad,
            "habitaciones_min": busqueda.get("habitaciones_min"),
            "precio_min": busqueda.get("presupuesto_min"),
            "precio_max": busqueda.get("presupuesto_max"),
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


def ejecutar_busqueda(busqueda: dict, portales: list[str], cantidad: int, municipio_nombre: str, busqueda_id: int) -> list[dict]:
    """Pipeline completo para UN municipio: busca en los portales pedidos,
    deduplica contra la tabla maestra, revalida anuncios existentes, procesa
    los nuevos, y devuelve todos los anuncios activos encontrados.

    Revisa la bandera de cancelacion entre cada portal y entre cada
    anuncio procesado - Python no puede matar un thread de forma segura
    a mitad de ejecucion, asi que la cancelacion es cooperativa: se
    detiene en el proximo punto seguro, no instantaneamente."""
    todas_urls = []
    for portal in portales:
        if _fue_cancelada(busqueda_id):
            db.actualizar_busqueda_log(busqueda_id, "Búsqueda cancelada por el usuario.", "info")
            return []
        filtros = _filtros_desde_cliente(busqueda, portal, cantidad, municipio_nombre)
        urls = buscar_portal(portal, filtros)
        todas_urls.extend(urls)
        db.actualizar_busqueda_log(busqueda_id, f"{municipio_nombre} / {portal}: {len(urls)} anuncios encontrados", "ok")

    if _fue_cancelada(busqueda_id):
        db.actualizar_busqueda_log(busqueda_id, "Búsqueda cancelada por el usuario.", "info")
        return []

    urls_existentes = [u for u in todas_urls if db.buscar_anuncio_por_url(u) is not None]
    revalidar_anuncios_existentes(urls_existentes)

    urls_nuevas = filtrar_urls_nuevas(todas_urls)
    db.actualizar_busqueda_log(busqueda_id, f"{municipio_nombre}: {len(urls_nuevas)} anuncios nuevos por procesar", "info")

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


def _distribuir_cantidad(cantidad: int, n: int) -> list[int]:
    """Reparte 'cantidad' en n baldes lo mas parejo posible. Si no divide
    exacto, los primeros baldes (en el orden recibido) se llevan el
    remanente - esto es lo que le da a la lista ordenada de municipios su
    prioridad quieta en los empates."""
    if n <= 0:
        return []
    base, resto = divmod(cantidad, n)
    return [base + 1 if i < resto else base for i in range(n)]


def _merge_nuevos(actual: list[dict], nuevos: list[dict]) -> list[dict]:
    """Combina resultados de una nueva ronda de busqueda con los ya
    acumulados para el mismo municipio, sin duplicar por id (una ronda
    posterior con mas paginas deberia ser un superset, pero no se asume)."""
    ids_vistos = {a["id"] for a in actual}
    combinados = list(actual)
    for a in nuevos:
        if a["id"] not in ids_vistos:
            combinados.append(a)
            ids_vistos.add(a["id"])
    return combinados


def _aplanar(encontrados_por_municipio: dict[str, list[dict]]) -> list[dict]:
    resultado = []
    ids_vistos = set()
    for lista in encontrados_por_municipio.values():
        for a in lista:
            if a["id"] not in ids_vistos:
                resultado.append(a)
                ids_vistos.add(a["id"])
    return resultado


def ejecutar_busqueda_multi_municipio(
    busqueda: dict, portales: list[str], cantidad: int, municipios: list[dict], busqueda_id: int, max_iteraciones: int = 5
) -> list[dict]:
    """Reparte 'cantidad' entre los municipios de la lista (en el orden que
    el funcionario definio) y ejecuta una busqueda por cada uno.

    Si al sumar todos los municipios no se alcanza el total pedido, reparte
    lo faltante de forma equitativa:
      - entre los municipios que SI tuvieron resultados, si al menos uno
        se quedo en cero: los que no tuvieron nada no dan mas para dar.
      - entre los n-1 municipios con MAS anuncios encontrados, si todos
        tuvieron resultados: se favorece a los que ya mostraron tener mas
        oferta disponible.
    Los empates se resuelven a favor del primero en la lista original
    (orden estable). El proceso se repite hasta completar la cantidad
    pedida, hasta un tope de iteraciones, o hasta que una ronda no sume
    ningun anuncio nuevo (senal de que ya no hay mas oferta que sacar).

    Caso especial de un solo municipio: si no se completa el total, se
    hace UN UNICO reintento con mas paginas (no se repite en loop)."""
    n = len(municipios)
    if n == 0:
        return []

    nombres = [m.get("municipio") for m in municipios]
    encontrados_por_municipio: dict[str, list[dict]] = {nombre: [] for nombre in nombres}
    objetivo_acumulado = dict(zip(nombres, _distribuir_cantidad(cantidad, n)))

    for nombre in nombres:
        if _fue_cancelada(busqueda_id):
            return _aplanar(encontrados_por_municipio)
        encontrados_por_municipio[nombre] = ejecutar_busqueda(
            busqueda, portales, objetivo_acumulado[nombre], nombre, busqueda_id
        )

    total_encontrado = sum(len(v) for v in encontrados_por_municipio.values())
    faltante = cantidad - total_encontrado

    if n == 1:
        nombre = nombres[0]
        if faltante > 0 and not _fue_cancelada(busqueda_id):
            db.actualizar_busqueda_log(
                busqueda_id,
                f"{nombre}: solo se encontraron {total_encontrado}/{cantidad}, reintentando una vez más con más páginas...",
                "info",
            )
            objetivo_acumulado[nombre] += max(faltante * 2, 10)
            nuevo_resultado = ejecutar_busqueda(busqueda, portales, objetivo_acumulado[nombre], nombre, busqueda_id)
            encontrados_por_municipio[nombre] = _merge_nuevos(encontrados_por_municipio[nombre], nuevo_resultado)
        return _aplanar(encontrados_por_municipio)

    iteracion = 0
    while faltante > 0 and iteracion < max_iteraciones and not _fue_cancelada(busqueda_id):
        iteracion += 1
        conteos = {nombre: len(encontrados_por_municipio[nombre]) for nombre in nombres}

        if any(c == 0 for c in conteos.values()):
            candidatos = [nombre for nombre in nombres if conteos[nombre] > 0]
        else:
            orden_desc = sorted(nombres, key=lambda nom: -conteos[nom])  # sort estable -> empates respetan orden original
            candidatos = orden_desc[:-1] if len(orden_desc) > 1 else orden_desc

        if not candidatos:
            db.actualizar_busqueda_log(busqueda_id, "No se encontraron más inmuebles disponibles en los municipios buscados.", "info")
            break

        extras = _distribuir_cantidad(faltante, len(candidatos))
        progreso = False
        for nombre, extra in zip(candidatos, extras):
            if extra <= 0 or _fue_cancelada(busqueda_id):
                continue
            objetivo_acumulado[nombre] += extra
            db.actualizar_busqueda_log(busqueda_id, f"{nombre}: buscando {extra} inmuebles adicionales (ronda {iteracion})...", "info")
            nuevo_resultado = ejecutar_busqueda(busqueda, portales, objetivo_acumulado[nombre], nombre, busqueda_id)
            combinados = _merge_nuevos(encontrados_por_municipio[nombre], nuevo_resultado)
            if len(combinados) > len(encontrados_por_municipio[nombre]):
                progreso = True
            encontrados_por_municipio[nombre] = combinados

        total_encontrado = sum(len(v) for v in encontrados_por_municipio.values())
        faltante = cantidad - total_encontrado

        if not progreso:
            db.actualizar_busqueda_log(busqueda_id, "No fue posible encontrar más inmuebles nuevos, se detiene la búsqueda de adicionales.", "info")
            break

    return _aplanar(encontrados_por_municipio)


def ejecutar_busqueda_completa(busqueda_id: int, top: int = 5):
    """Orquesta el flujo completo de un click en 'Buscar': scraping + dedup
    (ejecutar_busqueda), scoring de todos los candidatos con el LLM (un
    solo llamado por busqueda, no uno por inmueble), y guarda el ranking
    en resultados_busqueda. Los reportes NO se generan aca - se generan
    on-demand cuando el funcionario le da clic a "Generar reporte" sobre
    un inmueble especifico en la tabla de resultados (ver /api/reportes/generar
    en app.py), asi no se gasta tiempo/costo de Claude en reportes que
    nadie va a pedir."""
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
        municipios = busqueda_obj.get("municipios") or []

        if not municipios:
            raise ValueError("La búsqueda no tiene ningún municipio configurado")

        candidatos = ejecutar_busqueda_multi_municipio(busqueda_obj, portales, cantidad, municipios, busqueda_id)

        if _fue_cancelada(busqueda_id):
            db.finalizar_busqueda(busqueda_id, "cancelada")
            return

        db.actualizar_busqueda_log(busqueda_id, f"{len(candidatos)} anuncios activos encontrados", "ok")

        if candidatos:
            db.actualizar_busqueda_log(busqueda_id, "Calculando compatibilidad con IA...", "info")
        rankeados = rankear_candidatos_llm(busqueda_obj, candidatos)
        mejores = top_n(rankeados, top)
        ids_top = {a["id"] for a in mejores}

        for a in rankeados:
            db.guardar_resultado_busqueda(busqueda_id, a["id"], a["score"], a["id"] in ids_top)

        db.actualizar_busqueda_log(busqueda_id, "Busqueda completada", "ok")
        db.finalizar_busqueda(busqueda_id, "done")
    except Exception as e:
        db.actualizar_busqueda_log(busqueda_id, f"Error: {e}", "error")
        db.finalizar_busqueda(busqueda_id, "error")
