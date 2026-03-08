"""
F1 Data API Client
===================
Primary:   Jolpica (Ergast successor) — rich, structured, 1-2 calls per session
Fallback:  OpenF1 — faster availability (~30 min), used when Jolpica has no data yet

Jolpica delivers qualifying Q1/Q2/Q3 times, race results with positions/points/
status/fastest-lap/constructor all in one payload.  Data typically appears within
a few hours of the session ending.

OpenF1 delivers session_result data within ~30 min but requires extra calls to
resolve driver-to-constructor mappings and fastest lap.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import requests

logger = logging.getLogger("f1_api_client")


# ---------------------------------------------------------------------------
# Helpers — safe type conversions for API data that may contain None
# ---------------------------------------------------------------------------

def _safe_int(value, default: int = 0) -> int:
    """Convert value to int, returning *default* when value is None or invalid."""
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _safe_float(value, default: float = 0.0) -> float:
    """Convert value to float, returning *default* when value is None or invalid."""
    if value is None:
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class QualifyingResult:
    position: int
    driver_name: str          # "GivenName FamilyName"
    constructor_name: str
    q1_time: Optional[str]    # e.g. "1:29.179" or None
    q2_time: Optional[str]
    q3_time: Optional[str]


@dataclass
class RaceResultEntry:
    position: int
    driver_name: str
    constructor_name: str
    grid: int
    points: float
    status: str               # "Finished", "Retired", "Collision", …
    fastest_lap_rank: Optional[int]   # 1 = holder of the fastest lap
    laps: int


@dataclass
class GPSessionData:
    """All the data we need from a single GP weekend."""
    season: int
    round_number: int
    gp_name: str
    qualifying: list[QualifyingResult] = field(default_factory=list)
    race: list[RaceResultEntry] = field(default_factory=list)
    # Sprint sessions (empty on non-sprint weekends)
    sprint_qualifying: list[QualifyingResult] = field(default_factory=list)
    sprint_race: list[RaceResultEntry] = field(default_factory=list)
    sprint_winner: Optional[str] = None           # driver name
    # Key results
    pole_sitter: Optional[str] = None            # driver name
    race_winner: Optional[str] = None             # driver name
    second_place: Optional[str] = None
    third_place: Optional[str] = None
    fastest_lap_driver: Optional[str] = None      # driver name
    winning_constructor: Optional[str] = None     # constructor name


# ---------------------------------------------------------------------------
# Jolpica client  (primary)
# ---------------------------------------------------------------------------

JOLPICA_BASE = "https://api.jolpi.ca/ergast/f1"
REQUEST_TIMEOUT = 30  # seconds


def _jolpica_get(path: str) -> Optional[dict]:
    """GET helper with basic retry (respects 4 req/s rate limit)."""
    url = f"{JOLPICA_BASE}/{path}"
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            logger.warning("Jolpica %s returned %s (attempt %d)", url, resp.status_code, attempt + 1)
        except requests.RequestException as exc:
            logger.warning("Jolpica request failed: %s (attempt %d)", exc, attempt + 1)
        time.sleep(1.5)
    return None


def fetch_qualifying_jolpica(season: int, round_number: int) -> list[QualifyingResult]:
    """Fetch qualifying results from Jolpica."""
    data = _jolpica_get(f"{season}/{round_number}/qualifying.json?limit=100")
    if not data:
        return []

    races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    if not races:
        return []

    results = []
    for r in races[0].get("QualifyingResults", []):
        driver = r.get("Driver", {})
        name = f"{driver.get('givenName', '')} {driver.get('familyName', '')}".strip()
        constructor = r.get("Constructor", {}).get("name", "")
        results.append(QualifyingResult(
            position=_safe_int(r.get("position")),
            driver_name=name,
            constructor_name=constructor,
            q1_time=r.get("Q1"),
            q2_time=r.get("Q2"),
            q3_time=r.get("Q3"),
        ))
    return results


def fetch_race_results_jolpica(season: int, round_number: int) -> list[RaceResultEntry]:
    """Fetch race results from Jolpica — includes fastest lap, status, constructor."""
    data = _jolpica_get(f"{season}/{round_number}/results.json?limit=100")
    if not data:
        return []

    races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    if not races:
        return []

    results = []
    for r in races[0].get("Results", []):
        driver = r.get("Driver", {})
        name = f"{driver.get('givenName', '')} {driver.get('familyName', '')}".strip()
        constructor = r.get("Constructor", {}).get("name", "")
        fl = r.get("FastestLap", {})
        fl_rank = _safe_int(fl.get("rank")) if fl.get("rank") else None
        results.append(RaceResultEntry(
            position=_safe_int(r.get("position")),
            driver_name=name,
            constructor_name=constructor,
            grid=_safe_int(r.get("grid")),
            points=_safe_float(r.get("points")),
            status=r.get("status", "Unknown"),
            fastest_lap_rank=fl_rank,
            laps=_safe_int(r.get("laps")),
        ))
    return results


def fetch_sprint_results_jolpica(season: int, round_number: int) -> list[RaceResultEntry]:
    """Fetch sprint race results from Jolpica. Returns empty list on non-sprint weekends."""
    data = _jolpica_get(f"{season}/{round_number}/sprint.json?limit=100")
    if not data:
        return []

    races = data.get("MRData", {}).get("RaceTable", {}).get("Races", [])
    if not races:
        return []

    results = []
    for r in races[0].get("SprintResults", []):
        driver = r.get("Driver", {})
        name = f"{driver.get('givenName', '')} {driver.get('familyName', '')}".strip()
        constructor = r.get("Constructor", {}).get("name", "")
        fl = r.get("FastestLap", {})
        fl_rank = _safe_int(fl.get("rank")) if fl.get("rank") else None
        results.append(RaceResultEntry(
            position=_safe_int(r.get("position")),
            driver_name=name,
            constructor_name=constructor,
            grid=_safe_int(r.get("grid")),
            points=_safe_float(r.get("points")),
            status=r.get("status", "Unknown"),
            fastest_lap_rank=fl_rank,
            laps=_safe_int(r.get("laps")),
        ))
    return results


def fetch_sprint_results_openf1(season: int, round_number: int) -> list[RaceResultEntry]:
    """Fetch sprint race results from OpenF1. Returns empty list on non-sprint weekends."""
    sprint_key = _openf1_find_session_key(season, round_number, "Sprint")
    if not sprint_key:
        return []

    drivers_map = _openf1_get_drivers_map(sprint_key)
    results_raw = _openf1_get(f"session_result?session_key={sprint_key}")
    if not results_raw or not isinstance(results_raw, list):
        return []

    results = []
    for r in results_raw:
        num = r.get("driver_number")
        name, constructor = drivers_map.get(num, ("Unknown", "Unknown"))
        results.append(RaceResultEntry(
            position=_safe_int(r.get("position")),
            driver_name=name,
            constructor_name=constructor,
            grid=0,
            points=_safe_float(r.get("points")),
            status="DNF" if r.get("dnf") else ("DNS" if r.get("dns") else "Finished"),
            fastest_lap_rank=None,
            laps=_safe_int(r.get("number_of_laps")),
        ))
    return results


def fetch_gp_data_jolpica(season: int, round_number: int) -> Optional[GPSessionData]:
    """
    Fetch complete GP data from Jolpica.
    Returns None if race data is not yet available.
    Also attempts to fetch sprint data (returns empty lists on non-sprint weekends).
    """
    qualifying = fetch_qualifying_jolpica(season, round_number)
    race = fetch_race_results_jolpica(season, round_number)
    sprint_race = fetch_sprint_results_jolpica(season, round_number)

    if not race:
        logger.info("No race data from Jolpica for %s round %s", season, round_number)
        return None

    gp_data = GPSessionData(
        season=season,
        round_number=round_number,
        gp_name=f"Round {round_number}",
        qualifying=qualifying,
        race=race,
        sprint_race=sprint_race,
    )

    # Derive key results
    if qualifying:
        gp_data.pole_sitter = qualifying[0].driver_name

    if race:
        sorted_race = sorted(race, key=lambda r: r.position)
        if len(sorted_race) >= 1:
            gp_data.race_winner = sorted_race[0].driver_name
            gp_data.winning_constructor = sorted_race[0].constructor_name
        if len(sorted_race) >= 2:
            gp_data.second_place = sorted_race[1].driver_name
        if len(sorted_race) >= 3:
            gp_data.third_place = sorted_race[2].driver_name

        fl_drivers = [r for r in race if r.fastest_lap_rank == 1]
        if fl_drivers:
            gp_data.fastest_lap_driver = fl_drivers[0].driver_name

    # Sprint winner
    if sprint_race:
        sorted_sprint = sorted(sprint_race, key=lambda r: r.position)
        gp_data.sprint_winner = sorted_sprint[0].driver_name

    return gp_data


# ---------------------------------------------------------------------------
# OpenF1 client  (fallback)
# ---------------------------------------------------------------------------

OPENF1_BASE = "https://api.openf1.org/v1"


def _openf1_get(path: str) -> Optional[list | dict]:
    """GET helper for OpenF1."""
    url = f"{OPENF1_BASE}/{path}"
    for attempt in range(3):
        try:
            resp = requests.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            logger.warning("OpenF1 %s returned %s (attempt %d)", url, resp.status_code, attempt + 1)
        except requests.RequestException as exc:
            logger.warning("OpenF1 request failed: %s (attempt %d)", exc, attempt + 1)
        time.sleep(1.5)
    return None


def _openf1_find_session_key(season: int, round_number: int, session_type: str) -> Optional[int]:
    """Find an OpenF1 session_key for a given meeting + session type."""
    # First, find the meeting
    meetings = _openf1_get(f"meetings?year={season}")
    if not meetings or not isinstance(meetings, list):
        return None

    # Meetings are returned in order; match by round number (meeting_key order)
    if round_number < 1 or round_number > len(meetings):
        return None

    meeting_key = meetings[round_number - 1].get("meeting_key")
    if not meeting_key:
        return None

    # Now find the session
    sessions = _openf1_get(f"sessions?meeting_key={meeting_key}&session_type={session_type}")
    if not sessions or not isinstance(sessions, list):
        return None

    return sessions[0].get("session_key")


def _openf1_get_drivers_map(session_key: int) -> dict[int, tuple[str, str]]:
    """Map driver_number → (full_name, team_name)."""
    drivers = _openf1_get(f"drivers?session_key={session_key}")
    if not drivers or not isinstance(drivers, list):
        return {}

    mapping = {}
    for d in drivers:
        num = d.get("driver_number")
        full_name = d.get("full_name", "Unknown")
        team = d.get("team_name", "Unknown")
        if num:
            mapping[num] = (full_name, team)
    return mapping


def fetch_gp_data_openf1(season: int, round_number: int) -> Optional[GPSessionData]:
    """
    Fetch GP data from OpenF1 as fallback.
    More API calls needed, but data available ~30 min after session.
    """
    race_key = _openf1_find_session_key(season, round_number, "Race")
    if not race_key:
        logger.info("No OpenF1 race session key for %s round %s", season, round_number)
        return None

    quali_key = _openf1_find_session_key(season, round_number, "Qualifying")
    drivers_map = _openf1_get_drivers_map(race_key)

    # Race results
    race_results_raw = _openf1_get(f"session_result?session_key={race_key}")
    if not race_results_raw or not isinstance(race_results_raw, list):
        return None

    race = []
    for r in race_results_raw:
        num = r.get("driver_number")
        name, constructor = drivers_map.get(num, ("Unknown", "Unknown"))
        race.append(RaceResultEntry(
            position=_safe_int(r.get("position")),
            driver_name=name,
            constructor_name=constructor,
            grid=0,  # not directly in session_result; would need starting_grid call
            points=_safe_float(r.get("points")),
            status="DNF" if r.get("dnf") else ("DNS" if r.get("dns") else "Finished"),
            fastest_lap_rank=None,  # would need laps endpoint
            laps=_safe_int(r.get("number_of_laps")),
        ))

    # Qualifying results
    qualifying = []
    if quali_key:
        quali_results_raw = _openf1_get(f"session_result?session_key={quali_key}")
        quali_drivers_map = _openf1_get_drivers_map(quali_key)
        if quali_results_raw and isinstance(quali_results_raw, list):
            for r in quali_results_raw:
                num = r.get("driver_number")
                name, constructor = quali_drivers_map.get(num, ("Unknown", "Unknown"))
                durations = r.get("duration", [])
                qualifying.append(QualifyingResult(
                    position=_safe_int(r.get("position")),
                    driver_name=name,
                    constructor_name=constructor,
                    q1_time=str(durations[0]) if len(durations) > 0 and durations[0] else None,
                    q2_time=str(durations[1]) if len(durations) > 1 and durations[1] else None,
                    q3_time=str(durations[2]) if len(durations) > 2 and durations[2] else None,
                ))

    # Find fastest lap from laps endpoint
    fastest_lap_driver = None
    laps_data = _openf1_get(f"laps?session_key={race_key}")
    if laps_data and isinstance(laps_data, list):
        valid_laps = [l for l in laps_data if l.get("lap_duration") is not None]
        if valid_laps:
            fastest = min(valid_laps, key=lambda l: l["lap_duration"])
            fl_num = fastest.get("driver_number")
            if fl_num in drivers_map:
                fastest_lap_driver = drivers_map[fl_num][0]

    # Also fetch sprint data
    sprint_race = fetch_sprint_results_openf1(season, round_number)

    gp_data = GPSessionData(
        season=season,
        round_number=round_number,
        gp_name=f"Round {round_number}",
        qualifying=qualifying,
        race=race,
        sprint_race=sprint_race,
    )

    if qualifying:
        sorted_q = sorted(qualifying, key=lambda q: q.position)
        gp_data.pole_sitter = sorted_q[0].driver_name

    if race:
        sorted_race = sorted(race, key=lambda r: r.position)
        if len(sorted_race) >= 1:
            gp_data.race_winner = sorted_race[0].driver_name
            gp_data.winning_constructor = sorted_race[0].constructor_name
        if len(sorted_race) >= 2:
            gp_data.second_place = sorted_race[1].driver_name
        if len(sorted_race) >= 3:
            gp_data.third_place = sorted_race[2].driver_name

    if sprint_race:
        sorted_sprint = sorted(sprint_race, key=lambda r: r.position)
        gp_data.sprint_winner = sorted_sprint[0].driver_name

    gp_data.fastest_lap_driver = fastest_lap_driver

    return gp_data


# ---------------------------------------------------------------------------
# Qualifying-only fetchers  (used by the qualy pipeline trigger)
# ---------------------------------------------------------------------------

def fetch_qualy_data_jolpica(season: int, round_number: int) -> Optional[GPSessionData]:
    """
    Fetch qualifying-only data from Jolpica.
    Also attempts to fetch sprint race data (available on sprint weekends).
    Returns GPSessionData with qualifying + sprint lists and pole_sitter, but NO race data.
    Returns None if qualifying data is not yet available.
    """
    qualifying = fetch_qualifying_jolpica(season, round_number)
    if not qualifying:
        logger.info("No qualifying data from Jolpica for %s round %s", season, round_number)
        return None

    # Also try to fetch sprint data (non-sprint weekends return empty list)
    sprint_race = fetch_sprint_results_jolpica(season, round_number)

    gp_data = GPSessionData(
        season=season,
        round_number=round_number,
        gp_name=f"Round {round_number}",
        qualifying=qualifying,
        race=[],  # no race data yet
        sprint_race=sprint_race,
    )
    gp_data.pole_sitter = qualifying[0].driver_name

    if sprint_race:
        sorted_sprint = sorted(sprint_race, key=lambda r: r.position)
        gp_data.sprint_winner = sorted_sprint[0].driver_name

    return gp_data


def fetch_qualy_data_openf1(season: int, round_number: int) -> Optional[GPSessionData]:
    """
    Fetch qualifying-only data from OpenF1 as fallback.
    Also attempts to fetch sprint race data.
    Returns GPSessionData with qualifying list and pole_sitter, but NO race data.
    """
    quali_key = _openf1_find_session_key(season, round_number, "Qualifying")
    if not quali_key:
        logger.info("No OpenF1 qualifying session key for %s round %s", season, round_number)
        return None

    quali_drivers_map = _openf1_get_drivers_map(quali_key)
    quali_results_raw = _openf1_get(f"session_result?session_key={quali_key}")
    if not quali_results_raw or not isinstance(quali_results_raw, list):
        return None

    qualifying = []
    for r in quali_results_raw:
        num = r.get("driver_number")
        name, constructor = quali_drivers_map.get(num, ("Unknown", "Unknown"))
        durations = r.get("duration", [])
        qualifying.append(QualifyingResult(
            position=_safe_int(r.get("position")),
            driver_name=name,
            constructor_name=constructor,
            q1_time=str(durations[0]) if len(durations) > 0 and durations[0] else None,
            q2_time=str(durations[1]) if len(durations) > 1 and durations[1] else None,
            q3_time=str(durations[2]) if len(durations) > 2 and durations[2] else None,
        ))

    if not qualifying:
        return None

    # Also try to fetch sprint data
    sprint_race = fetch_sprint_results_openf1(season, round_number)

    gp_data = GPSessionData(
        season=season,
        round_number=round_number,
        gp_name=f"Round {round_number}",
        qualifying=qualifying,
        race=[],
        sprint_race=sprint_race,
    )
    sorted_q = sorted(qualifying, key=lambda q: q.position)
    gp_data.pole_sitter = sorted_q[0].driver_name

    if sprint_race:
        sorted_sprint = sorted(sprint_race, key=lambda r: r.position)
        gp_data.sprint_winner = sorted_sprint[0].driver_name

    return gp_data


def fetch_qualy_data(season: int, round_number: int) -> Optional[GPSessionData]:
    """
    Fetch qualifying-only data.  Jolpica first, OpenF1 fallback.
    Returns GPSessionData with qualifying + pole_sitter but no race data.
    Returns None if neither API has qualifying data yet.
    """
    logger.info("Fetching QUALY data for %s round %s from Jolpica...", season, round_number)
    data = fetch_qualy_data_jolpica(season, round_number)
    if data:
        logger.info("Successfully fetched qualy from Jolpica.")
        return data

    logger.info("Jolpica qualy unavailable, trying OpenF1...")
    data = fetch_qualy_data_openf1(season, round_number)
    if data:
        logger.info("Successfully fetched qualy from OpenF1.")
        return data

    logger.warning("No qualifying data from either API for %s round %s.", season, round_number)
    return None


# ---------------------------------------------------------------------------
# Unified fetcher with fallback
# ---------------------------------------------------------------------------

def fetch_gp_data(season: int, round_number: int) -> Optional[GPSessionData]:
    """
    Try Jolpica first (richer data). Fall back to OpenF1 if unavailable.
    Returns None if neither API has data yet.
    """
    logger.info("Fetching GP data for %s round %s from Jolpica...", season, round_number)
    data = fetch_gp_data_jolpica(season, round_number)
    if data:
        logger.info("Successfully fetched from Jolpica.")
        return data

    logger.info("Jolpica unavailable, trying OpenF1...")
    data = fetch_gp_data_openf1(season, round_number)
    if data:
        logger.info("Successfully fetched from OpenF1.")
        return data

    logger.warning("No data available from either API for %s round %s.", season, round_number)
    return None
