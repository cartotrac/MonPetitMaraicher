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

from .forms import ClientRegisterForm, ProductForm, ProducerRegisterForm
from .models import (HarvestItem, HarvestWeek, Order, OrderItem, Producer,
                     Product)


def home(request):
    """Landing : bandeau, recherche, hero, carte des producteurs."""
    producers = (Producer.objects.filter(is_visible=True)
                 .exclude(latitude=None, longitude=None)
                 .order_by("farm_name"))
    return render(request, "portal/home.html", {"producers": producers})


def producer_search(request):
    """Recherche multi-critères : producteur, produit, ville, département, catégorie."""
    producers = Producer.objects.filter(is_visible=True).order_by("farm_name")
    q = request.GET.get("q", "").strip()
    dept = request.GET.get("dept", "").strip()
    cert = request.GET.get("cert", "").strip()
    if q:
        producers = producers.filter(
            Q(farm_name__icontains=q) | Q(city__icontains=q)
            | Q(products__name__icontains=q)
            | Q(products__category__icontains=q)).distinct()
    if dept:
        producers = producers.filter(department=dept)
    if cert:
        producers = producers.filter(certification=cert)
    return render(request, "portal/search_results.html", {
        "producers": producers,
        "q": q, "dept": dept, "cert": cert,
    })


def producers_geojson(request):
    """Données carte : producteurs visibles avec coordonnées."""
    producers = (Producer.objects.filter(is_visible=True)
                 .exclude(latitude=None, longitude=None))
    data = [{
        "slug": p.slug,
        "farm_name": p.farm_name,
        "certification": p.certification,
        "city": p.city,
        "latitude": p.latitude,
        "longitude": p.longitude,
        "url": p.get_absolute_url(),
    } for p in producers]
    return JsonResponse(list(data), encoder=DjangoJSONEncoder, safe=False)


def producer_detail(request, slug):
    """Page publique d'un maraîcher : catalogue + récolte de la semaine."""
    producer = get_object_or_404(Producer, slug=slug, is_visible=True)
    today = timezone.localdate()
    monday = today - datetime.timedelta(days=today.weekday())
    harvest = (HarvestWeek.objects.filter(producer=producer, is_published=True,
                                          week_start__lte=monday)
               .order_by("-week_start").first())
    harvest_items = harvest.items.select_related("product") if harvest else []
    return render(request, "portal/producer_detail.html", {
        "producer": producer,
        "harvest": harvest,
        "harvest_items": harvest_items,
        "delivery_points": producer.delivery_points.all(),
        "delivery_slots": producer.delivery_slots.select_related("delivery_point"),
    })


# ---------------------------------------------------------------- registres

def register_producer(request):
    if request.method == "POST":
        form = ProducerRegisterForm(request.POST, request.FILES)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(
                request, "Bienvenue ! Votre espace maraîcher est prêt : "
                "commencez par ajouter vos produits.")
            return redirect("portal:dashboard")
    else:
        form = ProducerRegisterForm()
    return render(request, "portal/registration/register_producer.html", {"form": form})


def register_client(request):
    if request.method == "POST":
        form = ClientRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Compte client créé. À vous de commander !")
            return redirect("portal:home")
    else:
        form = ClientRegisterForm()
    return render(request, "portal/registration/register_client.html", {"form": form})


def is_producer(user):
    return user.is_authenticated and hasattr(user, "producer")


producer_required = user_passes_test(is_producer, login_url="portal:login")


# ---------------------------------------------------------------- espace pro

@login_required
@producer_required
def dashboard(request):
    producer = request.user.producer
    return render(request, "portal/pro/dashboard.html", {
        "producer": producer,
        "products": producer.products.filter(is_active=True),
        "harvest": HarvestWeek.objects.filter(producer=producer)
                     .order_by("-week_start").first(),
        "points": producer.delivery_points.all(),
        "slots": producer.delivery_slots.all(),
        "pending_orders": producer.orders.filter(status=Order.Status.PENDING)
                          .order_by("-created_at")[:10],
    })


@login_required
@producer_required
def product_create(request):
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES)
        if form.is_valid():
            product = form.save(commit=False)
            product.producer = request.user.producer
            product.save()
            messages.success(request, f"Produit « {product.name} » ajouté.")
            return redirect("portal:dashboard")
    else:
        form = ProductForm()
    return render(request, "portal/pro/product_form.html",
                  {"form": form, "title": "Ajouter un produit"})


@login_required
@producer_required
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk, producer=request.user.producer)
    if request.method == "POST":
        form = ProductForm(request.POST, request.FILES, instance=product)
        if form.is_valid():
            form.save()
            messages.success(request, "Produit mis à jour.")
            return redirect("portal:dashboard")
    else:
        form = ProductForm(instance=product)
    return render(request, "portal/pro/product_form.html",
                  {"form": form, "title": "Modifier le produit"})


