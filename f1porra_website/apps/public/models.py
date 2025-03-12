from django.db import models
from django.contrib.auth.models import User


#Create your models
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
    """
    Bridge approach:
    - country is STILL primary_key=True for old references, but we add an `id` for the new PK.
    """
    # OLD PK
    country = models.CharField(max_length=64, primary_key=True)  
    # NEW PK (bridge)
    temp_id = models.IntegerField(null=True, blank=True, unique=True)

    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)
    nround = models.PositiveIntegerField(blank=True, null=True)
    name = models.CharField(max_length=64, blank=False, null=False)
    last_edit_date = models.DateTimeField(blank=True, null=True)
    gp_end_date = models.DateTimeField(blank=True, null=True)
    photo_link = models.CharField(max_length=300, blank=True, null=True)
    country_link = models.CharField(max_length=300, blank=True, null=True)
    gp_photo = models.CharField(max_length=300, blank=True, null=True)

    class Meta:
        db_table = 'public_grandprixes'
        verbose_name_plural = 'grandPrixes'

#
# TEAM
#
class Team(models.Model):
    # OLD PK
    name = models.CharField(max_length=64, primary_key=True)
    # NEW PK
    temp_id = models.IntegerField(null=True, blank=True, unique=True)

    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)
    color_rgb = models.CharField(max_length=7, blank=True, null=True)
    photo_link = models.CharField(max_length=300, blank=True, null=True)

    class Meta:
        db_table = 'public_teams'
        verbose_name_plural = 'teams'

#
# DRIVER
#
class Driver(models.Model):
    # OLD PK
    name = models.CharField(max_length=64, primary_key=True)
    # NEW PK
    temp_id = models.IntegerField(null=True, blank=True, unique=True)

    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, blank=True, null=True)
    photo_link = models.CharField(max_length=300, blank=True, null=True)

    class Meta:
        db_table = 'public_drivers'
        verbose_name_plural = 'drivers'
        


class DriverPoints(models.Model):
    class Meta:
        db_table = 'public_driverpoints'
        verbose_name_plural = 'driverpoints'

    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)

    # OLD references
    driver = models.ForeignKey(
        Driver, on_delete=models.CASCADE,
        db_column='driver'  # behind the scenes referencing name
    )
    gp = models.ForeignKey(
        GrandPrix, on_delete=models.CASCADE,
        db_column='country'  # behind the scenes referencing country
    )

    # NEW references (bridge)
    driver_new = models.ForeignKey(
        Driver, on_delete=models.CASCADE, to_field='temp_id', 
        blank=True, null=True, related_name='driverpoints_new'
        # This references the new 'id' in Driver
    )
    gp_new = models.ForeignKey(
        GrandPrix, to_field='temp_id',  on_delete=models.CASCADE,
        blank=True, null=True, related_name='driverpoints_new'
        # This references the new 'id' in GrandPrix
    )

    price = models.PositiveIntegerField(blank=True, null=True)
    points = models.IntegerField(blank=True, null=True)



class TeamPoints(models.Model):
    class Meta:
        db_table = 'public_teampoints'
        verbose_name_plural = 'teampoints'

    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)

    # OLD references
    team = models.ForeignKey(
        Team, on_delete=models.CASCADE,
        db_column='team'  # behind the scenes referencing `Team(name)`
    )
    gp = models.ForeignKey(
        GrandPrix, on_delete=models.CASCADE,
        db_column='country'  # referencing old PK `GrandPrix(country)`
    )

    # NEW references
    team_new = models.ForeignKey(
        Team, to_field='temp_id',  on_delete=models.CASCADE,
        blank=True, null=True, related_name='teampoints_new'
    )
    gp_new = models.ForeignKey(
        GrandPrix, to_field='temp_id', on_delete=models.CASCADE,
        blank=True, null=True, related_name='teampoints_new'
    )

    price = models.PositiveIntegerField(blank=True, null=True)
    points = models.IntegerField(blank=True, null=True)



