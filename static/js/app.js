// --- Conversion de moneda en vivo en el formulario de cliente ---
async function actualizarFx() {
  const ingresoInput = document.getElementById('ingreso_mensual');
  const ahorroInput = document.getElementById('ahorro_mensual');
  const monedaSelect = document.getElementById('ingreso_moneda');
  if (!ingresoInput || !monedaSelect) return;

  const moneda = monedaSelect.value;

  if (ingresoInput.value) {
    const resp = await fetch(`/api/fx?monto=${ingresoInput.value}&moneda=${moneda}`);
    const data = await resp.json();
    document.getElementById('fx-hint').textContent = data.cop
      ? `Equivale a ${Number(data.cop).toLocaleString('es-CO')} COP/mes`
      : 'No se pudo calcular la conversión';
  }
  if (ahorroInput && ahorroInput.value) {
    const resp = await fetch(`/api/fx?monto=${ahorroInput.value}&moneda=${moneda}`);
    const data = await resp.json();
    document.getElementById('fx-hint-ahorro').textContent = data.cop
      ? `Equivale a ${Number(data.cop).toLocaleString('es-CO')} COP/mes`
      : 'No se pudo calcular la conversión';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  ['ingreso_mensual', 'ahorro_mensual', 'ingreso_moneda'].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.addEventListener('change', actualizarFx);
  });
});

// --- Flujo de busqueda ---
async function iniciarBusqueda(clienteId) {
  const portales = [];
  if (document.getElementById('portal-fincaraiz').checked) portales.push('fincaraiz');
  if (document.getElementById('portal-metrocuadrado').checked) portales.push('metrocuadrado');
  const cantidad = document.getElementById('cantidad').value;

  const logDiv = document.getElementById('log-busqueda');
  logDiv.style.display = 'block';
  logDiv.innerHTML = '<p>Iniciando búsqueda...</p>';

  const resp = await fetch('/api/scrape', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cliente_id: clienteId, portales, cantidad: Number(cantidad) }),
  });
  const data = await resp.json();
  if (data.status === 'error') {
    logDiv.innerHTML = `<p class="log-error">${data.message}</p>`;
    return;
  }
  pollEstado(data.busqueda_id, clienteId);
}

function pollEstado(busquedaId, clienteId) {
  const logDiv = document.getElementById('log-busqueda');
  let ultimoTotal = 0;
  const intervalo = setInterval(async () => {
    const resp = await fetch(`/api/status?busqueda_id=${busquedaId}&since=${ultimoTotal}`);
    const data = await resp.json();
    ultimoTotal = data.total_logs;
    data.logs.forEach((log) => {
      const p = document.createElement('p');
      p.textContent = log.msg;
      if (log.level === 'error') p.className = 'log-error';
      if (log.level === 'ok') p.className = 'log-ok';
      logDiv.appendChild(p);
    });
    logDiv.scrollTop = logDiv.scrollHeight;

    if (data.status === 'done' || data.status === 'error') {
      clearInterval(intervalo);
      if (data.status === 'done') {
        setTimeout(() => { window.location.href = `/clientes/${clienteId}/resultados?busqueda_id=${busquedaId}`; }, 1200);
      }
    }
  }, 3000);
}

// --- Reportes ---
async function generarReporte(clienteId, anuncioId, boton) {
  boton.disabled = true;
  boton.textContent = 'Generando...';
  const resp = await fetch('/api/reportes/generar', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cliente_id: clienteId, anuncio_id: anuncioId }),
  });
  const data = await resp.json();
  if (data.reporte_id) {
    window.location.reload();
  } else {
    boton.disabled = false;
    boton.textContent = 'Reintentar';
  }
}

async function generarReportePorUrl(clienteId) {
  const url = document.getElementById('url-manual').value.trim();
  const resultado = document.getElementById('resultado-manual');
  if (!url) return;
  resultado.textContent = 'Buscando y generando reporte...';
  const resp = await fetch('/api/reportes/generar', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cliente_id: clienteId, url }),
  });
  const data = await resp.json();
  if (data.reporte_id) {
    resultado.innerHTML = `<a href="/reportes/${data.reporte_id}/pdf" class="btn btn-secondary btn-sm">Descargar PDF</a>`;
  } else {
    resultado.textContent = data.message || 'No se pudo generar el reporte.';
  }
}
