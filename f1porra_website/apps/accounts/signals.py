# accounts/signals.py
import logging

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.contrib.auth.signals import (
    user_logged_in, user_logged_out, user_login_failed,
)
from .utils import ensure_user_profile_for_active_season

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        ensure_user_profile_for_active_season(instance)


def _client_ip(request):
    """Behind App Service the real client sits in X-Forwarded-For."""
    if request is None:
        return "?"
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "?")


@receiver(user_logged_in)
def log_login(sender, request, user, **kwargs):
    logger.info("Acceso OK | usuario=%s | ip=%s", user.username, _client_ip(request))


@receiver(user_logged_out)
def log_logout(sender, request, user, **kwargs):
    logger.info("Cierre de sesion | usuario=%s", user.username if user else "?")


@receiver(user_login_failed)
def log_login_failed(sender, credentials, request=None, **kwargs):
    # credentials comes pre-masked by Django, so no password ends up here.
    logger.warning(
        "Acceso FALLIDO | usuario=%s | ip=%s",
        credentials.get("username", "?"), _client_ip(request),
    )
