"""
Automated GP Points Pipeline — Dual-Trigger Architecture
==========================================================
Orchestrates two separate workflows per GP weekend:

**Qualifying pipeline** (triggered ~3-4 h after qualy_date):
    1. Fetch qualifying results from API
    2. Create RaceResults record with poleman only
    3. Compute qualifying-only driver & team fantasy points
    4. Save DriverPoints / TeamPoints (qualy portion only)
    5. Compute each user's partial Porra points (poleman + qualy fantasy)

**Race pipeline** (triggered ~4-5 h after gp_date):
    1. Fetch full GP data (qualy + race) from API
    2. Update existing RaceResults with race fields (P1-P3, fast lap, team winner)
    3. Compute combined driver & team fantasy points (qualy + race)
    4. Update DriverPoints / TeamPoints with full combined points
    5. Recompute each user's Porra points (all predictions + full fantasy)
    6. Update prices for the next GP
    7. Recompute achievements

A legacy ``run_gp_pipeline()`` is kept for backward compatibility (runs both
phases in sequence).

This module is API-driven: no Excel file needed.
"""
import logging
import time as _time
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd
from django.db import transaction
from django.db.models import Max

from f1porra_website.apps.public.models import (
    Season, GrandPrix, Driver, Team,
    DriverPoints, TeamPoints, RaceResults, Porra, BlockChip,
    DriverGPPointsDetail, TeamGPPointsDetail,
)
from f1porra_website.apps.public.src.api_client import (
    fetch_gp_data, fetch_qualy_data,
    GPSessionData, QualifyingResult, RaceResultEntry,
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
# Step 2 — Create / Update RaceResults
# ---------------------------------------------------------------------------

def create_qualy_race_results(season: Season, gp: GrandPrix, data: GPSessionData) -> RaceResults:
    """Create the RaceResults record after qualifying — sets poleman only."""
    pole = _resolve_driver(season, data.pole_sitter) if data.pole_sitter else None

    rr, created = RaceResults.objects.update_or_create(
        season=season,
        gp=gp,
        defaults={"poleman": pole},
    )
    action = "Created" if created else "Updated"
    logger.info("%s RaceResults (qualy) for %s — poleman: %s", action, gp, pole)
    return rr


def update_race_results(season: Season, gp: GrandPrix, data: GPSessionData) -> RaceResults:
    """Update existing RaceResults with race fields (P1-P3, fast lap, team winner)."""
    first = _resolve_driver(season, data.race_winner) if data.race_winner else None
    second = _resolve_driver(season, data.second_place) if data.second_place else None
    third = _resolve_driver(season, data.third_place) if data.third_place else None
    fast = _resolve_driver(season, data.fastest_lap_driver) if data.fastest_lap_driver else None
    team_w = _resolve_team(season, data.winning_constructor) if data.winning_constructor else None
    # Also re-set poleman in case qualy data was incomplete earlier
    pole = _resolve_driver(season, data.pole_sitter) if data.pole_sitter else None

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
    logger.info("%s RaceResults (race) for %s", action, gp)
    return rr


def create_race_results(season: Season, gp: GrandPrix, data: GPSessionData) -> RaceResults:
    """Legacy: Create or update the full RaceResults record for a GP (both qualy + race)."""
    return update_race_results(season, gp, data)


# ---------------------------------------------------------------------------
# Step 3 — Compute driver & team fantasy points from API data
# ---------------------------------------------------------------------------

# Qualifying helpers (same logic as existing calculate_gp_points.py)

def _quali_participation(q: QualifyingResult) -> int:
    if q.q3_time:
        return 3
    if q.q2_time:
        return 2
    # Every driver in qualifying gets at least 1 point (Q1 participation)
    return 1


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

# Sprint race position points: 8,7,6,5,4,3,2,1 for P1-P8
SPRINT_POSITION_POINTS = {1: 8, 2: 7, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}


def compute_qualy_fantasy_points(data: GPSessionData) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Compute QUALIFYING-ONLY driver and team fantasy points.
    Called after qualifying, before the race has happened.

    Returns (driver_points_df, team_points_df) with columns:
        Driver:  [Driver, Constructor, Total Points]   (qualy points only)
        Team:    [Constructor, Total Points]            (team qualy points only)
    """
    if not data.qualifying:
        return (
            pd.DataFrame(columns=["Driver", "Constructor", "Total Points"]),
            pd.DataFrame(columns=["Constructor", "Total Points"]),
        )

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
                        else 1),  # every driver gets at least 1 pt (Q1 participation)
        axis=1,
    )
    qdf["Reverse"] = qdf["Position"].apply(lambda p: max(0, 11 - p) if p <= 10 else 0)
    qdf["TeammateBonus"] = qdf.groupby("Constructor")["Position"].transform(
        lambda x: (x == x.min()).astype(int)
    )
    # DNS/DNF penalty: -10 if no Q1 time set (crash, technical, DNS)
    qdf["QualyDNSPenalty"] = qdf["Q1"].apply(
        lambda v: -10 if (v is None or (isinstance(v, str) and v.strip() == "")) else 0
    )
    qdf["QualyPoints"] = (
        qdf["Participation"] + qdf["Reverse"] + qdf["TeammateBonus"]
        + qdf["QualyDNSPenalty"]
    )

    # Driver output: qualy points (with breakdown for detail table)
    driver_total = qdf[["Driver", "Constructor", "QualyPoints",
                         "Participation", "Reverse", "TeammateBonus",
                         "QualyDNSPenalty"]].copy()
    driver_total["Total Points"] = driver_total["QualyPoints"]

    # Team qualifying
    team_q = qdf.groupby("Constructor").agg(
        q3_count=("Q3", lambda x: x.apply(lambda v: v is not None and v != "").sum()),
        q2_count=("Q2", lambda x: x.apply(lambda v: v is not None and v != "").sum()),
        driver_q_pts=("QualyPoints", "sum"),
    ).reset_index()
    team_q["TeamQualyBonus"] = team_q.apply(
        lambda r: _team_quali_bonus(int(r["q3_count"]), int(r["q2_count"])), axis=1
    )
    team_q["Total Points"] = team_q["TeamQualyBonus"] + team_q["driver_q_pts"]

    # ── Sprint race points (only on sprint weekends) ───────────────────
    if data.sprint_race:
        sprint_driver_pts, sprint_team_pts = _compute_sprint_race_points(data)

        # Add sprint race points to driver totals
        if not sprint_driver_pts.empty:
            sprint_merge_cols = [c for c in sprint_driver_pts.columns if c != "Constructor"]
            driver_total = driver_total.merge(
                sprint_driver_pts[sprint_merge_cols],
                on="Driver", how="left",
            )
            driver_total["SprintRacePoints"] = driver_total["SprintRacePoints"].fillna(0)
            for sc in ["SprintPosPts", "SprintPosGained", "SprintTeammate", "SprintDNF"]:
                if sc in driver_total.columns:
                    driver_total[sc] = driver_total[sc].fillna(0)
            driver_total["Total Points"] = driver_total["Total Points"] + driver_total["SprintRacePoints"]

        # Add sprint race points to team totals
        if not sprint_team_pts.empty:
            team_q = team_q.merge(
                sprint_team_pts[["Constructor", "TeamSprintRacePoints"]],
                on="Constructor", how="left",
            )
            team_q["TeamSprintRacePoints"] = team_q["TeamSprintRacePoints"].fillna(0)
            team_q["Total Points"] = team_q["Total Points"] + team_q["TeamSprintRacePoints"]

    return driver_total, team_q[["Constructor", "Total Points", "TeamQualyBonus",
                                  "driver_q_pts"] + (
                                  ["TeamSprintRacePoints"] if "TeamSprintRacePoints" in team_q.columns else []
                                 )]


def _compute_sprint_race_points(data: GPSessionData) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Compute sprint race fantasy points.

    Same logic as regular race points BUT:
    - Position points: 8,7,6,5,4,3,2,1 for P1-P8 (instead of F1 25,18,15,12,10,8,6,4,2,1)
    - Positions gained from sprint grid
    - DNF penalty (-10)
    - Teammate bonus (+2 to driver finishing ahead)

    Returns (driver_sprint_df, team_sprint_df).
    """
    if not data.sprint_race:
        return (
            pd.DataFrame(columns=["Driver", "Constructor", "SprintRacePoints"]),
            pd.DataFrame(columns=["Constructor", "TeamSprintRacePoints"]),
        )

    s_rows = []
    for r in data.sprint_race:
        s_rows.append({
            "Driver": r.driver_name,
            "Constructor": r.constructor_name,
            "Position_Sprint": r.position,
            "SprintGrid": r.grid,
            "Status": r.status,
            "Laps": r.laps,
        })
    sdf = pd.DataFrame(s_rows)

    def sprint_pts(row):
        status = str(row.get("Status", ""))
        if status in DNF_STATUSES or status.startswith("Retired"):
            return -10
        pos = int(row["Position_Sprint"])
        f1_pts = SPRINT_POSITION_POINTS.get(pos, 0)
        positions_gained = int(row["SprintGrid"]) - pos
        return f1_pts + positions_gained

    sdf["SprintRacePoints"] = sdf.apply(sprint_pts, axis=1)

    # Sprint breakdown for detail table
    sdf["SprintPosPts"] = sdf["Position_Sprint"].apply(
        lambda p: SPRINT_POSITION_POINTS.get(int(p), 0)
    )
    sdf["SprintDNF"] = sdf.apply(
        lambda r: -10 if (str(r.get("Status", "")) in DNF_STATUSES
                          or str(r.get("Status", "")).startswith("Retired")) else 0,
        axis=1,
    )
    sdf["SprintPosGained"] = sdf.apply(
        lambda r: 0 if int(r["SprintDNF"]) != 0
                  else int(r["SprintGrid"]) - int(r["Position_Sprint"]),
        axis=1,
    )
    sdf["SprintTeammate"] = 0  # filled by teammate_bonus below

    # Teammate bonus: driver finishing ahead gets +2
    def teammate_bonus(group):
        if len(group) == 2:
            g = group.sort_values("Position_Sprint")
            idx_first = g.index[0]
            group.loc[idx_first, "SprintRacePoints"] = group.loc[idx_first, "SprintRacePoints"] + 2
            group.loc[idx_first, "SprintTeammate"] = 2
        return group

    sdf = sdf.groupby("Constructor", group_keys=False).apply(teammate_bonus).reset_index(drop=True)

    # Team sprint points
    team_s = sdf.groupby("Constructor")["SprintRacePoints"].sum().reset_index()
    team_s.columns = ["Constructor", "TeamSprintRacePoints"]

    return sdf[["Driver", "Constructor", "SprintRacePoints",
                "SprintPosPts", "SprintPosGained", "SprintTeammate", "SprintDNF"]], team_s


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
                            else 1),  # every driver gets at least 1 pt (Q1 participation)
            axis=1,
        )
        qdf["Reverse"] = qdf["Position"].apply(lambda p: max(0, 11 - p) if p <= 10 else 0)
        qdf["TeammateBonus"] = qdf.groupby("Constructor")["Position"].transform(
            lambda x: (x == x.min()).astype(int)
        )
        # DNS/DNF penalty: -10 if no Q1 time set (crash, technical, DNS)
        qdf["QualyDNSPenalty"] = qdf["Q1"].apply(
            lambda v: -10 if (v is None or (isinstance(v, str) and v.strip() == "")) else 0
        )
        qdf["QualyPoints"] = (
            qdf["Participation"] + qdf["Reverse"] + qdf["TeammateBonus"]
            + qdf["QualyDNSPenalty"]
        )

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

        # Breakdown columns for the detail table
        rdf["RaceF1Pts"] = rdf["F1Points"].astype(int)
        rdf["RaceDNF"] = rdf.apply(
            lambda r: -10 if (str(r.get("Status", "")) in DNF_STATUSES
                              or str(r.get("Status", "")).startswith("Retired")) else 0,
            axis=1,
        )
        rdf["RacePosGained"] = rdf.apply(
            lambda r: 0 if int(r["RaceDNF"]) != 0
                      else int(r["Position_Qualy"]) - int(r["Position_Race"]),
            axis=1,
        )
        rdf["RaceTeammate"] = 0  # will be filled by teammate_bonus below

        # Teammate bonus: driver finishing ahead gets +2
        def teammate_bonus(group):
            if len(group) == 2:
                g = group.sort_values("Position_Race")
                idx_first = g.index[0]
                group.loc[idx_first, "RacePoints"] = group.loc[idx_first, "RacePoints"] + 2
                group.loc[idx_first, "RaceTeammate"] = 2
            return group

        rdf = rdf.groupby("Constructor", group_keys=False).apply(teammate_bonus).reset_index(drop=True)

        # Team race points
        team_r = rdf.groupby("Constructor")["RacePoints"].sum().reset_index()
        team_r.columns = ["Constructor", "TeamRacePoints"]
    else:
        rdf = pd.DataFrame(columns=["Driver", "Constructor", "RacePoints", "Position_Race"])
        team_r = pd.DataFrame(columns=["Constructor", "TeamRacePoints"])

    # ── Combine ────────────────────────────────────────────────────────
    race_detail_cols = ["Driver", "Constructor", "RacePoints", "Position_Race",
                        "RaceF1Pts", "RaceDNF", "RacePosGained", "RaceTeammate"]
    qualy_detail_cols = ["Driver", "QualyPoints", "Participation", "Reverse",
                         "TeammateBonus", "QualyDNSPenalty"]

    if not rdf.empty and not qdf.empty and "QualyPoints" in qdf.columns:
        avail_race = [c for c in race_detail_cols if c in rdf.columns]
        avail_qualy = [c for c in qualy_detail_cols if c in qdf.columns]
        driver_total = rdf[avail_race].merge(
            qdf[avail_qualy], on="Driver", how="left"
        )
        driver_total["QualyPoints"] = driver_total["QualyPoints"].fillna(0)
    elif not rdf.empty:
        avail_race = [c for c in race_detail_cols if c in rdf.columns]
        driver_total = rdf[avail_race].copy()
        driver_total["QualyPoints"] = 0
    else:
        driver_total = pd.DataFrame(columns=["Driver", "Constructor", "RacePoints", "QualyPoints"])

    # Fill missing breakdown columns with 0
    for col in ["Participation", "Reverse", "TeammateBonus", "QualyDNSPenalty",
                "RaceF1Pts", "RaceDNF", "RacePosGained", "RaceTeammate"]:
        if col not in driver_total.columns:
            driver_total[col] = 0
        else:
            driver_total[col] = driver_total[col].fillna(0)

    driver_total["Total Points"] = driver_total["RacePoints"] + driver_total["QualyPoints"]

    if not team_r.empty and not team_q.empty:
        team_q_cols = [c for c in ["Constructor", "TeamQualyPoints", "TeamQualyBonus",
                                    "driver_q_pts"] if c in team_q.columns]
        team_total = team_q[team_q_cols].merge(
            team_r, on="Constructor", how="outer"
        )
        team_total = team_total.fillna(0)
    elif not team_r.empty:
        team_total = team_r.copy()
        team_total["TeamQualyPoints"] = 0
        team_total["TeamQualyBonus"] = 0
        team_total["driver_q_pts"] = 0
    elif not team_q.empty:
        team_q_cols = [c for c in ["Constructor", "TeamQualyPoints", "TeamQualyBonus",
                                    "driver_q_pts"] if c in team_q.columns]
        team_total = team_q[team_q_cols].copy()
        team_total["TeamRacePoints"] = 0
    else:
        team_total = pd.DataFrame(columns=["Constructor", "TeamQualyPoints", "TeamRacePoints"])

    if "TeamQualyPoints" in team_total.columns and "TeamRacePoints" in team_total.columns:
        team_total["Total Points"] = team_total["TeamQualyPoints"] + team_total["TeamRacePoints"]
    else:
        team_total["Total Points"] = 0

    # ── Sprint race points (only on sprint weekends) ───────────────────
    if data.sprint_race:
        sprint_driver_pts, sprint_team_pts = _compute_sprint_race_points(data)

        if not sprint_driver_pts.empty and not driver_total.empty:
            sprint_merge_cols = [c for c in sprint_driver_pts.columns if c != "Constructor"]
            driver_total = driver_total.merge(
                sprint_driver_pts[sprint_merge_cols],
                on="Driver", how="left",
            )
            driver_total["SprintRacePoints"] = driver_total["SprintRacePoints"].fillna(0)
            for sc in ["SprintPosPts", "SprintPosGained", "SprintTeammate", "SprintDNF"]:
                if sc in driver_total.columns:
                    driver_total[sc] = driver_total[sc].fillna(0)
            driver_total["Total Points"] = driver_total["Total Points"] + driver_total["SprintRacePoints"]

        if not sprint_team_pts.empty and not team_total.empty:
            team_total = team_total.merge(
                sprint_team_pts[["Constructor", "TeamSprintRacePoints"]],
                on="Constructor", how="left",
            )
            team_total["TeamSprintRacePoints"] = team_total["TeamSprintRacePoints"].fillna(0)
            team_total["Total Points"] = team_total["Total Points"] + team_total["TeamSprintRacePoints"]

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
# Step 4b — Save points breakdown to detail tables
# ---------------------------------------------------------------------------

