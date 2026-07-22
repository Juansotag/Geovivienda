import os
import csv
import json
import logging
import threading

from dotenv import load_dotenv, find_dotenv
from flask import Flask, render_template, request, jsonify, redirect, url_for, Response

load_dotenv(find_dotenv(), override=True)

import config
from database import db
from services import fx
from services import scoring
from services import reportes
from services import busqueda
from services import spatial_analysis
from services.scheduler import iniciar_scheduler

app = Flask(__name__)
# Con debug=False, Jinja2 cachea las plantillas compiladas en memoria y no
# detecta cambios en disco por si solo - sin esto hay que reiniciar el
# proceso despues de cada edicion a un .html para ver el cambio reflejado.
app.config["TEMPLATES_AUTO_RELOAD"] = True


@app.errorhandler(Exception)
def handle_all_errors(e):
    import traceback
    tb = traceback.format_exc()
    logging.error(f"UNHANDLED EXCEPTION: {tb}")
    # Also write to a simple file so we can read it easily
    with open('last_500_error.txt', 'w', encoding='utf-8') as f:
        f.write(tb)
    if request.path.startswith('/api/'):
        return jsonify({'error': str(e)}), 500
    return f"<pre style='color:red;padding:20px;font-size:13px;'>[500 ERROR]\n{tb}</pre>", 500


