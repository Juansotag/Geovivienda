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


CATALOGO_COMODIDADES = [
    "Ascensor", "Ascensor panorámico", "Ascensor de servicio", "Ascensor inteligente", "Rampa de acceso",
    "Vigilancia 24 horas", "Portería", "Recepción / Lobby", "Citófono", "Circuito cerrado de TV",
    "Acceso con tarjeta o dispositivo", "Conjunto cerrado", "Control de acceso peatonal",
    "Control de acceso vehicular", "Alarma de seguridad", "Detección de humo", "Puerta de seguridad",
    "Cerca eléctrica", "Casetas de vigilancia",
    "Parqueadero", "Garaje cubierto", "Parqueadero descubierto", "Parqueadero de visitantes", "Bahía de parqueo",
    "Parqueadero para motos", "Bicicletero", "Estación de carga para vehículos eléctricos",
    "Parqueadero para personas con movilidad reducida",
    "Piscina", "Piscina climatizada", "Jacuzzi", "Sauna", "Turco (baño turco)", "Gimnasio",
    "Cancha múltiple", "Cancha de fútbol", "Cancha de baloncesto", "Cancha de squash", "Cancha de tenis",
    "Zona de golf / mini golf", "Sendero para trotar", "Zona de yoga", "Muro de escalada", "Piscina para niños",
    "Salón comunal", "Salón social", "Salón de eventos", "Zona BBQ", "Zona de asados", "Coworking",
    "Sala de juntas", "Salón de juegos", "Zona de cine / cinema", "Terraza rooftop", "Zona lounge",
    "Rooftop bar", "Biblioteca", "Sala de estudio", "Zona kids / ludoteca", "Guardería",
    "Zona infantil", "Parque infantil", "Apto para niños", "Zona de juegos exteriores",
    "Piscina infantil", "Sala de lactancia",
    "Zonas verdes", "Jardines", "Senderos peatonales", "Huerta comunitaria", "Zona de mascotas",
    "Parque canino", "Terraza común", "Plazoleta",
    "Cocina integral", "Cocina abierta / americana", "Cocina cerrada", "Isla de cocina",
    "Barra estilo americano", "Horno", "Lavaplatos incluido", "Nevera incluida", "Estufa incluida",
    "Extractor de olores", "Despensa",
    "Baño auxiliar", "Baño de servicio", "Baño en suite", "Ducha de hidromasaje",
    "Sanitarios de bajo consumo", "Calentador de agua", "Ventana en baño",
    "Walking closet", "Closets", "Estudio / cuarto de estudio", "Cuarto de servicio", "Cuarto útil",
    "Depósito", "Bodega", "Vestier",
    "Pisos en porcelanato", "Pisos en madera", "Pisos en baldosa", "Doble altura",
    "Ventanales de piso a techo", "Vista panorámica", "Buena iluminación natural", "Chimenea",
    "Aire acondicionado", "Calefacción", "Control térmico", "Ventilación cruzada",
    "Insonorización / control de ruido", "Amoblado",
    "Balcón", "Terraza privada", "Patio", "Jardín privado", "Solarium",
    "Zona de lavandería", "Cuarto de lavado", "Patio de ropas",
    "Planta eléctrica", "Shut de basura", "Recolección de basuras", "Wifi en zonas comunes",
    "Administración incluida", "Conserjería", "Servicio de mensajería", "Casa club",
    "Paneles solares", "Energía solar", "Sistema de recolección de aguas lluvias",
    "Certificación LEED / construcción sostenible",
    "Se permiten mascotas", "Se permite fumar", "Apto para arriendo tipo Airbnb",
    "Sala de ventas", "Apartamento modelo", "Entrega inmediata", "Sobre planos",
    "Financiación directa con constructora", "Subsidio de vivienda aplicable",
]


