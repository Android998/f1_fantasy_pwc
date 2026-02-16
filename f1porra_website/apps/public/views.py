from django.shortcuts import redirect, render, get_object_or_404
from django.db.models import Sum, Max, F, Q, Count, Value
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from datetime import datetime
import datetime as dt
import pytz
import json
from datetime import date
from .models import Season, Driver, Team, DriverPoints, TeamPoints, GrandPrix, Porra, RaceResults
from f1porra_website.apps.accounts.models import UserProfile, UsersTeam
from f1porra_website.apps.public.services import (
    build_assets_matrix_payload,
    build_assets_trends_payload,
    build_matrix_payload,
    build_optimal_team_payload,
    build_teams_matrix_payload,
    build_teams_trends_payload,
    build_trends_payload,
)
from django.contrib.auth.models import User
import logging
from django.core.exceptions import ObjectDoesNotExist
from collections import Counter

logger = logging.getLogger(__name__)

current_year = date.today().year
try:
    current_season = Season.objects.get(year=current_year)
except Season.DoesNotExist:
    current_season = None  # or handle it as appropriate

def adjust_color(hex_color, amount):
    # Convert hex to RGB
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)

    # Adjust each component
    r = min(max(r + amount, 0), 255)
    g = min(max(g + amount, 0), 255)
    b = min(max(b + amount, 0), 255)

    # Convert back to hex
    return "#{:02x}{:02x}{:02x}".format(r, g, b)


def normalize_name(name):
    return ' '.join(word.capitalize() if word != "RB" else "RB" for word in name.split())


