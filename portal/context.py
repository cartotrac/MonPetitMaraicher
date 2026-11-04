"""Processeur de contexte : l'exploitation gérée par le compte courant.

Un compte peut être propriétaire de son exploitation (Exploitant.user) ou
simple membre de l'équipe (MembreExploitation) : dans les deux cas les
menus et l'espace pro affichent la même ferme.
"""

from .models import exploitant_pour


def exploitant_contexte(request):
    try:
        return {"exploitant_courant": exploitant_pour(request.user)}
    except Exception:
        return {"exploitant_courant": None}
