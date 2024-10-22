from django.core.management.base import BaseCommand
from f1porra_website.apps.public.src.compute_points import compute_porra_points
from f1porra_website.apps.public.src.actualizar_precios import update_points


class Command(BaseCommand):
    help = 'Computes points for each user\'s Porra for the latest Grand Prix'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('Starting points calculation...'))
        compute_porra_points()
        self.stdout.write(self.style.SUCCESS('Points calculation completed.'))

        self.stdout.write(self.style.SUCCESS('\nStarting price update...'))
        update_points()
        self.stdout.write(self.style.SUCCESS('Driver and Team updtaes completed.'))
