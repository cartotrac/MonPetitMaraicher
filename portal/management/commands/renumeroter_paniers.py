"""Rattache un point de livraison aux commandes et paniers qui n'en ont
pas, puis renumérote TOUS les paniers : séquence 1..X par
(exploitation, date de livraison, point de livraison), dans l'ordre
chronologique puis de création.

Usage :
    venv/bin/python manage.py renumeroter_paniers            # 1er point
    venv/bin/python manage.py renumeroter_paniers --point 3  # point précis
    venv/bin/python manage.py renumeroter_paniers --sech     # sans confirmation
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from portal.models import Commande, Panier, PointLivraison


class Command(BaseCommand):
    help = ("Rattache un point de livraison aux commandes/paniers sans "
            "point, puis renumérote les paniers par exploitation, date "
            "et point de livraison.")

    def add_arguments(self, parser):
        parser.add_argument("--point", type=int, default=None,
                            help="ID du point de livraison à affecter "
                                 "(par défaut : le premier trouvé)")
        parser.add_argument("--sech", action="store_true",
                            help="Ne pas demander de confirmation")

    def handle(self, *args, **options):
        point = None
        if options["point"]:
            point = PointLivraison.objects.filter(
                pk=options["point"]).first()
            if point is None:
                raise CommandError(f"Aucun point de livraison n°{options['point']}.")
        if point is None:
            point = PointLivraison.objects.order_by("id").first()
        if point is None:
            raise CommandError("Aucun point de livraison : créez-en un "
                               "d'abord (menu Livraison).")

        commandes_sans_point = Commande.objects.filter(
            point_livraison__isnull=True).count()
        paniers_sans_point = Panier.objects.filter(
            point_livraison__isnull=True).count()
        self.stdout.write(f"Point de livraison à affecter : « {point.nom} » "
                          f"({point.ville})")
        self.stdout.write(f"Commandes sans point : {commandes_sans_point}")
        self.stdout.write(f"Paniers sans point   : {paniers_sans_point}")
        self.stdout.write("Les paniers seront renumérotés : séquence par "
                          "exploitation, date et point de livraison.")

        if not options["sech"]:
            reponse = input("Continuer ? (oui/non) ")
            if reponse.strip().lower() not in ("oui", "o", "y", "yes"):
                self.stdout.write("Abandon : rien n'a été modifié.")
                return

        with transaction.atomic():
            Commande.objects.filter(
                point_livraison__isnull=True).update(point_livraison=point)
            Panier.objects.filter(
                point_livraison__isnull=True).update(point_livraison=point)
            compte = {}
            modifies = 0
            for panier in Panier.objects.order_by("date_livraison", "id"):
                cle = (panier.exploitant_id, panier.date_livraison,
                       panier.point_livraison_id)
                compte[cle] = compte.get(cle, 0) + 1
                if panier.numero != compte[cle]:
                    panier.numero = compte[cle]
                    panier.save(update_fields=["numero"])
                    modifies += 1

        self.stdout.write(self.style.SUCCESS(
            f"Terminé : {commandes_sans_point} commande(s) et "
            f"{paniers_sans_point} panier(s) rattachés au point "
            f"« {point.nom} », {modifies} panier(s) renuméroté(s)."))
