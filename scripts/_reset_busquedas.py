import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()
import db, json

with db.get_cursor() as cur:
    cur.execute("UPDATE busquedas SET status = 'pendiente', log = '[]'::jsonb WHERE status IN ('running', 'error')")
    print("Busquedas reseteadas")
    cur.execute("SELECT id, status FROM busquedas ORDER BY id")
    for r in cur.fetchall():
        print(f"  [{r['id']}] {r['status']}")
