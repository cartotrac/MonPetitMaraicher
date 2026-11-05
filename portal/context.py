"""Processeur de contexte : l'exploitation gérée par le compte courant.

Un compte peut être propriétaire de son exploitation (Exploitant.user) ou
simple membre de l'équipe (MembreExploitation) : dans les deux cas les
menus et l'espace pro affichent la même ferme. `est_proprietaire`
distingue le gestionnaire principal (fiche ferme, SIRET, équipe,
catalogue) des membres limités à la gestion courante.
"""

from django.conf import settings

from .models import exploitant_pour


def exploitant_contexte(request):
    try:
        return {
            "exploitant_courant": exploitant_pour(request.user),
            "est_proprietaire": hasattr(request.user, "exploitant"),
        }
    except Exception:
        return {"exploitant_courant": None, "est_proprietaire": False}


def instance_contexte(request):
    """Identité de l'admin de l'instance (pied de page, mentions légales) :
    réglable via settings.INSTANCE_ADMIN sans toucher aux templates."""
    admin = getattr(settings, "INSTANCE_ADMIN", None) or {}
    return {
        "instance_admin_nom": admin.get("nom", ""),
        "instance_admin_url": admin.get("url", ""),
        "instance_admin_logo": admin.get("logo", ""),
    }