def _val(row, col):
    """Safely extract an integer from a DataFrame row, defaulting to 0."""
    v = row.get(col)
    return int(v) if pd.notna(v) else 0


def save_gp_points_detail(
    season: Season,
    gp: GrandPrix,
    driver_df: pd.DataFrame,
    team_df: pd.DataFrame,
) -> None:
    """
    Persist per-component breakdown into DriverGPPointsDetail / TeamGPPointsDetail.

    Preserves any existing ``admin_adjustment`` so admin overrides survive
    pipeline re-runs.  After saving, updates the DataFrames' "Total Points"
    column in-place so that ``save_gp_points`` (called next) stores the
    ``final_total`` that includes the adjustment.
    """
    with transaction.atomic():
        # ── Drivers ────────────────────────────────────────────────────
        for idx, row in driver_df.iterrows():
            driver = _resolve_driver(season, row["Driver"])
            if not driver:
                continue

            # Preserve admin override if it already exists
            existing = DriverGPPointsDetail.objects.filter(
                season=season, driver=driver, gp=gp,
            ).first()
            admin_adj = existing.admin_adjustment if existing else 0
            admin_note = existing.admin_note if existing else ""

            detail, _ = DriverGPPointsDetail.objects.update_or_create(
                season=season, driver=driver, gp=gp,
                defaults={
                    "qualy_participation": _val(row, "Participation"),
                    "qualy_position": _val(row, "Reverse"),
                    "qualy_teammate": _val(row, "TeammateBonus"),
                    "qualy_dns_penalty": _val(row, "QualyDNSPenalty"),
                    "race_f1_points": _val(row, "RaceF1Pts"),
                    "race_positions_gained": _val(row, "RacePosGained"),
                    "race_teammate": _val(row, "RaceTeammate"),
                    "race_dnf_penalty": _val(row, "RaceDNF"),
                    "sprint_position_pts": _val(row, "SprintPosPts"),
                    "sprint_positions_gained": _val(row, "SprintPosGained"),
                    "sprint_teammate": _val(row, "SprintTeammate"),
                    "sprint_dnf_penalty": _val(row, "SprintDNF"),
                    "admin_adjustment": admin_adj,
                    "admin_note": admin_note,
                },
            )
            detail.compute_totals()
            detail.save()

            # Propagate final_total (includes admin_adjustment) to DataFrame
            driver_df.at[idx, "Total Points"] = detail.final_total
            logger.info(
                "DriverDetail: %s → auto=%d adj=%d final=%d",
                driver.name, detail.auto_total, detail.admin_adjustment,
                detail.final_total,
            )

        # ── Teams ──────────────────────────────────────────────────────
        for idx, row in team_df.iterrows():
            team = _resolve_team(season, row["Constructor"])
            if not team:
                continue

            existing = TeamGPPointsDetail.objects.filter(
                season=season, team=team, gp=gp,
            ).first()
            admin_adj = existing.admin_adjustment if existing else 0
            admin_note = existing.admin_note if existing else ""

            detail, _ = TeamGPPointsDetail.objects.update_or_create(
                season=season, team=team, gp=gp,
                defaults={
                    "qualy_driver_pts_sum": _val(row, "driver_q_pts"),
                    "qualy_team_bonus": _val(row, "TeamQualyBonus"),
                    "race_driver_pts_sum": _val(row, "TeamRacePoints"),
                    "sprint_driver_pts_sum": _val(row, "TeamSprintRacePoints"),
                    "admin_adjustment": admin_adj,
                    "admin_note": admin_note,
                },
            )
            detail.compute_totals()
            detail.save()

            team_df.at[idx, "Total Points"] = detail.final_total
            logger.info(
                "TeamDetail: %s → auto=%d adj=%d final=%d",
                team.name, detail.auto_total, detail.admin_adjustment,
                detail.final_total,
            )


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
# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

