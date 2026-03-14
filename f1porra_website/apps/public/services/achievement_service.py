from __future__ import annotations

from collections import defaultdict
from typing import Any

from django.contrib.auth.models import User
from django.utils import timezone

from f1porra_website.apps.accounts.models import UserProfile
from f1porra_website.apps.public.models import (
    Achievement,
    BlockChip,
    DriverPoints,
    GrandPrix,
    Porra,
    RaceResults,
    Season,
    TeamPoints,
    UserAchievement,
)


ACHIEVEMENTS: list[dict[str, Any]] = [
    {"slug": "big_guy", "name": "Big Guy", "category": "season", "icon": "3000", "icon_class": "icon-number",
     "description": "Consigue 3000 puntos en una misma temporada."},
    {"slug": "hall_of_fame", "name": "Hall of Fame", "category": "all_time", "icon": "♛", "icon_class": "icon-symbol",
     "description": "Alcanza 10000 puntos acumulados en toda tu historia en la porra."},
    {"slug": "grand_chelem", "name": "Grand Chelem", "category": "season", "icon": "3x", "icon_class": "icon-number",
     "description": "Gana 3 GPs seguidos en la misma temporada."},
    {"slug": "untouchable", "name": "Untouchable", "category": "season", "icon": "🛡", "icon_class": "icon-symbol",
     "description": "Encadena 5 GPs consecutivos terminando en top 3."},
    {"slug": "world_champion", "name": "World Champion", "category": "season", "icon": "🏆", "icon_class": "icon-symbol",
     "description": "Termina la temporada como lider absoluto de la clasificacion general."},
    {"slug": "constructor_legend", "name": "Constructor Legend", "category": "season", "icon": "👥", "icon_class": "icon-symbol",
     "description": "Tu equipo de usuarios acaba primero en la clasificacion por equipos de la temporada."},
    {"slug": "comeback_kid", "name": "Comeback Kid", "category": "season", "icon": "↗", "icon_class": "icon-symbol",
     "description": "Gana un GP estando fuera del top 5 general antes de esa carrera."},
    {"slug": "sniper", "name": "Sniper", "category": "gp", "icon": "🔫", "icon_class": "icon-symbol",
     "description": "Clava todos los bonus en un GP: Poleman, P1, P2, P3, Fast Lap y Best Team."},
    {"slug": "capitan_general", "name": "Capitan General", "category": "gp", "icon": "🎖", "icon_class": "icon-symbol",
     "description": "Tu piloto principal suma al menos 40 puntos en un GP (sin contar el x2)."},
    {"slug": "chip_combo", "name": "Chip Combo", "category": "season", "icon": "⚡", "icon_class": "icon-symbol",
     "description": "Usa DRS Boost y Pit Stop en el mismo GP."},
    {"slug": "cold_blood", "name": "Cold Blood", "category": "gp", "icon": "❄", "icon_class": "icon-symbol",
     "description": "Gana un GP en el que otro usuario te haya aplicado un bloqueo."},
    {"slug": "rainbow", "name": "Rainbow", "category": "gp", "icon": "🌈", "icon_class": "icon-symbol",
     "description": "5 pilotos de 5 constructores distintos + 2 constructores fuera de esos 5."},
    {"slug": "public_enemy", "name": "Public Enemy Number One", "category": "season", "icon": "🎯", "icon_class": "icon-symbol",
     "description": "Recibe 3 bloqueos en una misma temporada."},
    {"slug": "block_master", "name": "Block Master", "category": "gp", "icon": "🔒", "icon_class": "icon-symbol",
     "description": "Bloquea a un rival y ese rival termina en los dos ultimos puestos del GP."},
    {"slug": "timely_drs", "name": "Timely DRS", "category": "gp", "icon": "⏱", "icon_class": "icon-symbol",
     "description": "Activa DRS Boost y gana ese GP."},
    {"slug": "latifisexual", "name": "Latifisexual", "category": "season", "icon": "🐐", "icon_class": "icon-symbol",
     "description": "Encadena 3 GPs seguidos en los dos ultimos puestos."},
    {"slug": "rock_bottom", "name": "Rock Bottom", "category": "season", "icon": "⚓", "icon_class": "icon-symbol",
     "description": "Termina 5 veces o mas entre los dos ultimos en una temporada."},
    {"slug": "almost_there", "name": "Almost There", "category": "season", "icon": "🥈", "icon_class": "icon-symbol",
     "description": "Consigue al menos 3 segundos puestos en una temporada sin ganar ningun GP."},
    {"slug": "mr_consistency", "name": "Mr. Consistency", "category": "season", "icon": "🔁", "icon_class": "icon-symbol",
     "description": "Encadena 8 GPs consecutivos terminando en top 5."},
    {"slug": "zero_to_hero", "name": "Zero to Hero", "category": "season", "icon": "🦸", "icon_class": "icon-symbol",
     "description": "Pasa de estar en los dos ultimos en un GP a ganar el siguiente."},
    {"slug": "tacanos_extremos", "name": "Tacanos Extremos", "category": "gp", "icon": "135", "icon_class": "icon-number",
     "description": "Gana un GP gastando menos de 135.0 M de presupuesto."},
    {"slug": "photo_finish", "name": "Photo Finish", "category": "gp", "icon": "📸", "icon_class": "icon-symbol",
     "description": "Gana un GP por 1 punto de diferencia sobre el segundo."},
]


