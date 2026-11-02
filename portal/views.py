import datetime
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (InscriptionClientForm, InscriptionExploitantForm,
                    ProduitForm)
from .models import (Commande, Exploitant, LigneCommande, LignePanier,
                    LigneRecolte, Panier, Produit, SemaineRecolte)


def home(request):
    """Landing : bandeau, recherche, hero, carte des exploitants."""
    exploitants = (Exploitant.objects.filter(visible=True)
                   .exclude(latitude=None, longitude=None)
                   .order_by("nom_ferme"))
    return render(request, "portal/home.html", {"exploitants": exploitants})


def producer_search(request):
    """Recherche multi-critères : exploitant, produit, ville, département, mode."""
    exploitants = Exploitant.objects.filter(visible=True).order_by("nom_ferme")
    q = request.GET.get("q", "").strip()
    dept = request.GET.get("dept", "").strip()
    mode = request.GET.get("mode", "").strip()
    if q:
        exploitants = exploitants.filter(
            Q(nom_ferme__icontains=q) | Q(ville__icontains=q)
            | Q(produits__nom__icontains=q)
            | Q(produits__categorie__nom__icontains=q)).distinct()
    if dept:
        exploitants = exploitants.filter(departement=dept)
    if mode:
        exploitants = exploitants.filter(mode_production=mode)
    return render(request, "portal/search_results.html", {
        "exploitants": exploitants,
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
    """Page publique d'un exploitant : catalogue + récolte de la semaine."""
    exploitant = get_object_or_404(Exploitant, slug=slug, visible=True)
    today = timezone.localdate()
    lundi = today - datetime.timedelta(days=today.weekday())
    semaine = (SemaineRecolte.objects.filter(exploitant=exploitant,
                                             publiee=True,
                                             lundi__lte=lundi)
               .order_by("-lundi").first())
    lignes = semaine.lignes.select_related("produit") if semaine else []
    return render(request, "portal/producer_detail.html", {
        "exploitant": exploitant,
        "semaine": semaine,
        "lignes": lignes,
        "points_livraison": exploitant.points_livraison.all(),
        "creneaux": exploitant.creneaux.select_related("point_livraison"),
    })


# ---------------------------------------------------------------- registres

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
    return user.is_authenticated and hasattr(user, "exploitant")


exploitant_requis = user_passes_test(est_exploitant, login_url="portal:login")


# ---------------------------------------------------------------- espace pro

@login_required
@exploitant_requis
def dashboard(request):
    exploitant = request.user.exploitant
    return render(request, "portal/pro/dashboard.html", {
        "exploitant": exploitant,
        "produits": exploitant.produits.filter(actif=True),
        "semaine": SemaineRecolte.objects.filter(exploitant=exploitant)
                   .order_by("-lundi").first(),
        "points": exploitant.points_livraison.all(),
        "creneaux": exploitant.creneaux.all(),
        "commandes_attente": exploitant.commandes
                             .filter(statut=Commande.Statut.NOUVELLE)
                             .order_by("-creee_le")[:10],
        "paniers_en_cours": exploitant.paniers
                            .exclude(statut=Panier.Statut.RECU).count(),
    })


@login_required
@exploitant_requis
def produit_creer(request):
    if request.method == "POST":
        form = ProduitForm(request.POST, request.FILES)
        if form.is_valid():
            produit = form.save(commit=False)
            produit.exploitant = request.user.exploitant
            produit.save()
            messages.success(request, f"Produit « {produit.nom} » ajouté.")
            return redirect("portal:dashboard")
    else:
        form = ProduitForm()
    return render(request, "portal/pro/product_form.html",
                  {"form": form, "titre": "Ajouter un produit"})


@login_required
@exploitant_requis
def produit_modifier(request, pk):
    produit = get_object_or_404(Produit, pk=pk,
                                exploitant=request.user.exploitant)
    if request.method == "POST":
        form = ProduitForm(request.POST, request.FILES, instance=produit)
        if form.is_valid():
            form.save()
            messages.success(request, "Produit mis à jour.")
            return redirect("portal:dashboard")
    else:
        form = ProduitForm(instance=produit)
    return render(request, "portal/pro/product_form.html",
                  {"form": form, "titre": "Modifier le produit"})


@login_required
@exploitant_requis
def harvest_manage(request, semaine_id=None):
    """Saisie des dispos hebdo (ESTIMATIONS) : quantité estimée + prix."""
    exploitant = request.user.exploitant
    today = timezone.localdate()
    lundi = today - datetime.timedelta(days=today.weekday())
    semaine = None
    if semaine_id:
        semaine = get_object_or_404(SemaineRecolte, pk=semaine_id,
                                   exploitant=exploitant)
    elif request.method == "GET":
        semaine = (SemaineRecolte.objects.filter(exploitant=exploitant)
                   .order_by("-lundi").first())
        if semaine:
            return redirect("portal:harvest_manage", semaine.pk)

    if request.method == "POST":
        if not semaine:
            lundi_saisi = request.POST.get("lundi") or lundi.isoformat()
            try:
                lundi_saisi = datetime.date.fromisoformat(lundi_saisi)
            except ValueError:
                lundi_saisi = lundi
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
        messages.success(request, "Récolte enregistrée.")
        return redirect("portal:dashboard")

    lignes = {l.produit_id: l for l in semaine.lignes.all()} if semaine else {}
    rows = [{
        "produit": p,
        "qty": lignes[p.pk].quantite_estimee if p.pk in lignes else None,
        "price": lignes[p.pk].prix_unitaire if p.pk in lignes else None,
    } for p in exploitant.produits.filter(actif=True)]
    return render(request, "portal/pro/harvest_form.html", {
        "semaine": semaine,
        "rows": rows,
        "lundi_defaut": (semaine.lundi if semaine else lundi),
    })


@login_required
@exploitant_requis
def order_list(request, statut=None):
    exploitant = request.user.exploitant
    commandes = exploitant.commandes.order_by("-creee_le")
    if statut:
        commandes = commandes.filter(statut=statut)
    return render(request, "portal/pro/orders.html",
                  {"commandes": commandes, "filtre_statut": statut})


@login_required
@exploitant_requis
def order_validate(request, commande_id):
    """Validation / refus.

    Valider crée le PANIER numéroté pré-rempli (copie des lignes de la
    commande) : l'exploitant ajustera ensuite le contenu EFFECTIVEMENT
    livré — seul décompte de production (règle DATA_MODEL v0.3).
    """
    exploitant = request.user.exploitant
    commande = get_object_or_404(Commande, pk=commande_id, exploitant=exploitant)
    if (request.method == "POST"
            and commande.statut == Commande.Statut.NOUVELLE):
        action = request.POST.get("action")
        if action == "validate":
            with transaction.atomic():
                commande.statut = Commande.Statut.VALIDEE
                commande.validee_le = timezone.now()
                commande.save()
                panier = Panier.objects.create(
                    exploitant=exploitant,
                    client=commande.client,
                    nom_client=commande.nom_client,
                    email_client=commande.email_client,
                    telephone_client=commande.telephone_client,
                    numero=Panier.prochain_numero(
                        exploitant, commande.date_livraison,
                        client=commande.client,
                        nom_client=commande.nom_client),
                    date_livraison=commande.date_livraison,
                    point_livraison=commande.point_livraison,
                    commande=commande,
                    statut=Panier.Statut.PREPARATION,
                    total=commande.total)
                for ligne in commande.lignes.select_related("produit"):
                    LignePanier.objects.create(
                        panier=panier, produit=ligne.produit,
                        quantite=ligne.quantite,
                        prix_unitaire=ligne.prix_unitaire)
            messages.success(
                request, f"Commande #{commande.pk} validée → "
                f"panier n°{panier.numero} créé pour "
                f"{panier.nom_client}.")
        elif action == "refuse":
            commande.statut = Commande.Statut.REFUSEE
            commande.save()
            messages.info(request, f"Commande #{commande.pk} refusée.")
    return redirect("portal:order_list")


@login_required
@exploitant_requis
def panier_list(request):
    """Liste des paniers, filtrable par jour de livraison."""
    exploitant = request.user.exploitant
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
def panier_detail(request, panier_id):
    """Préparation du panier : ajustement du contenu EFFECTIVEMENT livré
    (quantités, ajout/retrait de produits) et changement de statut.
    C'est la source du décompte de production et de l'export (issue #8)."""
    exploitant = request.user.exploitant
    panier = get_object_or_404(Panier, pk=panier_id, exploitant=exploitant)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "lignes":
            with transaction.atomic():
                total = Decimal("0")
                for ligne in panier.lignes.select_related("produit"):
                    brut = request.POST.get(f"qty_{ligne.pk}", "").strip()
                    if not brut:
                        ligne.delete()
                        continue
                    try:
                        qty = Decimal(brut)
                    except InvalidOperation:
                        continue
                    if qty <= 0:
                        ligne.delete()
                        continue
                    ligne.quantite = qty
                    ligne.save()
                    total += qty * ligne.prix_unitaire
                # Ajout d'un produit non commandé (prix du catalogue)
                pid = request.POST.get("produit_ajout", "").strip()
                qadd = request.POST.get("qty_ajout", "").strip()
                if pid and qadd:
                    produit = exploitant.produits.filter(
                        pk=pid, actif=True).first()
                    try:
                        qadd = Decimal(qadd)
                    except InvalidOperation:
                        qadd = None
                    if produit and qadd and qadd > 0:
                        prix = produit.prix or Decimal("0")
                        LignePanier.objects.create(
                            panier=panier, produit=produit,
                            quantite=qadd, prix_unitaire=prix)
                        total += qadd * prix
                panier.total = total
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

        return redirect("portal:panier_detail", panier.pk)

    return render(request, "portal/pro/panier_detail.html", {
        "panier": panier,
        "produits": exploitant.produits.filter(actif=True),
    })


# ---------------------------------------------------------------- client

@login_required
def order_create(request, slug):
    """Le client choisit produits/quantités/date et soumet sa commande.

    Les quantités affichées sont des estimations : aucune commande n'est
    bloquée par une quantité indicative.
    """
    exploitant = get_object_or_404(Exploitant, slug=slug, visible=True)
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
            lignes_souhaitees.append((ligne, qty))
            total += qty * ligne.prix_unitaire
        point = exploitant.points_livraison.filter(
            pk=request.POST.get("point_livraison")).first()
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
        nom_client = (request.user.get_full_name() or request.user.username)
        with transaction.atomic():
            commande = Commande.objects.create(
                exploitant=exploitant, client=request.user,
                nom_client=nom_client, email_client=request.user.email,
                point_livraison=point, date_livraison=date_livraison,
                note=request.POST.get("note", ""), total=total)
            for ligne, qty in lignes_souhaitees:
                LigneCommande.objects.create(
                    commande=commande, produit=ligne.produit,
                    quantite=qty, prix_unitaire=ligne.prix_unitaire)
        messages.success(
            request, "Commande envoyée ! Le producteur va la valider, "
            "vous la retrouverez dans « Mes commandes ».")
        return redirect("portal:my_orders")

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
    commandes = (request.user.commandes.select_related("exploitant")
                 .prefetch_related("lignes__produit").order_by("-creee_le"))
    return render(request, "portal/my_orders.html",
                  {"commandes": commandes})


@login_required
def order_cancel(request, commande_id):
    commande = get_object_or_404(Commande, pk=commande_id, client=request.user)
    if (request.method == "POST"
            and commande.statut == Commande.Statut.NOUVELLE):
        commande.statut = Commande.Statut.ANNULEE
        commande.save()
        messages.info(request, f"Commande #{commande.pk} annulée.")
    return redirect("portal:my_orders")
