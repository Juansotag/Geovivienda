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
