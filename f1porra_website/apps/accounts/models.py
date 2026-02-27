# accounts/models.py
from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from f1porra_website.apps.public.models import Season

class UsersTeam(models.Model):
    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=255)
    color = models.CharField(max_length=7, blank=True, default='#000000')  # Optional for now
    photo = models.ImageField(upload_to='team_photos/', null=True, blank=True)

    class Meta:
        unique_together = [['season', 'name']]

    def __str__(self):
        season_name = self.season.name if self.season else "No Season"
        return f"{season_name} - {self.name}"

class UserProfile(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    photo = models.ImageField(upload_to='user_photos/', null=True, blank=True)
    users_team = models.ForeignKey(UsersTeam, on_delete=models.SET_NULL, null=True, blank=True)
    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        unique_together = [['user', 'season']]

    def __str__(self):
        season_name = self.season.name if self.season else "No Season"
        return f"{season_name} - {self.user.username}"