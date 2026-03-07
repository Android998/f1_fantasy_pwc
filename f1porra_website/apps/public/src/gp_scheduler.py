"""
GP Scheduler — Dual-Trigger Architecture
==========================================
Checks for Grand Prix weekends that need processing and triggers the
appropriate pipeline phase:

    • **Qualifying phase**: triggered ~3-4 h after ``qualy_date``
      (1 h for qualy to finish + 2-3 h for API data to appear)
    • **Race phase**: triggered ~4-5 h after ``gp_date``
      (2 h for race to finish + 2-3 h for API data to appear)

Detection logic:
    • Qualy pending: ``qualy_date + delay`` has passed AND no RaceResults exists yet
    • Race pending:  ``gp_date + delay`` has passed AND RaceResults exists with
      poleman but ``first_pos`` is NULL (qualy done, race not processed)

Two ways to run:
    1. ``python manage.py process_gp_results``          — one-shot check
    2. ``python manage.py process_gp_results --watch``  — continuous loop
"""
import logging
from datetime import timedelta
from enum import Enum

from django.utils import timezone
from django.db.models import Q

from f1porra_website.apps.public.models import (
    Season, GrandPrix, DriverPoints, RaceResults,
)
from f1porra_website.apps.public.src.gp_pipeline import (
    run_gp_pipeline, run_qualy_pipeline, run_race_pipeline, PipelineResult,
)

logger = logging.getLogger("gp_scheduler")

# Delays: how long after the session time to wait for API data.
# Qualy: ~1 h session + 2-3 h API publication = ~3-4 h after qualy_date
# Race:  ~2 h session + 2-3 h API publication = ~4-5 h after gp_date
QUALY_DELAY = timedelta(hours=4)
RACE_DELAY = timedelta(hours=5)

# Legacy default (used by old find_pending_gps signature)
DEFAULT_DELAY = timedelta(hours=3)

# Maximum age: ignore GPs older than this (prevents processing ancient ones)
MAX_AGE = timedelta(days=7)


class PendingPhase(Enum):
    QUALY = "qualy"
    RACE = "race"


def find_pending_qualy_gps(season: Season,
                           delay: timedelta = QUALY_DELAY) -> list[GrandPrix]:
    """
    Return GPs whose ``qualy_date + delay`` is in the past and that have
    no RaceResults record yet (qualy pipeline hasn't run).
    """
    now = timezone.now()
    cutoff = now - delay
    oldest = now - MAX_AGE

    gps_with_results = RaceResults.objects.filter(
        season=season,
    ).values_list("gp_id", flat=True)

    pending = (
        GrandPrix.objects
        .filter(season=season)
        .filter(qualy_date__isnull=False)
        .filter(qualy_date__lte=cutoff)
        .filter(qualy_date__gte=oldest)
        .exclude(id__in=gps_with_results)
        .order_by("nround")
    )
    return list(pending)


def find_pending_race_gps(season: Season,
                          delay: timedelta = RACE_DELAY) -> list[GrandPrix]:
    """
    Return GPs whose ``gp_date + delay`` is in the past and that have
    a RaceResults record with poleman set but first_pos still NULL
    (qualy pipeline ran, race pipeline hasn't).
    """
    now = timezone.now()
    cutoff = now - delay
    oldest = now - MAX_AGE

    # GPs that have RaceResults WITH poleman but WITHOUT first_pos
    qualy_done_race_pending = RaceResults.objects.filter(
        season=season,
        poleman__isnull=False,
        first_pos__isnull=True,
    ).values_list("gp_id", flat=True)

    pending = (
        GrandPrix.objects
        .filter(season=season)
        .filter(gp_date__isnull=False)
        .filter(gp_date__lte=cutoff)
        .filter(gp_date__gte=oldest)
        .filter(id__in=qualy_done_race_pending)
        .order_by("nround")
    )
    return list(pending)


def find_pending_gps(season: Season,
                     delay: timedelta = DEFAULT_DELAY) -> list[GrandPrix]:
    """
    Legacy: Return GPs whose ``gp_date + delay`` is in the past and that
    have no RaceResults record yet (i.e., haven't been processed at all).
    Used by the legacy single-phase pipeline.
    """
    now = timezone.now()
    cutoff = now - delay
    oldest = now - MAX_AGE

    gps_with_results = RaceResults.objects.filter(
        season=season,
    ).values_list("gp_id", flat=True)

    pending = (
        GrandPrix.objects
        .filter(season=season)
        .filter(gp_date__isnull=False)
        .filter(gp_date__lte=cutoff)
        .filter(gp_date__gte=oldest)
        .exclude(id__in=gps_with_results)
        .order_by("nround")
    )
    return list(pending)


def process_pending_gps_dual(
    season: Season = None,
    qualy_delay: timedelta = QUALY_DELAY,
    race_delay: timedelta = RACE_DELAY,
) -> list[PipelineResult]:
    """
    Find and process all pending GP phases (qualy + race) for a season.

    Checks both qualifying-pending and race-pending GPs and runs the
    appropriate pipeline for each.

    Returns a list of PipelineResult objects.
    """
    if season is None:
        year = timezone.now().year
        try:
            season = Season.objects.get(year=year)
        except Season.DoesNotExist:
            logger.error("No season found for year %d", year)
            return []

    results = []

    # Phase 1: qualifying-pending GPs
    qualy_pending = find_pending_qualy_gps(season, qualy_delay)
    for gp in qualy_pending:
        logger.info("Running QUALY pipeline for: %s (round %s)", gp, gp.nround)
        result = run_qualy_pipeline(gp)
        results.append(result)
        if not result.success:
            logger.error("Qualy pipeline failed for %s: %s", gp, result.errors)
        else:
            logger.info("Qualy pipeline succeeded for %s", gp)

    # Phase 2: race-pending GPs
    race_pending = find_pending_race_gps(season, race_delay)
    for gp in race_pending:
        logger.info("Running RACE pipeline for: %s (round %s)", gp, gp.nround)
        result = run_race_pipeline(gp)
        results.append(result)
        if not result.success:
            logger.error("Race pipeline failed for %s: %s", gp, result.errors)
        else:
            logger.info("Race pipeline succeeded for %s", gp)

    if not results:
        logger.info("No pending GPs to process for season %s.", season)

    return results


def process_pending_gps(season: Season = None,
                        delay: timedelta = DEFAULT_DELAY) -> list[PipelineResult]:
    """
    Legacy: Find and process all pending GPs using the single combined pipeline.
    """
    if season is None:
        year = timezone.now().year
        try:
            season = Season.objects.get(year=year)
        except Season.DoesNotExist:
            logger.error("No season found for year %d", year)
            return []

    pending = find_pending_gps(season, delay)
    if not pending:
        logger.info("No pending GPs to process for season %s.", season)
        return []

    results = []
    for gp in pending:
        logger.info("Processing pending GP: %s (round %s)", gp, gp.nround)
        result = run_gp_pipeline(gp)
        results.append(result)

        if not result.success:
            logger.error("Pipeline failed for %s: %s", gp, result.errors)
        else:
            logger.info("Pipeline succeeded for %s", gp)

    return results