@login_required
@producer_required
def harvest_manage(request, harvest_id=None):
    """Saisie des dispos hebdo (ESTIMATIONS) : quantité estimée + prix."""
    producer = request.user.producer
    today = timezone.localdate()
    monday = today - datetime.timedelta(days=today.weekday())
    harvest = None
    if harvest_id:
        harvest = get_object_or_404(HarvestWeek, pk=harvest_id, producer=producer)
    elif request.method == "GET":
        harvest = (HarvestWeek.objects.filter(producer=producer)
                   .order_by("-week_start").first())
        if harvest:
            return redirect("portal:harvest_manage", harvest.pk)

    if request.method == "POST":
        if not harvest:
            week_start = request.POST.get("week_start") or monday.isoformat()
            try:
                week_start = datetime.date.fromisoformat(week_start)
            except ValueError:
                week_start = monday
            harvest, _created = HarvestWeek.objects.get_or_create(
                producer=producer,
                week_start=week_start,
                defaults={"note": request.POST.get("note", "")})
        harvest.note = request.POST.get("note", "")
        harvest.is_published = bool(request.POST.get("is_published"))
        harvest.save()
        for product in producer.products.filter(is_active=True):
            qty = request.POST.get(f"qty_{product.pk}", "").strip()
            price = request.POST.get(f"price_{product.pk}", "").strip()
            if not qty or not price:
                continue
            try:
                qty, price = Decimal(qty), Decimal(price)
            except InvalidOperation:
                continue
            HarvestItem.objects.update_or_create(
                harvest=harvest, product=product,
                defaults={"quantity_estimate": qty, "unit_price": price})
        for item in harvest.items.all():
            if f"qty_{item.product_id}" not in request.POST:
                item.delete()
        messages.success(request, "Récolte enregistrée.")
        return redirect("portal:dashboard")

    items = {i.product_id: i for i in harvest.items.all()} if harvest else {}
    rows = [{
        "product": p,
        "qty": items[p.pk].quantity_estimate if p.pk in items else None,
        "price": items[p.pk].unit_price if p.pk in items else None,
    } for p in producer.products.filter(is_active=True)]
    return render(request, "portal/pro/harvest_form.html", {
        "harvest": harvest,
        "rows": rows,
        "default_monday": (harvest.week_start if harvest else monday),
    })


@login_required
@producer_required
def order_list(request, status=None):
    producer = request.user.producer
    orders = producer.orders.select_related("client").order_by("-created_at")
    if status:
        orders = orders.filter(status=status)
    return render(request, "portal/pro/orders.html",
                  {"orders": orders, "status_filter": status})


@login_required
@producer_required
def order_validate(request, order_id):
    """Validation / refus — les quantités restent des estimations, rien
    n'est décompté ici ; seul le contenu livré des paniers comptera (V2)."""
    producer = request.user.producer
    order = get_object_or_404(Order, pk=order_id, producer=producer)
    if request.method == "POST" and order.status == Order.Status.PENDING:
        action = request.POST.get("action")
        if action == "validate":
            order.status = Order.Status.VALIDATED
            order.validated_at = timezone.now()
            order.save()
            messages.success(request, f"Commande #{order.pk} validée.")
        elif action == "refuse":
            order.status = Order.Status.REFUSED
            order.save()
            messages.info(request, f"Commande #{order.pk} refusée.")
    return redirect("portal:order_list")


# ---------------------------------------------------------------- client

@login_required
def order_create(request, slug):
    """Le client choisit produits/quantités/date et soumet sa commande.

    Les quantités affichées sont des estimations : aucune commande n'est
    bloquée par une quantité indicative.
    """
    producer = get_object_or_404(Producer, slug=slug, is_visible=True)
    today = timezone.localdate()
    monday = today - datetime.timedelta(days=today.weekday())
    harvest = (HarvestWeek.objects.filter(producer=producer, is_published=True,
                                          week_start__lte=monday)
               .order_by("-week_start").first())
    if not harvest:
        messages.info(request, "Ce maraîcher n'a pas encore publié de récolte.")
        return redirect("portal:producer_detail", slug=slug)
    items = harvest.items.select_related("product")

    if request.method == "POST":
        order_items, total = [], Decimal("0")
        for item in items:
            raw = request.POST.get(f"qty_{item.pk}", "").strip()
            if not raw:
                continue
            try:
                qty = Decimal(raw)
            except InvalidOperation:
                continue
            if qty <= 0:
                continue
            order_items.append((item, qty))
            total += qty * item.unit_price
        point = producer.delivery_points.filter(
            pk=request.POST.get("delivery_point")).first()
        try:
            delivery_date = datetime.date.fromisoformat(request.POST["delivery_date"])
        except (KeyError, ValueError):
            delivery_date = None
        if not order_items or delivery_date is None or delivery_date < today:
            messages.error(request,
                           "Commande invalide : vérifiez les quantités et la date.")
            return redirect("portal:order_create", slug=slug)
        with transaction.atomic():
            order = Order.objects.create(
                producer=producer, client=request.user,
                delivery_point=point, delivery_date=delivery_date,
                note=request.POST.get("note", ""), total=total)
            for item, qty in order_items:
                OrderItem.objects.create(
                    order=order, product=item.product,
                    quantity=qty, unit_price=item.unit_price)
        messages.success(
            request, "Commande envoyée ! Le maraîcher va la valider, "
            "vous la retrouverez dans « Mes commandes ».")
        return redirect("portal:my_orders")

    # Dates futures correspondant aux jours de créneaux (28 jours)
    slot_days = {s.day_of_week for s in producer.delivery_slots.all()}
    dates = []
    for i in range(0, 29):
        d = today + datetime.timedelta(days=i)
        if d.isoweekday() in slot_days or not slot_days:
            dates.append(d)
    return render(request, "portal/order_create.html", {
        "producer": producer,
        "harvest": harvest,
        "items": items,
        "delivery_points": producer.delivery_points.all(),
        "dates": dates,
    })


@login_required
def my_orders(request):
    orders = (request.user.orders.select_related("producer")
              .prefetch_related("items__product").order_by("-created_at"))
    return render(request, "portal/my_orders.html", {"orders": orders})


@login_required
def order_cancel(request, order_id):
    order = get_object_or_404(Order, pk=order_id, client=request.user)
    if request.method == "POST" and order.status == Order.Status.PENDING:
        order.status = Order.Status.CANCELLED
        order.save()
        messages.info(request, f"Commande #{order.pk} annulée.")
    return redirect("portal:my_orders")
