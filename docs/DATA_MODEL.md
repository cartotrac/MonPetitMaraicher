# Structure de données définitive

> Document de référence pour l'évolution des modèles Django (`portal/models.py`).
> À valider avant l'écriture des migrations. Les modèles déjà en place en V1
> sont signalés **[V1]**, les ajouts prévus **[V2]** (issues #1–#9).

## Principes

1. **PostgreSQL** en prod : les attributs libres utilisent des champs **JSONB**
   (SQLite accepté en mono-ferme : Django dégrade `JSONField` en texte — OK,
   aucun filtrage avancé requis sur ces attributs).
2. **Quantités hebdo = estimations** : aucun décompte à la commande.
   Seules les quantités **livrées dans les paniers** sont décomptées.
3. **Catalogues par producteur** : chacun possède ses catégories et produits ;
   le catalogue standard embarqué n'est qu'un point de départ copiable.
4. **Prix et quantités figés à la commande** : modifier un produit n'altère
   jamais l'historique.
5. **Volumes fichiers maîtrisés** (voir § Médias) : l'illustration par défaut
   est l'emoji/SVG du catalogue standard — une ferme complète doit pouvoir
   tourner **sans aucun fichier importé**.
6. **Maximum de process côté navigateur** (voir § Front) : le serveur stocke
   et valide, le navigateur calcule, filtre et compresse.
7. **Données client minimales** : l'exploitant ne voit les coordonnées d'un
   client que pour les paniers **livrés** (voir § Données personnelles) ;
   il ne reçoit que les commandes et infos associées à ses clients, jamais
   la base client du portail.
8. **Paramétrage hebdo par l'exploitant** : la récolte publiée chaque semaine
   détermine ce qui est visible ; ses modalités d'échange (modèles de
   messages, préférences) ne changent que s'il les modifie.

## Catalogue

### ProductCategory **[V2 — issue #5]**

Catégories **définies par chaque producteur** (remplacent le champ texte `category` de Product).

| Champ | Type | Notes |
|---|---|---|
| producer | FK Producer, CASCADE | `related_name="categories"` |
| name | Char(80) | ex : « Légumes d'hiver » |
| slug | Slug(100) | auto, unique par producteur |
| position | PositiveSmallInt | tri d'affichage |

`unique_together = ("producer", "name")`

### Product **[V1 → évolué en V2]**

| Champ | Type | Notes |
|---|---|---|
| category | FK ProductCategory, SET_NULL, null | remplace le champ texte |
| attributes | JSONField, default dict | attributs libres : `{"variété": "Butternut", "label": "AB", "saison": ["été"]}` — JSONB |
| from_standard | FK StandardProduct, SET_NULL, null | traçabilité de la copie |
| is_custom | Boolean | produit créé pour l'usage propre du producteur |
| emoji | Char(8), blank | illustration embarquée héritée du produit standard |
| svg | Text, blank | SVG inline optionnel (embarqué, licence libre) |
| photo | ImageField, **null/blank** | optionnelle, redimensionnée/compressée côté navigateur avant envoi |
| price | Decimal(6,2) | prix de référence |

### StandardProduct **[V2 — issue #1]**

Catalogue standard embarqué (~80–120 produits types), en données de départ
(fixture/migration), **lecture seule** pour les producteurs.

| Champ | Type | Notes |
|---|---|---|
| name | Char(150) unique | « Carotte » |
| category | Char(80) | catégorie standard simple |
| unit | Char(2) choices | kg / pièce / botte / barquette |
| seasons | JSONField | `["printemps", "été"]` → filtre saison |
| emoji | Char(8) | 🥕 — zéro dépendance, zéro fichier |
| svg | Text, blank | SVG inline optionnel |

Filtres (navigateur) : catégorie, saison, recherche nom. Copie à cocher →
`Product.objects.create(from_standard=…)`.

## Récoltes et paniers

### HarvestWeek **[V1 → complétée]**

| Champ ajouté | Type | Notes |
|---|---|---|
| is_published | Boolean, default False | **paramétrage hebdo** : la récolte n'est visible côté client que publiée ; l'exploitant peut préparer la semaine à l'avance puis publier |

### HarvestItem **[V1]**

Inchangés : estimations hebdo, prix par ligne, aucune réservation de stock.

### Basket **[V2 — issues #2, #6, #8]**

Panier **numéroté**, préparé pour un client, un jour de livraison.

| Champ | Type | Notes |
|---|---|---|
| producer | FK Producer, CASCADE | |
| client | FK User, SET_NULL, null | null si client sans compte (saisie producteur) |
| client_name | Char(150) | figé à la création |
| number | PositiveSmallInt | **n°1..X par client et par jour** |
| delivery_date | Date, indexé | jour de livraison réel |
| delivery_slot / delivery_point | FK, SET_NULL, null | |
| order | FK Order, SET_NULL, null | commande portail d'origine, null si saisie directe |
| status | Choices | `PREPARING` / `READY` / `DELIVERED` / `COLLECTED` |
| total | Decimal(8,2) | |

`unique_together = ("producer", "client", "delivery_date", "number")`

### BasketItem **[V2]**

Contenu **effectivement livré** — source du décompte de production.

| Champ | Type | Notes |
|---|---|---|
| basket | FK Basket, CASCADE | `related_name="items"` |
| product | FK Product, PROTECT | |
| quantity | Decimal(8,2) | quantité réellement mise dans le panier |
| unit_price | Decimal(6,2) | prix figé à la livraison |

