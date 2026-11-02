"""
Point d'entrée WSGI (AlwaysData : chemin de l'application = ce fichier).

uWSGI exécute ce fichier depuis le dossier config/ : il faut donc
ajouter le dossier parent au chemin de recherche Python pour que
le paquet « config » soit importable (config.settings).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
