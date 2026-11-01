# Structure de données définitive

> Document de référence pour les modèles Django (`portal/models.py`).
> Convention : **noms de tables et de champs en français**, sans accent dans
> les identifiants (Django et PostgreSQL les acceptent, mais on garde
> `numero` plutôt que `numéro` : plus sûr pour les shells, exports et
> migrations). Les modèles déjà en place en V1 sont signalés **[V1]**, les
> ajouts prévus **[V2]** (issues #1–#9).

## Principes

- **PostgreSQL** en prod : attributs libres en **JSONB** (SQLite accepté en
  mono-ferme : Django dégrade `JSONField` en texte — OK, aucun filtrage
  avancé requis sur ces attributs).
- Les quantités hebdo sont des **estimations** : aucun décompte à la commande.
  Seules les quantités **livrées dans les paniers** sont décomptées.
- **Seules les commandes validées par l'exploitant puis livrées** persistent
  en base ; les paniers non confirmés ou abandonnés sont **purgés**.
- Chaque producteur possède **ses propres catégories et produits** ; le
  catalogue standard embarqué n'est qu'un **point de départ copiable**.
- Les prix et quantités sont **figés** (copie) au moment de la commande :
  modifier un produit n'altère jamais l'historique.
- **Fichiers** : seuls les visuels de l'exploitant sont importés, sous
  `media/exploitants/{id}/` avec un **naming explicite** et un **quota par
  type**. Le catalogue standard vit en emojis/SVG embarqués : zéro fichier.
- Identifiants en anglais : `id`, `pk`, `fk` restent standard.

## Catalogue

### Categorie **[V2 — issue #5]**

Catégories **définies par chaque exploitant**.

| Champ | Type | Notes |
|---|---|---|
| exploitant | FK Exploitant, CASCADE | `related_name="categories"` |
| nom | Char(80) | ex : « Légumes d'hiver » |
| slug | Slug(100) | auto, unique par exploitant |
| position | PositiveSmallInt | tri d'affichage |

`unique_together = ("exploitant", "nom")`

### Produit **[V1 → évolué en V2]**

| Champ | Type | Notes |
|---|---|---|
| exploitant | FK Exploitant, CASCADE | |
| categorie | FK Categorie, SET_NULL, null | remplace le champ texte `category` |
| nom | Char(150) | |
| description | Text, blank | |
| unite_vente | Char(2) choices | kg / pièce / botte / barquette |
| illustration | Image, blank | photo perso ; sinon emoji/SVG du standard |
| attributs | JSONField, default dict | `{"variété": "Butternut", "label": "AB", "saison": ["été", "automne"]}` — JSONB |
| origine_standard | FK ProduitStandard, SET_NULL, null | traçabilité de la copie |
| perso | Boolean | produit créé pour l'usage propre de l'exploitant |
| prix | Decimal(6,2) | tarif de référence, modifiable librement |
| actif | Boolean | visible ou non dans la vitrine |

### ProduitStandard **[V2 — issue #1]**

Catalogue standard embarqué (~80–120 produits types), en données de départ,
**lecture seule** pour les exploitants.

| Champ | Type | Notes |
|---|---|---|
| nom | Char(150) unique | « Carotte » |
| categorie | Char(80) | « Légumes racines » (catégorie standard simple) |
| unite_vente | Char(2) choices | kg / pièce / botte / barquette |
| saisons | JSONField | `["printemps", "été"]` → filtre saison |
| emoji | Char(8) | illustration embarquée 🥕 (zéro dépendance) |
| svg | Text, blank | SVG inline optionnel |

Filtres : catégorie, saison, recherche nom. Copie cochable →
`Produit.objects.create(origine_standard=…)` par exploitant.

## Récoltes et paniers

### SemaineRecolte / LigneRecolte **[V1]**

Estimations hebdo, prix par ligne, aucune réservation de stock. L'exploitant
paramètre chaque semaine **ce qui est visible** côté vitrine.

### Panier **[V2 — issues #2, #6, #8]**

Panier **numéroté**, préparé pour un client, un jour de livraison.

| Champ | Type | Notes |
|---|---|---|
| exploitant | FK Exploitant, CASCADE | |
| client | FK Utilisateur, SET_NULL, null | null si commande saisie pour un client sans compte |
| nom_client | Char(150) | figé : nom affiché même si le compte disparaît |
| numero | PositiveSmallInt | **n°1..X par client et par jour** — (dernier n° du couple client/jour) + 1 |
| date_livraison | Date, indexé | jour de livraison réel |
| creneau | FK CreneauLivraison, SET_NULL, null | |
| point_livraison | FK PointLivraison, SET_NULL, null | |
| commande | FK Commande, SET_NULL, null | origine portail ; null si saisie directe |
| statut | Choices | `PREPARATION` / `PRET` / `LIVRE` / `RECU` |
| total | Decimal(8,2) | |

`unique_together = ("exploitant", "client", "date_livraison", "numero")`

### LignePanier **[V2]**

Contenu **effectivement livré** — LA source du décompte de production.

| Champ | Type | Notes |
|---|---|---|
| panier | FK Panier, CASCADE | `related_name="lignes"` |
| produit | FK Produit, PROTECT | |
| quantite | Decimal(8,2) | quantité validée par l'exploitant |
| prix_unitaire | Decimal(6,2) | **tarif figé au moment de la commande** |

**Export comptable CSV** (issue #8) : produit, quantité, prix, total, date de
livraison, client — uniquement `statut = LIVRE / RECU`.

### Commande / LigneCommande **[V1]**

Évolutions mineures :

- `Commande` : `saisie_exploitant = True` pour les saisies directes
  (issue #2) ; statut `VALIDEE` figé par l'exploitant ;
- à la validation, un `Panier` pré-rempli est proposé (contenu
  copiable/ajustable) — la commande ne décompte rien ;
- `LigneCommande` reste figée (historique du panier **souhaité**), les
  ajustements de l'exploitant se font dans `LignePanier` (panier **livré**) ;
- **purge automatique** des commandes non validées ou non livrées
  (tâche planifiée) : seules les paniers livrés persistent.

## Livraison

### PointLivraison / CreneauLivraison **[V1]**

Inchangés. Écrans exploitant dédiés prévus (issue #9).

## Communication **[V2 — issue #3]**

### ModeleMessage

Modèles personnalisables, placeholders `{{ client }}`, `{{ panier }}`,
`{{ ferme }}`, `{{ creneau }}`…

| Champ | Type | Notes |
|---|---|---|
| exploitant | FK Exploitant, CASCADE | `unique_together ("exploitant", "type")` |
| type | Choices | `CONFIRMATION_COMMANDE` / `PANIER_PRET` / `LIVRAISON_FAITE` / `BULLETIN` / `ANNONCE` |
| canal | Choices | `EMAIL` / `SMS` |
| objet | Char(200) | |
| corps | Text | placeholders inclus |
| actif | Boolean | un actif par (exploitant, type, canal) |

Contenu **par défaut fourni en fixture** et éditable ; **fallback sur le
défaut** si le modèle personnalisé est cassé.

### Bulletin / Annonce

| Modèle | Champs | Notes |
|---|---|---|
| Bulletin | exploitant, semaine (FK SemaineRecolte nullable), objet, corps, envoye_le | envoyé aux clients abonnés |
| Annonce | exploitant, objet, corps, envoye_le | annonce ponctuelle (« paniers disponibles ») |

### PreferenceContact

Par couple client ↔ exploitant.

| Champ | Type | Notes |
|---|---|---|
| client | FK Utilisateur, CASCADE | `unique_together ("client", "exploitant")` |
| exploitant | FK Exploitant, CASCADE | |
| veut_bulletin | Boolean, default True | |
| veut_annonces | Boolean, default True | |
| canal | Choices | `EMAIL` / `SMS` | `SMS` → n° du ProfilClient requis |

### ConfigMessagerie

SMTP et passerelle SMS **de l'exploitant** (jamais centralisés).

| Champ | Type | Notes |
|---|---|---|
| exploitant | OneToOne Exploitant | |
| smtp_hote / smtp_port / smtp_utilisateur / smtp_mot_de_passe / smtp_expediteur | Char/Int | mot de passe chiffré au repos, jamais exporté |
| passerelle_sms | Choices | `FREE` / `OVH` / `TWILIO` / `HTTP_PERSONNALISE`… |
| config_sms | JSONField | endpoint + identifiants (chiffrés) |
| quota_journalier / heures_calmes | SmallInt / Char | garde-fous anti-spam |

## Vitrine **[V2 — issue #4]**

### ParametresVitrine

| Champ | Type | Notes |
|---|---|---|
| exploitant | OneToOne Exploitant | |
| titre_accroche / texte_accroche | Char/Text | bloc d'accueil personnalisé |
| couleur_theme | Char(7) | accent (#RRGGBB) |
| image_banniere | Image | sous `media/exploitants/{id}/banniere.jpg` |
| afficher_recolte / afficher_catalogue / afficher_creneaux | Boolean | sections visibles |
| reseaux | JSONField | `{"facebook": "…"}` |

## Système de fichiers (naming explicite, volumes maîtrisés)

Chaque exploitant a un dossier dédié `media/exploitants/{id}/` :

| Fichier | Règle | Quota |
|---|---|---|
| `logo.png` | 1 seul, écrasé à la mise à jour | 1 |
| `banniere.jpg` | 1 seul, écrasée | 1 |
| `ferme-*.jpg` | photos de la ferme, slug explicite | ≤ 10 |
| `produits/{slug_produit}.jpg` | 1 image par produit, écrasée à la mise à jour | 1 par produit |

- Écrasement plutôt qu'accumulation : **pas de versions orphelines**.
- Compression/redimensionnement automatique à l'import (taille max par image).
- Zéro fichier pour le catalogue standard (emojis/SVG embarqués).

## Historique des modifications

| Version | Changement |
|---|---|
| 0.2 | Noms de tables et champs en français ; purge des commandes non livrées ; système de fichiers/naming/quota |
| 0.1 | Première rédaction |
