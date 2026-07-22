"""
Parcha todos los anuncios que tienen comodidades_normalizadas = NULL
usando la columna parqueaderos directamente (sin LLM).
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv; load_dotenv()
import db

print("Parcheando comodidades_normalizadas NULL con fallback estructural...")

with db.get_cursor() as cur:
    cur.execute("""
        SELECT id, parqueaderos, comodidades
        FROM anuncios
        WHERE comodidades_normalizadas IS NULL
    """)
    rows = cur.fetchall()

print(f"Anuncios con comodidades_normalizadas = NULL: {len(rows)}")

actualizados = 0
for r in rows:
    lista = []
    # Fallback estructural: parqueaderos
    if (r['parqueaderos'] or 0) > 0:
        lista.append("Parqueadero")
    # Guardar aunque sea lista vacía para que ya no sea NULL
    db.actualizar_anuncio(r['id'], {"comodidades_normalizadas": lista})
    actualizados += 1

print(f"Actualizados: {actualizados}")
print()

# Verificar resultado
with db.get_cursor() as cur:
    cur.execute("""
        SELECT COUNT(*) as n FROM anuncios WHERE comodidades_normalizadas IS NULL
    """)
    restantes = cur.fetchone()['n']
    print(f"Anuncios aún con NULL: {restantes}")

    cur.execute("""
        SELECT COUNT(*) as n FROM anuncios 
        WHERE comodidades_normalizadas IS NOT NULL
          AND comodidades_normalizadas::jsonb @> '["Parqueadero"]'::jsonb
    """)
    con_parq = cur.fetchone()['n']
    print(f"Anuncios con Parqueadero normalizado: {con_parq}")

    cur.execute("SELECT COUNT(*) as n FROM anuncios WHERE (parqueaderos or 0) > 0")
    total_parq = cur.fetchone()['n']
    print(f"Anuncios con columna parqueaderos > 0: {total_parq}")
