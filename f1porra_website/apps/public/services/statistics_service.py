from __future__ import annotations

from collections import defaultdict
from itertools import combinations
import re
from pathlib import Path
from statistics import pstdev
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User

from f1porra_website.apps.accounts.models import UserProfile
from f1porra_website.apps.public.models import DriverPoints, GrandPrix, Porra, RaceResults, Season, TeamPoints


ALLOWED_SORT_FIELDS = {
    "username",
    "team_name",
    "total_points",
    "avg_points_gp",
    "wins_gp",
    "podiums_gp",
    "bottom3_gp",
    "volatility",
    "consistency",
    "best_gp_points",
    "worst_gp_points",
    "gps_played",
    "teammate_h2h_wins",
    "teammate_h2h_losses",
    "teammate_h2h_ties",
}

ALLOWED_TREND_METRICS = {
    "cumulative_points",
    "points_per_gp",
    "rank_per_gp",
    "gap_to_leader",
}

ALLOWED_PRESETS = {
    "me_teammate",
    "me_vs_user",
    "top3",
    "bottom3",
    "all",
    "my_team",
}

ALLOWED_TEAM_PRESETS = {
    "my_team",
    "top3",
    "bottom3",
    "all",
}

ALLOWED_ASSET_TYPES = {"drivers", "constructors"}
ALLOWED_ASSET_METRICS = {
    "cumulative_points",
    "points_per_gp",
    "rank_per_gp",
    "gap_to_leader",
    "price",
    "price_change_gp",
    "points_per_million_gp",
    "cumulative_points_per_million",
    "rolling_avg_points_3gp",
    "rolling_avg_points_per_million_3gp",
    "pick_rate_gp",
}

BONUS_POINTS = {
    "poleman": 5,
    "first_pos": 10,
    "second_pos": 10,
    "third_pos": 10,
    "fast_lap": 3,
    "team_winner": 5,
}


def build_matrix_payload(
    *,
    season_year: int | None = None,
    gp_from: int | None = None,
    gp_to: int | None = None,
    sort_by: str = "total_points",
    sort_dir: str = "desc",
) -> dict[str, Any]:
    """Builds user statistics matrix payload for the requested season/range.

    This is a read-only backend service meant to be consumed by future JSON API views.
    """
    season = _resolve_season(season_year)

    if season is None:
        return {
            "entity_type": "users",
            "season": season_year,
            "rows": [],
            "sort_by": _normalize_sort_by(sort_by),
            "sort_dir": _normalize_sort_dir(sort_dir),
            "empty_state": True,
            "meta": {
                "reason": "season_not_found_or_no_scored_data",
                "scored_gps": 0,
                "total_users": 0,
            },
        }

    gps = _get_scored_gps(season=season, gp_from=gp_from, gp_to=gp_to)
    if not gps:
        return {
            "entity_type": "users",
            "season": season.year,
            "rows": [],
            "sort_by": _normalize_sort_by(sort_by),
            "sort_dir": _normalize_sort_dir(sort_dir),
            "empty_state": True,
            "meta": {
                "reason": "no_scored_gps_in_range",
                "scored_gps": 0,
                "total_users": 0,
            },
        }

    gp_ids = [gp.id for gp in gps]

    porras = list(
        Porra.objects.filter(season=season, gp_id__in=gp_ids, points__isnull=False)
        .select_related("user", "gp")
        .order_by("gp__nround", "user__username")
    )

    if not porras:
        return {
            "entity_type": "users",
            "season": season.year,
            "rows": [],
            "sort_by": _normalize_sort_by(sort_by),
            "sort_dir": _normalize_sort_dir(sort_dir),
            "empty_state": True,
            "meta": {
                "reason": "no_scored_entries",
                "scored_gps": len(gp_ids),
                "total_users": 0,
            },
        }

    users_by_id: dict[int, User] = {}
    user_scores_by_gp: dict[int, dict[int, float]] = defaultdict(dict)
    gp_scores: dict[int, list[tuple[int, float]]] = defaultdict(list)

    for porra in porras:
        if porra.points is None:
            continue
        points = float(porra.points)
        users_by_id[porra.user_id] = porra.user
        user_scores_by_gp[porra.user_id][porra.gp_id] = points
        gp_scores[porra.gp_id].append((porra.user_id, points))

    wins, podiums, bottom3 = _compute_gp_position_counts(gp_scores)
    team_by_user_id, teammate_by_user_id = _build_team_maps(season=season)

    rows: list[dict[str, Any]] = []
    for user_id, user in users_by_id.items():
        scores = list(user_scores_by_gp[user_id].values())
        gps_played = len(scores)
        total_points = sum(scores)
        avg_points_gp = (total_points / gps_played) if gps_played else 0.0
        volatility = pstdev(scores) if gps_played > 1 else 0.0
        consistency = 1.0 / (1.0 + volatility)
        best_gp_points = max(scores) if scores else 0.0
        worst_gp_points = min(scores) if scores else 0.0

        h2h_w, h2h_l, h2h_t = _compute_teammate_h2h(
            user_id=user_id,
            teammate_id=teammate_by_user_id.get(user_id),
            scores_by_user=user_scores_by_gp,
        )

        rows.append(
            {
                "user_id": user_id,
                "username": user.username,
                "team_name": team_by_user_id.get(user_id),
                "total_points": round(total_points, 2),
                "avg_points_gp": round(avg_points_gp, 2),
                "wins_gp": wins.get(user_id, 0),
                "podiums_gp": podiums.get(user_id, 0),
                "bottom3_gp": bottom3.get(user_id, 0),
                "volatility": round(volatility, 4),
                "consistency": round(consistency, 4),
                "best_gp_points": round(best_gp_points, 2),
                "worst_gp_points": round(worst_gp_points, 2),
                "gps_played": gps_played,
                "teammate_h2h_wins": h2h_w,
                "teammate_h2h_losses": h2h_l,
                "teammate_h2h_ties": h2h_t,
            }
        )

    normalized_sort_by = _normalize_sort_by(sort_by)
    normalized_sort_dir = _normalize_sort_dir(sort_dir)

    rows = _sort_rows(rows, sort_by=normalized_sort_by, sort_dir=normalized_sort_dir)

    return {
        "entity_type": "users",
        "season": season.year,
        "rows": rows,
        "sort_by": normalized_sort_by,
        "sort_dir": normalized_sort_dir,
        "empty_state": False,
        "meta": {
            "reason": None,
            "scored_gps": len(gp_ids),
            "total_users": len(rows),
            "gp_from": gp_from,
            "gp_to": gp_to,
        },
    }


