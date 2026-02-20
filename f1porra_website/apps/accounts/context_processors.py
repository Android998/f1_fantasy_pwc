from datetime import date

from f1porra_website.apps.accounts.models import UserProfile
from f1porra_website.apps.public.models import Season


def current_user_profile(request):
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {'current_user_profile': None}

    season = Season.objects.filter(year=date.today().year).first()
    if season is None:
        return {'current_user_profile': None}

    profile = (
        UserProfile.objects.filter(user=request.user, season=season)
        .select_related('users_team')
        .first()
    )
    return {'current_user_profile': profile}