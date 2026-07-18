import json
import os

import anthropic
from dotenv import load_dotenv

load_dotenv()
_client = anthropic.Anthropic()

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(_BASE_DIR, "score_config.json"), encoding="utf-8") as f:
    PESOS = json.load(f)


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
    # se toma la mejor coincidencia entre cualquiera de los estratos elegidos
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


def calcular_score(cliente: dict, anuncio: dict) -> dict:
    componentes = {
        "presupuesto": _score_presupuesto(cliente, anuncio),
        "estrato": _score_estrato(cliente, anuncio),
        "habitaciones_banos": _score_habitaciones_banos(cliente, anuncio),
        "transporte": _score_transporte(anuncio),
        "tipo_vivienda": _score_tipo_vivienda(cliente, anuncio),
        "antiguedad_estado": _score_antiguedad_estado(anuncio),
    }
    total = sum(componentes[k] * PESOS[k] for k in PESOS)
    return {"total": round(total, 3), "componentes": componentes}


def rankear_candidatos(cliente: dict, anuncios: list[dict]) -> list[dict]:
    resultados = []
    for anuncio in anuncios:
        score = calcular_score(cliente, anuncio)
        resultados.append({**anuncio, "score": score["total"], "score_desglose": score["componentes"]})
    return sorted(resultados, key=lambda r: r["score"], reverse=True)


def top_n(candidatos_rankeados: list[dict], n: int = 5) -> list[dict]:
    return candidatos_rankeados[:n]


def _resumir_anuncio_para_prompt(a: dict) -> str:
    precio = a.get("precio_venta") or 0
    admin = a.get("administracion")
    admin_txt = f"${admin:,.0f} COP/mes" if admin else "no especificada"
    return (
        f"- id={a['id']}: {a.get('tipo_inmueble')}, {a.get('estado')}, antigüedad: {a.get('antiguedad') or 'no especificada'}, "
        f"{a.get('habitaciones')} hab, {a.get('banos')} baños, {a.get('parqueaderos') or 0} parqueadero(s), {a.get('area_metros')} m², "
        f"estrato {a.get('estrato')} (estrato del sector 200m: {a.get('estrato_promedio_200m')}), "
        f"${precio:,.0f} COP, administración: {admin_txt}, ubicación: {a.get('ubicacion_texto')}, "
        f"distancia a TransMilenio: {a.get('dist_tm')}m, distancia a SITP: {a.get('dist_sitp')}m, distancia a ciclorruta: {a.get('dist_ciclo')}m, "
        f"comodidades: {a.get('comodidades') or 'no especificadas'}, "
        f"descripción: {(a.get('descripcion') or '')[:200]}"
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

    prompt = f"""Eres un asesor inmobiliario de Casa en Casa evaluando que tan bien encajan
varios inmuebles con el perfil de un cliente especifico.

CRITERIOS DE BUSQUEDA DEL CLIENTE:
- Municipios de interés: {_texto_lista([m.get('municipio') for m in (busqueda.get('municipios') or [])])}
- Presupuesto: {(busqueda.get('presupuesto_min') or 0):,.0f} a {(busqueda.get('presupuesto_max') or 0):,.0f} COP
- Estrato(s) objetivo: {_texto_lista(busqueda.get('estrato_objetivo'))}
- Tipo de vivienda: {busqueda.get('tipo_vivienda')}, estado deseado: {busqueda.get('estado_deseado')}
- Antigüedad deseada: {_texto_rango_anios(busqueda.get('antiguedad_anios_min'), busqueda.get('antiguedad_anios_max'))}
- Habitaciones mínimas: {busqueda.get('habitaciones_min')} (exactas: {busqueda.get('habitaciones_exactas')})
- Baños mínimos: {busqueda.get('banos_min')} (exactos: {busqueda.get('banos_exactos')})
- Uso previsto: {_texto_lista(busqueda.get('uso_previsto'))}
- Comodidades relevantes (pesan en el score, no son obligatorias): {_texto_lista(busqueda.get('comodidades_relevantes'), "no especificadas")}
- Comodidades indispensables: {_texto_lista(busqueda.get('comodidades_indispensables'), "ninguna")} (nota: todos los inmuebles de esta lista YA fueron filtrados y cumplen estas comodidades, no necesitas verificarlas ni penalizar por ellas)
- Qué busca en la vivienda y su entorno (respuesta abierta del cliente): {busqueda.get('pregunta_abierta') or 'no especificado'}

INMUEBLES A EVALUAR:
{lista_inmuebles}

Para cada inmueble, asigna un score de compatibilidad entre 0.0 y 1.0 (usa 2 decimales),
donde 1.0 es un match perfecto y 0.0 no encaja para nada. Considera TODOS los criterios,
no solo presupuesto/estrato — también el entorno, las comodidades, y lo que el cliente
dijo textualmente que busca. Diferencia de verdad entre inmuebles: si dos inmuebles tienen
diferencias reales entre sí (ubicación, comodidades, estado), sus scores deben reflejarlo,
no le des el mismo número a todos por comodidad.

IMPORTANTE - restricciones duras: habitaciones mínimas y baños mínimos NO son una
preferencia más entre varias, son un requisito. Si "exactas"/"exactos" es true, el
inmueble debe tener EXACTAMENTE ese número; si es false, debe tener ESE NÚMERO O MÁS.
Un inmueble que incumple habitaciones mínimas o baños mínimos no puede pasar de 0.35
de score sin importar qué tan bien encaje en todo lo demás (los datos del scraper a
veces no filtran bien esto, así que verifícalo tú mismo con los datos de cada inmueble
antes de puntuar). La antigüedad y las comodidades indispensables, en cambio, ya
fueron aplicadas como filtro duro ANTES de que este inmueble llegara a tu evaluación
- no las vuelvas a verificar ni las penalices, enfócate en diferenciar por lo demás.

Responde ÚNICAMENTE con un array JSON, sin texto adicional antes o después, con este
formato exacto:
[{{"id": 123, "score": 0.85, "razon": "explicación breve de una línea"}}, ...]
"""

    try:
        respuesta = _client.messages.create(
            model="claude-sonnet-5",
            max_tokens=4000,
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


def rankear_candidatos_llm(busqueda: dict, anuncios: list[dict]) -> list[dict]:
    """Igual que rankear_candidatos, pero usa el score del LLM cuando esta
    disponible y cae al heuristico anuncio-por-anuncio para los que el
    LLM no cubrio (llamada fallida, respuesta incompleta, etc.)."""
    scores_llm = calcular_scores_llm(busqueda, anuncios)

    resultados = []
    for anuncio in anuncios:
        info_llm = scores_llm.get(anuncio["id"])
        if info_llm is not None:
            resultados.append({
                **anuncio,
                "score": info_llm["score"],
                "score_desglose": {"razon_llm": info_llm["razon"]},
            })
        else:
            score = calcular_score(busqueda, anuncio)
            resultados.append({**anuncio, "score": score["total"], "score_desglose": score["componentes"]})

    return sorted(resultados, key=lambda r: r["score"], reverse=True)
