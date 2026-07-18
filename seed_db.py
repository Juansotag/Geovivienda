import os
import json
import psycopg2
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

def main():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            # Clear old data in order
            print("Limpiando tablas...")
            cur.execute("TRUNCATE TABLE reportes, resultados_busqueda, busquedas, clientes, anuncios, hexagonos, perfil RESTART IDENTITY CASCADE;")
            
            # 1. Insert Profile
            print("Insertando perfil...")
            cur.execute(
                "INSERT INTO perfil (nombre, correo, cargo) VALUES (%s, %s, %s);",
                ("Funcionario Casa en Casa", "funcionario@casaencasa-co.com", "Asesor de vivienda senior")
            )

            # 2. Insert Clients (Only personal details)
            print("Insertando clientes...")
            clientes = [
                ("Juan Carlos Ramírez Pérez", "España", "Madrid", "Cédula de Ciudadanía", "1020304050", 2200.0, "EUR", 9900000.0, 300.0, 1350000.0),
                ("María Camila Torres", "Estados Unidos", "Miami", "Cédula de Extranjería", "2030405060", 4500.0, "USD", 18900000.0, 800.0, 3360000.0),
                ("Andrés Felipe Gómez", "Canadá", "Toronto", "Pasaporte", "PA102030", 3800.0, "USD", 15960000.0, 600.0, 2500000.0)
            ]
            
            cliente_ids = []
            for c in clientes:
                cur.execute(
                    """
                    INSERT INTO clientes (
                        nombre, pais_residencia, ciudad_residencia, tipo_identificacion, numero_identificacion,
                        ingreso_mensual, ingreso_moneda, ingreso_mensual_cop, ahorro_mensual, ahorro_mensual_cop
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                    """,
                    c
                )
                cliente_ids.append(cur.fetchone()[0])

            # 3. Insert Hexagons (Geo-spatial attributes table)
            print("Insertando hexágonos...")
            hexagonos = [
                ("862f10727ffffff", 400.0, 250.0, 600.0, 3.2),  # Cedritos
                ("862f1072bffffff", 200.0, 800.0, 150.0, 3.8),  # Colina
                ("862f10737ffffff", 900.0, 1200.0, 350.0, 3.9), # Suba Coban
                ("862f10707ffffff", 350.0, 450.0, 100.0, 3.0)   # Engativá
            ]
            for h in hexagonos:
                cur.execute(
                    """
                    INSERT INTO hexagonos (h3_index, dist_sitp, dist_tm, dist_ciclo, estrato_promedio_200m)
                    VALUES (%s, %s, %s, %s, %s);
                    """,
                    h
                )

            # 4. Insert Ads (Referencing H3 hexagons, removed spatial variables)
            print("Insertando anuncios...")
            anuncios = [
                (
                    "https://www.fincaraiz.com.co/anuncio-1", "fincaraiz", "FR-101", "apartamento", "usado", "venta",
                    240000000, 150000, "Cedritos, Bogotá", "bogota", 3, 65.0, 2, 2, 1, "3 a 5 años", 4, 5,
                    "balcon, ascensor, parqueadero, salon comun", "Hermoso apartamento iluminado en Cedritos",
                    4.7214, -74.0321, "862f10727ffffff"
                ),
                (
                    "https://www.metrocuadrado.com/anuncio-2", "metrocuadrado", "M4-202", "apartamento", "usado", "venta",
                    290000000, 180000, "Colina Campestre, Bogotá", "bogota", 4, 78.0, 3, 2, 1, "1 a 3 años", 2, 6,
                    "balcon, ascensor, parqueadero, vigilancia", "Excelente ubicación con terraza y parque infantil",
                    4.7350, -74.0580, "862f1072bffffff"
                ),
                (
                    "https://www.metrocuadrado.com/proyecto-3", "metrocuadrado", "M4-PROJ3", "casa", "nuevo/proyecto", "venta",
                    520000000, 0, "Suba Coban, Bogotá", "bogota", 4, 120.0, 3, 3, 2, "Sobre planos", 1, 2,
                    "parqueadero, deposito, vigilancia, zonas verdes", "Proyecto de casas en conjunto cerrado moderno",
                    4.7521, -74.0911, "862f10737ffffff"
                ),
                (
                    "https://www.fincaraiz.com.co/anuncio-4", "fincaraiz", "FR-404", "casa", "usado", "venta",
                    320000000, 0, "Engativá, Bogotá", "bogota", 3, 110.0, 3, 2, 2, "Más de 10 años", 1, 2,
                    "parqueadero, patio, terraza", "Casa amplia cerca al portal de la 80",
                    4.7082, -74.1121, "862f10707ffffff"
                )
            ]
            
            anuncio_ids = []
            for a in anuncios:
                cur.execute(
                    """
                    INSERT INTO anuncios (
                        url, portal, codigo_portal, tipo_inmueble, estado, operacion, precio_venta,
                        administracion, ubicacion_texto, ciudad, estrato, area_metros, habitaciones,
                        banos, parqueaderos, antiguedad, piso_nro, cantidad_pisos, comodidades,
                        descripcion, latitud, longitud, h3_index
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                    """,
                    a
                )
                anuncio_ids.append(cur.fetchone()[0])

            # 5. Insert Searches (Including criteria fields)
            print("Insertando búsquedas...")
            ahora = datetime.now()
            busquedas = [
                # Búsqueda 1: Juan Carlos - Apartamento en Bogotá
                (
                    cliente_ids[0], json.dumps(["fincaraiz", "metrocuadrado"]), 30, "done",
                    json.dumps([{"msg": "Iniciando búsqueda...", "level": "info"}, {"msg": "12 inmuebles encontrados", "level": "ok"}]),
                    ahora - timedelta(minutes=15), ahora - timedelta(minutes=13),
                    "Bogotá D.C.", "Bogotá", "11001", "apartamento", "usado", "0 a 5 años", "urbano",
                    2, False, 1, False, 3, 200000000, 300000000, "vivir", json.dumps(["balcon", "ascensor"]),
                    "Me gustaría un sector tranquilo, cerca de parques y con buena luz natural, con transporte cercano."
                ),
                # Búsqueda 2: María Camila - Casa en Medellín
                (
                    cliente_ids[1], json.dumps(["metrocuadrado"]), 20, "done",
                    json.dumps([{"msg": "Conectando con Selenium Grid...", "level": "info"}, {"msg": "8 inmuebles encontrados", "level": "ok"}]),
                    ahora - timedelta(hours=2), ahora - timedelta(hours=1, minutes=58),
                    "Antioquia", "Medellín", "05001", "casa", "nuevo", "0 a 5 años", "urbano",
                    3, False, 2, False, 4, 400000000, 600000000, "arrendar", json.dumps(["parqueadero", "deposito", "vigilancia"]),
                    "Busco un proyecto moderno que tenga alta demanda para arrendar rápido y buenas áreas comunes."
                ),
                # Búsqueda 3: Andrés Felipe - Casa en Soacha (Rural)
                (
                    cliente_ids[2], json.dumps(["fincaraiz"]), 15, "running",
                    json.dumps([{"msg": "Cargando portal FincaRaiz...", "level": "info"}]),
                    ahora - timedelta(minutes=2), None,
                    "Cundinamarca", "Soacha", "25754", "casa", "usado", "5 a 10 años", "rural",
                    3, False, 3, False, 3, 250000000, 450000000, "indeciso", json.dumps(["parqueadero", "patio"]),
                    "Prefiero una casa lote o casa con patio para mi familia cuando visitemos Colombia."
                )
            ]
            
            busqueda_ids = []
            for b in busquedas:
                cur.execute(
                    """
                    INSERT INTO busquedas (
                        cliente_id, portales, cantidad_solicitada, status, log, creada_en, terminada_en,
                        departamento_interes, municipio_interes, municipio_codigo, tipo_vivienda, estado_deseado,
                        antiguedad_deseada, zona_deseada, habitaciones_min, habitaciones_exactas, banos_min, banos_exactos,
                        estrato_objetivo, presupuesto_min, presupuesto_max, uso_previsto, comodidades, pregunta_abierta
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id;
                    """,
                    b
                )
                busqueda_ids.append(cur.fetchone()[0])
            
            # 6. Insert Search Results (Matches linked by busqueda_id)
            print("Insertando resultados de búsqueda...")
            resultados = [
                (busqueda_ids[0], anuncio_ids[0], 0.92, True), # Cedritos Apt (FR-101)
                (busqueda_ids[0], anuncio_ids[1], 0.78, True), # Colina Apt (M4-202)
                (busqueda_ids[0], anuncio_ids[3], 0.42, False), # Engativá Casa (Mismatched type/budget)
                
                (busqueda_ids[1], anuncio_ids[2], 0.95, True), # Suba Coban Casa proyecto (M4-PROJ3)
                (busqueda_ids[1], anuncio_ids[1], 0.35, False), # Colina Apt (Mismatched type/budget)
            ]
            
            for r in resultados:
                cur.execute(
                    """
                    INSERT INTO resultados_busqueda (busqueda_id, anuncio_id, score, es_top)
                    VALUES (%s, %s, %s, %s);
                    """,
                    r
                )
            
            # 7. Insert Mock Report
            print("Insertando reportes...")
            cur.execute(
                """
                INSERT INTO reportes (cliente_id, anuncio_id, score, contenido_html, generado_en, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s);
                """,
                (
                    cliente_ids[0], anuncio_ids[0], 0.92,
                    "<html><body><h1>Reporte Mock</h1><p>Excelente match en Cedritos para Juan Carlos.</p></body></html>",
                    ahora - timedelta(minutes=10), ahora + timedelta(days=14, hours=23, minutes=50)
                )
            )

        conn.commit()
        print("¡Base de datos sembrada correctamente con datos mock!")
    except Exception as e:
        conn.rollback()
        print(f"Error al sembrar la base de datos: {e}")
        raise e
    finally:
        conn.close()

if __name__ == "__main__":
    main()
