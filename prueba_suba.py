import json
import os
import sys
import time

from dotenv import load_dotenv

# Cargar variables de entorno del archivo .env local
load_dotenv()

# Forzar modo visible de Chrome (sin headless)
os.environ["HEADLESS"] = "false"

import db
from busqueda import ejecutar_busqueda_completa


def main():
    print("=" * 70)
    print(" PRUEBA DE BÚSQUEDA NORMAL (SUBA - BOGOTÁ) CON GUARDADO DE RESULTADOS")
    print("=" * 70)

    # 1. Obtener o crear un cliente de prueba
    clientes = db.listar_clientes()
    if clientes:
        cliente_id = clientes[0]["id"]
        nombre_cliente = clientes[0]["nombre"]
        print(f"✓ Usando cliente existente: {nombre_cliente} (ID: {cliente_id})")
    else:
        cliente_id = db.insertar_cliente({
            "nombre": "Cliente Prueba Suba",
            "pais_residencia": "Colombia",
            "ciudad_residencia": "Bogotá",
            "tipo_identificacion": "CC",
            "numero_identificacion": "123456789",
            "ingreso_mensual": 10000000,
            "ingreso_moneda": "COP",
            "ingreso_mensual_cop": 10000000
        })
        print(f"✓ Cliente de prueba creado con ID: {cliente_id}")

    # 2. Registrar la búsqueda exactamente igual a como se hace desde la app
    print("\nRegistrando parámetros de búsqueda en la base de datos...")
    busqueda_id = db.crear_busqueda({
        "cliente_id": cliente_id,
        "portales": ["fincaraiz", "metrocuadrado"],
        "cantidad_solicitada": 5,
        "tipo_vivienda": "apartamento",
        "estado_deseado": "usado",
        "presupuesto_min": 200000000,
        "presupuesto_max": 500000000,
        "habitaciones_min": 1,
        "banos_min": 1,
        "municipios": [{"departamento": "Bogotá, D.C.", "municipio": "Bogotá, D.C.", "codigo": "11001"}],
        "upz": ["Suba"],
        "pregunta_abierta": "que tenga transporte",
        "status": "running",
        "top_n": 5
    })

    print(f"✓ Búsqueda creada con ID: {busqueda_id}")
    print("\nParámetros configurados:")
    print(" - Inmueble: Apartamento (usado)")
    print(" - Presupuesto: $200M a $500M COP")
    print(" - Ubicación: UPZ Suba, Bogotá, D.C.")
    print(" - Requisitos: Mínimo 1 Hab, 1 Baño")
    print(" - Descripción abierta: 'que tenga transporte'")
    print(" - Cantidad objetivo: 5 inmuebles")
    print(" - Modo Selenium: VISIBLE (HEADLESS=false)")
    print("\nEjecutando pipeline completo (Scraping -> Dedup -> Enrichment -> Hybrid Scoring)...")
    print("Por favor no cierres la consola hasta que finalice.\n")

    t0 = time.time()
    try:
        ejecutar_busqueda_completa(busqueda_id, top=5)
        duracion = time.time() - t0

        print(f"\n" + "=" * 70)
        print(f" SUCCESS: Búsqueda completada exitosamente en {duracion:.1f} segundos")
        print("=" * 70)

        # 3. Obtener resultados completos de la DB
        resultados = db.obtener_resultados_busqueda(busqueda_id)

        # 4. Guardar archivo JSON detallado
        archivo_json = "resultado_prueba_suba.json"
        with open(archivo_json, "w", encoding="utf-8") as f:
            json.dump(resultados, f, ensure_ascii=False, indent=2, default=str)
        print(f"\n💾 Guardado JSON detallado en: {os.path.abspath(archivo_json)}")

        # 5. Guardar informe Markdown con formato legible
        archivo_md = "resultado_prueba_suba.md"
        with open(archivo_md, "w", encoding="utf-8") as f:
            f.write(f"# Resultados de Búsqueda: UPZ Suba (ID Búsqueda: {busqueda_id})\n\n")
            f.write(f"- **Duración total:** {duracion:.1f} s\n")
            f.write(f"- **Total inmuebles evaluados/rankeados:** {len(resultados)}\n\n")
            f.write("## Ranking de Inmuebles Encontrados\n\n")

            for i, r in enumerate(resultados, 1):
                top_badge = "⭐ TOP 5" if r.get("es_top") else "  "
                score = r.get("score")
                score_str = f"{score:.1f}" if score is not None else "N/D"
                precio = r.get("precio_venta")
                precio_str = f"${precio/1e6:.0f}M" if precio else "N/D"

                f.write(f"### {i}. {top_badge} [{score_str} pts] {r.get('tipo_inmueble')} en {r.get('upz') or 'N/D'} - {precio_str}\n")
                f.write(f"- **Portal:** {r.get('portal')}\n")
                f.write(f"- **URL:** [{r.get('url')}]({r.get('url')})\n")
                f.write(f"- **Características:** {r.get('habitaciones')} hab | {r.get('banos')} baños | {r.get('area_metros')} m² | Estrato {r.get('estrato')}\n")
                f.write(f"- **Distancias Geoespaciales:** SITP: {r.get('dist_sitp')}m | TransMilenio: {r.get('dist_tm')}m | Ciclorruta: {r.get('dist_ciclo')}m\n")
                if r.get("sub_scores"):
                    f.write(f"- **Desglose de Sub-scores:** `{json.dumps(r.get('sub_scores'), ensure_ascii=False)}`\n")
                f.write("\n---\n\n")

        print(f"📄 Guardado resumen en Markdown en: {os.path.abspath(archivo_md)}")

        # 6. Imprimir resumen en consola
        print(f"\nResumen de Inmuebles Rankeados ({len(resultados)}):")
        for i, r in enumerate(resultados, 1):
            top_mark = "⭐ TOP 5" if r.get("es_top") else "      "
            score = r.get("score")
            score_str = f"{score:.1f} pts" if score is not None else "Sin score"
            precio = r.get("precio_venta")
            precio_str = f"${precio/1e6:.0f}M" if precio else "N/D"
            print(f" {i}. {top_mark} | [{score_str}] {r.get('tipo_inmueble')} en {r.get('upz')} - {precio_str} | Portal: {r.get('portal')}")

    except Exception as e:
        import traceback
        print("\n❌ Error durante la ejecución:")
        traceback.print_exc()


if __name__ == "__main__":
    main()
