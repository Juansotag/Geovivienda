import json
import re
import time
from datetime import datetime

import anthropic
import h3
import requests
from dotenv import load_dotenv

import config
from database import db
from extractors.portales import buscar_portal, extraer_detalle
from extractors.extractor_links import configurar_driver
from services.spatial_analysis import enriquecer_inmueble, verificar_ubicacion_rapida
from services.scoring import rankear_candidatos_llm, top_n

load_dotenv()
_client = anthropic.Anthropic()


# Catalogo cerrado de comodidades DEL INMUEBLE (no del entorno/zona - eso
# tiene tratamiento aparte). Aprobado por el usuario 2026-07-18. Un LLM
# clasifica el texto libre de cada anuncio contra ESTE catalogo exacto
# (ver normalizar_comodidades_llm) - asi "zona verde"/"zonas verdes"/
# "patio"/"zona campestre" en el texto crudo de los portales convergen a
# un solo valor canonico, en vez del match por keyword fragil que habia
# antes (SINONIMOS_COMODIDADES, ahora reemplazado por esto).
CATALOGO_COMODIDADES = [
    # Ascensor y circulación vertical
    "Ascensor", "Ascensor panorámico", "Ascensor de servicio", "Ascensor inteligente", "Rampa de acceso",
    # Seguridad y acceso
    "Vigilancia 24 horas", "Portería", "Recepción / Lobby", "Citófono", "Circuito cerrado de TV",
    "Acceso con tarjeta o dispositivo", "Conjunto cerrado", "Control de acceso peatonal",
    "Control de acceso vehicular", "Alarma de seguridad", "Detección de humo", "Puerta de seguridad",
    "Cerca eléctrica", "Casetas de vigilancia",
    # Parqueadero
    "Parqueadero", "Garaje cubierto", "Parqueadero descubierto", "Parqueadero de visitantes", "Bahía de parqueo",
    "Parqueadero para motos", "Bicicletero", "Estación de carga para vehículos eléctricos",
    "Parqueadero para personas con movilidad reducida",
    # Zonas comunes recreativas y deportivas
    "Piscina", "Piscina climatizada", "Jacuzzi", "Sauna", "Turco (baño turco)", "Gimnasio",
    "Cancha múltiple", "Cancha de fútbol", "Cancha de baloncesto", "Cancha de squash", "Cancha de tenis",
    "Zona de golf / mini golf", "Sendero para trotar", "Zona de yoga", "Muro de escalada", "Piscina para niños",
    # Zonas comunes sociales y de reunión
    "Salón comunal", "Salón social", "Salón de eventos", "Zona BBQ", "Zona de asados", "Coworking",
    "Sala de juntas", "Salón de juegos", "Zona de cine / cinema", "Terraza rooftop", "Zona lounge",
    "Rooftop bar", "Biblioteca", "Sala de estudio", "Zona kids / ludoteca", "Guardería",
    # Zonas infantiles y familiares
    "Zona infantil", "Parque infantil", "Apto para niños", "Zona de juegos exteriores",
    "Piscina infantil", "Sala de lactancia",
    # Zonas verdes y exteriores comunes
    "Zonas verdes", "Jardines", "Senderos peatonales", "Huerta comunitaria", "Zona de mascotas",
    "Parque canino", "Terraza común", "Plazoleta",
    # Interior - cocina
    "Cocina integral", "Cocina abierta / americana", "Cocina cerrada", "Isla de cocina",
    "Barra estilo americano", "Horno", "Lavaplatos incluido", "Nevera incluida", "Estufa incluida",
    "Extractor de olores", "Despensa",
    # Interior - baños
    "Baño auxiliar", "Baño de servicio", "Baño en suite", "Ducha de hidromasaje",
    "Sanitarios de bajo consumo", "Calentador de agua", "Ventana en baño",
    # Interior - habitaciones y almacenamiento
    "Walking closet", "Closets", "Estudio / cuarto de estudio", "Cuarto de servicio", "Cuarto útil",
    "Depósito", "Bodega", "Vestier",
    # Interior - acabados y confort
    "Pisos en porcelanato", "Pisos en madera", "Pisos en baldosa", "Doble altura",
    "Ventanales de piso a techo", "Vista panorámica", "Buena iluminación natural", "Chimenea",
    "Aire acondicionado", "Calefacción", "Control térmico", "Ventilación cruzada",
    "Insonorización / control de ruido", "Amoblado",
    # Exterior privado de la unidad
    "Balcón", "Terraza privada", "Patio", "Jardín privado", "Solarium",
    # Zona de ropas
    "Zona de lavandería", "Cuarto de lavado", "Patio de ropas",
    # Servicios del edificio / conjunto
    "Planta eléctrica", "Shut de basura", "Recolección de basuras", "Wifi en zonas comunes",
    "Administración incluida", "Conserjería", "Servicio de mensajería", "Casa club",
    # Sostenibilidad
    "Paneles solares", "Energía solar", "Sistema de recolección de aguas lluvias",
    "Certificación LEED / construcción sostenible",
    # Mascotas y normas
    "Se permiten mascotas", "Se permite fumar", "Apto para arriendo tipo Airbnb",
    # Especiales / proyectos nuevos
    "Sala de ventas", "Apartamento modelo", "Entrega inmediata", "Sobre planos",
    "Financiación directa con constructora", "Subsidio de vivienda aplicable",
]


