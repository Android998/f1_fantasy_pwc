# accounts/models.py
from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError

class UsersTeam(models.Model):
    name = models.CharField(max_length=255)
    color = models.CharField(max_length=7)  # Assuming hex color codes
    photo = models.ImageField(upload_to='team_photos/', null=True, blank=True)

    def __str__(self):
        return self.name

    def clean(self):
        if self.userprofile_set.count() > 2:
            raise ValidationError('A team can have at most 2 users.')

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    photo = models.ImageField(upload_to='user_photos/', null=True, blank=True)
    users_team = models.ForeignKey(UsersTeam, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.user.username