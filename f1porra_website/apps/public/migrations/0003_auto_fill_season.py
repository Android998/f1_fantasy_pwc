# your_app/migrations/0002_auto_fill_season.py
from django.db import migrations

def assign_default_season(apps, schema_editor):
    Season = apps.get_model('public', 'Season')
    GrandPrix = apps.get_model('public', 'GrandPrix')
    Team = apps.get_model('public', 'Team')
    Driver = apps.get_model('public', 'Driver')
    DriverPoints = apps.get_model('public', 'DriverPoints')
    TeamPoints = apps.get_model('public', 'TeamPoints')
    Porra = apps.get_model('public', 'Porra')
    RaceResults = apps.get_model('public', 'RaceResults')

    # 1) Create or get your default Season row
    default_season, created = Season.objects.get_or_create(
        year=2024,  # or 2023 or any year
        name = '2024 Season',
        defaults={'name': '2024 Season'}  # optional
    )

    # 2) Assign this season to all existing records with null season
    GrandPrix.objects.filter(season__isnull=True).update(season=default_season)
    Team.objects.filter(season__isnull=True).update(season=default_season)
    Driver.objects.filter(season__isnull=True).update(season=default_season)
    DriverPoints.objects.filter(season__isnull=True).update(season=default_season)
    TeamPoints.objects.filter(season__isnull=True).update(season=default_season)
    Porra.objects.filter(season__isnull=True).update(season=default_season)
    RaceResults.objects.filter(season__isnull=True).update(season=default_season)

class Migration(migrations.Migration):

    dependencies = [
        ('public', '0002_season_driver_season_driverpoints_season_and_more'),  # or the last migration
    ]

    operations = [
        migrations.RunPython(assign_default_season, reverse_code=migrations.RunPython.noop),
    ]
