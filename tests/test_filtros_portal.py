"""Pruebas de construccion de filtros/URL por portal. Todo en memoria, sin
red - construir_url_fincaraiz solo arma un string, no visita el sitio."""
import busqueda
from extractor_links import construir_url_fincaraiz

CRITERIOS_BASE = {
    "tipo_vivienda": "casa",
    "estado_deseado": "usado",
    "estrato_objetivo": [5, 6],
    "presupuesto_min": 200_000_000,
    "presupuesto_max": 800_000_000,
    "habitaciones_min": 2,
    "banos_min": 2,
}


def test_fincaraiz_no_recibe_habitaciones_ni_banos():
    """Regresion: FincaRaiz trata /N-habitaciones/N-banos como coincidencia
    EXACTA, no como minimo - confirmado en vivo (busqueda #14, casa
    estrato 5-6 200-800M: 0 resultados con esos segmentos, 79 sin ellos).
    Por eso _filtros_desde_cliente no debe pasarlos para este portal."""
    filtros = busqueda._filtros_desde_cliente(CRITERIOS_BASE, "fincaraiz", 10, "Bogotá, D.C.")
    assert "habitaciones" not in filtros
    assert "banos" not in filtros


def test_metrocuadrado_si_recibe_habitaciones_min_y_banos_min():
    """Metrocuadrado si soporta minimo real via su propio parametro, a
    diferencia de FincaRaiz - no se le debe quitar."""
    filtros = busqueda._filtros_desde_cliente(CRITERIOS_BASE, "metrocuadrado", 10, "Bogotá, D.C.")
    assert filtros["habitaciones_min"] == 2
    assert filtros["banos_min"] == 2


def test_fincaraiz_ubicacion_bogota_usa_sufijo_dc():
    filtros = busqueda._filtros_desde_cliente(CRITERIOS_BASE, "fincaraiz", 10, "Bogotá, D.C.")
    assert filtros["ubicacion"] == "bogota/bogota-dc"


def test_construir_url_fincaraiz_sin_habitaciones_banos_no_aparecen_en_path():
    url = construir_url_fincaraiz(
        operacion="venta", tipos_inmueble=["casa"], ubicacion="bogota/bogota-dc",
        estado="usados", precio_min=200_000_000, precio_max=800_000_000, estratos=[5, 6],
    )
    assert "habitaciones" not in url
    assert "banos" not in url
    assert url == (
        "https://www.fincaraiz.com.co/venta/casas/bogota/bogota-dc/usados"
        "/desde-200000000/hasta-800000000?IDmoneda=4&stratum[]=5&stratum[]=6"
    )


def test_construir_url_fincaraiz_con_habitaciones_banos_si_aparecen_en_path():
    """Si en el futuro se decide pasarlos a proposito para otro portal o
    caso de uso, confirma que siguen siendo un simple segmento de ruta."""
    url = construir_url_fincaraiz(
        operacion="venta", tipos_inmueble=["apartamento"], ubicacion="bogota/bogota-dc",
        habitaciones=3, banos=2,
    )
    assert "/3-habitaciones/2-banos" in url