# Create your views here.
def home(request):
    # Get the latest Grand Prix round number
    latest_gp = DriverPoints.objects.filter(season=current_season).aggregate(max_nround=Max('gp__nround'))['max_nround']

    # Get the latest Grand Prix details
    latest_grand_prix = GrandPrix.objects.filter(season=current_season).get(nround=latest_gp)

    # Calculate time remaining
    now = datetime.now(pytz.UTC)  # Make the current time timezone-aware
    time_remaining = latest_grand_prix.last_edit_date - now # Calculate time remaining
    due_date = latest_grand_prix.last_edit_date <= now
    days = max(time_remaining.days, 0)
    hours = time_remaining.seconds//3600 if not due_date else 0
    minutes = (time_remaining.seconds//60)%60 if not due_date else 0
    data = {
        'round': latest_grand_prix.nround,
        'name': latest_grand_prix.country,
        'official_name': latest_grand_prix.name,
        'photo_link': latest_grand_prix.photo_link,  
        'country_link': latest_grand_prix.country_link, 
        'gp_photo': latest_grand_prix.gp_photo, 
        'hours': hours,
        'minutes': minutes,
        'days': days,
        'due_date': due_date
    }
    return render(request, 'home.html', {'data': data})

def prices(request):
    return render(request, 'prices.html')

def rules(request):
    return render(request, 'rules.html')

def statistics(request):
    return redirect("public:statistics_users")


def statistics_users(request):
    # Fetch all Grand Prix and Drivers
    grand_prix_list = GrandPrix.objects.filter(season=current_season).order_by('nround')
    driver_list = Driver.objects.filter(season=current_season).order_by('team__name')

    # Get selected filters from request
    selected_grand_prix = request.GET.getlist('grand_prix', [])
    selected_drivers = request.GET.getlist('drivers', [])

    # Fetch filtered data
    driver_points = (
        DriverPoints.objects.filter(season=current_season)
        .select_related('driver', 'gp')
        .filter(points__isnull=False, driver__isnull=False, gp__isnull=False)
    )

    if selected_grand_prix:
        driver_points = driver_points.filter(gp__country__in=selected_grand_prix)

    if selected_drivers:
        driver_points = driver_points.filter(driver__name__in=selected_drivers)

    # Count occurrences of each driver
    driver_counts = Counter(dp.driver.name for dp in driver_points if dp.driver)

    # Get the maximum occurrence of any driver
    max_driver_repeats = max(driver_counts.values(), default=0)  # default=0 if no drivers
    
    # Prepare data for the chart
    labels = []
    datasets = {}
    
    for dp in driver_points:
        if not dp.driver or not dp.gp:
            continue
        if dp.gp.country not in labels:
            labels.append(dp.gp.country) 
        
        if dp.driver.name not in datasets:
            team_color = dp.driver.team.color_rgb if dp.driver.team else '#000000'

            datasets[dp.driver.name] = {
                "label": dp.driver.name,
                "data": [0]*max_driver_repeats,
                "borderColor": team_color,
                "backgroundColor": 'rgba(0, 0, 0, 0)',
                "fill": False,
                "tension": 0.1
            }

            # Adjust colors for the same team
            if driver_counts[dp.driver.name] > 1:
                datasets[dp.driver.name]["borderColor"] = adjust_color(team_color, -40)  # Make it darker
        
        # Assign points to the correct position in the data array
        index = labels.index(dp.gp.country)
        datasets[dp.driver.name]["data"][index] = dp.points

    if selected_grand_prix and selected_drivers:
        # Convert datasets dictionary to a list
        datasets_list = list(datasets.values())
    else:
        # If no filters are applied, set to empty
        datasets_list = []

    context = {
        'labels': json.dumps(labels),
        'datasets': json.dumps(datasets_list),
        'grand_prix_list': grand_prix_list,
        'driver_list': driver_list,
        'selected_grand_prix': selected_grand_prix,
        'selected_drivers': selected_drivers,
    }
    
    return render(request, 'statistics.html', context)


def statistics_assets(request):
    return render(request, "statistics_assets.html")


def statistics_optimal_team(request):
    season = _parse_int(request.GET.get("season"))
    gp_round = _parse_int(request.GET.get("gp"))
    budget = _parse_int(request.GET.get("budget")) or 150
    if budget not in {150, 160}:
        budget = 150

    payload = build_optimal_team_payload(
        season_year=season,
        gp_round=gp_round,
        budget=budget,
    )

    context = {
        "payload": payload,
        "season_options": payload.get("season_options", []),
        "gp_options": payload.get("gp_options", []),
        "selected": payload.get("selected", {}),
        "gp_info": payload.get("gp"),
        "optimal_team": payload.get("optimal_team"),
        "empty_state": payload.get("empty_state", True),
        "reason": payload.get("meta", {}).get("reason"),
    }
    return render(request, "statistics_optimal_team.html", context)


def statistics_matrix_api(request):
    season = _parse_int(request.GET.get("season"))
    gp_from = _parse_int(request.GET.get("gp_from"))
    gp_to = _parse_int(request.GET.get("gp_to"))
    sort_by = request.GET.get("sort_by", "total_points")
    sort_dir = request.GET.get("sort_dir", "desc")
    entity = request.GET.get("entity", "users")

    if entity == "teams":
        payload = build_teams_matrix_payload(
            season_year=season,
            gp_from=gp_from,
            gp_to=gp_to,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
    else:
        payload = build_matrix_payload(
            season_year=season,
            gp_from=gp_from,
            gp_to=gp_to,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
    return JsonResponse(payload)


def statistics_trends_api(request):
    season = _parse_int(request.GET.get("season"))
    gp_from = _parse_int(request.GET.get("gp_from"))
    gp_to = _parse_int(request.GET.get("gp_to"))
    metric = request.GET.get("metric", "cumulative_points")
    preset = request.GET.get("preset")
    current_user_id = request.user.id if request.user.is_authenticated else None
    entity = request.GET.get("entity", "users")

    if entity == "teams":
        teams = _parse_int_list(request.GET.getlist("teams"))
        teams_csv = _parse_int_list([request.GET.get("teams", "")])
        selected_teams = teams if teams else teams_csv
        payload = build_teams_trends_payload(
            season_year=season,
            metric=metric,
            gp_from=gp_from,
            gp_to=gp_to,
            preset=preset,
            current_user_id=current_user_id,
            selected_team_ids=selected_teams or None,
        )
    else:
        users = _parse_int_list(request.GET.getlist("users"))
        users_csv = _parse_int_list([request.GET.get("users", "")])
        selected_users = users if users else users_csv
        payload = build_trends_payload(
            season_year=season,
            metric=metric,
            gp_from=gp_from,
            gp_to=gp_to,
            preset=preset,
            current_user_id=current_user_id,
            selected_user_ids=selected_users or None,
        )
    return JsonResponse(payload)


def statistics_assets_matrix_api(request):
    season = _parse_int(request.GET.get("season"))
    gp_from = _parse_int(request.GET.get("gp_from"))
    gp_to = _parse_int(request.GET.get("gp_to"))
    asset_type = request.GET.get("asset_type", "drivers")
    sort_by = request.GET.get("sort_by", "total_points")
    sort_dir = request.GET.get("sort_dir", "desc")

    payload = build_assets_matrix_payload(
        season_year=season,
        asset_type=asset_type,
        gp_from=gp_from,
        gp_to=gp_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return JsonResponse(payload)


def statistics_assets_trends_api(request):
    season = _parse_int(request.GET.get("season"))
    gp_from = _parse_int(request.GET.get("gp_from"))
    gp_to = _parse_int(request.GET.get("gp_to"))
    asset_type = request.GET.get("asset_type", "drivers")
    metric = request.GET.get("metric", "cumulative_points")
    assets = _parse_int_list(request.GET.getlist("assets"))
    assets_csv = _parse_int_list([request.GET.get("assets", "")])

    selected_assets = assets if assets else assets_csv
    payload = build_assets_trends_payload(
        season_year=season,
        asset_type=asset_type,
        metric=metric,
        gp_from=gp_from,
        gp_to=gp_to,
        selected_asset_ids=selected_assets or None,
    )
    return JsonResponse(payload)


def _parse_int(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_int_list(values):
    parsed = []
    for value in values:
        if value in (None, ""):
            continue
        chunks = str(value).split(",")
        for chunk in chunks:
            item = chunk.strip()
            if not item:
                continue
            try:
                parsed.append(int(item))
            except ValueError:
                continue
    # Preserve order, deduplicate
    return list(dict.fromkeys(parsed))


def standings(request):
    selected_gp = request.GET.get('gp', 'overall')

    # Get all users and initialize counts
    all_users = UserProfile.objects.all().values('user__username')
    wins_per_user = {user['user__username']: 0 for user in all_users}
    podiums_per_user = {user['user__username']: 0 for user in all_users}
    last_2_per_user = {user['user__username']: 0 for user in all_users}
    wins_per_team = {}

    # Get all completed Grand Prixes (those with points)
    grand_prix_with_points = Porra.objects.filter(points__gt=0).values_list('gp', flat=True).distinct().filter(season=current_season)
    grand_prix_list = GrandPrix.objects.filter(id__in=grand_prix_with_points).order_by('nround')
    print(grand_prix_list)

    if selected_gp == 'overall':
        # Overall standings: no filtering by Grand Prix
        porra_entries = Porra.objects.filter(season=current_season).all()
    else:
        # Filter standings by the selected Grand Prix
        porra_entries = Porra.objects.filter(season=current_season, gp__country=selected_gp)

    for gp in grand_prix_list:
        # Get the relevant Porra entries for this Grand Prix
        gp_entries = porra_entries.filter(season=current_season, gp=gp)

        # Get the last two positions
        last_two_entries = gp_entries.order_by('points')[:2].values('user__username')

        # Determine the top 3 scores
        top_3_scores = gp_entries.order_by('-points')[:3]
        top_3_users = top_3_scores.values('user__username', 'points')

        max_points = top_3_scores.first().points if top_3_scores.exists() else 0

        # Update wins and podiums
        for top_user in top_3_users:
            username = top_user['user__username']

            # Count wins only for the top scorer
            if top_user['points'] == max_points:
                wins_per_user[username] += 1

            # Update podiums
            podiums_per_user[username] += 1

        # Update last 2 positions
        for last_user in last_two_entries:
            username = last_user['user__username']
            last_2_per_user[username] += 1
        
        # Calculate team scores for this GP
        team_scores = (
            gp_entries
            .values('user__userprofile__users_team__name')  # Group by team name
            .annotate(team_points=Sum('points'))  # Sum of points per team
            .filter(user__userprofile__users_team__name__isnull=False)  # Exclude users with no team
            .order_by('-team_points')  # Order by points descending
        )

        # Determine the team with the highest score and count it as a win
        if team_scores.exists():
            top_team = team_scores.first()
            top_team_name = top_team['user__userprofile__users_team__name']
            wins_per_team[top_team_name] = wins_per_team.get(top_team_name, 0) + 1

    # Aggregate the total points for each user
    user_standings = porra_entries.values(
        'user__username',
        'user__first_name',
        'user__userprofile__photo',
        'user__userprofile__users_team__name'
    ).annotate(total_points=Sum('points')).order_by('-total_points')

    team_standings = (
        porra_entries
        .values('user__userprofile__users_team__name')  # Group by team name
        .annotate(
            total_points=Sum('points')  # Sum of points per team
        )
        .filter(user__userprofile__users_team__name__isnull=False)  # Exclude users with no team
        .order_by('-total_points')  # Order by points descending
    )

    # Add wins to each team's standings
    for team in team_standings:
        team_name = team['user__userprofile__users_team__name']
        team['wins'] = wins_per_team.get(team_name, 0)

    # Merge the standings, wins, podiums, and last 2 into a single list of dictionaries
    standings_with_counts = []
    for user in user_standings:
        username = user['user__username']
        user['wins'] = wins_per_user.get(username, 0)
        user['podiums'] = podiums_per_user.get(username, 0)
        user['last_2'] = last_2_per_user.get(username, 0)
        standings_with_counts.append(user)

    return render(request, 'standings.html', {'user_standings': standings_with_counts, 'grand_prix_list': grand_prix_list, 'selected_gp': selected_gp, 'team_standings': team_standings})  


def view_team(request, username, gp):
    user = get_object_or_404(User, username=username)

    porra_entry = Porra.objects.filter(season=current_season, user=user, gp__country=gp).first()
    try:
        race_results = RaceResults.objects.get(season=current_season, gp=porra_entry.gp)
    except ObjectDoesNotExist:
        race_results = None

    # Initialize cost cap
    cost_cap = 0

    # Points and cost for drivers 1-5
    driver_points = {}
    drivers = {'driver1': porra_entry.driver1, 'driver2': porra_entry.driver2, 'driver3': porra_entry.driver3, 'driver4': porra_entry.driver4, 'driver5': porra_entry.driver5}
    for key, driver in drivers.items():
        driver_point = DriverPoints.objects.get(season=current_season, driver=driver, gp=porra_entry.gp)
        driver_points[key] = {'points': driver_point.points if driver_point.points else 0, 'price': driver_point.price if driver_point.price else 0}
        cost_cap += driver_point.price if driver_point.price else 0

    # Points and cost for teams 1-2
    team_points = {}
    teams = {'team1': porra_entry.team1, 'team2': porra_entry.team2}
    for key, team in teams.items():
        print(team, porra_entry.gp)
        team_point = TeamPoints.objects.get(season=current_season, team=team, gp=porra_entry.gp)
        team_points[key] = {'points': team_point.points if team_point.points else 0, 'price': team_point.price if team_point.price else 0}
        cost_cap += team_point.price if team_point.price else 0

    bonus_points = {
        'poleman': 5 if race_results and porra_entry.poleman == race_results.poleman else 0,
        'first_pos': 10 if race_results and porra_entry.first_pos == race_results.first_pos else 0,
        'second_pos': 10 if race_results and porra_entry.second_pos == race_results.second_pos else 0,
        'third_pos': 10 if race_results and porra_entry.third_pos == race_results.third_pos else 0,
        'fast_lap': 3 if race_results and porra_entry.fast_lap == race_results.fast_lap else 0,
        'team_winner': 5 if race_results and porra_entry.team_winner == race_results.team_winner else 0,
    }

    # Prepare the context
    context = {
        'teamuser': user,
        'porra_entries': porra_entry,
        'driver_points': driver_points,
        'team_points': team_points,
        'bonus_points': bonus_points,
        'cost_cap': cost_cap,
        'gp': gp,
    }

    return render(request, 'view_team.html', context)


@login_required
def team(request):
    now = datetime.now(pytz.UTC)  # Make the current time timezone-aware
    if request.method == 'POST':
        try:
            data = json.loads(request.body)

            #Get data from json
            gp_id = data.get('gp_id')
            poleman_name = data.get('poleman_name')
            first_pos_name = data.get('first_pos_name')
            second_pos_name = data.get('second_pos_name')
            third_pos_name = data.get('third_pos_name')
            fast_lap_name = data.get('fast_lap_name')
            best_team_name = data.get('best_team_name')
            driver1_name = normalize_name(data.get('driver1'))
            driver2_name = normalize_name(data.get('driver2'))
            driver3_name = normalize_name(data.get('driver3'))
            driver4_name = normalize_name(data.get('driver4'))
            driver5_name = normalize_name(data.get('driver5'))
            team1_name = normalize_name(data.get('team1'))
            team2_name = normalize_name(data.get('team2'))
            

            # Get or create the GP
            user = request.user
            gp = GrandPrix.objects.get(season=current_season, country=gp_id)

            # Obtener o crear la porra para el usuario y el GP
            porra, created = Porra.objects.update_or_create(
                user=request.user,
                gp=gp,
                defaults={
                    "season": current_season,
                    'fill_date': now,
                    'poleman': Driver.objects.filter(season=current_season, name=poleman_name).first() if poleman_name else None,
                    'first_pos': Driver.objects.filter(season=current_season, name=first_pos_name).first() if first_pos_name else None,
                    'second_pos': Driver.objects.filter(season=current_season, name=second_pos_name).first() if second_pos_name else None,
                    'third_pos': Driver.objects.filter(season=current_season, name=third_pos_name).first() if third_pos_name else None,
                    'fast_lap': Driver.objects.filter(season=current_season, name=fast_lap_name).first() if fast_lap_name else None,
                    'team_winner': Team.objects.filter(season=current_season, name=best_team_name).first() if best_team_name else None,
                    'driver1': Driver.objects.filter(season=current_season, name=driver1_name).first() if driver1_name else None,
                    'driver2': Driver.objects.filter(season=current_season, name=driver2_name).first() if driver2_name else None,
                    'driver3': Driver.objects.filter(season=current_season, name=driver3_name).first() if driver3_name else None,
                    'driver4': Driver.objects.filter(season=current_season, name=driver4_name).first() if driver4_name else None,
                    'driver5': Driver.objects.filter(season=current_season, name=driver5_name).first() if driver5_name else None,
                    'team1': Team.objects.filter(season=current_season, name=team1_name).first() if team1_name else None,
                    'team2': Team.objects.filter(season=current_season, name=team2_name).first() if team2_name else None,
                }
            )
          

            return JsonResponse({'success': True})
        
        except json.JSONDecodeError as e:
            logger.error(f"JSONDecodeError: {e}")
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
        except Exception as e:
            logger.error(f"Exception: {e}")
            return JsonResponse({'success': False, 'error': str(e)}, status=500)
        

    # Get the latest Grand Prix round number
    latest_gp = DriverPoints.objects.filter(season=current_season).aggregate(max_nround=Max('gp__nround'))['max_nround']

    # Default placeholders
    latest_grand_prix = None
    sec_latest_grand_prix = None

    # Determine second latest only when there's more than one round
    second_latest_gp = None
    if latest_gp and latest_gp > 1:
        second_latest_gp = latest_gp - 1

    # Use .first() to avoid DoesNotExist exceptions
    if latest_gp:
        latest_grand_prix = GrandPrix.objects.filter(season=current_season, nround=latest_gp).first()
    if second_latest_gp:
        sec_latest_grand_prix = GrandPrix.objects.filter(season=current_season, nround=second_latest_gp).first()

    # Calculate time remaining only when latest GP and its date exist
    if latest_grand_prix and latest_grand_prix.last_edit_date:
        time_remaining = latest_grand_prix.last_edit_date - now
        due_date = latest_grand_prix.last_edit_date <= now
        days = max(time_remaining.days, 0)
        hours = time_remaining.seconds // 3600 if not due_date else 0
        minutes = (time_remaining.seconds // 60) % 60 if not due_date else 0

        data = {
            'round': latest_grand_prix.nround,
            'name': latest_grand_prix.country,
            'official_name': latest_grand_prix.name,
            'photo_link': latest_grand_prix.photo_link,
            'country_link': latest_grand_prix.country_link,
            'gp_photo': latest_grand_prix.gp_photo,
            'hours': hours,
            'minutes': minutes,
            'days': days,
            'due_date': due_date
        }
    else:
        data = {
            'round': latest_gp,
            'name': '',
            'official_name': '',
            'photo_link': '',
            'country_link': '',
            'gp_photo': '',
            'hours': 0,
            'minutes': 0,
            'days': 0,
            'due_date': True
        }

    # Calculate the number of porras
    total_porras = Porra.objects.filter(season=current_season).count()

    # Compute pick rates for drivers
    driver_pick_counts = Porra.objects.filter(season=current_season).values('driver1', 'driver2', 'driver3', 'driver4', 'driver5').annotate(
        count_driver1=Count('driver1'),
        count_driver2=Count('driver2'),
        count_driver3=Count('driver3'),
        count_driver4=Count('driver4'),
        count_driver5=Count('driver5')
    )

    # Aggregate pick counts for drivers
    driver_pick_rates = {}
    for entry in driver_pick_counts:
        for key in ['driver1', 'driver2', 'driver3', 'driver4', 'driver5']:
            driver_id = entry[key]
            if driver_id is not None:
                driver_pick_rates[driver_id] = driver_pick_rates.get(driver_id, 0) + entry[f'count_{key}']

    # Compute pick rates for teams
    team_pick_counts = Porra.objects.filter(season=current_season).values('team1', 'team2').annotate(
        count_team1=Count('team1'),
        count_team2=Count('team2')
    )

    # Aggregate pick counts for teams
    team_pick_rates = {}
    for entry in team_pick_counts:
        for key in ['team1', 'team2']:
            team_id = entry[key]
            if team_id is not None:
                team_pick_rates[team_id] = team_pick_rates.get(team_id, 0) + entry[f'count_{key}']


    # Drivers
    # Annotate prices only when GP info available; otherwise only total points
    if latest_grand_prix and sec_latest_grand_prix:
        drivers = Driver.objects.filter(season=current_season).annotate(
            total_points=Coalesce(Sum('driverpoints__points'), Value(0)),
            current_price=Coalesce(Sum('driverpoints__price', filter=Q(driverpoints__gp__id=latest_grand_prix.id)), Value(0)),
            previous_price=Coalesce(Sum('driverpoints__price', filter=Q(driverpoints__gp__id=sec_latest_grand_prix.id)), Value(0))
        ).order_by('-total_points')
    else:
        drivers = Driver.objects.filter(season=current_season).annotate(
            total_points=Coalesce(Sum('driverpoints__points'), Value(0))
        ).order_by('-total_points')

    for driver in drivers:
        # Ensure price fields exist
        current_price = getattr(driver, 'current_price', 0) or 0
        previous_price = getattr(driver, 'previous_price', 0) or 0
        driver.price_change = current_price - previous_price if previous_price else 0
        # Avoid division by zero when there are no porras
        if total_porras and total_porras > 0:
            driver.pick_rate = round(driver_pick_rates.get(driver.id, 0) * 100.0 / total_porras, 1)
        else:
            driver.pick_rate = 0


    # Teams
    if latest_grand_prix and sec_latest_grand_prix:
        teams = Team.objects.filter(season=current_season).annotate(
            total_points=Coalesce(Sum('teampoints__points'), Value(0)),
            current_price=Coalesce(Sum('teampoints__price', filter=Q(teampoints__gp__id=latest_grand_prix.id)), Value(0)),
            previous_price=Coalesce(Sum('teampoints__price', filter=Q(teampoints__gp__id=sec_latest_grand_prix.id)), Value(0))
        ).order_by('-total_points')
    else:
        teams = Team.objects.filter(season=current_season).annotate(
            total_points=Coalesce(Sum('teampoints__points'), Value(0))
        ).order_by('-total_points')

    for team in teams:
        current_price = getattr(team, 'current_price', 0) or 0
        previous_price = getattr(team, 'previous_price', 0) or 0
        team.price_change = current_price - previous_price if previous_price else 0
        if total_porras and total_porras > 0:
            team.pick_rate = round(team_pick_rates.get(team.id, 0) * 100.0 / total_porras, 1)
        else:
            team.pick_rate = 0


    # Get the user's Porra for the latest Grand Prix
    user = request.user
    user_profile = UserProfile.objects.get(user=user)
    user_team = user_profile.users_team
    gp = GrandPrix.objects.filter(season=current_season, nround=latest_gp).first() if latest_gp else None
    last_gp = GrandPrix.objects.filter(season=current_season, nround=second_latest_gp).first() if second_latest_gp else None

    # Get user's porra only if there's a latest GP
    if gp:
        try:
            user_porra = Porra.objects.get(user=user, gp=gp, season=current_season)
        except Porra.DoesNotExist:
            user_porra = {}
    else:
        user_porra = {}

    # Get latest first_pos from the previous GP when available
    if last_gp:
        try:
            latest_first_pos_obj = Porra.objects.filter(season=current_season).get(user=user, gp=last_gp)
            latest_first_pos = latest_first_pos_obj.first_pos.name if latest_first_pos_obj.first_pos else ""
        except Porra.DoesNotExist:
            latest_first_pos = ""
    else:
        latest_first_pos = ""

    # Initialize total price and price change dictionaries
    total_price = 0
    porra_list_names = []

    if user_porra:
        # Get prices for drivers
        drivers_in_porra = [
            user_porra.driver1, user_porra.driver2, user_porra.driver3, user_porra.driver4, user_porra.driver5]
        teams_in_porra = [user_porra.team1, user_porra.team2]

        for driver in drivers_in_porra:
            if driver:
                porra_list_names.append(driver.name)
                if latest_grand_prix:
                    driver.current_price = DriverPoints.objects.filter(driver=driver, gp=latest_grand_prix).aggregate(Sum('price'))['price__sum'] or 0
                else:
                    driver.current_price = 0
                if sec_latest_grand_prix:
                    previous_price = DriverPoints.objects.filter(driver=driver, gp=sec_latest_grand_prix).aggregate(Sum('price'))['price__sum'] or 0
                else:
                    previous_price = 0
                driver.price_change = driver.current_price - previous_price
                total_price += driver.current_price
            else:
                porra_list_names.append("")

        for team in teams_in_porra:
            if team:
                porra_list_names.append(team.name)
                if latest_grand_prix:
                    team.current_price = TeamPoints.objects.filter(team=team, gp=latest_grand_prix).aggregate(Sum('price'))['price__sum'] or 0
                else:
                    team.current_price = 0
                if sec_latest_grand_prix:
                    previous_price = TeamPoints.objects.filter(team=team, gp=sec_latest_grand_prix).aggregate(Sum('price'))['price__sum'] or 0
                else:
                    previous_price = 0
                team.price_change = team.current_price - previous_price
                total_price += team.current_price
            else:
                porra_list_names.append("")

    # Calculate total points for each UsersTeam
    users_teams = UsersTeam.objects.annotate(
        total_points=Coalesce(Sum('userprofile__user__porra__points', filter=Q(userprofile__user__porra__season=current_season)), Value(0))
    ).order_by('total_points')  # Ascending order to get the team with the lowest points
    last_users_team = users_teams.first() if users_teams.exists() else None

    # Check if the user is in the last-placed UsersTeam
    if user_team == last_users_team:
        remain_price = 160.0 - total_price
        bar_length = remain_price * 220 / 160
    else:
        remain_price = 150.0 - total_price
        bar_length = remain_price * 220 / 150

    # Crear un diccionario para mapear nombres a posiciones
    piloto_positions = {name: index + 1 if index<6 else index-4 for index, name in enumerate(porra_list_names) if name != ""}

    return render(request, 'team.html', {'data': data, "pilotos": drivers, "equipos": teams, 'user_porra': user_porra, 'remain_price': remain_price, 'bar_length': bar_length, 'porra_list_names': porra_list_names, 'piloto_positions': piloto_positions, 'latest_first_pos':latest_first_pos})
