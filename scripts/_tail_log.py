import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()
import db

with db.get_cursor() as cur:
    cur.execute("SELECT log FROM busquedas WHERE id = 3")
    log = cur.fetchone()['log']
    if isinstance(log, str):
        log = json.loads(log or '[]')

print(f"Total entradas en log: {len(log)}\n")
print("=== ULTIMAS 15 ENTRADAS (las más recientes del nuevo run) ===")
for e in log[-15:]:
    print(f"  [{e.get('level','?')}] {e.get('msg','')}")
