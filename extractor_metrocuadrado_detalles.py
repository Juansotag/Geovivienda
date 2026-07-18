import re

from extractor_metrocuadrado_links import _CACHE

# Modulo de funciones para extraer detalles de Metrocuadrado.
#
# No visita la ficha individual: el registro completo ya quedo cacheado por
# extractor_metrocuadrado_links.py al momento de la busqueda (ver ese modulo
# para el porque). html_source se acepta solo para mantener la misma firma
# que extraer_detalles_inmueble() de FincaRaiz y poder usarse detras de la
# interfaz comun (portales.py).
#
# Campos de FincaRaiz sin equivalente confirmado en Metrocuadrado:
# Administracion (cuota mensual) y Cantidad_Pisos (total del edificio) -
# ninguno de los dos aparece en el JSON de busqueda para ningun registro
# revisado. Quedan en None a proposito, no es un bug.


def _to_int(valor):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return None


def _valor_featured(featured, clave):
    for item in featured or []:
        k, _, v = item.strip().partition(":")
        if k == clave:
            return v
    return None


def _humanizar_clave(clave: str) -> str:
    # separa camelCase: "cercaAGimnasio" -> "cerca a gimnasio"
    palabras = re.sub(r"(?<!^)(?=[A-Z])", " ", clave).lower()
    return re.sub(r"\s+", " ", palabras).strip()


def _comodidades_legibles(featured) -> str:
    items = []
    for entry in featured or []:
        clave, _, valor = entry.strip().partition(":")
        if valor.strip() == "S":
            items.append(_humanizar_clave(clave))
    return ", ".join(items)


def extraer_detalles_inmueble(html_source: str = "", url_referencia: str = "") -> dict:
    r = _CACHE.get(url_referencia)

    detalles = {
        "URL": url_referencia,
        "Precio_Venta": None,
        "Administracion": None,
        "Habitaciones": None,
        "Banos": None,
        "Area_Metros": None,
        "Ubicacion": None,
        "Tipo_Inmueble": None,
        "Estado": None,
        "Antiguedad": None,
        "Parqueaderos": None,
        "Area_Construida": None,
        "Area_Privada": None,
        "Estrato": None,
        "Piso_Nro": None,
        "Cantidad_Pisos": None,
        "Comodidades": "",
        "Descripcion": None,
        "Codigo_FincaRaiz": None,
        "Foto_URL": None,
        "Latitud": "",
        "Longitud": "",
    }

    if r is None:
        print(f"Aviso: {url_referencia} no estaba en cache de Metrocuadrado (¿se llamo sin pasar por extraer_links_metrocuadrado?).")
        return detalles

    featured = r.get("featured") or []
    ciudad = (r.get("mciudad") or {}).get("nombre", "")
    barrio = r.get("mnombrecomunbarrio") or r.get("mbarrio") or ""
    ubicacion = ", ".join(p for p in [barrio, ciudad] if p)
    loc = r.get("localizacion") or {}

    # Patron de URL confirmado: multimedia.metrocuadrado.com/{codigo}/{id_galeria}_p.jpg
    codigo = r.get("midinmueble")
    galeria = r.get("mgaleriainmueble") or []
    primera_foto = galeria[0] if galeria else (r.get("data") or {}).get("mprimerafotoinmueble")
    foto_url = f"https://multimedia.metrocuadrado.com/{codigo}/{primera_foto}_p.jpg" if codigo and primera_foto else None

    detalles.update({
        "Precio_Venta": r.get("mvalorventa"),
        "Habitaciones": _to_int(r.get("mnrocuartos")),
        "Banos": _to_int(r.get("mnrobanos")),
        "Area_Metros": r.get("marea"),
        "Ubicacion": ubicacion,
        "Tipo_Inmueble": (r.get("mtipoinmueble") or {}).get("nombre"),
        "Estado": r.get("mestadoinmueble"),
        "Antiguedad": _valor_featured(featured, "tiempoConstruido"),
        "Parqueaderos": _to_int(r.get("mnrogarajes")),
        "Area_Construida": r.get("mareac"),
        "Area_Privada": r.get("areaprivada") or r.get("areaPrivada"),
        "Estrato": r.get("estrato"),
        "Piso_Nro": _to_int(_valor_featured(featured, "nroPiso")),
        "Comodidades": _comodidades_legibles(featured),
        "Descripcion": r.get("comment"),
        "Codigo_FincaRaiz": r.get("midinmueble"),
        "Foto_URL": foto_url,
        "Latitud": loc.get("lat", ""),
        "Longitud": loc.get("lon", ""),
    })

    return detalles
