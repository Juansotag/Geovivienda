import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()
import db

with db.get_cursor() as cur:
    cur.execute("SELECT id, status, tipo_vivienda, presupuesto_max, portales, log FROM busquedas ORDER BY id")
    rows = cur.fetchall()
    for b in rows:
        log = b['log'] if isinstance(b['log'], list) else json.loads(b['log'] or '[]')
        print(f"\n=== Busqueda [{b['id']}] {b['tipo_vivienda']} max={b['presupuesto_max']:,.0f} | STATUS: {b['status']} ===")
        if log:
            for e in log[-20:]:  # ultimos 20 eventos
                print(f"  [{e.get('level','?')}] {e.get('msg','')}")
        else:
            print("  (sin logs)")
