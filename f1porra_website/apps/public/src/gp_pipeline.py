"""
Automated GP Points Pipeline
==============================
Orchestrates the full post-race workflow:

1. Fetch results from Jolpica (primary) or OpenF1 (fallback)
2. Create the RaceResults record for the GP
3. Compute driver & team fantasy points (qualifying + race)
4. Upload points (DriverPoints / TeamPoints) for the GP
5. Compute each user's Porra points
6. Update prices for the *next* GP
7. Recompute achievements

This module is API-driven: no Excel file needed.
"""
import logging
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd
from django.db import transaction
from django.db.models import Max

from f1porra_website.apps.public.models import (
    Season, GrandPrix, Driver, Team,
    DriverPoints, TeamPoints, RaceResults, Porra, BlockChip,
)
from f1porra_website.apps.public.src.api_client import (
    fetch_gp_data, GPSessionData, QualifyingResult, RaceResultEntry,
)
from f1porra_website.apps.public.src.actualizar_precios import update_points
from f1porra_website.apps.public.services.achievement_service import recompute_achievements

logger = logging.getLogger("gp_pipeline")

# ---------------------------------------------------------------------------
# Name normalization — API names → DB names
# ---------------------------------------------------------------------------
# Add entries here whenever the API spells a name differently from your DB.

DRIVER_NAME_MAP: dict[str, str] = {
    "Nico Hülkenberg": "Nico Hulkenberg",
    "Sergio Pérez": "Sergio Perez",
    "Guanyu Zhou": "Zhou Guanyu",
    "Franco Colapinto ": "Franco Colapinto",
    "Andrea Kimi Antonelli": "Kimi Antonelli",
}

CONSTRUCTOR_NAME_MAP: dict[str, str] = {
    "Alpine F1 Team": "Alpine",
    "Haas F1 Team": "Haas F1 Team",
    "RB F1 Team": "Racing Bulls",
    "Racing Bulls": "Racing Bulls",
    "Sauber": "Audi",
    "Stake F1 Team Kick Sauber": "Audi",
    "McLaren": "McLaren",
    "Red Bull": "Red Bull Racing",
    "Cadillac F1 Team": "Cadillac",
}


def _norm_driver(name: str) -> str:
    return DRIVER_NAME_MAP.get(name, name).strip()


def _norm_constructor(name: str) -> str:
    return CONSTRUCTOR_NAME_MAP.get(name, name).strip()


# ---------------------------------------------------------------------------
# Step 1 — Resolve helpers
# ---------------------------------------------------------------------------

def _resolve_driver(season: Season, name: str) -> Optional[Driver]:
    """Resolve an API driver name to a DB Driver object."""
    norm = _norm_driver(name)
    driver = Driver.objects.filter(season=season, name=norm).first()
    if not driver:
        # Try fuzzy: last-name match
        last = norm.split()[-1] if norm else ""
        driver = Driver.objects.filter(season=season, name__icontains=last).first()
    if not driver:
        logger.warning("Could not resolve driver '%s' (normalized: '%s') in season %s", name, norm, season)
    return driver


def _resolve_team(season: Season, name: str) -> Optional[Team]:
    """Resolve an API constructor name to a DB Team object."""
    norm = _norm_constructor(name)
    team = Team.objects.filter(season=season, name=norm).first()
    if not team:
        # Fuzzy
        team = Team.objects.filter(season=season, name__icontains=norm.split()[0]).first()
    if not team:
        logger.warning("Could not resolve team '%s' (normalized: '%s') in season %s", name, norm, season)
    return team


# ---------------------------------------------------------------------------
# Step 2 — Create RaceResults
# ---------------------------------------------------------------------------

