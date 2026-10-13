import logging
import os

from django.apps import AppConfig

logger = logging.getLogger(__name__)

_telemetry_started = False


def _start_telemetry():
    """Ship logs and requests to Application Insights.

    Runs from ready() rather than settings.py: Django applies LOGGING after the
    settings module is imported, which would strip the handler off the root logger.
    """
    global _telemetry_started
    connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "").strip()
    if _telemetry_started or not connection_string:
        return

    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
    except ImportError:
        logger.warning("azure-monitor-opentelemetry no instalado; sin telemetria remota.")
        return

    try:
        configure_azure_monitor(connection_string=connection_string)
        _telemetry_started = True
        logger.info("Telemetria conectada a Application Insights.")
    except Exception:
        # Telemetry must never take the site down.
        logger.exception("No se pudo iniciar la telemetria.")


class PublicConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'f1porra_website.apps.public'

    def ready(self):
        _start_telemetry()