def build_trends_payload(
    *,
    season_year: int | None = None,
    metric: str = "cumulative_points",
    gp_from: int | None = None,
    gp_to: int | None = None,
    preset: str | None = None,
    current_user_id: int | None = None,
    selected_user_ids: list[int] | None = None,
) -> dict[str, Any]:
    season = _resolve_season(season_year)
    normalized_metric = _normalize_trend_metric(metric)
    normalized_preset = _normalize_preset(preset)

    if season is None:
        return {
            "entity_type": "users",
            "season": season_year,
            "metric": normalized_metric,
            "preset": normalized_preset,
            "labels": [],
            "gp_options": [],
            "series": [],
            "resolved_user_ids": [],
            "empty_state": True,
            "meta": {"reason": "season_not_found_or_no_scored_data", "scored_gps": 0},
        }

    gps = _get_scored_gps(season=season, gp_from=gp_from, gp_to=gp_to)
    if not gps:
        return {
            "entity_type": "users",
            "season": season.year,
            "metric": normalized_metric,
            "preset": normalized_preset,
            "labels": [],
            "gp_options": [],
            "series": [],
            "resolved_user_ids": [],
            "empty_state": True,
            "meta": {"reason": "no_scored_gps_in_range", "scored_gps": 0},
        }

    gp_ids = [gp.id for gp in gps]
    labels = [gp.country for gp in gps]
    gp_options = [{"round": gp.nround, "name": gp.country} for gp in gps]
    porras = list(
        Porra.objects.filter(season=season, gp_id__in=gp_ids, points__isnull=False)
        .select_related("user")
        .order_by("gp__nround", "user__username")
    )
    if not porras:
        return {
            "entity_type": "users",
            "season": season.year,
            "metric": normalized_metric,
            "preset": normalized_preset,
            "labels": labels,
            "gp_options": gp_options,
            "series": [],
            "resolved_user_ids": [],
            "empty_state": True,
            "meta": {"reason": "no_scored_entries", "scored_gps": len(gps)},
        }

    users_by_id: dict[int, User] = {}
    scores_by_user: dict[int, dict[int, float]] = defaultdict(dict)
    for porra in porras:
        points = float(porra.points)
        users_by_id[porra.user_id] = porra.user
        scores_by_user[porra.user_id][porra.gp_id] = points

    team_by_user_id, teammate_by_user_id = _build_team_maps(season=season)

    resolved_user_ids = _resolve_trend_users(
        users_by_id=users_by_id,
        scores_by_user=scores_by_user,
        teammate_by_user_id=teammate_by_user_id,
        selected_user_ids=selected_user_ids,
        preset=normalized_preset,
        current_user_id=current_user_id,
    )

    all_cumulative_by_gp: dict[int, dict[int, float]] = {}
    running_all: dict[int, float] = {uid: 0.0 for uid in users_by_id}
    for gp in gps:
        gp_scores = scores_by_user
        for uid in users_by_id:
            running_all[uid] += gp_scores.get(uid, {}).get(gp.id, 0.0)
        all_cumulative_by_gp[gp.id] = dict(running_all)

    series: list[dict[str, Any]] = []
    for user_id in resolved_user_ids:
        user = users_by_id[user_id]
        data = _build_series_data_for_user(
            metric=normalized_metric,
            user_id=user_id,
            gps=gps,
            scores_by_user=scores_by_user,
            all_cumulative_by_gp=all_cumulative_by_gp,
        )
        series.append(
            {
                "user_id": user_id,
                "username": user.username,
                "team_name": team_by_user_id.get(user_id),
                "data": data,
            }
        )

    return {
        "entity_type": "users",
        "season": season.year,
        "metric": normalized_metric,
        "preset": normalized_preset,
        "labels": labels,
        "gp_options": gp_options,
        "series": series,
        "resolved_user_ids": resolved_user_ids,
        "empty_state": False,
        "meta": {
            "reason": None,
            "scored_gps": len(gps),
            "total_series": len(series),
            "gp_from": gp_from,
            "gp_to": gp_to,
        },
    }


def build_teams_matrix_payload(
    *,
    season_year: int | None = None,
    gp_from: int | None = None,
    gp_to: int | None = None,
    sort_by: str = "total_points",
    sort_dir: str = "desc",
) -> dict[str, Any]:
    season = _resolve_season(season_year)

    if season is None:
        return {
            "entity_type": "teams",
            "season": season_year,
            "rows": [],
            "sort_by": _normalize_sort_by(sort_by),
            "sort_dir": _normalize_sort_dir(sort_dir),
            "empty_state": True,
            "meta": {
                "reason": "season_not_found_or_no_scored_data",
                "scored_gps": 0,
                "total_teams": 0,
            },
        }

    gps = _get_scored_gps(season=season, gp_from=gp_from, gp_to=gp_to)
    if not gps:
        return {
            "entity_type": "teams",
            "season": season.year,
            "rows": [],
            "sort_by": _normalize_sort_by(sort_by),
            "sort_dir": _normalize_sort_dir(sort_dir),
            "empty_state": True,
            "meta": {
                "reason": "no_scored_gps_in_range",
                "scored_gps": 0,
                "total_teams": 0,
            },
        }

    gp_ids = [gp.id for gp in gps]
    porras = list(
        Porra.objects.filter(season=season, gp_id__in=gp_ids, points__isnull=False)
        .select_related("user", "gp")
        .order_by("gp__nround", "user__username")
    )

    if not porras:
        return {
            "entity_type": "teams",
            "season": season.year,
            "rows": [],
            "sort_by": _normalize_sort_by(sort_by),
            "sort_dir": _normalize_sort_dir(sort_dir),
            "empty_state": True,
            "meta": {
                "reason": "no_scored_entries",
                "scored_gps": len(gp_ids),
                "total_teams": 0,
            },
        }

    team_by_user_id, team_names_by_id, members_by_team_id = _build_users_team_maps(season=season)
    if not team_names_by_id:
        return {
            "entity_type": "teams",
            "season": season.year,
            "rows": [],
            "sort_by": _normalize_sort_by(sort_by),
            "sort_dir": _normalize_sort_dir(sort_dir),
            "empty_state": True,
            "meta": {
                "reason": "no_teams_found",
                "scored_gps": len(gp_ids),
                "total_teams": 0,
            },
        }

    scores_by_team: dict[int, dict[int, float]] = defaultdict(dict)
    gp_scores: dict[int, list[tuple[int, float]]] = defaultdict(list)

    for porra in porras:
        team_id = team_by_user_id.get(porra.user_id)
        if team_id is None:
            continue
        points = float(porra.points or 0.0)
        scores_by_team[team_id][porra.gp_id] = scores_by_team[team_id].get(porra.gp_id, 0.0) + points

    for team_id, scores in scores_by_team.items():
        for gp_id, points in scores.items():
            gp_scores[gp_id].append((team_id, points))

    wins, podiums, bottom3 = _compute_gp_position_counts(gp_scores)

    rows: list[dict[str, Any]] = []
    for team_id, team_name in team_names_by_id.items():
        scores = list(scores_by_team.get(team_id, {}).values())
        if not scores:
            continue
        gps_played = len(scores)
        total_points = sum(scores)
        avg_points_gp = (total_points / gps_played) if gps_played else 0.0
        volatility = pstdev(scores) if gps_played > 1 else 0.0
        members = sorted(members_by_team_id.get(team_id, []), key=str.lower)

        rows.append(
            {
                "team_id": team_id,
                "team_name": team_name,
                "members": members,
                "total_points": round(total_points, 2),
                "avg_points_gp": round(avg_points_gp, 2),
                "wins_gp": wins.get(team_id, 0),
                "podiums_gp": podiums.get(team_id, 0),
                "bottom3_gp": bottom3.get(team_id, 0),
                "volatility": round(volatility, 4),
                "gps_played": gps_played,
            }
        )

    normalized_sort_by = _normalize_sort_by(sort_by)
    normalized_sort_dir = _normalize_sort_dir(sort_dir)
    rows = _sort_rows(rows, sort_by=normalized_sort_by, sort_dir=normalized_sort_dir)

    return {
        "entity_type": "teams",
        "season": season.year,
        "rows": rows,
        "sort_by": normalized_sort_by,
        "sort_dir": normalized_sort_dir,
        "empty_state": len(rows) == 0,
        "meta": {
            "reason": None if rows else "no_team_rows",
            "scored_gps": len(gp_ids),
            "total_teams": len(rows),
        },
    }


