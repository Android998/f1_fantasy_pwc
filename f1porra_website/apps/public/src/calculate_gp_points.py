import requests
import xml.etree.ElementTree as ET
import datetime
import pandas as pd

from django.db.models import Max
from f1porra_website.apps.public.models import Season, DriverPoints, TeamPoints, Driver, Team, GrandPrix

# 1. Driver Points: Participation based on Q3, Q2, Q1
def assign_participation_points(row):
    if pd.notna(row['Q3 Time']):
        return 3
    elif pd.notna(row['Q2 Time']):
        return 2
    elif pd.notna(row['Q1 Time']):
        return 1
    else:
        return 0  # In case there's no qualifying time at all
    

# 2. Reverse Points for Top 10
def assign_reverse_points(position):
    if position <= 10:
        return 11 - position
    else:
        return 0  # No reverse points for positions outside the top 10
    

# 5. Team Points Calculation
# For team points, we first calculate qualifying performance points based on both drivers' results in each team
def calculate_team_qualifying_points(q3_count, q2_count):
    if q3_count == 2:
        return 5  # Both drivers reached Q3
    elif q2_count == 2:
        return 3  # Both drivers reached Q2
    else:
        return 1  # Otherwise


# Adding the 2 points bonus for finishing ahead of the teammate
def add_team_bonus(group):
    if len(group) == 2:
        # If the first driver finishes ahead of their teammate, give 2 points
        if int(group.iloc[0]['Position_Race']) < int(group.iloc[1]['Position_Race']):
            group.iloc[0, group.columns.get_loc('DriverPoints')] += 2
        else:
            group.iloc[1, group.columns.get_loc('DriverPoints')] += 2
    return group

# Calculate driver points
def calculate_race_points(row):
    # Start with the points assigned in the race
    total_points = int(row['Points'])
    
    # If the driver is "Retired," apply the -10 penalty
    if row['Status'] in ['Retired', 'Accident', 'Power Unit', 'Brakes', 'Collision', 'Engine', 'Radiator', 'Collision Damage']:
        return -10
    
    # Points for positions gained (comparing qualy position and race position)
    positions_gained = int(row['Position_Qualy']) - int(row['Position_Race'])
    total_points += positions_gained
    
    return total_points