def normalizar_comodidades_llm(anuncios: list[dict]) -> dict[int, list[str]]:
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
- Si dos formas distintas de decir lo mismo aparecen, usa el termino del catalogo mas cercano.
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
            comodidades_validas = [c for c in (item.get("comodidades") or []) if c in catalogo_set]
            resultado[int(item["id"])] = comodidades_validas
        return resultado
    except Exception:
        return {}


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
    if max1 is not None and min2 is not None and max1 < min2:
        return False
    if max2 is not None and min1 is not None and max2 < min1:
        return False
    return True


def _cumple_antiguedad(busqueda: dict, anuncio: dict) -> bool:
    b_min, b_max = busqueda.get("antiguedad_anios_min"), busqueda.get("antiguedad_anios_max")
    if b_min is None and b_max is None:
        return True
    a_min, a_max = anuncio.get("antiguedad_anios_min"), anuncio.get("antiguedad_anios_max")
    if a_min is None and a_max is None:
        return True
    return _rangos_se_solapan(a_min, a_max, b_min, b_max)


def _cumple_comodidades_indispensables(busqueda: dict, anuncio: dict) -> bool:
    indispensables = busqueda.get("comodidades_indispensables") or []
    if not indispensables:
        return True
    normalizadas = anuncio.get("comodidades_normalizadas")
    if normalizadas is None:
        return True
    normalizadas_set = set(normalizadas)
    return all(c in normalizadas_set for c in indispensables)


def _upz_a_upl_norm(nombre: str) -> str:
    clave = nombre.strip().upper()
    upl = UPZ_A_UPL.get(clave, nombre)
    return _sin_tildes(upl.strip().lower())


def _cumple_sectores(busqueda: dict, anuncio: dict) -> bool:
    sectores_pedidos = busqueda.get("sectores") or []
    if not sectores_pedidos:
        return True

    a_sec = anuncio.get("nivel_admin_2")
    if not a_sec:
        return True

    a_sec_norm = _sin_tildes(str(a_sec).strip().lower())
    a_admin1_norm = _upz_a_upl_norm(str(a_sec)) # TODO: Mapeo generico Admin2->Admin1

    for s_item in sectores_pedidos:
        b_norm = _sin_tildes(str(s_item).strip().lower())
        if b_norm in a_sec_norm or a_sec_norm in b_norm or b_norm in a_admin1_norm or a_admin1_norm in b_norm:
            return True
    return False


# Lista canónica de ciudades que NO son Bogotá y se usan para descartar URLs/textos
# que claramente pertenecen a otra ciudad colombiana. Antes existían DOS versiones
# inline con contenidos distintos en _es_url_valida_para_municipios y _cumple_municipios;
# esta constante las unifica.
_CIUDADES_AJENAS = [
    "manizales", "cali", "barranquilla", "bucaramanga", "medellin", "cartagena",
    "pereira", "cucuta", "pasto", "ibague", "neiva", "tunja", "bello",
    "floridablanca", "itagui", "sabaneta", "dosquebradas", "piedecuesta", "armenia",
    "barrancabermeja", "yumbo", "quimbaya", "la-estrella", "villamaria", "girardot",
    "fusagasuga", "ricaurte", "flandes", "sopo", "tocancipa", "facatativa",
    "zipaquira", "chia", "cajica", "madrid", "mosquera", "funza", "la-calera",
    "soacha", "sibate", "tabio", "tenjo", "cota", "gachancipa",
]


def _es_url_valida_para_municipios(url: str, municipios_pedidos: list[str]) -> bool:
    if not municipios_pedidos:
        return True
    url_slug = url.lower()
    m_norms = [_sin_tildes(str(m).strip().lower()).replace(".", "").replace(",", "") for m in municipios_pedidos]

    for c in _CIUDADES_AJENAS:
        # Revisa si la ciudad ajena está presente en la URL como slug o segmento de ruta
        if f"-{c}" in url_slug or f"/{c}" in url_slug or f"{c}-" in url_slug:
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

    ciudades_ajenas_txt = [c.replace("-", "") for c in _CIUDADES_AJENAS]
    if any(c in ubi_txt for c in ciudades_ajenas_txt):
        return False

    return True


