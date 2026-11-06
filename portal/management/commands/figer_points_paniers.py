"""Fige les infos de point de retrait des paniers EXISTANTS.

À exécuter une fois après la migration des champs d'instantané
(point_nom, point_adresse…, figés à la création des paniers) :
les paniers déjà livrés, créés avant le figage, récupèrent le nom,
l'adresse et la position du point tel qu'il est aujourd'hui. Une
modification ultérieure du point par le producteur ne changera plus
l'historique déjà transmis aux clients.

Idempotent : seuls les paniers dont l'instantané est vide sont
complétés ; relancer la commande ne change rien.
"""
from django.core.management.base import BaseCommand

from portal.models import Panier


class Command(BaseCommand):
    help = ("Fige le nom / l'adresse / la position du point de retrait "
            "sur les paniers existants (protection de l'historique "
            "client lors des modifications de points).")

    def handle(self, *args, **options):
        paniers = Panier.objects.filter(
            point_livraison__isnull=False, point_nom="").select_related(
            "point_livraison")
        total = 0
        for panier in paniers.iterator():
            p = panier.point_livraison
            panier.point_nom = p.nom
            panier.point_adresse = p.adresse
            panier.point_code_postal = p.code_postal
            panier.point_ville = p.ville
            panier.point_latitude = p.latitude
            panier.point_longitude = p.longitude
            panier.save(update_fields=[
                "point_nom", "point_adresse", "point_code_postal",
                "point_ville", "point_latitude", "point_longitude"])
            total += 1
        self.stdout.write(self.style.SUCCESS(
            f"{total} panier(s) figé(s) : leur point de retrait ne "
            "changera plus dans l'historique client."))