def build_teams_trends_payload(
    *,
    season_year: int | None = None,
    metric: str = "cumulative_points",
    gp_from: int | None = None,
    gp_to: int | None = None,
    preset: str | None = None,
    current_user_id: int | None = None,
    selected_team_ids: list[int] | None = None,
) -> dict[str, Any]:
    season = _resolve_season(season_year)
    normalized_metric = _normalize_trend_metric(metric)
    normalized_preset = _normalize_team_preset(preset)

    if season is None:
        return {
            "entity_type": "teams",
            "season": season_year,
            "metric": normalized_metric,
            "preset": normalized_preset,
            "labels": [],
            "gp_options": [],
            "series": [],
            "resolved_team_ids": [],
            "empty_state": True,
            "meta": {"reason": "season_not_found_or_no_scored_data", "scored_gps": 0},
        }

    gps = _get_scored_gps(season=season, gp_from=gp_from, gp_to=gp_to)
    if not gps:
        return {
            "entity_type": "teams",
            "season": season.year,
            "metric": normalized_metric,
            "preset": normalized_preset,
            "labels": [],
            "gp_options": [],
            "series": [],
            "resolved_team_ids": [],
            "empty_state": True,
            "meta": {"reason": "no_scored_gps_in_range", "scored_gps": 0},
        }

    gp_ids = [gp.id for gp in gps]
    labels = [gp.country for gp in gps]
    gp_options = [{"round": gp.nround, "name": gp.country} for gp in gps]

    porras = list(
        Porra.objects.filter(season=season, gp_id__in=gp_ids, points__isnull=False)
        .select_related("user", "gp")
        .order_by("gp__nround", "user__username")
    )

    if not porras:
        return {
            "entity_type": "teams",
            "season": season.year,
            "metric": normalized_metric,
            "preset": normalized_preset,
            "labels": labels,
            "gp_options": gp_options,
            "series": [],
            "resolved_team_ids": [],
            "empty_state": True,
            "meta": {"reason": "no_scored_entries", "scored_gps": len(gps)},
        }

    team_by_user_id, team_names_by_id, members_by_team_id = _build_users_team_maps(season=season)
    if not team_names_by_id:
        return {
            "entity_type": "teams",
            "season": season.year,
            "metric": normalized_metric,
            "preset": normalized_preset,
            "labels": labels,
            "gp_options": gp_options,
            "series": [],
            "resolved_team_ids": [],
            "empty_state": True,
            "meta": {"reason": "no_teams_found", "scored_gps": len(gps)},
        }

    scores_by_team: dict[int, dict[int, float]] = defaultdict(dict)
    for porra in porras:
        team_id = team_by_user_id.get(porra.user_id)
        if team_id is None:
            continue
        points = float(porra.points or 0.0)
        scores_by_team[team_id][porra.gp_id] = scores_by_team[team_id].get(porra.gp_id, 0.0) + points

    resolved_team_ids = _resolve_trend_teams(
        team_names_by_id=team_names_by_id,
        scores_by_team=scores_by_team,
        selected_team_ids=selected_team_ids,
        preset=normalized_preset,
        current_user_id=current_user_id,
        team_by_user_id=team_by_user_id,
    )

    all_cumulative_by_gp: dict[int, dict[int, float]] = {}
    running_all = {tid: 0.0 for tid in team_names_by_id}
    for gp in gps:
        for tid in team_names_by_id:
            running_all[tid] += scores_by_team.get(tid, {}).get(gp.id, 0.0)
        all_cumulative_by_gp[gp.id] = dict(running_all)

    series: list[dict[str, Any]] = []
    for team_id in resolved_team_ids:
        data = _build_series_data_for_user(
            metric=normalized_metric,
            user_id=team_id,
            gps=gps,
            scores_by_user=scores_by_team,
            all_cumulative_by_gp=all_cumulative_by_gp,
        )
        series.append(
            {
                "team_id": team_id,
                "team_name": team_names_by_id.get(team_id),
                "members": sorted(members_by_team_id.get(team_id, []), key=str.lower),
                "data": data,
            }
        )

    return {
        "entity_type": "teams",
        "season": season.year,
        "metric": normalized_metric,
        "preset": normalized_preset,
        "labels": labels,
        "gp_options": gp_options,
        "series": series,
        "resolved_team_ids": resolved_team_ids,
        "empty_state": False,
        "meta": {
            "reason": None,
            "scored_gps": len(gps),
            "total_series": len(series),
            "gp_from": gp_from,
            "gp_to": gp_to,
        },
    }


def build_assets_matrix_payload(
    *,
    season_year: int | None = None,
    asset_type: str = "drivers",
    gp_from: int | None = None,
    gp_to: int | None = None,
    sort_by: str = "total_points",
    sort_dir: str = "desc",
) -> dict[str, Any]:
    season = _resolve_season(season_year)
    normalized_type = _normalize_asset_type(asset_type)
    normalized_sort_dir = _normalize_sort_dir(sort_dir)

    if season is None:
        return {
            "season": season_year,
            "asset_type": normalized_type,
            "rows": [],
            "sort_by": sort_by,
            "sort_dir": normalized_sort_dir,
            "empty_state": True,
            "meta": {"reason": "season_not_found_or_no_scored_data", "scored_gps": 0},
        }

    gps = _get_scored_gps(season=season, gp_from=gp_from, gp_to=gp_to)
    if not gps:
        return {
            "season": season.year,
            "asset_type": normalized_type,
            "rows": [],
            "sort_by": sort_by,
            "sort_dir": normalized_sort_dir,
            "empty_state": True,
            "meta": {"reason": "no_scored_gps_in_range", "scored_gps": 0},
        }

    gp_ids = [gp.id for gp in gps]
    if normalized_type == "drivers":
        rows = _build_driver_rows(season=season, gp_ids=gp_ids)
    else:
        rows = _build_constructor_rows(season=season, gp_ids=gp_ids)

    rows = _sort_asset_rows(rows, sort_by=sort_by, sort_dir=normalized_sort_dir)
    return {
        "season": season.year,
        "asset_type": normalized_type,
        "rows": rows,
        "sort_by": sort_by,
        "sort_dir": normalized_sort_dir,
        "empty_state": len(rows) == 0,
        "meta": {"reason": None if rows else "no_asset_rows", "scored_gps": len(gp_ids), "total_assets": len(rows)},
    }