class Porra(models.Model):
    class Meta:
        db_table = 'public_porra'
        verbose_name_plural = 'porras'

    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)

    # OLD GP
    gp = models.ForeignKey(GrandPrix, on_delete=models.CASCADE)
    # NEW GP
    gp_new = models.ForeignKey(
        GrandPrix, to_field='temp_id', on_delete=models.CASCADE,
        blank=True, null=True, related_name='porra_new'
    )

    fill_date = models.DateTimeField(blank=True, null=True)

    # OLD Driver references
    poleman = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='poleman')
    first_pos = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='first_pos')
    second_pos = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='second_pos')
    third_pos = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='third_pos')
    fast_lap = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='fast_lap')
    driver1 = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='driver1')
    driver2 = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='driver2')
    driver3 = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='driver3')
    driver4 = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='driver4')
    driver5 = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='driver5')

    # OLD Team references
    team_winner = models.ForeignKey(Team, on_delete=models.SET_NULL, blank=True, null=True, related_name='team_winner')
    team1 = models.ForeignKey(Team, on_delete=models.SET_NULL, blank=True, null=True, related_name='team1')
    team2 = models.ForeignKey(Team, on_delete=models.SET_NULL, blank=True, null=True, related_name='team2')

    # NEW Driver references (bridge)
    poleman_new = models.ForeignKey(Driver, to_field='temp_id', on_delete=models.SET_NULL, blank=True, null=True, related_name='poleman_new')
    first_pos_new = models.ForeignKey(Driver, to_field='temp_id', on_delete=models.SET_NULL, blank=True, null=True, related_name='first_pos_new')
    second_pos_new = models.ForeignKey(Driver, to_field='temp_id', on_delete=models.SET_NULL, blank=True, null=True, related_name='second_pos_new')
    third_pos_new = models.ForeignKey(Driver, to_field='temp_id', on_delete=models.SET_NULL, blank=True, null=True, related_name='third_pos_new')
    fast_lap_new = models.ForeignKey(Driver, to_field='temp_id', on_delete=models.SET_NULL, blank=True, null=True, related_name='fast_lap_new')
    driver1_new = models.ForeignKey(Driver, to_field='temp_id', on_delete=models.SET_NULL, blank=True, null=True, related_name='driver1_new')
    driver2_new = models.ForeignKey(Driver, to_field='temp_id', on_delete=models.SET_NULL, blank=True, null=True, related_name='driver2_new')
    driver3_new = models.ForeignKey(Driver, to_field='temp_id', on_delete=models.SET_NULL, blank=True, null=True, related_name='driver3_new')
    driver4_new = models.ForeignKey(Driver, to_field='temp_id', on_delete=models.SET_NULL, blank=True, null=True, related_name='driver4_new')
    driver5_new = models.ForeignKey(Driver, to_field='temp_id', on_delete=models.SET_NULL, blank=True, null=True, related_name='driver5_new')

    # NEW Team references (bridge)
    team_winner_new = models.ForeignKey(Team, to_field='temp_id', on_delete=models.SET_NULL, blank=True, null=True, related_name='team_winner_new')
    team1_new = models.ForeignKey(Team, to_field='temp_id', on_delete=models.SET_NULL, blank=True, null=True, related_name='team1_new')
    team2_new = models.ForeignKey(Team, to_field='temp_id', on_delete=models.SET_NULL, blank=True, null=True, related_name='team2_new')

    points = models.IntegerField(blank=True, null=True)


class RaceResults(models.Model):
    class Meta:
        db_table = 'public_raceresults'
        verbose_name_plural = 'raceresults'

    season = models.ForeignKey(Season, on_delete=models.CASCADE, null=True, blank=True)

    # OLD GP
    gp = models.ForeignKey(GrandPrix, on_delete=models.CASCADE)
    # NEW GP
    gp_new = models.ForeignKey(
        GrandPrix, to_field='temp_id', on_delete=models.CASCADE,
        blank=True, null=True, related_name='raceresults_new'
    )

    # OLD Driver references
    poleman = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='poleman_res')
    first_pos = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='first_pos_res')
    second_pos = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='second_pos_res')
    third_pos = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='third_pos_res')
    fast_lap = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='fast_lap_res')

    # NEW references
    poleman_new = models.ForeignKey(Driver, to_field='temp_id', on_delete=models.SET_NULL, blank=True, null=True, related_name='poleman_res_new')
    first_pos_new = models.ForeignKey(Driver, to_field='temp_id', on_delete=models.SET_NULL, blank=True, null=True, related_name='first_pos_res_new')
    second_pos_new = models.ForeignKey(Driver, to_field='temp_id', on_delete=models.SET_NULL, blank=True, null=True, related_name='second_pos_res_new')
    third_pos_new = models.ForeignKey(Driver, to_field='temp_id', on_delete=models.SET_NULL, blank=True, null=True, related_name='third_pos_res_new')
    fast_lap_new = models.ForeignKey(Driver, to_field='temp_id', on_delete=models.SET_NULL, blank=True, null=True, related_name='fast_lap_res_new')

    team_winner = models.ForeignKey(Team, to_field='temp_id', on_delete=models.SET_NULL, blank=True, null=True, related_name='team_winner_res')
    team_winner_new = models.ForeignKey(Team, to_field='temp_id', on_delete=models.SET_NULL, blank=True, null=True, related_name='team_winner_res_new')