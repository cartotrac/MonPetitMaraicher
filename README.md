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
- une **carte de France** (Leaflet / fond IGN) des producteurs **catégorisés par mode de production** — AB, permaculture, agriculture paysanne, raisonnée, conventionnelle — avec légende filtrante et **géolocalisation de l'utilisateur** pour recentrer la carte sur sa position.

## Fonctionnalités (cible V1/V2)

| Espace | Fonctions |
|---|---|
| **Public** | Landing avec carte des producteurs, recherche multi-critères (producteur, produit, ville, département, catégorie de production), pages publiques des fermes (logo, présentation, certification, produits, récolte de la semaine, équipe, points de livraison géolocalisés, créneaux, réseaux sociaux) |
| **Maraîcher** | Inscription (SIRET validé, mode de production, logo, localisation par clic carte) ; **catalogue produit illustré** édité **directement en mode édition du dashboard** (ajout, reclassement ▲▼, changement de catégorie, catégories personnalisables, attributs libres JSONB) ; **équipe multi-comptes** : le propriétaire administre (fiche, équipe, paramètres, catalogue standard), des membres rattachés au SIRET gèrent le courant |
| **Récoltes & dispo** | Saisie des **dispos hebdo = estimations** ; la page de commande affiche la **dispo restante de la semaine** (estimation − quantités déjà commandées) ; **sans récolte publiée, commande possible sur le catalogue** avec avertissement « quantités soumises à validation » |
| **Commandes** | Via le portail **ou saisies par le producteur** ; validation/refus ; **paniers numérotés n°1..X par jour et par point de livraison** ; commandes/paniers **regroupés par jour** (sections dépliables) côté maraîcher et client ; position du point **transmise au client** (adresse + lien carte) au passage en prêt/livré ; **export comptable des paniers livrés** (CSV) |
| **Client** | Commande **avec ou sans compte** (nom + téléphone obligatoires, e-mail optionnel pour la newsletter), mention « commandé à Nom de l'exploitation », suivi et annulation ; **identité vivante** : le profil mis à jour remonte rétroactivement dans commandes et paniers |
| **Communication** | Onglet **Publications** : newsletter de la semaine et annonces, diffusion e-mail ; **annonce SMS de la mise à disposition des paniers** ; envoi via **le SMTP propre à l'exploitation** (page Paramètres) et **la passerelle SMS de son choix** |
| **Paramètres** | Page unique **Ma ferme / Mon profil / Équipe / Messagerie** (SMTP + passerelle SMS par exploitation, propriétaire uniquement) |
| **Admin** | Back-office Django complet (`/admin/`) |

## Feuille de route

Le backlog détaillé est suivi dans les [issues du dépôt](https://github.com/cartotrac/MonPetitMaraicher/issues) :

- [x] [#1 — Catalogue de produits standard embarqué (emojis/SVG libres) avec filtres](https://github.com/cartotrac/MonPetitMaraicher/issues/1)
- [x] [#2 — Saisie directe de commandes par le producteur](https://github.com/cartotrac/MonPetitMaraicher/issues/2)
- [x] [#3 — Communication producteur ↔ clients : newsletter, annonces, confirmations e-mail/SMS](https://github.com/cartotrac/MonPetitMaraicher/issues/3) *(SMS : passerelle paramétrable, envoi à brancher)*
- [x] [#4 — Vitrine producteur personnalisable](https://github.com/cartotrac/MonPetitMaraicher/issues/4)
- [x] [#5 — Catégories personnalisables et attributs libres des produits (JSONB)](https://github.com/cartotrac/MonPetitMaraicher/issues/5)
- [x] [#6 — Paniers numérotés par jour de livraison et par point](https://github.com/cartotrac/MonPetitMaraicher/issues/6)
- [x] [#7 — Géocodage des adresses + carte (clic, Nominatim, fond IGN)](https://github.com/cartotrac/MonPetitMaraicher/issues/7) *(clustering à venir)*
- [ ] [#8 — Export comptable des paniers livrés (CSV)](https://github.com/cartotrac/MonPetitMaraicher/issues/8)
- [x] [#9 — Écrans producteur : points de livraison et créneaux hebdo](https://github.com/cartotrac/MonPetitMaraicher/issues/9)

Plus loin : panier multi-producteurs, mutualisation par département / pays, automatisation du déploiement.

## Stack

Python 3.11+ · Django 5 · **PostgreSQL** (prod, champs JSONB pour les attributs personnalisés) / SQLite (dev et instance mono-ferme) · Leaflet + **fond IGN Plan V2 sans clé** / ortho Esri · templates HTML/CSS sobres · déploiement WSGI (AlwaysData compatible)

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