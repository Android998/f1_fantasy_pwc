# accounts/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile
from f1porra_website.apps.public.models import Season
from datetime import datetime

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        current_year = datetime.now().year
        try:
            current_season = Season.objects.get(year=current_year)
            UserProfile.objects.get_or_create(user=instance, season=current_season)
        except Season.DoesNotExist:
            # If no current season, don't create profile
            pass
