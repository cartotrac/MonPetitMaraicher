# Décisions techniques

Choix actés pour MonPetitMaraicher. Ce document garde la trace des décisions et de leur raison d'être — le modifier quand une décision évolue.

## Licence : GNU AGPL-3.0

Anti-fourke fermée et bien commun : toute instance publique modifiée doit partager ses modifications. `LICENSE` = texte anglais de référence ; `LICENSE.fr.md` = résumé non contraignant à visée pédagogique.

## Stack : Django 5, templates classiques

Python 3.11+ / Django 5, templates HTML/CSS sobres, **pas de framework front**. Back-office : l'admin Django. Objectif : maintenable par des contributeurs backend, léger à héberger.

## Base de données : PostgreSQL en prod, SQLite en mono-ferme

- **PostgreSQL** (natif AlwaysData) pour les instances mutualisées : champs **JSONB** pour les attributs personnalisés des produits.
- **SQLite** acceptable pour une instance mono-ferme (Raspberry Pi, très petit hébergement) : base = un fichier, sauvegardable/copiable d'un coup.
- **MySQL n'est pas supporté** — choix volontaire.
- **Pas de stockage fichier primaire** pour items/catégories : la portabilité est assurée par **export/import JSON** des catalogues (bien commun, migration d'instance à l'autre).

## Quantités hebdo = estimations, pas un stock

Les quantités saisies par le producteur sont **indicatives**. Aucune commande n'est bloquée ni décomptée à la validation. **Seules les quantités effectivement livrées dans les paniers sont décomptées** (suivi de production réel). Les paniers sont **numérotés 1..X par client, par jour de livraison**.

## Commandes : portail + saisie producteur

Les commandes arrivent via le portail **ou sont saisies directement par le producteur** (clients sans compte, achats sur place). Export comptable CSV des paniers livrés.

## Communication : SMTP et SMS du producteur

Newsletter, annonce de mise à dispo, confirmations e-mail/SMS : modèles **automatiques et personnalisables** (éditables par le producteur), envoyés via **le SMTP du producteur** et **la passerelle SMS de son choix**. Le portail ne s'interpose pas entre le producteur et ses clients.

## Catalogue standard embarqué

Un **catalogue de ~80–120 produits types** est embarqué avec des **illustrations emojis/SVG** incluses au dépôt : choix explicite — **zéro dépendance externe, zéro contrainte de licence** (pas Wikimedia). Filtres catégorie/saison/nom ; le producteur copie en cochant les produits qu'il veut dans son catalogue personnel, et peut créer ses propres produits.

## Cartographie : Leaflet + OpenStreetMap

Carte Leaflet/OSM, producteurs catégorisés par mode de production (AB, permaculture, agriculture paysanne, raisonnée, conventionnelle), légende filtrante, géolocalisation navigateur. Géocodage automatique des adresses et clustering des marqueurs prévus (issue #7).
