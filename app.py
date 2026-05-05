import os
import threading
import shutil
import pandas as pd
from flask import Flask, render_template, request, jsonify, send_from_directory

from extractor_links import extraer_links_fincaraiz
from extractor_detalles import procesar_lista_links

app = Flask(__name__)

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
CSV_RAW_PATH = os.path.join(BASE_DIR, 'dataset_fincaraiz.csv')
CSV_PATH     = os.path.join(BASE_DIR, 'dataset_enriquecido.csv')

job_state = {'thread': None, 'log': [], 'status': 'idle'}

def push_log(msg, level='info'):
    job_state['log'].append({'msg': msg, 'level': level})

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data')
def get_data():
    if not os.path.exists(CSV_PATH):
        return jsonify([])
    try:
        df = pd.read_csv(CSV_PATH, sep=';', decimal=',', encoding='utf-8-sig')
        for col in ['Area_Metros', 'Area_Construida', 'Area_Privada']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').round(0).astype('Int64').astype(object).fillna('')
        df = df.fillna('')
        return jsonify(df.to_dict(orient='records'))
    except Exception as e:
        raise e

@app.route('/api/status')
def get_status():
    since = int(request.args.get('since', 0))
    return jsonify({
        'status': job_state['status'],
        'logs': job_state['log'][since:],
        'total_logs': len(job_state['log'])
    })

@app.route('/api/geo/<path:filename>')
def serve_geojson(filename):
    return send_from_directory(os.path.join(app.root_path, 'static', 'geo'), filename, mimetype='application/json')

@app.route('/api/delete_row', methods=['POST'])
def delete_row():
    url = request.json.get('url')
    if not url or not os.path.exists(CSV_PATH):
        return jsonify({'status': 'error'})
    try:
        df = pd.read_csv(CSV_PATH, sep=';', decimal=',', encoding='utf-8-sig')
        df[df['URL'] != url].to_csv(CSV_PATH, index=False, encoding='utf-8-sig', sep=';', decimal=',')
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/api/clear', methods=['POST'])
def clear_all():
    for p in [CSV_PATH, CSV_RAW_PATH]:
        if os.path.exists(p):
            os.remove(p)
    return jsonify({'status': 'ok'})

@app.route('/api/reset', methods=['POST'])
def reset_job():
    job_state.update({'thread': None, 'log': [], 'status': 'idle'})
    return jsonify({'status': 'ok'})

@app.route('/api/scrape', methods=['POST'])
def scrape():
    t = job_state.get('thread')
    if t is not None and t.is_alive():
        return jsonify({'status': 'warning', 'message': 'Ya hay un rastreo en curso.'}), 409
    job_state['log'] = []
    job_state['status'] = 'running'
    thread = threading.Thread(target=run_scrape_job, args=(request.json,), daemon=True)
    job_state['thread'] = thread
    thread.start()
    return jsonify({'status': 'started'})


def run_scrape_job(data):
    try:
        paginas      = int(data.get('paginas', 1))
        comodidades  = data.get('comodidades', [])
        con_ascensor = 'con-ascensor' in comodidades
        con_balcon   = 'con-balcon' in comodidades
        extras       = [c for c in comodidades if c not in {'con-ascensor', 'con-balcon'}]
        parq_raw     = data.get('parqueaderos')
        parqueaderos = int(parq_raw) if parq_raw else None
        estratos     = [int(e) for e in data.get('estratos', []) if e]

        push_log(f'Buscando links en FincaRaiz ({paginas} paginas)...', 'info')

        links = extraer_links_fincaraiz(
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

        if not links:
            push_log('No se encontraron resultados con estos filtros.', 'warn')
            job_state['status'] = 'done'
            return

        lista = list(links)
        push_log(f'{len(lista)} propiedades encontradas. Extrayendo detalles...', 'ok')

        df = procesar_lista_links(lista, archivo_salida=CSV_RAW_PATH, log_callback=push_log)

        if df.empty:
            push_log('No se guardaron propiedades nuevas.', 'warn')
            job_state['status'] = 'done'
            return

        push_log(f'Extraccion completada: {len(df)} inmuebles. Iniciando analisis espacial...', 'ok')

        try:
            from spatial_analysis import run_analysis
            run_analysis(CSV_RAW_PATH, CSV_PATH, log_callback=push_log)
        except Exception as e:
            push_log(f'Analisis espacial fallo: {e}. Cargando datos sin enriquecer.', 'warn')
            shutil.copy(CSV_RAW_PATH, CSV_PATH)

        job_state['status'] = 'done'

    except Exception as e:
        push_log(f'Error en el rastreo: {e}', 'error')
        job_state['status'] = 'error'


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
