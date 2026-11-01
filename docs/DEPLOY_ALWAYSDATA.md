# Déploiement sur AlwaysData (sous-domaine)

MonPetitMaraicher est une application Django servie en **WSGI**,
directement supporté par AlwaysData. Base de données recommandée :
**PostgreSQL** (natif chez AlwaysData, champs JSONB pour les attributs
personnalisés des produits).

## 1. Prérequis

- Une offre AlwaysData avec accès **SSH** et **Python 3.11+**
  (Web > Sites > type d'application Python/WSGI)
- Un sous-domaine configuré (ex : `monpetitmaraicher.tondomaine.fr`) pointé
  vers AlwaysData

## 2. Installation via SSH

```bash
ssh toncompte@ssh-toncompte.alwaysdata.net

git clone https://github.com/cartotrac/MonPetitMaraicher.git ~/monpetitmaraicher
cd ~/monpetitmaraicher
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
DJANGO_ALLOWED_HOSTS=monpetitmaraicher.tondomaine.fr
DB_ENGINE=django.db.backends.postgresql
DB_NAME=toncompte_mpm
DB_USER=toncompte_mpm
DB_PASSWORD=***
DB_HOST=postgresql-toncompte.alwaysdata.net
DB_PORT=5432
```

Puis :

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
| Chemin de l'application | `/home/toncompte/monpetitmaraicher/config/wsgi.py` |
| Environnement Python | virtualenv : `/home/toncompte/monpetitmaraicher/venv` |

Ajouter les variables d'environnement ci-dessus dans « Variables
d'environnement » du site.

### Fichiers statiques et médias

Toujours dans **Web > Sites**, ajouter deux « Collections » (routes) :

| Route | Réglage | Dossier racine |
|---|---|---|
| `/static/` | Fichiers statiques | `/home/toncompte/monpetitmaraicher/staticfiles` |
| `/media/` | Fichiers statiques | `/home/toncompte/monpetitmaraicher/media` |

> ⚠️ Les fichiers media (logos, photos) ne survivent pas à un redéploiement
> git : prévoir à terme un stockage objet (S3-compatible) ou des sauvegardes.

## 5. Mise à jour

```bash
cd ~/monpetitmaraicher && git pull
venv/bin/pip install -r requirements.txt
venv/bin/python manage.py migrate
venv/bin/python manage.py collectstatic --noinput
```

Redémarrer l'application WSGI depuis le panneau si nécessaire.

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
