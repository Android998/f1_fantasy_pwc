from django.contrib import admin
from .models import GrandPrix, Driver, Team, TeamPoints, DriverPoints, Porra, RaceResults


# Register your models here.
admin.site.register(GrandPrix)
admin.site.register(Driver)
admin.site.register(Team)
admin.site.register(TeamPoints)
admin.site.register(DriverPoints)
admin.site.register(RaceResults)
admin.site.register(Porra)