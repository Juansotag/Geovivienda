"""
Script de seed: limpia la base de datos y crea 3 perfiles de cliente
muy distintos, cada uno con 2 búsquedas listas para lanzar.

Perfiles:
  1. Valentina Roa - Joven profesional bogotana (compra primer aprtamento)
  2. Hans & Liesel Müller - Pareja alemana (se muda a Bogotá, busca vivienda familiar grande)
  3. Alberto Gómez - Inversionista jubilado (compra para arrendar o valorizar)
"""

import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import db

# ─────────────────────────────────────────────
# 1. LIMPIAR TODO
# ─────────────────────────────────────────────
print("Vaciando tablas...")
with db.get_cursor() as cur:
    cur.execute("TRUNCATE TABLE reportes, resultados_busqueda, busquedas, anuncios, clientes RESTART IDENTITY CASCADE")
print("✓ Tablas vaciadas\n")


# ─────────────────────────────────────────────
# PERFIL 1: Valentina Roa
# Joven profesional, 27 años, arquitecta
# Ingreso: ~6.5M COP/mes | Ahorro: 2M/mes
# Busca: apartamento pequeño/mediano, primer inmueble,
#         cerca a transporte, estrato 4, Chapinero o Teusaquillo
# ─────────────────────────────────────────────
v_id = db.insertar_cliente({
    "nombre": "Valentina Roa Morales",
    "pais_residencia": "Colombia",
    "ciudad_residencia": "Bogotá",
    "tipo_identificacion": "CC",
    "numero_identificacion": "1018523841",
    "ingreso_mensual": 6_500_000,
    "ingreso_moneda": "COP",
    "ingreso_mensual_cop": 6_500_000,
    "ahorro_mensual": 2_000_000,
    "ahorro_mensual_cop": 2_000_000,
})
print(f"✓ Valentina Roa → cliente_id={v_id}")

# Búsqueda 1A: Apartamento usado en Chapinero/Teusaquillo, cerca a Transmilenio
db.crear_busqueda({
    "cliente_id": v_id,
    "portales": ["fincaraiz", "metrocuadrado"],
    "cantidad_solicitada": 30,
    "cantidad_exacta": False,
    "top_n": 5,
    "status": "pendiente",
    "log": [],
    "municipios": [{"departamento": "Cundinamarca", "municipio": "Bogotá D.C.", "codigo": "11001"}],
    "tipo_vivienda": "apartamento",
    "estado_deseado": "usado",
    "antiguedad_anios_min": None,
    "antiguedad_anios_max": 15,
    "zona_deseada": "",
    "habitaciones_min": 2,
    "habitaciones_exactas": False,
    "banos_min": 1,
    "banos_exactos": False,
    "estrato_objetivo": [3, 4],
    "presupuesto_min": 200_000_000,
    "presupuesto_max": 320_000_000,
    "uso_previsto": ["vivienda propia"],
    "comodidades_relevantes": ["Ascensor", "Balcón", "Vigilancia 24 horas"],
    "comodidades_indispensables": [],
    "upz": ["Chapinero", "Teusaquillo", "Galerías"],
    "pregunta_abierta": "Soy arquitecta, trabajo en el centro ampliado. Necesito vivir cerca al TransMilenio o Metro. Me importa mucho que el sector sea seguro y caminable, con cafés y comercio cerca. Prefiero algo moderno o bien remodelado, con balcón si es posible. No me gustan los sectores ruidosos.",
})
print("  → Búsqueda 1A: Apto usado Chapinero/Teusaquillo")

# Búsqueda 1B: Apartaestudio nuevo en Zona Rosa o Usaquén, para vivir sola
db.crear_busqueda({
    "cliente_id": v_id,
    "portales": ["fincaraiz", "metrocuadrado"],
    "cantidad_solicitada": 25,
    "cantidad_exacta": False,
    "top_n": 4,
    "status": "pendiente",
    "log": [],
    "municipios": [{"departamento": "Cundinamarca", "municipio": "Bogotá D.C.", "codigo": "11001"}],
    "tipo_vivienda": "apartaestudio",
    "estado_deseado": "nuevo",
    "antiguedad_anios_min": None,
    "antiguedad_anios_max": 5,
    "zona_deseada": "",
    "habitaciones_min": 1,
    "habitaciones_exactas": True,
    "banos_min": 1,
    "banos_exactos": False,
    "estrato_objetivo": [4, 5],
    "presupuesto_min": 180_000_000,
    "presupuesto_max": 280_000_000,
    "uso_previsto": ["vivienda propia"],
    "comodidades_relevantes": ["Ascensor", "Gimnasio", "Vigilancia 24 horas"],
    "comodidades_indispensables": ["Ascensor"],
    "upz": ["Chicó Lago", "Usaquén"],
    "pregunta_abierta": "Quiero vivir sola por primera vez. Busco un apartaestudio nuevo o casi nuevo, en una zona con mucha vida urbana, restaurantes y parques cerca. Seguridad es clave. Que tenga gym en el edificio sería ideal. Estoy mirando Zona Rosa, Chicó o Usaquén.",
})
print("  → Búsqueda 1B: Apartaestudio nuevo Chicó/Usaquén\n")


