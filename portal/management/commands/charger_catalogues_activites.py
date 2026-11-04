"""Charge les catalogues de produits types par activité (idempotent).

Le catalogue historique reste classé « maraîcher » (activite par
défaut) ; cette commande crée les listes des autres activités
(arboriculture, élevage, fromagerie, ruche) et repositionne
explicitement les produits existants en maraîcher.

Usage :  python manage.py charger_catalogues_activites
"""
from django.core.management.base import BaseCommand

from portal.models import Exploitant, ProduitStandard

# (nom, categorie, unite, emoji, saisons)
CATALOGUES = {    Exploitant.Activite.ARBORICULTEUR: [
        ("Pomme", "Fruits", "KG", "🍎", ["automne", "hiver"]),
        ("Pomme à jus", "Fruits", "KG", "🍎", ["automne"]),
        ("Poire", "Fruits", "KG", "🍐", ["automne"]),
        ("Pêche", "Fruits", "KG", "🍑", ["été"]),
        ("Nectarine", "Fruits", "KG", "🍑", ["été"]),
        ("Abricot", "Fruits", "KG", "🍑", ["été"]),
        ("Cerise", "Fruits", "KG", "🍒", ["été"]),
        ("Prune", "Fruits", "KG", "🫐", ["été"]),
        ("Fraise", "Fruits", "BQ", "🍓", ["printemps", "été"]),
        ("Framboise", "Fruits", "BQ", "🍓", ["été"]),
        ("Myrtille", "Fruits", "BQ", "🫐", ["été"]),
        ("Raisin", "Fruits", "KG", "🍇", ["automne"]),
        ("Melon", "Fruits", "PC", "🍈", ["été"]),
        ("Pastèque", "Fruits", "PC", "🍉", ["été"]),
        ("Noix", "Fruits", "KG", "🌰", ["automne"]),
        ("Noisette", "Fruits", "KG", "🌰", ["automne"]),
        ("Jus de pomme", "Transformés", "PC", "🧃", []),
        ("Compote de pomme", "Transformés", "PC", "🥧", []),
    ],
    Exploitant.Activite.ELEVEUR: [
        ("Bœuf (colis ou au kg)", "Viandes", "KG", "🐄", []),
        ("Veau", "Viandes", "KG", "🐂", []),
        ("Agneau", "Viandes", "KG", "🐑", []),
        ("Porc", "Viandes", "KG", "🐖", []),
        ("Saucisse", "Viandes", "KG", "🌭", []),
        ("Saucisson", "Viandes", "PC", "🌭", []),
        ("Poulet fermier", "Volaille", "PC", "🐔", []),
        ("Poulet", "Volaille", "PC", "🐔", []),
        ("Canard", "Volaille", "PC", "🦆", []),
        ("Oie", "Volaille", "PC", "🦢", []),
        ("Œufs", "Œufs", "PC", "🥚", []),
        ("Œufs de poule (boîte de 6)", "Œufs", "PC", "🥚", []),
        ("Œufs de cane", "Œufs", "PC", "🥚", []),
    ],
    Exploitant.Activite.FROMAGER: [
        ("Tomme", "Fromages", "PC", "🧀", []),
        ("Saint-Nectaire", "Fromages", "PC", "🧀", []),
        ("Cantal", "Fromages", "PC", "🧀", []),
        ("Reblochon", "Fromages", "PC", "🧀", []),
        ("Chèvre", "Fromages", "PC", "🧀", []),
        ("Brebis", "Fromages", "PC", "🧀", []),
        ("Vache qui rit fermière", "Fromages", "PC", "🧀", []),
        ("Yaourt", "Produits laitiers", "BQ", "🥛", []),
        ("Faisselle", "Produits laitiers", "BQ", "🥛", []),
        ("Fromage blanc", "Produits laitiers", "KG", "🥛", []),
        ("Lait cru", "Produits laitiers", "PC", "🥛", []),
        ("Beurre", "Produits laitiers", "PC", "🧈", []),
        ("Crème fraîche", "Produits laitiers", "PC", "🥛", []),
    ],
    Exploitant.Activite.APICULTEUR: [
        ("Miel de fleurs", "Ruche", "PC", "🍯", []),
        ("Miel d'acacia", "Ruche", "PC", "🍯", []),
        ("Miel de châtaignier", "Ruche", "PC", "🍯", []),
        ("Miel de tilleul", "Ruche", "PC", "🍯", []),
        ("Miel de sapin", "Ruche", "PC", "🍯", []),
        ("Miel toutes fleurs (pot)", "Ruche", "PC", "🍯", []),
        ("Pollen", "Ruche", "PC", "🌼", []),
        ("Propolis", "Ruche", "PC", "🌿", []),
        ("Gelée royale", "Ruche", "PC", "👑", []),
        ("Cire d'abeille", "Ruche", "PC", "🕯️", []),
    ],
    Exploitant.Activite.MICRO_BRASSEUR: [
        ("Blonde", "Bières", "PC", "🍺", []),
        ("Blonde de garde", "Bières", "PC", "🍺", []),
        ("Ambrée", "Bières", "PC", "🍺", []),
        ("Rousse", "Bières", "PC", "🍺", []),
        ("Brune", "Bières", "PC", "🍺", []),
        ("Blanche", "Bières", "PC", "🍺", []),
        ("IPA", "Bières", "PC", "🍺", []),
        ("APA", "Bières", "PC", "🍺", []),
        ("Saison", "Bières", "PC", "🍺", []),
        ("Stout", "Bières", "PC", "🍺", []),
        ("Porter", "Bières", "PC", "🍺", []),
        ("Triple", "Bières", "PC", "🍺", []),
        ("Weizen", "Bières", "PC", "🍺", []),
        ("Bière sans alcool", "Bières", "PC", "🫙", []),
        ("Bière de Noël", "Bières", "PC", "🎄", ["hiver"]),
        ("Fût 10 L", "Fûts", "PC", "🛢️", []),
        ("Fût 20 L", "Fûts", "PC", "🛢️", []),
        ("Fût 30 L", "Fûts", "PC", "🛢️", []),
    ],
}


