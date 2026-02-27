from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone

from f1porra_website.apps.public.models import Season
from .models import UserProfile


def get_active_season():
    """Return the active season for user profile operations.

    Prefer the current calendar year season and fallback to the latest season.
    """
    year = timezone.now().year
    try:
        return Season.objects.filter(year=year).first() or Season.objects.order_by('-year').first()
    except (ProgrammingError, OperationalError):
        return None


def ensure_user_profile_for_active_season(user):
    season = get_active_season()
    if season is None:
        return None
    profile, _ = UserProfile.objects.get_or_create(user=user, season=season)
    return profile