import csv
import datetime
import io
import re
from decimal import Decimal, InvalidOperation

import django.core.mail
from django.conf import settings

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import (AnnonceForm, BulletinForm, InscriptionClientForm,
                    InscriptionExploitantForm, MessagerieForm, ProduitForm,
                    ProfilExploitantForm, ProfilPersonnelForm)
from .meteo import meteo_synthese
from .models import (Annonce, Bulletin, Categorie, Commande, CreneauLivraison,
                    Exploitant, Favori, LigneCommande, LignePanier,
                    LigneRecolte, MembreExploitation, Panier,
                    ParametresVitrine, PointLivraison, PreferenceContact,
                    Produit, ProduitStandard, ProfilClient, SemaineRecolte,
                    exploitant_pour)
from .notifications import envoyer_sms, notifier_client

# Unités vendues à la pièce : quantités entières uniquement.
UNITES_ENTIERES = ("PC", "BO", "BQ")


def apres_connexion(request):
    """Après connexion (et après inscription) : un compte pro tombe
    directement sur son dashboard ; un client sur « Mes commandes » ;
    un visiteur non connecté sur l'accueil."""
    if not request.user.is_authenticated:
        return redirect("portal:home")
    if exploitant_pour(request.user) is not None:
        return redirect("portal:dashboard")
    return redirect("portal:my_orders")


def mentions_legales(request):
    """Mentions légales : application libre (dépôt GitHub), instance
    hébergée par son opérateur, hébergeur technique AlwaysData."""
    return render(request, "portal/mentions.html")


def home(request):
    """Landing : bandeau, hero, présentation du portail."""
    exploitants = (Exploitant.objects.filter(visible=True)
                   .exclude(latitude=None, longitude=None)
                   .order_by("nom_ferme"))
    return render(request, "portal/home.html", {"exploitants": exploitants})


def producer_search(request):
    """Recherche multi-critères : exploitant, produit, ville, département
    (ou code postal), mode de production — plus la CARTE des résultats."""
    exploitants = Exploitant.objects.filter(visible=True).order_by("nom_ferme")
    q = request.GET.get("q", "").strip()
    dept = request.GET.get("dept", "").strip()
    mode = request.GET.get("mode", "").strip()
    activite = request.GET.get("activite", "").strip()
    if q:
        exploitants = exploitants.filter(
            Q(nom_ferme__icontains=q) | Q(ville__icontains=q)
            | Q(code_postal__icontains=q)
            | Q(departement__icontains=q)
            | Q(produits__nom__icontains=q)
            | Q(produits__categorie__nom__icontains=q)).distinct()
    if dept:
        # Département saisi (« 81 », « Tarn »…) OU code postal commençant
        # par ces chiffres : un exploitant sans champ département rempli
        # reste trouvable depuis son code postal.
        exploitants = exploitants.filter(
            Q(departement__iexact=dept)
            | Q(code_postal__istartswith=dept)).distinct()
    if mode:
        exploitants = exploitants.filter(mode_production=mode)
    if activite:
        exploitants = exploitants.filter(activite=activite)
    exploitants = list(exploitants)
    # Données carto : uniquement les résultats filtrés avec coordonnées.
    carte_data = [{
        "nom_ferme": e.nom_ferme,
        "mode_production": e.mode_production,
        "activite": e.activite,
        "ville": e.ville,
        "latitude": e.latitude,
        "longitude": e.longitude,
        "est_demo": e.est_demo,
        "url": e.get_absolute_url(),
    } for e in exploitants
        if e.latitude is not None and e.longitude is not None]
    return render(request, "portal/search_results.html", {
        "exploitants": exploitants,
        "carte_data": carte_data,
        "activites": Exploitant.Activite.choices,
        "q": q, "dept": dept, "mode": mode, "activite": activite,
    })


def producteurs_geojson(request):
    """Données carte : exploitants visibles avec coordonnées."""
    exploitants = (Exploitant.objects.filter(visible=True)
                   .exclude(latitude=None, longitude=None))
    data = [{
        "slug": e.slug,
        "nom_ferme": e.nom_ferme,
        "mode_production": e.mode_production,
        "activite": e.activite,
        "ville": e.ville,
        "latitude": e.latitude,
        "longitude": e.longitude,
        "est_demo": e.est_demo,
        "url": e.get_absolute_url(),
    } for e in exploitants]
    return JsonResponse(list(data), encoder=DjangoJSONEncoder, safe=False)


def producer_detail(request, slug):
    """Page publique d'un exploitant : récolte de la semaine + à venir,
    météo en direct à la ferme et bandeau des créneaux de livraison."""
    exploitant = get_object_or_404(Exploitant, slug=slug, visible=True)
    today = timezone.localdate()
    lundi = today - datetime.timedelta(days=today.weekday())
    semaines_avenir = list(
        SemaineRecolte.objects.filter(exploitant=exploitant, publiee=True,
                                      lundi__gt=lundi).order_by("lundi"))
    semaine = (SemaineRecolte.objects.filter(exploitant=exploitant,
                                             publiee=True,
                                             lundi__lte=lundi)
               .order_by("-lundi").first())
    lignes = list(semaine.lignes.select_related("produit__categorie",
                                                "produit__origine_standard")
                  if semaine else [])
    # Produits regroupés par catégorie (même présentation que côté
    # maraîcher) : tri par position de catégorie puis nom.
    lignes.sort(key=lambda l: (
        (l.produit.categorie.position if l.produit.categorie else 9999)
        or 9999,
        l.produit.categorie.nom if l.produit.categorie else "zz",
        l.produit.nom))
    groupes, courant = [], None
    for ligne in lignes:
        nom_cat = (ligne.produit.categorie.nom
                   if ligne.produit.categorie else "Autres produits")
        if not groupes or groupes[-1][0] != nom_cat:
            groupes.append((nom_cat, []))
        groupes[-1][1].append(ligne)
    vitrine, _cree = ParametresVitrine.objects.get_or_create(
        exploitant=exploitant)
    # Équipe affichée sur la vitrine : gérant + associés rattachés,
    # avec leur photo de profil externe si elle existe.
    def _membre(user, role):
        try:
            photo = user.profil_client.photo_url
        except Exception:
            photo = ""
        return {"nom": user.get_full_name() or user.username,
                "role": role, "photo_url": photo}
    equipe = [_membre(exploitant.user, "Gérant")]
    equipe += [_membre(m.user, "Associé·e")
                for m in exploitant.membres.select_related("user")]
    # Dispo restante par produit (colonne de saisie directe sur la
    # vitrine : les quantités partent pré-remplies vers la commande).
    restes = {}
    if semaine:
        offres_recolte, _mode = _offres_commande(exploitant, semaine)
        restes = {o["produit"].pk: o["reste"] for o in offres_recolte}
    est_favori = (request.user.is_authenticated
                  and Favori.objects.filter(user=request.user,
                                            exploitant=exploitant).exists())
    nature_favori = ""
    if est_favori:
        nature_favori = (Favori.objects.filter(
            user=request.user, exploitant=exploitant)
            .values_list("nature", flat=True).first() or "")
    return render(request, "portal/producer_detail.html", {
        "exploitant": exploitant,
        "vitrine": vitrine,
        "reseaux": vitrine.reseaux or {},
        "equipe": equipe,
        "semaine": semaine,
        "lignes": lignes,
        "groupes_categories": groupes,
        "semaines_avenir": semaines_avenir,
        "restes": restes,
        "est_favori": est_favori,
        "nature_favori": nature_favori,
        "est_compte_pro": exploitant_pour(request.user) is not None,
        "meteo": meteo_synthese(exploitant),
        "points_livraison": exploitant.points_livraison.all(),
        "creneaux": exploitant.creneaux.select_related("point_livraison"),
    })