def normalizar_comodidades_llm(anuncios: list[dict]) -> dict[int, list[str]]:
    """Le pide a Claude que clasifique el texto crudo de comodidades de cada
    anuncio contra CATALOGO_COMODIDADES en UN SOLO llamado (batcheado, igual
    que calcular_scores_llm) - asi "zona verde"/"zonas verdes"/"patio"/
    "zona campestre" convergen al mismo valor canonico en vez de quedar
    como strings distintos que el filtro duro nunca hace matchear entre si.

    El LLM SOLO puede devolver valores que existen literalmente en el
    catalogo - no inventa categorias nuevas (eso descontrolaria el
    catalogo con el tiempo). Si nada del catalogo aplica, devuelve lista
    vacia para ese anuncio, no null.

    Devuelve {anuncio_id: [comodidades canonicas]}. Si la llamada falla
    (API, parseo), devuelve {} - quien llama debe tratar eso como
    "todavia no procesado", no como "no tiene comodidades"."""
    if not anuncios:
        return {}

    catalogo_txt = "\n".join(f"- {c}" for c in CATALOGO_COMODIDADES)
    anuncios_txt = "\n".join(
        f"- id={a['id']}: {(a.get('comodidades') or 'sin texto de comodidades')[:400]}"
        + (f" | descripción: {(a.get('descripcion') or '')[:200]}" if a.get("descripcion") else "")
        for a in anuncios
    )

    prompt = f"""Eres un clasificador de comodidades inmobiliarias. Tienes un CATALOGO
CERRADO de comodidades y el texto crudo (mal escrito, inconsistente, con
sinonimos) que cada portal trae para cada anuncio. Tu trabajo es asignar a
cada anuncio SOLO las comodidades del catalogo que efectivamente aplican
segun su texto.

CATALOGO CERRADO (usa EXACTAMENTE estos textos, no inventes variantes):
{catalogo_txt}

ANUNCIOS A CLASIFICAR:
{anuncios_txt}

Reglas:
- Solo puedes usar valores que aparecen LITERALMENTE en el catalogo de arriba.
- Si el texto menciona algo que no esta en el catalogo, ignoralo (no lo agregues).
- Si dos formas distintas de decir lo mismo aparecen (ej. "zona verde" y "patio"
  cuando claramente se refieren a lo mismo), usa el termino del catalogo mas cercano.
- Si un anuncio no tiene comodidades reconocibles del catalogo, devuelve una lista vacia para el.

Responde ÚNICAMENTE con un array JSON, sin texto adicional, con este formato exacto:
[{{"id": 123, "comodidades": ["Ascensor", "Piscina"]}}, ...]
"""

    try:
        respuesta = _client.messages.create(
            model=config.CLAUDE_SMART,
            max_tokens=config.MAX_TOKENS_SCORING,
            messages=[{"role": "user", "content": prompt}],
        )
        texto = "".join(b.text for b in respuesta.content if b.type == "text").strip()
        if texto.startswith("```"):
            texto = texto.split("```")[1]
            if texto.lower().startswith("json"):
                texto = texto[4:]
        datos = json.loads(texto)
        catalogo_set = set(CATALOGO_COMODIDADES)
        resultado = {}
        for item in datos:
            # filtro de seguridad: descarta cualquier cosa que el LLM haya
            # devuelto fuera del catalogo, por si alucino un termino nuevo
            comodidades_validas = [c for c in (item.get("comodidades") or []) if c in catalogo_set]
            resultado[int(item["id"])] = comodidades_validas
        return resultado
    except Exception:
        return {}


# Catalogo completo de valores de "antiguedad" que efectivamente producen
# los dos portales (verificado contra texto real ya scrapeado, no es una
# lista teorica) - se usa para validar el campo en el formulario de editar
# inmueble como un select cerrado, no texto libre (si el usuario puede
# escribir cualquier cosa ahi, _parsear_antiguedad no la reconoce y el
# anuncio pierde su filtro duro de antiguedad silenciosamente).
ANTIGUEDAD_VALORES_FINCARAIZ = ["menor a 1 año", "1 a 8 años", "9 a 15 años", "16 a 30 años", "más de 30 años"]
ANTIGUEDAD_VALORES_METROCUADRADO = ["Entre 0 y 5 años", "Entre 5 y 10 años", "Entre 10 y 20 años", "Más de 20 años", "Remodelado"]
ANTIGUEDAD_VALORES_VALIDOS = ANTIGUEDAD_VALORES_FINCARAIZ + ANTIGUEDAD_VALORES_METROCUADRADO


def _sin_tildes(texto: str) -> str:
    reemplazos = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n"}
    t = texto.lower()
    for k, v in reemplazos.items():
        t = t.replace(k, v)
    return t


def _parsear_antiguedad(texto: str | None) -> tuple[int | None, int | None]:
    """Traduce el texto de antiguedad de CUALQUIERA de los dos portales a un
    rango numerico (anios_min, anios_max) - max=None significa sin limite
    superior ('mas de N anios'). Cubre las 5 categorias de FincaRaiz
    (menor a 1 anio / 1 a 8 / 9 a 15 / 16 a 30 / mas de 30) y las 4 de
    Metrocuadrado (Entre 0 y 5 / 5 y 10 / 10 y 20 / mas de 20), verificado
    contra los valores reales que ambos portales devuelven. Si el texto no
    matchea ningun patron conocido (ej. Metrocuadrado a veces trae
    "¡Preguntale!" cuando no lo sabe), devuelve (None, None) en vez de
    fallar - un anuncio sin antiguedad conocida no debe bloquear el filtro
    duro, solo queda fuera de la comparacion."""
    if not texto:
        return None, None
    t = _sin_tildes(texto.strip())

    m = re.search(r"menor a (\d+)", t)
    if m:
        return 0, int(m.group(1))

    m = re.search(r"mas de (\d+)", t)
    if m:
        return int(m.group(1)) + 1, None

    m = re.search(r"entre (\d+) y (\d+)", t)
    if m:
        return int(m.group(1)), int(m.group(2))

    m = re.search(r"(\d+) a (\d+)", t)
    if m:
        return int(m.group(1)), int(m.group(2))

    return None, None


