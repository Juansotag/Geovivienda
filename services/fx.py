import requests

_FALLBACK_RATES = {
    "EUR": 4600.0,
    "USD": 4200.0,
    "CAD": 3100.0,
    "AUD": 2800.0,
    "NZD": 2600.0,
    "GBP": 5400.0,
    "MXN": 230.0,
    "BRL": 760.0,
    "PEN": 1120.0,
    "CLP": 4.5,
    "ARS": 4.8,
    "JPY": 27.0,
    "KRW": 3.1,
    "CNY": 580.0,
    "AED": 1140.0,
    "QAR": 1150.0,
    "KWD": 13700.0,
    "SAR": 1120.0
}  # Tasas fijas razonables de respaldo a COP si la API no cubre la moneda o falla


def convertir_a_cop(monto: float, moneda_origen: str) -> float:
    moneda_origen = moneda_origen.upper()
    try:
        resp = requests.get(
            f"https://api.frankfurter.dev/v2/rate/{moneda_origen}/COP",
            timeout=5,
            headers={"User-Agent": "Geovivienda/1.0"},
        )
        resp.raise_for_status()
        tasa = resp.json()["rate"]
        return round(monto * tasa, 2)
    except (requests.RequestException, KeyError, ValueError):
        tasa = _FALLBACK_RATES.get(moneda_origen)
        if tasa is None:
            raise ValueError(f"No hay tasa de respaldo para {moneda_origen}")
        return round(monto * tasa, 2)