def _cumple_area_metros(busqueda: dict, anuncio: dict) -> bool:
    area = anuncio.get("area_metros")
    area_min = busqueda.get("area_metros_min")
    area_max = busqueda.get("area_metros_max")
    if area is None:
        return True
    if area_min is not None and float(area) < float(area_min):
        return False
    if area_max is not None and float(area) > float(area_max):
        return False
    return True


def _cumple_precio(busqueda: dict, anuncio: dict) -> bool:
    precio = anuncio.get("precio_venta")
    p_min = busqueda.get("presupuesto_min") or busqueda.get("precio_min")
    p_max = busqueda.get("presupuesto_max") or busqueda.get("precio_max")
    if precio is None:
        return True
    try:
        p_val = float(precio)
        if p_min is not None and p_val < float(p_min):
            return False
        if p_max is not None and p_val > float(p_max):
            return False
    except (TypeError, ValueError):
        pass
    return True


def _cumple_filtros_duros(busqueda: dict, anuncio: dict) -> bool:
    return (
        _cumple_antiguedad(busqueda, anuncio)
        and _cumple_comodidades_indispensables(busqueda, anuncio)
        and _cumple_precio(busqueda, anuncio)
        and _cumple_sectores(busqueda, anuncio)
        and _cumple_area_metros(busqueda, anuncio)
        and _cumple_precio(busqueda, anuncio)
    )


def filtrar_urls_nuevas(urls: list[str]) -> list[str]:
    urls_unicas = list(dict.fromkeys(urls))
    return [u for u in urls_unicas if db.buscar_anuncio_por_url(u) is None]


def anuncio_sigue_activo(url: str, timeout: int = 6) -> bool:
    try:
        r = requests.head(url, timeout=timeout, allow_redirects=True)
        if r.status_code == 405:
            r_get = requests.get(url, timeout=timeout, stream=True)
            status = r_get.status_code
            r_get.close()
            return status < 400
        return r.status_code < 400
    except requests.RequestException:
        return False


def revalidar_anuncios_existentes(urls: list[str]):
    for url in urls:
        a = db.buscar_anuncio_por_url(url)
        if a is None:
            continue

        if not anuncio_sigue_activo(url):
            db.marcar_inactivo(url)
            continue

        if not a.get("h3_index") and a.get("latitud") and a.get("longitud"):
            try:
                lat = float(a["latitud"])
                lng = float(a["longitud"])
                geo = enriquecer_inmueble(lat, lng)
                actualizaciones = {}
                if geo.get("h3_data"):
                    actualizaciones["h3_data"] = geo["h3_data"]
                if geo.get("nivel_admin_2"):
                    actualizaciones["nivel_admin_2"] = geo["nivel_admin_2"]
                if geo.get("nivel_admin_1"):
                    actualizaciones["nivel_admin_1"] = geo["nivel_admin_1"]
                if geo.get("municipio"):
                    actualizaciones["municipio_geo"] = geo["municipio"]
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
                pass


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
    n = n.replace(",", " ").replace(".", "")
    n = " ".join(n.split())
    if n in ("bogota", "bogota dc", "santafe de bogota", "santa fe de bogota"):
        return "bogota"
    return n.replace(" ", "-")


def _fue_cancelada(busqueda_id: int) -> bool:
    b = db.obtener_busqueda(busqueda_id)
    return b is not None and b.get("status") == "cancelando"