class PipelineResult:
    """Result summary of a pipeline run."""
    def __init__(self):
        self.success = False
        self.phase: str = "unknown"       # "qualy", "race", or "full"
        self.gp: Optional[GrandPrix] = None
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.steps_completed: list[str] = []

    def __str__(self):
        status = "SUCCESS" if self.success else "FAILED"
        return (
            f"Pipeline [{self.phase}] {status} for {self.gp}\n"
            f"  Steps: {', '.join(self.steps_completed)}\n"
            f"  Warnings: {len(self.warnings)}\n"
            f"  Errors: {len(self.errors)}"
        )


# ───────────────────────────────────────────────────────────────────────────
# Phase 1 — Qualifying pipeline
# ───────────────────────────────────────────────────────────────────────────

def run_qualy_pipeline(gp: GrandPrix, retry_count: int = 3,
                       retry_interval: int = 300) -> PipelineResult:
    """
    Post-qualifying pipeline.

    Steps:
        1. Fetch qualifying data from API (Jolpica → OpenF1 fallback)
        2. Create RaceResults record (poleman only)
        3. Compute qualifying-only driver & team fantasy points
        4. Save DriverPoints & TeamPoints (qualy portion)
        5. Compute partial porra points (poleman prediction + qualy fantasy)

    Args:
        retry_count: Number of fetch attempts before giving up.
        retry_interval: Seconds between retries (default 5 min).
    """
    result = PipelineResult()
    result.phase = "qualy"
    result.gp = gp
    season = gp.season

    if not season:
        result.errors.append("GP has no associated season.")
        return result
    nround = gp.nround
    if not nround:
        result.errors.append("GP has no round number.")
        return result

    # Step 1 — Fetch qualifying data
    logger.info("═══ QUALY Pipeline start: %s (round %d) ═══", gp, nround)
    qualy_data = None
    for attempt in range(1, retry_count + 1):
        qualy_data = fetch_qualy_data(season.year, nround)
        if qualy_data:
            break
        logger.warning("Qualy attempt %d/%d: No data yet, will retry in %ds...",
                        attempt, retry_count, retry_interval)
        if attempt < retry_count:
            _time.sleep(retry_interval)

    if not qualy_data:
        result.errors.append(
            f"No qualifying data available from any API after {retry_count} attempts. "
            "Qualifying results may not be published yet (rain/red flag delay?)."
        )
        return result
    result.steps_completed.append("1-fetch_qualy_data")

    # Step 2 — Create RaceResults (poleman only)
    try:
        create_qualy_race_results(season, gp, qualy_data)
        result.steps_completed.append("2-create_race_results_poleman")
    except Exception as exc:
        result.errors.append(f"Failed to create qualy RaceResults: {exc}")
        logger.exception("Qualy RaceResults creation failed")
        return result

    # Step 3+4 — Compute and save qualifying-only fantasy points
    try:
        driver_df, team_df = compute_qualy_fantasy_points(qualy_data)
        save_gp_points_detail(season, gp, driver_df, team_df)
        save_gp_points(season, gp, driver_df, team_df)
        result.steps_completed.append("3-compute_qualy_points")
        result.steps_completed.append("4-save_driver_team_points")
    except Exception as exc:
        result.errors.append(f"Failed to compute/save qualy fantasy points: {exc}")
        logger.exception("Qualy fantasy points computation failed")
        return result

    # Step 5 — Compute partial porra points
    try:
        compute_porra_points_for_gp(season, gp)
        result.steps_completed.append("5-compute_porra_points_partial")
    except Exception as exc:
        result.errors.append(f"Failed to compute qualy porra points: {exc}")
        logger.exception("Qualy porra points failed")
        return result

    result.success = True
    logger.info("═══ QUALY Pipeline complete: %s ═══\n%s", gp, result)
    return result


