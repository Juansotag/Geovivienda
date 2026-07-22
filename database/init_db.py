import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]


def _aplicar_sql(cur, archivo: str):
    """Ejecuta un archivo SQL contra la conexion activa."""
    with open(archivo, encoding="utf-8") as f:
        sql = f.read()
    if sql.strip():
        cur.execute(sql)
    print(f"  OK: {archivo}")


def main():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            # 1. Schema base: CREATE TABLE IF NOT EXISTS (estado final de cada tabla)
            _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
            _aplicar_sql(cur, os.path.join(_BASE_DIR, "schema.sql"))
            # 2. Migraciones: ALTER TABLE ADD COLUMN IF NOT EXISTS para columnas
            #    anadidas despues de la creacion inicial del schema.
            #    Seguro de re-ejecutar: cada sentencia usa IF NOT EXISTS / DO $$.
            mig_path = os.path.join(_BASE_DIR, "migrations.sql")
            if os.path.exists(mig_path):
                _aplicar_sql(cur, mig_path)
        conn.commit()
        print("Esquema y migraciones aplicados correctamente.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