def create_race_results(season: Season, gp: GrandPrix, data: GPSessionData) -> RaceResults:
    """Create or update the RaceResults record for a GP."""
    pole = _resolve_driver(season, data.pole_sitter) if data.pole_sitter else None
    first = _resolve_driver(season, data.race_winner) if data.race_winner else None
    second = _resolve_driver(season, data.second_place) if data.second_place else None
    third = _resolve_driver(season, data.third_place) if data.third_place else None
    fast = _resolve_driver(season, data.fastest_lap_driver) if data.fastest_lap_driver else None
    team_w = _resolve_team(season, data.winning_constructor) if data.winning_constructor else None

    rr, created = RaceResults.objects.update_or_create(
        season=season,
        gp=gp,
        defaults={
            "poleman": pole,
            "first_pos": first,
            "second_pos": second,
            "third_pos": third,
            "fast_lap": fast,
            "team_winner": team_w,
        },
    )
    action = "Created" if created else "Updated"
    logger.info("%s RaceResults for %s", action, gp)
    return rr


# ---------------------------------------------------------------------------
# Step 3 — Compute driver & team fantasy points from API data
# ---------------------------------------------------------------------------

# Qualifying helpers (same logic as existing calculate_gp_points.py)

def _quali_participation(q: QualifyingResult) -> int:
    if q.q3_time:
        return 3
    if q.q2_time:
        return 2
    if q.q1_time:
        return 1
    return 0


def _quali_reverse(position: int) -> int:
    return max(0, 11 - position) if position <= 10 else 0


def _team_quali_bonus(q3_count: int, q2_count: int) -> int:
    if q3_count == 2:
        return 5
    if q2_count == 2:
        return 3
    return 1


DNF_STATUSES = frozenset([
    "Retired", "Accident", "Power Unit", "Brakes", "Collision",
    "Engine", "Radiator", "Collision Damage", "Gearbox", "Hydraulics",
    "Electrical", "Transmission", "Clutch", "Suspension", "Puncture",
    "Mechanical", "Overheating", "Oil Leak", "Water Leak", "Fuel Pump",
    "Wheel", "Throttle", "Steering", "Technical", "Spun off",
    "DNF", "Did not finish",
])