UPL_A_LOCALIDAD_SLUG: dict[str, str] = {
    "arborizadora": "ciudad-bolivar",
    "barrios unidos": "barrios-unidos",
    "bosa": "bosa",
    "bosa central": "bosa",
    "bosa occidental": "bosa",
    "britalia": "suba",
    "centro historico": "santa-fe",
    "cerros orientales": "santa-fe",
    "chapinero": "chapinero",
    "chico lago": "chapinero",
    "cuenca del tunjuelo": "ciudad-bolivar",
    "eden": "bosa",
    "el eden": "bosa",
    "engativa": "engativa",
    "fontibon": "fontibon",
    "kennedy": "kennedy",
    "lucero": "ciudad-bolivar",
    "niza": "suba",
    "patio bonito": "kennedy",
    "porvenir": "bosa",
    "el porvenir": "bosa",
    "puente aranda": "puente-aranda",
    "rafael uribe": "rafael-uribe-uribe",
    "restrepo": "rafael-uribe-uribe",
    "rincon de suba": "suba",
    "salitre": "fontibon",
    "san cristobal": "san-cristobal",
    "suba": "suba",
    "sumapaz": "sumapaz",
    "tabora": "engativa",
    "teusaquillo": "teusaquillo",
    "tibabuyes": "suba",
    "tintal": "kennedy",
    "toberin": "usaquen",
    "torca": "suba",
    "tunjuelito": "tunjuelito",
    "usaquen": "usaquen",
    "usme": "usme",
    "usme - entrenubes": "usme",
}

LOCALIDADES_VALIDAS_BOGOTA = {
    "usaquen", "chapinero", "santa-fe", "san-cristobal", "usme", "tunjuelito",
    "bosa", "kennedy", "fontibon", "engativa", "suba", "barrios-unidos",
    "teusaquillo", "los-martires", "antonio-narino", "puente-aranda",
    "la-candelaria", "rafael-uribe-uribe", "ciudad-bolivar", "sumapaz"
}


def _admin1_slugs_desde_sectores(sectores_pedidos: list[str]) -> list[str]:
    """Obtiene slugs de nivel_admin_1 (ej. localidades) a partir de nombres de nivel_admin_2 (ej. UPZ)."""
    admin2_map = {}
    try:
        from services import spatial_analysis
        admin2_map = spatial_analysis.upz_a_localidad_map() or {}
    except Exception:
        pass

    slugs = set()
    for item in sectores_pedidos:
        item_norm = _sin_tildes(str(item).lower().strip())
        
        # 1. Búsqueda exacta primero
        encontrado = False
        for k, v in admin2_map.items():
            if _sin_tildes(str(k).strip().lower()) == item_norm:
                loc_slug = _sin_tildes(str(v).strip().lower()).replace(" ", "-")
                if loc_slug in LOCALIDADES_VALIDAS_BOGOTA:
                    slugs.add(loc_slug)
                encontrado = True
                break

        # 2. Buscar en UPL_A_LOCALIDAD_SLUG
        if not encontrado:
            loc_slug = UPL_A_LOCALIDAD_SLUG.get(item_norm)
            if loc_slug:
                slugs.add(loc_slug)
            else:
                slugs.add("bogota")

    return list(slugs)


def _filtros_desde_cliente(busqueda: dict, portal: str, cantidad: int, municipio_nombre: str, paginas_limite: int = 7, localidad_override: str | None = None) -> dict:
    tipos = [busqueda["tipo_vivienda"]]
    estado = "usados" if busqueda.get("estado_deseado") == "usado" else "nuevos"
    ciudad = _slugify_municipio(municipio_nombre)
    estratos = busqueda.get("estrato_objetivo") or None
    paginas = min(41, max(1, paginas_limite))

    p_min = busqueda.get("presupuesto_min") or busqueda.get("precio_min")
    p_max = busqueda.get("presupuesto_max") or busqueda.get("precio_max")
    es_bogota = ciudad == "bogota"

    if portal == "fincaraiz":
        if es_bogota:
            loc_slug = localidad_override or ciudad
            ubicacion = f"{loc_slug}/bogota" if loc_slug != "bogota" else "bogota/bogota-dc"
        else:
            ubicacion = ciudad

        return {
            "paginas_a_extraer": paginas,
            "operacion": "venta",
            "tipos_inmueble": tipos,
            "ubicacion": ubicacion,
            "habitaciones": busqueda.get("habitaciones_min"),
            "banos": busqueda.get("banos_min"),
            "extras": busqueda.get("comodidades_deseadas") or None,
            "parqueaderos": busqueda.get("parqueaderos_min"),
            "estado": estado,
            "precio_min": p_min,
            "precio_max": p_max,
            "antiguedad": busqueda.get("antiguedad_max"),
            "estratos": estratos,
        }
    elif portal == "metrocuadrado":
        return {
            "paginas_a_extraer": paginas,
            "operacion": "venta",
            "tipos_inmueble": tipos,
            "ciudad": ciudad,
            "habitaciones_min": busqueda.get("habitaciones_min"),
            "banos_min": busqueda.get("banos_min"),
            "precio_min": p_min,
            "precio_max": p_max,
            "estratos": estratos,
            "incluir_proyectos": False
        }
    else:
        raise ValueError(f"Portal no soportado: {portal}")


