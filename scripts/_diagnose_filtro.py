import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()
import db

with db.get_cursor() as cur:
    cur.execute("""
        SELECT id, comodidades, comodidades_normalizadas, parqueaderos
        FROM anuncios
        WHERE tipo_inmueble ILIKE '%casa%'
        ORDER BY id DESC
        LIMIT 5
    """)
    rows = cur.fetchall()

for r in rows:
    cn = r['comodidades_normalizadas']
    if cn and isinstance(cn, str):
        try:
            cn = json.loads(cn)
        except:
            pass
    
    raw_text = str(r['comodidades']) if r['comodidades'] else ""
    
    has_parq_raw = 'parquea' in raw_text.lower() or 'garaje' in raw_text.lower() or 'garage' in raw_text.lower()
    has_parq_norm = any('parque' in str(c).lower() for c in (cn if isinstance(cn, list) else []))
    
    print(f"ID={r['id']} parqueaderos={r['parqueaderos']}")
    print(f"  COMODIDADES RAW ({type(r['comodidades']).__name__}): {raw_text[:150]}")
    print(f"  NORMALIZADAS: {cn}")
    if has_parq_raw and not has_parq_norm:
        print(f"  *** BUG: parqueadero en raw texto pero no en normalizadas ***")
    elif r['parqueaderos'] and int(r['parqueaderos']) > 0 and not has_parq_norm:
        print(f"  *** BUG: columna parqueaderos={r['parqueaderos']} pero no normalizado ***")
    else:
        print(f"  parq_raw={has_parq_raw} parq_norm={has_parq_norm} -> {'OK' if not (has_parq_raw and not has_parq_norm) else 'MISMATCH'}")
    print()