# ---------------------------------------------------------------- registres


@login_required
def favoris_toggle(request, slug):
    """Ajoute/retire un producteur des favoris (étoile sur la vitrine).
    Les comptes pro précisent la nature : Fournisseur ou Client pro ;
    les clients l'ajoutent simplement. Redirige vers la vitrine."""
    exploitant = get_object_or_404(Exploitant, slug=slug, visible=True)
    nature = request.POST.get("nature", Favori.Nature.CLIENT)
    if nature not in Favori.Nature.values:
        nature = Favori.Nature.CLIENT
    # Un non-pro ne peut créer que des favoris « client »
    if (nature != Favori.Nature.CLIENT
            and exploitant_pour(request.user) is None):
        nature = Favori.Nature.CLIENT
    favori = Favori.objects.filter(user=request.user,
                                   exploitant=exploitant).first()
    if favori:
        favori.delete()
        messages.info(request, f"{exploitant.nom_ferme} retiré de vos "
                       "favoris.")
    else:
        Favori.objects.create(user=request.user, exploitant=exploitant,
                              nature=nature)
        libelle = dict(Favori.Nature.choices).get(nature, "")
        messages.success(request, f"{exploitant.nom_ferme} ajouté à vos "
                         f"favoris ⭐ ({libelle.lower()})")
    return redirect("portal:producer_detail", slug=slug)


@login_required
def mes_producteurs(request):
    """Les favoris du compte : côté client, les producteurs suivis et
    les fermes déjà commandées ; côté pro, distinction Fournisseurs /
    Clients pro (les fermes déjà commandées sont intégrées)."""
    favoris = list(Favori.objects.filter(user=request.user)
                   .select_related("exploitant"))
    exploitant_ids = [f.exploitant_id for f in favoris]
    deja_commandes = (Exploitant.objects.filter(
        visible=True, commandes__client=request.user)
        .exclude(pk__in=exploitant_ids)
        .distinct().order_by("nom_ferme"))
    est_pro = exploitant_pour(request.user) is not None
    if est_pro:
        # Les fermes déjà commandées sont classées « client pro »
        deja = list(deja_commandes)
        return render(request, "portal/mes_producteurs.html", {
            "est_pro": True,
            "favoris_fournisseurs": [f.exploitant for f in favoris
                                     if f.nature
                                     == Favori.Nature.FOURNISSEUR],
            "favoris_clients": [f.exploitant for f in favoris
                                if f.nature
                                != Favori.Nature.FOURNISSEUR],
            "deja_commandes": deja,
        })
    return render(request, "portal/mes_producteurs.html", {
        "est_pro": False,
        "favoris": [f.exploitant for f in favoris],
        "deja_commandes": deja_commandes,
    })


def _enregistrer_image_externe(produit, url):
    """Photo externe (drive, cloud, réseau) : stockée dans attributs
    JSONB, aucun fichier sur le serveur. Vide = lien retiré."""
    url = (url or "").strip()
    attributs = dict(produit.attributs or {})
    if url:
        attributs["image_url"] = url
    else:
        attributs.pop("image_url", None)
    produit.attributs = attributs

def register_exploitant(request):
    if request.method == "POST":
        form = InscriptionExploitantForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(
                request, "Bienvenue ! Votre espace producteur est prêt. "
                "Complétez votre fiche (SIRET, logo, description, points de "
                "livraison) depuis la page ⚙️ Paramètres, puis importez vos "
                "produits depuis le catalogue de votre activité.")
            return redirect("portal:dashboard")
    else:
        form = InscriptionExploitantForm()
    return render(request, "portal/registration/register_producer.html",
                  {"form": form})


def register_client(request):
    if request.method == "POST":
        form = InscriptionClientForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Compte client créé. À vous de commander !")
            return redirect("portal:apres_connexion")
    else:
        form = InscriptionClientForm()
    return render(request, "portal/registration/register_client.html",
                  {"form": form})


def est_exploitant(user):
    # Propriétaire de l'exploitation OU membre rattaché (équipe).
    return exploitant_pour(user) is not None


exploitant_requis = user_passes_test(est_exploitant, login_url="portal:login")


