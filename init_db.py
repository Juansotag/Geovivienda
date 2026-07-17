import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]


def main():
    with open("schema.sql", encoding="utf-8") as f:
        ddl = f.read()
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()
        print("Esquema aplicado correctamente.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
