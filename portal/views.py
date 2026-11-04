import csv
import datetime
import io
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (InscriptionClientForm, InscriptionExploitantForm,
                    ProduitForm, ProfilExploitantForm, ProfilPersonnelForm)
from .meteo import meteo_synthese
from .models import (Categorie, Commande, CreneauLivraison, Exploitant,
                    LigneCommande, LignePanier, LigneRecolte,
                    MembreExploitation, Panier, ParametresVitrine,
                    PointLivraison, PreferenceContact, Produit,
                    ProduitStandard, ProfilClient, SemaineRecolte,
                    exploitant_pour)
from .notifications import notifier_client

# Unités vendues à la pièce : quantités entières uniquement.
UNITES_ENTIERES = ("PC", "BO", "BQ")


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
    exploitants = list(exploitants)
    # Données carto : uniquement les résultats filtrés avec coordonnées.
    carte_data = [{
        "nom_ferme": e.nom_ferme,
        "mode_production": e.mode_production,
        "ville": e.ville,
        "latitude": e.latitude,
        "longitude": e.longitude,
        "url": e.get_absolute_url(),
    } for e in exploitants
        if e.latitude is not None and e.longitude is not None]
    return render(request, "portal/search_results.html", {
        "exploitants": exploitants,
        "carte_data": carte_data,
        "q": q, "dept": dept, "mode": mode,
    })