def _normalizar_estado(texto: str | None) -> str | None:
    if not texto: return None
    t = _sin_tildes(texto.strip())
    if "nuevo" in t or "sobre plano" in t or "en construccion" in t: return "Nuevo"
    if "usado" in t or "remodelado" in t: return "Usado"
    return texto.strip()


def _normalizar_para_db(detalle: dict, portal: str) -> dict:
    url = detalle.get("URL") or ""
    codigo = detalle.get("Codigo_FincaRaiz") or (url.split("/")[-1] if "/" in url else None)

    ant_text = detalle.get("Antiguedad")
    a_min, a_max = _parsear_antiguedad(ant_text)

    lat = None
    lng = None
    try:
        if detalle.get("Latitud") != "" and detalle.get("Latitud") is not None:
            lat = float(detalle["Latitud"])
        if detalle.get("Longitud") != "" and detalle.get("Longitud") is not None:
            lng = float(detalle["Longitud"])
    except (TypeError, ValueError):
        pass

    return {
        "url": url,
        "portal": portal,
        "codigo_portal": str(codigo) if codigo else None,
        "tipo_inmueble": detalle.get("Tipo_Inmueble"),
        "estado": _normalizar_estado(detalle.get("Estado")),
        "precio_venta": detalle.get("Precio_Venta"),
        "administracion": detalle.get("Administracion"),
        "ubicacion_texto": detalle.get("Ubicacion") or detalle.get("ubicacion_texto"),
        "estrato": detalle.get("Estrato"),
        "area_metros": detalle.get("Area_Metros") or detalle.get("Area_Construida"),
        "habitaciones": detalle.get("Habitaciones"),
        "banos": detalle.get("Banos"),
        "parqueaderos": detalle.get("Parqueaderos"),
        "antiguedad": ant_text,
        "antiguedad_anios_min": a_min,
        "antiguedad_anios_max": a_max,
        "piso_nro": detalle.get("Piso_Nro"),
        "comodidades": detalle.get("Comodidades"),
        "descripcion": detalle.get("Descripcion"),
        "foto_url": detalle.get("Foto_URL"),
        "latitud": lat,
        "longitud": lng,
    }


