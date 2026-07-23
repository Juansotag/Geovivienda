import json
import math
import os
from contextlib import contextmanager

import psycopg2
from dotenv import load_dotenv
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

load_dotenv()

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    raise RuntimeError("La variable de entorno DATABASE_URL no está configurada.")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

_pool = ThreadedConnectionPool(minconn=1, maxconn=10, dsn=db_url, connect_timeout=3)



def _obtener_conexion_viva():
    """Descarta conexiones muertas del pool hasta encontrar una viva."""
    for _ in range(3):
        try:
            conn = _pool.getconn()
        except Exception:
            break

        if conn.closed != 0:
            try:
                _pool.putconn(conn, close=True)
            except Exception:
                pass
            continue
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            conn.rollback()
            return conn
        except (psycopg2.OperationalError, psycopg2.InterfaceError):
            try:
                _pool.putconn(conn, close=True)
            except Exception:
                pass
    return _pool.getconn()


@contextmanager
def get_cursor():
    """Obtiene una conexion viva del pool y la devuelve al terminar."""
    conn = _obtener_conexion_viva()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        conn.commit()
        _pool.putconn(conn)
    except (psycopg2.OperationalError, psycopg2.InterfaceError):
        try:
            _pool.putconn(conn, close=True)
        except Exception:
            pass
        raise
    except Exception:
        try:
            conn.rollback()
            _pool.putconn(conn)
        except Exception:
            pass
        raise


def buscar_anuncio_por_url(url: str) -> dict | None:
    """Incluye el join con hexagonos (dist_tm/dist_sitp/dist_ciclo/estrato_promedio_200m)
    porque esta es la funcion que arma la lista de candidatos para el scoring
    LLM (ver busqueda.py) - sin el join, el LLM quedaba ciego al contexto
    geoespacial de cada anuncio durante una busqueda real."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.*, h.dist_sitp, h.dist_tm, h.dist_ciclo, h.estrato_promedio_200m
            FROM anuncios a
            LEFT JOIN hexagonos h ON h.h3_index = a.h3_index
            WHERE a.url = %s
            """,
            (url,),
        )
        return cur.fetchone()


def obtener_hexagono(h3_index: str) -> dict | None:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM hexagonos WHERE h3_index = %s", (h3_index,))
        return cur.fetchone()


def insertar_hexagono(datos: dict):
    preparados, columnas_jsonb = _preparar_datos(datos)
    columnas = list(preparados.keys())
    placeholders = [f"%({c})s::jsonb" if c in columnas_jsonb else f"%({c})s" for c in columnas]
    query = f"""
        INSERT INTO hexagonos ({', '.join(columnas)})
        VALUES ({', '.join(placeholders)})
        ON CONFLICT (h3_index) DO NOTHING
    """
    with get_cursor() as cur:
        cur.execute(query, preparados)


def _preparar_datos(datos: dict) -> tuple[dict, list[str]]:
    """Convierte valores list/dict a JSON (para columnas JSONB) y devuelve
    tambien la lista de columnas que necesitan el cast ::jsonb en el SQL,
    porque psycopg2 adaptaria una lista de Python a un array nativo de
    Postgres por defecto, no a JSON.

    Usa _NumpyEncoder para tolerar valores numpy.float64/int64 que puedan
    llegar en h3_data u otras columnas JSONB sin lanzar TypeError."""

    class _NumpyEncoder(json.JSONEncoder):
        """Convierte tipos numpy a Python nativo; NaN → null JSON."""
        def default(self, obj):  # noqa: D102
            try:
                import numpy as np
                if isinstance(obj, np.floating):
                    return None if math.isnan(float(obj)) else float(obj)
                if isinstance(obj, np.integer):
                    return int(obj)
                if isinstance(obj, np.bool_):
                    return bool(obj)
            except ImportError:
                pass
            return super().default(obj)

    preparados = {}
    columnas_jsonb = []
    for k, v in datos.items():
        if isinstance(v, (list, dict)):
            preparados[k] = json.dumps(v, cls=_NumpyEncoder)
            columnas_jsonb.append(k)
        else:
            preparados[k] = v
    return preparados, columnas_jsonb


