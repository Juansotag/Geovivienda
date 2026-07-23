import json
import os

import anthropic
from dotenv import load_dotenv

import config

load_dotenv()
_client = anthropic.Anthropic()

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

with open(os.path.join(_BASE_DIR, "score_config.json"), encoding="utf-8") as f:
    PESOS = json.load(f)

# Definición de las 5 dimensiones del scoring híbrido.
# Cada dimensión es una lista de (rank_key, peso_interno).
# Los pesos internos suman 1.0 dentro de cada dimensión.
DIMENSIONES_H3 = {
    "s_seguridad": {
        "label": "Seguridad Ciudadana",
        "color": "#e74c3c",
        "variables": [
            ("rank_hurtos_upz", 0.35),
            ("rank_hurtos_personas", 0.25),
            ("rank_siniestros_viales_300m", 0.20),
            ("rank_dist_cai", 0.10),
            ("rank_dist_est_policia", 0.10),
        ],
        # Etiquetas legibles y unidades para mostrar en el perfil
        "val_labels": {
            "val_hurtos_upz": ("Hurtos totales UPZ", "casos"),
            "val_hurtos_personas": ("Hurtos a personas", "casos"),
            "val_siniestros_viales_300m": ("Siniestros viales 300m", "accidentes"),
            "val_dist_cai": ("Distancia a CAI", "m"),
            "val_dist_est_policia": ("Distancia a Estación de Policía", "m"),
        },
    },
    "s_transporte": {
        "label": "Transporte y Movilidad",
        "color": "#3498db",
        "variables": [
            ("rank_dist_brt", 0.25),
            ("rank_brt_500m", 0.15),
            ("rank_dist_sitp", 0.20),
            ("rank_sitp_300m", 0.15),
            ("rank_dist_metro", 0.15),
            ("rank_dist_ciclo", 0.10),
        ],
        "val_labels": {
            "val_dist_brt": ("Distancia a BRT/Cable", "m"),
            "val_brt_500m": ("Estaciones BRT 500m", "estaciones"),
            "val_dist_sitp": ("Distancia a SITP", "m"),
            "val_sitp_300m": ("Paraderos SITP 300m", "paraderos"),
            "val_dist_metro": ("Distancia a Metro", "m"),
            "val_dist_ciclo": ("Distancia a Ciclorruta", "m"),
        },
    },
    "s_comercio": {
        "label": "Comercio y Servicios",
        "color": "#f39c12",
        "variables": [
            ("rank_dist_d1_ara", 0.30),
            ("rank_conteo_hard_discount_500m", 0.20),
            ("rank_dist_supermercado_premium", 0.25),
            ("rank_dist_centro_comercial", 0.25),
        ],
        "val_labels": {
            "val_dist_d1_ara": ("Distancia a D1/Ara", "m"),
            "val_conteo_hard_discount_500m": ("D1/Ara en 500m", "tiendas"),
            "val_dist_supermercado_premium": ("Distancia a supermercado premium", "m"),
            "val_dist_centro_comercial": ("Distancia a centro comercial", "m"),
        },
    },
    "s_entorno_verde": {
        "label": "Entorno Verde y Ambiental",
        "color": "#27ae60",
        "variables": [
            ("rank_dist_parque", 0.35),
            ("rank_arboles_300m", 0.30),
            ("rank_pm25", 0.20),
            ("rank_dist_recreacion_deporte", 0.15),
        ],
        "val_labels": {
            "val_dist_parque": ("Distancia a parque", "m"),
            "val_arboles_300m": ("Árboles en 300m", "árboles"),
            "val_pm25": ("Contaminación PM2.5", "µg/m³"),
            "val_dist_recreacion_deporte": ("Distancia a canchas/gimnasios", "m"),
        },
    },
    "s_estrato_valor": {
        "label": "Estrato y Valorización",
        "color": "#9b59b6",
        "variables": [
            ("rank_estrato", 0.40),
            ("rank_avaluo_catastral_m2", 0.30),
            ("rank_hospitales_500m", 0.15),
            ("rank_colegios_500m", 0.15),
        ],
        "val_labels": {
            "estrato_promedio_200m": ("Estrato promedio 200m", ""),
            "val_avaluo_catastral_m2": ("Avalúo catastral", "COP/m²"),
            "val_hospitales_500m": ("Hospitales en 500m", "centros"),
            "val_colegios_500m": ("Colegios en 500m", "colegios"),
        },
    },
}

