"""Pruebas unitarias en memoria para funciones auxiliares de busqueda.py:
- _parsear_antiguedad
- _sin_tildes
- _upz_a_upl_norm
- _es_url_valida_para_municipios
- _distribuir_cantidad
- _normalizar_estado
- _normalizar_para_db
"""
from services import busqueda


def test_sin_tildes():
    assert busqueda._sin_tildes("Bogotá, D.C. Ñandú") == "bogota, d.c. nandu"


def test_parsear_antiguedad_menor_a():
    min_a, max_a = busqueda._parsear_antiguedad("menor a 1 año")
    assert min_a == 0
    assert max_a == 1


def test_parsear_antiguedad_mas_de():
    min_a, max_a = busqueda._parsear_antiguedad("más de 30 años")
    assert min_a == 31
    assert max_a is None


def test_parsear_antiguedad_rango_entre():
    min_a, max_a = busqueda._parsear_antiguedad("Entre 5 y 10 años")
    assert min_a == 5
    assert max_a == 10


def test_parsear_antiguedad_rango_a():
    min_a, max_a = busqueda._parsear_antiguedad("9 a 15 años")
    assert min_a == 9
    assert max_a == 15


def test_parsear_antiguedad_invalida_o_vacia():
    assert busqueda._parsear_antiguedad(None) == (None, None)
    assert busqueda._parsear_antiguedad("") == (None, None)


def test_es_url_valida_para_municipios_filtra_ciudades_ajenas():
    # URL de Medellín no debe pasar si el usuario pidió Bogotá
    url_medellin = "https://www.fincaraiz.com.co/apartamento-en-venta/medellin/el-poblado/123456"
    assert not busqueda._es_url_valida_para_municipios(url_medellin, ["Bogotá, D.C."])

    # URL de Medellín sí debe pasar si Medellín fue pedido
    assert busqueda._es_url_valida_para_municipios(url_medellin, ["Medellín"])


def test_distribuir_cantidad():
    # 10 inmuebles entre 3 municipios: [4, 3, 3]
    res = busqueda._distribuir_cantidad(10, 3)
    assert sum(res) == 10
    assert res == [4, 3, 3]


def test_normalizar_estado():
    assert busqueda._normalizar_estado("En construccion / Sobre planos") == "Nuevo"
    assert busqueda._normalizar_estado("Remodelado / Usado") == "Usado"
    assert busqueda._normalizar_estado(None) is None


def test_normalizar_para_db():
    detalle_raw = {
        "URL": "https://www.fincaraiz.com.co/apartamento-en-venta/bogota/chapinero/100",
        "Codigo_FincaRaiz": "100",
        "Tipo_Inmueble": "Apartamento",
        "Estado": "Usado",
        "Precio_Venta": 450000000,
        "Latitud": "4.6486",
        "Longitud": "-74.0628",
        "Antiguedad": "1 a 8 años",
    }
    norm = busqueda._normalizar_para_db(detalle_raw, "fincaraiz")
    assert norm["portal"] == "fincaraiz"
    assert norm["precio_venta"] == 450000000
    assert norm["latitud"] == 4.6486
    assert norm["longitud"] == -74.0628
    assert norm["antiguedad"] == "1 a 8 años"
    assert norm["antiguedad_anios_min"] == 1
    assert norm["antiguedad_anios_max"] == 8


def test_cumple_precio():
    busqueda_obj = {"presupuesto_min": 200000000, "presupuesto_max": 400000000}
    assert busqueda._cumple_precio(busqueda_obj, {"precio_venta": 300000000})
    assert not busqueda._cumple_precio(busqueda_obj, {"precio_venta": 150000000})
    assert not busqueda._cumple_precio(busqueda_obj, {"precio_venta": 500000000})


def test_filtros_desde_cliente_extrae_presupuesto():
    b_dict = {
        "tipo_vivienda": "apartamento",
        "estado_deseado": "usado",
        "presupuesto_min": 200000000,
        "presupuesto_max": 380000000,
        "habitaciones_min": 2,
        "banos_min": 2,
    }
    filtros = busqueda._filtros_desde_cliente(b_dict, "fincaraiz", 10, "Bogotá, D.C.")
    assert filtros["precio_min"] == 200000000
    assert filtros["precio_max"] == 380000000


def test_localidades_slugs_desde_upzs():
    upzs = ["Porvenir", "Edén", "Bosa Central", "Niza", "Teusaquillo"]
    locs = busqueda._localidades_slugs_desde_upzs(upzs)
    assert locs == ["bosa", "suba", "teusaquillo"]


def test_filtros_desde_cliente_localidad_override():
    b_dict = {"tipo_vivienda": "apartamento", "estado_deseado": "usado"}
    filtros = busqueda._filtros_desde_cliente(b_dict, "fincaraiz", 10, "Bogotá, D.C.", localidad_override="bosa")
    assert filtros["ubicacion"] == "bosa/bogota"

