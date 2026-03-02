from django.urls import path
from django.contrib import admin
from django.contrib.auth import views as auth_views

from . import views

app_name = "accounts"
urlpatterns = [
    #Django Auth Staff    
    path('admin/', admin.site.urls),
    path('login/', views.user_login, name='login'),
    path("logout", auth_views.LogoutView.as_view(), name="logout"),
    path('profile/', views.ProfileView.as_view(), name='profile'),
    path('api/search-teams/', views.search_teams, name='search_teams'),

    # Password reset
    path('password_reset/', views.password_reset, name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='accounts/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='accounts/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='accounts/password_reset_complete.html'), name='password_reset_complete'),
]