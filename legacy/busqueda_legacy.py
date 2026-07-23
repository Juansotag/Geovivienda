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
from services.upz_upl_mapping import UPZ_A_UPL

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
    # Ascensor y circulaciÃ³n vertical
    "Ascensor", "Ascensor panorÃ¡mico", "Ascensor de servicio", "Ascensor inteligente", "Rampa de acceso",
    # Seguridad y acceso
    "Vigilancia 24 horas", "PorterÃ­a", "RecepciÃ³n / Lobby", "CitÃ³fono", "Circuito cerrado de TV",
    "Acceso con tarjeta o dispositivo", "Conjunto cerrado", "Control de acceso peatonal",
    "Control de acceso vehicular", "Alarma de seguridad", "DetecciÃ³n de humo", "Puerta de seguridad",
    "Cerca elÃ©ctrica", "Casetas de vigilancia",
    # Parqueadero
    "Parqueadero", "Garaje cubierto", "Parqueadero descubierto", "Parqueadero de visitantes", "BahÃ­a de parqueo",
    "Parqueadero para motos", "Bicicletero", "EstaciÃ³n de carga para vehÃ­culos elÃ©ctricos",
    "Parqueadero para personas con movilidad reducida",
    # Zonas comunes recreativas y deportivas
    "Piscina", "Piscina climatizada", "Jacuzzi", "Sauna", "Turco (baÃ±o turco)", "Gimnasio",
    "Cancha mÃºltiple", "Cancha de fÃºtbol", "Cancha de baloncesto", "Cancha de squash", "Cancha de tenis",
    "Zona de golf / mini golf", "Sendero para trotar", "Zona de yoga", "Muro de escalada", "Piscina para niÃ±os",
    # Zonas comunes sociales y de reuniÃ³n
    "SalÃ³n comunal", "SalÃ³n social", "SalÃ³n de eventos", "Zona BBQ", "Zona de asados", "Coworking",
    "Sala de juntas", "SalÃ³n de juegos", "Zona de cine / cinema", "Terraza rooftop", "Zona lounge",
    "Rooftop bar", "Biblioteca", "Sala de estudio", "Zona kids / ludoteca", "GuarderÃ­a",
    # Zonas infantiles y familiares
    "Zona infantil", "Parque infantil", "Apto para niÃ±os", "Zona de juegos exteriores",
    "Piscina infantil", "Sala de lactancia",
    # Zonas verdes y exteriores comunes
    "Zonas verdes", "Jardines", "Senderos peatonales", "Huerta comunitaria", "Zona de mascotas",
    "Parque canino", "Terraza comÃºn", "Plazoleta",
    # Interior - cocina
    "Cocina integral", "Cocina abierta / americana", "Cocina cerrada", "Isla de cocina",
    "Barra estilo americano", "Horno", "Lavaplatos incluido", "Nevera incluida", "Estufa incluida",
    "Extractor de olores", "Despensa",
    # Interior - baÃ±os
    "BaÃ±o auxiliar", "BaÃ±o de servicio", "BaÃ±o en suite", "Ducha de hidromasaje",
    "Sanitarios de bajo consumo", "Calentador de agua", "Ventana en baÃ±o",
    # Interior - habitaciones y almacenamiento
    "Walking closet", "Closets", "Estudio / cuarto de estudio", "Cuarto de servicio", "Cuarto Ãºtil",
    "DepÃ³sito", "Bodega", "Vestier",
    # Interior - acabados y confort
    "Pisos en porcelanato", "Pisos en madera", "Pisos en baldosa", "Doble altura",
    "Ventanales de piso a techo", "Vista panorÃ¡mica", "Buena iluminaciÃ³n natural", "Chimenea",
    "Aire acondicionado", "CalefacciÃ³n", "Control tÃ©rmico", "VentilaciÃ³n cruzada",
    "InsonorizaciÃ³n / control de ruido", "Amoblado",
    # Exterior privado de la unidad
    "BalcÃ³n", "Terraza privada", "Patio", "JardÃ­n privado", "Solarium",
    # Zona de ropas
    "Zona de lavanderÃ­a", "Cuarto de lavado", "Patio de ropas",
    # Servicios del edificio / conjunto
    "Planta elÃ©ctrica", "Shut de basura", "RecolecciÃ³n de basuras", "Wifi en zonas comunes",
    "AdministraciÃ³n incluida", "ConserjerÃ­a", "Servicio de mensajerÃ­a", "Casa club",
    # Sostenibilidad
    "Paneles solares", "EnergÃ­a solar", "Sistema de recolecciÃ³n de aguas lluvias",
    "CertificaciÃ³n LEED / construcciÃ³n sostenible",
    # Mascotas y normas
    "Se permiten mascotas", "Se permite fumar", "Apto para arriendo tipo Airbnb",
    # Especiales / proyectos nuevos
    "Sala de ventas", "Apartamento modelo", "Entrega inmediata", "Sobre planos",
    "FinanciaciÃ³n directa con constructora", "Subsidio de vivienda aplicable",
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
        + (f" | descripciÃ³n: {(a.get('descripcion') or '')[:200]}" if a.get("descripcion") else "")
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

