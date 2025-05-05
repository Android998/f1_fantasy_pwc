from f1porra_website.apps.public.models import Season, DriverPoints, TeamPoints, GrandPrix, Driver, Team
from django.db.models import Max
import pandas as pd
import datetime

PATH = "C:/Users/agurtubay/OneDrive - Microsoft/Desktop/PuntosF1.xlsx"

# Get the latest Grand Prix based on round number
season = datetime.datetime.now().year
try:
    current_season = Season.objects.get(year=season)
except Season.DoesNotExist:
    current_season = None  # or handle it as appropriate

print(f"Current season: {current_season}")

latest_gp_nround = DriverPoints.objects.filter(season=current_season).aggregate(max_nround=Max('gp__nround'))['max_nround']
latest_gp = GrandPrix.objects.filter(season=current_season).filter(nround = latest_gp_nround).first()

def read_data():
    df_drivers = pd.read_excel(PATH, sheet_name="Drivers", header=1, usecols="B:C")
    df_teams = pd.read_excel(PATH, sheet_name="Teams", header=1, usecols="B:C")
    return df_drivers, df_teams

def insert_points(df_drivers, df_teams):
    # Save updated driver prices for the next GP
    for _, row in df_drivers.iterrows():
        print(f"Inserting driver points: {row.Piloto}...",  end="\t")
        driver = Driver.objects.filter(season=current_season).filter(name = row.Piloto).first()

        DriverPoints.objects.filter(season=current_season).filter(gp = latest_gp).update_or_create(
            driver=driver,
            gp=latest_gp,
            defaults={'points': row['Puntos Totales']}
        )

        print("Done!")

    # Save updated team prices for the next GP
    for _, row in df_teams.iterrows():
        print(f"Inserting team points: {row.Equipos}...",  end="\t")
        team = Team.objects.filter(season=current_season).filter(name = row.Equipos).first()

        TeamPoints.objects.filter(season=current_season).filter(gp = latest_gp).update_or_create(
            team=team,
            gp=latest_gp,
            defaults={'points': row['Puntos Totales']}
        )

        print("Done!")

    print("Done!!")

def upload_points():
    df_drivers, df_teams = read_data()
    insert_points(df_drivers, df_teams)
    print("Points uploaded successfully!")