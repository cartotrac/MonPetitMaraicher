"""Resynchronise l'identité des clients : met à jour le nom et l'e-mail
enregistrés dans les commandes et paniers à partir du compte client
(prénom/nom/e-mail actuels du profil). À lancer une fois après la
livraison de la synchronisation de profil, ou après toute modification
d'identité faite hors du portail (admin Django par exemple).

Les commandes sans compte (invités) ne sont pas modifiées : elles n'ont
pas de compte de référence.

Usage :
    venv/bin/python manage.py resynchroniser_clients
    venv/bin/python manage.py resynchroniser_clients --sech  # sans conf.
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from portal.models import Commande, Panier, ProfilClient


class Command(BaseCommand):
    help = ("Met à jour nom_client / email_client (et téléphone si "
            "renseigné) des commandes et paniers rattachés à un compte, "
            "d'après les informations actuelles du compte client.")

    def add_arguments(self, parser):
        parser.add_argument("--sech", action="store_true",
                            help="exécuter sans demande de confirmation")

    def handle(self, *args, **options):
        profils = ProfilClient.objects.exclude(user=None).select_related("user")
        total_commandes = 0
        total_paniers = 0
        if not options["sech"]:
            reponse = input("Resynchroniser l'identité de toutes les "
                            "commandes/paniers rattachés à un compte ? [o/N] ")
            if reponse.strip().lower() not in ("o", "oui", "y", "yes"):
                self.stdout.write("Annulé.")
                return
        for profil in profils:
            user = profil.user
            nom_complet = (user.get_full_name() or user.username)[:150]
            maj = {"nom_client": nom_complet, "email_client": user.email}
            if profil.telephone:
                maj["telephone_client"] = profil.telephone[:20]
            total_commandes += Commande.objects.filter(
                client=user).update(**maj)
            total_paniers += Panier.objects.filter(client=user).update(**maj)
        self.stdout.write(self.style.SUCCESS(
            f"{total_commandes} commande(s) et {total_paniers} panier(s) "
            "mis à jour d'après les profils clients."))