Responde ÃNICAMENTE con un array JSON, sin texto adicional, con este formato exacto:
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
ANTIGUEDAD_VALORES_FINCARAIZ = ["menor a 1 aÃ±o", "1 a 8 aÃ±os", "9 a 15 aÃ±os", "16 a 30 aÃ±os", "mÃ¡s de 30 aÃ±os"]
ANTIGUEDAD_VALORES_METROCUADRADO = ["Entre 0 y 5 aÃ±os", "Entre 5 y 10 aÃ±os", "Entre 10 y 20 aÃ±os", "MÃ¡s de 20 aÃ±os", "Remodelado"]
ANTIGUEDAD_VALORES_VALIDOS = ANTIGUEDAD_VALORES_FINCARAIZ + ANTIGUEDAD_VALORES_METROCUADRADO


def _sin_tildes(texto: str) -> str:
    reemplazos = {"Ã¡": "a", "Ã©": "e", "Ã­": "i", "Ã³": "o", "Ãº": "u", "Ã±": "n"}
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
    "Â¡Preguntale!" cuando no lo sabe), devuelve (None, None) en vez de
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


def _upz_a_upl_norm(nombre: str) -> str:
    """Dado un nombre de UPZ (pre-2023, MAYUSCULAS) o UPL (post-2023),
    devuelve la UPL post-2023 normalizada (sin tildes, minusculas).
    Si el nombre ya es una UPL o no hay mapeo, lo normaliza directamente."""
    clave = nombre.strip().upper()
    upl = UPZ_A_UPL.get(clave, nombre)   # traduce si es UPZ conocida
    return _sin_tildes(upl.strip().lower())


def _cumple_upz(busqueda: dict, anuncio: dict) -> bool:
    """upz es una LISTA (puede combinar UPZ de localidades distintas en la
    misma busqueda). El anuncio pasa si cae en AL MENOS UNA de las UPZ/UPLs
    pedidas. Traduce nombres pre-2023 (H3 maestro) a UPL post-2023 antes
    de comparar, usando el mapeo geografico UPZ_A_UPL."""
    upz_pedidas = busqueda.get("upz") or []
    if not upz_pedidas:
        return True

    a_upz = anuncio.get("upz")
    if not a_upz:
        return True  # sin dato: no descartamos por falta de UPZ

    # Traducir UPZ pre-2023 del anuncio a su UPL post-2023 equivalente
    a_upl_norm = _upz_a_upl_norm(str(a_upz))

    for upz_pedida in upz_pedidas:
        # La UPL pedida viene del formulario (post-2023): solo normalizar
        b_norm = _sin_tildes(str(upz_pedida).strip().lower())
        if b_norm in a_upl_norm or a_upl_norm in b_norm:
            return True
    return False