def _rangos_se_solapan(min1, max1, min2, max2) -> bool:
    """None en cualquier punta significa 'sin limite' de ese lado."""
    if max1 is not None and min2 is not None and max1 < min2:
        return False
    if max2 is not None and min1 is not None and max2 < min1:
        return False
    return True


def _cumple_antiguedad(busqueda: dict, anuncio: dict) -> bool:
    b_min, b_max = busqueda.get("antiguedad_anios_min"), busqueda.get("antiguedad_anios_max")
    if b_min is None and b_max is None:
        return True  # el cliente no puso limite de antiguedad
    a_min, a_max = anuncio.get("antiguedad_anios_min"), anuncio.get("antiguedad_anios_max")
    if a_min is None and a_max is None:
        return True  # no sabemos la antiguedad del anuncio - no lo descartamos por falta de dato
    return _rangos_se_solapan(a_min, a_max, b_min, b_max)


def _cumple_comodidades_indispensables(busqueda: dict, anuncio: dict) -> bool:
    """Match exacto contra comodidades_normalizadas (calculado por
    normalizar_comodidades_llm), no keyword-matching sobre texto libre -
    por eso el formulario solo deja elegir Indispensables del catalogo
    cerrado, garantizando que lo que el cliente pide y lo que el anuncio
    tiene esten en el mismo vocabulario exacto."""
    indispensables = busqueda.get("comodidades_indispensables") or []
    if not indispensables:
        return True
    normalizadas = anuncio.get("comodidades_normalizadas")
    if normalizadas is None:
        return True  # todavia no se ha clasificado - no descartar por falta de dato
    normalizadas_set = set(normalizadas)
    return all(c in normalizadas_set for c in indispensables)


def _cumple_upz(busqueda: dict, anuncio: dict) -> bool:
    """upz es una LISTA (puede combinar UPZ de localidades distintas en la
    misma busqueda - localidad ya no es un criterio propio, cada UPZ trae
    su localidad solo como etiqueta informativa en el formulario). El
    anuncio pasa si cae en AL MENOS UNA de las UPZ pedidas, mismo patron
    OR que _cumple_municipios.

    IMPORTANTE: NO se llama enriquecer_inmueble aqui. La UPZ ya se carga
    en procesar_anuncio_nuevo. Si no llegó (anuncio sin coordenadas o
    fuera de Bogotá), pasamos el filtro (no descartamos por falta de dato)."""
    upz_pedidas = busqueda.get("upz") or []
    if not upz_pedidas:
        return True

    a_upz = anuncio.get("upz")
    if not a_upz:
        return True  # sin dato: no descartamos por falta de UPZ

    a_norm = _sin_tildes(str(a_upz).strip().lower())
    for upz_pedida in upz_pedidas:
        b_norm = _sin_tildes(str(upz_pedida).strip().lower())
        if b_norm in a_norm or a_norm in b_norm:
            return True
    return False



def _cumple_municipios(busqueda: dict, anuncio: dict) -> bool:
    """A diferencia de localidad/upz (un valor opcional), 'municipios' es
    una lista ORDENADA que toda busqueda trae obligatoriamente - el
    anuncio pasa si cae geograficamente en AL MENOS UNO de los municipios
    pedidos (no tiene que coincidir con todos). Esto es la verificacion
    real de que el anuncio quedo donde el portal deberia haberlo filtrado
    por URL - a veces un portal se cuela con un resultado de otra zona.

    IMPORTANTE: NO se llama enriquecer_inmueble aqui. Eso ya se hizo en
    procesar_anuncio_nuevo y municipio_geo ya debe estar en la DB. Si no
    esta, pasamos el filtro (no descartamos por falta de dato)."""
    municipios_pedidos = busqueda.get("municipios") or []
    nombres_pedidos = [m.get("municipio") for m in municipios_pedidos if m.get("municipio")]
    if not nombres_pedidos:
        return True

    a_mpio = anuncio.get("municipio_geo")
    if not a_mpio:
        return True  # sin dato: no descartamos (municipio_geo se carga al enriquecer)

    a_norm = _sin_tildes(str(a_mpio).strip().lower())
    # Normalizar variantes de Bogotá: 'bogota d.c.', 'bogota dc', 'bogota d c' -> 'bogota'
    a_norm = a_norm.replace(".", "").replace(",", " ")
    a_norm = " ".join(a_norm.split())  # colapsar espacios
    for nombre in nombres_pedidos:
        b_norm = _sin_tildes(str(nombre).strip().lower())
        b_norm = b_norm.replace(".", "").replace(",", " ")
        b_norm = " ".join(b_norm.split())
        if b_norm in a_norm or a_norm in b_norm:
            return True
    return False


def _cumple_area_metros(busqueda: dict, anuncio: dict) -> bool:
    """Filtro duro de area: si el anuncio tiene area conocida y la busqueda
    especifica un rango, el anuncio debe quedar dentro. Si el anuncio no
    tiene area registrada se le da el beneficio de la duda (pasa)."""
    area = anuncio.get("area_metros")
    area_min = busqueda.get("area_metros_min")
    area_max = busqueda.get("area_metros_max")
    if area is None:
        return True  # sin datos: pasa
    if area_min is not None and float(area) < float(area_min):
        return False
    if area_max is not None and float(area) > float(area_max):
        return False
    return True


