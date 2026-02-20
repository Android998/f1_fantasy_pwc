from django.db.models import Max
from datetime import date
from f1porra_website.apps.public.models import Season, DriverPoints, TeamPoints, Porra, RaceResults, BlockChip

def compute_porra_points():
    # Get the latest Grand Prix based on round number
    current_year = date.today().year
    try:
        current_season = Season.objects.get(year=current_year)
    except Season.DoesNotExist:
        current_season = None  # or handle it as appropriate
    latest_gp = DriverPoints.objects.filter(season=current_season).aggregate(max_nround=Max('gp__nround'))['max_nround']

    if latest_gp is None:
        print("No Grand Prix found.")
        return

    # Get the results for the latest Grand Prix
    race_results = RaceResults.objects.filter(season=current_season).get(gp__nround=latest_gp)

    # Get all Porras for the latest Grand Prix
    porras = Porra.objects.filter(season=current_season, gp__nround=latest_gp)

    for porra in porras:
        total_points = 0
        print(f"\nProcessing Porra for user: {porra.user.username}, GP: {porra.gp.name}")

        # Race Results Section
        # Poleman
        if porra.poleman == race_results.poleman:
            total_points += 5

        # First position
        if porra.first_pos == race_results.first_pos:
            total_points += 10

        # Second position
        if porra.second_pos == race_results.second_pos:
            total_points += 10

        # Third position
        if porra.third_pos == race_results.third_pos:
            total_points += 10

        # Fastest lap
        if porra.fast_lap == race_results.fast_lap:
            total_points += 3

        # Team winner
        if porra.team_winner == race_results.team_winner:
            total_points += 5

        # Fantasy Section
        # Get driver and team points for the latest Grand Prix
        driver_points = DriverPoints.objects.filter(season=current_season, gp__nround=latest_gp)
        team_points = TeamPoints.objects.filter(season=current_season, gp__nround=latest_gp)

         # Apply optional block-chip effects for this user and GP
        block_effect = BlockChip.objects.filter(
            season=current_season,
            gp__nround=latest_gp,
            target=porra.user,
        ).first()

        blocked_driver_id = block_effect.blocked_driver_id if block_effect else None
        blocked_team_id = block_effect.blocked_team_id if block_effect else None

        # Summing up points for selected drivers
        for i, driver in enumerate([porra.driver1, porra.driver2, porra.driver3, porra.driver4, porra.driver5], start=1):
            if driver:
                if blocked_driver_id and driver.id == blocked_driver_id:
                    continue

                driver_point = driver_points.filter(driver=driver).first()
                if driver_point:
                    if i == 1:
                        multiplier = 3 if porra.triple_points_chip else 2
                        total_points += driver_point.points * multiplier
                    else:
                        total_points += driver_point.points

        # Summing up points for selected teams
        for i, team in enumerate([porra.team1, porra.team2], start=1):
            if team:
                if blocked_team_id and team.id == blocked_team_id:
                    continue


        # Print total points for the user
        print(f"Total points for user {porra.user.username}: {total_points}")

        # Update the Porra with the calculated total points
        porra.points = total_points
        porra.save()

    print(f"\nPoints calculation completed for Grand Prix round {latest_gp}.")
