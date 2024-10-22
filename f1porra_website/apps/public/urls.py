from django.contrib import admin
from django.urls import path

from . import views

app_name = "public"
urlpatterns = [
    path('', views.home, name="home"),
    path('prices/', views.prices, name="prices"),
    path('rules/', views.rules, name="rules"),
    path('standings/', views.standings, name="standings"),
    path('statistics/', views.statistics, name="statistics"),
    path('team/', views.team, name="team"),
    path('view_team/<str:username>/<str:gp>/', views.view_team, name='view_team'),
]