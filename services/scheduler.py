from apscheduler.schedulers.background import BackgroundScheduler

from database.db import limpiar_reportes_vencidos


def _job_limpieza():
    borrados = limpiar_reportes_vencidos()
    if borrados:
        print(f"[scheduler] {borrados} reportes vencidos eliminados.")


def iniciar_scheduler() -> BackgroundScheduler:
    """Corre dentro del mismo proceso Flask, sin worker aparte. Con
    --workers 2 de Gunicorn este modulo se importa en ambos procesos y el
    job corre duplicado - no es un problema porque el DELETE es idempotente
    (borrar dos veces lo mismo en la misma hora no rompe nada)."""
    scheduler = BackgroundScheduler()
    scheduler.add_job(_job_limpieza, "interval", hours=1, id="limpieza_reportes")
    scheduler.start()
    return scheduler