# Filtro personalizado: deserializar JSONB que llega como string desde PostgreSQL
@app.template_filter("from_json")
def from_json_filter(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return {}
    return value or {}


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
# Ruta relativa al propio archivo app.py, no al directorio de trabajo desde
# donde se lance "python app.py" - si no, esto se rompe segun desde donde
# se arranque el proceso (nos paso justo eso).
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_divipola_data = {}
csv_path = os.path.join(BASE_DIR, "geodata", "DIVIPOLA-_Códigos_municipios_20260717.csv")
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
else:
    print(f"AVISO: no se encontro el CSV de DIVIPOLA en {csv_path} - departamentos/municipios quedaran vacios.")

# Ordenar departamentos y municipios
for dept in _divipola_data:
    _divipola_data[dept] = sorted(_divipola_data[dept], key=lambda x: x["nombre"])
_divipola_data = dict(sorted(_divipola_data.items()))


@app.context_processor
def inject_global_catalogs():
    from services import paises_onu
    return {
        "paises_onu": paises_onu.PAISES_ONU,
        "tipos_permiso": paises_onu.TIPOS_PERMISO_RESIDENCIA,
        "ciudades_populares": paises_onu.CIUDADES_POPULARES,
        "ciudades": CIUDADES,
        "google_maps_api_key": os.environ.get("GOOGLE_MAPS_API_KEY", "") or getattr(config, "GOOGLE_MAPS_API_KEY", ""),
    }


@app.route("/api/divipola")
def api_divipola():
    return jsonify(_divipola_data)


@app.route("/api/bogota/localidades")
def api_bogota_localidades():
    try:
        from services import spatial_analysis
        sitp, tm, ciclo, estratos, col_estrato, localidades, upzs, metro, municipios, upz_a_loc = spatial_analysis._capas()
        loc_names = sorted([str(x).strip().title() for x in localidades["LOCNOMBRE"].dropna().unique()])
        return jsonify(loc_names)
    except Exception as e:
        print("Error al cargar localidades:", e)
        return jsonify([])


@app.route("/api/bogota/upzs")
def api_bogota_upzs():
    """Si se pasa ?localidad=X, solo devuelve las UPZ que caen dentro de esa
    localidad (antes traia siempre las UPZ de toda la ciudad, sin importar
    la localidad ya elegida)."""
    try:
        from services import spatial_analysis
        sitp, tm, ciclo, estratos, col_estrato, localidades, upzs, metro, municipios, upz_a_loc = spatial_analysis._capas()
        localidad_filtro = request.args.get("localidad", "").strip()

        if localidad_filtro:
            loc_norm = localidad_filtro.strip().lower()
            nombres = [
                nombre for nombre, loc in upz_a_loc.items()
                if loc.strip().lower() == loc_norm
            ]
            upz_names = sorted(str(n).strip().title() for n in nombres)
        else:
            upz_names = sorted([str(x).strip().title() for x in upzs["NOMBRE"].dropna().unique()])
        return jsonify(upz_names)
    except Exception as e:
        print("Error al cargar UPZs:", e)
        return jsonify([])


@app.context_processor
def inject_perfil():
    try:
        return dict(perfil=db.obtener_perfil())
    except Exception:
        return dict(perfil=None)


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
    from services import paises_onu
    if request.method == "GET":
        return render_template(
            "cliente_form.html",
            activo="clientes",
            ciudades=CIUDADES,
            cliente=None,
            paises_onu=paises_onu.PAISES_ONU,
            tipos_permiso=paises_onu.TIPOS_PERMISO_RESIDENCIA,
        )

    moneda = request.form["ingreso_moneda"]
    ingreso = float(request.form["ingreso_mensual"])
    ahorro = float(request.form["ahorro_mensual"])

    cliente_id = db.insertar_cliente({
        "nombre": request.form["nombre"],
        "pais_residencia": request.form["pais_residencia"],
        "ciudad_residencia": request.form["ciudad_residencia"],
        "nacionalidad": request.form.get("nacionalidad"),
        "anios_en_pais": _int_opcional(request.form.get("anios_en_pais")),
        "tipo_permiso_residencia": request.form.get("tipo_permiso_residencia"),
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
        
    from services import paises_onu
    if request.method == "GET":
        return render_template(
            "cliente_form.html",
            activo="clientes",
            ciudades=CIUDADES,
            cliente=cliente,
            paises_onu=paises_onu.PAISES_ONU,
            tipos_permiso=paises_onu.TIPOS_PERMISO_RESIDENCIA,
        )

    moneda = request.form["ingreso_moneda"]
    ingreso = float(request.form["ingreso_mensual"])
    ahorro = float(request.form["ahorro_mensual"])

    db.actualizar_cliente(cliente_id, {
        "nombre": request.form["nombre"],
        "pais_residencia": request.form["pais_residencia"],
        "ciudad_residencia": request.form["ciudad_residencia"],
        "nacionalidad": request.form.get("nacionalidad"),
        "anios_en_pais": _int_opcional(request.form.get("anios_en_pais")),
        "tipo_permiso_residencia": request.form.get("tipo_permiso_residencia"),
        "tipo_identificacion": request.form["tipo_identificacion"],
        "numero_identificacion": request.form["numero_identificacion"],
        "ingreso_mensual": ingreso,
        "ingreso_moneda": moneda,
        "ingreso_mensual_cop": fx.convertir_a_cop(ingreso, moneda),
        "ahorro_mensual": ahorro,
        "ahorro_mensual_cop": fx.convertir_a_cop(ahorro, moneda),
    })
    return redirect(url_for("cliente_detalle", cliente_id=cliente_id))


@app.route("/clientes/<int:cliente_id>/eliminar", methods=["POST"])
def cliente_eliminar(cliente_id):
    db.eliminar_cliente(cliente_id)
    return redirect(url_for("clientes"))


@app.route("/busquedas")
def busquedas():
    all_b = db.obtener_todas_busquedas()
    return render_template("busquedas.html", activo="busquedas", busquedas=all_b)


@app.route("/busquedas/<int:busqueda_id>/eliminar", methods=["POST"])
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
    clientes = db.listar_clientes()
    return render_template("inmuebles.html", activo="inmuebles", anuncios=all_a, clientes=clientes)


@app.route("/inmuebles/<int:anuncio_id>/eliminar", methods=["POST"])
def anuncio_eliminar(anuncio_id):
    db.eliminar_anuncio(anuncio_id)
    return redirect(url_for("inmuebles"))


@app.route("/mapa")
def mapa():
    focus_id = request.args.get("focus_id", type=int)
    busqueda_id = request.args.get("busqueda_id", type=int)
    all_anuncios = db.obtener_todos_anuncios_con_scores()
    clientes = db.listar_clientes()
    all_b = db.obtener_todas_busquedas()

    busqueda_resultados_map = db.obtener_mapa_busqueda_resultados()

    return render_template(
        "mapa.html",
        activo="mapa",
        anuncios=all_anuncios,
        clientes=clientes,
        busquedas=all_b,
        focus_id=focus_id,
        busqueda_id=busqueda_id,
        busqueda_resultados_map=busqueda_resultados_map,
        google_maps_api_key=os.environ.get("GOOGLE_MAPS_API_KEY", "") or getattr(config, "GOOGLE_MAPS_API_KEY", ""),
    )


@app.route("/api/h3/geojson")
def api_h3_geojson():
    """Sirve el archivo GeoJSON de hexágonos H3 de Bogotá para la capa GIS del mapa."""
    geo_path = os.path.join(BASE_DIR, "geodata", "mapa_h3_bogota.geojson")
    if not os.path.exists(geo_path):
        return jsonify({"error": "GeoJSON de hexágonos H3 no encontrado"}), 404
    with open(geo_path, encoding="utf-8") as f:
        data = json.load(f)
    resp = jsonify(data)
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@app.route("/api/boundaries/localidades")
def api_boundaries_localidades():
    """Sirve el polígono GeoJSON de las 20 localidades de Bogotá."""
    path = os.path.join(BASE_DIR, "static", "geo", "localidad.geojson")
    if not os.path.exists(path):
        return jsonify({"error": "GeoJSON de localidades no encontrado"}), 404
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    resp = jsonify(data)
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@app.route("/api/boundaries/upz")
def api_boundaries_upz():
    """Sirve el polígono GeoJSON de las UPZ de Bogotá."""
    path = os.path.join(BASE_DIR, "geodata", "upz.geojson")
    if not os.path.exists(path):
        path = os.path.join(BASE_DIR, "static", "geo", "upz.geojson")
    if not os.path.exists(path):
        return jsonify({"error": "GeoJSON de UPZ no encontrado"}), 404
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    resp = jsonify(data)
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp



ESTADO_INMUEBLE_VALORES_VALIDOS = ("usado", "nuevo", "proyecto")


@app.route("/inmuebles/<int:anuncio_id>/editar", methods=["GET", "POST"])
def anuncio_editar(anuncio_id):
    anuncio = db.obtener_anuncio(anuncio_id)
    if not anuncio:
        return "Inmueble no encontrado", 404

    if request.method == "GET":
        return render_template(
            "inmueble_form.html",
            activo="inmuebles",
            anuncio=anuncio,
            antiguedad_opciones=busqueda.ANTIGUEDAD_VALORES_VALIDOS,
        )

    estado = request.form["estado"]
    if estado not in ESTADO_INMUEBLE_VALORES_VALIDOS:
        return "Estado invalido", 400

    antiguedad = request.form.get("antiguedad") or None
    if antiguedad and antiguedad not in busqueda.ANTIGUEDAD_VALORES_VALIDOS:
        return "Antigüedad inválida", 400
    antiguedad_min, antiguedad_max = busqueda._parsear_antiguedad(antiguedad)

    db.actualizar_anuncio(anuncio_id, {
        "tipo_inmueble": request.form["tipo_inmueble"],
        "estado": estado,
        "precio_venta": int(request.form["precio_venta"]),
        "administracion": _int_opcional(request.form.get("administracion")),
        "estrato": int(request.form["estrato"]),
        "area_metros": float(request.form["area_metros"]),
        "habitaciones": int(request.form["habitaciones"]),
        "banos": int(request.form["banos"]),
        "parqueaderos": _int_opcional(request.form.get("parqueaderos")),
        "antiguedad": antiguedad,
        "antiguedad_anios_min": antiguedad_min,
        "antiguedad_anios_max": antiguedad_max,
        "piso_nro": _int_opcional(request.form.get("piso_nro")),
        "cantidad_pisos": _int_opcional(request.form.get("cantidad_pisos")),
        "latitud": float(request.form["latitud"]),
        "longitud": float(request.form["longitud"]),
        "comodidades": request.form["comodidades"],
        "descripcion": request.form["descripcion"],
        "ubicacion_texto": request.form["ubicacion_texto"]
    })
    return redirect(url_for("inmuebles"))


@app.route("/inmuebles/<int:anuncio_id>/recalcular-score", methods=["POST"])
def anuncio_recalcular_score(anuncio_id):
    """Reevalua un anuncio (ya corregido a mano) contra cada busqueda a la
    que pertenece, usando el LLM - para cuando un error de scraping
    evidente (ej. area mal capturada) infla o hunde el score sin que el
    dato real de fondo haya cambiado."""
    anuncio_obj = db.obtener_anuncio(anuncio_id)
    if not anuncio_obj:
        return jsonify({"status": "error", "message": "Inmueble no encontrado"}), 404

    resultados = db.obtener_resultados_por_anuncio(anuncio_id)
    if not resultados:
        return jsonify({"status": "error", "message": "Este inmueble no aparece en ninguna búsqueda todavía."})

    actualizados = 0
    for r in resultados:
        scores = scoring.calcular_scores_llm(r, [anuncio_obj])
        info = scores.get(anuncio_id)
        if info is not None:
            db.actualizar_score_resultado(r["resultado_id"], info["score"])
            actualizados += 1

    return jsonify({"status": "ok", "actualizados": actualizados, "total": len(resultados)})


@app.route("/inmuebles/<int:anuncio_id>/buscar-administracion", methods=["POST"])
def anuncio_buscar_administracion(anuncio_id):
    anuncio_obj = db.obtener_anuncio(anuncio_id)
    if not anuncio_obj:
        return jsonify({"status": "error", "message": "Inmueble no encontrado"}), 404
    if anuncio_obj["portal"] != "metrocuadrado":
        return jsonify({"status": "error", "message": "Esta función es solo para anuncios de Metrocuadrado."})

    try:
        valor = busqueda.buscar_administracion_metrocuadrado(anuncio_obj["url"])
    except Exception as e:
        return jsonify({"status": "error", "message": f"No se pudo abrir el anuncio original: {e}"}), 500

    if valor is None:
        return jsonify({"status": "error", "message": "No se encontró el valor de administración en la ficha del inmueble."})

    db.actualizar_anuncio(anuncio_id, {"administracion": valor})
    return jsonify({"status": "ok", "administracion": valor})


@app.route("/inmuebles/estandarizar-comodidades", methods=["POST"])
def inmuebles_estandarizar_comodidades():
    """Backfill: normaliza contra CATALOGO_COMODIDADES los anuncios que
    existian antes del clasificador (los nuevos ya se normalizan solos
    durante la busqueda, ver busqueda.ejecutar_busqueda)."""
    total_procesados = 0
    for _ in range(10):  # tope de seguridad: hasta 400 anuncios por click
        pendientes = db.obtener_anuncios_sin_comodidades_normalizadas(limite=40)
        if not pendientes:
            break
        normalizadas = busqueda.normalizar_comodidades_llm(pendientes)
        if not normalizadas:
            break  # la llamada al LLM fallo - no reintentar en loop
        for a in pendientes:
            lista = normalizadas.get(a["id"])
            if lista is not None:
                db.actualizar_anuncio(a["id"], {"comodidades_normalizadas": lista})
                total_procesados += 1
    return jsonify({"status": "ok", "procesados": total_procesados})


@app.route("/clientes/<int:cliente_id>")
def cliente_detalle(cliente_id):
    cliente = db.obtener_cliente(cliente_id)
    if not cliente:
        return "Cliente no encontrado", 404
    busquedas = db.obtener_busquedas_cliente(cliente_id)
    return render_template("cliente_detalle.html", activo="clientes", cliente=cliente, busquedas=busquedas)


@app.route("/clientes/<int:cliente_id>/resultados")
def cliente_resultados(cliente_id):
    try:
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
    except Exception as _e:
        import traceback as _tb
        err = _tb.format_exc()
        print(f"\n[RESULTADOS 500 ERROR]\n{err}\n", flush=True)
        return f"<pre style='color:red;padding:20px;font-size:13px;'>[RESULTADOS ERROR]\n{err}</pre>", 500



def _int_opcional(valor):
    valor = (valor or "").strip()
    return int(valor) if valor else None


def _float_opcional(valor):
    valor = (valor or "").strip()
    return float(valor) if valor else None


def _upz_opciones():
    """Lista (upz_nombre, localidad_nombre) para el checkbox grid del
    formulario de busqueda, ordenada por localidad y luego por UPZ."""
    from services import spatial_analysis
    upz_a_loc = spatial_analysis.upz_a_localidad_map()
    pares = [(nombre.strip().title(), loc.strip().title()) for nombre, loc in upz_a_loc.items()]
    return sorted(pares, key=lambda par: (par[1], par[0]))


def _parse_busqueda_form(form) -> dict:
    """Compilado compartido entre crear y editar una busqueda: uso_previsto
    y estrato_objetivo son multi-choice (getlist); antiguedad es un rango
    numerico de anios (min/max, cualquiera puede quedar vacio = sin limite);
    comodidades se reparten en dos listas segun la columna donde el
    funcionario las haya dejado en el picker de arrastrar-y-soltar
    (relevantes pesan en el score del LLM, indispensables son filtro duro);
    los municipios llegan como JSON serializado por el picker ordenable."""
    portales = form.getlist("portales") or ["fincaraiz", "metrocuadrado"]
    cantidad = int(form.get("cantidad", 30))

    try:
        municipios = json.loads(form.get("municipios_json") or "[]")
    except (ValueError, TypeError):
        municipios = []

    return {
        "portales": portales,
        "cantidad_solicitada": cantidad,
        "cantidad_exacta": form.get("cantidad_exacta") == "true",
        "top_n": min(int(form.get("top_n") or 5), 10),
        "municipios": municipios,
        "tipo_vivienda": form["tipo_vivienda"],
        "estado_deseado": form["estado_deseado"],
        "antiguedad_anios_min": _int_opcional(form.get("antiguedad_anios_min")),
        "antiguedad_anios_max": _int_opcional(form.get("antiguedad_anios_max")),
        "zona_deseada": form["zona_deseada"],
        "habitaciones_min": int(form["habitaciones_min"]),
        "habitaciones_exactas": form.get("habitaciones_exactas") == "true",
        "banos_min": int(form["banos_min"]),
        "banos_exactos": form.get("banos_exactos") == "true",
        "estrato_objetivo": [int(e) for e in form.getlist("estrato_objetivo")],
        "presupuesto_min": int(form["presupuesto_min"]),
        "presupuesto_max": int(form["presupuesto_max"]),
        "uso_previsto": form.getlist("uso_previsto"),
        "comodidades_relevantes": form.getlist("comodidades_relevantes"),
        "comodidades_indispensables": form.getlist("comodidades_indispensables"),
        "upz": form.getlist("upz"),
        "area_metros_min": _float_opcional(form.get("area_metros_min")),
        "area_metros_max": _float_opcional(form.get("area_metros_max")),
        "pregunta_abierta": form["pregunta_abierta"],
        "usar_normalizacion_llm": form.get("usar_normalizacion_llm") == "true",
    }


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
            ciudades=CIUDADES,
            busqueda=None,
            catalogo_comodidades=busqueda.CATALOGO_COMODIDADES,
            upz_opciones=_upz_opciones(),
        )

    # POST: Process search criteria
    resolved_cliente_id = cliente["id"] if cliente else int(request.form["cliente_id"])

    datos = _parse_busqueda_form(request.form)
    datos.update({
        "cliente_id": resolved_cliente_id,
        "status": "pendiente",
        "log": [],
    })
    db.crear_busqueda(datos)

    return redirect(url_for("busquedas"))


@app.route("/busquedas/<int:busqueda_id>/editar", methods=["GET", "POST"])
def busqueda_editar(busqueda_id):
    busqueda_obj = db.obtener_busqueda(busqueda_id)
    if not busqueda_obj:
        return "Búsqueda no encontrada", 404
    if busqueda_obj["status"] != "pendiente":
        # Solo se puede editar antes de lanzarla - una vez corriendo o
        # terminada, los criterios ya quedaron fijados en los resultados.
        return redirect(url_for("busquedas"))

    if request.method == "GET":
        cliente = db.obtener_cliente(busqueda_obj["cliente_id"])
        return render_template(
            "busqueda_form.html",
            activo="busquedas",
            cliente=cliente,
            clientes=[],
            ciudades=CIUDADES,
            busqueda=busqueda_obj,
            catalogo_comodidades=busqueda.CATALOGO_COMODIDADES,
            upz_opciones=_upz_opciones(),
        )

    datos = _parse_busqueda_form(request.form)
    db.actualizar_busqueda(busqueda_id, datos)
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


@app.route("/api/busquedas/<int:busqueda_id>/cancelar", methods=["POST"])
def api_cancelar_busqueda(busqueda_id):
    busqueda_obj = db.obtener_busqueda(busqueda_id)
    if not busqueda_obj:
        return jsonify({"status": "error", "message": "Búsqueda no encontrada"}), 404
    if busqueda_obj["status"] != "running":
        return jsonify({"status": "error", "message": "Solo se pueden cancelar búsquedas en curso"}), 400

    # Cancelacion cooperativa: el hilo en background revisa este estado
    # entre cada portal y cada anuncio, y se detiene solo en el proximo
    # punto seguro - no es instantaneo si esta a mitad de una carga de
    # pagina, pero si en cuestion de segundos.
    db.actualizar_busqueda_status(busqueda_id, "cancelando")
    db.actualizar_busqueda_log(busqueda_id, "Cancelación solicitada, deteniendo en el próximo punto seguro...", "info")
    return jsonify({"status": "ok"})


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

    # La tabla clientes solo tiene datos personales/financieros - los
    # criterios de vivienda (tipo, estrato, presupuesto, etc.) viven en la
    # busqueda. Sin este merge el reporte y el score quedan sin criterios
    # reales para comparar contra el anuncio.
    criterios = cliente
    if data.get("busqueda_id"):
        busqueda_obj = db.obtener_busqueda(data["busqueda_id"])
        if busqueda_obj:
            criterios = {**cliente, **busqueda_obj, "id": cliente["id"]}

    score = scoring.calcular_score(criterios, anuncio)
    reporte_id = reportes.crear_y_guardar_reporte(criterios, anuncio, score)
    return jsonify({"reporte_id": reporte_id})


@app.route("/reportes/<int:reporte_id>")
def ver_reporte_html(reporte_id):
    reporte = db.obtener_reporte(reporte_id)
    if not reporte:
        return "Reporte no encontrado", 404
    return reporte["contenido_html"]


@app.route("/reportes/<int:reporte_id>/html")
def descargar_reporte_html(reporte_id):
    reporte = db.obtener_reporte(reporte_id)
    if not reporte:
        return "Reporte no encontrado", 404
    return Response(
        reporte["contenido_html"],
        mimetype="text/html",
        headers={"Content-Disposition": f"attachment; filename=reporte_{reporte_id}.html"},
    )


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


@app.route("/inmuebles/<int:anuncio_id>/perfil")
def inmueble_perfil(anuncio_id):
    """Página de perfil detallado del inmueble con análisis de sector H3, Sub-Scores y POIs."""
    anuncio = db.buscar_anuncio_por_id(anuncio_id)
    if not anuncio:
        return "Inmueble no encontrado", 404

    # Calcular Sub-Scores desde h3_data
    sub_scores = scoring.calcular_sub_scores(anuncio)

    # POIs cercanos desde las coordenadas exactas del inmueble
    pois = {}
    lat, lon = anuncio.get("latitud"), anuncio.get("longitud")
    if lat and lon:
        try:
            from services import spatial_analysis
            pois = spatial_analysis.pois_cercanos(float(lat), float(lon), radio_m=700)
        except Exception as e:
            print(f"Error calculando POIs para inmueble {anuncio_id}: {e}")

    # Metadatos de dimensiones para el template
    dimensiones = scoring.DIMENSIONES_H3

    key = os.environ.get("GOOGLE_MAPS_API_KEY", "") or getattr(config, "GOOGLE_MAPS_API_KEY", "")
    return render_template(
        "inmueble_perfil.html",
        activo="inmuebles",
        anuncio=anuncio,
        sub_scores=sub_scores,
        pois=pois,
        dimensiones=dimensiones,
        google_maps_api_key=key,
    )


@app.route("/api/inmuebles/<int:anuncio_id>/analisis-llm", methods=["POST"])
def inmueble_analisis_llm(anuncio_id):
    """Genera un informe cualitativo on-demand para un inmueble específico."""
    anuncio = db.buscar_anuncio_por_id(anuncio_id)
    if not anuncio:
        return jsonify({"status": "error", "message": "Inmueble no encontrado"}), 404

    busqueda_id = request.json.get("busqueda_id") if request.is_json else None
    busqueda_obj = db.obtener_busqueda(busqueda_id) if busqueda_id else {}
    if not busqueda_obj:
        busqueda_obj = {}

    # Enriquecer el anuncio con sub_scores y POIs para el prompt
    sub = scoring.calcular_sub_scores(anuncio)
    anuncio["_sub_scores"] = sub
    lat, lon = anuncio.get("latitud"), anuncio.get("longitud")
    if lat and lon:
        try:
            from services import spatial_analysis
            anuncio["_pois_cercanos"] = spatial_analysis.pois_cercanos(float(lat), float(lon))
        except Exception:
            pass

    scores_llm = scoring.calcular_scores_llm(busqueda_obj, [anuncio])
    info = scores_llm.get(anuncio_id)
    razon = info.get("razon", "") if info else "No se pudo generar el análisis."
    return jsonify({"status": "ok", "razon": razon})


@app.route("/api/h3/distribuciones")
def api_h3_distribuciones():
    """Sirve el JSON pre-calculado de distribuciones de variables H3 para los histogramas del perfil."""
    dist_path = os.path.join(BASE_DIR, "static", "data", "h3_distribuciones.json")
    if not os.path.exists(dist_path):
        return jsonify({"error": "Distribuciones no generadas. Ejecuta scripts/generar_distribuciones_h3.py"}), 404
    with open(dist_path, encoding="utf-8") as f:
        data = json.load(f)
    resp = jsonify(data)
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)

