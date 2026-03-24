import os
import json
import threading
import pandas as pd
from flask import Flask, render_template, request, jsonify, Response
from extractor_links import extraer_links_fincaraiz
from extractor_detalles import procesar_lista_links

app = Flask(__name__)
CSV_PATH = 'dataset_fincaraiz.csv'
GEO_DIR  = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'Información geográfica', 'Datasets', 'Transporte')

# Estado compartido del job de scraping actual
job_state = {
    'thread': None,   # referencia al Thread activo
    'log': [],
    'status': 'idle'
}

def push_log(msg, level='info'):
    job_state['log'].append({'msg': msg, 'level': level})

# ---- ROUTES ----

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data', methods=['GET'])
def get_data():
    if os.path.exists(CSV_PATH):
        try:
            df = pd.read_csv(CSV_PATH, sep=';', decimal=',', encoding='utf-8-sig')
            
            # Forzar redondeo a enteros en áreas para evitar el bug de comas en el frontend
            for col in ['Area_Metros', 'Area_Construida', 'Area_Privada']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').round(0).astype('Int64')
            
            df = df.fillna('')
            return jsonify(df.to_dict(orient='records'))
        except Exception as e:
            print("Error cargando CSV:", e)
    return jsonify([])

@app.route('/api/status', methods=['GET'])
def get_status():
    """El frontend hace polling aquí para obtener logs y saber si el job terminó."""
    since = int(request.args.get('since', 0))
    new_logs = job_state['log'][since:]
    return jsonify({
        'status': job_state['status'],
        'logs': new_logs,
        'total_logs': len(job_state['log'])
    })

@app.route('/api/delete_row', methods=['POST'])
def delete_row():
    url = request.json.get('url')
    if not url or not os.path.exists(CSV_PATH):
        return jsonify({'status': 'error'})
    try:
        df = pd.read_csv(CSV_PATH, sep=';', decimal=',', encoding='utf-8-sig')
        df = df[df['URL'] != url]
        df.to_csv(CSV_PATH, index=False, encoding='utf-8-sig', sep=';', decimal=',')
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/clear', methods=['POST'])
def clear_all():
    if os.path.exists(CSV_PATH):
        os.remove(CSV_PATH)
    return jsonify({'status': 'ok'})

@app.route('/api/geo/tm')
def geo_tm():
    path = os.path.join(GEO_DIR, 'estaciones_tm.geojson')
    with open(path, 'r', encoding='utf-8') as f:
        return Response(f.read(), mimetype='application/json')

@app.route('/api/geo/sitp')
def geo_sitp():
    path = os.path.join(GEO_DIR, 'estaciones_sitp.geojson')
    with open(path, 'r', encoding='utf-8') as f:
        return Response(f.read(), mimetype='application/json')

@app.route('/api/reset', methods=['POST'])
def reset_job():
    """Fuerza el reset del estado del job en caso de que quede atascado."""
    job_state['thread'] = None
    job_state['log'] = []
    job_state['status'] = 'idle'
    return jsonify({'status': 'ok'})

@app.route('/api/scrape', methods=['POST'])
def scrape():
    """Lanza el scraping en un hilo de fondo y retorna inmediatamente."""
    # Verificar si hay un thread real corriendo (no solo una bandera)
    t = job_state.get('thread')
    if t is not None and t.is_alive():
        return jsonify({'status': 'warning', 'message': 'Ya hay un rastreo en curso. Espera a que termine.'}), 409

    # Resetear estado
    job_state['log'] = []
    job_state['status'] = 'running'

    data = request.json
    new_thread = threading.Thread(target=run_scrape_job, args=(data,), daemon=True)
    job_state['thread'] = new_thread
    new_thread.start()

    return jsonify({'status': 'started', 'message': 'Rastreo iniciado en segundo plano.'})


def run_scrape_job(data):
    """Ejecutado en hilo de fondo. Actualiza job_state con el progreso."""
    try:
        paginas = int(data.get('paginas', 1))

        comodidades = data.get('comodidades', [])
        con_ascensor = 'con-ascensor' in comodidades
        con_balcon   = 'con-balcon'   in comodidades
        skip = {'con-ascensor', 'con-balcon'}
        extras = [c for c in comodidades if c not in skip]

        parq_raw = data.get('parqueaderos')
        parqueaderos = int(parq_raw) if parq_raw else None

        estratos_raw = data.get('estratos', [])
        estratos = [int(e) for e in estratos_raw if e] if estratos_raw else []

        push_log(f'Buscando links en FincaRaiz ({paginas} paginas)...', 'info')

        links_obtenidos = extraer_links_fincaraiz(
            paginas_a_extraer=paginas,
            operacion=data.get('operacion', 'venta'),
            tipos_inmueble=[data.get('tipo', 'apartamento')],
            ubicacion=data.get('ubicacion', 'bogota/bogota-dc'),
            habitaciones=data.get('habitaciones', '1-o-mas'),
            banos=data.get('banos', '1-o-mas'),
            con_balcon=con_balcon,
            con_ascensor=con_ascensor,
            extras=extras,
            parqueaderos=parqueaderos,
            estado=data.get('estado', 'usados'),
            precio_min=int(float(data.get('precio_min', 0))),
            precio_max=int(float(data.get('precio_max', 500000000))),
            antiguedad='de-1-a-8-anios',
            estratos=estratos
        )

        if not links_obtenidos:
            push_log('No se encontraron resultados con estos filtros.', 'warn')
            job_state['status'] = 'done'
            return

        lista = list(links_obtenidos)
        push_log(f'{len(lista)} propiedades encontradas. Extrayendo detalles...', 'ok')

        df_resultado = procesar_lista_links(lista, archivo_salida=CSV_PATH, log_callback=push_log)

        if not df_resultado.empty:
            push_log(f'Extraccion completada. Base actualizada: {len(df_resultado)} inmuebles en total.', 'ok')
            job_state['status'] = 'done'
        else:
            push_log('No se guardaron propiedades nuevas.', 'warn')
            job_state['status'] = 'done'

    except Exception as e:
        push_log(f'Error en el rastreo: {str(e)}', 'error')
        job_state['status'] = 'error'


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
