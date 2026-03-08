"""
Management command: process_gp_results
=======================================
Automatically processes GP results using the dual-trigger architecture:
qualifying phase after qualy, race phase after the race.

Usage:
    # One-shot: check and process any pending GP phases (qualy + race)
    python manage.py process_gp_results

    # Continuous: check every 30 minutes (default)
    python manage.py process_gp_results --watch

    # Custom interval (minutes) and delays (hours)
    python manage.py process_gp_results --watch --interval 15 --qualy-delay 3 --race-delay 5

    # Process a specific GP round (auto-detect phase)
    python manage.py process_gp_results --round 5

    # Force a specific phase for a round
    python manage.py process_gp_results --round 5 --phase qualy
    python manage.py process_gp_results --round 5 --phase race

    # Legacy mode: run old single-phase pipeline
    python manage.py process_gp_results --round 5 --phase full

    # Dry-run: show what would be processed
    python manage.py process_gp_results --dry-run
"""
import time
import logging

from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from f1porra_website.apps.public.models import Season, GrandPrix, RaceResults
from f1porra_website.apps.public.src.gp_scheduler import (
    process_pending_gps_dual, find_pending_qualy_gps, find_pending_race_gps,
)
from f1porra_website.apps.public.src.gp_pipeline import (
    run_gp_pipeline, run_qualy_pipeline, run_race_pipeline,
)

logger = logging.getLogger("process_gp_results")