def build_assets_trends_payload(
    *,
    season_year: int | None = None,
    asset_type: str = "drivers",
    metric: str = "cumulative_points",
    gp_from: int | None = None,
    gp_to: int | None = None,
    selected_asset_ids: list[int] | None = None,
) -> dict[str, Any]:
    season = _resolve_season(season_year)
    normalized_type = _normalize_asset_type(asset_type)
    normalized_metric = _normalize_asset_metric(metric)

    if season is None:
        return {
            "season": season_year,
            "asset_type": normalized_type,
            "metric": normalized_metric,
            "labels": [],
            "gp_options": [],
            "series": [],
            "empty_state": True,
            "meta": {"reason": "season_not_found_or_no_scored_data", "scored_gps": 0},
        }

    gps = _get_scored_gps(season=season, gp_from=gp_from, gp_to=gp_to)
    if not gps:
        return {
            "season": season.year,
            "asset_type": normalized_type,
            "metric": normalized_metric,
            "labels": [],
            "gp_options": [],
            "series": [],
            "empty_state": True,
            "meta": {"reason": "no_scored_gps_in_range", "scored_gps": 0},
        }

    gp_ids = [gp.id for gp in gps]
    labels = [gp.country for gp in gps]
    gp_options = [{"round": gp.nround, "name": gp.country} for gp in gps]

    if normalized_type == "drivers":
        points_qs = DriverPoints.objects.filter(
            season=season, gp_id__in=gp_ids, driver__isnull=False
        ).select_related("driver", "driver__team", "gp")
        key_field = "driver_id"
        name_getter = lambda row: row.driver.name
        group_name = "driver_name"
        _slots_per_entry = 5
    else:
        points_qs = TeamPoints.objects.filter(
            season=season, gp_id__in=gp_ids, team__isnull=False
        ).select_related("team", "gp")
        key_field = "team_id"
        name_getter = lambda row: row.team.name
        group_name = "team_name"
        _slots_per_entry = 2

    scores_by_asset: dict[int, dict[int, float]] = defaultdict(dict)
    prices_by_asset: dict[int, dict[int, float]] = defaultdict(dict)
    names_by_asset: dict[int, str] = {}
    team_names_by_asset: dict[int, str | None] = {}
    team_colors_by_asset: dict[int, str | None] = {}
    for row in points_qs:
        asset_id = getattr(row, key_field)
        names_by_asset[asset_id] = name_getter(row)
        if normalized_type == "drivers":
            team_names_by_asset[asset_id] = row.driver.team.name if row.driver and row.driver.team else None
            team_colors_by_asset[asset_id] = (
                row.driver.team.color_rgb if row.driver and row.driver.team and row.driver.team.color_rgb else None
            )
        else:
            team_names_by_asset[asset_id] = row.team.name if row.team else None
            team_colors_by_asset[asset_id] = row.team.color_rgb if row.team and row.team.color_rgb else None
        if row.points is not None:
            scores_by_asset[asset_id][row.gp_id] = float(row.points)
        if row.price is not None:
            prices_by_asset[asset_id][row.gp_id] = float(row.price)

    pick_counts_by_gp_asset: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    gp_entries_count: dict[int, int] = defaultdict(int)
    if normalized_type == "drivers":
        picks_rows = Porra.objects.filter(season=season, gp_id__in=gp_ids).values_list(
            "gp_id", "driver1_id", "driver2_id", "driver3_id", "driver4_id", "driver5_id"
        )
    else:
        picks_rows = Porra.objects.filter(season=season, gp_id__in=gp_ids).values_list(
            "gp_id", "team1_id", "team2_id"
        )
    for row in picks_rows:
        gp_id = row[0]
        gp_entries_count[gp_id] += 1
        for asset_id in row[1:]:
            if asset_id is None:
                continue
            pick_counts_by_gp_asset[gp_id][asset_id] += 1

    if not names_by_asset:
        return {
            "season": season.year,
            "asset_type": normalized_type,
            "metric": normalized_metric,
            "labels": labels,
            "gp_options": gp_options,
            "series": [],
            "empty_state": True,
            "meta": {"reason": "no_asset_points", "scored_gps": len(gps)},
        }

    selected = [aid for aid in (selected_asset_ids or []) if aid in names_by_asset]
    asset_ids = selected if selected else sorted(names_by_asset.keys(), key=lambda aid: names_by_asset[aid].lower())

    all_cumulative_by_gp: dict[int, dict[int, float]] = {}
    running_all = {aid: 0.0 for aid in names_by_asset}
    for gp in gps:
        for aid in names_by_asset:
            running_all[aid] += scores_by_asset.get(aid, {}).get(gp.id, 0.0)
        all_cumulative_by_gp[gp.id] = dict(running_all)

    series = []
    for aid in asset_ids:
        running = 0.0
        running_ppm = 0.0
        prev_price: float | None = None
        points_window: list[float] = []
        ppm_window: list[float | None] = []
        data = []
        for gp in gps:
            points = scores_by_asset.get(aid, {}).get(gp.id, 0.0)
            price = prices_by_asset.get(aid, {}).get(gp.id)
            running += points
            ppm_gp = (points / price) if price not in (None, 0) else None
            if ppm_gp is not None:
                running_ppm += ppm_gp

            points_window.append(points)
            if len(points_window) > 3:
                points_window.pop(0)

            ppm_window.append(ppm_gp)
            if len(ppm_window) > 3:
                ppm_window.pop(0)

            if normalized_metric == "points_per_gp":
                data.append(round(points, 2))
            elif normalized_metric == "gap_to_leader":
                leader = max(all_cumulative_by_gp[gp.id].values()) if all_cumulative_by_gp[gp.id] else 0.0
                data.append(round(leader - running, 2))
            elif normalized_metric == "rank_per_gp":
                data.append(float(_competition_rank(running, all_cumulative_by_gp[gp.id].values())))
            elif normalized_metric == "price":
                data.append(round(price, 2) if price is not None else None)
            elif normalized_metric == "price_change_gp":
                if price is None or prev_price is None:
                    data.append(None)
                else:
                    data.append(round(price - prev_price, 2))
            elif normalized_metric == "points_per_million_gp":
                data.append(round(ppm_gp, 4) if ppm_gp is not None else None)
            elif normalized_metric == "cumulative_points_per_million":
                data.append(round(running_ppm, 4))
            elif normalized_metric == "rolling_avg_points_3gp":
                data.append(round(sum(points_window) / len(points_window), 2) if points_window else None)
            elif normalized_metric == "rolling_avg_points_per_million_3gp":
                valid_ppm = [value for value in ppm_window if value is not None]
                data.append(round(sum(valid_ppm) / len(valid_ppm), 4) if valid_ppm else None)
            elif normalized_metric == "pick_rate_gp":
                gp_entries = gp_entries_count.get(gp.id, 0)
                denominator = gp_entries
                if denominator:
                    picks = pick_counts_by_gp_asset.get(gp.id, {}).get(aid, 0)
                    data.append(round((picks / denominator) * 100.0, 2))
                else:
                    data.append(None)
            else:
                data.append(round(running, 2))

            if price is not None:
                prev_price = price

        series.append(
            {
                "asset_id": aid,
                group_name: names_by_asset[aid],
                "team_name": team_names_by_asset.get(aid),
                "team_color": team_colors_by_asset.get(aid),
                "data": data,
            }
        )

    return {
        "season": season.year,
        "asset_type": normalized_type,
        "metric": normalized_metric,
        "labels": labels,
        "gp_options": gp_options,
        "series": series,
        "empty_state": False,
        "meta": {"reason": None, "scored_gps": len(gps), "total_series": len(series)},
    }


def _resolve_season(season_year: int | None) -> Season | None:
    if season_year is not None:
        return Season.objects.filter(year=season_year).first()

    return (
        Season.objects.filter(porra__points__isnull=False)
        .distinct()
        .order_by("-year")
        .first()
    )


def _get_scored_gps(*, season: Season, gp_from: int | None, gp_to: int | None) -> list[GrandPrix]:
    queryset = (
        GrandPrix.objects.filter(season=season, porra__points__isnull=False)
        .distinct()
        .order_by("nround")
    )

    if gp_from is not None:
        queryset = queryset.filter(nround__gte=gp_from)
    if gp_to is not None:
        queryset = queryset.filter(nround__lte=gp_to)

    return list(queryset)