def proprietaire_requis(fonction):
    """Réservé au gestionnaire principal (compte propriétaire de
    l'exploitation) : fiche ferme/SIRET, équipe, catalogue et catégories.
    Les membres de l'équipe n'ont accès qu'à la gestion courante :
    récoltes, commandes, paniers, points de livraison."""
    def wrapper(request, *args, **kwargs):
        if not hasattr(request.user, "exploitant"):
            messages.error(
                request, "Action réservée au gestionnaire principal de "
                "l'exploitation (fiche ferme, SIRET, équipe, catalogue).")
            return redirect("portal:dashboard")
        return fonction(request, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------- espace pro

def _calendrier_recoltes(exploitant):
    """Vue calendaire hebdomadaire des récoltes (dashboard) : les 8
    prochaines semaines, chacune reliée à sa semaine de récolte si elle
    existe (publiée ou brouillon), sinon à la création."""
    aujourd_hui = timezone.localdate()
    lundi_courant = aujourd_hui - datetime.timedelta(
        days=aujourd_hui.weekday())
    semaines = (SemaineRecolte.objects
                .filter(exploitant=exploitant,
                        lundi__gte=lundi_courant
                        - datetime.timedelta(days=7))
                .annotate(nb_lignes=Count("lignes")))
    par_lundi = {s.lundi: s for s in semaines}
    calendrier = []
    for i in range(8):
        lundi = lundi_courant + datetime.timedelta(weeks=i)
        s = par_lundi.get(lundi)
        calendrier.append({
            "lundi": lundi,
            "dimanche": lundi + datetime.timedelta(days=6),
            "semaine": s,
            "nb_lignes": s.nb_lignes if s else 0,
            "passe": lundi < lundi_courant,
            # Code couleur calendrier : bleu passé, vert semaine
            # courante, orange à venir (dashboard + vitrine publique).
            "etat": ("passe" if lundi < lundi_courant
                     else "courante" if lundi == lundi_courant
                     else "avenir"),
        })
    return calendrier


def dashboard(request):
    """Page centrale du maraîcher : rubriques à gauche, aperçu de la
    vitrine publique en direct à droite, hero météo et bandeau des
    créneaux de livraison (jour + horaires). Produits rangés par
    catégorie, éditables sur place (libellé, unité, prix)."""
    exploitant = exploitant_pour(request.user)
    produits = (exploitant.produits.filter(actif=True)
                .select_related("categorie", "origine_standard")
                .order_by("categorie__position", "categorie__nom",
                          "position", "nom"))
    groupes, ordre = {}, []
    for p in produits:
        cat = p.categorie
        if cat not in groupes:
            groupes[cat] = []
            ordre.append(cat)
        groupes[cat].append(p)
    paires = [(cat, groupes[cat]) for cat in ordre]
    return render(request, "portal/pro/dashboard.html", {
        "exploitant": exploitant,
        "est_proprietaire": hasattr(request.user, "exploitant"),
        "paires": paires,
        "categories": list(Categorie.objects.filter(exploitant=exploitant)
                           .order_by("position", "nom")),
        "unite_choices": Produit.Unite.choices,
        "meteo": meteo_synthese(exploitant),
        "semaine": SemaineRecolte.objects.filter(exploitant=exploitant)
                   .order_by("-lundi").first(),
        "semaines": list(SemaineRecolte.objects
                         .filter(exploitant=exploitant)
                         .annotate(nb_lignes=Count("lignes"))
                         .order_by("-lundi")[:6]),
        "calendrier": _calendrier_recoltes(exploitant),
        "points": exploitant.points_livraison.all(),
        "creneaux": exploitant.creneaux.select_related("point_livraison"),
        "commandes_attente": exploitant.commandes
                             .filter(statut=Commande.Statut.NOUVELLE)
                             .order_by("-creee_le")[:10],
        "paniers_en_cours": exploitant.paniers
                            .exclude(statut=Panier.Statut.RECU).count(),
    })


@login_required
@exploitant_requis
@proprietaire_requis
def product_list(request):
    """Page « Produits » dédiée (bandeau pro → Gestion → Produits) :
    édition complète du catalogue — libellé, unité, prix, ordre,
    catégories, ajout/retrait en lot — pendant que le dashboard ne
    garde que la gestion des catégories et le déplacement des
    produits entre catégories."""
    exploitant = exploitant_pour(request.user)
    produits = (exploitant.produits.filter(actif=True)
                .select_related("categorie", "origine_standard")
                .order_by("categorie__position", "categorie__nom",
                          "position", "nom"))
    groupes, ordre = {}, []
    for p in produits:
        cat = p.categorie
        if cat not in groupes:
            groupes[cat] = []
            ordre.append(cat)
        groupes[cat].append(p)
    paires = [(cat, groupes[cat]) for cat in ordre]
    return render(request, "portal/pro/produits.html", {
        "exploitant": exploitant,
        "paires": paires,
        "categories": list(Categorie.objects.filter(exploitant=exploitant)
                           .order_by("position", "nom")),
        "unite_choices": Produit.Unite.choices,
    })


@login_required
@exploitant_requis
@proprietaire_requis
def produit_creer(request):
    exploitant = exploitant_pour(request.user)
    if request.method == "POST":
        form = ProduitForm(request.POST, request.FILES, exploitant=exploitant)
        if form.is_valid():
            produit = form.save(commit=False)
            produit.exploitant = exploitant
            _enregistrer_image_externe(produit,
                                        request.POST.get("image_externe", ""))
            produit.save()
            messages.success(request, f"Produit « {produit.nom} » ajouté.")
            return redirect("portal:product_list")
    else:
        form = ProduitForm(exploitant=exploitant)
    return render(request, "portal/pro/product_form.html",
                  {"form": form, "titre": "Ajouter un produit",
                   "categories_url": "portal:categories_manage"})


@login_required
@exploitant_requis
@proprietaire_requis
def produit_modifier(request, pk):
    produit = get_object_or_404(Produit, pk=pk,
                                exploitant=exploitant_pour(request.user))
    if request.method == "POST":
        form = ProduitForm(request.POST, request.FILES, instance=produit,
                           exploitant=exploitant_pour(request.user))
        if form.is_valid():
            produit = form.save(commit=False)
            _enregistrer_image_externe(produit,
                                        request.POST.get("image_externe", ""))
            produit.save()
            messages.success(request, "Produit mis à jour.")
            return redirect("portal:product_list")
    else:
        form = ProduitForm(instance=produit,
                           exploitant=exploitant_pour(request.user))
    return render(request, "portal/pro/product_form.html",
                  {"form": form, "titre": "Modifier le produit",
                   "categories_url": "portal:categories_manage"})


@login_required
@exploitant_requis
def produit_edition_rapide(request):
    """Mode édition du dashboard « Mes produits » : libellé, unité et prix
    modifiés en place, ET ergonomie complète — ajout de produit, ajout
    de catégorie, reclassement des produits (▲▼, changement de
    catégorie) et des catégories, sans quitter la page."""
    exploitant = exploitant_pour(request.user)

    def _produits_de_la_categorie(categorie):
        qs = exploitant.produits.filter(actif=True)
        if categorie:
            qs = qs.filter(categorie=categorie)
        else:
            qs = qs.filter(categorie__isnull=True)
        return list(qs.order_by("position", "nom"))

    # Page de retour après l'action : la page « Produits » dédiée
    # (retour=produits) ou le dashboard (défaut).
    destination = ("portal:product_list"
                   if request.POST.get("retour", "") == "produits"
                   else "portal:dashboard")

    def _voisin(liste, produit, sens):
        """Produit à échanger avec `produit` dans l'ordre affiché."""
        index = next((i for i, p in enumerate(liste) if p.pk == produit.pk),
                     None)
        if index is None:
            return None
        voisin = index - 1 if sens == "haut" else index + 1
        if 0 <= voisin < len(liste):
            return liste[voisin]
        return None

    if request.method == "POST":
        # Actions de gestion : renommer/supprimer une catégorie,
        # retirer un ou plusieurs produits du catalogue. Le pk est
        # porté par la valeur du bouton (« action:pk »).
        action = request.POST.get("action", "")
        nature_action, _, cible_pk = action.partition(":")

        def _cible_categorie():
            try:
                pk = int(cible_pk)
            except ValueError:
                return None
            return Categorie.objects.filter(pk=pk,
                                            exploitant=exploitant).first()

        if nature_action == "categorie_renommer":
            cat = _cible_categorie()
            if cat is None:
                messages.error(request, "Catégorie introuvable.")
                return redirect(destination)
            nom = request.POST.get(f"nom_cat_{cat.pk}", "").strip()
            if nom:
                cat.nom = nom[:80]
                cat.save()
                messages.success(request, f"Catégorie renommée « {cat.nom} ».")
            else:
                messages.error(request, "Nom de catégorie vide.")
            return redirect(destination)
        if nature_action == "categorie_supprimer":
            cat = _cible_categorie()
            if cat is None:
                messages.error(request, "Catégorie introuvable.")
                return redirect(destination)
            nb = cat.produits.count()
            Produit.objects.filter(categorie=cat).update(categorie=None,
                                                         position=0)
            cat.delete()
            message = f"Catégorie « {cat.nom} » supprimée"
            if nb:
                message += (f" — {nb} produit(s) désormais sans catégorie "
                            "(reclassez-les dans la colonne Catégorie).")
            messages.info(request, message + ".")
            return redirect(destination)
        if nature_action == "categorie_ajouter":
            nom = request.POST.get("nouvelle_categorie", "").strip()
            if not nom:
                messages.error(request, "Nom de catégorie vide.")
                return redirect(destination)
            categorie = (Categorie.objects.filter(
                exploitant=exploitant, nom__iexact=nom).first())
            if categorie:
                messages.info(request, f"La catégorie « {categorie.nom} » "
                              "existe déjà.")
                return redirect(destination)
            position = (Categorie.objects.filter(exploitant=exploitant)
                        .aggregate(m=Max("position"))["m"] or 0)
            categorie = Categorie.objects.create(
                exploitant=exploitant, nom=nom[:80], position=position + 1)
            messages.success(request, f"Catégorie « {categorie.nom} » créée.")
            return redirect(destination)
        if nature_action == "produit_retirer":
            try:
                pk = int(cible_pk)
            except ValueError:
                pk = None
            produit = (Produit.objects.filter(pk=pk,
                                              exploitant=exploitant).first()
                       if pk else None)
            if produit is None:
                messages.error(request, "Produit introuvable.")
            else:
                produit.actif = False
                produit.save()
                messages.info(request, f"« {produit.nom} » retiré du "
                              "catalogue (l'historique des commandes "
                              "passées est conservé).")
            return redirect(destination)
        if nature_action == "produits_retirer":
            pks = request.POST.getlist("supprimer")
            concernes = Produit.objects.filter(pk__in=pks,
                                               exploitant=exploitant)
            nb = concernes.update(actif=False)
            if nb:
                messages.info(request, f"{nb} produit(s) retiré(s) du "
                              "catalogue (l'historique des commandes est "
                              "conservé).")
            else:
                messages.error(request, "Cochez d'abord les produits à "
                               "retirer.")
            return redirect(destination)

        # ▲▼ : déplacement d'un produit ou d'une catégorie
        mouvement = request.POST.get("mouvement", "")
        if mouvement:
            try:
                nature, pk, sens = mouvement.split(":")
                pk = int(pk)
            except ValueError:
                messages.error(request, "Requête de reclassement invalide.")
                return redirect(destination)
            if nature == "categorie":
                cat = get_object_or_404(Categorie, pk=pk,
                                        exploitant=exploitant)
                voisines = list(Categorie.objects.filter(
                    exploitant=exploitant).order_by("position", "nom"))
                autre = _voisin(voisines, cat, sens)
                if autre:
                    cat.position, autre.position = autre.position, cat.position
                    autre.save()
                    cat.save()
                    messages.success(request, "Catégorie déplacée.")
            else:
                produit = get_object_or_404(Produit, pk=pk,
                                           exploitant=exploitant)
                voisin = _voisin(_produits_de_la_categorie(produit.categorie),
                                 produit, sens)
                if voisin:
                    (produit.position,
                     voisin.position) = voisin.position, produit.position
                    voisin.save()
                    produit.save()
                    messages.success(
                        request, f"« {produit.nom} » déplacé.")
            return redirect(destination)

        # Changement de catégorie d'un produit
        cible = request.POST.get("appliquer_categorie", "")
        if cible:
            produit = get_object_or_404(Produit, pk=cible,
                                        exploitant=exploitant)
            cat_pk = request.POST.get(f"categorie_cible_{produit.pk}", "")
            if not cat_pk:
                produit.categorie = None
                produit.position = 0
                produit.save()
                messages.info(request, f"« {produit.nom} » placé hors "
                               "catégorie.")
            else:
                cat = get_object_or_404(Categorie, pk=cat_pk,
                                        exploitant=exploitant)
                produit.categorie = cat
                dernier = _produits_de_la_categorie(cat)
                produit.position = (max((p.position for p in dernier),
                                        default=0) + 1)
                produit.save()
                messages.success(request, f"« {produit.nom} » déplacé dans "
                                 f"« {cat.nom} ».")
            return redirect(destination)

        # ➕ Ajout d'un produit (avec catégorie nouvelle ou existante)
        if request.POST.get("action") == "produit_ajouter":
            nom = request.POST.get("nouveau_nom", "").strip()
            unite = request.POST.get("nouveau_unite", "").strip()
            cat_pk = request.POST.get("nouvelle_categorie", "").strip()
            nouvelle_cat = request.POST.get("nom_nouvelle_categorie",
                                           "").strip()
            brut_prix = request.POST.get("nouveau_prix", "").strip()
            erreurs = []
            prix = None
            if not nom:
                erreurs.append("Nom du produit requis.")
            if unite not in Produit.Unite.values:
                erreurs.append("Unité inconnue.")
            if brut_prix:
                try:
                    prix = Decimal(brut_prix)
                except InvalidOperation:
                    erreurs.append("Prix invalide.")
            categorie = None
            if nouvelle_cat:
                categorie = (Categorie.objects.filter(
                    exploitant=exploitant, nom__iexact=nouvelle_cat).first())
                if not categorie:
                    position = (Categorie.objects.filter(
                        exploitant=exploitant)
                        .aggregate(m=Max("position"))["m"] or 0)
                    categorie = Categorie.objects.create(
                        exploitant=exploitant, nom=nouvelle_cat[:80],
                        position=position + 1)
            elif cat_pk:
                categorie = get_object_or_404(Categorie, pk=cat_pk,
                                              exploitant=exploitant)
            if erreurs:
                messages.error(request, " ".join(erreurs))
            else:
                position = (max(
                    (p.position
                     for p in _produits_de_la_categorie(categorie)),
                    default=0) + 1)
                produit = Produit.objects.create(
                    exploitant=exploitant, nom=nom[:150], categorie=categorie,
                    unite_vente=unite, prix=prix, position=position)
                messages.success(request, f"Produit « {produit.nom} » "
                                 "ajouté.")
            return redirect(destination)

        # Enregistrement en masse : libellé, unité, prix
        erreurs, modifies = [], 0
        for produit in exploitant.produits.filter(actif=True):
            if f"nom_{produit.pk}" not in request.POST:
                continue
            nom = request.POST.get(f"nom_{produit.pk}", "").strip()
            unite = request.POST.get(f"unite_{produit.pk}", "").strip()
            brut_prix = request.POST.get(f"prix_{produit.pk}", "").strip()
            if not nom:
                erreurs.append(f"« {produit.nom} » : nom vide, non modifié.")
                continue
            if unite not in Produit.Unite.values:
                erreurs.append(f"« {nom} » : unité inconnue, non modifié.")
                continue
            prix_cible = None
            if brut_prix:
                try:
                    prix_cible = Decimal(brut_prix)
                except InvalidOperation:
                    erreurs.append(f"« {nom} » : prix invalide, non modifié.")
                    continue
            if (nom != produit.nom or unite != produit.unite_vente
                    or prix_cible != produit.prix):
                produit.nom = nom[:150]
                produit.unite_vente = unite
                produit.prix = prix_cible
                produit.save()
                modifies += 1
        if erreurs:
            messages.error(request, " ".join(erreurs))
        if modifies:
            messages.success(request, f"{modifies} produit(s) mis à jour.")
        elif not erreurs:
            messages.info(request, "Aucune modification à enregistrer.")
    return redirect(destination)


@login_required
@exploitant_requis
def harvest_list(request):
    """Toutes les récoltes de l'exploitant (fréquence libre : hebdo,
    moins souvent… c'est lui qui choisit). Publication / dépublication
    en un clic (impact immédiat sur la vitrine), suppression possible."""
    exploitant = exploitant_pour(request.user)
    today = timezone.localdate()
    lundi_courant = today - datetime.timedelta(days=today.weekday())

    if request.method == "POST":
        semaine = get_object_or_404(SemaineRecolte,
                                    pk=request.POST.get("pk"),
                                    exploitant=exploitant)
        action = request.POST.get("action")
        if action == "publier":
            semaine.publiee = True
            semaine.save()
            messages.success(request, "Récolte du "
                             + semaine.lundi.strftime("%d/%m/%Y")
                             + " publiée : visible sur la vitrine.")
        elif action == "depublier":
            semaine.publiee = False
            semaine.save()
            messages.info(request, "Récolte du "
                          + semaine.lundi.strftime("%d/%m/%Y")
                          + " masquée de la vitrine.")
        elif action == "supprimer":
            lundi_sup = semaine.lundi
            semaine.delete()
            messages.info(request, "Récolte du "
                          + lundi_sup.strftime("%d/%m/%Y") + " supprimée.")
        return redirect("portal:harvest_list")

    semaines = list(SemaineRecolte.objects
                    .filter(exploitant=exploitant)
                    .annotate(nb_lignes=Count("lignes"))
                    .order_by("-lundi"))
    courante, a_venir, passees = None, [], []
    for s in semaines:
        if s.lundi == lundi_courant:
            courante = s
        elif s.lundi > lundi_courant:
            a_venir.append(s)
        else:
            passees.append(s)
    return render(request, "portal/pro/harvest_list.html", {
        "courante": courante,
        "a_venir": a_venir,
        "passees": passees,
        "lundi_courant": lundi_courant,
    })


@login_required
@exploitant_requis
def harvest_manage(request, semaine_id=None, nouvelle=False):
    """Saisie d'une récolte (ESTIMATIONS) : quantité estimée + prix, produits
    regroupés par catégorie.

    Ergonomie : les valeurs sont pré-remplies depuis la semaine précédente
    (ou la semaine source choisie) ; les lignes reprises sont signalées.
    Le PRIX DE RÉFÉRENCE du catalogue préremplit les prix manquants.
    La date (lundi) est modifiable : déplacer la récolte change la semaine
    affichée sur la vitrine (refus propre si déjà existante).
    """
    exploitant = exploitant_pour(request.user)
    today = timezone.localdate()
    lundi = today - datetime.timedelta(days=today.weekday())
    semaine = None
    if semaine_id:
        semaine = get_object_or_404(SemaineRecolte, pk=semaine_id,
                                   exploitant=exploitant)

    lundi_defaut = lundi
    if nouvelle and not semaine:
        derniere = (SemaineRecolte.objects.filter(exploitant=exploitant)
                   .order_by("-lundi").first())
        if derniere:
            lundi_defaut = derniere.lundi + datetime.timedelta(days=7)

    if request.method == "POST":
        try:
            lundi_saisi = datetime.date.fromisoformat(
                request.POST.get("lundi") or lundi.isoformat())
        except ValueError:
            lundi_saisi = lundi
        if semaine is not None and lundi_saisi != semaine.lundi:
            autre = (SemaineRecolte.objects
                     .filter(exploitant=exploitant, lundi=lundi_saisi)
                     .exclude(pk=semaine.pk).first())
            if autre:
                messages.error(
                    request, "Une récolte existe déjà pour la semaine du "
                    + lundi_saisi.strftime("%d/%m/%Y")
                    + " : elle a été ouverte à la place.")
                return redirect("portal:harvest_manage", autre.pk)
            semaine.lundi = lundi_saisi
            semaine.save()
        if semaine is None:
            semaine, _cree = SemaineRecolte.objects.get_or_create(
                exploitant=exploitant,
                lundi=lundi_saisi,
                defaults={"note": request.POST.get("note", "")})
        semaine.note = request.POST.get("note", "")
        semaine.publiee = bool(request.POST.get("publiee"))
        semaine.save()
        for produit in exploitant.produits.filter(actif=True):
            qty = request.POST.get(f"qty_{produit.pk}", "").strip()
            prix = request.POST.get(f"price_{produit.pk}", "").strip()
            if not qty or not prix:
                continue
            try:
                qty, prix = Decimal(qty), Decimal(prix)
            except InvalidOperation:
                continue
            LigneRecolte.objects.update_or_create(
                recolte=semaine, produit=produit,
                defaults={"quantite_estimee": qty, "prix_unitaire": prix})
        for ligne in semaine.lignes.all():
            if f"qty_{ligne.produit_id}" not in request.POST:
                ligne.delete()
        messages.success(request, "Récolte du "
                         + semaine.lundi.strftime("%d/%m/%Y")
                         + " enregistrée.")
        return redirect("portal:harvest_list")

    # ---- Pré-remplissage : semaine source des valeurs reprises ----
    source = None
    if request.method == "GET":
        copier = request.GET.get("copier", "").strip()
        if copier:
            source = (SemaineRecolte.objects
                      .filter(exploitant=exploitant, pk=copier).first())
        if source is None:
            reference = semaine.lundi if semaine else lundi_defaut
            source = (SemaineRecolte.objects
                      .filter(exploitant=exploitant, lundi__lt=reference)
                      .order_by("-lundi").first())
        if source is None:
            source = (SemaineRecolte.objects
                      .filter(exploitant=exploitant)
                      .exclude(pk=semaine.pk if semaine else -1)
                      .order_by("-lundi").first())

    valeurs = {}   # produit_id -> (quantite, prix, reprise)
    if semaine:
        for l in semaine.lignes.all():
            valeurs[l.produit_id] = (l.quantite_estimee, l.prix_unitaire,
                                     False)
    if source and source.pk != (semaine.pk if semaine else None):
        for l in source.lignes.all():
            if l.produit_id not in valeurs:
                valeurs[l.produit_id] = (l.quantite_estimee,
                                         l.prix_unitaire, True)

    # ---- Produits regroupés par catégorie (position de l'exploitant) ----
    produits = (exploitant.produits.filter(actif=True)
                .select_related("categorie", "origine_standard")
                .order_by("categorie__position", "categorie__nom", "nom"))
    groupes, ordre = {}, []
    for p in produits:
        nom_cat = p.categorie.nom if p.categorie else "Sans catégorie"
        if nom_cat not in groupes:
            groupes[nom_cat] = []
            ordre.append(nom_cat)
        v = valeurs.get(p.pk)
        # Prix de la ligne de récolte, sinon prix de RÉFÉRENCE du
        # catalogue (saisi à l'import/création) : préremplit la colonne
        # prix, reste éditable à cet endroit.
        prix_affiche = (v[1] if v and v[1] is not None else None) or p.prix
        groupes[nom_cat].append({
            "produit": p,
            "qty": v[0] if v else None,
            "price": prix_affiche,
            "reprise": bool(v and v[2]),
            "step": "0.01" if p.unite_vente == "KG" else "1",
        })
    paires = [(nom, groupes[nom]) for nom in ordre]

    if semaine:
        lundi_defaut = semaine.lundi
    autres = (SemaineRecolte.objects.filter(exploitant=exploitant)
              .exclude(pk=semaine.pk if semaine else -1)
              .order_by("-lundi"))
    return render(request, "portal/pro/harvest_form.html", {
        "semaine": semaine,
        "source": source if source and not semaine else None,
        "autres": autres,
        "paires": paires,
        "lundi_defaut": lundi_defaut,
    })


def _groupes_lignes(lignes):
    """Lignes de commande (ou de panier) triées et regroupées par
    catégorie du produit — même présentation que la vitrine :
    [(nom_categorie, [lignes…]), …]."""
    lignes = sorted(lignes, key=lambda l: (
        (l.produit.categorie.position
         if l.produit.categorie else 9999) or 9999,
        l.produit.categorie.nom if l.produit.categorie else "zz",
        l.produit.nom))
    groupes = []
    for ligne in lignes:
        nom = (ligne.produit.categorie.nom
               if ligne.produit.categorie else "Sans catégorie")
        if not groupes or groupes[-1][0] != nom:
            groupes.append((nom, []))
        groupes[-1][1].append(ligne)
    return groupes


def _profils_clients(user_ids):
    """Photos et téléphones des clients concernés, SANS lever l'erreur
    « profil client inexistant » (un compte pro qui commande chez un
    confrère n'a pas de ProfilClient : c'est ce qui provoquait les
    erreurs 500 sur les listes commandes/paniers)."""
    profils = {p.user_id: p for p in ProfilClient.objects.filter(
        user_id__in=user_ids)}
    return ({i: profils[i].photo_url for i in profils
             if profils[i].photo_url},
            {i: profils[i].telephone for i in profils
             if profils[i].telephone})


def _badges_par_jour(objets, champ_statut, statuts):
    """Pour l'en-tête de chaque jour (commandes, paniers) : comptage par
    statut, ordonné, avec libellé — [(statut, nombre, libellé), …]."""
    comptes = {}
    for objet in objets:
        statut = getattr(objet, champ_statut)
        par_statut = comptes.setdefault(getattr(objet, "date_livraison"), {})
        par_statut[statut] = par_statut.get(statut, 0) + 1
    libelles = dict(statuts)
    return {jour: [(statut, par[statut], libelles[statut])
                  for statut, _libelle in statuts if statut in par]
            for jour, par in comptes.items()}


@login_required
@exploitant_requis
def order_list(request, statut=None):
    """Commandes reçues, avec contact client (e-mail, téléphone, canal
    préféré si le client en a exprimé un). Produits rangés par
    catégorie ; pour les commandes validées, les ajustements faits à
    la validation (contenu du panier) sont affichés."""
    exploitant = exploitant_pour(request.user)
    commandes = exploitant.commandes.order_by("-date_livraison", "-creee_le")
    if statut:
        commandes = commandes.filter(statut=statut)
    canaux = {p.client_id: p.get_canal_display()
              for p in PreferenceContact.objects.filter(exploitant=exploitant)}
    commandes = list(commandes.prefetch_related(
        "lignes__produit__categorie", "lignes__produit__origine_standard"))
    # Ajustements de la validation : quantités retenues dans le panier
    paniers_valides = {p.commande_id: p for p in Panier.objects.filter(
        commande_id__in=[c.pk for c in commandes],
        exploitant=exploitant).prefetch_related("lignes")}
    ajustements = {cid: {ligne.produit_id: ligne.quantite
                         for ligne in panier.lignes.all()}
                   for cid, panier in paniers_valides.items()}
    photos, telephones = _profils_clients(
        {c.client_id for c in commandes if c.client_id})
    for c in commandes:
        c.canal_pref = canaux.get(c.client_id) if c.client_id else None
        c.photo_client = photos.get(c.client_id, "")
        c.tel_client = telephones.get(c.client_id, "")
        c.groupes_lignes = _groupes_lignes(list(c.lignes.all()))
        c.ajustements = ajustements.get(c.pk)
    return render(request, "portal/pro/orders.html", {
        "commandes": commandes, "filtre_statut": statut,
        "points": exploitant.points_livraison.all(),
        "today": timezone.localdate(),
        "jours_badges": _badges_par_jour(commandes, "statut",
                                         Commande.Statut.choices),
    })


def _quantite_ajustee(brut, quantite_commandee, produit):
    """Valide une quantité ajustée : Decimal, positive, entière si l'unité
    se vend à la pièce. Retourne (quantite, erreur_ou_None)."""
    if brut == "":
        qty = quantite_commandee
    else:
        try:
            qty = Decimal(brut)
        except InvalidOperation:
            return None, f"« {produit.nom} » : quantité invalide."
    if qty <= 0:
        return None, None  # ligne retirée volontairement
    if (produit.unite_vente in UNITES_ENTIERES
            and qty != qty.to_integral_value()):
        return None, (f"« {produit.nom} » se vend à la pièce : "
                      "quantité entière requise.")
    return qty, None


@login_required
@exploitant_requis
def order_direct_create(request):
    """Saisie directe d'une commande par l'exploitant (issue #2) : au
    téléphone, au marché… La commande est immédiatement validée et le
    panier numéroté créé (contenu ajustable ensuite). Les prix de
    référence du catalogue s'appliquent."""
    exploitant = exploitant_pour(request.user)
    produits = list(exploitant.produits.filter(actif=True)
                    .select_related("categorie", "origine_standard")
                    .order_by("categorie__position", "nom"))
    points = exploitant.points_livraison.all()
    creneaux = exploitant.creneaux.select_related("point_livraison")

    # Estimations de la récolte publiée la plus récente (mêmes règles
    # que la vitrine) : guide la saisie, l'exploitant reste libre de
    # enregistrer plus (il ajustera à la préparation).
    jour = timezone.localdate()
    lundi_courant = jour - datetime.timedelta(days=jour.weekday())
    semaine = (SemaineRecolte.objects.filter(exploitant=exploitant,
                                             publiee=True,
                                             lundi__lte=lundi_courant)
               .order_by("-lundi").first())
    restes, mode = {}, "catalogue"
    if semaine:
        offres_semaine, mode = _offres_commande(exploitant, semaine)
        restes = {o["produit"].pk: (o["estime"], o["reste"])
                  for o in offres_semaine}
    # Produits regroupés par catégorie (même présentation que la
    # vitrine et la page de commande client).
    groupes_produits, ordre_cats = {}, []
    for p in produits:
        cat = p.categorie
        if cat not in groupes_produits:
            groupes_produits[cat] = []
            ordre_cats.append(cat)
        groupes_produits[cat].append(p)
    paires = [(cat, groupes_produits[cat]) for cat in ordre_cats]

    if request.method == "POST":
        nom_client = request.POST.get("nom_client", "").strip()
        email_client = request.POST.get("email_client", "").strip()
        telephone_client = request.POST.get("telephone_client", "").strip()
        point = exploitant.points_livraison.filter(
            pk=request.POST.get("point_livraison")).first()
        creneau = exploitant.creneaux.filter(
            pk=request.POST.get("creneau")).first()
        try:
            date_livraison = datetime.date.fromisoformat(
                request.POST["date_livraison"])
        except (KeyError, ValueError):
            date_livraison = None
        note = request.POST.get("note", "").strip()

        erreurs = []
        if not nom_client:
            erreurs.append("Nom du client requis.")
        if not email_client and not telephone_client:
            erreurs.append("E-mail ou téléphone requis (identité contact).")
        if (date_livraison is None
                or date_livraison < timezone.localdate()):
            erreurs.append("Date de livraison invalide "
                           "(aujourd'hui ou plus tard).")
        # Un point de livraison est obligatoire pour numéroter le panier :
        # soit celui choisi, soit — s'il n'en existe aucun — un message
        # invitant à en créer un d'abord (menu « Livraison »).
        if point is None:
            if points:
                erreurs.append("Point de livraison requis : "
                               "choisissez un point pour cette commande.")
            else:
                erreurs.append("Aucun point de livraison : créez-en un "
                               "d'abord dans « Livraison » "
                               "(Points & créneaux).")

        lignes, total = [], Decimal("0")
        for produit in produits:
            brut = request.POST.get(f"qty_{produit.pk}", "").strip()
            if not brut:
                continue
            try:
                qty = Decimal(brut)
            except InvalidOperation:
                erreurs.append(f"« {produit.nom} » : quantité invalide.")
                continue
            if qty <= 0:
                continue
            if (produit.unite_vente in UNITES_ENTIERES
                    and qty != qty.to_integral_value()):
                erreurs.append(f"« {produit.nom} » se vend à la pièce : "
                               "quantité entière requise.")
                continue
            if produit.prix is None:
                erreurs.append(f"« {produit.nom} » : aucun prix de "
                               "référence dans le catalogue.")
                continue
            lignes.append((produit, qty, produit.prix))
            total += qty * produit.prix
        if not lignes:
            erreurs.append("Aucun produit commandé.")

        if erreurs:
            messages.error(request, " ".join(erreurs))
        else:
            client = None
            if email_client:
                client = User.objects.filter(
                    email__iexact=email_client).first()
            with transaction.atomic():
                commande = Commande.objects.create(
                    exploitant=exploitant, client=client,
                    nom_client=nom_client[:150],
                    email_client=email_client,
                    telephone_client=telephone_client,
                    point_livraison=point,
                    date_livraison=date_livraison,
                    statut=Commande.Statut.VALIDEE,
                    validee_le=timezone.now(),
                    total=total, saisie_exploitant=True, note=note)
                panier = Panier.objects.create(
                    exploitant=exploitant, client=client,
                    nom_client=nom_client[:150],
                    email_client=email_client,
                    telephone_client=telephone_client,
                    numero=Panier.prochain_numero(
                        exploitant, date_livraison,
                        point_livraison=point),
                    date_livraison=date_livraison, creneau=creneau,
                    point_livraison=point, commande=commande,
                    statut=Panier.Statut.PREPARATION,
                    total=total, note=note)
                for produit, qty, prix in lignes:
                    LigneCommande.objects.create(
                        commande=commande, produit=produit,
                        quantite=qty, prix_unitaire=prix)
                    LignePanier.objects.create(
                        panier=panier, produit=produit,
                        quantite=qty, prix_unitaire=prix)
            messages.success(request, "Commande de " + nom_client
                             + " enregistrée → panier n°"
                             + str(panier.numero) + " créé.")
            notifier_client(request, panier, "CONFIRMATION_COMMANDE")
            return redirect("portal:panier_detail", panier.pk)

    return render(request, "portal/pro/order_direct.html", {
        "produits": produits,
        "paires": paires,
        "restes": restes,
        "mode": mode,
        "semaine": semaine,
        "points": points,
        "creneaux": creneaux,
        "date_defaut": timezone.localdate().isoformat(),
    })


@login_required
@exploitant_requis
def order_validate(request, commande_id):
    """Validation / refus d'une commande.

    L'exploitant peut AJUSTER les quantités au moment de valider (0 ou vide =
    retirer la ligne) et laisser un commentaire visible par le client.
    Le panier numéroté est créé avec le contenu ajusté : point de départ
    du contenu livré (DATA_MODEL v0.3). Le client est notifié.
    """
    exploitant = exploitant_pour(request.user)
    commande = get_object_or_404(Commande, pk=commande_id, exploitant=exploitant)
    if (request.method == "POST"
            and commande.statut == Commande.Statut.NOUVELLE):
        action = request.POST.get("action")
        if action == "validate":
            # Point de livraison obligatoire pour créer le panier numéroté :
            # par défaut celui de la commande, sinon celui choisi au moment
            # de la validation.
            point = commande.point_livraison
            if point is None:
                point = exploitant.points_livraison.filter(
                    pk=request.POST.get("point_livraison")).first()
            if point is None and exploitant.points_livraison.exists():
                messages.error(
                    request, "Un point de livraison est requis pour "
                    "valider : choisissez-en un puis validez à nouveau.")
                return redirect("portal:order_list")
            if point is None:
                messages.error(
                    request, "Aucun point de livraison : créez-en un "
                    "d'abord dans « Livraison » (Points & créneaux).")
                return redirect("portal:order_list")
            ajustees, erreurs, total = [], [], Decimal("0")
            for ligne in commande.lignes.select_related("produit"):
                brut = request.POST.get(f"qty_{ligne.pk}", "").strip()
                qty, erreur = _quantite_ajustee(brut, ligne.quantite,
                                                ligne.produit)
                if erreur:
                    erreurs.append(erreur)
                    continue
                if qty is None:
                    continue  # ligne retirée
                ajustees.append((ligne, qty))
                total += qty * ligne.prix_unitaire
            if erreurs:
                messages.error(request, " ".join(erreurs))
                return redirect("portal:order_list")
            if not ajustees:
                messages.error(
                    request, "Impossible de valider : toutes les lignes "
                    "auraient été retirées.")
                return redirect("portal:order_list")
            with transaction.atomic():
                commande.statut = Commande.Statut.VALIDEE
                commande.validee_le = timezone.now()
                commande.point_livraison = point
                commande.save()
                panier = Panier.objects.create(
                    exploitant=exploitant,
                    client=commande.client,
                    nom_client=commande.nom_client,
                    email_client=commande.email_client,
                    telephone_client=commande.telephone_client,
                    numero=Panier.prochain_numero(
                        exploitant, commande.date_livraison,
                        point_livraison=point),
                    date_livraison=commande.date_livraison,
                    point_livraison=point,
                    commande=commande,
                    statut=Panier.Statut.PREPARATION,
                    total=total,
                    note=request.POST.get("note", "").strip())
                for ligne, qty in ajustees:
                    LignePanier.objects.create(
                        panier=panier, produit=ligne.produit,
                        quantite=qty,
                        prix_unitaire=ligne.prix_unitaire)
            messages.success(
                request, f"Commande #{commande.pk} validée → "
                f"panier n°{panier.numero} créé pour "
                f"{panier.nom_client}.")
            notifier_client(request, panier, "CONFIRMATION_COMMANDE")
        elif action == "refuse":
            commande.statut = Commande.Statut.REFUSEE
            commande.save()
            messages.info(request, f"Commande #{commande.pk} refusée.")
    return redirect("portal:order_list")


@login_required
@exploitant_requis
def panier_list(request):
    """Liste des paniers, regroupés visuellement par jour de livraison
    (en-tête du jour : comptage par statut, code couleur associé)."""
    exploitant = exploitant_pour(request.user)
    paniers = list((exploitant.paniers
                    .select_related("client", "point_livraison")
                    .prefetch_related("lignes__produit__categorie",
                                      "lignes__produit__origine_standard")
                    .order_by("-date_livraison", "numero")))
    photos, telephones = _profils_clients(
        {p.client_id for p in paniers if p.client_id})
    for panier in paniers:
        panier.photo_client = photos.get(panier.client_id, "")
        panier.tel_client = telephones.get(panier.client_id, "")
        panier.groupes_lignes = _groupes_lignes(list(panier.lignes.all()))
    return render(request, "portal/pro/paniers.html", {
        "paniers": paniers,
        "today": timezone.localdate(),
        "jours_badges": _badges_par_jour(paniers, "statut",
                                         Panier.Statut.choices),
    })


@login_required
@exploitant_requis
def panier_export_csv(request):
    """Export CSV (issue #8). Deux modes :
    - detail (défaut) : ligne par ligne, chaque panier avec son client ;
    - production : récapitulatif par produit des paniers LIVRÉS/REÇUS
      (seule source du décompte de production). Filtre date optionnel."""
    exploitant = exploitant_pour(request.user)
    date_filter = request.GET.get("date", "").strip()
    mode = request.GET.get("mode", "detail")
    paniers = (exploitant.paniers.select_related("client", "point_livraison")
               .prefetch_related("lignes__produit")
               .order_by("date_livraison", "numero"))
    if date_filter:
        try:
            date_filter = datetime.date.fromisoformat(date_filter).isoformat()
        except ValueError:
            date_filter = ""
        else:
            paniers = paniers.filter(date_livraison=date_filter)
    paniers = list(paniers)

    tampon = io.StringIO()
    writer = csv.writer(tampon, delimiter=";")
    if mode == "production":
        writer.writerow(["Produit", "Unite", "Quantite livree",
                         "Total (EUR)", "Nb paniers"])
        agg = {}
        for panier in paniers:
            if panier.statut not in (Panier.Statut.LIVRE,
                                     Panier.Statut.RECU):
                continue
            for ligne in panier.lignes.all():
                e = agg.setdefault(ligne.produit_id,
                                   {"produit": ligne.produit,
                                    "qte": Decimal("0"),
                                    "total": Decimal("0"),
                                    "paniers": set()})
                e["qte"] += ligne.quantite
                e["total"] += ligne.quantite * ligne.prix_unitaire
                e["paniers"].add(panier.pk)
        for e in sorted(agg.values(), key=lambda x: x["produit"].nom):
            writer.writerow([
                e["produit"].nom, e["produit"].unite_courte,
                str(e["qte"]).replace(".", ","),
                str(e["total"]).replace(".", ","),
                len(e["paniers"])])
    else:
        writer.writerow(["Panier", "Date", "Statut", "Client", "E-mail",
                         "Telephone", "Point de livraison",
                         "Produit", "Unite", "Quantite livree",
                         "Prix unitaire (EUR)", "Total ligne (EUR)",
                         "Total panier (EUR)"])
        for panier in paniers:
            lignes = list(panier.lignes.all())
            if not lignes:
                writer.writerow([f"n°{panier.numero}",
                                 panier.date_livraison.strftime("%d/%m/%Y"),
                                 panier.get_statut_display(),
                                 panier.nom_client, panier.email_client,
                                 panier.telephone_client,
                                 panier.point_livraison.nom
                                 if panier.point_livraison else "",
                                 "", "", "", "", "",
                                 str(panier.total).replace(".", ",")])
            for ligne in lignes:
                writer.writerow([
                    f"n°{panier.numero}",
                    panier.date_livraison.strftime("%d/%m/%Y"),
                    panier.get_statut_display(),
                    panier.nom_client, panier.email_client,
                    panier.telephone_client,
                    panier.point_livraison.nom
                    if panier.point_livraison else "",
                    ligne.produit.nom,
                    ligne.produit.unite_courte,
                    str(ligne.quantite).replace(".", ","),
                    str(ligne.prix_unitaire).replace(".", ","),
                    str(ligne.total_ligne()).replace(".", ","),
                    str(panier.total).replace(".", ",")])

    nom = "paniers_" + (date_filter or "tous") + "_" + mode + ".csv"
    reponse = HttpResponse("\ufeff" + tampon.getvalue(),
                           content_type="text/csv; charset=utf-8")
    reponse["Content-Disposition"] = f'attachment; filename="{nom}"'
    return reponse


@login_required
@exploitant_requis
def panier_detail(request, panier_id):
    """Préparation du panier : ajustement du contenu EFFECTIVEMENT livré,
    comparé côte à côte aux quantités souhaitées par le client, avec
    commentaire visible par le client. Chaque changement de statut notifie
    le client (panier prêt, livraison faite) selon son canal préféré."""
    exploitant = exploitant_pour(request.user)
    panier = get_object_or_404(Panier, pk=panier_id, exploitant=exploitant)
    verrouille = panier.statut in (Panier.Statut.LIVRE,
                                   Panier.Statut.RECU)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "lignes":
            if verrouille:
                messages.warning(