**Export comptable CSV** (issue #8) : produit, quantité, prix, total, date,
client — uniquement `DELIVERED / COLLECTED`.

### Order / OrderItem **[V1]**

Évolutions mineures :

- `created_by_producer = Boolean` pour les saisies directes (issue #2) ;
- validation d'une commande → un `Basket` pré-rempli est proposé
  (ajustable), la commande ne décompte rien ;
- `OrderItem` figé (historique), ajustements dans `BasketItem`.

## Livraison

### DeliveryPoint / DeliverySlot **[V1]**

Inchangés. Écrans producteur prévus (issue #9).

## Communication **[V2 — issue #3]**

L'exploitant garde ses modalités d'échange par défaut ; il ne les modifie
que s'il le souhaite.

### MessageTemplate

| Champ | Type | Notes |
|---|---|---|
| producer | FK, CASCADE | `unique_together ("producer", "kind")` |
| kind | Choices | `ORDER_CONFIRM` / `BASKET_READY` / `DELIVERY_DONE` / `NEWSLETTER` / `ANNOUNCEMENT` |
| subject | Char(200) | |
| body | Text | placeholders `{{ client }}`, `{{ panier }}`, `{{ ferme }}`, `{{ creneau }}` |
| channel | Choices | `EMAIL` / `SMS` |
| is_active | Boolean | fallback sur le défaut si modèle cassé |

### Newsletter / Announcement

| Modèle | Champs | Notes |
|---|---|---|
| Newsletter | producer, week_start (FK HarvestWeek nullable), subject, body, sent_at | aux clients abonnés |
| Announcement | producer, subject, body, sent_at | annonce ponctuelle (paniers dispo…) |

### ContactPreference

| Champ | Type | Notes |
|---|---|---|
| client | FK User, CASCADE | `unique_together ("client", "producer")` |
| producer | FK Producer, CASCADE | |
| wants_newsletter / wants_announcements | Boolean, default True | |
| channel | Choices | `EMAIL` / `SMS` / `BOTH` |

### ProducerMessagingConfig

SMTP et passerelle SMS **du producteur** (jamais centralisés) : smtp_*,
sms_provider + sms_config (JSON, credentials chiffrés), daily_quota,
quiet_hours. Cf. version précédente.

## Vitrine **[V2 — issue #4]**

### ProducerSiteSettings

| Champ | Type | Notes |
|---|---|---|
| producer | OneToOne Producer | |
| hero_title / hero_text | Char/Text | personnalisables |
| theme_color | Char(7) | #RRGGBB |
| banner_image | Image, **null/blank** | optionnelle, compressée côté navigateur |
| show_harvest / show_catalog / show_slots | Boolean | sections visibles |
| social_links | JSONField | `{"facebook": "…"}` |

## Médias : maîtrise des volumes

Objectif : **une instance entière doit rester légère**, même avec des
dizaines de producteurs.

- **Défaut zéro fichier** : emoji/SVG inline (catalogue standard) — une ferme
  sans logo ni photo fonctionne à l'identique, avec un avatar emoji 🌱
  généré par défaut.
- Logo/banner/photo **optionnels** ; s'ils existent :
  - compression **dans le navigateur** avant upload (Canvas API :
    max 512 px de côté, JPEG qualité ~0.8, cible < 100 Ko) ;
  - contrôle serveur en second recours (rejet > 300 Ko).
- Pas de stockage de documents (catalogues produits en base + JSON, pas en
  fichiers) ; export/import JSON pour la portabilité.
- Nettoyage : toute image orpheline (produit supprimé) purgée.

## Front : maximum de process dans le navigateur

Le serveur Django **stocke, authentifie et valide** ; le navigateur client
fait le reste, en JavaScript vanilla (pas de framework, décision maintenue) :

- filtres catalogue (catégorie, saison, recherche) **côté client** sur le
  JSON servi une seule fois ;
- **calcul du panier en direct** (totaux, quantités) dans le navigateur ;
  le serveur ne fait qu'une validation des prix/poids à la soumission ;
- compression d'images avant upload (Canvas) ;
- carte Leaflet : filtrage et clustering des marqueurs localement.

Bénéfices : moins de trafic serveur, réactivité, et un portail utilisable
sur les connexions rurales lentes.

## Données personnelles : partage minimal avec l'exploitant

- Les coordonnées complètes d'un client (e-mail, téléphone, adresse)
  restent **côté portail** ; l'exploitant ne voit, pour un panier donné, que
  le **nom** (nécessaire à la numérotation) tant que le panier n'est pas livré.
- Au passage `DELIVERED / COLLECTED`, un **instantané** `client_contact`
  (JSON : e-mail/tél. selon le canal choisi) est copié dans le `Basket` :
  l'exploitant détient alors l'historique de ses livraisons avec les infos
  clients associées, en base, liées à son exploitation.
- L'exploitant **ne peut pas** lister ni exporter l'ensemble des clients du
  portail : il ne reçoit que les commandes et infos liées à ses propres
  paniers.
- RGPD : finalité explicite (exécution de la commande), durée de conservation
  paramétrable, droit d'accès/effacement côté portail.

## Historique des modifications

| Version | Changement |
|---|---|
| 0.1 | Première rédaction |
| 0.2 | Volumes maîtrisés, process navigateur, données client partagées à la livraison, publication hebdo (retours Julien) |