def _es_url_valida_para_municipios(url: str, municipios_pedidos: list[str]) -> bool:
    """Verifica mediante la URL slug de forma instantánea (~0ms) si el anuncio pertenece
    a una ciudad distinta a la solicitada. Evita lanzar navegadores o hacer peticiones HTTP
    para anuncios patrocinados de Manizales, Cali, Barranquilla, Bucaramanga, etc.
    """
    if not municipios_pedidos:
        return True
    url_slug = url.split('/')[-2].lower() if '/' in url else url.lower()
    m_norms = [_sin_tildes(str(m).strip().lower()).replace(".", "").replace(",", "") for m in municipios_pedidos]
    
    ciudades_ajenas = [
        "-manizales", "-cali", "-barranquilla", "-bucaramanga", "-medellin", "-cartagena", 
        "-pereira", "-cucuta", "-pasto", "-ibague", "-neiva", "-tunja", "-bello", 
        "-floridablanca", "-itagui", "-sabaneta", "-dosquebradas", "-piedecuesta", "-armenia", 
        "-barrancabermeja", "-yumbo", "-quimbaya", "-la-estrella", "-villamaria", "-girardot",
        "-fusagasuga", "-ricaurte", "-flandes", "-sopo", "-tocancipa", "-facatativa",
        "-zipaquira", "-chia", "-cajica", "-madrid", "-mosquera", "-funza", "-la-calera",
        "-soacha", "-sibate", "-tabio", "-tenjo", "-cota", "-gachancipa"
    ]
    for c in ciudades_ajenas:
        if c in url_slug:
            c_limpia = c.replace("-", "")
            pasa_explicitamente = any(c_limpia in m for m in m_norms)
            if not pasa_explicitamente:
                return False
    return True


