"""Processeur de contexte : l'exploitation gérée par le compte courant.

Un compte peut être propriétaire de son exploitation (Exploitant.user) ou
simple membre de l'équipe (MembreExploitation) : dans les deux cas les
menus et l'espace pro affichent la même ferme. `est_proprietaire`
distingue le gestionnaire principal (fiche ferme, SIRET, équipe,
catalogue) des membres limités à la gestion courante.
"""

from .models import exploitant_pour


def exploitant_contexte(request):
    try:
        return {
            "exploitant_courant": exploitant_pour(request.user),
            "est_proprietaire": hasattr(request.user, "exploitant"),
        }
    except Exception:
        return {"exploitant_courant": None, "est_proprietaire": False}
