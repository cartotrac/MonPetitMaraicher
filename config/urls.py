from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("comptes/", include("django.contrib.auth.urls")),  # login, logout, password...
    path("", include("portal.urls")),
]

# Fichiers statiques (CSS…) et médias (logos, photos).
# En production AlwaysData (WSGI, DEBUG=0), Django les sert lui-même :
# c'est le plus simple pour un site de cette taille (pas d'alias Apache).
# REQUIS : lancer « manage.py collectstatic » après chaque modification
# de fichiers statiques (donc après chaque git pull qui en touche).
urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = "MonPetitMaraicher — Administration"
admin.site.site_title = "MonPetitMaraicher"
admin.site.index_title = "Back-office du portail"