def _compute_gp_position_counts(
    gp_scores: dict[int, list[tuple[int, float]]]
) -> tuple[dict[int, int], dict[int, int], dict[int, int]]:
    wins: dict[int, int] = defaultdict(int)
    podiums: dict[int, int] = defaultdict(int)
    bottom3: dict[int, int] = defaultdict(int)

    for scores in gp_scores.values():
        if not scores:
            continue

        values = [points for _, points in scores]

        max_points = max(values)
        for user_id, points in scores:
            if points == max_points:
                wins[user_id] += 1

        podium_threshold = _boundary_threshold(values, top=True)
        bottom_threshold = _boundary_threshold(values, top=False)

        for user_id, points in scores:
            if points >= podium_threshold:
                podiums[user_id] += 1
            if points <= bottom_threshold:
                bottom3[user_id] += 1

    return dict(wins), dict(podiums), dict(bottom3)


def _boundary_threshold(values: list[float], *, top: bool) -> float:
    unique_sorted = sorted(set(values), reverse=top)
    idx = min(2, len(unique_sorted) - 1)
    return unique_sorted[idx]


def _build_team_maps(*, season: Season) -> tuple[dict[int, str | None], dict[int, int | None]]:
    profiles = list(
        UserProfile.objects.filter(season=season)
        .select_related("users_team", "user")
        .order_by("users_team_id", "user_id")
    )

    team_by_user_id: dict[int, str | None] = {}
    members_by_team: dict[int, list[int]] = defaultdict(list)

    for profile in profiles:
        team_name = profile.users_team.name if profile.users_team else None
        team_by_user_id[profile.user_id] = team_name
        if profile.users_team_id is not None:
            members_by_team[profile.users_team_id].append(profile.user_id)

    teammate_by_user_id: dict[int, int | None] = {}

    for member_ids in members_by_team.values():
        if len(member_ids) != 2:
            for uid in member_ids:
                teammate_by_user_id[uid] = None
            continue

        a, b = member_ids
        teammate_by_user_id[a] = b
        teammate_by_user_id[b] = a

    for user_id in team_by_user_id:
        teammate_by_user_id.setdefault(user_id, None)

    return team_by_user_id, teammate_by_user_id


def _build_users_team_maps(
    *,
    season: Season,
) -> tuple[dict[int, int], dict[int, str], dict[int, list[str]]]:
    profiles = list(
        UserProfile.objects.filter(season=season, users_team__isnull=False)
        .select_related("users_team", "user")
        .order_by("users_team_id", "user_id")
    )

    team_by_user_id: dict[int, int] = {}
    team_names_by_id: dict[int, str] = {}
    members_by_team_id: dict[int, list[str]] = defaultdict(list)

    for profile in profiles:
        if profile.users_team_id is None:
            continue
        team_by_user_id[profile.user_id] = profile.users_team_id
        if profile.users_team:
            team_names_by_id[profile.users_team_id] = profile.users_team.name
        members_by_team_id[profile.users_team_id].append(profile.user.username)

    return team_by_user_id, team_names_by_id, members_by_team_id


def _compute_teammate_h2h(
    *,
    user_id: int,
    teammate_id: int | None,
    scores_by_user: dict[int, dict[int, float]],
) -> tuple[int, int, int]:
    if teammate_id is None:
        return 0, 0, 0

    user_scores = scores_by_user.get(user_id, {})
    teammate_scores = scores_by_user.get(teammate_id, {})

    compared_gps = set(user_scores.keys()) & set(teammate_scores.keys())

    wins = losses = ties = 0
    for gp_id in compared_gps:
        a = user_scores[gp_id]
        b = teammate_scores[gp_id]
        if a > b:
            wins += 1
        elif a < b:
            losses += 1
        else:
            ties += 1

    return wins, losses, ties


def _normalize_sort_by(sort_by: str) -> str:
    if sort_by in ALLOWED_SORT_FIELDS:
        return sort_by
    return "total_points"


def _normalize_sort_dir(sort_dir: str) -> str:
    if sort_dir == "asc":
        return "asc"
    return "desc"


def _sort_rows(rows: list[dict[str, Any]], *, sort_by: str, sort_dir: str) -> list[dict[str, Any]]:
    reverse = sort_dir == "desc"

    def sort_key(row: dict[str, Any]) -> tuple[Any, str]:
        value = row.get(sort_by)
        fallback = row.get("username") or row.get("team_name") or row.get("name", "")

        # Keep None values stable at the end for both directions.
        none_rank = 1 if value is None else 0
        return none_rank, value, fallback

    return sorted(rows, key=sort_key, reverse=reverse)


def _normalize_trend_metric(metric: str) -> str:
    if metric in ALLOWED_TREND_METRICS:
        return metric
    return "cumulative_points"


def _normalize_preset(preset: str | None) -> str:
    if preset in ALLOWED_PRESETS:
        return preset
    return "all"


def _normalize_team_preset(preset: str | None) -> str:
    if preset in ALLOWED_TEAM_PRESETS:
        return preset
    return "all"


def _normalize_asset_type(asset_type: str | None) -> str:
    if asset_type in ALLOWED_ASSET_TYPES:
        return asset_type
    return "drivers"


def _normalize_asset_metric(metric: str | None) -> str:
    if metric in ALLOWED_ASSET_METRICS:
        return metric
    return "cumulative_points"


def _build_driver_rows(*, season: Season, gp_ids: list[int]) -> list[dict[str, Any]]:
    gps_in_range = GrandPrix.objects.filter(id__in=gp_ids).order_by("nround")
    gp_sequence = list(gps_in_range.values_list("id", flat=True))
    latest_gp_id = gp_sequence[-1] if gp_sequence else None
    prev_gp_id = gp_sequence[-2] if len(gp_sequence) > 1 else None

    pick_counts, latest_pick_counts, total_entries, latest_entries, _slots_per_entry = _build_pick_rate_maps(
        season=season,
        gp_ids=gp_ids,
        asset_type="drivers",
    )

    rows = []
    for driver_id, driver_name, team_name in (
        DriverPoints.objects.filter(season=season, gp_id__in=gp_ids, driver__isnull=False)
        .values_list("driver_id", "driver__name", "driver__team__name")
        .distinct()
    ):
        points_rows = DriverPoints.objects.filter(
            season=season, gp_id__in=gp_ids, driver_id=driver_id, points__isnull=False
        )
        points = [float(v) for v in points_rows.values_list("points", flat=True)]
        if not points:
            continue
        total_points = sum(points)
        gps_played = len(points)
        avg_points = total_points / gps_played if gps_played else 0.0
        volatility = pstdev(points) if gps_played > 1 else 0.0
        form_3gp = (sum(points[-3:]) / min(3, gps_played)) if gps_played else 0.0

        current_price = (
            DriverPoints.objects.filter(season=season, gp_id=latest_gp_id, driver_id=driver_id)
            .values_list("price", flat=True)
            .first()
            if latest_gp_id
            else None
        ) or 0
        prev_price = (
            DriverPoints.objects.filter(season=season, gp_id=prev_gp_id, driver_id=driver_id)
            .values_list("price", flat=True)
            .first()
            if prev_gp_id
            else None
        ) or 0
        price_change = current_price - prev_price
        ppm = (total_points / current_price) if current_price else 0.0
        total_denominator = total_entries
        latest_denominator = latest_entries
        pick_rate = (
            (pick_counts.get(driver_id, 0) / total_denominator) * 100.0
            if total_denominator
            else 0.0
        )
        pick_rate_last_gp = (
            (latest_pick_counts.get(driver_id, 0) / latest_denominator) * 100.0
            if latest_denominator
            else 0.0
        )

        rows.append(
            {
                "asset_id": driver_id,
                "name": driver_name,
                "asset_group": team_name or "No Team",
                "total_points": round(total_points, 2),
                "avg_points_gp": round(avg_points, 2),
                "volatility": round(volatility, 4),
                "form_3gp": round(form_3gp, 2),
                "gps_played": gps_played,
                "current_price": round(float(current_price), 2),
                "price_change": round(float(price_change), 2),
                "points_per_million": round(ppm, 3),
                "pick_rate": round(pick_rate, 2),
                "pick_rate_last_gp": round(pick_rate_last_gp, 2),
            }
        )
    return rows


