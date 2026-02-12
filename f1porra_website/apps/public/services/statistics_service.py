from __future__ import annotations

from collections import defaultdict
from statistics import pstdev
from typing import Any

from django.contrib.auth.models import User

from f1porra_website.apps.accounts.models import UserProfile
from f1porra_website.apps.public.models import GrandPrix, Porra, Season


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
            "season": season_year,
            "metric": normalized_metric,
            "preset": normalized_preset,
            "labels": [],
            "series": [],
            "resolved_user_ids": [],
            "empty_state": True,
            "meta": {"reason": "season_not_found_or_no_scored_data", "scored_gps": 0},
        }

    gps = _get_scored_gps(season=season, gp_from=gp_from, gp_to=gp_to)
    if not gps:
        return {
            "season": season.year,
            "metric": normalized_metric,
            "preset": normalized_preset,
            "labels": [],
            "series": [],
            "resolved_user_ids": [],
            "empty_state": True,
            "meta": {"reason": "no_scored_gps_in_range", "scored_gps": 0},
        }

    gp_ids = [gp.id for gp in gps]
    labels = [f"R{gp.nround} {gp.country}" for gp in gps]
    porras = list(
        Porra.objects.filter(season=season, gp_id__in=gp_ids, points__isnull=False)
        .select_related("user")
        .order_by("gp__nround", "user__username")
    )
    if not porras:
        return {
            "season": season.year,
            "metric": normalized_metric,
            "preset": normalized_preset,
            "labels": labels,
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
        "season": season.year,
        "metric": normalized_metric,
        "preset": normalized_preset,
        "labels": labels,
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
        fallback = row.get("username", "")

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

    if selected_user_ids:
        selected = [uid for uid in selected_user_ids if uid in users_by_id]
        if selected:
            return sorted(selected, key=lambda uid: users_by_id[uid].username.lower())

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
            return [current_user_id]

    if preset == "top3":
        return _top_n_user_ids(users_by_id=users_by_id, totals=totals, n=3, reverse=True)

    if preset == "bottom3":
        return _top_n_user_ids(users_by_id=users_by_id, totals=totals, n=3, reverse=False)

    return sorted(all_user_ids, key=lambda uid: users_by_id[uid].username.lower())


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