# Pesos por defecto del score global cuando el LLM no ha respondido
PESOS_GLOBALES_DEFAULT = {
    "s_seguridad": 0.25,
    "s_transporte": 0.10,
    "s_comercio": 0.15,
    "s_entorno_verde": 0.20,
    "s_estrato_valor": 0.20,
    # Restante: 0.10 se asigna al score clásico del inmueble (presupuesto, habitaciones, etc.)
    "_score_inmueble": 0.10,
}


def calcular_sub_scores(anuncio: dict) -> dict:
    """Calcula los 5 Sub-Scores a partir de los rank_* guardados en h3_data del anuncio.
    Cada Sub-Score es un float entre 0.0 (peor percentil urbano) y 1.0 (mejor).
    Devuelve un dict con las 5 claves y además el score global ponderado con pesos default."""
    h3_data = anuncio.get("h3_data") or {}
    if isinstance(h3_data, str):
        try:
            h3_data = json.loads(h3_data)
        except Exception:
            h3_data = {}

    sub = {}
    for dim_key, dim_cfg in DIMENSIONES_H3.items():
        total_peso = 0.0
        total_score = 0.0
        for rank_key, peso in dim_cfg["variables"]:
            val = h3_data.get(rank_key)
            if val is not None:
                try:
                    total_score += float(val) * peso
                    total_peso += peso
                except (TypeError, ValueError):
                    pass
        sub[dim_key] = round(total_score / total_peso, 4) if total_peso > 0 else None

    return sub


def solicitar_pesos_llm(busqueda: dict) -> dict:
    """Llamado ultrarrápido a Claude (~300ms, max_tokens=250) que devuelve los pesos
    personalizados de las 5 dimensiones según el perfil del cliente.
    Devuelve dict con claves s_seguridad, s_transporte, s_comercio, s_entorno_verde,
    s_estrato_valor, _score_inmueble (todos sumando 1.0).
    Si falla, devuelve los pesos por defecto."""
    pregunta = (busqueda.get("pregunta_abierta") or "").strip()
    estrato = busqueda.get("estrato_objetivo") or []
    uso = busqueda.get("uso_previsto") or []

    prompt = f"""Eres un sistema de scoring inmobiliario. Dado el perfil del cliente, 
asigna pesos (0.0-1.0, sumando exactamente 1.0) a 6 dimensiones de evaluación.

PERFIL DEL CLIENTE:
- Lo que busca (texto libre): {pregunta or 'no especificado'}
- Estrato objetivo: {estrato}
- Uso previsto: {uso}
- Presupuesto: {busqueda.get('presupuesto_min', 0):,.0f} a {busqueda.get('presupuesto_max', 0):,.0f} COP

DIMENSIONES (asigna un peso a cada una):
- s_seguridad: seguridad ciudadana, hurtos, accidentalidad
- s_transporte: TransMilenio, Metro, SITP, ciclovías
- s_comercio: supermercados, centros comerciales, D1/Ara
- s_entorno_verde: parques, árboles, calidad del aire, recreación
- s_estrato_valor: estrato, avalúo catastral, colegios, hospitales
- _score_inmueble: características físicas del inmueble (precio, habitaciones, comodidades)

Responde ÚNICAMENTE con un objeto JSON, sin texto adicional:
{{"s_seguridad": 0.XX, "s_transporte": 0.XX, "s_comercio": 0.XX, "s_entorno_verde": 0.XX, "s_estrato_valor": 0.XX, "_score_inmueble": 0.XX}}"""

    try:
        respuesta = _client.messages.create(
            model=config.CLAUDE_FAST,
            max_tokens=config.MAX_TOKENS_PESOS,
            messages=[{"role": "user", "content": prompt}],
        )
        texto = "".join(b.text for b in respuesta.content if b.type == "text").strip()
        if texto.startswith("```"):
            texto = texto.split("```")[1]
            if texto.lower().startswith("json"):
                texto = texto[4:]
        pesos = json.loads(texto)
        # Normalizar para que sumen exactamente 1.0
        total = sum(pesos.values())
        if total > 0:
            pesos = {k: round(v / total, 4) for k, v in pesos.items()}
        # Validar que todas las claves existan
        for k in PESOS_GLOBALES_DEFAULT:
            if k not in pesos:
                pesos[k] = PESOS_GLOBALES_DEFAULT[k]
        return pesos
    except Exception:
        return dict(PESOS_GLOBALES_DEFAULT)


