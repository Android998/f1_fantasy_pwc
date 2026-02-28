# accounts/models.py
from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from f1porra_website.apps.public.models import Season

class UsersTeam(models.Model):
    MAX_TEAM_MEMBERS = 2
    
    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=255)
    color = models.CharField(max_length=7, blank=True, default='#000000')  # Optional for now
    photo = models.ImageField(upload_to='team_photos/', null=True, blank=True)

    class Meta:
        unique_together = [['season', 'name']]

    def __str__(self):
        season_name = self.season.name if self.season else "No Season"
        return f"{season_name} - {self.name}"
    
    def get_member_count(self):
        """Get the number of members currently in the team."""
        return self.userprofile_set.filter(season=self.season).count()
    
    def is_full(self):
        """Check if the team is at maximum capacity."""
        return self.get_member_count() >= self.MAX_TEAM_MEMBERS
    
    def has_available_space(self):
        """Check if the team has available space for new members."""
        return self.get_member_count() < self.MAX_TEAM_MEMBERS

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