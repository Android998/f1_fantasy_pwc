from django.core.management.base import BaseCommand

from f1porra_website.apps.public.services.achievement_service import recompute_achievements


class Command(BaseCommand):
    help = "Compute and backfill user achievements."

    def add_arguments(self, parser):
        parser.add_argument(
            "--rebuild",
            action="store_true",
            help="Clear existing user achievements before recomputing.",
        )

    def handle(self, *args, **options):
        rebuild = bool(options.get("rebuild"))
        recompute_achievements(rebuild=rebuild)
        self.stdout.write(self.style.SUCCESS("Achievements computed."))