def buscar_administracion_metrocuadrado(url: str) -> int | None:
    try:
        r = requests.get(url, timeout=5, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return None
        m = re.search(r'["\']mvalotadministracion["\']\s*:\s*["\']?(\d+)["\']?', r.text)
        if m:
            val = int(m.group(1))
            return val if val > 0 else None
        m2 = re.search(r'Administraci(?:ó|o)n\s*[:$]\s*([\d.,]+)', r.text, re.IGNORECASE)
        if m2:
            nums = re.sub(r'[^\d]', '', m2.group(1))
            return int(nums) if nums else None
    except Exception:
        pass
    return None


def procesar_anuncio_nuevo(url: str, sectores_pedidos: list = None, municipios_pedidos: list = None, driver=None) -> int | None:
    if municipios_pedidos and not _es_url_valida_para_municipios(url, municipios_pedidos):
        return None
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
        html = ""

    detalle = extraer_detalle(portal, html, url)

    lat = None
    lng = None
    try:
        lat = float(detalle["Latitud"])
        lng = float(detalle["Longitud"])
    except (TypeError, ValueError, KeyError):
        pass

    ubi_rapida = None
    if lat is not None and lng is not None:
        try:
            ubi_rapida = verificar_ubicacion_rapida(lat, lng)

            if municipios_pedidos:
                a_mpio = ubi_rapida.get("municipio") or ""
                a_norm = _sin_tildes(a_mpio.strip().lower()).replace(".", "").replace(",", " ")
                a_norm = " ".join(a_norm.split())
                pasa_mpio = False
                for nombre in municipios_pedidos:
                    b_norm = _sin_tildes(str(nombre).strip().lower()).replace(".", "").replace(",", " ")
                    b_norm = " ".join(b_norm.split())
                    if b_norm in a_norm or (a_norm and a_norm in b_norm):
                        pasa_mpio = True
                        break
                if not pasa_mpio:
                    return None

            if sectores_pedidos:
                a_sec = ubi_rapida.get("nivel_admin_2") or ""
                if a_sec:
                    a_admin1_norm = _upz_a_upl_norm(str(a_sec))
                    pasa_sec = False
                    for s_item in sectores_pedidos:
                        s_norm = _sin_tildes(str(s_item).strip().lower())
                        if s_norm in _sin_tildes(a_sec.lower()) or _sin_tildes(a_sec.lower()) in s_norm or s_norm in a_admin1_norm or a_admin1_norm in s_norm:
                            pasa_sec = True
                            break
                    if not pasa_sec:
                        return None
        except Exception:
            pass
    else:
        ubicacion_txt = _sin_tildes((detalle.get("Ubicacion") or detalle.get("ubicacion_texto") or "").lower())
        if municipios_pedidos:
            es_bogota = any(_sin_tildes(m.strip().lower()).startswith("bogota") for m in municipios_pedidos)
            if es_bogota:
                palabras_otras_regiones = ["antioquia", "armenia", "quindio", "medellin", "cali", "bello", "barranquilla", "bucaranga", "cartagena", "manizales", "pereira", "villavicencio"]
                if any(p in ubicacion_txt for p in palabras_otras_regiones) and "bogota" not in ubicacion_txt:
                    return None
                if "bogota" not in ubicacion_txt:
                    return None

    geo = {"dist_sitp": None, "dist_tm": None, "dist_ciclo": None, "estrato_promedio_200m": None}
    if lat is not None and lng is not None:
        try:
            geo = enriquecer_inmueble(lat, lng)
        except Exception:
            if ubi_rapida:
                geo["nivel_admin_2"] = ubi_rapida.get("nivel_admin_2")
                geo["nivel_admin_1"] = ubi_rapida.get("nivel_admin_1")
                geo["municipio"] = ubi_rapida.get("municipio")

    h3_index = None
    if lat is not None and lng is not None:
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
    if geo.get("nivel_admin_1"):
        datos_anuncio["nivel_admin_1"] = geo["nivel_admin_1"]
    if geo.get("nivel_admin_2"):
        datos_anuncio["nivel_admin_2"] = geo["nivel_admin_2"]
    if geo.get("municipio"):
        datos_anuncio["municipio_geo"] = geo["municipio"]
    if geo.get("h3_data"):
        datos_anuncio["h3_data"] = geo["h3_data"]
    return db.insertar_anuncio(datos_anuncio)


def ejecutar_busqueda(busqueda: dict, portales: list[str], cantidad: int, municipio_nombre: str, busqueda_id: int, paginas_limite: int = 7) -> list[dict]:
    todas_urls = []
    for portal in portales:
        if _fue_cancelada(busqueda_id):
            db.actualizar_busqueda_log(busqueda_id, "Detención solicitada: finalizando recolección de enlaces...", "info")
            break

        sectores_pedidos = busqueda.get("sectores") or []
        es_bogota = _sin_tildes(municipio_nombre.strip().lower()).startswith("bogota")
        loc_slugs = _admin1_slugs_desde_sectores(sectores_pedidos) if (es_bogota and sectores_pedidos) else []

        urls = []
        if loc_slugs and portal == "fincaraiz":
            cant_por_loc = max(1, cantidad // len(loc_slugs))
            for loc_slug in loc_slugs:
                if _fue_cancelada(busqueda_id):
                    break
                filtros = _filtros_desde_cliente(busqueda, portal, cant_por_loc, municipio_nombre, paginas_limite=paginas_limite, localidad_override=loc_slug)
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

    sectores_pedidos = busqueda.get("sectores") or []
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
            if insertados >= cantidad:
                db.actualizar_busqueda_log(busqueda_id, f"Meta alcanzada ({insertados}/{cantidad} inmuebles insertados). Finalizando recolección de detalles.", "ok")
                break
            prefijo = f"[{i}/{total_nuevos}]"
            url_corta = url.split("/")[-2] if "/" in url else url[-40:]
            db.actualizar_busqueda_log(busqueda_id, f"{prefijo} ⏳ Cargando anuncio: {url_corta}...", "info")
            t_anuncio = time.perf_counter()
            try:
                resultado = procesar_anuncio_nuevo(
                    url,
                    sectores_pedidos=sectores_pedidos or None,
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
                        sec_  = anuncio.get("nivel_admin_2") or "?"
                        tipo  = (anuncio.get("tipo_inmueble") or "Inmueble").title()
                        prec  = anuncio.get("precio_venta")
                        prec_s = f"${prec:,.0f}" if prec else ""
                        h3ok  = "🔵" if anuncio.get("h3_data") else "🟡"
                        detalle = f" — {h3ok} {tipo} en {sec_} {prec_s}"
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
                    f"⚠️ ADVERTENCIA: la búsqueda tiene {len(indispensables)} comodidad(es) indispensable(s) pero la normalización IA está desactivada.",
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
    d_antiguedad = d_comods = d_sectores = d_municipio = d_precio = d_area = 0
    for a in candidatos_activos:
        if not _cumple_antiguedad(busqueda, a):
            d_antiguedad += 1; continue
        if not _cumple_comodidades_indispensables(busqueda, a):
            d_comods += 1; continue
        if not _cumple_sectores(busqueda, a):
            d_sectores += 1; continue
        if not _cumple_municipios(busqueda, a):
            d_municipio += 1; continue
        if not _cumple_precio(busqueda, a):
            d_precio += 1; continue
        if not _cumple_area_metros(busqueda, a):
            d_area += 1; continue
        resultados.append(a)

    razones = []
    if d_antiguedad: razones.append(f"{d_antiguedad} por antigüedad")
    if d_comods:    razones.append(f"{d_comods} por comodidades")
    if d_sectores:  razones.append(f"{d_sectores} por Sector")
    if d_municipio: razones.append(f"{d_municipio} por municipio")
    if d_precio:    razones.append(f"{d_precio} por precio")
    if d_area:      razones.append(f"{d_area} por área")
    if razones:
        db.actualizar_busqueda_log(
            busqueda_id,
            f"{municipio_nombre}: {sum([d_antiguedad, d_comods, d_sectores, d_municipio, d_precio, d_area])} descartados — " + ", ".join(razones),
            "info",
        )
    return resultados


def _distribuir_cantidad(cantidad: int, n: int) -> list[int]:
    if n <= 0:
        return []
    base, resto = divmod(cantidad, n)
    return [base + 1 if i < resto else base for i in range(n)]


def _merge_nuevos(actual: list[dict], nuevos: list[dict]) -> list[dict]:
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
    import random
    n = len(municipios)
    if n == 0:
        return []

    nombres = [m.get("municipio") for m in municipios]
    encontrados_por_municipio: dict[str, list[dict]] = {nombre: [] for nombre in nombres}
    objetivo_acumulado = dict(zip(nombres, _distribuir_cantidad(cantidad, n)))

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

        items_ordenados = list(nombres)
        random.shuffle(items_ordenados)
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
    s = int(segundos)
    if s < 60:
        return f"{segundos:.1f}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"


def ejecutar_busqueda_completa(busqueda_id: int, top: int = 5):
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
        db.actualizar_busqueda_log(busqueda_id, f"Error fatal: {e} | {tb[-500:]}", "error")
        db.finalizar_busqueda(busqueda_id, "error")