def _score_presupuesto(cliente: dict, anuncio: dict) -> float:
    precio = anuncio.get("precio_venta")
    lo, hi = cliente.get("presupuesto_min"), cliente.get("presupuesto_max")
    if precio is None or lo is None or hi is None:
        return 0.5
    if lo <= precio <= hi:
        return 1.0
    exceso = (precio - hi) if precio > hi else (lo - precio)
    rango = (hi - lo) or 1
    return max(0.0, 1 - exceso / rango)


def _score_estrato(cliente: dict, anuncio: dict) -> float:
    objetivos = cliente.get("estrato_objetivo")  # lista (multi-choice)
    real = anuncio.get("estrato_promedio_200m")
    if real is None:
        real = anuncio.get("estrato")
    if not objetivos or real is None:
        return 0.5
    return max(max(0.0, 1 - abs(o - real) / 3) for o in objetivos)


def _score_habitaciones_banos(criterios: dict, anuncio: dict) -> float:
    hab_min = criterios.get("habitaciones_min") or 0
    banos_min = criterios.get("banos_min") or 0

    if criterios.get("habitaciones_exactas"):
        hab_ok = (anuncio.get("habitaciones") or 0) == hab_min
    else:
        hab_ok = (anuncio.get("habitaciones") or 0) >= hab_min

    if criterios.get("banos_exactos"):
        banos_ok = (anuncio.get("banos") or 0) == banos_min
    else:
        banos_ok = (anuncio.get("banos") or 0) >= banos_min

    return (hab_ok + banos_ok) / 2


def _score_transporte(anuncio: dict) -> float:
    dist_tm = anuncio.get("dist_tm")
    dist_sitp = anuncio.get("dist_sitp")
    candidatos = [d for d in (dist_tm, dist_sitp) if d is not None]
    if not candidatos:
        return 0.5
    dist = min(candidatos)
    if dist <= 300:
        return 1.0
    if dist >= 1500:
        return 0.0
    return 1 - (dist - 300) / 1200


def _score_tipo_vivienda(cliente: dict, anuncio: dict) -> float:
    tipo_cliente = (cliente.get("tipo_vivienda") or "").lower()
    tipo_anuncio = (anuncio.get("tipo_inmueble") or "").lower()
    if not tipo_cliente or not tipo_anuncio:
        return 0.5
    return 1.0 if tipo_cliente in tipo_anuncio or tipo_anuncio in tipo_cliente else 0.0


def _score_antiguedad_estado(anuncio: dict) -> float:
    estado = (anuncio.get("estado") or "").lower()
    if not estado:
        return 0.5
    return 0.6 if "planos" in estado or "proyecto" in estado else 1.0


def calcular_score_inmueble(cliente: dict, anuncio: dict) -> float:
    """Score clásico basado solo en atributos físicos del inmueble (0.0–1.0)."""
    componentes = {
        "presupuesto": _score_presupuesto(cliente, anuncio),
        "estrato": _score_estrato(cliente, anuncio),
        "habitaciones_banos": _score_habitaciones_banos(cliente, anuncio),
        "transporte": _score_transporte(anuncio),
        "tipo_vivienda": _score_tipo_vivienda(cliente, anuncio),
        "antiguedad_estado": _score_antiguedad_estado(anuncio),
    }
    total = sum(componentes[k] * PESOS[k] for k in PESOS)
    return round(total, 4)


def calcular_score(cliente: dict, anuncio: dict) -> dict:
    """API pública de scoring clásico — devuelve {total, componentes}.
    Usada por reportes.py y el botón 'Recalcular score'.
    Delega en calcular_score_inmueble para no duplicar la lógica de componentes."""
    componentes = {
        "presupuesto": _score_presupuesto(cliente, anuncio),
        "estrato": _score_estrato(cliente, anuncio),
        "habitaciones_banos": _score_habitaciones_banos(cliente, anuncio),
        "transporte": _score_transporte(anuncio),
        "tipo_vivienda": _score_tipo_vivienda(cliente, anuncio),
        "antiguedad_estado": _score_antiguedad_estado(anuncio),
    }
    total = sum(componentes[k] * PESOS[k] for k in PESOS)
    return {"total": round(total, 4), "componentes": componentes}


def rankear_candidatos(cliente: dict, anuncios: list[dict]) -> list[dict]:
    resultados = []
    for anuncio in anuncios:
        score = calcular_score(cliente, anuncio)
        resultados.append({**anuncio, "score": score["total"], "score_desglose": score["componentes"]})
    return sorted(resultados, key=lambda r: r["score"], reverse=True)


def top_n(candidatos_rankeados: list[dict], n: int = 5) -> list[dict]:
    return candidatos_rankeados[:n]


