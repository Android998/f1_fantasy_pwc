from django.contrib import admin
from .models import GrandPrix, Driver, Team, TeamPoints, DriverPoints, Porra, RaceResults, Season


# Register your models here.
class GrandPrixAdmin(admin.ModelAdmin):
    list_display = ('country', 'nround', 'api_round', 'season', 'is_sprint', 'qualy_date', 'gp_date')
    list_editable = ('api_round',)
    list_filter = ('season',)
    ordering = ('season', 'nround')

admin.site.register(GrandPrix, GrandPrixAdmin)
admin.site.register(Driver)
admin.site.register(Team)
admin.site.register(TeamPoints)
admin.site.register(DriverPoints)
admin.site.register(RaceResults)
admin.site.register(Porra)
admin.site.register(Season)