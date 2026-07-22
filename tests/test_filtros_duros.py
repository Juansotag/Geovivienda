"""Pruebas de los filtros duros (_cumple_X) en busqueda.py. Todas usan
diccionarios en memoria - ningun caso aqui debe tocar la base de datos ni
la red (si un anuncio no trae 'upz'/'municipio_geo' precalculado y tampoco
trae lat/lng, _cumple_upz/_cumple_municipios devuelven True sin intentar
geolocalizar, que es justo el comportamiento fail-open que se prueba)."""
from services import busqueda


def test_cumple_antiguedad_sin_restriccion():
    b = {"antiguedad_anios_min": None, "antiguedad_anios_max": None}
    assert busqueda._cumple_antiguedad(b, {"antiguedad_anios_min": 20, "antiguedad_anios_max": 30})


def test_cumple_antiguedad_dentro_del_rango():
    b = {"antiguedad_anios_min": 0, "antiguedad_anios_max": 10}
    a = {"antiguedad_anios_min": 1, "antiguedad_anios_max": 8}
    assert busqueda._cumple_antiguedad(b, a)


def test_cumple_antiguedad_fuera_del_rango():
    b = {"antiguedad_anios_min": 0, "antiguedad_anios_max": 5}
    a = {"antiguedad_anios_min": 16, "antiguedad_anios_max": 30}
    assert not busqueda._cumple_antiguedad(b, a)


def test_cumple_comodidades_indispensables_vacio_siempre_pasa():
    b = {"comodidades_indispensables": []}
    assert busqueda._cumple_comodidades_indispensables(b, {"comodidades_normalizadas": []})


def test_cumple_comodidades_indispensables_tiene_todas():
    b = {"comodidades_indispensables": ["Ascensor", "Piscina"]}
    a = {"comodidades_normalizadas": ["Ascensor", "Piscina", "Balcón"]}
    assert busqueda._cumple_comodidades_indispensables(b, a)


def test_cumple_comodidades_indispensables_falta_una():
    b = {"comodidades_indispensables": ["Ascensor", "Piscina"]}
    a = {"comodidades_normalizadas": ["Ascensor"]}
    assert not busqueda._cumple_comodidades_indispensables(b, a)


def test_cumple_upz_sin_criterio_siempre_pasa():
    assert busqueda._cumple_upz({"upz": []}, {"id": 1, "upz": None})


def test_cumple_upz_coincide():
    b = {"upz": ["Chapinero", "Usaquén"]}
    assert busqueda._cumple_upz(b, {"id": 1, "upz": "Chapinero"})


def test_cumple_upz_no_coincide():
    b = {"upz": ["Chapinero", "Usaquén"]}
    assert not busqueda._cumple_upz(b, {"id": 1, "upz": "Bosa"})


def test_cumple_upz_sin_dato_no_descarta():
    """Fail-open: sin upz precalculado y sin lat/lng no se intenta
    geolocalizar (evita tocar red/geopandas en una prueba unitaria) y el
    anuncio no se descarta."""
    b = {"upz": ["Chapinero"]}
    a = {"id": 1, "upz": None, "latitud": None, "longitud": None}
    assert busqueda._cumple_upz(b, a)


def test_cumple_municipios_coincide():
    b = {"municipios": [{"municipio": "Bogotá, D.C."}]}
    assert busqueda._cumple_municipios(b, {"id": 1, "municipio_geo": "Bogotá, D.C."})


def test_cumple_municipios_no_coincide():
    b = {"municipios": [{"municipio": "Bogotá, D.C."}]}
    assert not busqueda._cumple_municipios(b, {"id": 1, "municipio_geo": "Chía"})


def test_cumple_filtros_duros_combina_todos():
    b = {
        "antiguedad_anios_min": None, "antiguedad_anios_max": None,
        "comodidades_indispensables": ["Ascensor"],
        "upz": ["Chapinero"],
        "municipios": [{"municipio": "Bogotá, D.C."}],
    }
    a_ok = {
        "id": 1, "antiguedad_anios_min": 2, "antiguedad_anios_max": 8,
        "comodidades_normalizadas": ["Ascensor", "Balcón"],
        "upz": "Chapinero", "municipio_geo": "Bogotá, D.C.",
    }
    assert busqueda._cumple_filtros_duros(b, a_ok)

    a_upz_ajena = dict(a_ok, upz="Bosa")
    assert not busqueda._cumple_filtros_duros(b, a_upz_ajena)

    a_sin_comodidad = dict(a_ok, comodidades_normalizadas=[])
    assert not busqueda._cumple_filtros_duros(b, a_sin_comodidad)
