# backend/config/settings.py
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DJANGO_DEBUG=(bool, False))

# Load .env from RoleFindr/, one level above backend/
ENV_FILE = BASE_DIR.parent / ".env"

if ENV_FILE.is_file():
    environ.Env.read_env(str(ENV_FILE))

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = ["*"] if DEBUG else env.list("ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "resumes",
    "jobs",
    "django.contrib.contenttypes", "django.contrib.auth", "django.contrib.sessions",
    "django.contrib.messages", "django.contrib.staticfiles", "django.contrib.admin",
    "corsheaders", "rest_framework", "accounts", "core",
]
AUTH_USER_MODEL = "accounts.User"
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates", "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages"]},
}]
DATABASES = {"default": env.db("DATABASE_URL")}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
STATIC_URL = "static/"
CORS_ALLOWED_ORIGINS = ["http://localhost:3000"]  # platform origin only; tighten per env

CELERY_BROKER_URL = env("REDIS_URL")
CELERY_TASK_ALWAYS_EAGER = env.bool("CELERY_EAGER", default=False)
MEDIA_ROOT = BASE_DIR / "media"  # dev only; private S3 bucket later
MEDIA_URL = "/media/"

# --- Scoring (Slice 3) ---
GEMINI_API_KEY = env("GEMINI_API_KEY", default="")
SCORING_TOP_N = env.int("SCORING_TOP_N", default=20)
SCORING_THRESHOLD = env.int("SCORING_THRESHOLD", default=70)

# --- ResumeIQ ---
RESUMEIQ_URL = env("RESUMEIQ_URL", default="")
RESUMEIQ_API_KEY = env("RESUMEIQ_API_KEY", default="")