def _fmt_score(val, decimales: int = 2) -> str:
    """Formatea un sub-score numérico a `decimales` cifras decimales.
    Devuelve 'N/D' si val es None (pasa cuando el hexágono H3 no tiene datos),
    evitando el TypeError que lanzaba `:.2f` sobre None."""
    if val is None:
        return "N/D"
    try:
        return f"{float(val):.{decimales}f}"
    except (TypeError, ValueError):
        return "N/D"


def _resumir_anuncio_para_prompt(a: dict) -> str:
    precio = a.get("precio_venta") or 0
    admin = a.get("administracion")
    admin_txt = f"${admin:,.0f} COP/mes" if admin else "no especificada"
    sub = a.get("_sub_scores") or {}
    sub_txt = ""
    if sub:
        sub_txt = (
            f" | Sub-Scores del sector: Seguridad={_fmt_score(sub.get('s_seguridad'))}, "
            f"Transporte={_fmt_score(sub.get('s_transporte'))}, "
            f"Comercio={_fmt_score(sub.get('s_comercio'))}, "
            f"Entorno Verde={_fmt_score(sub.get('s_entorno_verde'))}, "
            f"Estrato/Valor={_fmt_score(sub.get('s_estrato_valor'))}"
        )
    pois = a.get("_pois_cercanos") or {}
    pois_txt = ""
    if pois:
        partes = []
        for cat, items in pois.items():
            if items:
                partes.append(f"{cat}: " + ", ".join(f"{p['nombre']} ({p['distancia_m']}m)" for p in items[:2]))
        if partes:
            pois_txt = " | POIs más cercanos: " + "; ".join(partes)

    upz_orig = a.get("upz") or ""
    from services.busqueda import _upz_a_upl_norm
    upl_trad = _upz_a_upl_norm(upz_orig) if upz_orig else ""
    if upz_orig and upl_trad and upl_trad != upz_orig.lower():
        upz_txt = f"{upz_orig} (pertenece a la UPL {upl_trad.title()})"
    else:
        upz_txt = upz_orig or "no especificada"

    return (
        f"- id={a['id']}: {a.get('tipo_inmueble')}, {a.get('estado')}, antigüedad: {a.get('antiguedad') or 'no especificada'}, "
        f"{a.get('habitaciones')} hab, {a.get('banos')} baños, {a.get('parqueaderos') or 0} parqueadero(s), {a.get('area_metros')} m², "
        f"estrato {a.get('estrato')} (estrato del sector 200m: {a.get('estrato_promedio_200m')}), "
        f"${precio:,.0f} COP, administración: {admin_txt}, UPZ/UPL: {upz_txt}, ubicación: {a.get('ubicacion_texto')}, "
        f"distancia a TransMilenio: {a.get('dist_tm')}m, distancia a SITP: {a.get('dist_sitp')}m, distancia a ciclorruta: {a.get('dist_ciclo')}m, "
        f"comodidades: {a.get('comodidades') or 'no especificadas'}, "
        f"descripción: {(a.get('descripcion') or '')[:200]}"
        f"{sub_txt}{pois_txt}"
    )


def _texto_lista(valores, vacio="no especificado") -> str:
    if not valores:
        return vacio
    return ", ".join(str(v) for v in valores)


def _texto_rango_anios(minimo, maximo) -> str:
    if minimo is None and maximo is None:
        return "sin límite"
    if maximo is None:
        return f"{minimo}+ años"
    if minimo is None:
        return f"hasta {maximo} años"
    return f"{minimo} a {maximo} años"


def _score_comodidades_relevantes(busqueda: dict, anuncio: dict) -> float | None:
    """Fracción de comodidades OPCIONALES (relevantes) que tiene el inmueble (0.0–1.0).
    Devuelve None si la búsqueda no tiene lista de relevantes (no aplicar al score)."""
    relevantes = busqueda.get("comodidades_relevantes") or []
    if not relevantes:
        return None
    coms = anuncio.get("comodidades_normalizadas") or anuncio.get("comodidades") or []
    if isinstance(coms, str):
        try:
            coms = json.loads(coms)
        except Exception:
            coms = [coms]
    coms_lower = [str(c).lower() for c in coms]
    presentes = sum(
        1 for rel in relevantes
        if any(str(rel).lower() in c or c in str(rel).lower() for c in coms_lower)
    )
    return round(presentes / len(relevantes), 3)