class Command(BaseCommand):
    help = ("Charge les catalogues de produits types par activité "
            "(idempotent : lancez-le après chaque mise à jour).")


# Mots-clés (sans accent, minuscule) pour deviner l'emoji d'un produit
# type qui n'en a pas — chaque produit finit donc avec un symbole.
EMOJIS_PAR_MOTCLE = [
    ("carotte", "🥕"), ("tomate", "🍅"), ("pomme de terre", "🥔"),
    ("patate", "🥔"), ("oignon", "🧅"), ("échalote", "🧅"),
    ("echalote", "🧅"), ("ail", "🧄"), ("courgette", "🥒"),
    ("concombre", "🥒"), ("courge", "🎃"), ("potiron", "🎃"),
    ("potimarron", "🎃"), ("citrouille", "🎃"), ("aubergine", "🍆"),
    ("poivron", "🫑"), ("piment", "🌶️"), ("salade", "🥬"),
    ("laitue", "🥬"), ("roquette", "🥬"), ("mâche", "🥬"),
    ("mache", "🥬"), ("épinard", "🥬"), ("epinard", "🥬"),
    ("choux", "🥬"), ("chou", "🥬"), ("brocoli", "🥦"),
    ("poireau", "🥬"), ("betterave", "🟣"), ("navet", "🟠"),
    ("radis", "🌶️"), ("haricot", "🫛"), ("pois", "🫛"),
    ("fève", "🫛"), ("feve", "🫛"), ("fenouil", "🌿"),
    ("céleri", "🌿"), ("celeri", "🌿"), ("asperge", "🌿"),
    ("artichaut", "🌿"), ("herbe", "🌿"), ("persil", "🌿"),
    ("basilic", "🌿"), ("ciboule", "🌿"), ("coriandre", "🌿"),
    ("thym", "🌿"), ("menthe", "🌿"), ("laurier", "🌿"),
    ("maïs", "🌽"), ("mais", "🌽"), ("champignon", "🍄"),
    ("pomme", "🍎"), ("poire", "🍐"), ("pêche", "🍑"),
    ("peche", "🍑"), ("nectarine", "🍑"), ("abricot", "🍑"),
    ("cerise", "🍒"), ("prune", "🫐"), ("fraise", "🍓"),
    ("framboise", "🍓"), ("myrtille", "🫐"), ("cassis", "🫐"),
    ("groseille", "🫐"), ("raisin", "🍇"), ("melon", "🍈"),
    ("pastèque", "🍉"), ("pasteque", "🍉"), ("kiwi", "🥝"),
    ("citron", "🍋"), ("orange", "🍊"), ("mandarine", "🍊"),
    ("clémentine", "🍊"), ("clementine", "🍊"), ("avocat", "🥑"),
    ("banane", "🍌"), ("figue", "🫒"), ("noix", "🌰"),
    ("noisette", "🌰"), ("amande", "🌰"), ("œuf", "🥚"),
    ("oeuf", "🥚"), ("lait", "🥛"), ("yaourt", "🥛"),
    ("faisselle", "🥛"), ("fromage", "🧀"), ("tomme", "🧀"),
    ("cantal", "🧀"), ("reblochon", "🧀"), ("chèvre", "🧀"),
    ("chevre", "🧀"), ("brebis", "🧀"), ("beurre", "🧈"),
    ("crème", "🥛"), ("creme", "🥛"), ("miel", "🍯"),
    ("gelée", "🍯"), ("gelee", "🍯"), ("confiture", "🍯"),
    ("bière", "🍺"), ("biere", "🍺"), ("houblon", "🍺"),
    ("fût", "🛢️"), ("fut", "🛢️"), ("jus", "🧃"), ("sirop", "🧃"),
    ("compote", "🥧"), ("tarte", "🥧"), ("pain", "🍞"),
    ("farine", "🌾"), ("lentille", "🫘"), ("pois chiche", "🫘"),
    ("haricot sec", "🫘"), ("huile", "🫒"), ("olive", "🫒"),
    ("bœuf", "🐄"), ("boeuf", "🐄"), ("veau", "🐂"),
    ("agneau", "🐑"), ("mouton", "🐑"), ("porc", "🐖"),
    ("saucisse", "🌭"), ("saucisson", "🌭"), ("jambon", "🥓"),
    ("poulet", "🐔"), ("canard", "🦆"), ("oie", "🦢"),
    ("dinde", "🦃"), ("lapin", "🐇"), ("escargot", "🐌"),
    ("truite", "🐟"), ("saumon", "🐟"), ("poisson", "🐟"),
]