def _cumple_filtros_duros(busqueda: dict, anuncio: dict) -> bool:
    """Filtro duro real: se evalua sobre el registro YA GUARDADO en la tabla
    maestra (nuevo o previamente conocido), asi que es correcto sin importar
    si el anuncio se acaba de scrapear para esta busqueda o ya existia de
    una busqueda anterior con otros criterios."""
    return (
        _cumple_antiguedad(busqueda, anuncio)
        and _cumple_comodidades_indispensables(busqueda, anuncio)
        and _cumple_upz(busqueda, anuncio)
        and _cumple_municipios(busqueda, anuncio)
        and _cumple_area_metros(busqueda, anuncio)
    )



def filtrar_urls_nuevas(urls: list[str]) -> list[str]:
    """Consulta la tabla maestra y devuelve solo las URLs que nunca se han visto.
    Deduplica la lista de entrada para que el mismo URL no se procese dos veces
    aunque el portal lo haya devuelto múltiples veces (paginación solapada)."""
    urls_unicas = list(dict.fromkeys(urls))  # preserva orden, elimina duplicados
    return [u for u in urls_unicas if db.buscar_anuncio_por_url(u) is None]


def anuncio_sigue_activo(url: str, timeout: int = 6) -> bool:
    try:
        r = requests.head(url, timeout=timeout, allow_redirects=True)
        if r.status_code == 405:  # algunos portales no aceptan HEAD, reintentar con GET
            r_get = requests.get(url, timeout=timeout, stream=True)
            status = r_get.status_code
            r_get.close()
            return status < 400
        return r.status_code < 400
    except requests.RequestException:
        return False


def revalidar_anuncios_existentes(urls: list[str]):
    """Marca como inactivos los anuncios que ya no existen en el portal.
    Además, re-enriquece geoespacialmente los anuncios que existen en la DB
    pero no tienen h3_index (fantasmas viejos de antes de implementar H3)."""
    for url in urls:
        a = db.buscar_anuncio_por_url(url)
        if a is None:
            continue

        # Revalidar si sigue activo en el portal
        if not anuncio_sigue_activo(url):
            db.marcar_inactivo(url)
            continue

        # Re-enriquecer si no tiene H3 (anuncio fantasma sin geodatos)
        if not a.get("h3_index") and a.get("latitud") and a.get("longitud"):
            try:
                lat = float(a["latitud"])
                lng = float(a["longitud"])
                geo = enriquecer_inmueble(lat, lng)
                actualizaciones = {}
                if geo.get("h3_data"):
                    actualizaciones["h3_data"] = geo["h3_data"]
                if geo.get("upz"):
                    actualizaciones["upz"] = geo["upz"]
                if geo.get("localidad"):
                    actualizaciones["localidad"] = geo["localidad"]
                if geo.get("municipio"):
                    actualizaciones["municipio_geo"] = geo["municipio"]
                # Calcular y guardar h3_index
                import h3 as h3lib
                h3_index = h3lib.latlng_to_cell(lat, lng, 9)
                actualizaciones["h3_index"] = h3_index
                if not db.obtener_hexagono(h3_index):
                    db.insertar_hexagono({
                        "h3_index": h3_index,
                        "dist_sitp": geo.get("dist_sitp"),
                        "dist_tm": geo.get("dist_tm"),
                        "dist_ciclo": geo.get("dist_ciclo"),
                        "estrato_promedio_200m": geo.get("estrato_promedio_200m"),
                    })
                if actualizaciones:
                    db.actualizar_anuncio(a["id"], actualizaciones)
            except Exception:
                pass  # Si falla el re-enriquecimiento, el anuncio sigue en DB pero sin H3


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

    # UPZs pedidas: si se especificaron y el municipio es Bogotá, las usamos
    # para orientar la URL del portal al sector correcto. El portal muestra
    # todos los anuncios de ese sector (incluyendo los que el vendedor etiquetó
    # con el nombre del barrio en vez de la UPZ) — la verificación geográfica
    # real se hace después con coordenadas.
    upzs_pedidas = busqueda.get("upz") or []
    es_bogota = ciudad == "bogota"

    if portal == "fincaraiz":
        # habitaciones_min y banos_min se pasan como "N-o-mas-habitaciones" /
        # "N-o-mas-banos" en la URL de FincaRaiz — formato confirmado en el sitio
        # real (ej: fincaraiz.com.co/venta/apartamentos/usaquen/bogota/2-o-mas-habitaciones/2-o-mas-banos).
        # construir_url_fincaraiz aplica el sufijo correcto automaticamente cuando se pasa un int.
        if es_bogota and upzs_pedidas:
            # Una búsqueda por UPZ en FincaRaíz: si hay múltiples UPZs, hacemos
            # una corrida por cada una (se manejan arriba en ejecutar_busqueda).
            # Aquí se pasa la primera; para múltiples UPZs se llamará esta
            # función varias veces — el dedup de URLs evita duplicados.
            # Formato FincaRaíz: bogota/usaquen-bogota-dc
            upz_slug = _sin_tildes(upzs_pedidas[0].strip().lower()).replace(" ", "-")
            ubicacion = f"bogota/{upz_slug}-bogota-dc"
        else:
            ubicacion = f"{ciudad}/{ciudad}-dc" if ciudad == "bogota" else ciudad
        return {
            "paginas_a_extraer": paginas,
            "operacion": "venta",
            "tipos_inmueble": tipos,
            "ubicacion": ubicacion,
            "estado": estado,
            "habitaciones": busqueda.get("habitaciones_min"),
            "banos": busqueda.get("banos_min"),
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
            "banos_min": busqueda.get("banos_min"),
            "precio_min": busqueda.get("presupuesto_min"),
            "precio_max": busqueda.get("presupuesto_max"),
            "estratos": estratos,
            "incluir_proyectos": True,
        }
    raise ValueError(f"Portal desconocido: {portal}")


