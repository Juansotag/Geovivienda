import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import app as app_module
import db


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    app_module.app.config["PROPAGATE_EXCEPTIONS"] = True
    return app_module.app.test_client()


@pytest.fixture
def cliente_temporal():
    """Crea un cliente descartable en la base real de Railway (no hay
    Postgres local) y lo borra al terminar el test, sin importar si el
    test paso o fallo."""
    cliente_id = db.insertar_cliente({
        "nombre": "Cliente de Prueba (pytest)",
        "pais_residencia": "España",
        "ciudad_residencia": "Madrid",
        "tipo_identificacion": "CC",
        "numero_identificacion": "0000000000",
        "ingreso_mensual": 5000000,
        "ingreso_moneda": "COP",
        "ingreso_mensual_cop": 5000000,
        "ahorro_mensual": 1000000,
        "ahorro_mensual_cop": 1000000,
    })
    yield cliente_id
    db.eliminar_cliente(cliente_id)


@pytest.fixture
def crear_busqueda(cliente_temporal):
    """Factory fixture: llamarla con overrides puntuales para crear una
    busqueda descartable. Borra todas las creadas al terminar el test."""
    creadas = []

    def _crear(**overrides):
        datos = {
            "cliente_id": cliente_temporal,
            "status": "pendiente",
            "log": [],
            "portales": ["fincaraiz", "metrocuadrado"],
            "cantidad_solicitada": 10,
            "cantidad_exacta": False,
            "municipios": [{"municipio": "Bogotá, D.C.", "departamento": "Bogotá, D.C."}],
            "tipo_vivienda": "apartamento",
            "estado_deseado": "cualquiera",
            "antiguedad_anios_min": None,
            "antiguedad_anios_max": None,
            "zona_deseada": "urbana",
            "habitaciones_min": 1,
            "habitaciones_exactas": False,
            "banos_min": 1,
            "banos_exactos": False,
            "estrato_objetivo": [3],
            "presupuesto_min": 100000000,
            "presupuesto_max": 300000000,
            "uso_previsto": [],
            "comodidades_relevantes": [],
            "comodidades_indispensables": [],
            "upz": [],
            "pregunta_abierta": "",
        }
        datos.update(overrides)
        busqueda_id = db.crear_busqueda(datos)
        creadas.append(busqueda_id)
        return busqueda_id

    yield _crear

    for bid in creadas:
        with db.get_cursor() as cur:
            cur.execute("DELETE FROM busquedas WHERE id = %s", (bid,))
