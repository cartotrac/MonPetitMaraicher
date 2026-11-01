from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from portal.models import Commande, Panier


class Command(BaseCommand):
    help = ("Purge RGPD : ne conserver en base que l'historique des "
            "commandes validées puis livrées. À planifier (cron quotidien).")

    def add_arguments(self, parser):
        parser.add_argument("--jours-refusees", type=int, default=30,
                            help="Commandes refusées/annulées supprimées "
                                 "après N jours (défaut : 30)")
        parser.add_argument("--jours-sans-suite", type=int, default=90,
                            help="Commandes validées jamais livrées "
                                 "supprimées après N jours (défaut : 90)")
        parser.add_argument("--simuler", action="store_true",
                            help="Ne rien supprimer, juste afficher")

    def handle(self, *args, **options):
        maintenant = timezone.now()
        limite_refusees = maintenant - timedelta(days=options["jours_refusees"])
        limite_sans_suite = maintenant - timedelta(days=options["jours_sans_suite"])

        refusees = Commande.objects.filter(
            statut__in=[Commande.Statut.REFUSEE, Commande.Statut.ANNULEE],
            creee_le__lt=limite_refusees)

        # Validées sans panier livré/reçu : l'exploitant n'a pas donné suite.
        sans_suite = Commande.objects.filter(
            statut=Commande.Statut.VALIDEE,
            creee_le__lt=limite_sans_suite
        ).exclude(paniers__statut__in=[Panier.Statut.LIVRE, Panier.Statut.RECU])

        self.stdout.write(
            f"À purger : {refusees.count()} refusées/annulées, "
            f"{sans_suite.count()} validées sans livraison.")

        if not options["simuler"]:
            n1, _ = refusees.delete()
            n2, _ = sans_suite.delete()
            self.stdout.write(self.style.SUCCESS(
                f"Purgé : {n1} + {n2} objets supprimés."))
