from django.db import models
from django.contrib.auth.models import User

# Create your models

class Season(models.Model):
    year = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=64, blank=True, null=True)
    start_date = models.DateField(blank=True, null=True)
    end_date = models.DateField(blank=True, null=True)
    
    def __str__(self):
        return self.name or str(self.year)

#
# GRAND PRIX
#
class GrandPrix(models.Model):
    # Using AutoField is recommended for PKs.
    id = models.AutoField(primary_key=True)
    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)
    country = models.CharField(max_length=64)
    nround = models.PositiveIntegerField(blank=True, null=True)
    name = models.CharField(max_length=64)
    last_edit_date = models.DateTimeField(blank=True, null=True)
    gp_end_date = models.DateTimeField(blank=True, null=True)
    photo_link = models.CharField(max_length=300, blank=True, null=True)
    country_link = models.CharField(max_length=300, blank=True, null=True)
    gp_photo = models.CharField(max_length=300, blank=True, null=True)

    class Meta:
        db_table = 'public_grandprixes'
        verbose_name_plural = 'grandPrixes'

    def __str__(self):
        return self.season.name + " - " + self.country or str(self.season.name + " - " + self.name)

#
# TEAM
#
class Team(models.Model):
    id = models.AutoField(primary_key=True)
    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=64)
    color_rgb = models.CharField(max_length=7, blank=True, null=True)
    photo_link = models.CharField(max_length=300, blank=True, null=True)
    selected_link = models.CharField(max_length=300, blank=True, null=True)

    class Meta:
        db_table = 'public_teams'
        verbose_name_plural = 'teams'
    
    def __str__(self):
        return self.season.name + " - " + self.name

#
# DRIVER
#
class Driver(models.Model):
    id = models.AutoField(primary_key=True)
    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=64)
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, blank=True, null=True)
    photo_link = models.CharField(max_length=300, blank=True, null=True)
    selected_link = models.CharField(max_length=300, blank=True, null=True)

    class Meta:
        db_table = 'public_drivers'
        verbose_name_plural = 'drivers'
    
    def __str__(self):
        return self.season.name + " - " + self.name

#
# DRIVER POINTS
#
class DriverPoints(models.Model):
    class Meta:
        db_table = 'public_driverpoints'
        verbose_name_plural = 'driverpoints'

    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)
    # Now referencing the new integer PK field 'id'
    driver = models.ForeignKey(Driver, to_field='id', on_delete=models.CASCADE, blank=True, null=True)
    gp = models.ForeignKey(GrandPrix, to_field='id', on_delete=models.CASCADE, blank=True, null=True)
    price = models.PositiveIntegerField(blank=True, null=True)
    points = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return str(self.season.year) + " " + self.gp.country + " - " + self.driver.name

#
# TEAM POINTS
#
class TeamPoints(models.Model):
    class Meta:
        db_table = 'public_teampoints'
        verbose_name_plural = 'teampoints'

    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)
    team = models.ForeignKey(Team, to_field='id', on_delete=models.CASCADE, blank=True, null=True)
    gp = models.ForeignKey(GrandPrix, to_field='id', on_delete=models.CASCADE, blank=True, null=True)
    price = models.PositiveIntegerField(blank=True, null=True)
    points = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return str(self.season.year) + " " + self.gp.country + " - " + self.team.name


#
# PORRA
#
class Porra(models.Model):
    class Meta:
        db_table = 'public_porra'
        verbose_name_plural = 'porras'

    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    gp = models.ForeignKey(GrandPrix, to_field='id', on_delete=models.CASCADE, blank=True, null=True)
    fill_date = models.DateTimeField(blank=True, null=True)
    poleman = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='poleman')
    first_pos = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='first_pos')
    second_pos = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='second_pos')
    third_pos = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='third_pos')
    fast_lap = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='fast_lap')
    driver1 = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='driver1')
    driver2 = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='driver2')
    driver3 = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='driver3')
    driver4 = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='driver4')
    driver5 = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='driver5')
    team_winner = models.ForeignKey(Team, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='team_winner')
    team1 = models.ForeignKey(Team, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='team1')
    team2 = models.ForeignKey(Team, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='team2')
    triple_points_chip = models.BooleanField(default=False)
    points = models.IntegerField(blank=True, null=True)


class BlockChip(models.Model):
    class AssetType(models.TextChoices):
        DRIVER = 'driver', 'Driver'
        TEAM = 'team', 'Team'

    class Meta:
        db_table = 'public_blockchip'
        verbose_name_plural = 'blockchips'
        constraints = [
            models.UniqueConstraint(fields=['season', 'blocker', 'gp'], name='unique_block_per_gp'),
        ]

    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)
    gp = models.ForeignKey(GrandPrix, to_field='id', on_delete=models.CASCADE)
    blocker = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocks_made')
    target = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocks_received')
    asset_type = models.CharField(max_length=8, choices=AssetType.choices)
    blocked_driver = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True)
    blocked_team = models.ForeignKey(Team, to_field='id', on_delete=models.SET_NULL, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.blocker.username} blocked {self.target.username} ({self.asset_type}) @ {self.gp.country}"

#
# RACE RESULTS
#
class RaceResults(models.Model):
    class Meta:
        db_table = 'public_raceresults'
        verbose_name_plural = 'raceresults'

    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)
    gp = models.ForeignKey(GrandPrix, to_field='id', on_delete=models.CASCADE, blank=True, null=True)
    poleman = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='poleman_res')
    first_pos = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='first_pos_res')
    second_pos = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='second_pos_res')
    third_pos = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='third_pos_res')
    fast_lap = models.ForeignKey(Driver, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='fast_lap_res')
    team_winner = models.ForeignKey(Team, to_field='id', on_delete=models.SET_NULL, blank=True, null=True, related_name='team_winner_res')
