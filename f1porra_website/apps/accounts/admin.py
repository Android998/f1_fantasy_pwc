# f1porra_website/apps/accounts/admin.py
from django.contrib import admin
from .models import UserProfile, UsersTeam

admin.site.register(UserProfile)
admin.site.register(UsersTeam)