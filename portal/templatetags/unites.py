"""Filtres de template pour l'accord des unités avec la quantité :
« 1 botte », « 3 bottes », « 2,50 kg ». Usage :
    {% load unites %}
    {{ ligne.quantite }} {{ ligne.quantite|unite:ligne.produit }}
"""
from django import template

register = template.Library()


@register.filter
def unite(quantite, produit):
    """Libellé d'unité accordé à la quantité (singulier/pluriel),
    via Produit.unite_pour(). Les quantités entières (pièce, botte,
    barquette) restent des entiers à la saisie ; seul le kilogramme
    accepte les décimales."""
    try:
        return produit.unite_pour(quantite)
    except AttributeError:
        return getattr(produit, "unite_courte", "")
