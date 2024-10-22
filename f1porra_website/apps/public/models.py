from django.db import models
from django.contrib.auth.models import User


#Create your models

#Grand Prixes
class GrandPrix(models.Model):
    class Meta:
        db_table = 'public_grandprixes'
        verbose_name_plural = 'grandPrixes' #Avoids plural misspelling

    nround = models.PositiveIntegerField(blank=True, null=True)
    country = models.CharField(max_length=64, blank=False, null=False, primary_key=True, default="DEFAULT")
    name = models.CharField(max_length=64, blank=False, null=False)
    last_edit_date = models.DateTimeField(blank=True, null=True)
    gp_end_date = models.DateTimeField(blank=True, null=True)
    photo_link = models.CharField(max_length=300, blank=True, null=True)
    country_link = models.CharField(max_length=300, blank=True, null=True)
    gp_photo = models.CharField(max_length=300, blank=True, null=True)


#Teams
class Team(models.Model):
    class Meta:
        db_table = 'public_teams'
        verbose_name_plural = 'teams' #Avoids plural misspelling

    name = models.CharField(max_length=64, blank=False, null=False, primary_key=True)
    color_rgb = models.CharField(max_length=7, blank=True, null=True)
    photo_link = models.CharField(max_length=300, blank=True, null=True)


#Drivers
class Driver(models.Model):
    class Meta:
        db_table = 'public_drivers'
        verbose_name_plural = 'drivers' #Avoids plural misspelling

    name = models.CharField(max_length=64, blank=False, null=False, primary_key=True)
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, blank=True, null=True)
    photo_link = models.CharField(max_length=300, blank=True, null=True)


class DriverPoints(models.Model):
    class Meta:
        db_table = 'public_driverpoints'
        verbose_name_plural = 'driverpoints' #Avoids plural misspelling

    driver = models.ForeignKey(Driver, on_delete=models.CASCADE)
    gp = models.ForeignKey(GrandPrix, on_delete=models.CASCADE, db_column='country')
    price = models.PositiveIntegerField(blank=True, null=True)
    points = models.IntegerField(blank=True, null=True)


class TeamPoints(models.Model):
    class Meta:
        db_table = 'public_teampoints'
        verbose_name_plural = 'teampoints' #Avoids plural misspelling

    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    gp = models.ForeignKey(GrandPrix, on_delete=models.CASCADE, db_column='country')
    price = models.PositiveIntegerField(blank=True, null=True)
    points = models.IntegerField(blank=True, null=True)


#Porra
class Porra(models.Model):
    class Meta:
        db_table = 'public_porra'
        verbose_name_plural = 'porras'  # Avoids plural misspelling

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    gp = models.ForeignKey(GrandPrix, on_delete=models.CASCADE)
    fill_date = models.DateTimeField(blank=True, null=True)
    poleman = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='poleman')
    first_pos = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='first_pos')
    second_pos = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='second_pos')
    third_pos = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='third_pos')
    fast_lap = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='fast_lap')
    team_winner = models.ForeignKey(Team, on_delete=models.SET_NULL, blank=True, null=True, related_name='team_winner')
    driver1 = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='driver1')
    driver2 = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='driver2')
    driver3 = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='driver3')
    driver4 = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='driver4')
    driver5 = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='driver5')
    team1 = models.ForeignKey(Team, on_delete=models.SET_NULL, blank=True, null=True, related_name='team1')
    team2 = models.ForeignKey(Team, on_delete=models.SET_NULL, blank=True, null=True, related_name='team2')
    points = models.IntegerField(blank=True, null=True)
    

class RaceResults(models.Model):
    class Meta:
        db_table = 'public_raceresults'
        verbose_name_plural = 'raceresults' #Avoids plural misspelling
    
    gp = models.ForeignKey(GrandPrix, on_delete=models.CASCADE)
    poleman = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='poleman_res')
    first_pos = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='first_pos_res')
    second_pos = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='second_pos_res')
    third_pos = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='third_pos_res')
    fast_lap = models.ForeignKey(Driver, on_delete=models.SET_NULL, blank=True, null=True, related_name='fast_lap_res')
    team_winner = models.ForeignKey(Team, on_delete=models.SET_NULL, blank=True, null=True, related_name='team_winner_res')
    