def _score_comodidades_indispensables(busqueda: dict, anuncio: dict) -> float | None:
    """Penalización fuerte si faltan comodidades INDISPENSABLES (0.0–1.0).
    Devuelve None si no hay lista de indispensables.
    Cada comodidad faltante resta 0.7 del score (mínimo 0.0)."""
    indispensables = busqueda.get("comodidades_indispensables") or []
    if not indispensables:
        return None
    coms = anuncio.get("comodidades_normalizadas") or anuncio.get("comodidades") or []
    if isinstance(coms, str):
        try:
            coms = json.loads(coms)
        except Exception:
            coms = [coms]
    coms_lower = [str(c).lower() for c in coms]
    faltantes = sum(
        1 for ind in indispensables
        if not any(str(ind).lower() in c or c in str(ind).lower() for c in coms_lower)
    )
    return round(max(0.0, 1.0 - faltantes * 0.7), 3)


def _score_administracion(anuncio: dict) -> float | None:
    """Score de administración mensual: None si no hay dato (se omite del cálculo).
    ≤$150.000/mes → 1.0 (barata), ≥$700.000/mes → 0.0 (cara), lineal entre medias."""
    admin = anuncio.get("administracion")
    if not admin:
        return None
    try:
        admin = float(admin)
    except (TypeError, ValueError):
        return None
    if admin <= 0:
        return None
    LOW, HIGH = 150_000.0, 700_000.0
    if admin <= LOW:
        return 1.0
    if admin >= HIGH:
        return 0.0
    return round(1.0 - (admin - LOW) / (HIGH - LOW), 3)


def _score_upz(busqueda: dict, anuncio: dict) -> float | None:
    """Match de UPZ/zona: 1.0 si el inmueble está en alguna UPZ/UPL deseada, 0.0 si no.
    Devuelve None si la búsqueda no especificó UPZ (no aplica al score).
    Traduce UPZ pre-2023 del inmueble a UPL post-2023."""
    upz_deseadas = busqueda.get("upz") or []
    if not upz_deseadas:
        return None

    a_upz = anuncio.get("upz")
    if not a_upz:
        return 1.0  # Sin dato: no penalizamos

    from services.busqueda import _upz_a_upl_norm, _sin_tildes
    a_upl_norm = _upz_a_upl_norm(str(a_upz))
    ubicacion_norm = _sin_tildes((anuncio.get("ubicacion_texto") or "").lower())
    texto = ubicacion_norm + " " + a_upl_norm + " " + _sin_tildes(str(a_upz).lower())

    for upz in upz_deseadas:
        b_norm = _sin_tildes(str(upz).strip().lower())
        if b_norm in texto or b_norm in a_upl_norm or a_upl_norm in b_norm:
            return 1.0
    return 0.0