def insertar_anuncio(datos: dict) -> int:
    preparados, columnas_jsonb = _preparar_datos(datos)
    columnas = list(preparados.keys())
    placeholders = [f"%({c})s::jsonb" if c in columnas_jsonb else f"%({c})s" for c in columnas]
    query = f"""
        INSERT INTO anuncios ({', '.join(columnas)})
        VALUES ({', '.join(placeholders)})
        ON CONFLICT (url) DO UPDATE SET
            ultima_verificacion = now(), activo = TRUE
        RETURNING id
    """
    with get_cursor() as cur:
        cur.execute(query, preparados)
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
    """Misma razon que buscar_anuncio_por_url: esta funcion alimenta al
    generador de reportes (ver reportes.py PROMPT_TEMPLATE, seccion
    ENTORNO), que necesita dist_tm/dist_sitp/dist_ciclo/estrato_promedio_200m
    y h3_data para el perfil detallado del inmueble."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.*, h.dist_sitp, h.dist_tm, h.dist_ciclo, h.estrato_promedio_200m
            FROM anuncios a
            LEFT JOIN hexagonos h ON h.h3_index = a.h3_index
            WHERE a.id = %s
            """,
            (anuncio_id,),
        )
        return cur.fetchone()


def crear_busqueda(datos: dict) -> int:
    preparados, columnas_jsonb = _preparar_datos(datos)
    columnas = list(preparados.keys())
    placeholders = [f"%({c})s::jsonb" if c in columnas_jsonb else f"%({c})s" for c in columnas]
    query = f"""
        INSERT INTO busquedas ({', '.join(columnas)})
        VALUES ({', '.join(placeholders)}) RETURNING id
    """
    with get_cursor() as cur:
        cur.execute(query, preparados)
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


def guardar_resultado_busqueda(busqueda_id: int, anuncio_id: int, score: float, es_top: bool = False, sub_scores: dict | None = None) -> int:
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO resultados_busqueda (busqueda_id, anuncio_id, score, es_top, sub_scores)
            VALUES (%s, %s, %s, %s, %s::jsonb) RETURNING id
            """,
            (busqueda_id, anuncio_id, score, es_top, json.dumps(sub_scores) if sub_scores else None),
        )
        return cur.fetchone()["id"]


def obtener_resultados_por_anuncio(anuncio_id: int) -> list[dict]:
    """Todas las busquedas donde este anuncio aparece como resultado, con
    los criterios completos de cada una - usado para recalcular el score
    cuando el funcionario corrige a mano un dato del anuncio que estaba
    mal (ej. un error de scraping evidente)."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT rb.id AS resultado_id, rb.score AS score_actual, b.*
            FROM resultados_busqueda rb
            JOIN busquedas b ON b.id = rb.busqueda_id
            WHERE rb.anuncio_id = %s
            """,
            (anuncio_id,),
        )
        return cur.fetchall()


def actualizar_score_resultado(resultado_id: int, score: float):
    with get_cursor() as cur:
        cur.execute("UPDATE resultados_busqueda SET score = %s WHERE id = %s", (score, resultado_id))


def actualizar_sub_scores_resultado(resultado_id: int, sub_scores: dict):
    with get_cursor() as cur:
        cur.execute(
            "UPDATE resultados_busqueda SET sub_scores = %s::jsonb WHERE id = %s",
            (json.dumps(sub_scores), resultado_id),
        )


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
    """Anuncios de una busqueda con su score, sub_scores y el id del reporte mas
    reciente (si ya se genero uno), ordenados de mejor a peor score."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.*, h.dist_sitp, h.dist_tm, h.dist_ciclo, h.estrato_promedio_200m,
                   rb.score, rb.es_top, rb.sub_scores, rb.id AS resultado_id,
                   (SELECT r.id FROM reportes r
                    WHERE r.anuncio_id = a.id AND r.cliente_id = (
                        SELECT cliente_id FROM busquedas WHERE id = %s
                    )
                    ORDER BY r.generado_en DESC LIMIT 1) AS reporte_id
            FROM resultados_busqueda rb
            JOIN anuncios a ON a.id = rb.anuncio_id
            LEFT JOIN hexagonos h ON h.h3_index = a.h3_index
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


def actualizar_cliente(cliente_id: int, datos: dict):
    preparados, columnas_jsonb = _preparar_datos(datos)
    updates = []
    for c in preparados.keys():
        if c in columnas_jsonb:
            updates.append(f"{c} = %({c})s::jsonb")
        else:
            updates.append(f"{c} = %({c})s")
    query = f"""
        UPDATE clientes
        SET {', '.join(updates)}
        WHERE id = %(cliente_id)s
    """
    preparados["cliente_id"] = cliente_id
    with get_cursor() as cur:
        cur.execute(query, preparados)


