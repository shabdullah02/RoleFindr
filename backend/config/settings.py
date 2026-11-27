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
RESUMEIQ_API_KEY = env("RESUMEIQ_API_KEY", default="")  # no trailing comma

# --- Cache and budgets (ADR 0003) ---
CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": env("REDIS_URL")}}
LINKEDIN_MAX_SEARCHES_PER_DAY = env.int("LINKEDIN_MAX_SEARCHES_PER_DAY", default=3)
LINKEDIN_MAX_DESCRIPTIONS_PER_DAY = env.int("LINKEDIN_MAX_DESCRIPTIONS_PER_DAY", default=40)
JOB_SEARCH_MAX_PER_USER_PER_DAY = env.int("JOB_SEARCH_MAX_PER_USER_PER_DAY", default=1)
JOB_SEARCH_CACHE_SECONDS = 6 * 60 * 60
LINKEDIN_PROXIES = [p for p in env.list("LINKEDIN_PROXIES", default=[]) if p]

# --- Session auth from the Next.js origin (ADR 0003 item 1) ---
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = ["http://localhost:3000"]
SESSION_COOKIE_SAMESITE = "Lax"

# --- allauth headless [VERIFY keys against the pinned version] ---
INSTALLED_APPS += ["django.contrib.sites", "allauth", "allauth.account", "allauth.headless"]
MIDDLEWARE += ["allauth.account.middleware.AccountMiddleware"]
SITE_ID = 1
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*"]
HEADLESS_ONLY = True
