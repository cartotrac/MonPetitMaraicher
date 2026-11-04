"""Peuple l'instance avec des fermes et clients de DÉMONSTRATION.

Crée trois exploitations fictives du Tarn (maraîcher, arboriculture et
fromagerie) avec des catalogues MIXTES multi-catégories (issus des
produits types), points de livraison et créneaux, récoltes de la
semaine, clients de démo et un historique de commandes/paniers couvrant
tous les statuts — de quoi montrer le portail de bout en bout en
quelques clics.

Les fermes de démo sont identifiables partout (vignettes de recherche,
carte, fiche producteur) par un badge 🧪 DÉMO.

⚠️ Toutes les données sont FICTIVES : noms, SIRET (valides au format
Luhn mais inventés), adresses et coordonnées ne référencent aucune
entreprise réelle.

Usage :
    python manage.py peupler_demo            # crée si absent (idempotent)
    python manage.py peupler_demo --purge   # supprime les comptes de démo

Comptes créés (mot de passe : demo1234!) :
    demo.maraicher (producteur maraîcher)   — Les Jardins du Sor
    demo.vergers   (producteur arboriculteur) — Les Vergers de l'Agout
    demo.fromager  (producteur fromager)    — Ferme des Cabanes
    demo.cliente   (cliente avec compte)
    demo.client    (client avec compte)
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from portal.models import (Bulletin, Categorie, Commande, CreneauLivraison,
                           Exploitant, LigneCommande, LignePanier,
                           LigneRecolte, Panier, PointLivraison, Produit,
                           ProduitStandard, ProfilClient, SemaineRecolte)

MOT_DE_PASSE_DEMO = "demo1234!"


def _siret_valide(prefixe13):
    """Complète 13 chiffres par la clé de Luhn (règle du modèle Produit
    — indices pairs doublés depuis la gauche sur 14 chiffres)."""
    chiffres = prefixe13
    for cle in range(10):
        candidat = chiffres + str(cle)
        total = 0
        for i, c in enumerate(candidat):
            d = int(c)
            if i % 2 == 0:
                d *= 2
                if d > 9:
                    d -= 9
            total += d
        if total % 10 == 0:
            return candidat
    return chiffres + "0"


FERMES = [
    {
        "utilisateur": "demo.maraicher",
        "ferme": "Les Jardins du Sor",
        "activite": Exploitant.Activite.MARAICHER,
        "mode": Exploitant.ModeProduction.PERMA,
        "siret_prefixe": "8150012300003",
        "adresse": "Chemin de Gandalou",
        "ville": "Lavaur",
        "cp": "81500",
        "lat": 43.699, "lon": 1.915,
        "tel": "05 63 00 00 03",
        "description": ("Jardin maraîcher en permaculture dans la vallée "
                        "du Sor : légumes de saison, herbes aromatiques, "
                        "œufs fermiers et fruits du verger, en "
                        "distribution directe."),
        "prix_base": Decimal("2.20"),
        "mix": [
            {"activite": Exploitant.Activite.MARAICHER, "limite": 24},
            {"activite": Exploitant.Activite.ARBORICULTEUR,
             "categorie": "Fruits", "limite": 6},
            {"activite": Exploitant.Activite.ELEVEUR,
             "categorie": "Œufs", "limite": 2},
            {"activite": Exploitant.Activite.APICULTEUR, "limite": 3},
        ],
        "points": [
            ("Marché de Lavaur", "Place de la Halle",
             "Lavaur", "81500", 43.700, 1.900),
            ("Quai de Rabastens", "Parking des halles",
             "Rabastens", "81600", 43.820, 1.722),
        ],
        "creneaux": [(6, "08:00", "12:00", 0), (2, "17:30", "19:30", 1)],
        "note_semaine": "Arrivée des premières courges — butternut et potimarron !",
        "bulletin": ("Paniers de la semaine aux Jardins du Sor",
                     "Courges d'hiver, poireaux, choux kale et salades "
                     "d'automne. Œufs fermiers en nombre limité, "
                     "pensez à les réserver avec votre panier."),
    },
    {
        "utilisateur": "demo.vergers",
        "ferme": "Les Vergers de l'Agout",
        "activite": Exploitant.Activite.ARBORICULTEUR,
        "mode": Exploitant.ModeProduction.AB,
        "siret_prefixe": "8137012340001",
        "adresse": "Chemin des Hauts, lieu-dit Las Rives",
        "ville": "Saint-Sulpice-la-Pointe",
        "cp": "81370",
        "lat": 43.656, "lon": 2.138,
        "tel": "05 63 00 00 01",
        "description": ("Vergers familiaux conduits en agriculture "
                        "biologique au bord de l'Agout : pommes, poires, "
                        "petits fruits et jus de la ferme, récoltés à "
                        "maturité et vendus en circuit court."),
        "prix_base": Decimal("1.90"),
        "mix": [
            {"activite": Exploitant.Activite.ARBORICULTEUR, "limite": 20},
            {"activite": Exploitant.Activite.APICULTEUR, "limite": 4},
            {"activite": Exploitant.Activite.ELEVEUR,
             "categorie": "Œufs", "limite": 3},
        ],
        "points": [
            ("Marché de Saint-Sulpice", "Place de la Halle",
             "Saint-Sulpice-la-Pointe", "81370", 43.660, 2.140),
            ("Place de Gaillac", "Place du marché couvert",
             "Gaillac", "81600", 43.900, 1.895),
        ],
        "creneaux": [(6, "08:30", "12:00", 0), (3, "17:00", "19:00", 1)],
        "note_semaine": "Premières pommes Gala de la saison — mûres à point !",
        "bulletin": ("Récolte de la semaine aux Vergers de l'Agout",
                     "Pommes Gala et Reinette arrivent au marché, "
                     "poires Williams à maturité. Les barquettes de "
                     "framboises partent vite : commandez tôt !"),
    },
    {
        "utilisateur": "demo.fromager",
        "ferme": "Ferme des Cabanes",
        "activite": Exploitant.Activite.FROMAGER,
        "mode": Exploitant.ModeProduction.PAYSAN,
        "siret_prefixe": "8128076540002",
        "adresse": "Route de Montredon, lieu-dit Les Cabanes",
        "ville": "Réalmont",
        "cp": "81280",
        "lat": 43.778, "lon": 2.531,
        "tel": "05 63 00 00 02",
        "description": ("Ferme fromagère familiale en agriculture paysanne "
                        "sur les coteaux du Dadou : tomme de brebis, "
                        "fromages frais et caillé, fabrication à la ferme "
                        "en bidons de cuivre."),
        "prix_base": Decimal("4.50"),
        "mix": [
            {"activite": Exploitant.Activite.FROMAGER, "limite": 20},
            {"activite": Exploitant.Activite.APICULTEUR, "limite": 2},
            {"activite": Exploitant.Activite.ELEVEUR,
             "categorie": "Œufs", "limite": 2},
        ],
        "points": [
            ("Halte de Réalmont", "Place de la République",
             "Réalmont", "81280", 43.775, 2.528),
            ("Marché de Castres", "Place Jean Jaurès (étal n°12)",
             "Castres", "81100", 43.605, 2.242),
        ],
        "creneaux": [(6, "09:00", "12:30", 0), (4, "16:30", "18:30", 1)],
        "note_semaine": "Tomme de brebis affinée 3 mois — stock limité.",
        "bulletin": ("Fromages de la semaine à la Ferme des Cabanes",
                     "La tomme de brebis 3 mois d'affinage est de retour ! "
                     "Fromage frais du vendredi et caillé à emporter "
                     "directement au marché."),
    },
]

CLIENTS = [
    {"utilisateur": "demo.cliente", "prenom": "Marie", "nom": "Dupont",
     "email": "marie.dupont@example.fr", "tel": "06 12 34 56 78",
     "ville": "Gaillac", "cp": "81600"},
    {"utilisateur": "demo.client", "prenom": "Paul", "nom": "Martin",
     "email": "paul.martin@example.fr", "tel": "06 98 76 54 32",
     "ville": "Castres", "cp": "81100"},
]


class Command(BaseCommand):
    help = ("Crée des données de démonstration fictives (fermes du Tarn, "
            "clients, commandes et paniers). Idempotent ; --purge efface.")

    def add_arguments(self, parser):
        parser.add_argument("--purge", action="store_true",
                            help="Supprime les comptes et données de démo")

    def _lundi(self):
        today = timezone.localdate()
        return today - datetime.timedelta(days=today.weekday())

    def _ferme(self, spec):
        """Exploitation de démo : compte, fiche, catalogue, points,
        créneaux, récolte de la semaine, bulletin."""
        if User.objects.filter(username=spec["utilisateur"]).exists():
            self.stdout.write(self.style.NOTICE(
                f"Compte {spec['utilisateur']} déjà présent : ferme ignorée."))
            return None
        user = User.objects.create_user(
            username=spec["utilisateur"], password=MOT_DE_PASSE_DEMO,
            first_name="Famille", last_name=spec["ferme"],
            email=spec["utilisateur"] + "@example.fr")
        exploitant = Exploitant.objects.create(
            user=user, nom_ferme=spec["ferme"], activite=spec["activite"],
            mode_production=spec["mode"],
            siret=_siret_valide(spec["siret_prefixe"]),
            description=spec["description"], adresse=spec["adresse"],
            ville=spec["ville"], code_postal=spec["cp"],
            telephone=spec["tel"], latitude=spec["lat"],
            longitude=spec["lon"], visible=True, est_demo=True)

        # Catalogue MIXTE multi-catégories : on pioche dans les
        # catalogues types de plusieurs activités (la catégorie type
        # de chaque produit devient une catégorie du producteur) ;
        # les prix progressent au sein de chaque catégorie.
        produits = []
        for source in spec["mix"]:
            qs = ProduitStandard.objects.filter(
                activite=source["activite"])
            if source.get("categorie"):
                qs = qs.filter(categorie=source["categorie"])
            for std in qs[:source["limite"]]:
                if Produit.objects.filter(
                        exploitant=exploitant,
                        origine_standard=std).exists():
                    continue
                cat, _cree = Categorie.objects.get_or_create(
                    exploitant=exploitant, nom=std.categorie)
                if _cree:
                    cat.position = exploitant.categories.count()
                    cat.save()
                rang = (Produit.objects
                        .filter(exploitant=exploitant, categorie=cat)
                        .count())
                produit = Produit.objects.create(
                    exploitant=exploitant, nom=std.nom, categorie=cat,
                    unite_vente=std.unite_vente,
                    attributs={"saisons": std.saisons},
                    origine_standard=std,
                    prix=spec["prix_base"] + Decimal(rang) * Decimal("0.50"),
                    actif=True)
                produits.append(produit)

        # Points de livraison + créneaux
        points = []
        for nom, adresse, ville, cp, lat, lon in spec["points"]:
            points.append(PointLivraison.objects.create(
                exploitant=exploitant, nom=nom, adresse=adresse,
                ville=ville, code_postal=cp, latitude=lat, longitude=lon))
        for jour, debut, fin, idx_point in spec["creneaux"]:
            CreneauLivraison.objects.create(
                exploitant=exploitant, point_livraison=points[idx_point],
                jour=jour,
                heure_debut=datetime.time.fromisoformat(debut),
                heure_fin=datetime.time.fromisoformat(fin),
                frequence=CreneauLivraison.Frequence.HEBDO)

        # Récolte de la semaine en cours (publiée) + une semaine à venir
        lundi = self._lundi()
        for decal, publiee in ((0, True), (7, True)):
            semaine = SemaineRecolte.objects.create(
                exploitant=exploitant,
                lundi=lundi + datetime.timedelta(days=decal),
                note=(spec["note_semaine"] if decal == 0 else ""),
                publiee=publiee)
            if decal == 0:
                for i, produit in enumerate(produits[:6]):
                    LigneRecolte.objects.create(
                        recolte=semaine, produit=produit,
                        quantite_estimee=Decimal(10 + 2 * i),
                        prix_unitaire=produit.prix)
        Bulletin.objects.create(
            exploitant=exploitant, objet=spec["bulletin"][0],
            corps=spec["bulletin"][1])
        self.stdout.write(self.style.SUCCESS(
            f"🌾 {exploitant.nom_ferme} créée (compte "
            f"{spec['utilisateur']}, mot de passe {MOT_DE_PASSE_DEMO}) : "
            f"{len(produits)} produits en "
            f"{exploitant.categories.count()} catégories, "
            f"{len(points)} points."))
        return exploitant, produits, points

    def _clients(self):
        clients = []
        for spec in CLIENTS:
            if User.objects.filter(username=spec["utilisateur"]).exists():
                user = User.objects.filter(
                    username=spec["utilisateur"]).first()
            else:
                user = User.objects.create_user(
                    username=spec["utilisateur"], password=MOT_DE_PASSE_DEMO,
                    first_name=spec["prenom"], last_name=spec["nom"],
                    email=spec["email"])
                self.stdout.write(self.style.SUCCESS(
                    f"👤 Client {spec['utilisateur']} créé "
                    f"(mot de passe {MOT_DE_PASSE_DEMO})."))
            ProfilClient.objects.get_or_create(
                user=user,
                defaults={"telephone": spec["tel"], "ville": spec["ville"],
                          "code_postal": spec["cp"]})
            clients.append(user)
        return clients

    def _commande(self, exploitant, produits, point, client, lignes,
                  statut, jours, panier_statut=None, quantite_livree=None):
        """Commande (+ éventuellement son panier numéroté) de démo."""
        date_livraison = self._lundi() + datetime.timedelta(days=jours)
        nom = (client.get_full_name() if client else "Client anonyme")
        commande = Commande.objects.create(
            exploitant=exploitant, client=client, nom_client=nom,
            email_client=(client.email if client else ""),
            telephone_client=("" if client else "06 11 22 33 44"),
            point_livraison=point, date_livraison=date_livraison,
            statut=statut,
            validee_le=(timezone.now() if statut != Commande.Statut.NOUVELLE
                        else None),
            note="")
        total = Decimal("0")
        for produit, quantite in lignes:
            LigneCommande.objects.create(
                commande=commande, produit=produit, quantite=quantite,
                prix_unitaire=produit.prix)
            total += quantite * produit.prix
        commande.total = total
        commande.save()
        if panier_statut:
            panier = Panier.objects.create(
                exploitant=exploitant, client=client, nom_client=nom,
                email_client=(client.email if client else ""),
                telephone_client=(
                    (client.profil_client.telephone
                     if hasattr(client, "profil_client") else "")
                    if client else "06 11 22 33 44"),
                numero=Panier.prochain_numero(exploitant, date_livraison,
                                               point),
                date_livraison=date_livraison, point_livraison=point,
                commande=commande, statut=panier_statut)
            total_panier = Decimal("0")
            for produit, quantite in lignes:
                q = quantite
                if quantite_livree is not None:
                    q = quantite_livree.get(produit.pk, quantite)
                if q <= 0:
                    continue
                LignePanier.objects.create(
                    panier=panier, produit=produit, quantite=q,
                    prix_unitaire=produit.prix)
                total_panier += q * produit.prix
            panier.total = total_panier
            panier.save()
        return commande

    def handle(self, *args, **options):
        if options["purge"]:
            n = 0
            for spec in FERMES:
                n += User.objects.filter(
                    username=spec["utilisateur"]).delete()[0]
            for spec in CLIENTS:
                n += User.objects.filter(
                    username=spec["utilisateur"]).delete()[0]
            self.stdout.write(self.style.SUCCESS(
                f"Données de démo supprimées ({n} objet(s))."))
            return

        clients = self._clients()
        for spec in FERMES:
            resultat = self._ferme(spec)
            if resultat is None:
                continue
            exploitant, produits, points = resultat
            # Garde-fou : les catalogues types comptent une dizaine de
            # produits, mais on reste robuste si un est plus court.
            def pick(i):
                return produits[i % len(produits)]
            deux = [(pick(0), Decimal("2")),
                    (pick(2), Decimal("1"))]
            trois = [(pick(1), Decimal("3")),
                     (pick(3), Decimal("2")),
                     (pick(4), Decimal("1"))]
            # 1. Commande à valider (portail, cliente avec compte)
            self._commande(exploitant, produits, points[0], clients[0],
                            deux, Commande.Statut.NOUVELLE, jours=6)
            # 2. Commande validée → panier en préparation
            self._commande(exploitant, produits, points[0], clients[1],
                           trois, Commande.Statut.VALIDEE, jours=6,
                           panier_statut=Panier.Statut.PREPARATION)
            # 3. Panier prêt (commande sans compte, au marché)
            self._commande(exploitant, produits, points[1], None,
                           deux, Commande.Statut.VALIDEE, jours=5,
                           panier_statut=Panier.Statut.PRET)
            # 4. Panier livré (lecture seule) avec un ajustement
            ajuste = {pick(1).pk: Decimal("2")}  # 3 kg souhaités → 2 livrés
            self._commande(exploitant, produits, points[1], clients[0],
                           trois, Commande.Statut.VALIDEE, jours=-2,
                           panier_statut=Panier.Statut.LIVRE,
                           quantite_livree=ajuste)
        self.stdout.write(self.style.SUCCESS(
            "Démonstration prête : 3 fermes fictives du Tarn (maraîcher, "
            "arboriculture, fromagerie) avec catalogues multi-catégories, "
            "2 clients, commandes à valider, paniers en préparation, "
            "prêts et livrés (lecture seule)."))
        self.stdout.write("Connexion producteur : demo.maraicher, "
                          "demo.vergers ou demo.fromager — mot de passe "
                          + MOT_DE_PASSE_DEMO)