def solicitar_pesos_llm_v2(busqueda: dict, cliente: dict | None = None) -> dict:
    """Versión expandida: asigna pesos a 13 dimensiones unificadas (5 H3 + 8 inmueble)
    que suman 1.0. Guía al LLM para dar más peso a criterios difíciles de satisfacer
    (UPZ, comodidades, habitaciones) y menos a los triviales (tipo, antigüedad)."""
    cliente = cliente or {}
    pregunta = (busqueda.get("pregunta_abierta") or "").strip()
    estrato = busqueda.get("estrato_objetivo") or []
    uso = busqueda.get("uso_previsto") or []
    ingreso = cliente.get("ingreso_mensual_cop") or 0
    coms_rel = _texto_lista(busqueda.get("comodidades_relevantes"), "ninguna")
    coms_ind = _texto_lista(busqueda.get("comodidades_indispensables"), "ninguna")
    hay_upz = bool(busqueda.get("upz"))
    hay_coms_rel = bool(busqueda.get("comodidades_relevantes"))
    hay_coms_ind = bool(busqueda.get("comodidades_indispensables"))

    prompt = f"""Eres un sistema de scoring inmobiliario personalizado. Dado el perfil del cliente,
asigna pesos (0.0–1.0, sumando EXACTAMENTE 1.0) a 13 dimensiones de evaluación.

PERFIL DEL CLIENTE:
- Qué busca (texto libre): {pregunta or 'no especificado'}
- Estrato objetivo: {estrato}
- Uso previsto: {_texto_lista(uso)}
- Presupuesto: {busqueda.get('presupuesto_min', 0):,.0f} a {busqueda.get('presupuesto_max', 0):,.0f} COP
- Ingreso mensual: {ingreso:,.0f} COP/mes
- Habitaciones mínimas: {busqueda.get('habitaciones_min', 'no especificado')}
- Baños mínimos: {busqueda.get('banos_min', 'no especificado')}
- UPZ/zona deseada: {_texto_lista(busqueda.get('upz'), 'no especificada')}
- Comodidades relevantes (opcionales): {coms_rel}
- Comodidades indispensables: {coms_ind}

CRITERIOS FÁCILES DE SATISFACER → asigna peso BAJO (0.02–0.06 cada uno):
- tipo_vivienda: casi todos los anuncios son del tipo correcto
- antiguedad: la mayoría de inmuebles no tienen restricción

CRITERIOS DIFÍCILES DE SATISFACER → asigna peso ALTO (según importancia):
- upz: pocos inmuebles están exactamente en la zona/UPZ deseada {'(sí aplica)' if hay_upz else '(no aplica → peso 0)'}
- comodidades_relevantes: varía mucho entre inmuebles {'(sí aplica)' if hay_coms_rel else '(no aplica → peso 0)'}
- comodidades_indispensables: filtro crítico {'(sí aplica)' if hay_coms_ind else '(no aplica → peso 0)'}
- habitaciones_banos: requisito mínimo difícil de cumplir exactamente
- administracion: costo que muchos inmuebles tienen alto o sin dato {'→ peso bajo si ingreso > 15M COP/mes' if ingreso > 15_000_000 else ''}

REGLAS DE PERSONALIZACIÓN POR PERFIL:
- Texto menciona parques/verde/naturaleza/aire → aumenta s_entorno_verde significativamente
- Texto menciona comercio/tiendas/restaurantes/servicios → aumenta s_comercio significativamente
- Texto menciona seguridad/tranquilidad → aumenta s_seguridad
- Texto menciona movilidad reducida/adulto mayor/pensionado → aumenta comodidades_relevantes mucho
- Texto menciona hijos/familia/niños → aumenta habitaciones_banos
- Texto menciona trabajo remoto/home office → reduce s_transporte
- Ingreso > 15M COP/mes → reduce presupuesto y administracion

DIMENSIONES DEL SECTOR H3 (datos del entorno urbano):
- s_seguridad: seguridad ciudadana, hurtos
- s_transporte: TransMilenio, Metro, SITP, ciclovías
- s_comercio: supermercados, centros comerciales
- s_entorno_verde: parques, árboles, recreación
- s_estrato_valor: estrato del sector, avalúo, colegios

DIMENSIONES DEL INMUEBLE:
- presupuesto: si el precio entra en el rango del cliente
- estrato: si el estrato coincide con el deseado
- habitaciones_banos: si cumple mínimo de habitaciones y baños
- upz: si está en la UPZ/zona deseada
- tipo_vivienda: si el tipo coincide (FÁCIL — peso bajo)
- antiguedad: si la antigüedad es aceptable (FÁCIL — peso bajo)
- comodidades_relevantes: fracción de comodidades opcionales presentes
- administracion: costo mensual de administración

Responde ÚNICAMENTE con JSON con exactamente estas 13 claves, sin texto adicional:
{{"s_seguridad":0.XX,"s_transporte":0.XX,"s_comercio":0.XX,"s_entorno_verde":0.XX,"s_estrato_valor":0.XX,"presupuesto":0.XX,"estrato":0.XX,"habitaciones_banos":0.XX,"upz":0.XX,"tipo_vivienda":0.XX,"antiguedad":0.XX,"comodidades_relevantes":0.XX,"administracion":0.XX}}"""

    EXPECTED = ["s_seguridad", "s_transporte", "s_comercio", "s_entorno_verde", "s_estrato_valor",
                "presupuesto", "estrato", "habitaciones_banos", "upz",
                "tipo_vivienda", "antiguedad", "comodidades_relevantes", "administracion"]
    DEFAULT = {
        "s_seguridad": 0.11, "s_transporte": 0.08, "s_comercio": 0.10,
        "s_entorno_verde": 0.11, "s_estrato_valor": 0.08,
        "presupuesto": 0.10, "estrato": 0.07, "habitaciones_banos": 0.10,
        "upz": 0.09 if hay_upz else 0.0,
        "tipo_vivienda": 0.03, "antiguedad": 0.03,
        "comodidades_relevantes": 0.07 if hay_coms_rel else 0.0,
        "administracion": 0.03,
    }
    # Renormalizar defaults por si algunas son 0
    total_def = sum(DEFAULT.values())
    if total_def > 0:
        DEFAULT = {k: round(v / total_def, 4) for k, v in DEFAULT.items()}

    try:
        respuesta = _client.messages.create(
            model=config.CLAUDE_FAST,
            max_tokens=320,
            messages=[{"role": "user", "content": prompt}],
        )
        texto = "".join(b.text for b in respuesta.content if b.type == "text").strip()
        if texto.startswith("```"):
            texto = texto.split("```")[1]
            if texto.lower().startswith("json"):
                texto = texto[4:]
        pesos = json.loads(texto)
        total = sum(pesos.values())
        if total > 0:
            pesos = {k: round(v / total, 4) for k, v in pesos.items()}
        for k in EXPECTED:
            if k not in pesos:
                pesos[k] = DEFAULT.get(k, 0.0)
        # Forzar a 0 las que no aplican
        if not hay_upz:
            pesos["upz"] = 0.0
        if not hay_coms_rel:
            pesos["comodidades_relevantes"] = 0.0
        return pesos
    except Exception:
        return dict(DEFAULT)


