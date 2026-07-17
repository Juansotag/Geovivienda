import os
import threading

from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, redirect, url_for, Response

import db
import fx
import scoring
import reportes
import busqueda
from scheduler import iniciar_scheduler

load_dotenv()

app = Flask(__name__)

CIUDADES = [
    {"slug": "bogota", "nombre": "Bogotá", "activa": True},
    {"slug": "medellin", "nombre": "Medellín", "activa": False},
    {"slug": "cali", "nombre": "Cali", "activa": False},
    {"slug": "barranquilla", "nombre": "Barranquilla", "activa": False},
    {"slug": "bucaramanga", "nombre": "Bucaramanga", "activa": False},
    {"slug": "santa-marta", "nombre": "Santa Marta", "activa": False},
    {"slug": "tunja", "nombre": "Tunja", "activa": False},
    {"slug": "popayan", "nombre": "Popayán", "activa": False},
    {"slug": "villavicencio", "nombre": "Villavicencio", "activa": False},
    {"slug": "ibague", "nombre": "Ibagué", "activa": False},
    {"slug": "neiva", "nombre": "Neiva", "activa": False},
    {"slug": "manizales", "nombre": "Manizales", "activa": False},
    {"slug": "armenia", "nombre": "Armenia", "activa": False},
    {"slug": "pereira", "nombre": "Pereira", "activa": False},
    {"slug": "monteria", "nombre": "Montería", "activa": False},
]


@app.route("/")
def index():
    return redirect(url_for("login"))


@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/perfil")
def perfil():
    return render_template("perfil.html", activo="perfil")


@app.route("/clientes")
def clientes():
    return render_template("clientes_lista.html", activo="clientes", clientes=db.listar_clientes())


@app.route("/clientes/nuevo", methods=["GET", "POST"])
def cliente_nuevo():
    if request.method == "GET":
        return render_template("cliente_form.html", activo="clientes", ciudades=CIUDADES)

    moneda = request.form["ingreso_moneda"]
    ingreso = float(request.form["ingreso_mensual"])
    ahorro = float(request.form["ahorro_mensual"])

    cliente_id = db.insertar_cliente({
        "nombre": request.form["nombre"],
        "pais_residencia": request.form["pais_residencia"],
        "ciudad_residencia": request.form["ciudad_residencia"],
        "ingreso_mensual": ingreso,
        "ingreso_moneda": moneda,
        "ingreso_mensual_cop": fx.convertir_a_cop(ingreso, moneda),
        "ahorro_mensual_cop": fx.convertir_a_cop(ahorro, moneda),
        "ciudades_interes": request.form.getlist("ciudades_interes") or ["bogota"],
        "tipo_vivienda": request.form["tipo_vivienda"],
        "estado_deseado": request.form["estado_deseado"],
        "habitaciones_min": int(request.form["habitaciones_min"]),
        "banos_min": int(request.form["banos_min"]),
        "estrato_objetivo": int(request.form["estrato_objetivo"]),
        "presupuesto_min": int(request.form["presupuesto_min"]),
        "presupuesto_max": int(request.form["presupuesto_max"]),
    })
    return redirect(url_for("cliente_detalle", cliente_id=cliente_id))


@app.route("/clientes/<int:cliente_id>")
def cliente_detalle(cliente_id):
    cliente = db.obtener_cliente(cliente_id)
    return render_template("cliente_detalle.html", activo="clientes", cliente=cliente)


@app.route("/clientes/<int:cliente_id>/resultados")
def cliente_resultados(cliente_id):
    cliente = db.obtener_cliente(cliente_id)
    busqueda_id = request.args.get("busqueda_id", type=int)
    resultados = db.obtener_resultados_busqueda(busqueda_id) if busqueda_id else []
    return render_template("resultados.html", activo="clientes", cliente=cliente, resultados=resultados)


@app.route("/api/fx")
def api_fx():
    monto = request.args.get("monto", type=float)
    moneda = request.args.get("moneda", default="EUR")
    if monto is None:
        return jsonify({"cop": None})
    try:
        return jsonify({"cop": fx.convertir_a_cop(monto, moneda)})
    except ValueError:
        return jsonify({"cop": None})


@app.route("/api/scrape", methods=["POST"])
def api_scrape():
    data = request.json
    cliente_id = data["cliente_id"]
    portales = data.get("portales") or ["fincaraiz", "metrocuadrado"]
    cantidad = int(data.get("cantidad", 30))

    cliente = db.obtener_cliente(cliente_id)
    if not cliente:
        return jsonify({"status": "error", "message": "Cliente no encontrado"}), 404

    busqueda_id = db.crear_busqueda(cliente_id, portales, cantidad)
    thread = threading.Thread(
        target=busqueda.ejecutar_busqueda_completa,
        args=(cliente, portales, cantidad, busqueda_id),
        daemon=True,
    )
    thread.start()
    return jsonify({"status": "started", "busqueda_id": busqueda_id})


@app.route("/api/status")
def api_status():
    busqueda_id = request.args.get("busqueda_id", type=int)
    since = request.args.get("since", default=0, type=int)
    b = db.obtener_busqueda(busqueda_id)
    if not b:
        return jsonify({"status": "error", "logs": [], "total_logs": 0})
    logs = b["log"] or []
    return jsonify({"status": b["status"], "logs": logs[since:], "total_logs": len(logs)})


@app.route("/api/reportes/generar", methods=["POST"])
def api_generar_reporte():
    data = request.json
    cliente = db.obtener_cliente(data["cliente_id"])
    if not cliente:
        return jsonify({"status": "error", "message": "Cliente no encontrado"}), 404

    anuncio = None
    if data.get("anuncio_id"):
        anuncio = db.buscar_anuncio_por_id(data["anuncio_id"])
    elif data.get("url"):
        anuncio = db.buscar_anuncio_por_url(data["url"])

    if not anuncio:
        return jsonify({
            "status": "error",
            "message": "No encontramos ese anuncio en la base — solo se puede generar reporte de anuncios que ya salieron en una búsqueda previa.",
        }), 404

    score = scoring.calcular_score(cliente, anuncio)
    reporte_id = reportes.crear_y_guardar_reporte(cliente, anuncio, score)
    return jsonify({"reporte_id": reporte_id})


@app.route("/reportes/<int:reporte_id>/pdf")
def descargar_reporte_pdf(reporte_id):
    reporte = db.obtener_reporte(reporte_id)
    if not reporte:
        return "Reporte no encontrado", 404
    pdf_bytes = reportes.html_a_pdf(reporte["contenido_html"])
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=reporte_{reporte_id}.pdf"},
    )


iniciar_scheduler()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