def eliminar_cliente(cliente_id: int):
    with get_cursor() as cur:
        cur.execute("DELETE FROM reportes WHERE cliente_id = %s", (cliente_id,))
        cur.execute("DELETE FROM resultados_busqueda WHERE busqueda_id IN (SELECT id FROM busquedas WHERE cliente_id = %s)", (cliente_id,))
        cur.execute("DELETE FROM busquedas WHERE cliente_id = %s", (cliente_id,))
        cur.execute("DELETE FROM clientes WHERE id = %s", (cliente_id,))


def eliminar_anuncio(anuncio_id: int):
    with get_cursor() as cur:
        cur.execute("DELETE FROM reportes WHERE anuncio_id = %s", (anuncio_id,))
        cur.execute("DELETE FROM resultados_busqueda WHERE anuncio_id = %s", (anuncio_id,))
        cur.execute("DELETE FROM anuncios WHERE id = %s", (anuncio_id,))


def eliminar_busqueda(busqueda_id: int):
    with get_cursor() as cur:
        cur.execute("DELETE FROM resultados_busqueda WHERE busqueda_id = %s", (busqueda_id,))
        cur.execute("DELETE FROM busquedas WHERE id = %s", (busqueda_id,))


def obtener_perfil() -> dict:
    with get_cursor() as cur:
        cur.execute("SELECT * FROM perfil LIMIT 1")
        perfil = cur.fetchone()
        if not perfil:
            cur.execute(
                "INSERT INTO perfil (nombre, correo, cargo) VALUES (%s, %s, %s) RETURNING *",
                ("Funcionario Casa en Casa", "funcionario@casaencasa-co.com", "Asesor de vivienda")
            )
            perfil = cur.fetchone()
        return perfil


def actualizar_perfil(nombre: str, correo: str, cargo: str):
    with get_cursor() as cur:
        cur.execute("SELECT id FROM perfil LIMIT 1")
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE perfil SET nombre = %s, correo = %s, cargo = %s WHERE id = %s",
                (nombre, correo, cargo, row["id"])
            )
        else:
            cur.execute(
                "INSERT INTO perfil (nombre, correo, cargo) VALUES (%s, %s, %s)",
                (nombre, correo, cargo)
            )


def obtener_todas_busquedas() -> list[dict]:
    """Devuelve todas las búsquedas con el nombre del cliente asociado.
    Usa LEFT JOIN para no descartar búsquedas cuyo cliente haya sido eliminado."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT b.*,
                   COALESCE(c.nombre, '(cliente eliminado)') AS cliente_nombre,
                   (SELECT COUNT(*) FROM resultados_busqueda rb WHERE rb.busqueda_id = b.id) AS encontrados,
                   (SELECT COUNT(*) FROM resultados_busqueda rb WHERE rb.busqueda_id = b.id AND rb.es_top = TRUE) AS tops,
                   COALESCE(EXTRACT(EPOCH FROM (b.terminada_en - b.creada_en))::integer, 0) AS duracion_segundos
            FROM busquedas b
            LEFT JOIN clientes c ON c.id = b.cliente_id
            ORDER BY b.creada_en DESC
            """
        )
        rows = cur.fetchall()
        return rows


def obtener_todos_anuncios_con_scores() -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.*, h.dist_sitp, h.dist_tm, h.dist_ciclo, h.estrato_promedio_200m,
                   COALESCE(
                       jsonb_agg(
                           jsonb_build_object(
                               'cliente_nombre', c.nombre,
                               'score', rb.score
                           )
                       ) FILTER (WHERE rb.anuncio_id IS NOT NULL),
                       '[]'::jsonb
                   ) AS compatibilidades
            FROM anuncios a
            LEFT JOIN hexagonos h ON h.h3_index = a.h3_index
            LEFT JOIN resultados_busqueda rb ON rb.anuncio_id = a.id
            LEFT JOIN busquedas b ON b.id = rb.busqueda_id
            LEFT JOIN clientes c ON c.id = b.cliente_id
            GROUP BY a.id, h.h3_index, h.dist_sitp, h.dist_tm, h.dist_ciclo, h.estrato_promedio_200m
            ORDER BY a.primera_vez_visto DESC
            """
        )
        return cur.fetchall()


def obtener_anuncio(anuncio_id: int) -> dict:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.*, h.dist_sitp, h.dist_tm, h.dist_ciclo, h.estrato_promedio_200m
            FROM anuncios a
            LEFT JOIN hexagonos h ON h.h3_index = a.h3_index
            WHERE a.id = %s
            """,
            (anuncio_id,)
        )
        return cur.fetchone()


