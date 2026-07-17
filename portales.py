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
