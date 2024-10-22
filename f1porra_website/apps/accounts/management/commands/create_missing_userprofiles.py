# f1porra_website/apps/accounts/management/commands/create_missing_userprofiles.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from f1porra_website.apps.accounts.models import UserProfile

class Command(BaseCommand):
    help = 'Create missing UserProfile objects for existing User objects'

    def handle(self, *args, **kwargs):
        users_without_profiles = User.objects.filter(userprofile__isnull=True)
        for user in users_without_profiles:
            UserProfile.objects.create(user=user)
            self.stdout.write(self.style.SUCCESS(f'Created UserProfile for user {user.username}'))
