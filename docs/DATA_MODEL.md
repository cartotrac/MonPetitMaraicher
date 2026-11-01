# Structure de données définitive

> Document de référence pour l'évolution des modèles Django (`portal/models.py`).
> À valider avant l'écriture des migrations. Les modèles déjà en place en V1
> sont signalés **[V1]**, les ajouts prévus **[V2]** (issues #1–#9).

## Principes

- **PostgreSQL** en prod : les attributs libres utilisent des champs **JSONB**
  (SQLite accepté en mono-ferme : Django dégrade `JSONField` en texte — OK,
  aucun filtrage avancé requis sur ces attributs).
- Les quantités hebdo sont des **estimations** : aucun décompte à la commande.
  Seules les quantités **livrées dans les paniers** sont décomptées.
- Chaque producteur possède **ses propres catégories et produits** ; le
  catalogue standard embarqué n'est qu'un **point de départ copiable**.
- Les prix et quantités sont **figés** (copie) au moment de la commande :
  modifier un produit n'altère jamais l'historique.

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

Évolutions du modèle existant :

| Champ | Type | Notes |
|---|---|---|
| category | FK ProductCategory, SET_NULL, null | remplace le champ texte |
| attributes | JSONField, default dict | attributs libres : `{"variété": "Butternut", "label": "AB", "saison": ["été", "automne"]}` — stockés en JSONB |
| from_standard | FK StandardProduct, SET_NULL, null | traçabilité de la copie depuis le catalogue standard |
| is_custom | Boolean | produit créé pour l'usage propre du producteur |
| price | Decimal(6,2) | prix de référence (peut être surchargé par ligne de récolte) |

### StandardProduct **[V2 — issue #1]**

Catalogue standard embarqué (~80–120 produits types), en données de départ
(fixture/migration), **pas éditable par les producteurs** (lecture seule).

| Champ | Type | Notes |
|---|---|---|
| name | Char(150) unique | « Carotte » |
| category | Char(80) | « Légumes racines » (catégorie standard simple) |
| unit | Char(2) choices | kg / pièce / botte / barquette |
| seasons | JSONField | `["printemps", "été", "automne"]` → filtre saison |
| emoji | Char(8) | illustration embarquée 🥕 (zéro dépendance) |
| svg | Text, blank | SVG inline optionnel (embarqué, licence libre) |

Filtres côté vitrine standard : catégorie, saison, recherche nom.
Copie : écran à cases à cocher → `Product.objects.create(from_standard=…)`
par producteur.

## Récoltes et paniers

### HarvestWeek / HarvestItem **[V1]**

Inchangés : estimations hebdo, prix par ligne, aucune réservation de stock.

### Basket **[V2 — issues #2, #6, #8]**

Panier **numéroté**, préparé pour un client, un jour de livraison.

| Champ | Type | Notes |
|---|---|---|
| producer | FK Producer, CASCADE | |
| client | FK User, SET_NULL, null | null si commande saisie par le producteur pour un client sans compte |
| client_name | Char(150) | figé : nom affiché même si le compte disparaît |
| number | PositiveSmallInt | **n°1..X par client et par jour** — calculé : (dernier n° du couple client/jour) + 1 |
| delivery_date | Date, indexé | jour de livraison réel |
| delivery_slot | FK DeliverySlot, SET_NULL, null | créneau associé |
| delivery_point | FK DeliveryPoint, SET_NULL, null | |
| order | FK Order, SET_NULL, null | commande d'origine si portail ; null si saisie directe |
| status | Choices | `PREPARING` / `READY` / `DELIVERED` / `COLLECTED` |
| total | Decimal(8,2) | |

`unique_together = ("producer", "client", "delivery_date", "number")`

### BasketItem **[V2]**

Contenu **effectivement livré** — c'est LA source du décompte de production.

| Champ | Type | Notes |
|---|---|---|
| basket | FK Basket, CASCADE | `related_name="items"` |
| product | FK Product, PROTECT | |
| quantity | Decimal(8,2) | quantité réellement mise dans le panier |
| unit_price | Decimal(6,2) | prix figé à la livraison |

**Export comptable CSV** (issue #8) : produit, quantité, prix, total, date de
livraison, client — uniquement `status = DELIVERED / COLLECTED`.

### Order / OrderItem **[V1]**

Évolutions mineures :

- `order` peut être `null` côté client → `created_by_producer = True` pour
  les saisies directes (issue #2) ;
- à la validation d'une commande, un `Basket` pré-rempli est proposé
  (contenu copiable/ajustable) — la commande ne décompte rien ;
- `OrderItem` reste figé (historique), les ajustements se font dans `BasketItem`.

## Livraison

### DeliveryPoint / DeliverySlot **[V1]**

Inchangés. Écrans producteur dédiés prévus (issue #9).

## Communication **[V2 — issue #3]**

### MessageTemplate

Modèles de messages personnalisables, avec placeholders `{{ client }}`,
`{{ panier }}`,`{{ ferme }}`,`{{ creneau }}`…

| Champ | Type | Notes |
|---|---|---|
| producer | FK Producer, CASCADE | `unique_together ("producer", "kind")` |
| kind | Choices | `ORDER_CONFIRM` / `BASKET_READY` / `DELIVERY_DONE` / `NEWSLETTER` / `ANNOUNCEMENT` |
| subject | Char(200) | |
| body | Text | texte du message, placeholders inclus |
| channel | Choices | `EMAIL` / `SMS` |
| is_active | Boolean | un modèle actif par (producer, kind, channel) |

Chaque type possède un **contenu par défaut** (fourni en fixture) que le
producteur édite — jamais d'envoi bloquant si le modèle est cassé : fallback
sur le défaut.

### Newsletter / Announcement

| Modèle | Champs | Notes |
|---|---|---|
| Newsletter | producer, week_start (FK HarvestWeek nullable), subject, body, sent_at | envoyée aux clients abonnés |
| Announcement | producer, subject, body, sent_at | annonce ponctuelle, ex : « paniers disponibles » |

### ContactPreference

Par client et par producteur (le même client peut vouloir tout d'un
maraîcher et seulement les annonces d'un autre) :

| Champ | Type | Notes |
|---|---|---|
| client | FK User, CASCADE | `unique_together ("client", "producer")` |
| producer | FK Producer, CASCADE | |
| wants_newsletter | Boolean, default True | |
| wants_announcements | Boolean, default True | |
| channel | Choices | `EMAIL` / `SMS` / `BOTH` | `SMS` → n° du ClientProfile requis |

### ProducerMessagingConfig

SMTP et passerelle SMS **du producteur** (jamais centralisés) :

| Champ | Type | Notes |
|---|---|---|
| producer | OneToOne Producer | |
| smtp_host / smtp_port / smtp_user / smtp_password / smtp_from | Char/Int | mot de passe chiffré au repos (Keyczar/Fernet), jamais exporté |
| sms_provider | Choices | `FREE` / `OVH` / `TWILIO` / `CUSTOM_HTTP`… |
| sms_config | JSONField | endpoint + credentials (chiffrés), format propre à la passerelle |
| daily_quota / quiet_hours | SmallInt / Char | garde-fous anti-spam |

## Vitrine **[V2 — issue #4]**

### ProducerSiteSettings

| Champ | Type | Notes |
|---|---|---|
| producer | OneToOne Producer | |
| hero_title / hero_text | Char/Text | bloc d'accueil personnalisé |
| theme_color | Char(7) | couleur d'accent (#RRGGBB) |
| banner_image | Image | |
| show_harvest / show_catalog / show_slots | Boolean | sections visibles |
| social_links | JSONField | `{"facebook": "…", "instagram": "…"}` |

## Historique des modifications

| Version | Changement |
|---|---|
| 0.1 | Première rédaction — à valider avant migrations |