def _build_constructor_rows(*, season: Season, gp_ids: list[int]) -> list[dict[str, Any]]:
    gps_in_range = GrandPrix.objects.filter(id__in=gp_ids).order_by("nround")
    gp_sequence = list(gps_in_range.values_list("id", flat=True))
    latest_gp_id = gp_sequence[-1] if gp_sequence else None
    prev_gp_id = gp_sequence[-2] if len(gp_sequence) > 1 else None

    pick_counts, latest_pick_counts, total_entries, latest_entries, _slots_per_entry = _build_pick_rate_maps(
        season=season,
        gp_ids=gp_ids,
        asset_type="constructors",
    )

    rows = []
    for team_id, team_name in (
        TeamPoints.objects.filter(season=season, gp_id__in=gp_ids, team__isnull=False)
        .values_list("team_id", "team__name")
        .distinct()
    ):
        points_rows = TeamPoints.objects.filter(
            season=season, gp_id__in=gp_ids, team_id=team_id, points__isnull=False
        )
        points = [float(v) for v in points_rows.values_list("points", flat=True)]
        if not points:
            continue
        total_points = sum(points)
        gps_played = len(points)
        avg_points = total_points / gps_played if gps_played else 0.0
        volatility = pstdev(points) if gps_played > 1 else 0.0
        form_3gp = (sum(points[-3:]) / min(3, gps_played)) if gps_played else 0.0

        current_price = (
            TeamPoints.objects.filter(season=season, gp_id=latest_gp_id, team_id=team_id)
            .values_list("price", flat=True)
            .first()
            if latest_gp_id
            else None
        ) or 0
        prev_price = (
            TeamPoints.objects.filter(season=season, gp_id=prev_gp_id, team_id=team_id)
            .values_list("price", flat=True)
            .first()
            if prev_gp_id
            else None
        ) or 0
        price_change = current_price - prev_price
        ppm = (total_points / current_price) if current_price else 0.0
        total_denominator = total_entries
        latest_denominator = latest_entries
        pick_rate = (
            (pick_counts.get(team_id, 0) / total_denominator) * 100.0
            if total_denominator
            else 0.0
        )
        pick_rate_last_gp = (
            (latest_pick_counts.get(team_id, 0) / latest_denominator) * 100.0
            if latest_denominator
            else 0.0
        )

        rows.append(
            {
                "asset_id": team_id,
                "name": team_name,
                "asset_group": None,
                "total_points": round(total_points, 2),
                "avg_points_gp": round(avg_points, 2),
                "volatility": round(volatility, 4),
                "form_3gp": round(form_3gp, 2),
                "gps_played": gps_played,
                "current_price": round(float(current_price), 2),
                "price_change": round(float(price_change), 2),
                "points_per_million": round(ppm, 3),
                "pick_rate": round(pick_rate, 2),
                "pick_rate_last_gp": round(pick_rate_last_gp, 2),
            }
        )
    return rows


def _sort_asset_rows(rows: list[dict[str, Any]], *, sort_by: str, sort_dir: str) -> list[dict[str, Any]]:
    reverse = sort_dir == "desc"
    key = sort_by if sort_by in {
        "name", "asset_group", "total_points", "avg_points_gp", "volatility", "form_3gp", "gps_played",
        "current_price", "price_change", "points_per_million", "pick_rate", "pick_rate_last_gp"
    } else "total_points"
    return sorted(rows, key=lambda row: (row.get(key), row.get("name", "")), reverse=reverse)


def _build_pick_rate_maps(
    *,
    season: Season,
    gp_ids: list[int],
    asset_type: str,
) -> tuple[dict[int, int], dict[int, int], int, int, int]:
    if not gp_ids:
        return {}, {}, 0, 0, 0

    latest_gp_id = gp_ids[-1]
    count_map: dict[int, int] = defaultdict(int)
    latest_count_map: dict[int, int] = defaultdict(int)

    if asset_type == "drivers":
        slots_per_entry = 5
        porra_rows = Porra.objects.filter(season=season, gp_id__in=gp_ids).values_list(
            "gp_id", "driver1_id", "driver2_id", "driver3_id", "driver4_id", "driver5_id"
        )
    else:
        slots_per_entry = 2
        porra_rows = Porra.objects.filter(season=season, gp_id__in=gp_ids).values_list(
            "gp_id", "team1_id", "team2_id"
        )

    total_entries = 0
    latest_entries = 0
    for row in porra_rows:
        gp_id = row[0]
        asset_ids = row[1:]
        total_entries += 1
        if gp_id == latest_gp_id:
            latest_entries += 1

        for asset_id in asset_ids:
            if asset_id is None:
                continue
            count_map[asset_id] += 1
            if gp_id == latest_gp_id:
                latest_count_map[asset_id] += 1

    return dict(count_map), dict(latest_count_map), total_entries, latest_entries, slots_per_entry


def _resolve_trend_users(
    *,
    users_by_id: dict[int, User],
    scores_by_user: dict[int, dict[int, float]],
    teammate_by_user_id: dict[int, int | None],
    selected_user_ids: list[int] | None,
    preset: str,
    current_user_id: int | None,
) -> list[int]:
    all_user_ids = list(users_by_id.keys())
    selected = [uid for uid in (selected_user_ids or []) if uid in users_by_id]

    totals = {
        uid: sum(scores_by_user.get(uid, {}).values())
        for uid in all_user_ids
    }

    if preset == "me_teammate":
        if current_user_id in users_by_id:
            users = [current_user_id]
            teammate = teammate_by_user_id.get(current_user_id)
            if teammate in users_by_id:
                users.append(teammate)
            return sorted(set(users), key=lambda uid: users_by_id[uid].username.lower())

    if preset == "me_vs_user":
        if current_user_id in users_by_id:
            opponent = next((uid for uid in selected if uid != current_user_id), None)
            if opponent is not None:
                return [current_user_id, opponent]
            return [current_user_id]
        if selected:
            return sorted(set(selected), key=lambda uid: users_by_id[uid].username.lower())

    if preset == "top3":
        return _top_n_user_ids(users_by_id=users_by_id, totals=totals, n=3, reverse=True)

    if preset == "bottom3":
        return _top_n_user_ids(users_by_id=users_by_id, totals=totals, n=3, reverse=False)

    if selected:
        return sorted(set(selected), key=lambda uid: users_by_id[uid].username.lower())

    return sorted(all_user_ids, key=lambda uid: users_by_id[uid].username.lower())


