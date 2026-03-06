from django.shortcuts import redirect, render, get_object_or_404
from django.db.models import Sum, Max, F, Q, Count, Value
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from datetime import datetime
import re
import datetime as dt
import pytz
import json
from datetime import date
from .models import Season, Driver, Team, DriverPoints, TeamPoints, GrandPrix, Porra, RaceResults, BlockChip
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
from f1porra_website.apps.public.services.achievement_service import sync_achievements
from f1porra_website.apps.public.models import Achievement, UserAchievement
from django.contrib.auth.models import User
import logging

from django.core.exceptions import ObjectDoesNotExist
from collections import Counter, defaultdict

logger = logging.getLogger(__name__)

from django.utils import timezone
from django.db.utils import ProgrammingError, OperationalError

# Security: Input validation helpers
def sanitize_string(value, max_length=255, allow_empty=False):
    """Sanitize string input to prevent injection attacks."""
    if value is None:
        return "" if allow_empty else None
    
    if not isinstance(value, str):
        value = str(value)
    
    # Strip whitespace and limit length
    value = value.strip()[:max_length]
    
    # Remove potentially dangerous characters
    value = re.sub(r'[<>"\']', '', value)
    
    if not allow_empty and not value:
        return None
    
    return value

def validate_positive_int(value, max_value=None):
    """Validate that value is a positive integer."""
    try:
        int_val = int(value)
        if int_val < 0:
            return None
        if max_value is not None and int_val > max_value:
            return None
        return int_val
    except (TypeError, ValueError):
        return None

def get_current_season():
    year = timezone.now().year
    try:
        return Season.objects.filter(year=year).first()
    except (ProgrammingError, OperationalError):
        # BBDD aún sin tablas / migraciones
        return None

def adjust_color(hex_color, amount):
    """Safely adjust color with input validation."""
    if not hex_color:
        return "#000000"
    
    # Validate hex color format
    hex_color = hex_color.lstrip('#')
    if not re.match(r'^[0-9A-Fa-f]{6}$', hex_color):
        return "#000000"
    
    # Convert hex to RGB
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
    """Safely normalize name with input validation."""
    if not name:
        return ""
    
    # Sanitize input
    name = sanitize_string(name, max_length=100, allow_empty=True)
    if not name:
        return ""
    
    def fix_mc(word):
        if word.upper() == "RB":
            return "RB"
        if word.lower().startswith("mc") and len(word) > 2:
            # Special case for McLaren and similar names
            return "Mc" + word[2].upper() + word[3:]
        return word.capitalize()
    return ' '.join(fix_mc(word) for word in name.split())


def _madrid_tz():
    return pytz.timezone('Europe/Madrid')


def _ensure_aware_utc(dt):
    if dt is None:
        return None
    if timezone.is_naive(dt):
        # assume stored in UTC when naive
        dt = timezone.make_aware(dt, pytz.UTC)
    return dt.astimezone(pytz.UTC)


def _gp_in_madrid(dt):
    utc_dt = _ensure_aware_utc(dt)
    if utc_dt is None:
        return None
    return utc_dt.astimezone(_madrid_tz())


def _now_madrid():
    return datetime.now(pytz.UTC).astimezone(_madrid_tz())


def _now_utc_from_madrid():
    return _now_madrid().astimezone(pytz.UTC)

def _chip_window(nround):
    if not nround:
        return None
    nround = validate_positive_int(nround)
    if nround is None:
        return None
    return (nround - 1) // 12


def _triple_chip_available(user, gp):
    if not gp or not gp.nround:
        return False
    return not Porra.objects.filter(
        season=get_current_season(),
        user=user,
        gp__nround__gt=_chip_window(gp.nround) * 12,
        gp__nround__lte=(_chip_window(gp.nround) + 1) * 12,
        triple_points_chip=True,
    ).exists()


def _block_chip_available(user, gp):
    if not gp or not gp.nround:
        return False
    return not BlockChip.objects.filter(
        season=get_current_season(),
        blocker=user,
        gp__nround__gt=_chip_window(gp.nround) * 12,
        gp__nround__lte=(_chip_window(gp.nround) + 1) * 12,
    ).exists()


def _block_chip_deadline_passed(gp, now):
    if not gp or not gp.last_edit_date:
        return True

    gp_madrid = _gp_in_madrid(gp.last_edit_date)
    if gp_madrid is None:
        return True

    # Deadline is 24 hours before GP close in Madrid timezone
    deadline_madrid = gp_madrid - dt.timedelta(days=1)
    deadline_utc = deadline_madrid.astimezone(pytz.UTC)

    # Normalize `now` to aware UTC
    if now is None:
        now = _now_utc_from_madrid()
    if timezone.is_naive(now):
        now = timezone.make_aware(now, pytz.UTC)
    else:
        now = now.astimezone(pytz.UTC)

    return now >= deadline_utc


def _get_incoming_block_for_user(user, gp):
    if not gp:
        return None
    return BlockChip.objects.filter(
        season=get_current_season(),
        gp=gp,
        target=user,
    ).select_related('blocker', 'blocked_driver', 'blocked_team').first()


def _remove_blocked_asset_from_porra(user, gp, blocked_driver=None, blocked_team=None):
    if not user or not gp:
        return

    porra = Porra.objects.filter(season=get_current_season(), user=user, gp=gp).first()
    if not porra:
        return

    fields_to_null = []
    if blocked_driver and blocked_driver in [porra.driver1, porra.driver2, porra.driver3, porra.driver4, porra.driver5]:
        for field in ['driver1', 'driver2', 'driver3', 'driver4', 'driver5']:
            if getattr(porra, field) == blocked_driver:
                setattr(porra, field, None)
                fields_to_null.append(field)

    if blocked_team and blocked_team in [porra.team1, porra.team2]:
        for field in ['team1', 'team2']:
            if getattr(porra, field) == blocked_team:
                setattr(porra, field, None)
                fields_to_null.append(field)

    if fields_to_null:
        porra.save(update_fields=fields_to_null)


