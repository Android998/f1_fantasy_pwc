from django.core.management.base import BaseCommand
from f1porra_website.apps.public.src.upload_points import upload_points
from f1porra_website.apps.public.src.compute_points import compute_porra_points


class Command(BaseCommand):
    help = 'Computes points for each user\'s Porra for the latest Grand Prix'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('Uploading points from excel file...'))
        upload_points()
        self.stdout.write(self.style.SUCCESS('Points upload completed.'))


        self.stdout.write(self.style.SUCCESS('Computing Porras results...'))
        compute_porra_points()
        self.stdout.write(self.style.SUCCESS('Points calculation completed.'))
