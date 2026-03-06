"""
Management command: process_gp_results
=======================================
Automatically processes GP results when ``gp_end_date`` has passed.

Usage:
    # One-shot: check and process any pending GPs now
    python manage.py process_gp_results

    # Continuous: check every 30 minutes (default)
    python manage.py process_gp_results --watch

    # Custom interval (minutes) and delay (hours after gp_end_date)
    python manage.py process_gp_results --watch --interval 15 --delay 2

    # Process a specific GP round (overrides automatic detection)
    python manage.py process_gp_results --round 5

    # Dry-run: show what would be processed without actually doing it
    python manage.py process_gp_results --dry-run
"""
import time
import logging

from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone

from f1porra_website.apps.public.models import Season, GrandPrix
from f1porra_website.apps.public.src.gp_scheduler import process_pending_gps, find_pending_gps
from f1porra_website.apps.public.src.gp_pipeline import run_gp_pipeline

logger = logging.getLogger("process_gp_results")


class Command(BaseCommand):
    help = (
        "Automatically fetch race results from Jolpica/OpenF1 APIs, compute "
        "fantasy points, update user porras, and adjust prices for the next GP. "
        "Triggered by gp_end_date."
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
            "--delay",
            type=float,
            default=3.0,
            help="Hours to wait after gp_end_date before processing (default: 3).",
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
        delay = timedelta(hours=options["delay"])

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
                self.stdout.write(self.style.WARNING(
                    f"[DRY RUN] Would process: {gp.country} (round {gp.nround})"
                ))
                return

            self.stdout.write(self.style.SUCCESS(
                f"Processing GP: {gp.country} (round {gp.nround})..."
            ))
            result = run_gp_pipeline(gp)
            self._print_result(result)
            return

        # ── Watch mode ─────────────────────────────────────────────────
        if options["watch"]:
            interval_sec = options["interval"] * 60
            self.stdout.write(self.style.SUCCESS(
                f"Watching for pending GPs every {options['interval']} min "
                f"(delay: {options['delay']}h after gp_end_date)..."
            ))
            while True:
                self._run_check(season, delay, options["dry_run"])
                self.stdout.write(f"Next check in {options['interval']} minutes...")
                time.sleep(interval_sec)
        else:
            # ── One-shot ───────────────────────────────────────────────
            self._run_check(season, delay, options["dry_run"])

    def _run_check(self, season, delay, dry_run):
        pending = find_pending_gps(season, delay)
        if not pending:
            self.stdout.write("No pending GPs to process.")
            return

        for gp in pending:
            if dry_run:
                self.stdout.write(self.style.WARNING(
                    f"[DRY RUN] Would process: {gp.country} (round {gp.nround}, "
                    f"end_date: {gp.gp_end_date})"
                ))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"Processing: {gp.country} (round {gp.nround})..."
                ))
                result = run_gp_pipeline(gp)
                self._print_result(result)

    def _print_result(self, result):
        if result.success:
            self.stdout.write(self.style.SUCCESS(f"  ✓ {result}"))
        else:
            self.stderr.write(self.style.ERROR(f"  ✗ {result}"))
            for err in result.errors:
                self.stderr.write(self.style.ERROR(f"    Error: {err}"))
        for warn in result.warnings:
            self.stdout.write(self.style.WARNING(f"    Warning: {warn}"))