def producteurs_geojson(request):
    """Données carte : exploitants visibles avec coordonnées."""
    exploitants = (Exploitant.objects.filter(visible=True)
                   .exclude(latitude=None, longitude=None))
    data = [{
        "slug": e.slug,
        "nom_ferme": e.nom_ferme,
        "mode_production": e.mode_production,
        "ville": e.ville,
        "latitude": e.latitude,
        "longitude": e.longitude,
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
    return render(request, "portal/producer_detail.html", {
        "exploitant": exploitant,
        "vitrine": vitrine,
        "semaine": semaine,
        "lignes": lignes,
        "groupes_categories": groupes,
        "semaines_avenir": semaines_avenir,
        "meteo": meteo_synthese(exploitant),
        "points_livraison": exploitant.points_livraison.all(),
        "creneaux": exploitant.creneaux.select_related("point_livraison"),
    })


# ---------------------------------------------------------------- registres


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
                request, "Bienvenue ! Votre espace exploitant est prêt : "
                "commencez par ajouter vos produits.")
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
            return redirect("portal:home")
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

@login_required
@exploitant_requis
def dashboard(request):
    """Page centrale du maraîcher : rubriques à gauche, aperçu de la
    vitrine publique en direct à droite, hero météo et bandeau des
    créneaux de livraison (jour + horaires). Produits rangés par
    catégorie, éditables sur place (libellé, unité, prix)."""
    exploitant = exploitant_pour(request.user)
    produits = (exploitant.produits.filter(actif=True)
                .select_related("categorie")
                .order_by("categorie__position", "categorie__nom", "nom"))
    groupes, ordre = {}, []
    for p in produits:
        nom_cat = p.categorie.nom if p.categorie else "Sans catégorie"
        if nom_cat not in groupes:
            groupes[nom_cat] = []
            ordre.append(nom_cat)
        groupes[nom_cat].append(p)
    paires = [(nom, groupes[nom]) for nom in ordre]
    return render(request, "portal/pro/dashboard.html", {
        "exploitant": exploitant,
        "paires": paires,
        "unite_choices": Produit.Unite.choices,
        "meteo": meteo_synthese(exploitant),
        "semaine": SemaineRecolte.objects.filter(exploitant=exploitant)
                   .order_by("-lundi").first(),
        "semaines": list(SemaineRecolte.objects
                         .filter(exploitant=exploitant)
                         .annotate(nb_lignes=Count("lignes"))
                         .order_by("-lundi")[:6]),
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
            return redirect("portal:dashboard")
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
            return redirect("portal:dashboard")
    else:
        form = ProduitForm(instance=produit,
                           exploitant=exploitant_pour(request.user))
    return render(request, "portal/pro/product_form.html",
                  {"form": form, "titre": "Modifier le produit",
                   "categories_url": "portal:categories_manage"})


@login_required
@exploitant_requis
def produit_edition_rapide(request):
    """Mode édition du dashboard : libellé, unité et prix de référence
    modifiés en place, sans passer par la fiche produit."""
    exploitant = exploitant_pour(request.user)
    if request.method == "POST":
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
    return redirect("portal:dashboard")


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
                .select_related("categorie")
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


@login_required
@exploitant_requis
def order_list(request, statut=None):
    """Commandes reçues, avec contact client (e-mail, téléphone, canal
    préféré si le client en a exprimé un)."""
    exploitant = exploitant_pour(request.user)
    commandes = exploitant.commandes.order_by("-creee_le")
    if statut:
        commandes = commandes.filter(statut=statut)
    canaux = {p.client_id: p.get_canal_display()
              for p in PreferenceContact.objects.filter(exploitant=exploitant)}
    commandes = list(commandes.prefetch_related("lignes__produit"))
    for c in commandes:
        c.canal_pref = canaux.get(c.client_id) if c.client_id else None
    return render(request, "portal/pro/orders.html",
                  {"commandes": commandes, "filtre_statut": statut,
                   "points": exploitant.points_livraison.all()})


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
                    .select_related("categorie")
                    .order_by("categorie__position", "nom"))
    points = exploitant.points_livraison.all()
    creneaux = exploitant.creneaux.select_related("point_livraison")

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
    """Liste des paniers, filtrable par jour de livraison."""
    exploitant = exploitant_pour(request.user)
    paniers = (exploitant.paniers.select_related("client", "point_livraison")
               .prefetch_related("lignes__produit")
               .order_by("-date_livraison", "numero"))
    date_filter = request.GET.get("date", "").strip()
    if date_filter:
        try:
            date_filter = datetime.date.fromisoformat(date_filter).isoformat()
        except ValueError:
            date_filter = ""
        else:
            paniers = paniers.filter(date_livraison=date_filter)
    return render(request, "portal/pro/paniers.html",
                  {"paniers": paniers, "date_filter": date_filter})


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

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "lignes":
            ajustes, erreurs, total = {}, [], Decimal("0")
            for ligne in panier.lignes.select_related("produit"):
                brut = request.POST.get(f"qty_{ligne.pk}", "").strip()
                if brut == "":
                    ajustes[ligne.pk] = ligne.quantite  # vide = conserver
                    continue
                try:
                    qty = Decimal(brut)
                except InvalidOperation:
                    erreurs.append(f"« {ligne.produit.nom} » : quantité invalide.")
                    continue
                if qty <= 0:
                    ajustes[ligne.pk] = None
                    continue
                if (ligne.produit.unite_vente in UNITES_ENTIERES
                        and qty != qty.to_integral_value()):
                    erreurs.append(f"« {ligne.produit.nom} » se vend à la "
                                   "pièce : quantité entière requise.")
                    continue
                ajustes[ligne.pk] = qty
            pid = request.POST.get("produit_ajout", "").strip()
            qadd = request.POST.get("qty_ajout", "").strip()
            ajout = None
            if pid and qadd:
                produit = exploitant.produits.filter(
                    pk=pid, actif=True).first()
                try:
                    qadd = Decimal(qadd)
                except InvalidOperation:
                    produit = None
                if produit and qadd > 0:
                    if (produit.unite_vente in UNITES_ENTIERES
                            and qadd != qadd.to_integral_value()):
                        erreurs.append(f"« {produit.nom} » se vend à la "
                                       "pièce : quantité entière requise.")
                    else:
                        ajout = (produit, qadd)
            if erreurs:
                messages.error(request, " ".join(erreurs))
                return redirect("portal:panier_detail", panier.pk)
            with transaction.atomic():
                for ligne in panier.lignes.select_related("produit"):
                    qty = ajustes.get(ligne.pk, ligne.quantite)
                    if qty is None:
                        ligne.delete()
                        continue
                    ligne.quantite = qty
                    ligne.save()
                    total += qty * ligne.prix_unitaire
                if ajout:
                    produit, qadd = ajout
                    prix = produit.prix or Decimal("0")
                    LignePanier.objects.create(
                        panier=panier, produit=produit,
                        quantite=qadd, prix_unitaire=prix)
                    total += qadd * prix
                panier.total = total
                panier.note = request.POST.get("note", "").strip()
                panier.save()
            messages.success(
                request, f"Panier n°{panier.numero} mis à jour "
                f"({panier.total} €).")

        elif action == "statut":
            nouveau = request.POST.get("statut", "")
            if nouveau in Panier.Statut.values:
                panier.statut = nouveau
                panier.save()
                messages.success(
                    request, f"Panier n°{panier.numero} : "
                    f"{panier.get_statut_display()}.")
                if panier.statut == Panier.Statut.PRET:
                    notifier_client(request, panier, "PANIER_PRET")
                elif panier.statut in (Panier.Statut.LIVRE,
                                       Panier.Statut.RECU):
                    notifier_client(request, panier, "LIVRAISON_FAITE")

        return redirect("portal:panier_detail", panier.pk)

    # Comparatif souhaité (client) / livré, ligne par ligne
    souhaitees = {}
    if panier.commande_id:
        souhaitees = {lc.produit_id: lc.quantite
                     for lc in panier.commande.lignes.all()}
    rows = []
    for ligne in panier.lignes.select_related("produit"):
        souh = souhaitees.get(ligne.produit_id)
        rows.append({
            "ligne": ligne,
            "souhaite": souh,
            "ajuste": souh is not None and souh != ligne.quantite,
            "step": "0.01" if ligne.produit.unite_vente == "KG" else "1",
        })
    return render(request, "portal/pro/panier_detail.html", {
        "panier": panier,
        "rows": rows,
        "produits": exploitant.produits.filter(actif=True),
    })


@login_required
@exploitant_requis
def clients_suivi(request):
    """Suivi « Mes clients » : regroupement par identité contact (compte
    client ou nom + e-mail/téléphone), cumul des commandes, paniers et
    chiffre d'affaires, canal de contact préféré."""
    exploitant = exploitant_pour(request.user)
    q = request.GET.get("q", "").strip().lower()
    registre = {}

    def enregistrer(client_id, nom, email, tel):
        cle = ("u%d" % client_id if client_id
               else "c:%s|%s" % ((nom or "").lower(), (email or "").lower()))
        if cle not in registre:
            registre[cle] = {
                "nom": nom, "email": email or "", "telephone": tel or "",
                "client_id": client_id,
                "nb_commandes": 0, "nb_paniers": 0,
                "total": Decimal("0"), "derniere": None,
            }
        return registre[cle]

    for c in exploitant.commandes.all():
        e = enregistrer(c.client_id, c.nom_client, c.email_client,
                        c.telephone_client)
        e["nb_commandes"] += 1
        if not e["derniere"] or c.date_livraison > e["derniere"]:
            e["derniere"] = c.date_livraison
    for p in exploitant.paniers.all():
        e = enregistrer(p.client_id, p.nom_client, p.email_client,
                        p.telephone_client)
        e["nb_paniers"] += 1
        e["total"] += p.total
        if not e["derniere"] or p.date_livraison > e["derniere"]:
            e["derniere"] = p.date_livraison

    canaux = {pc.client_id: pc for pc in
              PreferenceContact.objects.filter(exploitant=exploitant)}
    rows = []
    for e in registre.values():
        pref = canaux.get(e["client_id"]) if e["client_id"] else None
        e["canal"] = pref.get_canal_display() if pref else "E-mail"
        rows.append(e)
    rows.sort(key=lambda e: (-e["total"], e["nom"].lower()))
    if q:
        rows = [e for e in rows
                if q in e["nom"].lower() or q in e["email"].lower()
                or q in e["telephone"].lower()]
    return render(request, "portal/pro/clients.html",
                  {"rows": rows, "q": request.GET.get("q", "")})


@login_required
@exploitant_requis
def points_manage(request):
    """Points de livraison & créneaux (issue #9) : création, suppression,
    créneaux récurrents (jour, horaires, fréquence, capacité)."""
    exploitant = exploitant_pour(request.user)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "point_creer":
            nom = request.POST.get("nom", "").strip()
            adresse = request.POST.get("adresse", "").strip()
            ville = request.POST.get("ville", "").strip()
            code_postal = request.POST.get("code_postal", "").strip()
            note = request.POST.get("note", "").strip()
            if not nom or not ville:
                messages.error(request, "Nom et ville du point requis.")
            else:
                PointLivraison.objects.create(
                    exploitant=exploitant, nom=nom[:150],
                    adresse=adresse[:255], ville=ville[:100],
                    code_postal=code_postal[:10], note=note)
                messages.success(request,
                                 f"Point « {nom} » créé.")
        elif action == "point_supprimer":
            point = get_object_or_404(PointLivraison,
                                     pk=request.POST.get("pk"),
                                     exploitant=exploitant)
            nb = point.creneaux.count()
            point.delete()
            message = f"Point « {point.nom} » supprimé"
            if nb:
                message += f" (et {nb} créneau(x) rattaché(s))"
            messages.info(request, message + ".")
        elif action == "creneau_ajouter":
            brut_point = request.POST.get("point", "").strip()
            point = (exploitant.points_livraison
                     .filter(pk=brut_point).first() if brut_point else None)
            try:
                jour = int(request.POST.get("jour", ""))
                capacite = int(request.POST.get("capacite") or 10)
                heure_debut = datetime.time.fromisoformat(
                    request.POST.get("heure_debut", ""))
                heure_fin = datetime.time.fromisoformat(
                    request.POST.get("heure_fin", ""))
            except (TypeError, ValueError):
                messages.error(request, "Créneau invalide "
                               "(jour, horaires ou capacité).")
                return redirect("portal:points_manage")
            frequence = request.POST.get("frequence", "")
            if not (1 <= jour <= 7) or heure_debut >= heure_fin:
                messages.error(request, "Créneau invalide : jour entre "
                               "lundi et dimanche, fin après le début.")
            elif frequence not in CreneauLivraison.Frequence.values:
                messages.error(request, "Fréquence inconnue.")
            else:
                CreneauLivraison.objects.create(
                    exploitant=exploitant, point_livraison=point,
                    jour=jour, heure_debut=heure_debut,
                    heure_fin=heure_fin, frequence=frequence,
                    capacite=capacite)
                messages.success(request, "Créneau ajouté.")
        elif action == "creneau_supprimer":
            creneau = get_object_or_404(CreneauLivraison,
                                        pk=request.POST.get("pk"),
                                        exploitant=exploitant)
            creneau.delete()
            messages.info(request, "Créneau supprimé.")
        return redirect("portal:points_manage")

    points = (exploitant.points_livraison
              .prefetch_related("creneaux").order_by("ville", "nom"))
    return render(request, "portal/pro/points.html", {
        "points": points,
        "jours": CreneauLivraison._meta.get_field("jour").choices,
        "frequences": CreneauLivraison.Frequence.choices,
        "creneaux_sans_point": exploitant.creneaux
                              .filter(point_livraison__isnull=True),
    })


# ------------------------------------------------- catalogue & catégories

@login_required
@exploitant_requis
@proprietaire_requis
def catalogue_standard(request):
    """Catalogue embarqué de produits types (issue #1) : base de départ
    copiable en un clic, avec traçabilité origine_standard."""
    exploitant = exploitant_pour(request.user)
    standards = ProduitStandard.objects.order_by("categorie", "nom")
    deja_copies = set(Produit.objects.filter(
        exploitant=exploitant,
        origine_standard__isnull=False
    ).values_list("origine_standard_id", flat=True))
    groupes, ordre = {}, []
    for std in standards:
        if std.categorie not in groupes:
            groupes[std.categorie] = []
            ordre.append(std.categorie)
        groupes[std.categorie].append({
            "std": std,
            "deja": std.pk in deja_copies,
        })
    paires = [(cat, groupes[cat]) for cat in ordre]
    return render(request, "portal/pro/catalogue_standard.html",
                  {"paires": paires})


@login_required
@exploitant_requis
@proprietaire_requis
def catalogue_copier(request):
    """Copie les produits types sélectionnés dans le catalogue de
    l'exploitant : catégorie créée si besoin, prix optionnel, traçabilité
    origine_standard (issue #1)."""
    exploitant = exploitant_pour(request.user)
    if request.method == "POST":
        ids = request.POST.getlist("std")
        copies = 0
        for std in ProduitStandard.objects.filter(pk__in=ids):
            if Produit.objects.filter(exploitant=exploitant,
                                      origine_standard=std).exists():
                continue
            cat, _cree = Categorie.objects.get_or_create(
                exploitant=exploitant, nom=std.categorie)
            if _cree:
                cat.position = exploitant.categories.count()
                cat.save()
            prix = None
            brut = request.POST.get(f"prix_{std.pk}", "").strip()
            if brut:
                try:
                    prix = Decimal(brut)
                except InvalidOperation:
                    prix = None
            Produit.objects.create(
                exploitant=exploitant, nom=std.nom, categorie=cat,
                description="", unite_vente=std.unite_vente,
                attributs={"saisons": std.saisons},
                origine_standard=std, prix=prix, actif=True)
            copies += 1
        if copies:
            messages.success(request, f"{copies} produit(s) copié(s) dans "
                             "votre catalogue — complétez les prix si besoin.")
        else:
            messages.info(request, "Aucun nouveau produit copié.")
    return redirect("portal:catalogue_standard")


@login_required
@exploitant_requis
@proprietaire_requis
def categories_manage(request):
    """Gestion des catégories de l'exploitant (issue #5) : créer,
    renommer, réordonner, supprimer. Supprimer ne touche pas les produits
    (ils passent « sans catégorie»)."""
    exploitant = exploitant_pour(request.user)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "creer":
            nom = request.POST.get("nom", "").strip()
            if nom:
                cat, cree = Categorie.objects.get_or_create(
                    exploitant=exploitant, nom=nom[:80])
                if cree:
                    cat.position = exploitant.categories.count()
                    cat.save()
                    messages.success(request,
                                     f"Catégorie « {cat.nom} » créée.")
                else:
                    messages.info(request, "Cette catégorie existe déjà.")
        elif action == "renommer":
            cat = get_object_or_404(Categorie, pk=request.POST.get("pk"),
                                   exploitant=exploitant)
            nom = request.POST.get("nom", "").strip()
            if nom:
                cat.nom = nom[:80]
                cat.save()
                messages.success(request, "Catégorie renommée.")
        elif action == "supprimer":
            cat = get_object_or_404(Categorie, pk=request.POST.get("pk"),
                                   exploitant=exploitant)
            nb = cat.produits.count()
            nom = cat.nom
            cat.delete()
            message = f"Catégorie « {nom} » supprimée"
            if nb:
                message += (f" — {nb} produit(s) désormais sans catégorie "
                            "(reclassez-les en les modifiant).")
            messages.info(request, message + ".")
        elif action in ("monter", "descendre"):
            cat = get_object_or_404(Categorie, pk=request.POST.get("pk"),
                                    exploitant=exploitant)
            voisines = list(exploitant.categories.order_by("position", "nom"))
            i = voisines.index(cat)
            j = i - 1 if action == "monter" else i + 1
            if 0 <= j < len(voisines):
                voisines[i], voisines[j] = voisines[j], voisines[i]
                for k, c in enumerate(voisines):
                    c.position = k
                    c.save()
        return redirect("portal:categories_manage")
    categories = exploitant.categories.order_by("position", "nom")
    return render(request, "portal/pro/categories.html",
                  {"categories": categories})


# ---------------------------------------------------------------- client

def order_create(request, slug):
    """Le client choisit produits/quantités/date et soumet sa commande.

    Les quantités affichées sont des estimations : aucune commande n'est
    bloquée par une quantité indicative. Un exploitant ne peut pas se
    commander à lui-même via la vitrine : il doit passer par la saisie
    directe de son espace pro.

    Sans compte (nouveau client) : la commande est possible en
    renseignant nom + e-mail OU téléphone — le producteur recontacte le
    client au moment de la validation.
    """
    exploitant = get_object_or_404(Exploitant, slug=slug, visible=True)
    if (exploitant_pour(request.user) is not None
            and exploitant_pour(request.user).pk == exploitant.pk):
        messages.info(request, "Vous êtes le producteur de cette ferme : "
                     "utilisez « Saisir une commande » dans votre espace "
                     "pro pour enregistrer une commande (la vôtre par "
                     "exemple).")
        return redirect("portal:producer_detail", slug=slug)
    today = timezone.localdate()
    lundi = today - datetime.timedelta(days=today.weekday())
    semaine = (SemaineRecolte.objects.filter(exploitant=exploitant,
                                             publiee=True,
                                             lundi__lte=lundi)
               .order_by("-lundi").first())
    if not semaine:
        messages.info(request,
                      "Ce producteur n'a pas encore publié de récolte.")
        return redirect("portal:producer_detail", slug=slug)
    lignes = semaine.lignes.select_related("produit")

    if request.method == "POST":
        lignes_souhaitees, total = [], Decimal("0")
        for ligne in lignes:
            brut = request.POST.get(f"qty_{ligne.pk}", "").strip()
            if not brut:
                continue
            try:
                qty = Decimal(brut)
            except InvalidOperation:
                continue
            if qty <= 0:
                continue
            if (ligne.produit.unite_vente in UNITES_ENTIERES
                    and qty != qty.to_integral_value()):
                messages.error(
                    request, f"« {ligne.produit.nom} » se vend à la pièce : "
                    "merci de commander un nombre entier.")
                return redirect("portal:order_create", slug=slug)
            lignes_souhaitees.append((ligne, qty))
            total += qty * ligne.prix_unitaire
        point = exploitant.points_livraison.filter(
            pk=request.POST.get("point_livraison")).first()
        if point is None and exploitant.points_livraison.exists():
            messages.error(request, "Merci de choisir un point de "
                           "livraison pour votre commande.")
            return redirect("portal:order_create", slug=slug)
        try:
            date_livraison = datetime.date.fromisoformat(
                request.POST["date_livraison"])
        except (KeyError, ValueError):
            date_livraison = None
        if (not lignes_souhaitees or date_livraison is None
                or date_livraison < today):
            messages.error(request,
                           "Commande invalide : vérifiez les quantités et la date.")
            return redirect("portal:order_create", slug=slug)
        if request.user.is_authenticated:
            client, nom_client = request.user, (
                request.user.get_full_name() or request.user.username)
            email_client, telephone_client = request.user.email, ""
        else:
            client = None
            nom_client = request.POST.get("nom_client", "").strip()
            email_client = request.POST.get("email_client", "").strip()
            telephone_client = request.POST.get(
                "telephone_client", "").strip()
            if not nom_client:
                messages.error(request, "Merci d'indiquer votre nom.")
                return redirect("portal:order_create", slug=slug)
            if not email_client and not telephone_client:
                messages.error(request, "Sans compte, indiquez un e-mail ou "
                               "un téléphone pour que le producteur puisse "
                               "vous recontacter.")
                return redirect("portal:order_create", slug=slug)
        with transaction.atomic():
            commande = Commande.objects.create(
                exploitant=exploitant, client=client,
                nom_client=nom_client[:150], email_client=email_client,
                telephone_client=telephone_client,
                point_livraison=point, date_livraison=date_livraison,
                note=request.POST.get("note", ""), total=total)
            for ligne, qty in lignes_souhaitees:
                LigneCommande.objects.create(
                    commande=commande, produit=ligne.produit,
                    quantite=qty, prix_unitaire=ligne.prix_unitaire)
        if client:
            messages.success(
                request, "Commande envoyée ! Le producteur va la valider, "
                "vous la retrouverez dans « Mes commandes ».")
            return redirect("portal:my_orders")
        contact = email_client or telephone_client
        messages.success(
            request, "Commande envoyée ! Le producteur vous recontactera "
            f"via {contact} pour valider votre commande.")
        return redirect("portal:producer_detail", slug=slug)

    # Dates futures correspondant aux jours de créneaux (28 jours)
    jours = {c.jour for c in exploitant.creneaux.all()}
    dates = []
    for i in range(0, 29):
        d = today + datetime.timedelta(days=i)
        if d.isoweekday() in jours or not jours:
            dates.append(d)
    return render(request, "portal/order_create.html", {
        "exploitant": exploitant,
        "semaine": semaine,
        "lignes": lignes,
        "points_livraison": exploitant.points_livraison.all(),
        "dates": dates,
    })


@login_required
def my_orders(request):
    """Commandes du client ; les paniers validés montrent le contenu
    livré côte à côte du souhaité, avec le commentaire du producteur."""
    commandes = (request.user.commandes.select_related("exploitant")
                 .prefetch_related("lignes__produit").order_by("-creee_le"))
    resultats = []
    for commande in commandes:
        panier = (Panier.objects.filter(commande=commande)
                  .prefetch_related("lignes__produit").first())
        lignes_panier = []
        if panier:
            souhaitees = {lc.produit_id: lc.quantite
                          for lc in commande.lignes.all()}
            for lp in panier.lignes.all():
                souh = souhaitees.get(lp.produit_id)
                lignes_panier.append({
                    "ligne": lp,
                    "souhaite": souh,
                    "ajuste": souh is not None and souh != lp.quantite,
                })
        resultats.append({"commande": commande, "panier": panier,
                          "lignes_panier": lignes_panier})
    return render(request, "portal/my_orders.html",
                  {"resultats": resultats})


@login_required
def order_cancel(request, commande_id):
    commande = get_object_or_404(Commande, pk=commande_id, client=request.user)
    if (request.method == "POST"
            and commande.statut == Commande.Statut.NOUVELLE):
        commande.statut = Commande.Statut.ANNULEE
        commande.save()
        messages.info(request, f"Commande #{commande.pk} annulée.")
    return redirect("portal:my_orders")


# ----------------------------------------------------------- editions profil

def _enregistrer_infos_perso(request, redirect_vers):
    """Enregistre prenom / nom / e-mail du compte courant, et son
    telephone dans ProfilClient (commun clients et maraichers)."""
    profil, _cree = ProfilClient.objects.get_or_create(user=request.user)
    form = ProfilPersonnelForm(request.POST)
    if form.is_valid():
        user = request.user
        user.first_name = form.cleaned_data["prenom"]
        user.last_name = form.cleaned_data["nom"]
        user.email = form.cleaned_data["email"]
        user.save()
        profil.telephone = form.cleaned_data["telephone"]
        profil.save()
        messages.success(request, "Vos informations personnelles ont été "
                         "mises à jour.")
        return redirect(redirect_vers)
    return form


@login_required
def profil_client(request):
    """Le client édite ses informations : prenom, nom, e-mail, telephone."""
    profil, _cree = ProfilClient.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = _enregistrer_infos_perso(request, "portal:my_orders")
        if not hasattr(form, "is_valid"):
            return form  # redirection déjà émise
    else:
        form = ProfilPersonnelForm(initial={
            "prenom": request.user.first_name,
            "nom": request.user.last_name,
            "email": request.user.email,
            "telephone": profil.telephone,
        })
    return render(request, "portal/profil_client.html", {"form": form})


@login_required
@exploitant_requis
@proprietaire_requis
def profil_exploitant(request):
    """Fiche de l'exploitation : ferme, SIRET, adresse, coordonnees
    carto, logo (fichier OU lien externe). La validite du SIRET (cle de
    Luhn) determine le badge public. Le departement est deduit du code
    postal s'il n'est pas saisi."""
    exploitant = exploitant_pour(request.user)
    vitrine, _cree = ParametresVitrine.objects.get_or_create(
        exploitant=exploitant)
    if request.method == "POST":
        form = ProfilExploitantForm(request.POST, request.FILES,
                                    instance=exploitant)
        if form.is_valid():
            form.save()
            # Logo externe : stocke dans les parametres de vitrine
            # (JSONB reseaux), aucun fichier heberge par le portail.
            reseaux = dict(vitrine.reseaux or {})
            url = form.cleaned_data.get("logo_externe", "").strip()
            if url:
                reseaux["logo_url"] = url
            else:
                reseaux.pop("logo_url", None)
            vitrine.reseaux = reseaux
            vitrine.save()
            if exploitant.siret and not exploitant.siret_valide:
                messages.warning(
                    request, "Fiche enregistrée, mais le numéro SIRET "
                    "n'est pas valide (14 chiffres attendus) : votre "
                    "vitrine affichera « Producteur particulier ».")
            else:
                messages.success(request, "Votre fiche a été mise à jour.")
            return redirect("portal:dashboard")
    else:
        form = ProfilExploitantForm(
            instance=exploitant,
            initial={"logo_externe": (vitrine.reseaux or {}).get(
                "logo_url", "")})
    return render(request, "portal/pro/profil_exploitant.html",
                  {"form": form, "exploitant": exploitant})


@login_required
@exploitant_requis
def profil_personnel(request):
    """Informations personnelles du compte maraicher individuel (prenom,
    nom, e-mail, telephone) : chaque membre de l'equipe garde son
    identite propre, la fiche exploitation restant partagee."""
    profil, _cree = ProfilClient.objects.get_or_create(user=request.user)
    if request.method == "POST":
        resultat = _enregistrer_infos_perso(request, "portal:profil_personnel")
        if not hasattr(resultat, "is_valid"):
            return resultat  # redirection
        form = resultat
    else:
        form = ProfilPersonnelForm(initial={
            "prenom": request.user.first_name,
            "nom": request.user.last_name,
            "email": request.user.email,
            "telephone": profil.telephone,
        })
    return render(request, "portal/pro/profil_personnel.html",
                  {"form": form})


@login_required
@exploitant_requis
@proprietaire_requis
def equipe_manage(request):
    """Equipe de l'exploitation : plusieurs comptes individuels gerent la
    meme ferme (meme SIRET). Le proprietaire rattache un compte existant
    par e-mail ou identifiant ; un compte possedant deja sa propre
    exploitation est refuse."""
    exploitant = exploitant_pour(request.user)
    est_proprietaire = (hasattr(request.user, "exploitant")
                        and request.user.exploitant.pk == exploitant.pk)
    if request.method == "POST" and est_proprietaire:
        action = request.POST.get("action")
        if action == "ajouter":
            cle = request.POST.get("membre", "").strip()
            if not cle:
                messages.error(request, "Renseignez l'e-mail ou "
                               "l'identifiant du compte à rattacher.")
                return redirect("portal:equipe_manage")
            user = (User.objects.filter(email__iexact=cle).first()
                    or User.objects.filter(username__iexact=cle).first())
            if user is None:
                messages.error(
                    request, f"Aucun compte « {cle} » : la personne doit "
                    "d'abord créer un compte sur le portail, vous pourrez "
                    "ensuite la rattacher à l'exploitation.")
            elif hasattr(user, "exploitant"):
                messages.error(
                    request, f"« {cle} » possède déjà sa propre "
                    "exploitation : impossible de le rattacher en membre.")
            elif hasattr(user, "membre_exploitation"):
                messages.error(
                    request, f"« {cle} » est déjà membre d'une "
                    "exploitation.")
            else:
                MembreExploitation.objects.create(
                    user=user, exploitant=exploitant,
                    telephone=request.POST.get("telephone", "").strip())
                messages.success(
                    request, f"{user.get_full_name() or user.username} "
                    "rattaché(e) à l'exploitation : ce compte accède "
                    "désormais au même espace pro.")
        elif action == "retirer":
            membre = exploitant.membres.filter(
                pk=request.POST.get("membre_id")).first()
            if membre:
                nom = membre.user.get_full_name() or membre.user.username
                membre.delete()
                messages.info(request, f"{nom} n'est plus membre de "
                               "l'exploitation.")
        return redirect("portal:equipe_manage")
    membres = exploitant.membres.select_related("user").all()
    return render(request, "portal/pro/equipe.html", {
        "exploitant": exploitant,
        "membres": membres,
        "est_proprietaire": est_proprietaire,
    })