def calcular_scores_llm(busqueda: dict, anuncios: list[dict]) -> dict[int, dict]:
    """Le pide a Claude un score 0-1 para CADA anuncio en un solo llamado
    (no uno por inmueble, para no disparar costo/tiempo por busqueda),
    considerando los criterios completos de la busqueda y los datos de
    cada inmueble. Devuelve {anuncio_id: {"score": float, "razon": str}}.

    Si algo falla (API, parseo de la respuesta, etc.) devuelve un dict
    vacio - quien llama esta funcion debe caer al score heuristico
    (calcular_score) para los anuncios que no queden cubiertos, no debe
    asumir que todos los ids van a estar presentes."""
    if not anuncios:
        return {}

    lista_inmuebles = "\n".join(_resumir_anuncio_para_prompt(a) for a in anuncios)

    prompt = f"""Eres un asesor inmobiliario de Casa en Casa evaluando qué tan bien encajan
inmuebles con el perfil de un cliente. Usa una escala ESTRICTA y DIFERENCIADORA:

ESCALA OBLIGATORIA:
- 0.90–1.00: match casi perfecto — cumple UPZ, habitaciones, comodidades, precio Y entorno
- 0.75–0.89: muy buena opción — cumple lo importante, uno o dos puntos de mejora menores
- 0.60–0.74: opción válida — cumple requisitos mínimos pero faltan cosas relevantes
- 0.45–0.59: opción mediocre — cumple lo básico (presupuesto/tipo) pero falla en criterios clave
- 0.30–0.44: opción débil — varios criterios importantes sin cumplir
- 0.00–0.29: no recomendable — falla en requisitos fundamentales

CRITERIOS DE BÚSQUEDA DEL CLIENTE:
- Municipios de interés: {_texto_lista([m.get('municipio') for m in (busqueda.get('municipios') or [])])}
- UPZ/zona deseada: {_texto_lista(busqueda.get('upz'), 'no especificada')}
- Presupuesto: {(busqueda.get('presupuesto_min') or 0):,.0f} a {(busqueda.get('presupuesto_max') or 0):,.0f} COP
- Estrato(s) objetivo: {_texto_lista(busqueda.get('estrato_objetivo'))}
- Tipo de vivienda: {busqueda.get('tipo_vivienda')}, estado deseado: {busqueda.get('estado_deseado')}
- Antigüedad deseada: {_texto_rango_anios(busqueda.get('antiguedad_anios_min'), busqueda.get('antiguedad_anios_max'))}
- Habitaciones mínimas: {busqueda.get('habitaciones_min')} (exactas: {busqueda.get('habitaciones_exactas')})
- Baños mínimos: {busqueda.get('banos_min')} (exactos: {busqueda.get('banos_exactos')})
- Uso previsto: {_texto_lista(busqueda.get('uso_previsto'))}
- Comodidades relevantes: {_texto_lista(busqueda.get('comodidades_relevantes'), 'no especificadas')}
- Comodidades indispensables: {_texto_lista(busqueda.get('comodidades_indispensables'), 'ninguna')}
- Qué busca el cliente (texto libre): {busqueda.get('pregunta_abierta') or 'no especificado'}

INMUEBLES A EVALUAR (incluyen Sub-Scores del sector 0.0–1.0 y POIs cercanos):
{lista_inmuebles}

REGLAS DE PENALIZACIÓN EXPLÍCITA — aplica estas deducciones antes de cualquier otro ajuste:
1. UPZ/UPL/zona NO coincide con la deseada (nota: UPZs tradicionales como Galerías, La Esmeralda, Quinta Paredes, etc. forman parte de la UPL Teusaquillo; si el inmueble pertenece a la UPL deseada, SÍ COINCIDE y NO debes penalizar) → descuenta 0.18 del score máximo posible
2. Cada comodidad RELEVANTE faltante → descuenta 0.05 (p.ej. 3 faltantes = -0.15)
3. Habitaciones < mínimo requerido → score máximo 0.35 (requisito duro)
4. Baños < mínimo requerido → score máximo 0.35 (requisito duro)
5. Administración > $500.000/mes → descuenta 0.08
6. Administración > $700.000/mes → descuenta 0.15
7. Comodidad INDISPENSABLE faltante → score máximo 0.25 (muy raro dado el filtro previo, pero verifica)

IMPORTANTE:
- Tipo de vivienda y antigüedad son criterios triviales — NO les des protagonismo en el score
- UPZ, comodidades y habitaciones son los criterios que realmente diferencian inmuebles
- Si evaluás un solo inmueble, usa la escala completa igual — no inflés artificialmente
- Diferencia de verdad: dos inmuebles similares pero en diferente UPZ deben tener scores distintos

Responde ÚNICAMENTE con un array JSON, sin texto adicional, con este formato:
[{{"id": 123, "score": 0.72, "razon": "explicación concreta de una línea mencionando qué cumple y qué no"}}]
"""

    try:
        respuesta = _client.messages.create(
            model=config.CLAUDE_SMART,
            max_tokens=config.MAX_TOKENS_SCORING,
            messages=[{"role": "user", "content": prompt}],
        )
        texto = "".join(b.text for b in respuesta.content if b.type == "text").strip()
        if texto.startswith("```"):
            texto = texto.split("```")[1]
            if texto.lower().startswith("json"):
                texto = texto[4:]
        datos = json.loads(texto)
        return {
            int(item["id"]): {"score": round(float(item["score"]), 2), "razon": item.get("razon", "")}
            for item in datos
        }
    except Exception:
        return {}


