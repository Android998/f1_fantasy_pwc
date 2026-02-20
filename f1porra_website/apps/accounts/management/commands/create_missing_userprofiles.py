# f1porra_website/apps/accounts/management/commands/create_missing_userprofiles.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from datetime import date

from f1porra_website.apps.accounts.models import UserProfile
from f1porra_website.apps.public.models import Season

class Command(BaseCommand):
    help = 'Create missing UserProfile objects for existing User objects'

    def handle(self, *args, **kwargs):
        current_season = Season.objects.filter(year=date.today().year).first()
        if current_season is None:
            self.stdout.write(self.style.WARNING('No current season found; skipping profile creation.'))
            return

        for user in User.objects.all():
            _, created = UserProfile.objects.get_or_create(user=user, season=current_season)
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created UserProfile for user {user.username} ({current_season.year})'))
