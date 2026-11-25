# backend/config/urls.py
from django.contrib import admin
from django.urls import include, path

from core.views import health

urlpatterns = [
    path("api/resume/", include("resumes.urls")),path("admin/", admin.site.urls), path("api/health", health)]