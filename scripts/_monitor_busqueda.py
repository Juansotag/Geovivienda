import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()
import db

# Monitorear en tiempo real la busqueda en curso
BUSQUEDA_ID = 3
seen = 0

print(f"Monitoreando busqueda {BUSQUEDA_ID} en tiempo real (Ctrl+C para salir)...\n")
while True:
    with db.get_cursor() as cur:
        cur.execute("SELECT id, status, log FROM busquedas WHERE id = %s", (BUSQUEDA_ID,))
        b = cur.fetchone()
        cur.execute("SELECT COUNT(*) as n FROM anuncios")
        n_anuncios = cur.fetchone()['n']

    if not b:
        print("Busqueda no encontrada")
        break

    log = b['log'] if isinstance(b['log'], list) else json.loads(b['log'] or '[]')
    nuevos = log[seen:]
    if nuevos:
        for e in nuevos:
            print(f"  [{e.get('level','?')}] {e.get('msg','')}")
        seen = len(log)

    print(f"  --- status={b['status']} | anuncios_en_db={n_anuncios} | log_entries={len(log)} ---")

    if b['status'] in ('done', 'error'):
        print(f"\n=== BUSQUEDA TERMINADA: {b['status']} ===")
        break

    time.sleep(10)