def compute_fantasy_points(data: GPSessionData) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Compute driver and team fantasy points from API data.
    Returns (driver_points_df, team_points_df) with columns:
        Driver:  [Driver, Constructor, Total Points]
        Team:    [Constructor, Total Points]
    """
    # ── Qualifying points ──────────────────────────────────────────────
    if data.qualifying:
        q_rows = []
        for q in sorted(data.qualifying, key=lambda x: x.position):
            q_rows.append({
                "Driver": q.driver_name,
                "Constructor": q.constructor_name,
                "Position": q.position,
                "Q1": q.q1_time,
                "Q2": q.q2_time,
                "Q3": q.q3_time,
            })
        qdf = pd.DataFrame(q_rows)

        qdf["Participation"] = qdf.apply(
            lambda r: 3 if pd.notna(r["Q3"]) and r["Q3"]
                      else (2 if pd.notna(r["Q2"]) and r["Q2"]
                            else (1 if pd.notna(r["Q1"]) and r["Q1"] else 0)),
            axis=1,
        )
        qdf["Reverse"] = qdf["Position"].apply(lambda p: max(0, 11 - p) if p <= 10 else 0)
        qdf["TeammateBonus"] = qdf.groupby("Constructor")["Position"].transform(
            lambda x: (x == x.min()).astype(int)
        )
        qdf["QualyPoints"] = qdf["Participation"] + qdf["Reverse"] + qdf["TeammateBonus"]

        # Team qualifying
        team_q = qdf.groupby("Constructor").agg(
            q3_count=("Q3", lambda x: x.notna().sum() - (x == "").sum() if hasattr(x, 'str') else x.apply(lambda v: v is not None and v != "").sum()),
            q2_count=("Q2", lambda x: x.notna().sum() - (x == "").sum() if hasattr(x, 'str') else x.apply(lambda v: v is not None and v != "").sum()),
            driver_q_pts=("QualyPoints", "sum"),
        ).reset_index()
        team_q["TeamQualyBonus"] = team_q.apply(
            lambda r: _team_quali_bonus(int(r["q3_count"]), int(r["q2_count"])), axis=1
        )
        team_q["TeamQualyPoints"] = team_q["TeamQualyBonus"] + team_q["driver_q_pts"]
    else:
        # No qualifying data — zero out
        qdf = pd.DataFrame(columns=["Driver", "Constructor", "QualyPoints"])
        team_q = pd.DataFrame(columns=["Constructor", "TeamQualyPoints"])

    # ── Race points ────────────────────────────────────────────────────
    if data.race:
        r_rows = []
        for r in data.race:
            r_rows.append({
                "Driver": r.driver_name,
                "Constructor": r.constructor_name,
                "Position_Race": r.position,
                "Grid": r.grid,
                "F1Points": r.points,
                "Status": r.status,
                "Laps": r.laps,
            })
        rdf = pd.DataFrame(r_rows)

        # Merge qualy position
        if not qdf.empty and "Position" in qdf.columns:
            rdf = rdf.merge(
                qdf[["Driver", "Position"]].rename(columns={"Position": "Position_Qualy"}),
                on="Driver",
                how="left",
            )
            rdf["Position_Qualy"] = rdf["Position_Qualy"].fillna(rdf["Grid"]).astype(int)
        else:
            rdf["Position_Qualy"] = rdf["Grid"].astype(int)

        def race_pts(row):
            pts = int(row["F1Points"])
            status = str(row.get("Status", ""))
            # DNF penalty
            if status in DNF_STATUSES or status.startswith("Retired"):
                return -10
            positions_gained = int(row["Position_Qualy"]) - int(row["Position_Race"])
            return pts + positions_gained

        rdf["RacePoints"] = rdf.apply(race_pts, axis=1)

        # Teammate bonus: driver finishing ahead gets +2
        def teammate_bonus(group):
            if len(group) == 2:
                g = group.sort_values("Position_Race")
                idx_first = g.index[0]
                group.loc[idx_first, "RacePoints"] = group.loc[idx_first, "RacePoints"] + 2
            return group

        rdf = rdf.groupby("Constructor", group_keys=False).apply(teammate_bonus).reset_index(drop=True)

        # Team race points
        team_r = rdf.groupby("Constructor")["RacePoints"].sum().reset_index()
        team_r.columns = ["Constructor", "TeamRacePoints"]
    else:
        rdf = pd.DataFrame(columns=["Driver", "Constructor", "RacePoints", "Position_Race"])
        team_r = pd.DataFrame(columns=["Constructor", "TeamRacePoints"])

    # ── Combine ────────────────────────────────────────────────────────
    if not rdf.empty and not qdf.empty and "QualyPoints" in qdf.columns:
        driver_total = rdf[["Driver", "Constructor", "RacePoints", "Position_Race"]].merge(
            qdf[["Driver", "QualyPoints"]], on="Driver", how="left"
        )
        driver_total["QualyPoints"] = driver_total["QualyPoints"].fillna(0)
    elif not rdf.empty:
        driver_total = rdf[["Driver", "Constructor", "RacePoints", "Position_Race"]].copy()
        driver_total["QualyPoints"] = 0
    else:
        driver_total = pd.DataFrame(columns=["Driver", "Constructor", "RacePoints", "QualyPoints"])

    driver_total["Total Points"] = driver_total["RacePoints"] + driver_total["QualyPoints"]

    if not team_r.empty and not team_q.empty:
        team_total = team_q[["Constructor", "TeamQualyPoints"]].merge(
            team_r, on="Constructor", how="outer"
        )
        team_total = team_total.fillna(0)
    elif not team_r.empty:
        team_total = team_r.copy()
        team_total["TeamQualyPoints"] = 0
    elif not team_q.empty:
        team_total = team_q[["Constructor", "TeamQualyPoints"]].copy()
        team_total["TeamRacePoints"] = 0
    else:
        team_total = pd.DataFrame(columns=["Constructor", "TeamQualyPoints", "TeamRacePoints"])

    if "TeamQualyPoints" in team_total.columns and "TeamRacePoints" in team_total.columns:
        team_total["Total Points"] = team_total["TeamQualyPoints"] + team_total["TeamRacePoints"]
    else:
        team_total["Total Points"] = 0

    return driver_total, team_total


# ---------------------------------------------------------------------------
# Step 4 — Save DriverPoints / TeamPoints
# ---------------------------------------------------------------------------

def save_gp_points(
    season: Season,
    gp: GrandPrix,
    driver_df: pd.DataFrame,
    team_df: pd.DataFrame,
) -> None:
    """Persist computed fantasy points into DriverPoints and TeamPoints."""
    with transaction.atomic():
        for _, row in driver_df.iterrows():
            driver = _resolve_driver(season, row["Driver"])
            if not driver:
                continue
            DriverPoints.objects.update_or_create(
                season=season,
                driver=driver,
                gp=gp,
                defaults={"points": int(row["Total Points"])},
            )
            logger.info("DriverPoints: %s → %d pts", driver.name, int(row["Total Points"]))

        for _, row in team_df.iterrows():
            team = _resolve_team(season, row["Constructor"])
            if not team:
                continue
            TeamPoints.objects.update_or_create(
                season=season,
                team=team,
                gp=gp,
                defaults={"points": int(row["Total Points"])},
            )
            logger.info("TeamPoints: %s → %d pts", team.name, int(row["Total Points"]))


# ---------------------------------------------------------------------------
# Step 5 — Compute porra points (per user)
# ---------------------------------------------------------------------------

def compute_porra_points_for_gp(season: Season, gp: GrandPrix) -> None:
    """Calculate and save each user's porra points for a specific GP."""
    try:
        race_results = RaceResults.objects.get(season=season, gp=gp)
    except RaceResults.DoesNotExist:
        logger.error("No RaceResults found for %s — cannot compute porra points.", gp)
        return

    porras = Porra.objects.filter(season=season, gp=gp)
    driver_points_qs = DriverPoints.objects.filter(season=season, gp=gp)
    team_points_qs = TeamPoints.objects.filter(season=season, gp=gp)

    for porra in porras:
        total = 0

        # --- Prediction section ---
        if porra.poleman and porra.poleman == race_results.poleman:
            total += 5
        if porra.first_pos and porra.first_pos == race_results.first_pos:
            total += 10
        if porra.second_pos and porra.second_pos == race_results.second_pos:
            total += 10
        if porra.third_pos and porra.third_pos == race_results.third_pos:
            total += 10
        if porra.fast_lap and porra.fast_lap == race_results.fast_lap:
            total += 3
        if porra.team_winner and porra.team_winner == race_results.team_winner:
            total += 5

        # --- Fantasy section ---
        block = BlockChip.objects.filter(
            season=season, gp=gp, target=porra.user
        ).first()
        blocked_driver_id = block.blocked_driver_id if block else None
        blocked_team_id = block.blocked_team_id if block else None

        for i, driver in enumerate(
            [porra.driver1, porra.driver2, porra.driver3, porra.driver4, porra.driver5],
            start=1,
        ):
            if not driver:
                continue
            if blocked_driver_id and driver.id == blocked_driver_id:
                continue
            dp = driver_points_qs.filter(driver=driver).first()
            if dp and dp.points is not None:
                if i == 1:
                    multiplier = 3 if porra.triple_points_chip else 2
                    total += dp.points * multiplier
                else:
                    total += dp.points

        for team in [porra.team1, porra.team2]:
            if not team:
                continue
            if blocked_team_id and team.id == blocked_team_id:
                continue
            tp = team_points_qs.filter(team=team).first()
            if tp and tp.points is not None:
                total += tp.points

        porra.points = total
        porra.save()
        logger.info("Porra %s (%s) → %d pts", porra.user.username, gp.country, total)


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

