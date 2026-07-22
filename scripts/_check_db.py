import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
import db

with db.get_cursor() as cur:
    cur.execute("SELECT COUNT(*) as n FROM anuncios")
    print(f"anuncios:           {cur.fetchone()['n']}")
    cur.execute("SELECT COUNT(*) as n FROM resultados_busqueda")
    print(f"resultados:         {cur.fetchone()['n']}")
    cur.execute("SELECT COUNT(*) as n FROM reportes")
    print(f"reportes:           {cur.fetchone()['n']}")
    cur.execute("SELECT id, nombre FROM clientes ORDER BY id")
    clientes = cur.fetchall()
    print(f"\nclientes ({len(clientes)}):")
    for c in clientes:
        print(f"  [{c['id']}] {c['nombre']}")
    cur.execute("SELECT id, cliente_id, status, tipo_vivienda, presupuesto_max, top_n FROM busquedas ORDER BY id")
    busquedas = cur.fetchall()
    print(f"\nbusquedas ({len(busquedas)}):")
    for b in busquedas:
        print(f"  [{b['id']}] cliente={b['cliente_id']}  {b['tipo_vivienda']}  max={b['presupuesto_max']:,.0f}  top_n={b['top_n']}  status={b['status']}")
