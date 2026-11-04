"""Peuple l'instance avec des fermes et clients de DÉMONSTRATION.

Crée des exploitations fictives — le Tarn, ses départements
limitrophes (Aveyron, Aude, Hérault, Haute-Garonne, Tarn-et-Garonne),
la Bretagne, la Loire, la Corse, La Réunion et la Martinique — avec
des catalogues MIXTES multi-catégories (issus des produits types),
points de livraison, créneaux, récoltes de la semaine, clients de démo
et un historique de commandes/paniers couvrant tous les statuts : de
quoi montrer le portail de bout en bout, y compris la recherche
géographique, en quelques clics.

Les fermes de démo sont identifiables partout (vignettes de recherche,
carte, fiche producteur) par un badge 🧪 DÉMO et le champ
« Exploitation de démonstration » (page Paramètres).

⚠️ Toutes les données sont FICTIVES : noms, SIRET (valides au format
Luhn mais inventés), adresses et coordonnées ne référencent aucune
entreprise réelle.

Usage :
    python manage.py peupler_demo            # crée si absent (idempotent)
    python manage.py peupler_demo --purge   # supprime les comptes de démo

La purge efface TOUS les comptes de démo : ceux du jeu actuel, tout
compte en « demo.* » et toute exploitation marquée « démo » dans la
base (même issue d'un jeu plus ancien) — le jeu peut donc être purgé
et repeuplé à volonté.

Comptes créés (mot de passe : demo1234!) :
    Tarn        : demo.maraicher, demo.vergers, demo.fromager
    Limitrophes : demo.aveyron.eleveur, demo.aveyron.maraicher,
                  demo.aude.apiculteur, demo.herault.arboriculteur,
                  demo.toulouse.fromager, demo.montauban.maraicher
    Bretagne    : demo.brest.maraicher, demo.rennes.eleveur
    Loire       : demo.loire.maraicher, demo.loire.apiculteur
    Corse       : demo.corse.eleveur, demo.corse.fromager
    Réunion     : demo.reunion.maraicher, demo.reunion.arboriculteur
    Martinique  : demo.martinique.maraicher, demo.martinique.eleveur
    Brasseries : demo.brasserie.sor, demo.brasserie.leguer
    Clients     : demo.cliente, demo.client
"""
import datetime
from decimal import Decimal
from itertools import count

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils.text import slugify
from django.utils import timezone

from portal.models import (Bulletin, Categorie, Commande, CreneauLivraison,
                           Exploitant, LigneCommande, LignePanier,
                           LigneRecolte, Panier, PointLivraison, Produit,
                           ProduitStandard, ProfilClient, SemaineRecolte)

MOT_DE_PASSE_DEMO = "demo1234!"


def _siret_valide(prefixe13):
    """Complète 13 chiffres par la clé de Luhn (règle du modèle Produit
    — indices pairs doublés depuis la gauche sur 14 chiffres)."""
    total = 0
    for i, chiffre in enumerate(prefixe13):
        valeur = int(chiffre)
        if i % 2 == 0:
            valeur *= 2
            if valeur > 9:
                valeur -= 9
        total += valeur
    cle = (10 - total % 10) % 10
    return prefixe13 + str(cle)


_SIRET_SEQ = count(1)


def _ferme_spec(utilisateur, ferme, activite, mode, cp, adresse, ville,
                lat, lon, tel, description, prix_base, mix, points,
                creneaux, note_semaine, bulletin_objet, bulletin_corps):
    """Construit la spécification d'une ferme de démo (appel compact).
    Le préfixe SIRET (13 chiffres, clé de Luhn ajoutée ensuite) est
    dérivé du code postal + un compteur global unique."""
    return {
        "utilisateur": utilisateur, "ferme": ferme, "activite": activite,
        "mode": mode,
        "siret_prefixe": cp + "123400" + str(next(_SIRET_SEQ)).zfill(2),
        "adresse": adresse, "ville": ville, "cp": cp,
        "lat": lat, "lon": lon, "tel": tel,
        "description": description, "prix_base": prix_base, "mix": mix,
        "points": points, "creneaux": creneaux, "note_semaine": note_semaine,
        "bulletin": (bulletin_objet, bulletin_corps),
    }


