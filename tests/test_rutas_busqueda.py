"""Pruebas de integracion contra la base real de Railway (no hay Postgres
local) via Flask test_client. No lanzan Selenium ni llaman a Claude - solo
verifican render de formularios y persistencia de criterios. Usan los
fixtures cliente_temporal/crear_busqueda de conftest.py, que limpian todo
al terminar."""
import app as app_module


def test_form_nueva_muestra_checkboxes_upz_con_localidad(client, cliente_temporal):
    r = client.get(f"/busquedas/nueva?cliente_id={cliente_temporal}")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'name="upz"' in html
    assert "container-bogota-sectores" in html
    # al menos una opcion con el formato "Nombre (Localidad)"
    assert "(" in html and ")" in html


def test_crear_busqueda_con_upz_de_localidades_distintas(client, cliente_temporal):
    opciones = app_module._upz_opciones()
    por_localidad = {}
    for nombre, loc in opciones:
        por_localidad.setdefault(loc, nombre)
        if len(por_localidad) >= 2:
            break
    elegidas = list(por_localidad.values())
    assert len(elegidas) == 2

    form = {
        "municipios_json": '[{"municipio": "Bogotá, D.C.", "departamento": "Bogotá, D.C."}]',
        "tipo_vivienda": "apartamento",
        "estado_deseado": "cualquiera",
        "zona_deseada": "urbana",
        "habitaciones_min": "1",
        "banos_min": "1",
        "presupuesto_min": "100000000",
        "presupuesto_max": "300000000",
        "pregunta_abierta": "",
        "cantidad": "10",
        "upz": elegidas,
    }
    r = client.post(f"/busquedas/nueva?cliente_id={cliente_temporal}", data=form)
    assert r.status_code in (302, 200)

    import db
    busquedas = db.obtener_busquedas_cliente(cliente_temporal)
    assert busquedas, "la busqueda no se creo"
    nueva = max(busquedas, key=lambda b: b["id"])
    try:
        assert set(nueva["upz"]) == set(elegidas)
        assert "localidad" not in nueva
    finally:
        with db.get_cursor() as cur:
            cur.execute("DELETE FROM busquedas WHERE id = %s", (nueva["id"],))


def test_editar_busqueda_premarca_upz_seleccionadas(client, crear_busqueda):
    bid = crear_busqueda(upz=["Chapinero", "Usaquén"])
    r = client.get(f"/busquedas/{bid}/editar")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert 'value="Chapinero" onchange="toggleCheckboxClass(this)" checked' in html
    assert 'value="Usaquén" onchange="toggleCheckboxClass(this)" checked' in html


def test_boton_reintentar_aparece_para_busqueda_fallida(client, crear_busqueda):
    bid = crear_busqueda(status="error")

    r_lista = client.get("/busquedas")
    assert "Reintentar" in r_lista.get_data(as_text=True)

    r_resultados = client.get(f"/clientes/{_cliente_de(crear_busqueda, bid)}/resultados?busqueda_id={bid}")
    html = r_resultados.get_data(as_text=True)
    assert "Reintentar búsqueda" in html
    assert "falló durante su ejecución" in html


def test_boton_reintentar_aparece_para_busqueda_cancelada(client, crear_busqueda):
    bid = crear_busqueda(status="cancelada")
    r_resultados = client.get(f"/clientes/{_cliente_de(crear_busqueda, bid)}/resultados?busqueda_id={bid}")
    assert "Reintentar búsqueda" in r_resultados.get_data(as_text=True)


def test_boton_reintentar_no_aparece_para_busqueda_pendiente(client, crear_busqueda):
    bid = crear_busqueda(status="pendiente")
    r_lista = client.get("/busquedas")
    html = r_lista.get_data(as_text=True)
    # el boton "Lanzar" si debe estar, "Reintentar" no aplica aun
    assert "Lanzar" in html


def _cliente_de(crear_busqueda_fixture, busqueda_id):
    import db
    return db.obtener_busqueda(busqueda_id)["cliente_id"]
