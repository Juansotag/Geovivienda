import json
import pytest
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_api_h3_geojson_returns_ok(client):
    res = client.get("/api/bogota/h3/geojson")
    assert res.status_code == 200
    data = json.loads(res.data)
    assert data.get("type") == "FeatureCollection"
    assert len(data.get("features", [])) > 0


def test_cliente_nuevo_con_nacionalidad_y_permiso(client):
    res = client.post(
        "/clientes/nuevo",
        data={
            "nombre": "Test Cliente Fase 2",
            "pais_residencia": "España",
            "ciudad_residencia": "Madrid",
            "nacionalidad": "Colombia",
            "anios_en_pais": "4",
            "tipo_permiso_residencia": "Residente Permanente",
            "tipo_identificacion": "Cédula de Extranjería",
            "numero_identificacion": "999888777",
            "ingreso_mensual": "3000",
            "ingreso_moneda": "EUR",
            "ahorro_mensual": "500",
        },
        follow_redirects=True,
    )
    assert res.status_code == 200
    assert b"Test Cliente Fase 2" in res.data
    assert b"Residente Permanente" in res.data