def _resolve_trend_teams(
    *,
    team_names_by_id: dict[int, str],
    scores_by_team: dict[int, dict[int, float]],
    selected_team_ids: list[int] | None,
    preset: str,
    current_user_id: int | None,
    team_by_user_id: dict[int, int],
) -> list[int]:
    all_team_ids = list(team_names_by_id.keys())
    selected = [tid for tid in (selected_team_ids or []) if tid in team_names_by_id]

    totals = {
        tid: sum(scores_by_team.get(tid, {}).values())
        for tid in all_team_ids
    }

    if preset == "my_team":
        if current_user_id is not None:
            team_id = team_by_user_id.get(current_user_id)
            if team_id in team_names_by_id:
                return [team_id]

    if preset == "top3":
        return _top_n_entity_ids(names_by_id=team_names_by_id, totals=totals, n=3, reverse=True)

    if preset == "bottom3":
        return _top_n_entity_ids(names_by_id=team_names_by_id, totals=totals, n=3, reverse=False)

    if selected:
        return sorted(set(selected), key=lambda tid: team_names_by_id[tid].lower())

    return sorted(all_team_ids, key=lambda tid: team_names_by_id[tid].lower())


def _top_n_user_ids(
    *,
    users_by_id: dict[int, User],
    totals: dict[int, float],
    n: int,
    reverse: bool,
) -> list[int]:
    ranked = sorted(
        totals.items(),
        key=lambda item: (item[1], users_by_id[item[0]].username.lower()),
        reverse=reverse,
    )
    return [uid for uid, _ in ranked[:n]]


def _top_n_entity_ids(
    *,
    names_by_id: dict[int, str],
    totals: dict[int, float],
    n: int,
    reverse: bool,
) -> list[int]:
    ranked = sorted(
        totals.items(),
        key=lambda item: (item[1], names_by_id.get(item[0], "").lower()),
        reverse=reverse,
    )
    return [entity_id for entity_id, _ in ranked[:n]]


def _build_series_data_for_user(
    *,
    metric: str,
    user_id: int,
    gps: list[GrandPrix],
    scores_by_user: dict[int, dict[int, float]],
    all_cumulative_by_gp: dict[int, dict[int, float]],
) -> list[float]:
    running = 0.0
    values: list[float] = []

    for gp in gps:
        gp_points = scores_by_user.get(user_id, {}).get(gp.id, 0.0)
        running += gp_points

        if metric == "points_per_gp":
            values.append(round(gp_points, 2))
            continue

        if metric == "cumulative_points":
            values.append(round(running, 2))
            continue

        cumulative_for_gp = all_cumulative_by_gp[gp.id]

        if metric == "gap_to_leader":
            leader = max(cumulative_for_gp.values()) if cumulative_for_gp else 0.0
            values.append(round(leader - running, 2))
            continue

        # rank_per_gp
        values.append(float(_competition_rank(running, cumulative_for_gp.values())))

    return values


def _competition_rank(value: float, values: Any) -> int:
    unique_desc = sorted(set(values), reverse=True)
    for idx, ref in enumerate(unique_desc, start=1):
        if value == ref:
            return idx
    return len(unique_desc) + 1


def build_optimal_team_payload(
    *,
    season_year: int | None = None,
    gp_round: int | None = None,
    budget: int = 150,
) -> dict[str, Any]:
    season = _resolve_season(season_year)
    season_options = list(
        Season.objects.filter(porra__points__isnull=False)
        .distinct()
        .order_by("-year")
        .values_list("year", flat=True)
    )

    if season is None:
        return {
            "empty_state": True,
            "meta": {"reason": "season_not_found_or_no_scored_data"},
            "season_options": season_options,
            "gp_options": [],
            "selected": {"season": season_year, "gp_round": gp_round, "budget": budget},
            "optimal_team": None,
        }

    scored_gps = _get_scored_gps(season=season, gp_from=None, gp_to=None)
    gp_options = [{"round": gp.nround, "name": gp.country} for gp in scored_gps]
    if not scored_gps:
        return {
            "empty_state": True,
            "meta": {"reason": "no_scored_gps_in_season"},
            "season_options": season_options,
            "gp_options": gp_options,
            "selected": {"season": season.year, "gp_round": gp_round, "budget": budget},
            "optimal_team": None,
        }

    gp_by_round = {gp.nround: gp for gp in scored_gps}
    selected_gp = gp_by_round.get(gp_round) if gp_round is not None else scored_gps[-1]
    if selected_gp is None:
        selected_gp = scored_gps[-1]

    driver_rows = list(
        DriverPoints.objects.filter(
            season=season,
            gp=selected_gp,
            driver__isnull=False,
            points__isnull=False,
            price__isnull=False,
        ).select_related("driver", "driver__team")
    )
    constructor_rows = list(
        TeamPoints.objects.filter(
            season=season,
            gp=selected_gp,
            team__isnull=False,
            points__isnull=False,
            price__isnull=False,
        ).select_related("team")
    )

    if len(driver_rows) < 5 or len(constructor_rows) < 2:
        return {
            "empty_state": True,
            "meta": {"reason": "insufficient_assets_for_optimization"},
            "season_options": season_options,
            "gp_options": gp_options,
            "selected": {"season": season.year, "gp_round": selected_gp.nround, "budget": budget},
            "optimal_team": None,
        }

    best = _solve_optimal_lineup_single(
        driver_rows=driver_rows,
        constructor_rows=constructor_rows,
        budget=budget,
    )
    if best is None:
        return {
            "empty_state": True,
            "meta": {"reason": "no_valid_lineup_under_budget"},
            "season_options": season_options,
            "gp_options": gp_options,
            "selected": {"season": season.year, "gp_round": selected_gp.nround, "budget": budget},
            "optimal_team": None,
        }

    race_results = RaceResults.objects.filter(season=season, gp=selected_gp).select_related(
        "poleman", "first_pos", "second_pos", "third_pos", "fast_lap", "team_winner"
    ).first()
    bonus_breakdown = {
        "poleman": BONUS_POINTS["poleman"] if race_results and race_results.poleman else 0,
        "first_pos": BONUS_POINTS["first_pos"] if race_results and race_results.first_pos else 0,
        "second_pos": BONUS_POINTS["second_pos"] if race_results and race_results.second_pos else 0,
        "third_pos": BONUS_POINTS["third_pos"] if race_results and race_results.third_pos else 0,
        "fast_lap": BONUS_POINTS["fast_lap"] if race_results and race_results.fast_lap else 0,
        "team_winner": BONUS_POINTS["team_winner"] if race_results and race_results.team_winner else 0,
    }
    bonus_total = sum(bonus_breakdown.values())

    return {
        "empty_state": False,
        "meta": {"reason": None},
        "season_options": season_options,
        "gp_options": gp_options,
        "selected": {"season": season.year, "gp_round": selected_gp.nround, "budget": budget},
        "gp": {
            "round": selected_gp.nround,
            "country": selected_gp.country,
            "name": selected_gp.name,
            "photo_link": selected_gp.photo_link,
            "country_link": selected_gp.country_link,
            "gp_photo": selected_gp.gp_photo,
        },
        "optimal_team": {
            "drivers": [
                _serialize_driver_pick(row, season_year=season.year, is_captain=(index == 0))
                for index, row in enumerate(best["drivers"])
            ],
            "constructors": [_serialize_constructor_pick(row, season_year=season.year) for row in best["constructors"]],
            "drivers_points_base": round(best["drivers_points_base"], 2),
            "captain_points_bonus": round(best["captain_points"], 2),
            "assets_points": round(best["points"], 2),
            "bonus_points": bonus_breakdown,
            "bonus_total": bonus_total,
            "total_points": round(best["points"] + bonus_total, 2),
            "total_cost": round(best["cost"], 2),
            "race_results": _serialize_race_results(race_results),
            "bonus_selections": _serialize_bonus_selections(race_results, season_year=season.year),
        },
    }