def compute_gp_points():
    # Get the latest Grand Prix based on round number
    season = datetime.datetime.now().year
    try:
        current_season = Season.objects.get(year=season)
    except Season.DoesNotExist:
        current_season = None  # or handle it as appropriate

    latest_gp_nround = DriverPoints.objects.filter(season=current_season).aggregate(max_nround=Max('gp__nround'))['max_nround']
    latest_gp = GrandPrix.objects.filter(season=current_season).filter(nround = latest_gp_nround).first()
    

    url_race   = f"http://ergast.com/api/f1/{season}/{latest_gp_nround}/results"
    url_qualy  = f"http://ergast.com/api/f1/{season}/{latest_gp_nround}/qualifying"

    print("Getting qualy results...", end="\t")
    r = requests.get(url_qualy)
    print("Done!")
    
    
    print("Request result: " + str(r.status_code))
    print("Calculating qualy results...", end="\t")

    # Parse the XML content
    root = ET.fromstring(r.content)

    # Define the namespace (from the root element in the XML)
    namespace = {'mrd': 'http://ergast.com/mrd/1.5'}

    # Initialize a list to hold each result
    data = []

    # Loop through each qualifying result in the XML
    for result in root.findall('.//mrd:QualifyingResult', namespace):
        # Extract driver information
        driver = result.find('mrd:Driver', namespace)
        driver_name = f"{driver.find('mrd:GivenName', namespace).text} {driver.find('mrd:FamilyName', namespace).text}"
        
        # Extract constructor information
        constructor = result.find('mrd:Constructor', namespace)
        constructor_name = constructor.find('mrd:Name', namespace).text
        
        # Extract qualifying result information
        position = result.attrib['position']
        
        # Use `.find()` to check for Q1, Q2, and Q3, handle cases where times are missing
        q1_time = result.find('mrd:Q1', namespace)
        q1_time = q1_time.text if q1_time is not None else None
        
        q2_time = result.find('mrd:Q2', namespace)
        q2_time = q2_time.text if q2_time is not None else None
        
        q3_time = result.find('mrd:Q3', namespace)
        q3_time = q3_time.text if q3_time is not None else None

        # Append the extracted information to the data list
        data.append({
            'Position': position,
            'Driver': driver_name,
            'Constructor': constructor_name,
            'Q1 Time': q1_time,
            'Q2 Time': q2_time,
            'Q3 Time': q3_time
        })

    # Convert the list of dictionaries to a pandas DataFrame
    qualy_results = pd.DataFrame(data).sort_values(["Q3 Time", "Q2 Time", "Q1 Time"], na_position="last").reset_index(drop=True)
    qualy_results["Position"] = qualy_results.index + 1

    qualy_results['Participation Points'] = qualy_results.apply(assign_participation_points, axis=1)

    qualy_results['Reverse Points'] = qualy_results['Position'].apply(assign_reverse_points)

    # 3. Additional Points: Driver finishing ahead of teammate
    # We assume every team has exactly 2 drivers. The driver with the better position gets an additional point.

    qualy_results['Additional Point'] = qualy_results.groupby('Constructor')['Position'].transform(
        lambda x: (x == x.min()).astype(int)
    )

    # 4. Total Driver Points: Summing up all the points for each driver
    qualy_results['Driver Points'] = qualy_results['Participation Points'] + qualy_results['Reverse Points'] + qualy_results['Additional Point']

        # Aggregate the necessary information for team points
    team_aggregation = qualy_results.groupby('Constructor').agg(
        q3_count=('Q3 Time', lambda x: x.notna().sum()),
        q2_count=('Q2 Time', lambda x: x.notna().sum()),
        team_driver_points=('Driver Points', 'sum')
    ).reset_index()

    # Calculate team qualifying points
    team_aggregation['Team Qualifying Points'] = team_aggregation.apply(
        lambda row: calculate_team_qualifying_points(row['q3_count'], row['q2_count']),
        axis=1
    )

    # Calculate total team points
    team_aggregation['Total Team Points'] = team_aggregation['Team Qualifying Points'] + \
                                            team_aggregation['team_driver_points']

    # Select and rename relevant columns
    team_points_qualy = team_aggregation[['Constructor', 'Team Qualifying Points', 'team_driver_points', 'Total Team Points']]

    print("Done!!")
    print(qualy_results, team_points_qualy)


    print("Getting race results...", end="\t")
    r = requests.get(url_race)
    print("Done!")
    
    
    print("Request result: " + str(r.status_code))
    print("Calculating race results...", end="\t")

    # Parse the XML content
    root = ET.fromstring(r.content)

    # Define the namespace (from the root element in the XML)
    namespace = {'mrd': 'http://ergast.com/mrd/1.5'}

    # Initialize a list to hold each result
    data = []

    # Loop through each result in the XML
    for result in root.findall('.//mrd:Result', namespace):
        # Extract driver information
        driver = result.find('mrd:Driver', namespace)
        driver_name = f"{driver.find('mrd:GivenName', namespace).text} {driver.find('mrd:FamilyName', namespace).text}"
        
        # Extract constructor information
        constructor = result.find('mrd:Constructor', namespace)
        constructor_name = constructor.find('mrd:Name', namespace).text
        
        # Extract race result information
        position = result.attrib['position']
        points = result.attrib['points']
        
        # Extract status
        status = result.find('mrd:Status', namespace).text

        # Append the extracted information to the data list
        data.append({
            'Position': position,
            'Driver': driver_name,
            'Constructor': constructor_name,
            'Points': points,
            'Status': status,  # Adding the status here
        })

    # Convert the list of dictionaries to a pandas DataFrame
    race_results = pd.DataFrame(data)


    try:

        # Merge qualy_results with race_results on 'Driver' to compare positions
        merged_results = pd.merge(race_results, qualy_results[['Driver', 'Position']], on='Driver', how='left', suffixes=('_Race', '_Qualy'))

        # Apply the points calculation for each driver
        merged_results['DriverPoints'] = merged_results.apply(calculate_race_points, axis=1)

        # Apply the team bonus for finishing ahead of a teammate
        merged_results = merged_results.groupby('Constructor').apply(add_team_bonus).reset_index(drop=True)

        # Calculate team points by summing up the driver points
        team_points = merged_results.groupby('Constructor')['DriverPoints'].sum().reset_index()
        team_points.columns = ['Constructor', 'TeamPoints']

        # Print or display the final results with points
        merged_results.Position_Race = merged_results.Position_Race.astype(int)

        # Calculate team points by summing up the driver points for each constructor
        team_points_race = merged_results.groupby('Constructor')['DriverPoints'].sum().reset_index()
        team_points_race.columns = ['Constructor', 'TeamPoints']

    except:
        merged_results = qualy_results.Driver.to_frame()
        merged_results["Position_Race"] = merged_results.index + 1
        merged_results["DriverPoints"] = 0

        team_points_race = team_points_qualy.Constructor.to_frame()
        team_points_race["TeamPoints"] = 0

    print("Done!!")
    print(merged_results, team_points_race)

    total_driver_points = merged_results.set_index("Driver")[["DriverPoints", "Position_Race"]].rename(columns={"DriverPoints":"RacePoints"}).join(qualy_results.set_index("Driver")["Driver Points"].rename("QualyPoints")).reset_index().replace({"Nico Hülkenberg": "Nico Hulkenberg", "Sergio Pérez": "Sergio Perez", "Franco Colapinto ": "Franco Colapinto", "Guanyu Zhou": "Zhou Guanyu"})

    total_driver_points["Total Points"] = total_driver_points.RacePoints + total_driver_points.QualyPoints

    total_team_points = team_points_qualy.set_index("Constructor")["Total Team Points"].rename("QualyPoints").to_frame().join(team_points_race.set_index("Constructor")["TeamPoints"].rename("RacePoints").to_frame()).reset_index().replace({"Alpine F1 Team": "Alpine", "Haas F1 Team": "Haas", "RB F1 Team": "Visa RB", "Sauber": "Kick Sauber", "McLaren": "Mclaren", "Red Bull": "Red Bull Racing"})

    total_team_points["Total Points"] = total_team_points.RacePoints + total_team_points.QualyPoints

    print(total_driver_points, total_team_points)

    print("Updating drivers and teams points...")

    # Save updated driver prices for the next GP
    for _, row in total_driver_points.iterrows():
        print(f"Inserting driver points: {row.Driver}...",  end="\t")
        driver = Driver.objects.filter(season=current_season).filter(name = row.Driver).first()

        DriverPoints.objects.filter(season=current_season).update_or_create(
            driver=driver,
            gp=latest_gp,
            defaults={'points': row['Total Points']}
        )

        print("Done!")

    # Save updated team prices for the next GP
    for _, row in total_team_points.iterrows():
        print(f"Inserting team points: {row.Constructor}...",  end="\t")
        team = Team.objects.filter(season=current_season).filter(name = row.Constructor).first()

        TeamPoints.objects.filter(season=current_season).update_or_create(
            team=team,
            gp=latest_gp,
            defaults={'points': row['Total Points']}
        )

        print("Done!")

    print("Done!!")