# ─────────────────────────────────────────────
# PERFIL 2: Hans & Liesel Müller
# Pareja alemana, él es gerente regional (trasladado a Bogotá),
# ella es diseñadora freelance. Dos hijos pequeños.
# Ingreso: €8.500/mes (~36M COP) | Ahorro: €2.500/mes
# Busca: casa grande, sector tranquilo, colegios bilingües cerca,
#         entorno verde, estrato 5-6, Usaquén o Suba
# ─────────────────────────────────────────────
h_id = db.insertar_cliente({
    "nombre": "Hans Müller",
    "pais_residencia": "Alemania",
    "ciudad_residencia": "Múnich",
    "tipo_identificacion": "Pasaporte",
    "numero_identificacion": "C3X892047",
    "ingreso_mensual": 8_500,
    "ingreso_moneda": "EUR",
    "ingreso_mensual_cop": 36_125_000,   # aprox 4250 COP/EUR
    "ahorro_mensual": 2_500,
    "ahorro_mensual_cop": 10_625_000,
})
print(f"✓ Hans & Liesel Müller → cliente_id={h_id}")

# Búsqueda 2A: Casa grande en Usaquén, sector residencial tranquilo
db.crear_busqueda({
    "cliente_id": h_id,
    "portales": ["fincaraiz", "metrocuadrado"],
    "cantidad_solicitada": 20,
    "cantidad_exacta": False,
    "top_n": 5,
    "status": "pendiente",
    "log": [],
    "municipios": [{"departamento": "Cundinamarca", "municipio": "Bogotá D.C.", "codigo": "11001"}],
    "tipo_vivienda": "casa",
    "estado_deseado": "usado",
    "antiguedad_anios_min": None,
    "antiguedad_anios_max": 25,
    "zona_deseada": "",
    "habitaciones_min": 4,
    "habitaciones_exactas": False,
    "banos_min": 3,
    "banos_exactos": False,
    "estrato_objetivo": [5, 6],
    "presupuesto_min": 900_000_000,
    "presupuesto_max": 1_600_000_000,
    "uso_previsto": ["vivienda propia"],
    "comodidades_relevantes": ["Zonas verdes", "Vigilancia 24 horas", "Parqueadero", "Zona BBQ"],
    "comodidades_indispensables": ["Parqueadero"],
    "upz": ["Usaquén", "Santa Bárbara", "Los Cedros"],
    "pregunta_abierta": "Somos una familia alemana con dos hijos de 6 y 9 años que se muda a Bogotá. Necesitamos una casa grande con jardín o terraza, mínimo 4 habitaciones, garaje. Que esté en un barrio tranquilo, seguro, con parques cerca y colegios bilingües a poca distancia. El entorno verde es muy importante para nosotros. Queremos el norte de Bogotá.",
})
print("  → Búsqueda 2A: Casa grande Usaquén/Santa Bárbara")

# Búsqueda 2B: Apartamento de lujo en Chicó o Country Club (plan B si no hay casa)
db.crear_busqueda({
    "cliente_id": h_id,
    "portales": ["metrocuadrado"],
    "cantidad_solicitada": 20,
    "cantidad_exacta": False,
    "top_n": 5,
    "status": "pendiente",
    "log": [],
    "municipios": [{"departamento": "Cundinamarca", "municipio": "Bogotá D.C.", "codigo": "11001"}],
    "tipo_vivienda": "apartamento",
    "estado_deseado": "nuevo",
    "antiguedad_anios_min": None,
    "antiguedad_anios_max": 8,
    "zona_deseada": "",
    "habitaciones_min": 4,
    "habitaciones_exactas": False,
    "banos_min": 3,
    "banos_exactos": False,
    "estrato_objetivo": [6],
    "presupuesto_min": 1_000_000_000,
    "presupuesto_max": 2_000_000_000,
    "uso_previsto": ["vivienda propia"],
    "comodidades_relevantes": ["Piscina", "Gimnasio", "Zonas verdes", "Salón comunal", "Ascensor"],
    "comodidades_indispensables": ["Ascensor", "Vigilancia 24 horas"],
    "upz": ["Chicó Lago", "El Batán"],
    "pregunta_abierta": "Plan B: si no encontramos casa con jardín, buscamos un apartamento grande de lujo en Chicó o Country Club. Mínimo 4 habitaciones, 3 baños, con áreas comunes de primera (piscina, gimnasio, salón). Estrato 6. Que el edificio sea moderno y seguro. Presupuesto amplio.",
})
print("  → Búsqueda 2B: Apto lujo Chicó/Country Club\n")