class Command(BaseCommand):
    help = (
        "Automatically fetch race results from Jolpica/OpenF1 APIs, compute "
        "fantasy points, update user porras, and adjust prices for the next GP. "
        "Supports dual-trigger: runs qualy pipeline after qualifying, race pipeline after race."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--watch",
            action="store_true",
            help="Run continuously, checking for pending GPs at a fixed interval.",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=30,
            help="Check interval in minutes when using --watch (default: 30).",
        )
        parser.add_argument(
            "--qualy-delay",
            type=float,
            default=4.0,
            help="Hours to wait after qualy_date before processing qualifying (default: 4).",
        )
        parser.add_argument(
            "--race-delay",
            type=float,
            default=5.0,
            help="Hours to wait after gp_date before processing race (default: 5).",
        )
        parser.add_argument(
            "--round",
            type=int,
            default=None,
            help="Process a specific GP round number (overrides automatic detection).",
        )
        parser.add_argument(
            "--year",
            type=int,
            default=None,
            help="Season year (default: current year).",
        )
        parser.add_argument(
            "--phase",
            choices=["qualy", "race", "full", "auto"],
            default="auto",
            help=(
                "Which pipeline phase to run: "
                "'qualy' = qualifying only, 'race' = race only, "
                "'full' = legacy combined pipeline, "
                "'auto' = detect phase automatically (default)."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be processed without executing the pipeline.",
        )

    def handle(self, *args, **options):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        )

        year = options["year"] or timezone.now().year
        qualy_delay = timedelta(hours=options["qualy_delay"])
        race_delay = timedelta(hours=options["race_delay"])
        phase = options["phase"]

        # In watch mode, season is resolved inside the loop (handles year rollover).
        # For one-shot / specific round, resolve it now.
        season = None
        if not options["watch"]:
            try:
                season = Season.objects.get(year=year)
            except Season.DoesNotExist:
                self.stderr.write(self.style.ERROR(f"No season found for year {year}."))
                return

        # ── Specific round ─────────────────────────────────────────────
        if options["round"]:
            gp = GrandPrix.objects.filter(season=season, nround=options["round"]).first()
            if not gp:
                self.stderr.write(self.style.ERROR(
                    f"No GP found for season {year}, round {options['round']}."
                ))
                return

            if options["dry_run"]:
                detected = self._detect_phase(season, gp) if phase == "auto" else phase
                self.stdout.write(self.style.WARNING(
                    f"[DRY RUN] Would process: {gp.country} (round {gp.nround}) "
                    f"phase={detected}"
                ))
                return

            # Determine which phase to run
            if phase == "auto":
                phase = self._detect_phase(season, gp)

            self.stdout.write(self.style.SUCCESS(
                f"Processing GP: {gp.country} (round {gp.nround}) — phase: {phase}..."
            ))

            if phase == "qualy":
                result = run_qualy_pipeline(gp)
            elif phase == "race":
                result = run_race_pipeline(gp)
            else:  # "full"
                result = run_gp_pipeline(gp)

            self._print_result(result)
            return

        # ── Watch mode / one-shot ──────────────────────────────────────
        if options["watch"]:
            interval_sec = options["interval"] * 60
            self.stdout.write(self.style.SUCCESS(
                f"[GP Watcher] STARTED — checking every {options['interval']} min "
                f"(qualy delay: {options['qualy_delay']}h, "
                f"race delay: {options['race_delay']}h)"
            ))
            logger.info(
                "GP Results Watcher STARTED — interval=%d min, qualy_delay=%.1fh, race_delay=%.1fh, year=%s",
                options["interval"], options["qualy_delay"], options["race_delay"], year,
            )
            check_count = 0
            while True:
                check_count += 1
                try:
                    # Re-resolve season each iteration (handles year rollover / late creation)
                    current_year = options["year"] or timezone.now().year
                    try:
                        season = Season.objects.get(year=current_year)
                    except Season.DoesNotExist:
                        logger.warning("Watcher check #%d: No season for year %d, will retry next cycle.", check_count, current_year)
                        self.stdout.write(self.style.WARNING(
                            f"Watcher check #{check_count}: No season for year {current_year}. Retrying in {options['interval']} min..."
                        ))
                        time.sleep(interval_sec)
                        continue

                    logger.info("Watcher check #%d at %s (season %s)", check_count, timezone.now().isoformat(), season)
                    self._run_dual_check(season, qualy_delay, race_delay, options["dry_run"])

                except Exception:
                    logger.exception("Watcher check #%d crashed — will retry next cycle", check_count)

                self.stdout.write(f"Next check (#{check_count + 1}) in {options['interval']} minutes...")
                time.sleep(interval_sec)
        else:
            self._run_dual_check(season, qualy_delay, race_delay, options["dry_run"])

    def _detect_phase(self, season, gp) -> str:
        """Auto-detect which phase to run for a given GP."""
        try:
            rr = RaceResults.objects.get(season=season, gp=gp)
            if rr.first_pos is None:
                # RaceResults exists with poleman but no race data → race pending
                return "race"
            else:
                # Already fully processed → run race again (re-process)
                return "race"
        except RaceResults.DoesNotExist:
            # No RaceResults at all → qualy pending
            return "qualy"

    def _run_dual_check(self, season, qualy_delay, race_delay, dry_run):
        """Check for both qualy-pending and race-pending GPs."""
        qualy_pending = find_pending_qualy_gps(season, qualy_delay)
        race_pending = find_pending_race_gps(season, race_delay)

        if not qualy_pending and not race_pending:
            self.stdout.write("No pending GPs to process.")
            return

        # Process qualy-pending GPs
        for gp in qualy_pending:
            if dry_run:
                self.stdout.write(self.style.WARNING(
                    f"[DRY RUN] Would process QUALY: {gp.country} (round {gp.nround}, "
                    f"qualy_date: {gp.qualy_date})"
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"Processing QUALY: {gp.country} (round {gp.nround})..."
                ))
                result = run_qualy_pipeline(gp)
                self._print_result(result)

        # Process race-pending GPs
        for gp in race_pending:
            if dry_run:
                self.stdout.write(self.style.WARNING(
                    f"[DRY RUN] Would process RACE: {gp.country} (round {gp.nround}, "
                    f"gp_date: {gp.gp_date})"
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"Processing RACE: {gp.country} (round {gp.nround})..."
                ))
                result = run_race_pipeline(gp)
                self._print_result(result)

    def _print_result(self, result):
        if result.success:
            self.stdout.write(self.style.SUCCESS(f"  OK {result}"))
        else:
            self.stderr.write(self.style.ERROR(f"  FAIL {result}"))
            for err in result.errors:
                self.stderr.write(self.style.ERROR(f"    Error: {err}"))
        for warn in result.warnings:
            self.stdout.write(self.style.WARNING(f"    Warning: {warn}"))
