# 🌱 MonPetitMaraicher

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](LICENSE)

**Portail web libre de mise en relation et de gestion pour les maraîchers/producteurs locaux et leurs clients : vitrine, commandes, paniers hebdomadaires et communication directe (e-mail/SMS).**

Le producteur crée sa vitrine en ligne, publie ses récoltes et son planning de livraison, reçoit et gère ses commandes et ses clients (validation, paniers numérotés préparés pour chaque jour de livraison), et communique directement avec eux : newsletter de la semaine, annonce de la mise à disposition des paniers, validation des livraisons. Le client découvre les producteurs près de chez lui, commande ses paniers et suit ses livraisons.

> ⚠️ **État du projet** : V1 en cours de construction — la structure est posée, les fonctionnalités s'enrichissent itérativement. Contributions et retours terrain bienvenues !

## Pour qui ?

- 🧑‍🌾 **Les maraîchers et petits producteurs** : vitrine publique gratuite, catalogue illustré, récoltes hebdo, planning de livraison, gestion des commandes et de la communication client
- 🛒 **Les clients** : recherche par producteur, produit ou localisation, consultation libre sans compte, commande en quelques clics
- 🌍 **Les collectivités, AMAP et associations** : déployer une instance pour leur territoire — le code est libre et réplicable

## La page d'accueil

- un **bandeau** de navigation (logo, accès comptes) ;
- un bouton **« Chercher mon producteur ou un produit »** et un bouton **« Je suis producteur — rejoindre le réseau »** ;
- une **hero section** : présentation du portail, sa philosophie (circuits courts, indépendance des maraîchers, bien commun) et ses fonctionnalités clés ;
- une **carte de France** (Leaflet / OpenStreetMap) des producteurs **catégorisés par mode de production** — AB, permaculture, agriculture paysanne, raisonnée, conventionnelle — avec légende filtrante et **géolocalisation de l'utilisateur** pour recentrer la carte sur sa position.

## Fonctionnalités (cible V1/V2)

| Espace | Fonctions |
|---|---|
| **Public** | Landing avec carte des producteurs, recherche multi-critères (producteur, produit, ville, département, catégorie de production), pages publiques des fermes (logo, présentation, certification, produits, récolte de la semaine, points de livraison, créneaux) |
| **Maraîcher** | Inscription (SIRET, mode de production, logo, localisation, coordonnées carte) ; **catalogue produit illustré** : photo, description, unité de vente, **catégories personnalisables** (définies par le producteur) et **attributs libres** (variété, labels, saison…), possibilité de **créer des produits dédiés à son usage propre** ; saisie rapide des **dispos hebdo = estimations indicatives** (pas un stock : aucune commande n'est bloquée ni décomptée à ce stade) |
| **Commandes** | Commandes reçues via le portail **ou saisies par le producteur** (clients sans compte, achats sur place…) ; validation/refus ; **paniers numérotés** (n°1 à n°X par client, par jour de livraison selon le planning) ; **seules les quantités effectivement livrées dans les paniers sont décomptées** (suivi de production réel) ; marquage « livré / mis à disposition » ; **export comptable des paniers livrés** (CSV : produit, quantité, prix, date, client) |
| **Client** | Inscription, commande produits/quantités/date selon le planning, suivi et annulation des commandes, réception des annonces du producteur |
| **Communication** | Newsletter du producteur (récolte de la semaine, actualités), **annonce e-mail/SMS de la mise à disposition des paniers**, confirmations automatiques et **modèles de messages personnalisables** ; envoi via **le SMTP du producteur** (sa propre boîte mail) et **la passerelle SMS de son choix** — le portail ne s'interpose pas entre le producteur et ses clients |
| **Admin** | Back-office Django complet (`/admin/`) |

## Feuille de route

Le backlog détaillé est suivi dans les [issues du dépôt](https://github.com/cartotrac/MonPetitMaraicher/issues) :

- [ ] [#1 — Catalogue de produits standard embarqué (emojis/SVG libres) avec filtres](https://github.com/cartotrac/MonPetitMaraicher/issues/1)
- [ ] [#2 — Saisie directe de commandes par le producteur](https://github.com/cartotrac/MonPetitMaraicher/issues/2)
- [ ] [#3 — Communication producteur ↔ clients : newsletter, annonces, confirmations e-mail/SMS](https://github.com/cartotrac/MonPetitMaraicher/issues/3)
- [ ] [#4 — Vitrine producteur personnalisable](https://github.com/cartotrac/MonPetitMaraicher/issues/4)
- [ ] [#5 — Catégories personnalisables et attributs libres des produits (JSONB)](https://github.com/cartotrac/MonPetitMaraicher/issues/5)
- [ ] [#6 — Paniers numérotés par client et par jour de livraison](https://github.com/cartotrac/MonPetitMaraicher/issues/6)
- [ ] [#7 — Géocodage automatique des adresses + clustering carte](https://github.com/cartotrac/MonPetitMaraicher/issues/7)
- [ ] [#8 — Export comptable des paniers livrés (CSV)](https://github.com/cartotrac/MonPetitMaraicher/issues/8)
- [ ] [#9 — Écrans producteur : points de livraison et créneaux hebdo](https://github.com/cartotrac/MonPetitMaraicher/issues/9)

Plus loin : panier multi-producteurs, mutualisation par département / pays, automatisation du déploiement.

## Stack

Python 3.11+ · Django 5 · **PostgreSQL** (prod, champs JSONB pour les attributs personnalisés) / SQLite (dev et instance mono-ferme) · Leaflet + OpenStreetMap · templates HTML/CSS sobres · déploiement WSGI (AlwaysData compatible)

## Démarrage rapide

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py makemigrations portal && python manage.py migrate
python manage.py createsuperuser   # back-office /admin/
python manage.py runserver
```

## Déploiement

Voir [docs/DEPLOY_ALWAYSDATA.md](docs/DEPLOY_ALWAYSDATA.md) et les [décisions techniques](docs/DECISIONS.md).

## Licence

Logiciel libre sous **GNU AGPL-3.0** ([LICENSE](LICENSE) — version anglaise de référence) : déployez votre propre instance pour votre territoire, adaptez le code — toute instance publique modifiée doit partager ses modifications. Résumé en français : [LICENSE.fr.md](LICENSE.fr.md).

## Contribuer

Voir [CONTRIBUTING.md](CONTRIBUTING.md).
