import os
import csv
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


# Cargar DIVIPOLA desde CSV
_divipola_data = {}
csv_path = os.path.join("geodata", "DIVIPOLA-_Códigos_municipios_20260717.csv")
if os.path.exists(csv_path):
    with open(csv_path, mode="r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)  # omitir cabecera
        for row in reader:
            if len(row) >= 4:
                cod_dept, name_dept, cod_mun, name_mun = row[0], row[1], row[2], row[3]
                name_dept_clean = name_dept.strip().title()
                name_mun_clean = name_mun.strip().title()
                if name_dept_clean not in _divipola_data:
                    _divipola_data[name_dept_clean] = []
                _divipola_data[name_dept_clean].append({
                    "nombre": name_mun_clean,
                    "codigo": cod_mun.strip()
                })

# Ordenar departamentos y municipios
for dept in _divipola_data:
    _divipola_data[dept] = sorted(_divipola_data[dept], key=lambda x: x["nombre"])
_divipola_data = dict(sorted(_divipola_data.items()))


@app.route("/api/divipola")
def api_divipola():
    return jsonify(_divipola_data)


@app.context_processor
def inject_perfil():
    return dict(perfil=db.obtener_perfil())


@app.route("/")
def index():
    return render_template("landing.html")


@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/logout")
def logout():
    return redirect(url_for("login"))


@app.route("/perfil", methods=["GET", "POST"])
def perfil():
    if request.method == "POST":
        db.actualizar_perfil(
            nombre=request.form["nombre"],
            correo=request.form["correo"],
            cargo=request.form["cargo"]
        )
        return redirect(url_for("clientes"))
    p = db.obtener_perfil()
    return render_template("perfil.html", activo="perfil", perfil=p)


@app.route("/clientes")
def clientes():
    return render_template("clientes_lista.html", activo="clientes", clientes=db.listar_clientes())


@app.route("/clientes/nuevo", methods=["GET", "POST"])
def cliente_nuevo():
    if request.method == "GET":
        return render_template("cliente_form.html", activo="clientes", ciudades=CIUDADES, cliente=None)

    moneda = request.form["ingreso_moneda"]
    ingreso = float(request.form["ingreso_mensual"])
    ahorro = float(request.form["ahorro_mensual"])

    cliente_id = db.insertar_cliente({
        "nombre": request.form["nombre"],
        "pais_residencia": request.form["pais_residencia"],
        "ciudad_residencia": request.form["ciudad_residencia"],
        "tipo_identificacion": request.form["tipo_identificacion"],
        "numero_identificacion": request.form["numero_identificacion"],
        "ingreso_mensual": ingreso,
        "ingreso_moneda": moneda,
        "ingreso_mensual_cop": fx.convertir_a_cop(ingreso, moneda),
        "ahorro_mensual": ahorro,
        "ahorro_mensual_cop": fx.convertir_a_cop(ahorro, moneda),
    })
    return redirect(url_for("cliente_detalle", cliente_id=cliente_id))


@app.route("/clientes/<int:cliente_id>/editar", methods=["GET", "POST"])
def cliente_editar(cliente_id):
    cliente = db.obtener_cliente(cliente_id)
    if not cliente:
        return "Cliente no encontrado", 404
        
    if request.method == "GET":
        return render_template("cliente_form.html", activo="clientes", ciudades=CIUDADES, cliente=cliente)

    moneda = request.form["ingreso_moneda"]
    ingreso = float(request.form["ingreso_mensual"])
    ahorro = float(request.form["ahorro_mensual"])

    db.actualizar_cliente(cliente_id, {
        "nombre": request.form["nombre"],
        "pais_residencia": request.form["pais_residencia"],
        "ciudad_residencia": request.form["ciudad_residencia"],
        "tipo_identificacion": request.form["tipo_identificacion"],
        "numero_identificacion": request.form["numero_identificacion"],
        "ingreso_mensual": ingreso,
        "ingreso_moneda": moneda,
        "ingreso_mensual_cop": fx.convertir_a_cop(ingreso, moneda),
        "ahorro_mensual": ahorro,
        "ahorro_mensual_cop": fx.convertir_a_cop(ahorro, moneda),
    })
    return redirect(url_for("cliente_detalle", cliente_id=cliente_id))


@app.route("/clientes/<int:cliente_id>/eliminar", methods=["POST", "GET"])
def cliente_eliminar(cliente_id):
    db.eliminar_cliente(cliente_id)
    return redirect(url_for("clientes"))


@app.route("/busquedas")
def busquedas():
    all_b = db.obtener_todas_busquedas()
    return render_template("busquedas.html", activo="busquedas", busquedas=all_b)


@app.route("/busquedas/<int:busqueda_id>/eliminar", methods=["POST", "GET"])
def busqueda_eliminar(busqueda_id):
    busqueda_obj = db.obtener_busqueda(busqueda_id)
    cliente_id = busqueda_obj["cliente_id"] if busqueda_obj else None
    db.eliminar_busqueda(busqueda_id)
    if cliente_id:
        return redirect(url_for("cliente_detalle", cliente_id=cliente_id))
    return redirect(url_for("busquedas"))


@app.route("/inmuebles")
def inmuebles():
    all_a = db.obtener_todos_anuncios_con_scores()
    return render_template("inmuebles.html", activo="inmuebles", anuncios=all_a)


@app.route("/inmuebles/<int:anuncio_id>/eliminar", methods=["POST", "GET"])
def anuncio_eliminar(anuncio_id):
    db.eliminar_anuncio(anuncio_id)
    return redirect(url_for("inmuebles"))


@app.route("/mapa")
def mapa():
    focus_id = request.args.get("focus_id", type=int)
    all_anuncios = db.obtener_todos_anuncios_con_scores()
    clientes = db.listar_clientes()
    return render_template("mapa.html", activo="mapa", anuncios=all_anuncios, clientes=clientes, focus_id=focus_id)


@app.route("/inmuebles/<int:anuncio_id>/editar", methods=["GET", "POST"])
def anuncio_editar(anuncio_id):
    anuncio = db.obtener_anuncio(anuncio_id)
    if not anuncio:
        return "Inmueble no encontrado", 404
        
    if request.method == "GET":
        return render_template("inmueble_form.html", activo="inmuebles", anuncio=anuncio)
        
    db.actualizar_anuncio(anuncio_id, {
        "tipo_inmueble": request.form["tipo_inmueble"],
        "estado": request.form["estado"],
        "precio_venta": int(request.form["precio_venta"]),
        "administracion": int(request.form["administracion"] or 0),
        "estrato": int(request.form["estrato"]),
        "area_metros": float(request.form["area_metros"]),
        "habitaciones": int(request.form["habitaciones"]),
        "banos": int(request.form["banos"]),
        "parqueaderos": int(request.form["parqueaderos"] or 0),
        "antiguedad": request.form["antiguedad"],
        "latitud": float(request.form["latitud"]),
        "longitud": float(request.form["longitud"]),
        "comodidades": request.form["comodidades"],
        "descripcion": request.form["descripcion"],
        "ubicacion_texto": request.form["ubicacion_texto"]
    })
    return redirect(url_for("inmuebles"))


@app.route("/clientes/<int:cliente_id>")
def cliente_detalle(cliente_id):
    cliente = db.obtener_cliente(cliente_id)
    if not cliente:
        return "Cliente no encontrado", 404
    busquedas = db.obtener_busquedas_cliente(cliente_id)
    return render_template("cliente_detalle.html", activo="clientes", cliente=cliente, busquedas=busquedas)


@app.route("/clientes/<int:cliente_id>/resultados")
def cliente_resultados(cliente_id):
    cliente = db.obtener_cliente(cliente_id)
    busqueda_id = request.args.get("busqueda_id", type=int)
    if not busqueda_id:
        return "Búsqueda no encontrada", 404
    busqueda_obj = db.obtener_busqueda(busqueda_id)
    if not busqueda_obj:
        return "Búsqueda no encontrada", 404
    resultados = db.obtener_resultados_busqueda(busqueda_id)
    return render_template(
        "resultados.html",
        activo="clientes",
        cliente=cliente,
        resultados=resultados,
        status=busqueda_obj["status"],
        busqueda_id=busqueda_id
    )


@app.route("/busquedas/nueva", methods=["GET", "POST"])
def busqueda_nueva():
    cliente_id = request.args.get("cliente_id", type=int)
    cliente = db.obtener_cliente(cliente_id) if cliente_id else None
    
    if request.method == "GET":
        clientes_lista = db.listar_clientes() if not cliente else []
        return render_template(
            "busqueda_form.html",
            activo="busquedas",
            cliente=cliente,
            clientes=clientes_lista,
            ciudades=CIUDADES
        )

    # POST: Process search criteria
    resolved_cliente_id = cliente["id"] if cliente else int(request.form["cliente_id"])
    
    portales = request.form.getlist("portales") or ["fincaraiz", "metrocuadrado"]
    cantidad = int(request.form.get("cantidad", 30))

    comodidades = request.form.getlist("comodidades")
    adicionales = request.form.get("comodidades_adicionales", "").strip()
    if adicionales:
        for tag in adicionales.split(","):
            tag_clean = tag.strip().lower()
            if tag_clean and tag_clean not in comodidades:
                comodidades.append(tag_clean)

    busqueda_id = db.crear_busqueda({
        "cliente_id": resolved_cliente_id,
        "portales": portales,
        "cantidad_solicitada": cantidad,
        "status": "pendiente",
        "log": [],
        "departamento_interes": request.form.get("departamento_interes"),
        "municipio_interes": request.form.get("municipio_interes"),
        "municipio_codigo": request.form.get("municipio_codigo"),
        "tipo_vivienda": request.form["tipo_vivienda"],
        "estado_deseado": request.form["estado_deseado"],
        "antiguedad_deseada": request.form.get("antiguedad_deseada", "0 a 5 años"),
        "zona_deseada": request.form["zona_deseada"],
        "habitaciones_min": int(request.form["habitaciones_min"]),
        "habitaciones_exactas": request.form.get("habitaciones_exactas") == "true",
        "banos_min": int(request.form["banos_min"]),
        "banos_exactos": request.form.get("banos_exactos") == "true",
        "estrato_objetivo": int(request.form["estrato_objetivo"]),
        "presupuesto_min": int(request.form["presupuesto_min"]),
        "presupuesto_max": int(request.form["presupuesto_max"]),
        "uso_previsto": request.form["uso_previsto"],
        "comodidades": comodidades,
        "pregunta_abierta": request.form["pregunta_abierta"]
    })

    return redirect(url_for("busquedas"))


@app.route("/busquedas/<int:busqueda_id>/lanzar")
def busqueda_lanzar(busqueda_id):
    busqueda_obj = db.obtener_busqueda(busqueda_id)
    if not busqueda_obj:
        return "Búsqueda no encontrada", 404
        
    db.actualizar_busqueda_status(busqueda_id, "running")
    db.actualizar_busqueda_log(busqueda_id, "Iniciando ejecución de búsqueda...", "info")
    
    thread = threading.Thread(
        target=busqueda.ejecutar_busqueda_completa,
        args=(busqueda_id,),
        daemon=True,
    )
    thread.start()
    
    return redirect(url_for("cliente_resultados", cliente_id=busqueda_obj["cliente_id"], busqueda_id=busqueda_id))


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

    busqueda_id = db.crear_busqueda({
        "cliente_id": cliente_id,
        "portales": portales,
        "cantidad_solicitada": cantidad,
        "status": "running",
        "log": [],
        "tipo_vivienda": "apartamento",
        "estado_deseado": "usado",
        "antiguedad_deseada": "0 a 5 años",
        "zona_deseada": "urbano",
        "habitaciones_min": 1,
        "habitaciones_exactas": False,
        "banos_min": 1,
        "banos_exactos": False,
        "estrato_objetivo": 3,
        "presupuesto_min": 0,
        "presupuesto_max": 9999999999,
        "uso_previsto": "vivir",
        "comodidades": [],
        "pregunta_abierta": ""
    })
    thread = threading.Thread(
        target=busqueda.ejecutar_busqueda_completa,
        args=(busqueda_id,),
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
