import json
import os

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
    objetivo = cliente.get("estrato_objetivo")
    real = anuncio.get("estrato_promedio_200m")
    if real is None:
        real = anuncio.get("estrato")
    if objetivo is None or real is None:
        return 0.5
    return max(0.0, 1 - abs(objetivo - real) / 3)


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