def _normalizar_estado(texto: str | None) -> str | None:
    """Normaliza el estado del anuncio a uno de los 3 valores canonicos que
    usa el resto de la app (usado/nuevo/proyecto). Los portales devuelven
    texto libre inconsistente - ej. FincaRaiz a veces dice "Excelente
    estado" en vez de una categoria limpia como hace Metrocuadrado - y
    ademas en mayusculas, que no calzaba con los <option value="usado">
    en minuscula del formulario (el desplegable nunca quedaba preseleccionado)."""
    if not texto:
        return None
    t = _sin_tildes(texto.strip().lower())
    if "usado" in t:
        return "usado"
    if "sobre plano" in t or "en construccion" in t or "proyecto" in t:
        return "proyecto"
    return "nuevo"  # "nuevo", "excelente estado", "para estrenar", etc.


def _normalizar_para_db(detalle: dict, portal: str) -> dict:
    """Traduce el dict en español-con-mayusculas de los extractores a las
    columnas en minuscula/snake_case de la tabla anuncios."""
    antiguedad_min, antiguedad_max = _parsear_antiguedad(detalle.get("Antiguedad"))
    return {
        "url": detalle["URL"],
        "portal": portal,
        "codigo_portal": detalle.get("Codigo_FincaRaiz"),
        "tipo_inmueble": detalle.get("Tipo_Inmueble"),
        "estado": _normalizar_estado(detalle.get("Estado")),
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
        "antiguedad_anios_min": antiguedad_min,
        "antiguedad_anios_max": antiguedad_max,
        "piso_nro": detalle.get("Piso_Nro"),
        "cantidad_pisos": detalle.get("Cantidad_Pisos"),
        "comodidades": detalle.get("Comodidades"),
        "descripcion": detalle.get("Descripcion"),
        "foto_url": detalle.get("Foto_URL"),
        "latitud": detalle.get("Latitud") or None,
        "longitud": detalle.get("Longitud") or None,
    }


def buscar_administracion_metrocuadrado(url: str) -> int | None:
    """Visita la ficha INDIVIDUAL de un anuncio de Metrocuadrado para
    buscar el valor de administracion, que confirmamos que el portal solo
    publica ahi (no en el JSON de la pagina de resultados que usa
    extraer_links_metrocuadrado - por eso nunca se veia). A proposito NO
    se llama durante una busqueda masiva: visitar cada anuncio uno por uno
    agregaria varios minutos a cada busqueda para un dato secundario. Se
    usa bajo demanda, un anuncio a la vez, desde la pantalla de edicion.

    NOTA: la extraccion es best-effort por texto visible de la pagina
    (no se pudo verificar en vivo contra Metrocuadrado en este entorno de
    desarrollo por falta de un Selenium accesible - probar despues del
    deploy, donde si hay Selenium Grid disponible)."""
    driver = configurar_driver()
    try:
        try:
            driver.get(url)
        except Exception:
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass
        time.sleep(3)  # esperar hidratacion de Next.js, igual que en la busqueda masiva
        html = driver.page_source
    finally:
        driver.quit()

    m = re.search(r"administraci[oó]n[^\d$]{0,25}\$?\s*([\d.,]{4,})", html, re.IGNORECASE)
    if not m:
        return None
    numero = re.sub(r"[^\d]", "", m.group(1))
    return int(numero) if numero else None