def sync_achievements() -> dict[str, Achievement]:
    achievements_by_slug: dict[str, Achievement] = {}
    for index, data in enumerate(ACHIEVEMENTS, start=1):
        defaults = {
            "name": data["name"],
            "description": data["description"],
            "category": data["category"],
            "icon": data.get("icon"),
            "icon_class": data.get("icon_class"),
            "sort_order": data.get("sort_order", index),
        }
        achievement, _ = Achievement.objects.update_or_create(slug=data["slug"], defaults=defaults)
        achievements_by_slug[achievement.slug] = achievement
    return achievements_by_slug


def recompute_achievements(*, rebuild: bool = False) -> None:
    achievements_by_slug = sync_achievements()

    if rebuild:
        UserAchievement.objects.all().delete()

    unlocked = set(UserAchievement.objects.values_list("user_id", "achievement__slug"))

    def unlock(user_id: int, slug: str, *, season: Season | None, gp: GrandPrix | None) -> None:
        if (user_id, slug) in unlocked:
            return
        achievement = achievements_by_slug.get(slug)
        if not achievement:
            return
        UserAchievement.objects.create(
            user_id=user_id,
            achievement=achievement,
            season=season,
            gp=gp,
            unlocked_at=timezone.now(),
        )
        unlocked.add((user_id, slug))

    seasons = list(
        Season.objects.filter(porra__points__isnull=False)
        .distinct()
        .order_by("year")
    )
    if not seasons:
        return

    driver_points_map: dict[tuple[int, int], tuple[float, float]] = {}
    for row in DriverPoints.objects.filter(season__in=seasons).values_list("gp_id", "driver_id", "points", "price"):
        gp_id, driver_id, points, price = row
        driver_points_map[(gp_id, driver_id)] = (float(points or 0.0), float(price or 0.0))

    team_points_map: dict[tuple[int, int], float] = {}
    for row in TeamPoints.objects.filter(season__in=seasons).values_list("gp_id", "team_id", "price"):
        gp_id, team_id, price = row
        team_points_map[(gp_id, team_id)] = float(price or 0.0)

    race_results_map = {
        row.gp_id: row
        for row in RaceResults.objects.filter(season__in=seasons)
    }

    blockchips_by_gp: dict[int, list[BlockChip]] = defaultdict(list)
    for block in BlockChip.objects.filter(season__in=seasons).select_related("gp"):
        blockchips_by_gp[block.gp_id].append(block)

    all_time_points: dict[int, float] = defaultdict(float)
    hall_of_fame_unlocked: set[int] = set()

    for season in seasons:
        gps = list(
            GrandPrix.objects.filter(season=season, porra__points__isnull=False)
            .distinct()
            .order_by("nround")
        )
        if not gps:
            continue
        gp_ids = [gp.id for gp in gps]
        last_gp = gps[-1]

        porras = list(
            Porra.objects.filter(season=season, gp_id__in=gp_ids, points__isnull=False)
            .select_related(
                "user",
                "gp",
                "driver1__team",
                "driver2__team",
                "driver3__team",
                "driver4__team",
                "driver5__team",
                "team1",
                "team2",
            )
        )
        if not porras:
            continue

        porras_by_gp: dict[int, list[Porra]] = defaultdict(list)
        user_ids: set[int] = set()
        for porra in porras:
            porras_by_gp[porra.gp_id].append(porra)
            user_ids.add(porra.user_id)

        team_by_user_id: dict[int, int] = {}
        members_by_team: dict[int, list[int]] = defaultdict(list)
        for profile in UserProfile.objects.filter(season=season, users_team__isnull=False):
            if profile.users_team_id is None:
                continue
            team_by_user_id[profile.user_id] = profile.users_team_id
            members_by_team[profile.users_team_id].append(profile.user_id)

        cum_points: dict[int, float] = {uid: 0.0 for uid in user_ids}
        win_streak: dict[int, int] = defaultdict(int)
        top3_streak: dict[int, int] = defaultdict(int)
        top5_streak: dict[int, int] = defaultdict(int)
        bottom2_streak: dict[int, int] = defaultdict(int)
        bottom2_count: dict[int, int] = defaultdict(int)
        wins_count: dict[int, int] = defaultdict(int)
        second_count: dict[int, int] = defaultdict(int)
        prev_bottom2: set[int] = set()
        blocks_received_count: dict[int, int] = defaultdict(int)

        for gp in gps:
            gp_porras = porras_by_gp.get(gp.id, [])
            if not gp_porras:
                continue

            scores = [(porra.user_id, float(porra.points or 0.0)) for porra in gp_porras]
            values = [score for _, score in scores]
            unique_desc = sorted(set(values), reverse=True)
            unique_asc = sorted(set(values))
            rank_by_value = {value: idx + 1 for idx, value in enumerate(unique_desc)}
            max_points = unique_desc[0]
            second_max = unique_desc[1] if len(unique_desc) > 1 else None
            top3_thresh = unique_desc[min(2, len(unique_desc) - 1)]
            top5_thresh = unique_desc[min(4, len(unique_desc) - 1)]
            bottom2_thresh = unique_asc[min(1, len(unique_asc) - 1)]

            cum_values = [cum_points.get(uid, 0.0) for uid in user_ids]
            cum_unique_desc = sorted(set(cum_values), reverse=True)
            cum_rank_by_value = {value: idx + 1 for idx, value in enumerate(cum_unique_desc)}

            points_by_user = {uid: score for uid, score in scores}

            gp_blockchips = blockchips_by_gp.get(gp.id, [])
            block_targets = {block.target_id for block in gp_blockchips}
            block_blockers = {block.blocker_id for block in gp_blockchips}
            for block in gp_blockchips:
                if block.target_id:
                    blocks_received_count[block.target_id] += 1
                    if blocks_received_count[block.target_id] == 3:
                        unlock(block.target_id, "public_enemy", season=season, gp=gp)

            for porra in gp_porras:
                uid = porra.user_id
                points = float(porra.points or 0.0)
                rank = rank_by_value.get(points, 0)
                win = rank == 1
                top3 = points >= top3_thresh
                top5 = points >= top5_thresh
                bottom2 = points <= bottom2_thresh

                if win:
                    win_streak[uid] += 1
                else:
                    win_streak[uid] = 0
                if win_streak[uid] >= 3:
                    unlock(uid, "grand_chelem", season=season, gp=gp)

                if top3:
                    top3_streak[uid] += 1
                else:
                    top3_streak[uid] = 0
                if top3_streak[uid] >= 5:
                    unlock(uid, "untouchable", season=season, gp=gp)

                if top5:
                    top5_streak[uid] += 1
                else:
                    top5_streak[uid] = 0
                if top5_streak[uid] >= 8:
                    unlock(uid, "mr_consistency", season=season, gp=gp)

                if bottom2:
                    bottom2_streak[uid] += 1
                    bottom2_count[uid] += 1
                else:
                    bottom2_streak[uid] = 0
                if bottom2_streak[uid] >= 3:
                    unlock(uid, "latifisexual", season=season, gp=gp)
                if bottom2_count[uid] >= 5:
                    unlock(uid, "rock_bottom", season=season, gp=gp)

                if win:
                    wins_count[uid] += 1
                if rank == 2:
                    second_count[uid] += 1

                if win and cum_rank_by_value.get(cum_points.get(uid, 0.0), 0) > 5:
                    unlock(uid, "comeback_kid", season=season, gp=gp)

                if win and uid in prev_bottom2:
                    unlock(uid, "zero_to_hero", season=season, gp=gp)

                if win and uid in block_targets:
                    unlock(uid, "cold_blood", season=season, gp=gp)

                if win and porra.triple_points_chip:
                    unlock(uid, "timely_drs", season=season, gp=gp)

                if porra.triple_points_chip and uid in block_blockers:
                    unlock(uid, "chip_combo", season=season, gp=gp)

                if win and second_max is not None and max_points > second_max and (max_points - second_max) == 1:
                    unlock(uid, "photo_finish", season=season, gp=gp)

                if win:
                    driver_ids = [porra.driver1_id, porra.driver2_id, porra.driver3_id, porra.driver4_id, porra.driver5_id]
                    team_ids = [porra.team1_id, porra.team2_id]
                    if all(driver_ids) and all(team_ids):
                        total_cost = 0.0
                        cost_ok = True
                        for driver_id in driver_ids:
                            _, price = driver_points_map.get((gp.id, driver_id), (0.0, 0.0))
                            if price == 0.0:
                                cost_ok = False
                                break
                            total_cost += price
                        if cost_ok:
                            for team_id in team_ids:
                                price = team_points_map.get((gp.id, team_id), 0.0)
                                if price == 0.0:
                                    cost_ok = False
                                    break
                                total_cost += price
                        if cost_ok and total_cost < 135.0:
                            unlock(uid, "tacanos_extremos", season=season, gp=gp)

                driver1_id = porra.driver1_id
                if driver1_id:
                    driver_points = driver_points_map.get((gp.id, driver1_id))
                    if driver_points and driver_points[0] >= 40:
                        unlock(uid, "capitan_general", season=season, gp=gp)

                if all([porra.driver1_id, porra.driver2_id, porra.driver3_id, porra.driver4_id, porra.driver5_id]):
                    driver_teams = [
                        porra.driver1.team_id if porra.driver1 else None,
                        porra.driver2.team_id if porra.driver2 else None,
                        porra.driver3.team_id if porra.driver3 else None,
                        porra.driver4.team_id if porra.driver4 else None,
                        porra.driver5.team_id if porra.driver5 else None,
                    ]
                    if None not in driver_teams and len(set(driver_teams)) == 5:
                        team1_id = porra.team1_id
                        team2_id = porra.team2_id
                        if team1_id and team2_id and team1_id != team2_id:
                            if team1_id not in driver_teams and team2_id not in driver_teams:
                                unlock(uid, "rainbow", season=season, gp=gp)

                race_results = race_results_map.get(gp.id)
                if race_results:
                    if (
                        porra.poleman_id == race_results.poleman_id
                        and porra.first_pos_id == race_results.first_pos_id
                        and porra.second_pos_id == race_results.second_pos_id
                        and porra.third_pos_id == race_results.third_pos_id
                        and porra.fast_lap_id == race_results.fast_lap_id
                        and porra.team_winner_id == race_results.team_winner_id
                    ):
                        unlock(uid, "sniper", season=season, gp=gp)

            for block in gp_blockchips:
                target_points = points_by_user.get(block.target_id)
                if target_points is None:
                    continue
                if target_points <= bottom2_thresh:
                    unlock(block.blocker_id, "block_master", season=season, gp=gp)

            for uid, points in points_by_user.items():
                cum_points[uid] = cum_points.get(uid, 0.0) + points
                all_time_points[uid] = all_time_points.get(uid, 0.0) + points

                if cum_points[uid] >= 3000:
                    unlock(uid, "big_guy", season=season, gp=gp)

                if uid not in hall_of_fame_unlocked and all_time_points[uid] >= 10000:
                    unlock(uid, "hall_of_fame", season=season, gp=gp)
                    hall_of_fame_unlocked.add(uid)

            prev_bottom2 = {uid for uid, points in points_by_user.items() if points <= bottom2_thresh}

        # Season-end achievements — only unlock when ALL GPs in the season have been scored
        total_season_gps = GrandPrix.objects.filter(season=season).count()
        season_complete = len(gps) >= total_season_gps and total_season_gps > 0

        if season_complete and cum_points:
            max_points = max(cum_points.values())
            for uid, total_points in cum_points.items():
                if total_points == max_points:
                    unlock(uid, "world_champion", season=season, gp=last_gp)

        if season_complete and members_by_team:
            team_totals: dict[int, float] = defaultdict(float)
            for uid, total_points in cum_points.items():
                team_id = team_by_user_id.get(uid)
                if team_id is None:
                    continue
                team_totals[team_id] += total_points
            if team_totals:
                best_total = max(team_totals.values())
                for team_id, total in team_totals.items():
                    if total == best_total:
                        for member_id in members_by_team.get(team_id, []):
                            unlock(member_id, "constructor_legend", season=season, gp=last_gp)

        if season_complete:
            for uid in user_ids:
                if wins_count.get(uid, 0) == 0 and second_count.get(uid, 0) >= 3:
                    unlock(uid, "almost_there", season=season, gp=last_gp)
