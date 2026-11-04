# Déploiement sur AlwaysData (sous-domaine)

MonPetitProducteurLocal est une application Django servie en **WSGI**,
directement supporté par AlwaysData. Base de données recommandée :
**PostgreSQL** (natif chez AlwaysData, champs JSONB pour les attributs
personnalisés des produits et les paramètres).

## 1. Prérequis

- Une offre AlwaysData avec accès **SSH** et **Python 3.11+**
  (Web > Sites > type d'application Python/WSGI)
- Un sous-domaine configuré (ex : `monpetitproducteurlocal.tondomaine.fr`) pointé
  vers AlwaysData

## 2. Installation via SSH

```bash
ssh toncompte@ssh-toncompte.alwaysdata.net

git clone https://github.com/cartotrac/MonPetitProducteurLocal.git ~/monpetitproducteurlocal
cd ~/monpetitproducteurlocal
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/pip install "psycopg[binary]"
```

## 3. Base de données PostgreSQL

Dans le panneau AlwaysData : **Bases de données > PostgreSQL**, créer :
- une base (ex : `toncompte_mpm`)
- un utilisateur et son mot de passe

Renseigner ensuite les variables d'environnement (voir `.env.example`) :

```
DJANGO_SECRET_KEY=<générée>
DJANGO_DEBUG=0
DJANGO_ALLOWED_HOSTS=monpetitproducteurlocal.tondomaine.fr
CSRF_TRUSTED_ORIGINS=https://monpetitproducteurlocal.tondomaine.fr
DB_ENGINE=django.db.backends.postgresql
DB_NAME=toncompte_mpm
DB_USER=toncompte_mpm
DB_PASSWORD=***
DB_HOST=postgresql-toncompte.alwaysdata.net
DB_PORT=5432
```

> ⚠️ `CSRF_TRUSTED_ORIGINS` (avec `https://`) est **indispensable** :
> sinon tous les formulaires échouent avec « CSRF verification failed ».

Puis (les migrations ne sont pas versionnées : les générer sur le serveur) :

```bash
venv/bin/python manage.py makemigrations portal
venv/bin/python manage.py migrate
venv/bin/python manage.py createsuperuser
venv/bin/python manage.py collectstatic
```

> 💡 Alternative légère : pour une instance mono-ferme (Raspberry Pi, très
> petit hébergement), laisser `DB_ENGINE` vide => la base devient un simple
> fichier SQLite (`db.sqlite3`), sauvegardable/copiable d'un coup.

## 4. Configuration du site dans le panneau

**Web > Sites > modifier le site** :

| Réglage | Valeur |
|---|---|
| Type | WSGI (Python) |
| Chemin de l'application | `/home/toncompte/monpetitproducteurlocal/config/wsgi.py` |
| Environnement Python | virtualenv : `/home/toncompte/monpetitproducteurlocal/venv` |

Ajouter les variables d'environnement ci-dessus dans « Variables
d'environnement » du site.

### E-mails

Sans configuration, les e-mails du portail partent dans le **journal**
(backend console). Pour un envoi réel sur AlwaysData, ajouter :

```
EMAIL_HOST=localhost
EMAIL_PORT=25
```

Les exploitants peuvent de surcroît renseigner **leur propre SMTP** dans la
page **Paramètres** de leur espace pro — il est alors utilisé pour la
diffusion de leurs publications (newsletters, annonces).

### Fichiers statiques et médias

Toujours dans **Web > Sites**, ajouter deux « Collections » (routes) :

| Route | Réglage | Dossier racine |
|---|---|---|
| `/static/` | Fichiers statiques | `/home/toncompte/monpetitproducteurlocal/staticfiles` |
| `/media/` | Fichiers statiques | `/home/toncompte/monpetitproducteurlocal/media` |

> ⚠️ Les fichiers media (logos, photos) ne survivent pas à un redéploiement
> git : prévoir à terme un stockage objet (S3-compatible) ou des sauvegardes.
> Les images par **URL externe** (photo de profil, logo) ne posent pas ce
> problème : rien n'est hébergé par le portail.

## 5. Mise à jour

```bash
cd ~/monpetitproducteurlocal && git pull
venv/bin/pip install -r requirements.txt
venv/bin/python manage.py makemigrations portal
venv/bin/python manage.py migrate
venv/bin/python manage.py collectstatic --noinput
```

Puis **redémarrer l'application WSGI** depuis le panneau (toujours, même
sans modification : le code Python est chargé en mémoire).

### Commandes de maintenance

```bash
# Rattache un point aux commandes/paniers sans point puis renumérote
# les paniers : 1..X par (exploitation, jour, point de livraison)
venv/bin/python manage.py renumeroter_paniers --sech

# Met à jour nom/e-mail/téléphone des commandes et paniers rattachés
# à un compte, d'après les profils clients actuels
venv/bin/python manage.py resynchroniser_clients --sech

# Charge les catalogues de produits types par activité (maraîcher,
# arboriculteur, éleveur, fromager, apiculteur) — idempotent
venv/bin/python manage.py charger_catalogues_activites
```

## 6. Portabilité des données (bien commun)

- Les catalogues producteurs (produits, catégories personnalisées,
  attributs) pourront être **exportés/importés en JSON** pour sauvegarde ou
  migration d'une instance à l'autre.
- Sauvegardes recommandées : `pg_dump` quotidien de la base + archive du
  dossier `media/`.

## 7. Évolutions prévues

- Automatiser le déploiement (script `deploy.sh` ou GitHub Actions + SSH)
- Mutualisation par département : soit instances séparées, soit passage en
  multi-tenant (schémas PostgreSQL) quand le projet sera mûr
- Envoi effectif des SMS de disponibilité hebdo via la passerelle
  paramétrée (page Paramètres)