# ───────────────────────────────────────────────────────────────────────────
# Phase 2 — Race pipeline
# ───────────────────────────────────────────────────────────────────────────

def run_race_pipeline(gp: GrandPrix, retry_count: int = 3,
                      retry_interval: int = 300) -> PipelineResult:
    """
    Post-race pipeline.  Assumes the qualy pipeline has already run
    (RaceResults exists with poleman, DriverPoints/TeamPoints have qualy points).

    Steps:
        1. Fetch full GP data from API (qualy + race)
        2. Update existing RaceResults with race fields
        3. Compute FULL driver & team fantasy points (qualy + race combined)
        4. Update DriverPoints & TeamPoints with combined totals
        5. Recompute porra points (all predictions + full fantasy)
        6. Update prices for the next GP
        7. Recompute achievements

    Args:
        retry_count: Number of fetch attempts before giving up.
        retry_interval: Seconds between retries (default 5 min).
    """
    result = PipelineResult()
    result.phase = "race"
    result.gp = gp
    season = gp.season

    if not season:
        result.errors.append("GP has no associated season.")
        return result
    nround = gp.nround
    if not nround:
        result.errors.append("GP has no round number.")
        return result

    # Step 1 — Fetch full GP data (qualy + race)
    logger.info("═══ RACE Pipeline start: %s (round %d) ═══", gp, nround)
    gp_data = None
    for attempt in range(1, retry_count + 1):
        gp_data = fetch_gp_data(season.year, nround)
        if gp_data:
            break
        logger.warning("Race attempt %d/%d: No data yet, will retry in %ds...",
                        attempt, retry_count, retry_interval)
        if attempt < retry_count:
            _time.sleep(retry_interval)

    if not gp_data:
        result.errors.append(
            f"No race data available from any API after {retry_count} attempts. "
            "Race results may not be published yet (rain/red flag delay?)."
        )
        return result
    result.steps_completed.append("1-fetch_race_data")

    # Step 2 — Update RaceResults with race fields
    try:
        update_race_results(season, gp, gp_data)
        result.steps_completed.append("2-update_race_results")
    except Exception as exc:
        result.errors.append(f"Failed to update RaceResults: {exc}")
        logger.exception("Race RaceResults update failed")
        return result

    # Step 3+4 — Compute FULL fantasy points (qualy + race) and overwrite
    try:
        driver_df, team_df = compute_fantasy_points(gp_data)
        save_gp_points_detail(season, gp, driver_df, team_df)
        save_gp_points(season, gp, driver_df, team_df)
        result.steps_completed.append("3-compute_full_fantasy_points")
        result.steps_completed.append("4-save_driver_team_points")
    except Exception as exc:
        result.errors.append(f"Failed to compute/save full fantasy points: {exc}")
        logger.exception("Full fantasy points computation failed")
        return result

    # Step 5 — Recompute porra points (now with all prediction scores)
    try:
        compute_porra_points_for_gp(season, gp)
        result.steps_completed.append("5-recompute_porra_points")
    except Exception as exc:
        result.errors.append(f"Failed to recompute porra points: {exc}")
        logger.exception("Porra points recomputation failed")
        return result

    # Step 6 — Update prices for next GP
    try:
        update_points()
        result.steps_completed.append("6-update_next_gp_prices")
    except Exception as exc:
        result.warnings.append(f"Price update warning: {exc}")
        logger.warning("Price update issue (non-fatal): %s", exc)

    # Step 7 — Achievements
    try:
        recompute_achievements(rebuild=False)
        result.steps_completed.append("7-recompute_achievements")
    except Exception as exc:
        result.warnings.append(f"Achievement recompute warning: {exc}")
        logger.warning("Achievement recompute issue: %s", exc)

    result.success = True
    logger.info("═══ RACE Pipeline complete: %s ═══\n%s", gp, result)
    return result


# ───────────────────────────────────────────────────────────────────────────
# Legacy: Full pipeline (runs both phases sequentially)
# ───────────────────────────────────────────────────────────────────────────

def run_gp_pipeline(gp: GrandPrix, retry_count: int = 3) -> PipelineResult:
    """
    Run the full automated pipeline for a single Grand Prix.
    Legacy compatibility: runs qualy + race as a single combined pipeline.

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
    result.phase = "full"
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
            _time.sleep(60 * 5)  # wait 5 min between retries

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
        save_gp_points_detail(season, gp, driver_df, team_df)
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