A = Exploitant.Activite
M = Exploitant.ModeProduction

FERMES = [
    # ── Tarn ──────────────────────────────────────────────────────
    {
        "utilisateur": "demo.maraicher",
        "ferme": "Les Jardins du Sor",
        "activite": A.MARAICHER, "mode": M.PERMA,
        "siret_prefixe": "8150012300003",
        "adresse": "Chemin de Gandalou", "ville": "Lavaur",
        "cp": "81500", "lat": 43.699, "lon": 1.915,
        "tel": "05 63 00 00 03",
        "description": ("Jardin maraîcher en permaculture dans la vallée "
                        "du Sor : légumes de saison, herbes aromatiques, "
                        "œufs fermiers et fruits du verger, en "
                        "distribution directe."),
        "prix_base": Decimal("2.20"),
        "mix": [
            {"activite": A.MARAICHER, "limite": 24},
            {"activite": A.ARBORICULTEUR, "categorie": "Fruits",
             "limite": 6},
            {"activite": A.ELEVEUR, "categorie": "Œufs", "limite": 2},
            {"activite": A.APICULTEUR, "limite": 3},
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
        "activite": A.ARBORICULTEUR, "mode": M.AB,
        "siret_prefixe": "8137012340001",
        "adresse": "Chemin des Hauts, lieu-dit Las Rives",
        "ville": "Saint-Sulpice-la-Pointe", "cp": "81370",
        "lat": 43.656, "lon": 2.138,
        "tel": "05 63 00 00 01",
        "description": ("Vergers familiaux conduits en agriculture "
                        "biologique au bord de l'Agout : pommes, poires, "
                        "petits fruits et jus de la ferme, récoltés à "
                        "maturité et vendus en circuit court."),
        "prix_base": Decimal("1.90"),
        "mix": [
            {"activite": A.ARBORICULTEUR, "limite": 20},
            {"activite": A.APICULTEUR, "limite": 4},
            {"activite": A.ELEVEUR, "categorie": "Œufs", "limite": 3},
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
        "activite": A.FROMAGER, "mode": M.PAYSAN,
        "siret_prefixe": "8128076540002",
        "adresse": "Route de Montredon, lieu-dit Les Cabanes",
        "ville": "Réalmont", "cp": "81280",
        "lat": 43.778, "lon": 2.531,
        "tel": "05 63 00 00 02",
        "description": ("Ferme fromagère familiale en agriculture paysanne "
                        "sur les coteaux du Dadou : tomme de brebis, "
                        "fromages frais et caillé, fabrication à la ferme "
                        "en bidons de cuivre."),
        "prix_base": Decimal("4.50"),
        "mix": [
            {"activite": A.FROMAGER, "limite": 20},
            {"activite": A.APICULTEUR, "limite": 2},
            {"activite": A.ELEVEUR, "categorie": "Œufs", "limite": 2},
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
    # ── Aveyron (2) ──────────────────────────────────────────────
    _ferme_spec(
        "demo.aveyron.eleveur", "Ferme de l'Aubrac", A.ELEVEUR, M.PAYSAN,
        "12200", "Route de Laguiole, lieu-dit Coubjacou",
        "Villefranche-de-Rouergue", 44.349, 2.032, "05 65 00 00 04",
        "Élevage d'Aubrac en agriculture paysanne sur les causse : "
        "viande de bœuf et d'agneau, vente directe à la ferme et au "
        "marché de Villefranche.",
        Decimal("6.00"),
        [{"activite": A.ELEVEUR, "limite": 20},
         {"activite": A.APICULTEUR, "limite": 3}],
        [("Marché de Villefranche", "Place de la Halle",
          "Villefranche-de-Rouergue", "12200", 44.350, 2.030)],
        [(6, "08:00", "12:00", 0)],
        "Agneaux de pâturage prêts pour les fêtes de fin d'année.",
        "Viande de la semaine à la Ferme de l'Aubrac",
        "Colis de bœuf et agneau disponibles à la ferme ; le miel de "
        "causse part vite, réservez-le avec votre colis."),
    _ferme_spec(
        "demo.aveyron.maraicher", "Les Jardins de l'Ondes", A.MARAICHER,
        M.AB, "12000", "Chemin des Berges, Vallon des Ondes",
        "Rodez", 44.561, 2.575, "05 65 00 00 05",
        "Maraîchage biologique sur les hauteurs de Rodez : légumes de "
        "saison, salades et herbes, paniers hebdomadaires.",
        Decimal("2.40"),
        [{"activite": A.MARAICHER, "limite": 20},
         {"activite": A.APICULTEUR, "limite": 2}],
        [("Marché couvert de Rodez", "Place du Foirail",
          "Rodez", "12000", 44.352, 2.573)],
        [(6, "08:00", "12:30", 0), (4, "16:30", "19:00", 0)],
        "Retour des épinards d'hiver et des mâches.",
        "Paniers de la semaine aux Jardins de l'Ondes",
        "Légumes racines, choux et salades d'hiver du Rouergue. "
        "Paniers de 5 ou 8 € à retirer au Foirail."),
    # ── Aude (1) ──────────────────────────────────────────────────
    _ferme_spec(
        "demo.aude.apiculteur", "Ruchers de la Clamoux", A.APICULTEUR,
        M.AB, "11170", "Vallée de la Clamoux, lieu-dit La Prade",
        "Caunes-Minervois", 43.336, 2.531, "04 68 00 00 06",
        "Ruchers d'altitude sur les contreforts de la Montagne Noire : "
        "miels de garrigue, châtaignier et fleurs de printemps, cires "
        "et pollens, en bio.",
        Decimal("4.00"),
        [{"activite": A.APICULTEUR, "limite": 20},
         {"activite": A.ARBORICULTEUR, "categorie": "Fruits", "limite": 4}],
        [("Marché de Caunes", "Place de la Halle",
          "Caunes-Minervois", "11170", 43.335, 2.530)],
        [(3, "16:00", "19:00", 0)],
        "Récolte de miel de châtaignier — berlingots disponibles.",
        "Miel de la semaine aux Ruchers de la Clamoux",
        "Miels de garrigue et de châtaignier du Minervois, cire "
        "d'abeille et pollen frais. Vente au marché le mercredi."),
    # ── Hérault (1) ───────────────────────────────────────────────
    _ferme_spec(
        "demo.herault.arboriculteur", "Les Oliviers du Vic", A.ARBORICULTEUR,
        M.RAISONNE, "34500", "Chemin du Vic, lieu-dit Le Puech",
        "Béziers", 43.343, 3.221, "04 67 00 00 07",
        "Oliviers et vergers du Biterrois : huile d'olive de la "
        "première pression, olives de table, pêches et abricots "
        "de pleine saison, en agriculture raisonnée.",
        Decimal("2.10"),
        [{"activite": A.ARBORICULTEUR, "limite": 20},
         {"activite": A.APICULTEUR, "limite": 3},
         {"activite": A.ELEVEUR, "categorie": "Œufs", "limite": 3}],
        [("Les Halles de Béziers", "Place Pierre-Pascal",
          "Béziers", "34500", 43.341, 3.218)],
        [(5, "08:00", "12:00", 0)],
        "Nouvelle huile d'olive AOC — tombée début novembre.",
        "Récolte de la semaine aux Oliviers du Vic",
        "Huile d'olive nouvelle, olives cassées et pêches de vigne. "
        "Œufs du jour et miel de garrigue en complément."),
    # ── Haute-Garonne (1) ─────────────────────────────────────────
    _ferme_spec(
        "demo.toulouse.fromager", "Ferme du Lauragais", A.FROMAGER,
        M.PAYSAN, "31250", "Route de Sorèze, lieu-dit Lacombe",
        "Revel", 43.460, 2.004, "05 61 00 00 08",
        "Ferme du Lauragais au bord du lac de Saint-Ferréol : tomme de "
        "vache, fromages frais et yaourts au lait cru, fabrication "
        "à la ferme deux fois par jour.",
        Decimal("5.00"),
        [{"activite": A.FROMAGER, "limite": 18},
         {"activite": A.APICULTEUR, "limite": 2},
         {"activite": A.ELEVEUR, "categorie": "Œufs", "limite": 2}],
        [("Halle de Revel", "Place de la Halle",
          "Revel", "31250", 43.455, 2.007)],
        [(6, "09:00", "12:00", 0), (2, "17:00", "19:00", 0)],
        "Yaourts au lait cru à la vanille — fabrication du samedi.",
        "Fromages de la semaine à la Ferme du Lauragais",
        "Tomme de vache du Lauragais, fromage frais et yaourts. "
        "La traite du soir, c'est à 17 h : venez y goûter !"),
    # ── Tarn-et-Garonne (1) ───────────────────────────────────────
    _ferme_spec(
        "demo.montauban.maraicher", "Jardins du Tarn-et-Garonne",
        A.MARAICHER, M.PERMA, "82000", "Chemin de Sapiac",
        "Montauban", 44.017, 1.355, "05 63 00 00 09",
        "Maraîchage en permaculture dans la plaine du Tarn : légumes "
        "de saison, aromatiques et petits fruits, paniers et marché "
        "de Montauban.",
        Decimal("2.30"),
        [{"activite": A.MARAICHER, "limite": 18},
         {"activite": A.ARBORICULTEUR, "categorie": "Fruits", "limite": 5},
         {"activite": A.APICULTEUR, "limite": 2}],
        [("Marché de Sapiac", "Marché couvert de Sapiac",
          "Montauban", "82000", 44.012, 1.348)],
        [(6, "08:00", "12:00", 0), (3, "16:30", "19:00", 0)],
        "Choux-fleurs et brocolis — pleine saison.",
        "Paniers de la semaine aux Jardins du Tarn-et-Garonne",
        "Légumes d'automne de la plaine : choux, poireaux, salades. "
        "Pommes et poires du verger en supplément du panier."),
    # ── Bretagne (2) ──────────────────────────────────────────────
    _ferme_spec(
        "demo.brest.maraicher", "Jardins de l'Élorn", A.MARAICHER, M.AB,
        "29000", "Route de Landerneau, lieu-dit Kerivad",
        "Quimper", 47.996, -4.108, "02 98 00 00 10",
        "Maraîchage bio en bord d'Élorn : choux-fleurs, artichauts, "
        "poireaux et pommes de terre de primeur, le goût du "
        "littoral breton.",
        Decimal("2.60"),
        [{"activite": A.MARAICHER, "limite": 20},
         {"activite": A.ELEVEUR, "categorie": "Œufs", "limite": 3},
         {"activite": A.APICULTEUR, "limite": 2}],
        [("Marché de Quimper", "Place du Jubilé",
          "Quimper", "29000", 47.997, -4.100)],
        [(5, "08:00", "12:30", 0)],
        "Artichauts bretons primeurs — arrive en quantité cette semaine.",
        "Paniers de la semaine aux Jardins de l'Élorn",
        "Choux-fleurs, artichauts et poireaux du Finistère. Œufs "
        "de pleines mer du vendredi, beurre demi-sel de la ferme."),
    _ferme_spec(
        "demo.rennes.eleveur", "Ferme de la Vilaine", A.ELEVEUR, M.RAISONNE,
        "35600", "Les Rives de la Vilaine, lieu-dit Tréhan",
        "Redon", 47.652, -2.083, "02 99 00 00 11",
        "Élevage bovin en agriculture raisonnée dans la vallée de la "
        "Vilaine : veaux, bœufs et porc de la ferme, colis et "
        "vente directe.",
        Decimal("5.80"),
        [{"activite": A.ELEVEUR, "limite": 18},
         {"activite": A.FROMAGER, "limite": 5}],
        [("Marché de Redon", "Place de la République",
          "Redon", "35600", 47.650, -2.080)],
        [(6, "08:30", "12:30", 0)],
        "Colis de bœuf : commandes avant le vendredi midi.",
        "Viande de la semaine à la Ferme de la Vilaine",
        "Colis de bœuf et de veau de la vallée de la Vilaine ; "
        "tomme fermière et fromage frais en complément du colis."),
    # ── Loire (2) ─────────────────────────────────────────────────
    _ferme_spec(
        "demo.loire.maraicher", "Jardins du Gier", A.MARAICHER, M.PERMA,
        "42400", "Rue du Gier, lieu-dit Montferré",
        "Saint-Chamond", 45.473, 4.522, "04 77 00 00 12",
        "Maraîchage en permaculture dans la vallée du Gier : légumes "
        "de saison et aromatiques, paniers hebdomadaires à "
        "Saint-Chamond et Saint-Étienne.",
        Decimal("2.50"),
        [{"activite": A.MARAICHER, "limite": 18},
         {"activite": A.ARBORICULTEUR, "categorie": "Fruits", "limite": 5},
         {"activite": A.APICULTEUR, "limite": 2}],
        [("Marché de Saint-Chamond", "Place de la Halle",
          "Saint-Chamond", "42400", 45.470, 4.530),
         ("Marché de Saint-Étienne", "Grand Marché de Carnot",
          "Saint-Étienne", "42000", 45.439, 4.387)],
        [(6, "08:00", "12:00", 0), (5, "08:00", "12:00", 1)],
        "Cardons et blettes du Gier, spécialités foréziennes.",
        "Paniers de la semaine aux Jardins du Gier",
        "Légumes de la vallée du Gier : cardons, blettes, poireaux. "
        "Pommes du Pilat et miel de sapin en supplément."),
    _ferme_spec(
        "demo.loire.apiculteur", "Ruchers du Pilat", A.APICULTEUR, M.AB,
        "42220", "Route du Pilat, lieu-dit Les Sellières",
        "Bourg-Argental", 45.322, 4.292, "04 77 00 00 13",
        "Ruchers d'altitude dans le parc naturel du Pilat : miels de "
        "sapin, d'acacia et de montagne, gelée royale et propolis, "
        "en agriculture biologique.",
        Decimal("5.20"),
        [{"activite": A.APICULTEUR, "limite": 20},
         {"activite": A.ARBORICULTEUR, "categorie": "Fruits", "limite": 4}],
        [("Marché de Bourg-Argental", "Place de la Halle",
          "Bourg-Argental", "42220", 45.320, 4.290)],
        [(3, "16:00", "19:00", 0)],
        "Miel de sapin du Pilat — récolte d'altitude exceptionnelle.",
        "Miel de la semaine aux Ruchers du Pilat",
        "Miels de sapin et d'acacia du massif du Pilat, pollen et "
        "propolis. Pommes des vergers voisins en supplément."),
    # ── Corse (2) ─────────────────────────────────────────────────
    _ferme_spec(
        "demo.corse.eleveur", "Bergerie de Restonica", A.ELEVEUR, M.PAYSAN,
        "20250", "Route de la Restonica, lieu-dit Talcu",
        "Corte", 42.309, 9.148, "04 95 00 00 14",
        "Bergerie transhumante de la vallée de la Restonica : agneaux "
        "de lait, brocciu et charcuterie de montagne, les saveurs "
        "de la Corse de l'intérieur.",
        Decimal("7.00"),
        [{"activite": A.ELEVEUR, "limite": 18},
         {"activite": A.FROMAGER, "limite": 6},
         {"activite": A.APICULTEUR, "limite": 2}],
        [("Marché de Corte", "Place Paoli",
          "Corte", "20250", 42.306, 9.150)],
        [(5, "08:00", "12:00", 0)],
        "Brocciu frais de la traite du matin — du mardi au vendredi.",
        "Produits de la semaine à la Bergerie de Restonica",
        "Brocciu AOP, agneau de lait et figatellu de la vallée. "
        "Miel de maquis de nos ruchers d'altitude en supplément."),
    _ferme_spec(
        "demo.corse.fromager", "Fromagerie de Balagne", A.FROMAGER, M.AB,
        "20260", "Route de Calenzana, lieu-dit Spano",
        "Calvi", 42.569, 8.762, "04 95 00 00 15",
        "Fromagerie de brebis en Balagne, entre mer et montagne : "
        "tomme corse, brin d'amour et fromages frais, en "
        "agriculture biologique.",
        Decimal("6.50"),
        [{"activite": A.FROMAGER, "limite": 18},
         {"activite": A.ELEVEUR, "categorie": "Œufs", "limite": 2}],
        [("Port de Calvi", "Quai des Pêcheurs (étal été)",
          "Calvi", "20260", 42.570, 8.760)],
        [(6, "09:00", "12:30", 0)],
        "Brin d'amour affiné 2 mois — lot limité.",
        "Fromages de la semaine à la Fromagerie de Balagne",
        "Tomme corse et brin d'amour de la Balagne, fromage frais "
        "du vendredi. Œufs de la ferme voisine en supplément."),
    # ── La Réunion (2) ────────────────────────────────────────────
    _ferme_spec(
        "demo.reunion.maraicher", "Légumes des Hauts", A.MARAICHER, M.AB,
        "97410", "Chemin des Manguiers, Les Savannahs",
        "Saint-Pierre", -21.339, 55.478, "06 92 00 00 16",
        "Maraîchage bio sur les hauts de Saint-Pierre : chouchous, "
        "brèdes, piments et légumes créoles, paniers du terroir "
        "réunionnais.",
        Decimal("3.00"),
        [{"activite": A.MARAICHER, "limite": 20},
         {"activite": A.ARBORICULTEUR, "categorie": "Fruits", "limite": 5}],
        [("Marché forain de Saint-Pierre", "Terrain de l'Est",
          "Saint-Pierre", "97410", -21.340, 55.480)],
        [(6, "07:00", "11:00", 0), (3, "16:00", "18:00", 0)],
        "Chouchous des hauts — pleine récolte cette semaine.",
        "Paniers de la semaine aux Légumes des Hauts",
        "Brèdes songes, chouchous, piments et légumes créoles de "
        "La Réunion. Mangues et ananas Victoria du jardin en "
        "supplément du panier."),
    _ferme_spec(
        "demo.reunion.arboriculteur", "Vanilleraie de Sainte-Suzanne",
        A.ARBORICULTEUR, M.RAISONNE, "97441", "Chemin de la Vanilleraie",
        "Sainte-Suzanne", -20.906, 55.612, "06 92 00 00 17",
        "Vanilleraie et verger tropical au pied de la Rivière du "
        "Mât : gousses de vanille Bourbon, ananas Victoria et "
        "fruits de la passion, préparés à la ferme.",
        Decimal("3.50"),
        [{"activite": A.ARBORICULTEUR, "limite": 15},
         {"activite": A.APICULTEUR, "limite": 3}],
        [("Marché de Saint-André", "Champ Bazar",
         "Saint-André", "97490", -20.960, 55.650)],
        [(5, "07:30", "11:30", 0)],
        "Ananas Victoria mûres — récolte du jeudi.",
        "Récolte de la semaine à la Vanilleraie de Sainte-Suzanne",
        "Gousses de vanille Bourbon préparées à la ferme, ananas "
        "Victoria et fruits de la passion. Miel de fleurs tropicales "
        "des ruches du jardin."),
    # ── Martinique (2) ────────────────────────────────────────────
    _ferme_spec(
        "demo.martinique.maraicher", "Jardins Créoles du Lamentin",
        A.MARAICHER, M.AB, "97232", "Route de Duclos, lieu-dit La Jetée",
        "Le Lamentin", 14.610, -60.941, "06 96 00 00 18",
        "Maraîchage bio en plein cœur de la Martinique : ignames, "
        "dachines, christophines et légumes créoles, paniers "
        "ékotè et marché du Lamentin.",
        Decimal("3.20"),
        [{"activite": A.MARAICHER, "limite": 18},
         {"activite": A.APICULTEUR, "limite": 3}],
        [("Marché du Lamentin", "Place du Marché Couvert",
          "Le Lamentin", "97232", 14.608, -60.939)],
        [(6, "07:00", "11:00", 0), (4, "15:30", "18:00", 0)],
        "Ignames pays — récolte fraîche du jour.",
        "Paniers de la semaine aux Jardins Créoles",
        "Ignames, dachines, christophines et légumes créoles du "
        "Lamentin. Miel de fleurs de canne des ruches de la "
        "habitation voisine."),
    _ferme_spec(
        "demo.martinique.eleveur", "Élevage des Trois-Îlets",
        A.ELEVEUR, M.PAYSAN, "97229", "Route d'Anse à l'Âne",
        "Les Trois-Îlets", 14.541, -61.031, "06 96 00 00 19",
        "Élevage paysan face à la baie de Fort-de-France : porc "
        "créole, volailles de plein air et produits de la ferme "
        "transformés sur place.",
        Decimal("5.50"),
        [{"activite": A.ELEVEUR, "limite": 16},
         {"activite": A.APICULTEUR, "limite": 2}],
        [("Marché des Trois-Îlets", "Place des Artisans",
          "Les Trois-Îlets", "97229", 14.540, -61.035)],
        [(5, "08:00", "12:00", 0)],
        "Poulets de plein air — commande avant le jeudi.",
    # ── Micro-brasseries (mode boutique / stock à date) ───────────
    _ferme_spec(
        "demo.brasserie.sor", "Brasserie du Sor", A.MICRO_BRASSEUR, M.AB,
        "81600", "Route de Cordes, lieu-dit Les Chais",
        "Gaillac", 43.898, 1.898, "05 63 00 00 20",
        "Micro-brasserie bio au bord du Sor : blondes, ambrées, IPA et "
        "bières de saison brassées en petits lots, fûts et bouteilles "
        "en vente directe à la boutique de la brasserie.",
        Decimal("4.00"),
        [{"activite": A.MICRO_BRASSEUR, "limite": 18},
         {"activite": A.APICULTEUR, "limite": 2}],
        [("Boutique de la brasserie", "Route de Cordes",
          "Gaillac", "81600", 43.897, 1.899),
         ("Marché de Gaillac", "Place du marché couvert",
          "Gaillac", "81600", 43.900, 1.895)],
        [(5, "16:00", "19:30", 0), (6, "08:30", "12:30", 1)],
        "Nouvelle IPA aux houblons du Tarn — série limitée !",
        "Bières de la semaine à la Brasserie du Sor",
        "L'IPA aux houblons locaux arrive en fûts et en bouteilles ; "
        "la rousse de garde et la blanche restent disponibles toute la "
        "semaine en boutique. Miel de bruyère de la ferme voisine."),
    _ferme_spec(
        "demo.brasserie.leguer", "Brasserie du Léguer", A.MICRO_BRASSEUR,
        M.RAISONNE, "22300", "Quai du Léguer, zone du Rosmeur",
        "Lannion", 48.732, -3.478, "02 96 00 00 21",
        "Micro-brasserie lannionnaise en agriculture raisonnée : "
        "blondes et brunes maltées, weizen épicée et stout au blé noir, "
        "fûts 20 L pour les Associations et bouteilles en boutique.",
        Decimal("4.20"),
        [{"activite": A.MICRO_BRASSEUR, "limite": 18},
         {"activite": A.APICULTEUR, "limite": 2}],
        [("Boutique de la brasserie", "2 quai du Léguer",
          "Lannion", "22300", 48.733, -3.477)],
        [(3, "15:00", "19:00", 0), (5, "15:00", "19:00", 0)],
        "Stout au blé noir : le lot de novembre arrive en boutique.",
        "Bières de la semaine à la Brasserie du Léguer",
        "Blonde, ambrée et weizen en bouteilles et en fûts ; le stout "
        "au blé noir arrive mercredi. Miel de sarrasin des ruches de "
        "la baie de Lannion en complément."),
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
    help = ("Crée des données de démonstration fictives (Tarn et "
            "départements limitrophes, Bretagne, Loire, Corse, Réunion, "
            "Martinique ; clients, commandes et paniers). Idempotent ; "
            "--purge efface tout compte de démo, même d'un jeu plus "
            "ancien.")

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
            # Compte déjà présent : on s'assure au minimum qu'il porte
            # le badge démo, puis on passe (idempotence).
            Exploitant.objects.filter(
                user__username=spec["utilisateur"]
            ).update(est_demo=True)
            self.stdout.write(self.style.NOTICE(
                f"Compte {spec['utilisateur']} déjà présent : ferme "
                "ignorée (badge démo réappliqué)."))
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
        slugs_vus = set()
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
                # Les catalogues croisés peuvent contenir des produits
                # homonymes (ex. « Fraise » en maraîcher et en fruits) :
                # le slug du produit étant dérivé du nom, on ne garde
                # que le premier pour éviter la collision (exploitant,
                # slug).
                slug_produit = slugify(std.nom)
                if slug_produit in slugs_vus:
                    continue
                slugs_vus.add(slug_produit)
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
            f"🌾 {exploitant.nom_ferme} créée ({spec['ville']}, compte "
            f"{spec['utilisateur']}, mot de passe {MOT_DE_PASSE_DEMO}) : "
            f"{len(produits)} produits en "
            f"{exploitant.categories.count()} catégories, "
            f"{len(points)} point(s)."))
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
            # Purge LARGE : tout compte « demo.* », toute exploitation
            # marquée « démo » (même créée par un jeu plus ancien
            # aujourd'hui disparu de la liste) et les fermes du jeu
            # courant (au cas où un compte aurait été renommé).
            connus = ([s["utilisateur"] for s in FERMES]
                      + [s["utilisateur"] for s in CLIENTS])
            users = (User.objects.filter(username__startswith="demo.")
                     | User.objects.filter(exploitant__est_demo=True)
                     | User.objects.filter(
                         exploitant__nom_ferme__in=[
                             s["ferme"] for s in FERMES])
                     ).distinct()
            n, purges = 0, []
            for user in users:
                try:
                    n += user.delete()[0]
                    purges.append(user.username)
                except Exception as erreur:  # PROTECT éventuel
                    self.stdout.write(self.style.ERROR(
                        f"Impossible de supprimer {user.username} "
                        f"({erreur})."))
            if connus and not purges:
                self.stdout.write(self.style.NOTICE(
                    "Aucun compte de démo trouvé à purger."))
            elif purges:
                self.stdout.write(self.style.SUCCESS(
                    f"Comptes de démo supprimés : "
                    f"{', '.join(sorted(purges))} ({n} objet(s))."))
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
            self._commande(exploitant, produits, points[-1], None,
                           deux, Commande.Statut.VALIDEE, jours=5,
                           panier_statut=Panier.Statut.PRET)
            # 4. Panier livré (lecture seule) avec un ajustement
            ajuste = {pick(1).pk: Decimal("2")}  # 3 kg souhaités → 2 livrés
            self._commande(exploitant, produits, points[-1], clients[0],
                           trois, Commande.Statut.VALIDEE, jours=-2,
                           panier_statut=Panier.Statut.LIVRE,
                           quantite_livree=ajuste)
        self.stdout.write(self.style.SUCCESS(
            f"Démonstration prête : {len(FERMES)} fermes fictives "
            "(Tarn et départements limitrophes, Bretagne, Loire, Corse, "
            "Réunion, Martinique + 2 micro-brasseries en boutique) avec "
            f"{len(CLIENTS)} clients, commandes à valider, paniers en "
            "préparation, prêts et livrés (lecture seule)."))
        self.stdout.write("Connexion producteur : demo.maraicher, "
                          "demo.vergers, demo.fromager, etc. — mot de "
                          "passe " + MOT_DE_PASSE_DEMO)
