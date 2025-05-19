from f1porra_website.apps.public.models import Season, DriverPoints, TeamPoints, Porra, GrandPrix, Driver, Team
from collections import Counter
from sklearn.preprocessing import MinMaxScaler
from django.db.models import Max
import pandas as pd
from datetime import date

def scale_data(df, field, feature_range):
    scaler = MinMaxScaler(feature_range=feature_range)
    df[field] = scaler.fit_transform(df[field].values.reshape(-1, 1))
    return df

def round_deltas(x):
    if x > 0:  
        if x < round(x):
            return round(x)
        else:
            return round(x+1)  
    else:
        
        if x < round(x):
            return round(x-1)
        else:
            return round(x)
        
def cuadrar_precios(df):
    delta_precios = sum(df.Delta_final)

    df["Cuadrar"] = (df.Delta_final - df.Delta)
    df.sort_values("Cuadrar", inplace=True)
    df.reset_index(drop=True, inplace=True)

    if delta_precios < 0:
        df.loc[(df.index<=-(delta_precios+1))&(df["Delta_final"] < 0), "Delta_final"] += 1

    elif delta_precios > 0: 
        df.loc[(df.index>(max(df.index)-delta_precios))&(df["Delta_final"] > 0), "Delta_final"] += -1


    delta_precios = sum(df.Delta_final)
     
    i = 0

    while delta_precios != 0 and i <= 3:
        print(i, delta_precios)
        i+=1
        df.sort_values("Delta_final", inplace=True)
        df.reset_index(drop=True, inplace=True)

        if delta_precios < 0:
            df.loc[(df.index<=-(delta_precios+1))&(df["Delta_final"] < 0), "Delta_final"] += 1

        elif delta_precios > 0: 
            df.loc[(df.index>(max(df.index)-delta_precios))&(df["Delta_final"] > 0), "Delta_final"] += -1

        delta_precios = sum(df.Delta_final)


    df["Precio Final"] = df.price + df.Delta_final

    
    return df.drop("Cuadrar", axis = 1)

def update_points():
    # Get the latest Grand Prix based on round number
    current_year = date.today().year
    try:
        current_season = Season.objects.get(year=current_year)
    except Season.DoesNotExist:
        current_season = None  # or handle it as appropriate
 
    # Get the current and next GP
    current_gp = DriverPoints.objects.filter(season=current_season).aggregate(max_nround=Max('gp__nround'))['max_nround']
    next_gp = GrandPrix.objects.filter(season=current_season, nround__gt=current_gp).order_by('nround').first()

    # Get the prices for drivers and teams for the current GP
    driver_prices = DriverPoints.objects.filter(season=current_season, gp__nround=current_gp).values('driver_id', 'driver__name', 'points', 'price')
    team_prices = TeamPoints.objects.filter(season=current_season, gp__nround=current_gp).values('team_id', 'team__name', 'points', 'price')

    # Get all fantasy picks for drivers and teams from user Porra submissions
    driver_picks = Porra.objects.filter(season=current_season, gp__nround=current_gp).values('driver1', 'driver2', 'driver3', 'driver4', 'driver5')
    team_picks = Porra.objects.filter(season=current_season, gp__nround=current_gp).values('team1', 'team2')

    # Count picks for drivers
    driver_picks_flat = [pick for sublist in driver_picks.values_list('driver1', 'driver2', 'driver3', 'driver4', 'driver5') for pick in sublist]
    driver_pick_count = Counter(driver_picks_flat)

    # Count picks for teams
    team_picks_flat = [pick for sublist in team_picks.values_list('team1', 'team2') for pick in sublist]
    team_pick_count = Counter(team_picks_flat)

    # Apply scaling to driver and team prices
    driver_prices_df = pd.DataFrame(driver_prices)
    team_prices_df = pd.DataFrame(team_prices)

    # Add the number of picks to drivers and teams dataframes
    driver_prices_df['Picks'] = driver_prices_df['driver_id'].map(driver_pick_count).fillna(0)
    team_prices_df['Picks'] = team_prices_df['team_id'].map(team_pick_count).fillna(0)

    driver_prices_df['Total Points'] = driver_prices_df['Picks'] * driver_prices_df['points']
    team_prices_df['Total Points'] = team_prices_df['Picks'] * team_prices_df['points']
    driver_prices_df = driver_prices_df.loc[~driver_prices_df['Total Points'].isna()]
    team_prices_df = team_prices_df.loc[~team_prices_df['Total Points'].isna()]
    print(driver_prices_df)
    print(team_prices_df)
    # Scale the picks and total points
    driver_prices_df = scale_data(driver_prices_df, 'Picks', (-1, 1))
    driver_prices_df = scale_data(driver_prices_df, 'Total Points', (-1.5, 1.5))

    team_prices_df = scale_data(team_prices_df, 'Picks', (-1, 1))
    team_prices_df = scale_data(team_prices_df, 'Total Points', (-1.5, 1.5))

    # Calculate score and delta for drivers
    driver_prices_df["Score"] = driver_prices_df['Total Points'] - driver_prices_df['Total Points'].median() + driver_prices_df['Picks'] - driver_prices_df['Picks'].median()
    team_prices_df["Score"] = team_prices_df['Total Points'] - team_prices_df['Total Points'].median() + team_prices_df['Picks'] - team_prices_df['Picks'].median()
    
    driver_prices_df = scale_data(driver_prices_df, 'Score', (-1, 1))
    team_prices_df = scale_data(team_prices_df, 'Score', (-1, 1))
    
    
    driver_prices_df['Delta'] = driver_prices_df.apply(lambda row: max(1, row['price'] * 0.1) * row['Score'], axis=1)
    driver_prices_df['Delta_final'] = driver_prices_df['Delta'].apply(round_deltas)

    # Prevent price drops below 1
    driver_prices_df.loc[(driver_prices_df['price'] == 1) & (driver_prices_df['Delta_final'] < 0), 'Delta_final'] = 0

    # Repeat the same logic for teams
    team_prices_df['Delta'] = team_prices_df.apply(lambda row: max(1, row['price'] * 0.1) * row['Score'], axis=1)
    team_prices_df['Delta_final'] = team_prices_df['Delta'].apply(round_deltas)
    team_prices_df.loc[(team_prices_df['price'] == 1) & (team_prices_df['Delta_final'] < 0), 'Delta_final'] = 0

    # Balance driver prices
    driver_prices_df = cuadrar_precios(driver_prices_df)
    team_prices_df = cuadrar_precios(team_prices_df)
    
    print("**************** Final driver prices: ****************\n\n", driver_prices_df, "\n\n")
    print("**************** Final teams prices: ****************\n\n", team_prices_df, "\n\n")


    # Save updated driver prices for the next GP
    for _, row in driver_prices_df.iterrows():
        driver = Driver.objects.filter(season=current_season, name = row.driver__name).first()
        
        DriverPoints.objects.filter(season=current_season).update_or_create(
            season=next_gp.season,
            driver=driver,
            gp=next_gp,
            defaults={'price': row['Precio Final']}
        )

    # Save updated team prices for the next GP
    for _, row in team_prices_df.iterrows():
        team = Team.objects.filter(season=current_season, name = row.team__name).first()

        TeamPoints.objects.filter(season=current_season).update_or_create(
            season=next_gp.season,
            team=team,
            gp=next_gp,
            defaults={'price': row['Precio Final']}
        )