class PipelineResult:
    """Result summary of a pipeline run."""
    def __init__(self):
        self.success = False
        self.gp: Optional[GrandPrix] = None
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.steps_completed: list[str] = []

    def __str__(self):
        status = "SUCCESS" if self.success else "FAILED"
        return (
            f"Pipeline {status} for {self.gp}\n"
            f"  Steps: {', '.join(self.steps_completed)}\n"
            f"  Warnings: {len(self.warnings)}\n"
            f"  Errors: {len(self.errors)}"
        )


def run_gp_pipeline(gp: GrandPrix, retry_count: int = 3) -> PipelineResult:
    """
    Run the full automated pipeline for a single Grand Prix.

    Steps:
        1. Fetch GP data from API (Jolpica → OpenF1 fallback)
        2. Create RaceResults record
        3. Compute driver & team fantasy points
        4. Save DriverPoints & TeamPoints for this GP
        5. Compute porra points for all users
        6. Update prices for the next GP
        7. Recompute achievements
    """
    result = PipelineResult()
    result.gp = gp
    season = gp.season

    if not season:
        result.errors.append("GP has no associated season.")
        return result

    nround = gp.nround
    if not nround:
        result.errors.append("GP has no round number.")
        return result

    # Step 1 — Fetch data from API
    logger.info("═══ Pipeline start: %s (round %d) ═══", gp, nround)
    gp_data = None
    for attempt in range(1, retry_count + 1):
        gp_data = fetch_gp_data(season.year, nround)
        if gp_data:
            break
        logger.warning("Attempt %d/%d: No data yet, will retry...", attempt, retry_count)
        if attempt < retry_count:
            import time
            time.sleep(60 * 5)  # wait 5 min between retries

    if not gp_data:
        result.errors.append(
            f"No race data available from any API after {retry_count} attempts. "
            "Data may not be published yet."
        )
        return result
    result.steps_completed.append("1-fetch_api_data")

    # Step 2 — Create RaceResults
    try:
        create_race_results(season, gp, gp_data)
        result.steps_completed.append("2-create_race_results")
    except Exception as exc:
        result.errors.append(f"Failed to create RaceResults: {exc}")
        logger.exception("RaceResults creation failed")
        return result

    # Step 3+4 — Compute and save fantasy points
    try:
        driver_df, team_df = compute_fantasy_points(gp_data)
        save_gp_points(season, gp, driver_df, team_df)
        result.steps_completed.append("3-compute_fantasy_points")
        result.steps_completed.append("4-save_driver_team_points")
    except Exception as exc:
        result.errors.append(f"Failed to compute/save fantasy points: {exc}")
        logger.exception("Fantasy points computation failed")
        return result

    # Step 5 — Compute porra points
    try:
        compute_porra_points_for_gp(season, gp)
        result.steps_completed.append("5-compute_porra_points")
    except Exception as exc:
        result.errors.append(f"Failed to compute porra points: {exc}")
        logger.exception("Porra points computation failed")
        return result

    # Step 6 — Update prices for next GP
    try:
        update_points()
        result.steps_completed.append("6-update_next_gp_prices")
    except Exception as exc:
        result.warnings.append(f"Price update warning: {exc}")
        logger.warning("Price update issue (non-fatal): %s", exc)
        # Non-fatal: prices can be updated manually

    # Step 7 — Achievements
    try:
        recompute_achievements(rebuild=False)
        result.steps_completed.append("7-recompute_achievements")
    except Exception as exc:
        result.warnings.append(f"Achievement recompute warning: {exc}")
        logger.warning("Achievement recompute issue: %s", exc)

    result.success = True
    logger.info("═══ Pipeline complete: %s ═══\n%s", gp, result)
    return result