def rankear_candidatos_llm(busqueda: dict, anuncios: list[dict], n: int = 5) -> list[dict]:
    """Pipeline de scoring híbrido:
    1. Calcula los 5 Sub-Scores H3 para cada candidato (Python puro, <1ms/anuncio).
    2. Solicita al LLM los pesos personalizados según el perfil del cliente (1 llamado ultrarrápido).
    3. Calcula el score global ponderado matemáticamente en Python.
    4. Llama al LLM de evaluación cualitativa SOLO para el Top N, con contexto enriquecido.
    Devuelve la lista completa ordenada de mejor a peor score."""

    # 1. Sub-Scores H3 para todos los candidatos
    for anuncio in anuncios:
        sub = calcular_sub_scores(anuncio)
        anuncio["_sub_scores"] = sub

    # 2. Pesos LLM personalizados (1 llamado ultrarrápido)
    pesos_llm = solicitar_pesos_llm(busqueda)

    # 3. Score final ponderado en Python
    for anuncio in anuncios:
        sub = anuncio.get("_sub_scores") or {}
        score_inmueble = calcular_score_inmueble(busqueda, anuncio)
        total = 0.0
        for dim_key in ["s_seguridad", "s_transporte", "s_comercio", "s_entorno_verde", "s_estrato_valor"]:
            val = sub.get(dim_key)
            peso = pesos_llm.get(dim_key, PESOS_GLOBALES_DEFAULT[dim_key])
            if val is not None:
                total += float(val) * peso
        total += score_inmueble * pesos_llm.get("_score_inmueble", PESOS_GLOBALES_DEFAULT["_score_inmueble"])
        anuncio["_score_hibrido"] = round(total, 4)
        anuncio["_pesos_usados"] = pesos_llm

    # Ordenar por score híbrido
    rankeados = sorted(anuncios, key=lambda a: a.get("_score_hibrido", 0), reverse=True)

    # 4. LLM cualitativo solo para Top N
    top_anuncios = rankeados[:n]
    scores_llm = calcular_scores_llm(busqueda, top_anuncios)

    resultados = []
    for i, anuncio in enumerate(rankeados):
        is_top = i < n
        info_llm = scores_llm.get(anuncio["id"]) if is_top else None

        if info_llm is not None:
            score_final = info_llm["score"]
            razon = info_llm["razon"]
        else:
            score_final = anuncio["_score_hibrido"]
            razon = ""

        resultados.append({
            **anuncio,
            "score": score_final,
            "score_desglose": {
                "sub_scores": anuncio.get("_sub_scores"),
                "score_inmueble": calcular_score_inmueble(busqueda, anuncio),
                "pesos_llm": anuncio.get("_pesos_usados"),
                "razon_llm": razon,
            },
        })

    return resultados
