"""Fixea el estado de la DB post-seed:
1. Resetea busquedas 'running' a 'pendiente'
2. Crea la busqueda 4 que faltó (Hans Müller - plan B apto lujo)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
import db

# 1. Resetear running -> pendiente
with db.get_cursor() as cur:
    cur.execute("UPDATE busquedas SET status = 'pendiente', log = '[]' WHERE status IN ('running', 'error')")
    print(f"Busquedas reseteadas a 'pendiente'")

# 2. Verificar si falta la busqueda 4 (busqueda 2B de Hans)
with db.get_cursor() as cur:
    cur.execute("SELECT COUNT(*) as n FROM busquedas WHERE cliente_id = 2")
    count_hans = cur.fetchone()['n']

if count_hans < 2:
    db.crear_busqueda({
        "cliente_id": 2,
        "portales": ["metrocuadrado"],
        "cantidad_solicitada": 20,
        "cantidad_exacta": False,
        "top_n": 5,
        "status": "pendiente",
        "log": [],
        "municipios": [{"departamento": "Cundinamarca", "municipio": "Bogota D.C.", "codigo": "11001"}],
        "tipo_vivienda": "apartamento",
        "estado_deseado": "nuevo",
        "antiguedad_anios_min": None,
        "antiguedad_anios_max": 8,
        "zona_deseada": "",
        "habitaciones_min": 4,
        "habitaciones_exactas": False,
        "banos_min": 3,
        "banos_exactos": False,
        "estrato_objetivo": [6],
        "presupuesto_min": 1_000_000_000,
        "presupuesto_max": 2_000_000_000,
        "uso_previsto": ["vivienda propia"],
        "comodidades_relevantes": ["Piscina", "Gimnasio", "Zonas verdes", "Salón comunal", "Ascensor"],
        "comodidades_indispensables": ["Ascensor", "Vigilancia 24 horas"],
        "upz": ["Chicó Lago", "El Batán"],
        "pregunta_abierta": "Plan B: si no encontramos casa con jardín, buscamos un apartamento grande de lujo en Chicó o Country Club. Mínimo 4 habitaciones, 3 baños, con áreas comunes de primera (piscina, gimnasio, salón). Estrato 6. Que el edificio sea moderno y seguro. Presupuesto amplio.",
    })
    print("Busqueda 2B de Hans Müller creada")
else:
    print(f"Hans ya tiene {count_hans} busquedas, OK")

# Estado final
import sys
with db.get_cursor() as cur:
    cur.execute("SELECT id, cliente_id, status, tipo_vivienda, presupuesto_max, top_n FROM busquedas ORDER BY id")
    busquedas = cur.fetchall()
    print(f"\nEstado final ({len(busquedas)} busquedas):")
    for b in busquedas:
        print(f"  [{b['id']}] cliente={b['cliente_id']}  {b['tipo_vivienda']}  max={b['presupuesto_max']:,.0f}  top_n={b['top_n']}  status={b['status']}")
