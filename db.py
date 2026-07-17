import json
import os
from contextlib import contextmanager

from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

load_dotenv()

_pool = ThreadedConnectionPool(minconn=1, maxconn=10, dsn=os.environ["DATABASE_URL"])


@contextmanager
def get_cursor():
    conn = _pool.getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)


def buscar_anuncio_por_url(url: str) -> dict | None:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM anuncios WHERE url = %s", (url,))
        return cur.fetchone()


def _preparar_datos(datos: dict) -> tuple[dict, list[str]]:
    """Convierte valores list/dict a JSON (para columnas JSONB) y devuelve
    tambien la lista de columnas que necesitan el cast ::jsonb en el SQL,
    porque psycopg2 adaptaria una lista de Python a un array nativo de
    Postgres por defecto, no a JSON."""
    preparados = {}
    columnas_jsonb = []
    for k, v in datos.items():
        if isinstance(v, (list, dict)):
            preparados[k] = json.dumps(v)
            columnas_jsonb.append(k)
        else:
            preparados[k] = v
    return preparados, columnas_jsonb


def insertar_anuncio(datos: dict) -> int:
    columnas = list(datos.keys())
    placeholders = [f"%({c})s" for c in columnas]
    query = f"""
        INSERT INTO anuncios ({', '.join(columnas)})
        VALUES ({', '.join(placeholders)})
        ON CONFLICT (url) DO UPDATE SET
            ultima_verificacion = now(), activo = TRUE
        RETURNING id
    """
    with get_cursor() as cur:
        cur.execute(query, datos)
        return cur.fetchone()["id"]


def marcar_inactivo(url: str):
    with get_cursor() as cur:
        cur.execute("UPDATE anuncios SET activo = FALSE WHERE url = %s", (url,))


def insertar_cliente(datos: dict) -> int:
    preparados, columnas_jsonb = _preparar_datos(datos)
    columnas = list(preparados.keys())
    placeholders = [f"%({c})s::jsonb" if c in columnas_jsonb else f"%({c})s" for c in columnas]
    query = f"""
        INSERT INTO clientes ({', '.join(columnas)})
        VALUES ({', '.join(placeholders)}) RETURNING id
    """
    with get_cursor() as cur:
        cur.execute(query, preparados)
        return cur.fetchone()["id"]


def obtener_cliente(cliente_id: int) -> dict | None:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM clientes WHERE id = %s", (cliente_id,))
        return cur.fetchone()


def listar_clientes() -> list[dict]:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM clientes ORDER BY creado_en DESC")
        return cur.fetchall()


def buscar_anuncio_por_id(anuncio_id: int) -> dict | None:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM anuncios WHERE id = %s", (anuncio_id,))
        return cur.fetchone()


def crear_busqueda(cliente_id: int, portales: list[str], cantidad: int) -> int:
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO busquedas (cliente_id, portales, cantidad_solicitada, status, log)
            VALUES (%s, %s, %s, 'running', '[]'::jsonb) RETURNING id
            """,
            (cliente_id, json.dumps(portales), cantidad),
        )
        return cur.fetchone()["id"]


def actualizar_busqueda_log(busqueda_id: int, mensaje: str, nivel: str = "info"):
    evento = json.dumps([{"msg": mensaje, "level": nivel}])
    with get_cursor() as cur:
        cur.execute(
            "UPDATE busquedas SET log = log || %s::jsonb WHERE id = %s",
            (evento, busqueda_id),
        )


def obtener_busqueda(busqueda_id: int) -> dict | None:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM busquedas WHERE id = %s", (busqueda_id,))
        return cur.fetchone()


def finalizar_busqueda(busqueda_id: int, status: str):
    with get_cursor() as cur:
        cur.execute(
            "UPDATE busquedas SET status = %s, terminada_en = now() WHERE id = %s",
            (status, busqueda_id),
        )


def guardar_resultado_busqueda(busqueda_id: int, anuncio_id: int, score: float, es_top: bool = False) -> int:
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO resultados_busqueda (busqueda_id, anuncio_id, score, es_top)
            VALUES (%s, %s, %s, %s) RETURNING id
            """,
            (busqueda_id, anuncio_id, score, es_top),
        )
        return cur.fetchone()["id"]


def guardar_reporte(cliente_id: int, anuncio_id: int, score: float, html: str) -> int:
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO reportes (cliente_id, anuncio_id, score, contenido_html, expires_at)
            VALUES (%s, %s, %s, %s, now() + interval '15 days')
            RETURNING id
            """,
            (cliente_id, anuncio_id, score, html),
        )
        return cur.fetchone()["id"]


def obtener_reporte(reporte_id: int) -> dict | None:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM reportes WHERE id = %s", (reporte_id,))
        return cur.fetchone()


def obtener_resultados_busqueda(busqueda_id: int) -> list[dict]:
    """Anuncios de una busqueda con su score y el id del reporte mas
    reciente (si ya se genero uno), ordenados de mejor a peor score."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.*, rb.score, rb.es_top,
                   (SELECT r.id FROM reportes r
                    WHERE r.anuncio_id = a.id AND r.cliente_id = (
                        SELECT cliente_id FROM busquedas WHERE id = %s
                    )
                    ORDER BY r.generado_en DESC LIMIT 1) AS reporte_id
            FROM resultados_busqueda rb
            JOIN anuncios a ON a.id = rb.anuncio_id
            WHERE rb.busqueda_id = %s
            ORDER BY rb.score DESC
            """,
            (busqueda_id, busqueda_id),
        )
        return cur.fetchall()


def limpiar_reportes_vencidos() -> int:
    with get_cursor() as cur:
        cur.execute("DELETE FROM reportes WHERE expires_at < now()")
        return cur.rowcount
