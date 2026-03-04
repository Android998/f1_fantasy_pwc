"""
URL configuration for f1porra_website project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include, re_path
from django.views.static import serve
import os

# Security: Use environment variable for admin URL
ADMIN_URL = os.getenv('DJANGO_ADMIN_URL', 'admin/')

urlpatterns = [
    path(ADMIN_URL, admin.site.urls),  # Use custom admin URL
    path('', include("f1porra_website.apps.public.urls")),
    path('accounts/', include("f1porra_website.apps.accounts.urls")),
]

# Serve media files
# In DEBUG mode: use Django's static helper for local development
# In production with Azure Blob Storage: media is served directly from Azure (no local serving needed)
# In production without Azure: fallback to local serve view
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
elif not settings.MEDIA_URL.startswith('https://'):
    # Only add local media serving if not using Azure Blob Storage
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    ]
