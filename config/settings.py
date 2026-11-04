import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


# Charge le fichier .env à la racine du projet s'il existe (dev / déploiement
# AlwaysData en SSH). En WSGI, les variables du panneau priment (setdefault :
# l'environnement déjà défini gagne sur le fichier).
def _charger_env(chemin=BASE_DIR / ".env"):
    if not chemin.exists():
        return
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, _, valeur = ligne.partition("=")
        os.environ.setdefault(cle.strip(), valeur.strip())


_charger_env()


def env(key, default=None):
    return os.environ.get(key, default)


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-insecure-key-change-me")
DEBUG = env("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [h for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "portal.apps.PortalConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.template.context_processors.csrf",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                # Exploitation gérée par le compte courant (propriétaire ou
                # membre de l'équipe) : naviguation et menus partagés.
                "portal.context.exploitant_contexte",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# L'aperçu de la vitrine dans le dashboard est une iframe du même domaine :
# autoriser l'affichage same-origin (le DENY par défaut bloquait l'aperçu).
X_FRAME_OPTIONS = "SAMEORIGIN"

# CSRF : en https, Django vérifie l'en-tête Origin du navigateur contre la
# liste des origines de confiance. Renseigner dans .env l'URL exacte du site,
# avec scheme et domaine : ex. https://monpetitmaraicher.cartotrac.fr
CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in env("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

# SQLite par défaut (dev / instance mono-ferme) ; PostgreSQL en prod (voir .env.example)
DATABASES = {
    "default": {
        "ENGINE": env("DB_ENGINE", "django.db.backends.sqlite3"),
        "NAME": env("DB_NAME", str(BASE_DIR / "db.sqlite3")),
        "USER": env("DB_USER", ""),
        "PASSWORD": env("DB_PASSWORD", ""),
        "HOST": env("DB_HOST", ""),
        "PORT": env("DB_PORT", ""),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Europe/Paris"
USE_I18N = True
USE_TZ = True

# Fichiers statiques du projet (CSS, JS) : collectstatic les copie vers
# STATIC_ROOT (staticfiles/), servi en production par les « chemins
# statiques » du panneau AlwaysData (/static/ -> staticfiles) avec, en
# repli, le service Django de config/urls.py. Les URLs DOIVENT commencer
# par un slash : sinon les liens statiques deviennent relatifs à la page
# courante et cassent sur les pages profondes (/espace-pro/...).
# Après chaque modification de static/ :
#   manage.py collectstatic --noinput  puis redemarrer le site.
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# E-mails sortants (issue #3). Sans EMAIL_HOST, Django journalise au lieu
# d'envoyer (backend console) et l'interface en informe l'exploitant.
# AlwaysData : EMAIL_HOST=localhost (SMTP mutualisé) fonctionne aussi.
if env("EMAIL_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = env("EMAIL_HOST")
    EMAIL_PORT = int(env("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
    EMAIL_USE_TLS = env("EMAIL_USE_TLS", "0") == "1"
    EMAIL_USE_SSL = env("EMAIL_USE_SSL", "0") == "1"
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL",
                         "noreply@monpetitmaraicher.cartotrac.fr")

LOGIN_URL = "/comptes/connexion/"
LOGIN_REDIRECT_URL = "/apres-connexion/"
LOGOUT_REDIRECT_URL = "/"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Fichiers uploadés : 2 Mo max (logos et photos produits)
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024