def _solve_optimal_lineup_single(
    *,
    driver_rows: list[DriverPoints],
    constructor_rows: list[TeamPoints],
    budget: int,
) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None

    for driver_combo in combinations(driver_rows, 5):
        drivers_cost = sum(float(row.price or 0) for row in driver_combo)
        if drivers_cost > budget:
            continue
        sorted_drivers = sorted(
            driver_combo,
            key=lambda row: (
                float(row.points or 0),
                float(row.price or 0),
                row.driver.name.lower(),
            ),
            reverse=True,
        )
        captain = sorted_drivers[0]
        drivers_points_base = sum(float(row.points or 0) for row in sorted_drivers)
        captain_points = float(captain.points or 0)
        drivers_points = drivers_points_base + captain_points  # x2 for first selected driver

        for constructor_combo in combinations(constructor_rows, 2):
            constructors_cost = sum(float(row.price or 0) for row in constructor_combo)
            total_cost = drivers_cost + constructors_cost
            if total_cost > budget:
                continue

            constructors_points = sum(float(row.points or 0) for row in constructor_combo)
            total_points = drivers_points + constructors_points
            tie_break_key = (
                total_points,
                -total_cost,
                sorted(row.driver.name for row in sorted_drivers),
                sorted(row.team.name for row in constructor_combo),
            )

            if best is None or tie_break_key > best["key"]:
                best = {
                    "key": tie_break_key,
                    "drivers": list(sorted_drivers),
                    "constructors": list(constructor_combo),
                    "points": total_points,
                    "drivers_points_base": drivers_points_base,
                    "captain_points": captain_points,
                    "cost": total_cost,
                }

    return best


def _serialize_driver_pick(
    row: DriverPoints,
    *,
    season_year: int | None = None,
    is_captain: bool = False,
) -> dict[str, Any]:
    points = float(row.points or 0)
    image_link = _resolve_driver_image_link(
        season_year=season_year,
        driver_name=row.driver.name,
        selected_link=row.driver.selected_link,
    )
    return {
        "name": row.driver.name,
        "team_name": row.driver.team.name if row.driver.team else None,
        "team_color": row.driver.team.color_rgb if row.driver.team else None,
        "photo_link": image_link,
        "price": float(row.price or 0),
        "points": points,
        "effective_points": points * (2 if is_captain else 1),
        "is_captain": is_captain,
    }


def _serialize_constructor_pick(row: TeamPoints, *, season_year: int | None = None) -> dict[str, Any]:
    image_link = _resolve_team_image_link(
        season_year=season_year,
        team_name=row.team.name,
        selected_link=row.team.selected_link,
        photo_link=row.team.photo_link,
        prefer="cars",
    )
    return {
        "name": row.team.name,
        "color": row.team.color_rgb,
        "photo_link": image_link,
        "price": float(row.price or 0),
        "points": float(row.points or 0),
    }


def _serialize_race_results(result: RaceResults | None) -> dict[str, Any] | None:
    if result is None:
        return None
    return {
        "poleman": result.poleman.name if result.poleman else None,
        "first_pos": result.first_pos.name if result.first_pos else None,
        "second_pos": result.second_pos.name if result.second_pos else None,
        "third_pos": result.third_pos.name if result.third_pos else None,
        "fast_lap": result.fast_lap.name if result.fast_lap else None,
        "team_winner": result.team_winner.name if result.team_winner else None,
    }


def _serialize_bonus_selections(result: RaceResults | None, *, season_year: int | None = None) -> dict[str, Any]:
    if result is None:
        return {}
    return {
        "poleman": _serialize_driver_bonus_pick(result.poleman, season_year=season_year),
        "first_pos": _serialize_driver_bonus_pick(result.first_pos, season_year=season_year),
        "second_pos": _serialize_driver_bonus_pick(result.second_pos, season_year=season_year),
        "third_pos": _serialize_driver_bonus_pick(result.third_pos, season_year=season_year),
        "fast_lap": _serialize_driver_bonus_pick(result.fast_lap, season_year=season_year),
        "team_winner": _serialize_team_bonus_pick(result.team_winner, season_year=season_year),
    }


def _serialize_driver_bonus_pick(driver, *, season_year: int | None = None) -> dict[str, Any] | None:
    if driver is None:
        return None
    return {
        "name": driver.name,
        "photo_link": _resolve_driver_image_link(
            season_year=season_year,
            driver_name=driver.name,
            selected_link=driver.selected_link,
        ),
        "team_color": driver.team.color_rgb if driver.team else None,
    }


def _serialize_team_bonus_pick(team, *, season_year: int | None = None) -> dict[str, Any] | None:
    if team is None:
        return None
    image_link = _resolve_team_image_link(
        season_year=season_year,
        team_name=team.name,
        selected_link=team.selected_link,
        photo_link=team.photo_link,
        prefer="logos",
    )
    return {
        "name": team.name,
        "photo_link": image_link,
        "color": team.color_rgb,
    }


def _resolve_driver_image_link(
    *,
    season_year: int | None,
    driver_name: str,
    selected_link: str | None,
) -> str | None:
    candidates: list[str] = []
    if selected_link:
        candidates.append(selected_link)

    if season_year:
        season_folder = f"season{season_year}"
        filename = _slug_last_token(driver_name)
        candidates.extend(
            [
                f"{season_folder}/selected/{filename}.png",
                f"{season_folder}/drivers/{filename}.png",
                f"{season_folder}/driver/{filename}.png",
            ]
        )

    return _first_existing_relative("drivers", candidates)


def _resolve_team_image_link(
    *,
    season_year: int | None,
    team_name: str,
    selected_link: str | None,
    photo_link: str | None,
    prefer: str = "cars",
) -> str | None:
    candidates: list[str] = []
    if prefer == "cars":
        if selected_link:
            candidates.append(selected_link)
        if photo_link:
            candidates.append(photo_link)
    else:
        if photo_link:
            candidates.append(photo_link)
        if selected_link:
            candidates.append(selected_link)

    if season_year:
        season_folder = f"season{season_year}"
        filename = _team_filename(team_name)
        if prefer == "cars":
            candidates.extend(
                [
                    f"{season_folder}/cars/{filename}.png",
                    f"{season_folder}/teams/{filename}.png",
                    f"{season_folder}/logos/{filename}.png",
                ]
            )
        else:
            candidates.extend(
                [
                    f"{season_folder}/logos/{filename}.png",
                    f"{season_folder}/cars/{filename}.png",
                    f"{season_folder}/teams/{filename}.png",
                ]
            )

    return _first_existing_relative("teams", candidates)


def _first_existing_relative(asset_folder: str, candidates: list[str]) -> str | None:
    root = Path(settings.BASE_DIR) / "static" / "theme" / "assets" / asset_folder
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate:
            continue
        normalized = candidate.replace("\\", "/").strip().lstrip("/")
        if normalized in seen:
            continue
        seen.add(normalized)
        if (root / Path(*normalized.split("/"))).exists():
            return normalized
    return None


def _slug_last_token(name: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", name.lower())
    return tokens[-1] if tokens else "unknown"


def _team_filename(name: str) -> str:
    normalized = "".join(re.findall(r"[a-z0-9]+", name.lower()))
    aliases = {
        "redbullracing": "redbull",
        "visarb": "visaRB",
        "vcarb": "visaRB",
        "kicksauber": "kicksauber",
        "astonmartin": "astonmartin",
        "alphatauri": "visaRB",
        "racingbulls": "racingbulls",
    }
    return aliases.get(normalized, normalized)