def procesar_anuncio_nuevo(url: str, upz_pedidas: list = None, municipios_pedidos: list = None, driver=None) -> int | None:
    """Visita (si hace falta), extrae, verifica ubicación geográfica, enriquece
    geoespacialmente e inserta un anuncio nuevo en la tabla maestra.
    """
    portal = _portal_desde_url(url)

    if portal == "fincaraiz":
        driver_propio = False
        if driver is None:
            driver = configurar_driver()
            driver_propio = True
        try:
            try:
                driver.get(url)
            except Exception:
                try:
                    driver.execute_script("window.stop();")
                except Exception:
                    pass
            html = driver.page_source
        finally:
            if driver_propio:
                try:
                    driver.quit()
                except Exception:
                    pass
    else:
        html = ""  # metrocuadrado ya tiene el detalle cacheado desde la busqueda

    detalle = extraer_detalle(portal, html, url)

    lat = None
    lng = None
    try:
        lat = float(detalle["Latitud"])
        lng = float(detalle["Longitud"])
    except (TypeError, ValueError, KeyError):
        pass

    # --- VERIFICACIÓN RÁPIDA DE UBICACIÓN (~1ms) ---
    # Verifica MUNICIPIO y UPZ de forma instantánea mediante H3 lookup / point-in-polygon.
    # Si el inmueble cae en un municipio o UPZ distinto a los solicitados, se descarta
    # en 1ms, evitando gastar tiempo/recursos en enriquecer o guardar inmuebles fuera de zona.
    ubi_rapida = None
    if lat is not None and lng is not None:
        try:
            ubi_rapida = verificar_ubicacion_rapida(lat, lng)

            # 1. Filtro rápido por municipio
            if municipios_pedidos:
                a_mpio = ubi_rapida.get("municipio") or ""
                a_norm = _sin_tildes(a_mpio.strip().lower()).replace(".", "").replace(",", " ")
                a_norm = " ".join(a_norm.split())
                pasa_mpio = False
                for nombre in municipios_pedidos:
                    b_norm = _sin_tildes(str(nombre).strip().lower()).replace(".", "").replace(",", " ")
                    b_norm = " ".join(b_norm.split())
                    if b_norm in a_norm or a_norm in b_norm:
                        pasa_mpio = True
                        break
                if not pasa_mpio and a_mpio:
                    return None  # fuera del municipio

            # 2. Filtro rápido por UPZ
            if upz_pedidas:
                a_upz = ubi_rapida.get("upz") or ""
                if a_upz:
                    a_upz_norm = _sin_tildes(str(a_upz).strip().lower())
                    pasa_upz = False
                    for upz_pedida in upz_pedidas:
                        u_norm = _sin_tildes(str(upz_pedida).strip().lower())
                        if u_norm in a_upz_norm or a_upz_norm in u_norm:
                            pasa_upz = True
                            break
                    if not pasa_upz:
                        return None  # fuera de las UPZ pedidas (descarte instantaneo)
        except Exception:
            pass  # error en verificación: dejar pasar

    # --- ENRIQUECIMIENTO COMPLETO (~5s, solo si pasó la verificación) ---
    geo = {"dist_sitp": None, "dist_tm": None, "dist_ciclo": None, "estrato_promedio_200m": None}
    if lat is not None and lng is not None:
        try:
            geo = enriquecer_inmueble(lat, lng)
        except Exception:
            # Si ubi_rapida ya tiene upz/municipio, copiarlos al geo fallback
            if ubi_rapida:
                geo["upz"] = ubi_rapida.get("upz")
                geo["municipio"] = ubi_rapida.get("municipio")
                geo["localidad"] = ubi_rapida.get("localidad")

    h3_index = None
    if lat is not None and lng is not None:
        # Usar h3.latlng_to_cell (resolución 9) igual que enriquecer_inmueble en
        # spatial_analysis.py, para que el JOIN con la tabla hexagonos funcione
        # y los sub-scores H3 tengan datos reales. El código anterior usaba un
        # pseudo-índice "hex_{lat*200}_{lng*200}" que nunca coincidía.
        h3_index = h3.latlng_to_cell(lat, lng, 9)
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
    if geo.get("localidad"):
        datos_anuncio["localidad"] = geo["localidad"]
    if geo.get("upz"):
        datos_anuncio["upz"] = geo["upz"]
    if geo.get("municipio"):
        datos_anuncio["municipio_geo"] = geo["municipio"]
    if geo.get("h3_data"):
        datos_anuncio["h3_data"] = geo["h3_data"]
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

        upzs_pedidas = busqueda.get("upz") or []
        if portal == "fincaraiz" and municipio_nombre == "Bogotá, D.C." and len(upzs_pedidas) > 1:
            urls = []
            for u_item in upzs_pedidas:
                filtros = _filtros_desde_cliente(busqueda, portal, max(1, cantidad // len(upzs_pedidas)), municipio_nombre)
                upz_slug = _sin_tildes(u_item.strip().lower()).replace(" ", "-")
                filtros["ubicacion"] = f"bogota/{upz_slug}-bogota-dc"
                urls.extend(buscar_portal(portal, filtros))
        else:
            filtros = _filtros_desde_cliente(busqueda, portal, cantidad, municipio_nombre)
            urls = buscar_portal(portal, filtros)

        todas_urls.extend(urls)
        db.actualizar_busqueda_log(busqueda_id, f"{municipio_nombre} / {portal}: {len(urls)} anuncios encontrados", "ok")

    if _fue_cancelada(busqueda_id):
        db.actualizar_busqueda_log(busqueda_id, "Búsqueda cancelada por el usuario.", "info")
        return []

    # Deduplicar todas_urls antes de usarlas (el mismo portal puede devolver
    # la misma URL en páginas solapadas; esto evita duplicados en candidatos_activos)
    todas_urls = list(dict.fromkeys(todas_urls))

    urls_existentes = [u for u in todas_urls if db.buscar_anuncio_por_url(u) is not None]
    revalidar_anuncios_existentes(urls_existentes)

    urls_nuevas = filtrar_urls_nuevas(todas_urls)
    db.actualizar_busqueda_log(busqueda_id, f"{municipio_nombre}: {len(urls_nuevas)} anuncios nuevos por procesar", "info")

    upz_pedidas = busqueda.get("upz") or []
    nombres_municipios = [m.get("municipio") for m in (busqueda.get("municipios") or []) if m.get("municipio")]

    descartados_ubicacion = 0
    insertados = 0
    fallidos = 0
    total_nuevos = len(urls_nuevas)

    driver_compartido = None
    if any(_portal_desde_url(u) == "fincaraiz" for u in urls_nuevas):
        try:
            driver_compartido = configurar_driver()
        except Exception:
            driver_compartido = None

    try:
        for i, url in enumerate(urls_nuevas, 1):
            if _fue_cancelada(busqueda_id):
                db.actualizar_busqueda_log(busqueda_id, f"Búsqueda cancelada por el usuario ({total_nuevos - i + 1} anuncios sin procesar).", "info")
                break
            prefijo = f"[{i}/{total_nuevos}]"
            url_corta = url.split("/")[-2] if "/" in url else url[-40:]
            db.actualizar_busqueda_log(busqueda_id, f"{prefijo} ⏳ Cargando anuncio: {url_corta}...", "info")
            t_anuncio = time.perf_counter()
            try:
                resultado = procesar_anuncio_nuevo(
                    url,
                    upz_pedidas=upz_pedidas or None,
                    municipios_pedidos=nombres_municipios or None,
                    driver=driver_compartido
                )
                elapsed = _fmt_s(time.perf_counter() - t_anuncio)
                if resultado is None:
                    descartados_ubicacion += 1
                    db.actualizar_busqueda_log(busqueda_id, f"{prefijo} ⏭ Descartado zona ({elapsed}): {url_corta}", "info")
                else:
                    insertados += 1
                    anuncio = db.buscar_anuncio_por_url(url)
                    detalle = ""
                    if anuncio:
                        tipo  = anuncio.get("tipo_inmueble") or "?"
                        upz_  = anuncio.get("upz") or "?"
                        prec  = anuncio.get("precio_venta")
                        prec_s = f"${prec/1_000_000:.0f}M" if prec else "precio N/D"
                        h3ok  = "🔵" if anuncio.get("h3_data") else "🟡"  # azul = H3 fast path; amarillo = fallback
                        detalle = f" — {h3ok} {tipo} en {upz_} {prec_s}"
                    db.actualizar_busqueda_log(busqueda_id, f"{prefijo} ✅ Insertado ({elapsed}){detalle}", "ok")
            except Exception as e:
                import traceback
                elapsed = _fmt_s(time.perf_counter() - t_anuncio)
                fallidos += 1
                tb_lines = traceback.format_exc().strip().splitlines()
                tb_resumen = " | ".join(l.strip() for l in tb_lines[-3:] if l.strip())
                db.actualizar_busqueda_log(
                    busqueda_id,
                    f"{prefijo} ❌ Error ({elapsed}) en {url_corta}: {e} → {tb_resumen}",
                    "error"
                )
    finally:
        if driver_compartido:
            try:
                driver_compartido.quit()
            except Exception:
                pass

    resumen_scraping = f"{municipio_nombre}: scraping listo — {insertados} insertados"
    if descartados_ubicacion:
        resumen_scraping += f", {descartados_ubicacion} fuera de zona"
    if fallidos:
        resumen_scraping += f", {fallidos} con error"
    db.actualizar_busqueda_log(busqueda_id, resumen_scraping, "ok" if fallidos == 0 else "warn")

    candidatos_activos = []
    for url in todas_urls:
        a = db.buscar_anuncio_por_url(url)
        if a and a["activo"]:
            candidatos_activos.append(a)

    # Estandarizar comodidades ANTES del filtro duro (no despues) - si se
    # hiciera al momento de scorear, los anuncios ya habrian sido
    # descartados por el filtro duro con datos sin normalizar, que es
    # justo el problema que esto busca evitar. Solo se procesan los que
    # aun no tienen comodidades_normalizadas (nuevos, o de antes de este
    # feature) - los ya clasificados no se vuelven a mandar al LLM.
    sin_normalizar = [a for a in candidatos_activos if a.get("comodidades_normalizadas") is None]
    if sin_normalizar:
        usar_llm = busqueda.get("usar_normalizacion_llm", True)
        if usar_llm:
            db.actualizar_busqueda_log(busqueda_id, f"{municipio_nombre}: estandarizando comodidades de {len(sin_normalizar)} anuncios...", "info")
            normalizadas = normalizar_comodidades_llm(sin_normalizar)
        else:
            db.actualizar_busqueda_log(busqueda_id, f"{municipio_nombre}: normalización IA desactivada — usando campos estructurados ({len(sin_normalizar)} anuncios).", "info")
            normalizadas = {}  # sin LLM, solo fallback estructural
            # ADVERTENCIA: si la búsqueda tiene comodidades indispensables, el filtro
            # duro (_cumple_comodidades_indispensables) compara contra
            # comodidades_normalizadas, que quedará [] para estos anuncios — todos
            # pasarán el filtro aunque no tengan las comodidades requeridas.
            indispensables = busqueda.get("comodidades_indispensables") or []
            if indispensables:
                db.actualizar_busqueda_log(
                    busqueda_id,
                    f"⚠️ ADVERTENCIA: la búsqueda tiene {len(indispensables)} comodidad(es) indispensable(s) "
                    f"({', '.join(indispensables[:3])}{'...' if len(indispensables) > 3 else ''}) "
                    f"pero la normalización IA está desactivada. El filtro de indispensables NO "
                    f"funcionará correctamente para los {len(sin_normalizar)} anuncios sin clasificar.",
                    "error",
                )

        for a in sin_normalizar:
            lista = normalizadas.get(a["id"])
            if lista is None:
                lista = []  # LLM fallo o desactivado - usamos lista vacia para que no quede None
            # --- Fallback estructural: inferir comodidades de campos directos ---
            lista_set = set(lista)
            if (a.get("parqueaderos") or 0) > 0 and "Parqueadero" not in lista_set:
                lista.append("Parqueadero")
            db.actualizar_anuncio(a["id"], {"comodidades_normalizadas": lista})
            a["comodidades_normalizadas"] = lista


    resultados = []
    d_antiguedad = d_comods = d_upz = d_municipio = 0
    for a in candidatos_activos:
        if not _cumple_antiguedad(busqueda, a):
            d_antiguedad += 1; continue
        if not _cumple_comodidades_indispensables(busqueda, a):
            d_comods += 1; continue
        if not _cumple_upz(busqueda, a):
            d_upz += 1; continue
        if not _cumple_municipios(busqueda, a):
            d_municipio += 1; continue
        resultados.append(a)

    razones = []
    if d_antiguedad: razones.append(f"{d_antiguedad} por antigüedad")
    if d_comods:    razones.append(f"{d_comods} por comodidades")
    if d_upz:       razones.append(f"{d_upz} por UPZ")
    if d_municipio: razones.append(f"{d_municipio} por municipio")
    if razones:
        db.actualizar_busqueda_log(
            busqueda_id,
            f"{municipio_nombre}: {sum([d_antiguedad, d_comods, d_upz, d_municipio])} descartados — " + ", ".join(razones),
            "info",
        )
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



def _fmt_s(segundos: float) -> str:
    """Formatea una duracion en segundos a texto legible.
    Ej: 0.3 -> '0.3s', 90.5 -> '1m 30s', 3700 -> '1h 1m'."""
    s = int(segundos)
    if s < 60:
        return f"{segundos:.1f}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"


def ejecutar_busqueda_completa(busqueda_id: int, top: int = 5):
    """Orquesta el flujo completo de un click en 'Buscar': scraping + dedup
    (ejecutar_busqueda), scoring de todos los candidatos con el LLM (un
    solo llamado por busqueda, no uno por inmueble), y guarda el ranking
    en resultados_busqueda. Los reportes NO se generan aca - se generan
    on-demand cuando el funcionario le da clic a "Generar reporte" sobre
    un inmueble especifico en la tabla de resultados (ver /api/reportes/generar
    en app.py), asi no se gasta tiempo/costo de Claude en reportes que
    nadie va a pedir."""
    t_total = time.perf_counter()
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
        nombres_mpios = ", ".join(m.get("municipio","") for m in municipios)

        if not municipios:
            raise ValueError("La búsqueda no tiene ningún municipio configurado")

        ts = datetime.now().strftime("%d/%m/%Y %H:%M")
        db.actualizar_busqueda_log(busqueda_id, f"--- Nueva corrida · {ts} ---", "separator")
        db.actualizar_busqueda_log(
            busqueda_id,
            f"Buscando {cantidad} inmuebles en {nombres_mpios} via {', '.join(portales)}",
            "info"
        )

        # ── Fase 1: Scraping + dedup + enriquecimiento ───────────────────────
        db.actualizar_busqueda_log(busqueda_id, "▶ Fase 1/4: Scraping y enriquecimiento geoespacial...", "info")
        t1 = time.perf_counter()
        candidatos = ejecutar_busqueda_multi_municipio(busqueda_obj, portales, cantidad, municipios, busqueda_id)
        db.actualizar_busqueda_log(busqueda_id, f"✔ Fase 1/4 completada ({_fmt_s(time.perf_counter()-t1)}) — {len(candidatos)} candidatos activos", "ok")

        if _fue_cancelada(busqueda_id):
            db.finalizar_busqueda(busqueda_id, "cancelada")
            return

        # ── Fase 2: Filtros duros (ya aplicados dentro de ejecutar_busqueda) ─
        # (Los filtros duros se aplican POR municipio en ejecutar_busqueda;
        #  lo que llega aqui ya paso por antiguedad, comodidades, UPZ y municipio)

        if busqueda_obj.get("cantidad_exacta") and len(candidatos) > cantidad:
            db.actualizar_busqueda_log(
                busqueda_id,
                f"▶ Fase 2/4: Número exacto activado — recortando de {len(candidatos)} a {cantidad} candidatos",
                "info",
            )
            candidatos = candidatos[:cantidad]
        else:
            db.actualizar_busqueda_log(
                busqueda_id,
                f"▶ Fase 2/4: Filtros duros aplicados — {len(candidatos)} candidatos pasan al scoring",
                "info",
            )

        # ── Fase 3: Scoring hibrido H3 + LLM ────────────────────────────────
        top_n_valor = int(busqueda_obj.get("top_n") or 5)
        db.actualizar_busqueda_log(
            busqueda_id,
            f"▶ Fase 3/4: Scoring híbrido (sub-scores H3 + pesos LLM + top-{top_n_valor} evaluación cualitativa)...",
            "info"
        )
        t3 = time.perf_counter()
        rankeados = rankear_candidatos_llm(busqueda_obj, candidatos, n=top_n_valor)
        db.actualizar_busqueda_log(
            busqueda_id,
            f"✔ Fase 3/4 completada ({_fmt_s(time.perf_counter()-t3)}) — {len(rankeados)} inmuebles rankeados",
            "ok"
        )

        # ── Fase 4: Persistir resultados ─────────────────────────────────────
        db.actualizar_busqueda_log(busqueda_id, "▶ Fase 4/4: Guardando resultados...", "info")
        mejores_ids = {a["id"] for a in rankeados[:top_n_valor]}
        for a in rankeados:
            sub = a.get("score_desglose", {}).get("sub_scores")
            db.guardar_resultado_busqueda(
                busqueda_id, a["id"], a["score"], a["id"] in mejores_ids, sub_scores=sub
            )

        t_total_s = _fmt_s(time.perf_counter() - t_total)
        db.actualizar_busqueda_log(
            busqueda_id,
            f"✔ Búsqueda completada en {t_total_s} — {len(rankeados)} resultados (top {top_n_valor} marcados)",
            "ok"
        )
        db.finalizar_busqueda(busqueda_id, "done")

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        db.actualizar_busqueda_log(busqueda_id, f"Error fatal: {e}\n{tb[-500:]}", "error")
        db.finalizar_busqueda(busqueda_id, "error")
