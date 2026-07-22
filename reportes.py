from io import BytesIO

import anthropic
import markdown
from dotenv import load_dotenv
from xhtml2pdf import pisa

import config
import db

load_dotenv()

_client = anthropic.Anthropic()  # lee ANTHROPIC_API_KEY del entorno

PROMPT_TEMPLATE = """Eres un asesor inmobiliario de Casa en Casa. Genera un reporte de una
página para el siguiente cliente y vivienda candidata.

CLIENTE:
- Vive en {ciudad_residencia}, {pais_residencia}
- Ingreso: {ingreso_mensual_cop:,.0f} COP/mes (~{ingreso_mensual:,.0f} {ingreso_moneda})
- Ahorro disponible para cuota: {ahorro_mensual_cop:,.0f} COP/mes
- Busca: {tipo_vivienda}, {estado_deseado}, en {ciudades_interes_txt}
- Presupuesto: {presupuesto_min:,.0f} a {presupuesto_max:,.0f} COP
- Estrato objetivo: {estrato_objetivo}, mínimo {habitaciones_min} habitaciones

VIVIENDA:
Precio: {precio_venta:,.0f} COP | Área: {area_metros} m² | Habitaciones: {habitaciones} |
Baños: {banos} | Estrato: {estrato} | Ubicación: {ubicacion_texto}
Descripción original del anuncio: {descripcion}
Comodidades: {comodidades}

ENTORNO:
- Estrato promedio del sector (200m): {estrato_promedio_200m}
- Distancia a TransMilenio: {dist_tm}m | SITP: {dist_sitp}m | Ciclorruta: {dist_ciclo}m

SCORE CALCULADO: {score} / 1.0
DESGLOSE: {desglose}

Escribe un reporte de máximo 400 palabras, en español, con estas secciones:
1. Resumen (2-3 líneas)
2. Por qué esta vivienda encaja con este cliente (usa el desglose del score, sé concreto)
3. El entorno (transporte, estrato, contexto del sector)
4. Consideraciones a tener en cuenta (si algo no es perfecto, dilo — no vendas humo)
"""


def _formatear_desglose(componentes: dict) -> str:
    return ", ".join(f"{k}: {v:.2f}" for k, v in componentes.items())


def _valor_o(v, default="no especificado"):
    return v if v not in (None, "") else default


def _texto_lista(valores, vacio="no especificado") -> str:
    if not valores:
        return vacio
    return ", ".join(str(v) for v in valores)


def _armar_contexto(cliente: dict, anuncio: dict, score: dict) -> dict:
    municipios = cliente.get("municipios") or []
    ciudades_txt = _texto_lista([m.get("municipio") for m in municipios], "Bogotá")

    return {
        "ciudad_residencia": _valor_o(cliente.get("ciudad_residencia")),
        "pais_residencia": _valor_o(cliente.get("pais_residencia")),
        "ingreso_mensual_cop": cliente.get("ingreso_mensual_cop") or 0,
        "ingreso_mensual": cliente.get("ingreso_mensual") or 0,
        "ingreso_moneda": _valor_o(cliente.get("ingreso_moneda")),
        "ahorro_mensual_cop": cliente.get("ahorro_mensual_cop") or 0,
        "tipo_vivienda": _valor_o(cliente.get("tipo_vivienda")),
        "estado_deseado": _valor_o(cliente.get("estado_deseado")),
        "ciudades_interes_txt": ciudades_txt,
        "presupuesto_min": cliente.get("presupuesto_min") or 0,
        "presupuesto_max": cliente.get("presupuesto_max") or 0,
        "estrato_objetivo": _texto_lista(cliente.get("estrato_objetivo")),
        "habitaciones_min": _valor_o(cliente.get("habitaciones_min"), 0),
        "precio_venta": anuncio.get("precio_venta") or 0,
        "area_metros": _valor_o(anuncio.get("area_metros")),
        "habitaciones": _valor_o(anuncio.get("habitaciones")),
        "banos": _valor_o(anuncio.get("banos")),
        "estrato": _valor_o(anuncio.get("estrato")),
        "ubicacion_texto": _valor_o(anuncio.get("ubicacion_texto")),
        "descripcion": _valor_o(anuncio.get("descripcion"), "sin descripción"),
        "comodidades": _valor_o(anuncio.get("comodidades"), "no especificadas"),
        "estrato_promedio_200m": _valor_o(anuncio.get("estrato_promedio_200m")),
        "dist_tm": _valor_o(anuncio.get("dist_tm")),
        "dist_sitp": _valor_o(anuncio.get("dist_sitp")),
        "dist_ciclo": _valor_o(anuncio.get("dist_ciclo")),
        "score": score["total"],
        "desglose": _formatear_desglose(score["componentes"]),
    }


def generar_reporte(cliente: dict, anuncio: dict, score: dict) -> str:
    contexto = _armar_contexto(cliente, anuncio, score)
    prompt = PROMPT_TEMPLATE.format(**contexto)

    respuesta = _client.messages.create(
        model=config.CLAUDE_SMART,
        max_tokens=config.MAX_TOKENS_REPORTE,
        messages=[{"role": "user", "content": prompt}],
    )
    # respuesta.content puede traer bloques que no son de texto (ej. thinking)
    # antes del bloque de texto real — no asumir que content[0] es el texto.
    texto = "".join(b.text for b in respuesta.content if b.type == "text")
    return _envolver_en_html(texto, cliente, anuncio, score)


def html_a_pdf(html: str) -> bytes:
    buffer = BytesIO()
    pisa.CreatePDF(html, dest=buffer)
    return buffer.getvalue()


def crear_y_guardar_reporte(cliente: dict, anuncio: dict, score: dict) -> int:
    """Genera el reporte con Claude y lo persiste con expires_at a 15 dias
    (calculado por Postgres en db.guardar_reporte, no aca)."""
    html = generar_reporte(cliente, anuncio, score)
    return db.guardar_reporte(cliente["id"], anuncio["id"], score["total"], html)


def _envolver_en_html(texto: str, cliente: dict, anuncio: dict, score: dict) -> str:
    html_contenido = markdown.markdown(texto)
    return f"""
    <html><head><meta charset="utf-8"></head>
    <body style="font-family: Montserrat, sans-serif; color: #2F3670; max-width: 700px;">
      <h1 style="color:#2F3670;">Reporte de vivienda — {cliente.get('nombre', '')}</h1>
      <p><strong>Score:</strong> {score['total']:.2f} / 1.0</p>
      {html_contenido}
      <p><a href="{anuncio.get('url', '')}">Ver anuncio original</a></p>
    </body></html>
    """