def _cumple_municipios(busqueda: dict, anuncio: dict) -> bool:
    municipios_pedidos = busqueda.get("municipios") or []
    nombres_pedidos = [m.get("municipio") for m in municipios_pedidos if m.get("municipio")]
    if not nombres_pedidos:
        return True

    a_mpio = anuncio.get("municipio_geo")
    if a_mpio:
        a_norm = _sin_tildes(str(a_mpio).strip().lower()).replace(".", "").replace(",", " ")
        a_norm = " ".join(a_norm.split())
        for nombre in nombres_pedidos:
            b_norm = _sin_tildes(str(nombre).strip().lower()).replace(".", "").replace(",", " ")
            b_norm = " ".join(b_norm.split())
            if b_norm in a_norm or a_norm in b_norm:
                return True
        return False

    url_anuncio = anuncio.get("url") or ""
    if url_anuncio and not _es_url_valida_para_municipios(url_anuncio, nombres_pedidos):
        return False

    ubi_txt = _sin_tildes(str(anuncio.get("ubicacion") or "").lower())
    if not ubi_txt:
        return True

    for nombre in nombres_pedidos:
        b_norm = _sin_tildes(str(nombre).strip().lower()).replace(".", "").replace(",", " ")
        b_norm = " ".join(b_norm.split())
        if b_norm in ubi_txt:
            return True

    ciudades_ajenas = ["manizales", "cali", "barranquilla", "bucaramanga", "medellin", "cartagena", "pereira", "cucuta", "pasto", "ibague", "neiva", "tunja", "bello", "floridablanca", "itagui", "sabaneta", "dosquebradas", "piedecuesta", "armenia", "barrancabermeja", "yumbo"]
    if any(c in ubi_txt for c in ciudades_ajenas):
        return False

    return True


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
    aunque el portal lo haya devuelto mÃºltiples veces (paginaciÃ³n solapada)."""
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
    AdemÃ¡s, re-enriquece geoespacialmente los anuncios que existen en la DB
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
        "Ã¡": "a", "Ã©": "e", "Ã­": "i", "Ã³": "o", "Ãº": "u",
        "Ã±": "n", "Ã¼": "u"
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


def _filtros_desde_cliente(busqueda: dict, portal: str, cantidad: int, municipio_nombre: str, paginas_limite: int = 7) -> dict:
    tipos = [busqueda["tipo_vivienda"]]
    estado = "usados" if busqueda.get("estado_deseado") == "usado" else "nuevos"
    ciudad = _slugify_municipio(municipio_nombre)
    estratos = busqueda.get("estrato_objetivo") or None
    paginas = min(41, max(7, paginas_limite))

    upzs_pedidas = busqueda.get("upz") or []
    es_bogota = ciudad == "bogota"

    if portal == "fincaraiz":
        if es_bogota and upzs_pedidas:
            upz_slug = _sin_tildes(upzs_pedidas[0].strip().lower()).replace(" ", "-")
            ubicacion = f"{upz_slug}/bogota"
        else:
            ubicacion = f"{ciudad}/bogota-dc" if es_bogota else ciudad

        return {
            "operacion": "venta",
            "tipos_inmueble": tipos,
            "ubicacion": ubicacion,
            "habitaciones": busqueda.get("habitaciones_min"),
            "banos": busqueda.get("banos_min"),
            "extras": busqueda.get("comodidades_deseadas") or None,
            "parqueaderos": busqueda.get("parqueaderos_min"),
            "estado": estado,
            "precio_min": busqueda.get("precio_min"),
            "precio_max": busqueda.get("precio_max"),
            "antiguedad": busqueda.get("antiguedad_max"),
            "estratos": estratos,
            "paginas": paginas,
            "cantidad_deseada": cantidad
        }
    elif portal == "metrocuadrado":
        if es_bogota and upzs_pedidas:
            upz_slug = _sin_tildes(upzs_pedidas[0].strip().lower()).replace(" ", "-")
            ciudad_param = f"{upz_slug}-bogota"
        else:
            ciudad_param = ciudad

        return {
            "paginas_a_extraer": paginas,
            "operacion": "venta",
            "tipos_inmueble": tipos,
            "ciudad": ciudad_param,
            "habitaciones_min": busqueda.get("habitaciones_min"),
            "banos_min": busqueda.get("banos_min"),
            "precio_min": busqueda.get("precio_min"),
            "precio_max": busqueda.get("precio_max"),
            "estratos": estratos,
            "incluir_proyectos": False
        }
    else:
        raise ValueError(f"Portal no soportado: {portal}")


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
def ejecutar_busqueda_multi_municipio(
    busqueda: dict, portales: list[str], cantidad: int, municipios: list[dict], busqueda_id: int, max_iteraciones: int = 5
) -> list[dict]:
    """Reparte 'cantidad' entre los municipios y UPLs.
    Ronda 1: escaneo de hasta 7 páginas por zona.
    Rondas de escalamiento: si no se alcanza la meta, avanza en bloques de 7 páginas
    adicionales (14, 21, 28... hasta el tope duro de 41 páginas) priorizando las
    zonas de mayor abundancia. Si se solicita detención, devuelve los encontrados.
    """
    import random
    n = len(municipios)
    if n == 0:
        return []

    nombres = [m.get("municipio") for m in municipios]
    encontrados_por_municipio: dict[str, list[dict]] = {nombre: [] for nombre in nombres}
    objetivo_acumulado = dict(zip(nombres, _distribuir_cantidad(cantidad, n)))

    # Ronda 1: Límite inicial de 7 páginas
    paginas_limite_actual = 7
    for nombre in nombres:
        if _fue_cancelada(busqueda_id):
            return _aplanar(encontrados_por_municipio)
        encontrados_por_municipio[nombre] = ejecutar_busqueda(
            busqueda, portales, objetivo_acumulado[nombre], nombre, busqueda_id, paginas_limite=paginas_limite_actual
        )

    total_encontrado = sum(len(v) for v in encontrados_por_municipio.values())
    faltante = cantidad - total_encontrado

    iteracion = 0
    while faltante > 0 and iteracion < max_iteraciones and paginas_limite_actual < 41 and not _fue_cancelada(busqueda_id):
        iteracion += 1
        paginas_limite_actual = min(41, paginas_limite_actual + 7)
        conteos = {nombre: len(encontrados_por_municipio[nombre]) for nombre in nombres}

        # Ordenar zonas por abundancia descendente; desempate aleatorio si hay empate
        items_ordenados = list(nombres)
        random.shuffle(items_ordenados)  # Desempate estocástico
        candidatos = sorted(items_ordenados, key=lambda nom: -conteos[nom])

        if not candidatos:
            db.actualizar_busqueda_log(busqueda_id, "No se encontraron más inmuebles disponibles.", "info")
            break

        extras = _distribuir_cantidad(faltante, len(candidatos))
        progreso = False
        for nombre, extra in zip(candidatos, extras):
            if extra <= 0 or _fue_cancelada(busqueda_id):
                continue
            objetivo_acumulado[nombre] += extra
            db.actualizar_busqueda_log(
                busqueda_id,
                f"{nombre}: escalando búsqueda a pág {paginas_limite_actual} (+{extra} necesarios, ronda {iteracion})...",
                "info"
            )
            nuevo_resultado = ejecutar_busqueda(
                busqueda, portales, objetivo_acumulado[nombre], nombre, busqueda_id, paginas_limite=paginas_limite_actual
            )
            combinados = _merge_nuevos(encontrados_por_municipio[nombre], nuevo_resultado)
            if len(combinados) > len(encontrados_por_municipio[nombre]):
                progreso = True
            encontrados_por_municipio[nombre] = combinados

        total_encontrado = sum(len(v) for v in encontrados_por_municipio.values())
        faltante = cantidad - total_encontrado

        if not progreso:
            db.actualizar_busqueda_log(busqueda_id, "No fue posible encontrar más inmuebles nuevos en páginas avanzadas.", "info")
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
    (ejecutar_busqueda), scoring de todos los candidatos con el LLM,
    y guarda el ranking en resultados_busqueda. Si el usuario presiona
    'Detener', NO aborta los datos sino que califica y guarda todos los
    resultados recolectados hasta el momento de la detención.
    """
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
        db.actualizar_busqueda_log(busqueda_id, "[1/4] Scraping y enriquecimiento geoespacial...", "info")
        t1 = time.perf_counter()
        candidatos = ejecutar_busqueda_multi_municipio(busqueda_obj, portales, cantidad, municipios, busqueda_id)
        
        fue_detenido = _fue_cancelada(busqueda_id)
        if fue_detenido:
            db.actualizar_busqueda_log(
                busqueda_id,
                f"Detención solicitada por el usuario — procesando y clasificando los {len(candidatos)} inmuebles recolectados...",
                "warn"
            )
        else:
            db.actualizar_busqueda_log(busqueda_id, f"Fase 1/4 completada ({_fmt_s(time.perf_counter()-t1)}) — {len(candidatos)} candidatos activos", "ok")

        if not candidatos:
            db.actualizar_busqueda_log(busqueda_id, "No se encontraron inmuebles válidos.", "warn")
            db.finalizar_busqueda(busqueda_id, "done")
            return

        # ── Fase 2: Filtros duros ─────────────────────────────────────────────
        if busqueda_obj.get("cantidad_exacta") and len(candidatos) > cantidad:
            db.actualizar_busqueda_log(
                busqueda_id,
                f"[2/4] Número exacto activado — recortando de {len(candidatos)} a {cantidad} candidatos",
                "info",
            )
            candidatos = candidatos[:cantidad]
        else:
            db.actualizar_busqueda_log(
                busqueda_id,
                f"[2/4] Filtros duros aplicados — {len(candidatos)} candidatos pasan al scoring",
                "info",
            )

        # ── Fase 3: Scoring híbrido H3 + LLM ────────────────────────────────
        top_n_valor = int(busqueda_obj.get("top_n") or 5)
        db.actualizar_busqueda_log(
            busqueda_id,
            f"[3/4] Scoring híbrido (sub-scores H3 + pesos LLM + top-{top_n_valor} evaluación cualitativa)...",
            "info"
        )
        t3 = time.perf_counter()
        rankeados = rankear_candidatos_llm(busqueda_obj, candidatos, n=top_n_valor)
        db.actualizar_busqueda_log(
            busqueda_id,
            f"Fase 3/4 completada ({_fmt_s(time.perf_counter()-t3)}) — {len(rankeados)} inmuebles rankeados",
            "ok"
        )

        # ── Fase 4: Persistir resultados ─────────────────────────────────────
        db.actualizar_busqueda_log(busqueda_id, "[4/4] Guardando resultados...", "info")
        mejores_ids = {a["id"] for a in rankeados[:top_n_valor]}
        for a in rankeados:
            sub = a.get("score_desglose", {}).get("sub_scores")
            db.guardar_resultado_busqueda(
                busqueda_id, a["id"], a["score"], a["id"] in mejores_ids, sub_scores=sub
            )

        t_total_s = _fmt_s(time.perf_counter() - t_total)
        status_msg = "Búsqueda completada" if not fue_detenido else "Búsqueda finalizada tras detención"
        db.actualizar_busqueda_log(
            busqueda_id,
            f"{status_msg} en {t_total_s} — {len(rankeados)} resultados procesados (top {top_n_valor} marcados)",
            "ok"
        )
        db.finalizar_busqueda(busqueda_id, "done")

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        db.actualizar_busqueda_log(busqueda_id, f"Error fatal: {e}\n{tb[-500:]}", "error")
def ejecutar_busqueda(busqueda: dict, portales: list[str], cantidad: int, municipio_nombre: str, busqueda_id: int, paginas_limite: int = 7) -> list[dict]:
    todas_urls = []
    for portal in portales:
        if _fue_cancelada(busqueda_id):
            db.actualizar_busqueda_log(busqueda_id, "Detención solicitada: finalizando recolección de enlaces...", "info")
            break

        upzs_pedidas = busqueda.get("upz") or []
        es_bogota = _sin_tildes(municipio_nombre.strip().lower()).startswith("bogota")

        if es_bogota and len(upzs_pedidas) > 0:
            urls = []
            cant_por_upz = max(1, cantidad // len(upzs_pedidas))
            for u_item in upzs_pedidas:
                if _fue_cancelada(busqueda_id):
                    break
                upz_slug = _sin_tildes(u_item.strip().lower()).replace(" ", "-")
                filtros = _filtros_desde_cliente(busqueda, portal, cant_por_upz, municipio_nombre, paginas_limite=paginas_limite)
                if portal == "fincaraiz":
                    filtros["ubicacion"] = f"{upz_slug}/bogota"
                elif portal == "metrocuadrado":
                    filtros["ciudad"] = f"{upz_slug}-bogota"
                urls.extend(buscar_portal(portal, filtros))
        else:
            filtros = _filtros_desde_cliente(busqueda, portal, cantidad, municipio_nombre, paginas_limite=paginas_limite)
            urls = buscar_portal(portal, filtros)

        todas_urls.extend(urls)
        db.actualizar_busqueda_log(busqueda_id, f"{municipio_nombre} / {portal}: {len(urls)} anuncios encontrados (hasta pág {paginas_limite})", "ok")

    if _fue_cancelada(busqueda_id):
        db.actualizar_busqueda_log(busqueda_id, "Detención solicitada: procesando los enlaces recolectados...", "info")

    todas_urls = list(dict.fromkeys(todas_urls))
    urls_existentes = [u for u in todas_urls if db.buscar_anuncio_por_url(u) is not None]
    revalidar_anuncios_existentes(urls_existentes)

    urls_nuevas = filtrar_urls_nuevas(todas_urls)
    nombres_municipios = [m.get("municipio") for m in (busqueda.get("municipios") or []) if m.get("municipio")]
    urls_nuevas = [u for u in urls_nuevas if _es_url_valida_para_municipios(u, nombres_municipios)]

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
                    db.actualizar_busqueda_log(busqueda_id, f"{prefijo} ⛔ Descartado zona ({elapsed}): {url_corta}", "info")
                else:
                    insertados += 1
                    anuncio = db.buscar_anuncio_por_url(url)
                    detalle = ""
                    if anuncio:
                        tipo  = anuncio.get("tipo_inmueble") or "?"
                        upz_  = anuncio.get("upz") or "?"
                        prec  = anuncio.get("precio_venta")
                        prec_s = f"${prec/1_000_000:.0f}M" if prec else "precio N/D"
                        h3ok  = "🔵" if anuncio.get("h3_data") else "🟡"
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

    sin_normalizar = [a for a in candidatos_activos if a.get("comodidades_normalizadas") is None]
    if sin_normalizar:
        usar_llm = busqueda.get("usar_normalizacion_llm", True)
        if usar_llm:
            db.actualizar_busqueda_log(busqueda_id, f"{municipio_nombre}: estandarizando comodidades de {len(sin_normalizar)} anuncios...", "info")
            normalizadas = normalizar_comodidades_llm(sin_normalizar)
        else:
            db.actualizar_busqueda_log(busqueda_id, f"{municipio_nombre}: normalización IA desactivada — usando campos estructurados ({len(sin_normalizar)} anuncios).", "info")
            normalizadas = {}
            indispensables = busqueda.get("comodidades_indispensables") or []
            if indispensables:
                db.actualizar_busqueda_log(
                    busqueda_id,
                    f"⚠️ ADVERTENCIA: la búsqueda tiene {len(indispensables)} comodidad(es) indispensable(s) "
                    f"pero la normalización IA está desactivada.",
                    "error",
                )

        for a in sin_normalizar:
            lista = normalizadas.get(a["id"])
            if lista is None:
                lista = []
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


def ejecutar_busqueda_multi_municipio(
    busqueda: dict, portales: list[str], cantidad: int, municipios: list[dict], busqueda_id: int, max_iteraciones: int = 5
) -> list[dict]:
    """Reparte 'cantidad' entre los municipios y UPLs.
    Ronda 1: escaneo de hasta 7 páginas por zona.
    Rondas de escalamiento: si no se alcanza la meta, avanza en bloques de 7 páginas
    adicionales (14, 21, 28... hasta el tope duro de 41 páginas) priorizando las
    zonas de mayor abundancia. Si se solicita detención, devuelve los encontrados.
    """
    import random
    n = len(municipios)
    if n == 0:
        return []

    nombres = [m.get("municipio") for m in municipios]
    encontrados_por_municipio: dict[str, list[dict]] = {nombre: [] for nombre in nombres}
    objetivo_acumulado = dict(zip(nombres, _distribuir_cantidad(cantidad, n)))

    # Ronda 1: Límite inicial de 7 páginas
    paginas_limite_actual = 7
    for nombre in nombres:
        if _fue_cancelada(busqueda_id):
            return _aplanar(encontrados_por_municipio)
        encontrados_por_municipio[nombre] = ejecutar_busqueda(
            busqueda, portales, objetivo_acumulado[nombre], nombre, busqueda_id, paginas_limite=paginas_limite_actual
        )

    total_encontrado = sum(len(v) for v in encontrados_por_municipio.values())
    faltante = cantidad - total_encontrado

    iteracion = 0
    while faltante > 0 and iteracion < max_iteraciones and paginas_limite_actual < 41 and not _fue_cancelada(busqueda_id):
        iteracion += 1
        paginas_limite_actual = min(41, paginas_limite_actual + 7)
        conteos = {nombre: len(encontrados_por_municipio[nombre]) for nombre in nombres}

        # Ordenar zonas por abundancia descendente; desempate aleatorio si hay empate
        items_ordenados = list(nombres)
        random.shuffle(items_ordenados)  # Desempate estocástico
        candidatos = sorted(items_ordenados, key=lambda nom: -conteos[nom])

        if not candidatos:
            db.actualizar_busqueda_log(busqueda_id, "No se encontraron más inmuebles disponibles.", "info")
            break

        extras = _distribuir_cantidad(faltante, len(candidatos))
        progreso = False
        for nombre, extra in zip(candidatos, extras):
            if extra <= 0 or _fue_cancelada(busqueda_id):
                continue
            objetivo_acumulado[nombre] += extra
            db.actualizar_busqueda_log(
                busqueda_id,
                f"{nombre}: escalando búsqueda a pág {paginas_limite_actual} (+{extra} necesarios, ronda {iteracion})...",
                "info"
            )
            nuevo_resultado = ejecutar_busqueda(
                busqueda, portales, objetivo_acumulado[nombre], nombre, busqueda_id, paginas_limite=paginas_limite_actual
            )
            combinados = _merge_nuevos(encontrados_por_municipio[nombre], nuevo_resultado)
            if len(combinados) > len(encontrados_por_municipio[nombre]):
                progreso = True
            encontrados_por_municipio[nombre] = combinados

        total_encontrado = sum(len(v) for v in encontrados_por_municipio.values())
        faltante = cantidad - total_encontrado

        if not progreso:
            db.actualizar_busqueda_log(busqueda_id, "No fue posible encontrar más inmuebles nuevos en páginas avanzadas.", "info")
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
    (ejecutar_busqueda), scoring de todos los candidatos con el LLM,
    y guarda el ranking en resultados_busqueda. Si el usuario presiona
    'Detener', NO aborta los datos sino que califica y guarda todos los
    resultados recolectados hasta el momento de la detención.
    """
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
        db.actualizar_busqueda_log(busqueda_id, "[1/4] Scraping y enriquecimiento geoespacial...", "info")
        t1 = time.perf_counter()
        candidatos = ejecutar_busqueda_multi_municipio(busqueda_obj, portales, cantidad, municipios, busqueda_id)
        
        fue_detenido = _fue_cancelada(busqueda_id)
        if fue_detenido:
            db.actualizar_busqueda_log(
                busqueda_id,
                f"Detención solicitada por el usuario — procesando y clasificando los {len(candidatos)} inmuebles recolectados...",
                "warn"
            )
        else:
            db.actualizar_busqueda_log(busqueda_id, f"Fase 1/4 completada ({_fmt_s(time.perf_counter()-t1)}) — {len(candidatos)} candidatos activos", "ok")

        if not candidatos:
            db.actualizar_busqueda_log(busqueda_id, "No se encontraron inmuebles válidos.", "warn")
            db.finalizar_busqueda(busqueda_id, "done")
            return

        # ── Fase 2: Filtros duros ─────────────────────────────────────────────
        if busqueda_obj.get("cantidad_exacta") and len(candidatos) > cantidad:
            db.actualizar_busqueda_log(
                busqueda_id,
                f"[2/4] Número exacto activado — recortando de {len(candidatos)} a {cantidad} candidatos",
                "info",
            )
            candidatos = candidatos[:cantidad]
        else:
            db.actualizar_busqueda_log(
                busqueda_id,
                f"[2/4] Filtros duros aplicados — {len(candidatos)} candidatos pasan al scoring",
                "info",
            )

        # ── Fase 3: Scoring híbrido H3 + LLM ────────────────────────────────
        top_n_valor = int(busqueda_obj.get("top_n") or 5)
        db.actualizar_busqueda_log(
            busqueda_id,
            f"[3/4] Scoring híbrido (sub-scores H3 + pesos LLM + top-{top_n_valor} evaluación cualitativa)...",
            "info"
        )
        t3 = time.perf_counter()
        rankeados = rankear_candidatos_llm(busqueda_obj, candidatos, n=top_n_valor)
        db.actualizar_busqueda_log(
            busqueda_id,
            f"Fase 3/4 completada ({_fmt_s(time.perf_counter()-t3)}) — {len(rankeados)} inmuebles rankeados",
            "ok"
        )

        # ── Fase 4: Persistir resultados ─────────────────────────────────────
        db.actualizar_busqueda_log(busqueda_id, "[4/4] Guardando resultados...", "info")
        mejores_ids = {a["id"] for a in rankeados[:top_n_valor]}
        for a in rankeados:
            sub = a.get("score_desglose", {}).get("sub_scores")
            db.guardar_resultado_busqueda(
                busqueda_id, a["id"], a["score"], a["id"] in mejores_ids, sub_scores=sub
            )

        t_total_s = _fmt_s(time.perf_counter() - t_total)
        status_msg = "Búsqueda completada" if not fue_detenido else "Búsqueda finalizada tras detención"
        db.actualizar_busqueda_log(
            busqueda_id,
            f"{status_msg} en {t_total_s} — {len(rankeados)} resultados procesados (top {top_n_valor} marcados)",
            "ok"
        )
        db.finalizar_busqueda(busqueda_id, "done")

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        db.actualizar_busqueda_log(busqueda_id, f"Error fatal: {e}\n{tb[-500:]}", "error")
        db.finalizar_busqueda(busqueda_id, "error")