def _get_latest_gp_round_for_prices():
    current_season = get_current_season()
    if not current_season:
        return None
    
    driver_max = DriverPoints.objects.filter(
        season=current_season,
        price__isnull=False
    ).aggregate(max_round=Max('gp__nround'))['max_round']
    
    team_max = TeamPoints.objects.filter(
        season=current_season,
        price__isnull=False
    ).aggregate(max_round=Max('gp__nround'))['max_round']
    
    if driver_max is None and team_max is None:
        return None
    
    return min(filter(None, [driver_max, team_max]))


def _budget_cap_for_user(user):
    current_season = get_current_season()
    user_profile = UserProfile.objects.get(user=user, season=current_season)
    user_team = user_profile.users_team

    users_teams = UsersTeam.objects.annotate(
        total_points=Coalesce(
            Sum(
                'userprofile__user__porra__points',
                filter=Q(
                    userprofile__season=current_season,
                    userprofile__user__porra__season=current_season,
                ),
            ),
            Value(0),
        )
    ).order_by('total_points')
    last_users_team = users_teams.first() if users_teams.exists() else None

    return 160.0 if user_team == last_users_team else 150.0


# Security: Add rate limiting decorator (simple implementation)
from functools import wraps
from django.core.cache import cache

def rate_limit(key_prefix, limit=10, period=60):
    """Simple rate limiting decorator using Django cache."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if request.user.is_authenticated:
                cache_key = f"{key_prefix}_{request.user.id}"
            else:
                # Use IP address for anonymous users
                x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                if x_forwarded_for:
                    ip = x_forwarded_for.split(',')[0].strip()
                else:
                    ip = request.META.get('REMOTE_ADDR', 'unknown')
                cache_key = f"{key_prefix}_{ip}"
            
            count = cache.get(cache_key, 0)
            if count >= limit:
                return JsonResponse(
                    {'success': False, 'error': 'Too many requests. Please try again later.'},
                    status=429
                )
            
            cache.set(cache_key, count + 1, period)
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


# Create your views here.
def home(request):
    current_season = get_current_season()
    # Get the latest Grand Prix round number considering both drivers and constructors prices
    latest_gp = _get_latest_gp_round_for_prices()
    
    if not latest_gp or not current_season:
        return render(request, 'home.html', {'data': {}})

    # Get the latest Grand Prix details
    latest_grand_prix = GrandPrix.objects.filter(season=current_season, nround=latest_gp).first()
    
    if not latest_grand_prix:
        return render(request, 'home.html', {'data': {}})

    # Calculate time remaining (relative to Spain timezone)
    now_madrid = _now_madrid()
    gp_madrid = _gp_in_madrid(latest_grand_prix.last_edit_date)
    if gp_madrid is None:
        return render(request, 'home.html', {'data': {}})
    time_remaining = gp_madrid - now_madrid
    due_date = gp_madrid <= now_madrid
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

@login_required
def achievements(request):
    sync_achievements()
    current_season = get_current_season()
    profile = None
    if current_season:
        profile = UserProfile.objects.filter(user=request.user, season=current_season).select_related('featured_achievement').first()
    featured_id = profile.featured_achievement_id if profile else None

    achievements = list(Achievement.objects.order_by("sort_order", "name"))
    unlocked_map = {
        ua.achievement_id: ua
        for ua in UserAchievement.objects.filter(user=request.user).select_related("gp", "season")
    }

    payload = []
    for achievement in achievements:
        unlocked = unlocked_map.get(achievement.id)
        unlocked_label = None
        if unlocked:
            if unlocked.gp and unlocked.season:
                unlocked_label = f"{unlocked.gp.country} {unlocked.season.year}"
            elif unlocked.season:
                unlocked_label = f"{unlocked.season.year}"
            elif unlocked.gp:
                unlocked_label = unlocked.gp.country
        payload.append(
            {
                "slug": achievement.slug,
                "name": achievement.name,
                "description": achievement.description,
                "icon": achievement.icon,
                "icon_class": achievement.icon_class,
                "unlocked": bool(unlocked),
                "unlocked_label": unlocked_label,
                "is_featured": achievement.id == featured_id if featured_id else False,
                "id": achievement.id,
            }
        )

    hall_of_famers = {
        "big_guy",
        "hall_of_fame",
        "world_champion",
        "constructor_legend",
        "grand_chelem",
    }
    principiante = {
        "mr_consistency",
        "almost_there",
        "capitan_general",
        "untouchable",
    }
    cojo = {
        "latifisexual",
        "rock_bottom",
        "public_enemy",
    }

    sections = [
        {"title": "Hall of Famers", "achievements": []},
        {"title": "Principiante", "achievements": []},
        {"title": "Cojo", "achievements": []},
        {"title": "Miscelaneo", "achievements": []},
    ]
    section_map = {
        "hall": sections[0]["achievements"],
        "principiante": sections[1]["achievements"],
        "cojo": sections[2]["achievements"],
        "misc": sections[3]["achievements"],
    }

    for item in payload:
        slug = item.get("slug")
        if slug in hall_of_famers:
            section_map["hall"].append(item)
        elif slug in principiante:
            section_map["principiante"].append(item)
        elif slug in cojo:
            section_map["cojo"].append(item)
        else:
            section_map["misc"].append(item)

    unlocked_achievements = [
        {
            "id": item["id"],
            "name": item["name"],
        }
        for item in payload
        if item.get("unlocked")
    ]

    return render(
        request,
        "achievements.html",
        {
            "sections": sections,
            "unlocked_achievements": unlocked_achievements,
            "featured_id": featured_id,
        },
    )


@login_required
@require_POST
def set_featured_achievement(request):
    if request.method != "POST":
        return redirect("public:achievements")

    current_season = get_current_season()
    if current_season is None:
        return redirect("public:achievements")

    user_profile, _ = UserProfile.objects.get_or_create(user=request.user, season=current_season)
    achievement_id = request.POST.get("achievement_id") or None
    if achievement_id in (None, "", "0"):
        user_profile.featured_achievement = None
        user_profile.save(update_fields=["featured_achievement"])
        return redirect("public:achievements")

    try:
        achievement_id_int = int(achievement_id)
    except (TypeError, ValueError):
        return redirect("public:achievements")

    unlocked_ids = set(
        UserAchievement.objects.filter(user=request.user).values_list("achievement_id", flat=True)
    )
    if achievement_id_int not in unlocked_ids:
        return redirect("public:achievements")

    user_profile.featured_achievement_id = achievement_id_int
    user_profile.save(update_fields=["featured_achievement"])
    return redirect("public:achievements")


def prices(request):
    return render(request, 'prices.html')

def rules(request):
    return render(request, 'rules.html')


def bote(request):
    current_season = get_current_season()
    season = current_season or Season.objects.order_by('-year').first()

    if season is None:
        return render(
            request,
            "bote.html",
            {
                "season": None,
                "rows": [],
                "total_pool": 0.0,
                "gps_counted": 0,
            },
        )

    now = _now_utc_from_madrid()
    scored_gp_ids = (
        Porra.objects.filter(
            season=season,
            points__isnull=False,
            gp__last_edit_date__lte=now,
        )
        .values_list("gp_id", flat=True)
        .distinct()
    )
    gps = list(GrandPrix.objects.filter(id__in=scored_gp_ids).order_by("nround", "id"))

    season_profiles = (
        UserProfile.objects.filter(season=season)
        .select_related("user", "users_team")
    )
    profile_by_user_id = {profile.user_id: profile for profile in season_profiles}

    participant_ids = set(profile_by_user_id.keys())
    porra_user_ids = set(
        Porra.objects.filter(season=season, gp_id__in=[gp.id for gp in gps]).values_list("user_id", flat=True)
    )
    participant_ids.update(porra_user_ids)

    penalties = {
        user_id: {"last2": 0.0, "last_team": 0.0}
        for user_id in participant_ids
    }

    team_member_ids = defaultdict(list)
    for profile in season_profiles:
        if profile.users_team_id:
            team_member_ids[profile.users_team_id].append(profile.user_id)

    cumulative_team_points = {team_id: 0.0 for team_id in team_member_ids.keys()}

    for gp in gps:
        gp_entries = list(
            Porra.objects.filter(season=season, gp=gp, points__isnull=False)
            .values("user_id", "points")
        )
        if not gp_entries:
            continue

        # LAST 2 penalties:
        # - Last position: each tied user pays 3€
        # - Penultimate position tie: tied users split 3€ (3/N each)
        unique_scores = sorted({float(entry["points"] or 0.0) for entry in gp_entries})
        worst_score = unique_scores[0]
        worst_users = [entry["user_id"] for entry in gp_entries if float(entry["points"] or 0.0) == worst_score]
        if len(worst_users) > 1:
            split_last_penalty = 6.0 / len(worst_users)
            for user_id in worst_users:
                penalties.setdefault(user_id, {"last2": 0.0, "last_team": 0.0})
                penalties[user_id]["last2"] += split_last_penalty
        else:
            worst_user_id = worst_users[0]
            penalties.setdefault(worst_user_id, {"last2": 0.0, "last_team": 0.0})
            penalties[worst_user_id]["last2"] += 3.0

            if len(unique_scores) > 1:
                penultimate_score = unique_scores[1]
                penultimate_users = [
                    entry["user_id"]
                    for entry in gp_entries
                    if float(entry["points"] or 0.0) == penultimate_score
                ]
                if penultimate_users:
                    split_penalty = 3.0 / len(penultimate_users)
                    for user_id in penultimate_users:
                        penalties.setdefault(user_id, {"last2": 0.0, "last_team": 0.0})
                        penalties[user_id]["last2"] += split_penalty
            else:
                penalties[worst_user_id]["last2"] += 3.0

        # LAST TEAM penalties (accumulated standings after each GP):
        # penalize all members of the team that is last in cumulative team points.
        gp_team_points = defaultdict(float)
        for entry in gp_entries:
            user_id = entry["user_id"]
            profile = profile_by_user_id.get(user_id)
            if profile and profile.users_team_id:
                gp_team_points[profile.users_team_id] += float(entry["points"] or 0.0)

        for team_id in cumulative_team_points.keys():
            cumulative_team_points[team_id] += gp_team_points.get(team_id, 0.0)

        if cumulative_team_points:
            min_total = min(cumulative_team_points.values())
            last_team_ids = [
                team_id
                for team_id, total in cumulative_team_points.items()
                if total == min_total
            ]
            for team_id in last_team_ids:
                for user_id in team_member_ids.get(team_id, []):
                    penalties.setdefault(user_id, {"last2": 0.0, "last_team": 0.0})
                    penalties[user_id]["last_team"] += 3.0

    users_map = {user.id: user for user in User.objects.filter(id__in=participant_ids)}
    rows = []
    for user_id in participant_ids:
        user_obj = users_map.get(user_id)
        if not user_obj:
            continue
        profile = profile_by_user_id.get(user_id)
        team_name = profile.users_team.name if profile and profile.users_team else "No Team"
        last2 = round(penalties.get(user_id, {}).get("last2", 0.0), 2)
        last_team = round(penalties.get(user_id, {}).get("last_team", 0.0), 2)
        total = round(last2 + last_team, 2)
        rows.append(
            {
                "username": user_obj.username,
                "name": user_obj.first_name or user_obj.username,
                "team_name": team_name,
                "last2_penalty": last2,
                "last_team_penalty": last_team,
                "total_penalty": total,
            }
        )

    rows.sort(key=lambda row: (-row["total_penalty"], row["name"].lower()))
    total_pool = round(sum(row["total_penalty"] for row in rows), 2)

    return render(
        request,
        "bote.html",
        {
            "season": season,
            "rows": rows,
            "total_pool": total_pool,
            "gps_counted": len(gps),
        },
    )


@login_required
@require_POST
@rate_limit('use_block_chip', limit=5, period=60)
def use_block_chip(request):
    """Use block chip with enhanced security validation."""
    current_season = get_current_season()
    now = _now_utc_from_madrid()
    
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    # Validate and sanitize inputs
    gp_id = sanitize_string(payload.get('gp_id'), max_length=100)
    target_user_id = validate_positive_int(payload.get('target_user_id'))
    asset_type = sanitize_string(payload.get('asset_type'), max_length=10)
    blocked_asset_id = validate_positive_int(payload.get('blocked_asset_id'))

    if not all([gp_id, target_user_id, asset_type, blocked_asset_id]):
        return JsonResponse({'success': False, 'error': 'Missing or invalid parameters'}, status=400)

    # Validate asset_type
    if asset_type not in [BlockChip.AssetType.DRIVER, BlockChip.AssetType.TEAM]:
        return JsonResponse({'success': False, 'error': 'Tipo de activo no válido.'}, status=400)

    gp = GrandPrix.objects.filter(season=current_season, country=gp_id).first()
    if not gp:
        return JsonResponse({'success': False, 'error': 'GP no válido'}, status=400)

    if _block_chip_deadline_passed(gp, now):
        return JsonResponse({'success': False, 'error': 'El bloqueo debe usarse al menos 24h antes del cierre.'}, status=400)

    if not _block_chip_available(request.user, gp):
        return JsonResponse({'success': False, 'error': 'Ya has usado el chip de bloqueo en este bloque de 12 GPs.'}, status=400)

    # Prevent self-targeting
    if target_user_id == request.user.id:
        return JsonResponse({'success': False, 'error': 'No puedes bloquearte a ti mismo.'}, status=400)

    target = User.objects.filter(id=target_user_id, is_active=True).exclude(id=request.user.id).first()
    if not target:
        return JsonResponse({'success': False, 'error': 'Usuario objetivo no válido.'}, status=400)

    # Verify target has participated in current season
    if not Porra.objects.filter(season=current_season, user=target).exists():
        return JsonResponse({'success': False, 'error': 'El usuario objetivo no participa en esta temporada.'}, status=400)

    if BlockChip.objects.filter(season=current_season, gp=gp, target=target).exists():
        return JsonResponse({'success': False, 'error': 'Ese usuario ya ha sido bloqueado en este GP.'}, status=400)

    blocked_driver = None
    blocked_team = None
    if asset_type == BlockChip.AssetType.DRIVER:
        blocked_driver = Driver.objects.filter(season=current_season, id=blocked_asset_id).first()
        if not blocked_driver:
            return JsonResponse({'success': False, 'error': 'Piloto bloqueado no válido.'}, status=400)
    elif asset_type == BlockChip.AssetType.TEAM:
        blocked_team = Team.objects.filter(season=current_season, id=blocked_asset_id).first()
        if not blocked_team:
            return JsonResponse({'success': False, 'error': 'Constructor bloqueado no válido.'}, status=400)

    BlockChip.objects.create(
        season=current_season,
        gp=gp,
        blocker=request.user,
        target=target,
        asset_type=asset_type,
        blocked_driver=blocked_driver,
        blocked_team=blocked_team,
    )

    _remove_blocked_asset_from_porra(
        user=target,
        gp=gp,
        blocked_driver=blocked_driver,
        blocked_team=blocked_team,
    )

    logger.info(f"Block chip used: {request.user.username} blocked {target.username} for GP {gp.country}")

    return JsonResponse({'success': True})


@login_required
@require_POST
@rate_limit('cancel_block_chip', limit=5, period=60)
def cancel_block_chip(request):
    """Cancel block chip with enhanced security validation."""
    current_season = get_current_season()
    now = _now_utc_from_madrid()
    
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    gp_id = sanitize_string(payload.get('gp_id'), max_length=100)
    if not gp_id:
        return JsonResponse({'success': False, 'error': 'GP ID required'}, status=400)

    gp = GrandPrix.objects.filter(season=current_season, country=gp_id).first()
    if not gp:
        return JsonResponse({'success': False, 'error': 'GP no válido'}, status=400)

    # Only allow cancellation of user's own block
    current_block = BlockChip.objects.filter(
        season=current_season,
        gp=gp,
        blocker=request.user,  # Ensures user can only cancel their own block
    ).select_related('target', 'blocked_driver', 'blocked_team').first()
    
    if not current_block:
        return JsonResponse({'success': False, 'error': 'No tienes un bloqueo activo para este GP.'}, status=400)

    # Check if cancellation is still allowed (e.g., before deadline)
    if _block_chip_deadline_passed(gp, now):
        return JsonResponse({'success': False, 'error': 'No se puede cancelar después del deadline.'}, status=400)

    current_block.delete()
    logger.info(f"Block chip cancelled: {request.user.username} for GP {gp.country}")

    return JsonResponse({'success': True})


def calendar_view(request):
    current_season = get_current_season()
    gp_id = _parse_int(request.GET.get("gp"))
    season = current_season
    if season is None:
        season = Season.objects.order_by("-year").first()

    if season is None:
        return render(
            request,
            "calendar.html",
            {
                "gp_cards": [],
                "selected_gp": None,
                "state_counts": {"next": 0, "future": 0, "past": 0, "locked": 0},
            },
        )

    # Use Madrid as authoritative timezone; convert to UTC for DB queries
    now_madrid = _now_madrid()
    now_utc = now_madrid.astimezone(pytz.UTC)
    gps = list(GrandPrix.objects.filter(season=season).order_by("nround", "id"))
    scored_gp_ids = set(
        Porra.objects.filter(season=season, points__isnull=False).values_list("gp_id", flat=True).distinct()
    )
    user_porra_gp_ids = set()
    if request.user.is_authenticated:
        user_porra_gp_ids = set(
            Porra.objects.filter(season=season, user=request.user).values_list("gp_id", flat=True)
        )

    next_gp_id = None
    for gp in gps:
        if gp.last_edit_date and gp.last_edit_date > now_utc:
            next_gp_id = gp.id
            break

    gp_by_id = {}
    gp_cards = []
    state_counts = {"next": 0, "future": 0, "past": 0, "locked": 0}

    for gp in gps:
        gp_by_id[gp.id] = gp

        reference_dt = gp.gp_end_date or gp.last_edit_date
        if not reference_dt:
            continue

        # Compute race day and locked/past status relative to Spain timezone
        reference_dt_madrid = _gp_in_madrid(reference_dt)
        if reference_dt_madrid is None:
            continue
        race_day = reference_dt_madrid.date()
        is_past = gp.id in scored_gp_ids or (gp.gp_end_date is not None and gp.gp_end_date <= now_utc)
        is_locked = (gp.last_edit_date is not None and gp.last_edit_date <= now_utc and not is_past)

        if gp.id == next_gp_id:
            state = "next"
        elif is_past:
            state = "past"
        elif is_locked:
            state = "locked"
        else:
            state = "future"

        state_counts[state] += 1
        weekend_start = race_day - dt.timedelta(days=2)
        if weekend_start.month == race_day.month:
            date_label = f"{weekend_start.day:02d} - {race_day.day:02d} {race_day.strftime('%b').upper()}"
        else:
            date_label = (
                f"{weekend_start.day:02d} {weekend_start.strftime('%b').upper()} - "
                f"{race_day.day:02d} {race_day.strftime('%b').upper()}"
            )

        actions = []
        if state == "next":
            actions.append({"label": "My Team", "url": reverse("public:team"), "external": False})
        elif state == "past":
            if request.user.is_authenticated and gp.id in user_porra_gp_ids:
                actions.append(
                    {
                        "label": "My Team",
                        "url": reverse(
                            "public:view_team",
                            kwargs={"username": request.user.username, "gp": gp.country},
                        ),
                        "external": False,
                    }
                )
            actions.append(
                {
                    "label": "Standings",
                    "url": f"{reverse('public:standings')}?gp={gp.country}",
                    "external": False,
                }
            )

        gp_cards.append(
            {
                "id": gp.id,
                "round": gp.nround,
                "country": gp.country,
                "name": gp.name,
                "state": state,
                "date_label": date_label,
                "is_selected": gp.id == gp_id,
                "country_link": gp.country_link,
                "gp_photo": gp.gp_photo,
                "actions": actions,
            }
        )

    selected_gp = gp_by_id.get(gp_id) if gp_id else None

    return render(
        request,
        "calendar.html",
        {
            "selected_season": season.year,
            "gp_cards": gp_cards,
            "selected_gp": selected_gp,
            "state_counts": state_counts,
        },
    )

def statistics(request):
    return redirect("public:statistics_users")


def statistics_users(request):
    current_season = get_current_season()
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

@login_required
def use_block_chip(request):
    current_season = get_current_season()
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)

    now = _now_utc_from_madrid()
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    gp_id = payload.get('gp_id')
    target_user_id = payload.get('target_user_id')
    asset_type = payload.get('asset_type')
    blocked_asset_id = payload.get('blocked_asset_id')

    gp = GrandPrix.objects.filter(season=current_season, country=gp_id).first()
    if not gp:
        return JsonResponse({'success': False, 'error': 'GP no válido'}, status=400)

    if _block_chip_deadline_passed(gp, now):
        return JsonResponse({'success': False, 'error': 'El bloqueo debe usarse al menos 24h antes del cierre.'}, status=400)

    if not _block_chip_available(request.user, gp):
        return JsonResponse({'success': False, 'error': 'Ya has usado el chip de bloqueo en este bloque de 12 GPs.'}, status=400)

    target = User.objects.filter(id=target_user_id, is_active=True).exclude(id=request.user.id).first()
    if not target:
        return JsonResponse({'success': False, 'error': 'Usuario objetivo no válido.'}, status=400)

    if BlockChip.objects.filter(season=current_season, gp=gp, target=target).exists():
        return JsonResponse({'success': False, 'error': 'Ese usuario ya ha sido bloqueado en este GP.'}, status=400)

    blocked_driver = None
    blocked_team = None
    if asset_type == BlockChip.AssetType.DRIVER:
        blocked_driver = Driver.objects.filter(season=current_season, id=blocked_asset_id).first()
        if not blocked_driver:
            return JsonResponse({'success': False, 'error': 'Piloto bloqueado no válido.'}, status=400)
    elif asset_type == BlockChip.AssetType.TEAM:
        blocked_team = Team.objects.filter(season=current_season, id=blocked_asset_id).first()
        if not blocked_team:
            return JsonResponse({'success': False, 'error': 'Constructor bloqueado no válido.'}, status=400)
    else:
        return JsonResponse({'success': False, 'error': 'Tipo de activo no válido.'}, status=400)

    BlockChip.objects.create(
        season=current_season,
        gp=gp,
        blocker=request.user,
        target=target,
        asset_type=asset_type,
        blocked_driver=blocked_driver,
        blocked_team=blocked_team,
    )

    _remove_blocked_asset_from_porra(
        user=target,
        gp=gp,
        blocked_driver=blocked_driver,
        blocked_team=blocked_team,
    )

    return JsonResponse({'success': True})


@login_required
def cancel_block_chip(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)

    current_season = get_current_season()
    now = _now_utc_from_madrid()
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    gp_id = payload.get('gp_id')
    gp = GrandPrix.objects.filter(season=current_season, country=gp_id).first()
    if not gp:
        return JsonResponse({'success': False, 'error': 'GP no válido'}, status=400)

    current_block = BlockChip.objects.filter(
        season=current_season,
        gp=gp,
        blocker=request.user,  # Ensures user can only cancel their own block
    ).select_related('target', 'blocked_driver', 'blocked_team').first()
    
    if not current_block:
        return JsonResponse({'success': False, 'error': 'No tienes un bloqueo activo para este GP.'}, status=400)

    if _block_chip_deadline_passed(gp, now):
        return JsonResponse({'success': False, 'error': 'No se puede cancelar después del deadline.'}, status=400)

    current_block.delete()
    return JsonResponse({'success': True})

def standings(request):
    current_season = get_current_season()
    default_season = current_season or Season.objects.order_by('-year').first()
    if default_season is None:
        return render(request, 'standings.html', {
            'user_standings': [],
            'grand_prix_list': [],
            'selected_gp': 'overall',
            'team_standings': [],
            'season_list': [],
            'selected_season': None,
        })

    selected_season_year = request.GET.get('season', str(default_season.year))
    selected_season = Season.objects.filter(year=int(selected_season_year)).first() or default_season
    selected_gp = request.GET.get('gp', 'overall')
    now = _now_utc_from_madrid()

    # Get all completed Grand Prixes (those with points) for the selected season
    grand_prix_with_points = Porra.objects.filter(points__gt=0, season=selected_season).values_list('gp', flat=True).distinct()
    grand_prix_list = GrandPrix.objects.filter(id__in=grand_prix_with_points).order_by('nround')
    available_gp_countries = set(grand_prix_list.values_list('country', flat=True))
    if selected_gp != 'overall' and selected_gp not in available_gp_countries:
        selected_gp = 'overall'

    if selected_gp == 'overall':
        # Overall standings: no filtering by Grand Prix
        porra_entries = Porra.objects.filter(season=selected_season).all()
    else:
        # Filter standings by the selected Grand Prix
        porra_entries = Porra.objects.filter(season=selected_season, gp__country=selected_gp)

    selected_gp_obj = None
    if selected_gp != 'overall':
        selected_gp_obj = GrandPrix.objects.filter(season=selected_season, country=selected_gp).first()

    closed_gps = GrandPrix.objects.filter(season=selected_season, last_edit_date__lte=now).order_by('nround')
    max_closed_gp = closed_gps.last() if closed_gps.exists() else None

    if selected_gp == 'overall':
        reference_round = max_closed_gp.nround if max_closed_gp else None
    else:
        if selected_gp_obj and selected_gp_obj.last_edit_date and selected_gp_obj.last_edit_date <= now:
            reference_round = selected_gp_obj.nround
        else:
            reference_gp = closed_gps.filter(nround__lte=selected_gp_obj.nround).last() if selected_gp_obj else max_closed_gp
            reference_round = reference_gp.nround if reference_gp else None

    drs_used_by_user = set()
    pit_used_by_user = set()
    if reference_round:
        window = _chip_window(reference_round)
        window_start = window * 12
        window_end = min((window + 1) * 12, reference_round)
        drs_used_by_user = set(
            Porra.objects.filter(
                season=selected_season,
                gp__nround__gt=window_start,
                gp__nround__lte=window_end,
                gp__last_edit_date__lte=now,
                triple_points_chip=True,
            ).values_list('user_id', flat=True)
        )
        pit_used_by_user = set(
            BlockChip.objects.filter(
                season=selected_season,
                gp__nround__gt=window_start,
                gp__nround__lte=window_end,
                gp__last_edit_date__lte=now,
            ).values_list('blocker_id', flat=True)
        )
    # Get all users for the selected season who have porras
    all_users = porra_entries.values('user__username').distinct()
    wins_per_user = {user['user__username']: 0 for user in all_users}
    podiums_per_user = {user['user__username']: 0 for user in all_users}
    last_2_per_user = {user['user__username']: 0 for user in all_users}
    wins_per_team = {}

    # Build a season-scoped user profile map to avoid joining all historical user profiles.
    user_ids = list(porra_entries.values_list('user_id', flat=True).distinct())
    season_profiles = {
        profile.user_id: profile
        for profile in UserProfile.objects.filter(user_id__in=user_ids, season=selected_season)
        .select_related('users_team', 'featured_achievement')
    }
    achievements_by_user = defaultdict(list)
    for row in UserAchievement.objects.filter(user_id__in=user_ids).select_related('achievement'):
        if row.achievement:
            achievements_by_user[row.user_id].append(row.achievement)

    for gp in grand_prix_list:
        # Get the relevant Porra entries for this Grand Prix
        gp_entries = porra_entries.filter(season=selected_season, gp=gp)

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
        
        # Calculate team scores for this GP using season-bound profiles.
        team_scores = {}
        for gp_entry in gp_entries.values('user_id', 'points'):
            profile = season_profiles.get(gp_entry['user_id'])
            if not profile or not profile.users_team:
                continue
            team_name = profile.users_team.name
            team_scores[team_name] = team_scores.get(team_name, 0) + (gp_entry['points'] or 0)

        # Determine the team with the highest score and count it as a win
        if team_scores:
            top_team_name = max(team_scores.items(), key=lambda item: item[1])[0]
            wins_per_team[top_team_name] = wins_per_team.get(top_team_name, 0) + 1

    # Aggregate the total points for each user without joining UserProfile.
    raw_user_standings = (
        porra_entries
        .values('user_id', 'user__username', 'user__first_name')
        .annotate(total_points=Sum('points'))
        .order_by('-total_points')
    )

    standings_with_counts = []
    team_points_by_name = {}
    for user in raw_user_standings:
        profile = season_profiles.get(user['user_id'])
        team_name = profile.users_team.name if profile and profile.users_team else None
        photo = profile.photo if profile else None
        username = user['user__username']
        user_achievements = achievements_by_user.get(user['user_id'], [])
        featured = profile.featured_achievement if profile and profile.featured_achievement else None
        featured_id = featured.id if featured else None
        unique_achievements = {}
        for achievement in user_achievements:
            unique_achievements[achievement.id] = achievement
        achievements_list = [
            {
                "id": achievement.id,
                "name": achievement.name,
                "icon": achievement.icon,
                "icon_class": achievement.icon_class,
                "is_featured": achievement.id == featured_id,
            }
            for achievement in unique_achievements.values()
        ]
        achievements_list.sort(key=lambda item: (not item["is_featured"], item["name"].lower()))
        drs_available = user['user_id'] not in drs_used_by_user
        pit_available = user['user_id'] not in pit_used_by_user
        standing_row = {
            'user__username': username,
            'user__first_name': user['user__first_name'],
            'profile_photo': photo,
            'team_name': team_name,
            'total_points': user['total_points'],
            'wins': wins_per_user.get(username, 0),
            'podiums': podiums_per_user.get(username, 0),
            'last_2': last_2_per_user.get(username, 0),
            'achievements_list': achievements_list,
            'chips': {
                'drs_available': drs_available,
                'pit_available': pit_available,
            },
            'featured_achievement': {
                'name': featured.name,
                'icon': featured.icon,
                'icon_class': featured.icon_class,
            } if featured else None,
        }
        standings_with_counts.append(standing_row)

        if team_name:
            team_points_by_name[team_name] = team_points_by_name.get(team_name, 0) + (user['total_points'] or 0)

    team_standings = [
        {
            'team_name': team_name,
            'total_points': total_points,
            'wins': wins_per_team.get(team_name, 0),
        }
        for team_name, total_points in sorted(team_points_by_name.items(), key=lambda item: item[1], reverse=True)
    ]

    return render(request, 'standings.html', {
        'user_standings': standings_with_counts, 
        'grand_prix_list': grand_prix_list, 
        'selected_gp': selected_gp, 
        'team_standings': team_standings,
        'season_list': Season.objects.all().order_by('-year'),
        'selected_season': selected_season
    })  


def view_team(request, username, gp):
    """View team with input validation."""
    current_season = get_current_season()
    
    # Sanitize inputs
    username = sanitize_string(username, max_length=150)
    gp = sanitize_string(gp, max_length=100)
    
    if not username or not gp:
        return render(request, 'view_team.html', {'error': 'Invalid parameters'})
    
    user = get_object_or_404(User, username=username)

    porra_entry = Porra.objects.filter(season=current_season, user=user, gp__country=gp).first()
    if not porra_entry:
        return render(request, 'view_team.html', {'error': 'Team not found'})
    
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
        if not driver:
            continue
        driver_point = DriverPoints.objects.filter(season=current_season, driver=driver, gp=porra_entry.gp).first()
        if driver_point:
            driver_points[key] = {
                'name': driver.name,
                'points': driver_point.points or 0,
                'price': driver_point.price or 0,
            }
            cost_cap += driver_point.price or 0

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
@rate_limit('save_team', limit=10, period=60)
def team(request):
    """Team view with enhanced security."""
    current_season = get_current_season()
    now = _now_utc_from_madrid()
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

        # Sanitize all inputs
        gp_id = sanitize_string(data.get('gp_id'), max_length=100)
        poleman_name = sanitize_string(data.get('poleman_name'), max_length=100)
        first_pos_name = sanitize_string(data.get('first_pos_name'), max_length=100)
        second_pos_name = sanitize_string(data.get('second_pos_name'), max_length=100)
        third_pos_name = sanitize_string(data.get('third_pos_name'), max_length=100)
        fast_lap_name = sanitize_string(data.get('fast_lap_name'), max_length=100)
        best_team_name = sanitize_string(data.get('best_team_name'), max_length=100)
        driver1_name = normalize_name(data.get('driver1'))
        driver2_name = normalize_name(data.get('driver2'))
        driver3_name = normalize_name(data.get('driver3'))
        driver4_name = normalize_name(data.get('driver4'))
        driver5_name = normalize_name(data.get('driver5'))
        team1_name = normalize_name(data.get('team1'))
        team2_name = normalize_name(data.get('team2'))
        use_triple_points_chip = bool(data.get('triple_points_chip', False))

        if not gp_id:
            return JsonResponse({'success': False, 'error': 'GP ID required'}, status=400)
        
        # Get or create the GP
        user = request.user
        gp = GrandPrix.objects.filter(season=current_season, country=gp_id).first()
        
        if not gp:
            return JsonResponse({'success': False, 'error': 'GP no válido'}, status=400)

        # Check if deadline passed (Spain timezone)
        gp_madrid = _gp_in_madrid(gp.last_edit_date)
        now_madrid = _now_madrid()
        if gp_madrid and gp_madrid <= now_madrid:
            return JsonResponse({'success': False, 'error': 'El plazo para editar ha terminado.'}, status=400)

        incoming_block = _get_incoming_block_for_user(user, gp)
        blocked_driver = incoming_block.blocked_driver if incoming_block else None
        blocked_team = incoming_block.blocked_team if incoming_block else None

        blocked_driver_names = {blocked_driver.name} if blocked_driver else set()
        blocked_team_names = {blocked_team.name} if blocked_team else set()

        for driver_name in [driver1_name, driver2_name, driver3_name, driver4_name, driver5_name]:
            if driver_name and driver_name in blocked_driver_names:
                return JsonResponse({'success': False, 'error': 'Ese piloto está bloqueado para este GP.'}, status=400)

        for team_name in [team1_name, team2_name]:
            if team_name and team_name in blocked_team_names:
                return JsonResponse({'success': False, 'error': 'Ese constructor está bloqueado para este GP.'}, status=400)

        if use_triple_points_chip and not _triple_chip_available(user, gp):
            return JsonResponse({'success': False, 'error': 'Ya has usado el chip de triples puntos en este bloque de 12 GPs.'}, status=400)

        # Validate budget
        budget_cap = _budget_cap_for_user(user)
        total_cost = 0
        
        # Calculate total cost of selected drivers and teams
        driver_names = [driver1_name, driver2_name, driver3_name, driver4_name, driver5_name]
        team_names = [team1_name, team2_name]
        
        for d_name in driver_names:
            if d_name:
                driver = Driver.objects.filter(season=current_season, name=d_name).first()
                if driver:
                    dp = DriverPoints.objects.filter(season=current_season, driver=driver, gp=gp).first()
                    if dp and dp.price:
                        total_cost += dp.price

        for t_name in team_names:
            if t_name:
                team_obj = Team.objects.filter(season=current_season, name__iexact=t_name).first()
                if team_obj:
                    tp = TeamPoints.objects.filter(season=current_season, team=team_obj, gp=gp).first()
                    if tp and tp.price:
                        total_cost += tp.price

        if total_cost > budget_cap:
            return JsonResponse({'success': False, 'error': f'Presupuesto excedido. Máximo: {budget_cap}M'}, status=400)

        # Create/update porra
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
                'team_winner': Team.objects.filter(season=current_season, name__iexact=best_team_name).first() if best_team_name else None,
                'driver1': Driver.objects.filter(season=current_season, name=driver1_name).first() if driver1_name else None,
                'driver2': Driver.objects.filter(season=current_season, name=driver2_name).first() if driver2_name else None,
                'driver3': Driver.objects.filter(season=current_season, name=driver3_name).first() if driver3_name else None,
                'driver4': Driver.objects.filter(season=current_season, name=driver4_name).first() if driver4_name else None,
                'driver5': Driver.objects.filter(season=current_season, name=driver5_name).first() if driver5_name else None,
                'team1': Team.objects.filter(season=current_season, name__iexact=team1_name).first() if team1_name else None,
                'team2': Team.objects.filter(season=current_season, name__iexact=team2_name).first() if team2_name else None,
                'triple_points_chip': use_triple_points_chip,
            }
        )

        logger.info(f"Team saved: {request.user.username} for GP {gp.country}")
        return JsonResponse({'success': True})


    # Get the latest Grand Prix round number considering both drivers and constructors prices
    latest_gp = _get_latest_gp_round_for_prices()

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
        now_madrid = _now_madrid()
        gp_madrid = _gp_in_madrid(latest_grand_prix.last_edit_date)
        if gp_madrid is None:
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
        else:
            time_remaining = gp_madrid - now_madrid
            due_date = gp_madrid <= now_madrid
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
    if latest_grand_prix:
        driver_annotations = {
            'total_points': Coalesce(Sum('driverpoints__points'), Value(0)),
            'current_price': Coalesce(Sum('driverpoints__price', filter=Q(driverpoints__gp__id=latest_grand_prix.id)), Value(0)),
        }
        if sec_latest_grand_prix:
            driver_annotations['previous_price'] = Coalesce(Sum('driverpoints__price', filter=Q(driverpoints__gp__id=sec_latest_grand_prix.id)), Value(0))
        drivers = Driver.objects.filter(season=current_season).annotate(**driver_annotations).order_by('-total_points')
    else:
        drivers = Driver.objects.filter(season=current_season).annotate(
            total_points=Coalesce(Sum('driverpoints__points'), Value(0)),
            current_price=Value(0),
            previous_price=Value(0),
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
    if latest_grand_prix:
        team_annotations = {
            'total_points': Coalesce(Sum('teampoints__points'), Value(0)),
            'current_price': Coalesce(Sum('teampoints__price', filter=Q(teampoints__gp__id=latest_grand_prix.id)), Value(0)),
        }
        if sec_latest_grand_prix:
            team_annotations['previous_price'] = Coalesce(Sum('teampoints__price', filter=Q(teampoints__gp__id=sec_latest_grand_prix.id)), Value(0))
        teams = Team.objects.filter(season=current_season).annotate(**team_annotations).order_by('-total_points')
    else:
        teams = Team.objects.filter(season=current_season).annotate(
            total_points=Coalesce(Sum('teampoints__points'), Value(0)),
            current_price=Value(0),
            previous_price=Value(0)
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

    budget_cap = _budget_cap_for_user(user)
    remain_price = budget_cap - total_price
    bar_length = remain_price * 220 / budget_cap

    # Crear un diccionario para mapear nombres a posiciones
    piloto_positions = {name: index + 1 if index<6 else index-4 for index, name in enumerate(porra_list_names) if name != ""}

    triple_chip_available = _triple_chip_available(user, gp) if gp else False
    block_chip_available = _block_chip_available(user, gp) if gp else False
    block_chip_deadline_passed = _block_chip_deadline_passed(gp, now) if gp else True
    current_block = BlockChip.objects.filter(season=current_season, blocker=user, gp=gp).select_related('target', 'blocked_driver', 'blocked_team').first() if gp else None
    incoming_block = _get_incoming_block_for_user(user, gp) if gp else None
    blocked_driver_name = incoming_block.blocked_driver.name if incoming_block and incoming_block.blocked_driver else ''
    blocked_team_name = incoming_block.blocked_team.name if incoming_block and incoming_block.blocked_team else ''
    blocked_users_ids = list(BlockChip.objects.filter(season=current_season, gp=gp).values_list('target_id', flat=True)) if gp else []
    active_user_ids = Porra.objects.filter(season=current_season).values_list('user_id', flat=True).distinct()
    block_targets = (
        User.objects.filter(id__in=active_user_ids, is_active=True)
        .exclude(id=user.id)
        .order_by('username')
        if gp
        else User.objects.none()
    )

    block_chip_reset_message = "Si activas este chip, no podrás volver a usarlo en este bloque de 12 GPs."
    drs_chip_reset_message = block_chip_reset_message
    if gp and gp.nround:
        season_last_round = GrandPrix.objects.filter(season=current_season).aggregate(max_nround=Max('nround'))['max_nround'] or gp.nround
        next_window_round = ((_chip_window(gp.nround) + 1) * 12) + 1
        if next_window_round > season_last_round:
            block_chip_reset_message = "Si activas este chip, no podrás volver a usarlo hasta el final de temporada."
        else:
            block_chip_reset_message = f"Si activas este chip, no podrás volver a usarlo hasta la ronda {next_window_round}."
        drs_chip_reset_message = block_chip_reset_message

    return render(request, 'team.html', {
        'data': data,
        "pilotos": drivers,
        "equipos": teams,
        'user_porra': user_porra,
        'remain_price': remain_price,
        'bar_length': bar_length,
        'budget_cap': budget_cap,
        'porra_list_names': porra_list_names,
        'piloto_positions': piloto_positions,
        'latest_first_pos': latest_first_pos,
        'triple_chip_available': triple_chip_available,
        'block_chip_available': block_chip_available,
        'block_chip_deadline_passed': block_chip_deadline_passed,
        'block_targets': block_targets,
        'blocked_users_ids': blocked_users_ids,
        'current_block': current_block,
        'incoming_block': incoming_block,
        'blocked_driver_name': blocked_driver_name,
        'blocked_team_name': blocked_team_name,
        'block_chip_reset_message': block_chip_reset_message,
        'drs_chip_reset_message': drs_chip_reset_message,
    })