def emoji_pour_nom(nom):
    """Emoji deviné par mot-clé du nom du produit (sans accent,
    minuscule). Défaut : symbole de l'activité (🥬 maraîcher)."""
    texte = nom.lower()
    for motcle, emoji in EMOJIS_PAR_MOTCLE:
        if motcle in texte:
            return emoji
    return ""

    def handle(self, *args, **options):
        # 1. Le catalogue existant est explicitement classé maraîcher.
        existants = ProduitStandard.objects.filter(
            activite=Exploitant.Activite.MARAICHER).count()
        ProduitStandard.objects.filter(activite="").update(
            activite=Exploitant.Activite.MARAICHER)
        self.stdout.write(f"Catalogue maraîcher : {existants} produit(s).")

        # 2. Les catalogues des autres activités.
        for activite, produits in CATALOGUES.items():
            crees = 0
            for nom, categorie, unite, emoji, saisons in produits:
                _, cree = ProduitStandard.objects.get_or_create(
                    activite=activite, nom=nom,
                    defaults={"categorie": categorie, "unite_vente": unite,
                              "emoji": emoji, "saisons": saisons})
                crees += 1 if cree else 0
            libelle = Exploitant.Activite(activite).label
            total = ProduitStandard.objects.filter(
                activite=activite).count()
            self.stdout.write(
                f"{libelle} : {total} produit(s) "
                f"({crees} nouveau(x) cette exécution).")

        # 3. Aucun produit type sans emoji : on devine le symbole par
        #    mot-clé du nom, avec le symbole de l'activité en dernier
        #    recours — chaque produit a ainsi son emoji (vignettes,
        #    commandes, paniers, récoltes).
        sans_emoji = ProduitStandard.objects.filter(emoji="")
        remplaces = 0
        for std in sans_emoji:
            emoji = emoji_pour_nom(std.nom)
            if not emoji:
                emoji = Exploitant.ACTIVITE_EMOJIS.get(
                    std.activite, "🌱")
            std.emoji = emoji
            std.save(update_fields=["emoji"])
            remplaces += 1
        self.stdout.write(f"Emojis complétés : {remplaces} produit(s).")

        self.stdout.write(self.style.SUCCESS(
            "Catalogues par activité chargés."))