# ─────────────────────────────────────────────
# PERFIL 3: Alberto Gómez Restrepo
# Jubilado, 62 años, ex-empresario de Medellín.
# Capital disponible: ~1.500M COP | Ingreso pensión: 8M/mes
# Busca: inmueble para inversión — arrendar o valorizar.
#         Le interesa sector con alta demanda de arriendo,
#         estrato 3-4, zonas con comercio y universidades,
#         o bien Chía como segunda opción para vivir él
# ─────────────────────────────────────────────
a_id = db.insertar_cliente({
    "nombre": "Alberto Gómez Restrepo",
    "pais_residencia": "Colombia",
    "ciudad_residencia": "Medellín",
    "tipo_identificacion": "CC",
    "numero_identificacion": "71623940",
    "ingreso_mensual": 8_000_000,
    "ingreso_moneda": "COP",
    "ingreso_mensual_cop": 8_000_000,
    "ahorro_mensual": 5_000_000,
    "ahorro_mensual_cop": 5_000_000,
})
print(f"✓ Alberto Gómez Restrepo → cliente_id={a_id}")

# Búsqueda 3A: Apartamento para arriendo en zona universitaria (La Candelaria/Chapinero/Fontibón)
db.crear_busqueda({
    "cliente_id": a_id,
    "portales": ["fincaraiz", "metrocuadrado"],
    "cantidad_solicitada": 35,
    "cantidad_exacta": False,
    "top_n": 6,
    "status": "pendiente",
    "log": [],
    "municipios": [{"departamento": "Cundinamarca", "municipio": "Bogotá D.C.", "codigo": "11001"}],
    "tipo_vivienda": "apartamento",
    "estado_deseado": "usado",
    "antiguedad_anios_min": None,
    "antiguedad_anios_max": 20,
    "zona_deseada": "",
    "habitaciones_min": 2,
    "habitaciones_exactas": False,
    "banos_min": 1,
    "banos_exactos": False,
    "estrato_objetivo": [3, 4],
    "presupuesto_min": 180_000_000,
    "presupuesto_max": 380_000_000,
    "uso_previsto": ["inversión - arrendar"],
    "comodidades_relevantes": ["Ascensor", "Vigilancia 24 horas", "Parqueadero"],
    "comodidades_indispensables": [],
    "upz": ["Chapinero", "Galerías", "La Sabana", "Modelia"],
    "pregunta_abierta": "Soy inversionista jubilado. Quiero comprar 1 o 2 apartamentos para poner en arriendo. Me interesa que el sector tenga alta demanda de arriendos: cerca a universidades, oficinas o comercio. Estrato 3-4 para que la rentabilidad sea buena. Precio de compra máximo 380M. Que no esté muy deteriorado el sector.",
})
print("  → Búsqueda 3A: Apto inversión zona universitaria/oficinas")

# Búsqueda 3B: Casa o lote en Chía (Cundinamarca) para vivir o construir
db.crear_busqueda({
    "cliente_id": a_id,
    "portales": ["fincaraiz"],
    "cantidad_solicitada": 20,
    "cantidad_exacta": False,
    "top_n": 5,
    "status": "pendiente",
    "log": [],
    "municipios": [{"departamento": "Cundinamarca", "municipio": "Chía", "codigo": "25175"}],
    "tipo_vivienda": "casa",
    "estado_deseado": "usado",
    "antiguedad_anios_min": None,
    "antiguedad_anios_max": None,
    "zona_deseada": "",
    "habitaciones_min": 3,
    "habitaciones_exactas": False,
    "banos_min": 2,
    "banos_exactos": False,
    "estrato_objetivo": [3, 4, 5],
    "presupuesto_min": 400_000_000,
    "presupuesto_max": 900_000_000,
    "uso_previsto": ["vivienda propia", "inversión - valorizar"],
    "comodidades_relevantes": ["Zonas verdes", "Zona BBQ", "Parqueadero"],
    "comodidades_indispensables": ["Parqueadero"],
    "upz": [],
    "pregunta_abierta": "También evalúo comprar una casa en Chía para retirarme ahí o arrendar. Busco algo tranquilo, con jardín o patío, en conjunto cerrado si es posible. Mínimo 3 habitaciones. Que sea zona residencial, no industrial. El precio puede llegar a 900M si el inmueble lo justifica por tamaño o ubicación.",
})
print("  → Búsqueda 3B: Casa en Chía para retiro/inversión\n")

print("=" * 55)
print("✅ SEED COMPLETO")
print(f"   3 clientes creados (IDs: {v_id}, {h_id}, {a_id})")
print("   6 búsquedas en estado 'pendiente'")
print("   Anuncios e inmuebles: vaciados")
print("=" * 55)
