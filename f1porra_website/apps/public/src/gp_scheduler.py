"""
GP Scheduler
=============
Checks for Grand Prix races whose ``gp_end_date`` has passed and whose points
have not yet been computed, then triggers the automated pipeline.

Two ways to run:
    1. ``python manage.py process_gp_results``          — one-shot check
    2. ``python manage.py process_gp_results --watch``  — continuous loop (every N minutes)
"""
import logging
from datetime import timedelta

from django.utils import timezone
from django.db.models import Q

from f1porra_website.apps.public.models import (
    Season, GrandPrix, DriverPoints, RaceResults,
)
from f1porra_website.apps.public.src.gp_pipeline import run_gp_pipeline, PipelineResult

logger = logging.getLogger("gp_scheduler")

# How long after gp_end_date to wait before fetching data (gives APIs time to
# publish results).  Jolpica typically needs 2-4 h; OpenF1 ~30 min.
DEFAULT_DELAY = timedelta(hours=3)

# Maximum age: ignore GPs older than this (prevents processing ancient ones)
MAX_AGE = timedelta(days=7)


def find_pending_gps(season: Season, delay: timedelta = DEFAULT_DELAY) -> list[GrandPrix]:
    """
    Return GPs whose ``gp_end_date + delay`` is in the past and that have no
    RaceResults record yet (i.e., haven't been processed).
    """
    now = timezone.now()
    cutoff = now - delay
    oldest = now - MAX_AGE

    gps_with_results = RaceResults.objects.filter(season=season).values_list("gp_id", flat=True)

    pending = (
        GrandPrix.objects
        .filter(season=season)
        .filter(gp_end_date__isnull=False)
        .filter(gp_end_date__lte=cutoff)        # end_date + delay has passed
        .filter(gp_end_date__gte=oldest)         # not too old
        .exclude(id__in=gps_with_results)        # no RaceResults yet
        .order_by("nround")
    )
    return list(pending)


def process_pending_gps(season: Season = None, delay: timedelta = DEFAULT_DELAY) -> list[PipelineResult]:
    """
    Find and process all pending GPs for a season.
    Returns a list of PipelineResult objects.
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