def actualizar_anuncio(anuncio_id: int, datos: dict):
    preparados, columnas_jsonb = _preparar_datos(datos)
    updates = []
    for c in preparados.keys():
        if c in columnas_jsonb:
            updates.append(f"{c} = %({c})s::jsonb")
        else:
            updates.append(f"{c} = %({c})s")
    query = f"""
        UPDATE anuncios
        SET {', '.join(updates)}
        WHERE id = %(anuncio_id)s
    """
    preparados["anuncio_id"] = anuncio_id
    with get_cursor() as cur:
        cur.execute(query, preparados)


def obtener_anuncios_sin_comodidades_normalizadas(limite: int = 40) -> list[dict]:
    """Para el backfill: anuncios que existian antes del clasificador de
    comodidades o que por alguna razon nunca se procesaron. limite acota
    el tamano del prompt de un solo llamado al LLM."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, comodidades, descripcion FROM anuncios
            WHERE comodidades_normalizadas IS NULL AND comodidades IS NOT NULL AND comodidades <> ''
            ORDER BY id
            LIMIT %s
            """,
            (limite,),
        )
        return cur.fetchall()


def obtener_busquedas_cliente(cliente_id: int) -> list[dict]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT b.*,
                   (SELECT COUNT(*) FROM resultados_busqueda rb WHERE rb.busqueda_id = b.id) AS encontrados,
                   (SELECT COUNT(*) FROM resultados_busqueda rb WHERE rb.busqueda_id = b.id AND rb.es_top = TRUE) AS tops,
                   COALESCE(EXTRACT(EPOCH FROM (b.terminada_en - b.creada_en))::integer, 0) AS duracion_segundos
            FROM busquedas b
            WHERE b.cliente_id = %s
            ORDER BY b.creada_en DESC
            """,
            (cliente_id,)
        )
        return cur.fetchall()


# NOTA: la definición correcta de eliminar_busqueda está en la línea ~305 (borra
# resultados_busqueda + busquedas). Esta segunda definición incompleta fue eliminada
# para evitar que Python la sobrescribiera silenciosamente.


def actualizar_busqueda(busqueda_id: int, datos: dict):
    """Actualiza los criterios de una busqueda existente (solo permitido en
    estado 'pendiente', esa regla se aplica en la ruta de Flask, no aca)."""
    preparados, columnas_jsonb = _preparar_datos(datos)
    updates = []
    for c in preparados.keys():
        if c in columnas_jsonb:
            updates.append(f"{c} = %({c})s::jsonb")
        else:
            updates.append(f"{c} = %({c})s")
    query = f"""
        UPDATE busquedas
        SET {', '.join(updates)}
        WHERE id = %(busqueda_id)s
    """
    preparados["busqueda_id"] = busqueda_id
    with get_cursor() as cur:
        cur.execute(query, preparados)


def actualizar_busqueda_status(busqueda_id: int, status: str):
    with get_cursor() as cur:
        cur.execute(
            "UPDATE busquedas SET status = %s, terminada_en = NULL WHERE id = %s",
            (status, busqueda_id),
        )


def obtener_mapa_busqueda_resultados(limite: int = 5000) -> dict[str, list[int]]:
    """Devuelve un mapa {busqueda_id_str: [anuncio_id, ...]} para renderizar
    el filtro de búsquedas en la vista del mapa. Se limita a 'limite' filas
    para evitar cargar toda la tabla en memoria si hay muchos resultados.
    La clave del dict es str porque JS/Jinja2 convierten las claves numéricas
    de JSON a strings al hacer la comparación."""
    resultado: dict[str, list[int]] = {}
    with get_cursor() as cur:
        cur.execute(
            "SELECT busqueda_id, anuncio_id FROM resultados_busqueda ORDER BY busqueda_id LIMIT %s",
            (limite,),
        )
        for r in cur.fetchall():
            b_id = str(r["busqueda_id"])
            if b_id not in resultado:
                resultado[b_id] = []
            resultado[b_id].append(r["anuncio_id"])
    return resultado



