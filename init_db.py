import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]


def _aplicar_sql(cur, archivo: str):
    """Ejecuta un archivo SQL contra la conexion activa.
    psycopg2 no acepta multiples sentencias en un solo execute() (a diferencia
    de psql), asi que se separan por ';' y se ejecutan de una en una,
    omitiendo bloques vacios y comentarios de linea completa."""
    with open(archivo, encoding="utf-8") as f:
        sql = f.read()
    # Separar por ';' pero respetar los bloques DO $$ ... END $$;
    # Para simplicidad: usamos el token ';' seguido de nueva linea como delimitador.
    # Los bloques DO $$ tienen su propio ';' al final que forma la ultima sentencia.
    sentencias = [s.strip() for s in sql.split(";") if s.strip()]
    for stmt in sentencias:
        # Saltarse las lineas que son solo comentarios -- ...
        lineas_codigo = [l for l in stmt.splitlines() if not l.strip().startswith("--")]
        codigo = "\n".join(lineas_codigo).strip()
        if not codigo:
            continue
        cur.execute(stmt)
    print(f"  OK: {archivo}")


def main():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            # 1. Schema base: CREATE TABLE IF NOT EXISTS (estado final de cada tabla)
            _aplicar_sql(cur, "schema.sql")
            # 2. Migraciones: ALTER TABLE ADD COLUMN IF NOT EXISTS para columnas
            #    anadidas despues de la creacion inicial del schema.
            #    Seguro de re-ejecutar: cada sentencia usa IF NOT EXISTS / DO $$.
            if os.path.exists("migrations.sql"):
                _aplicar_sql(cur, "migrations.sql")
        conn.commit()
        print("Esquema y migraciones aplicados correctamente.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
