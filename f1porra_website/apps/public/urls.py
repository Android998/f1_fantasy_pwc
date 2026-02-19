from django.contrib import admin
from django.urls import path

from . import views

app_name = "public"
urlpatterns = [
    path('', views.home, name="home"),
    path('calendar/', views.calendar_view, name="calendar"),
    path('prices/', views.prices, name="prices"),
    path('rules/', views.rules, name="rules"),
    path('standings/', views.standings, name="standings"),
    path('statistics/', views.statistics, name="statistics"),
    path('statistics/users/', views.statistics_users, name="statistics_users"),
    path('statistics/assets/', views.statistics_assets, name="statistics_assets"),
    path('statistics/optimal-team/', views.statistics_optimal_team, name="statistics_optimal_team"),
    path('statistics/api/matrix/', views.statistics_matrix_api, name="statistics_matrix_api"),
    path('statistics/api/trends/', views.statistics_trends_api, name="statistics_trends_api"),
    path('statistics/api/assets/matrix/', views.statistics_assets_matrix_api, name="statistics_assets_matrix_api"),
    path('statistics/api/assets/trends/', views.statistics_assets_trends_api, name="statistics_assets_trends_api"),
    path('team/', views.team, name="team"),
    path('view_team/<str:username>/<str:gp>/', views.view_team, name='view_team'),
]
