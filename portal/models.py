from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse


def producer_logo_path(instance, filename):
    return f"logos/{instance.user.pk}/{filename}"


def product_image_path(instance, filename):
    return f"produits/{instance.producer.pk}/{filename}"


class Producer(models.Model):
    """Profil maraîcher : un compte utilisateur = une exploitation."""

    class Certification(models.TextChoices):
        AB = "AB", "Agriculture Biologique (AB)"
        PERMA = "PERMA", "Permaculture"
        PAYSAN = "PAYSAN", "Agriculture paysanne"
        RAISONNE = "RAISONNE", "Agriculture raisonnée"
        CONV = "CONV", "Conventionnelle"

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="producer")
    farm_name = models.CharField("Nom de l'exploitation", max_length=150)
    slug = models.SlugField("Adresse publique", max_length=160, unique=True, blank=True)
    siret = models.CharField("SIRET", max_length=14, blank=True)
    certification = models.CharField(
        "Mode de production", max_length=10,
        choices=Certification.choices, default=Certification.CONV
    )
    logo = models.ImageField("Logo miniature", upload_to=producer_logo_path, blank=True, null=True)
    description = models.TextField("Présentation de l'exploitation", blank=True)
    address = models.CharField("Adresse", max_length=255, blank=True)
    city = models.CharField("Ville", max_length=100, blank=True)
    zip_code = models.CharField("Code postal", max_length=10, blank=True)
    department = models.CharField("Département", max_length=3, db_index=True, blank=True)
    phone = models.CharField("Téléphone", max_length=20, blank=True)
    latitude = models.FloatField("Latitude", blank=True, null=True,
                                 help_text="Position sur la carte (optionnel en V1)")
    longitude = models.FloatField("Longitude", blank=True, null=True,
                                  help_text="Position sur la carte (optionnel en V1)")
    is_visible = models.BooleanField("Visible publiquement", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Maraîcher"
        verbose_name_plural = "Maraîchers"

    def __str__(self):
        return self.farm_name

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            base = slugify(self.farm_name) or "maraicher"
            slug = base
            n = 2
            while Producer.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("portal:producer_detail", kwargs={"slug": self.slug})


class ClientProfile(models.Model):
    """Profil client (optionnel, pour faciliter les commandes récurrentes)."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="client_profile")
    phone = models.CharField("Téléphone", max_length=20, blank=True)
    address = models.CharField("Adresse", max_length=255, blank=True)
    city = models.CharField("Ville", max_length=100, blank=True)
    zip_code = models.CharField("Code postal", max_length=10, blank=True)

    def __str__(self):
        return f"Client : {self.user.get_full_name() or self.user.username}"


class Product(models.Model):
    """Produit référencé par un maraîcher (catalogue).

    NB V2 prévue : catégories personnalisables par producteur et attributs
    libres (JSON) ; en V1 la catégorie est un champ texte simple.
    """

    class Unit(models.TextChoices):
        KG = "KG", "le kg"
        PIECE = "PC", "la pièce"
        BOTTE = "BO", "la botte"
        BARQUETTE = "BQ", "la barquette"

    producer = models.ForeignKey(Producer, on_delete=models.CASCADE, related_name="products")
    name = models.CharField("Nom", max_length=150)
    category = models.CharField("Catégorie", max_length=80, blank=True,
                                help_text="Ex : légumes, fruits, herbes, œufs…")
    description = models.TextField("Description", blank=True)
    image = models.ImageField("Photo", upload_to=product_image_path, blank=True, null=True)
    unit = models.CharField("Unité de vente", max_length=2, choices=Unit.choices, default=Unit.KG)
    is_active = models.BooleanField("Actif", default=True)

    class Meta:
        verbose_name = "Produit"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.producer.farm_name})"


class HarvestWeek(models.Model):
    """Récolte d'une semaine donnée pour un maraîcher."""

    producer = models.ForeignKey(Producer, on_delete=models.CASCADE, related_name="harvest_weeks")
    week_start = models.DateField("Lundi de la semaine", db_index=True)
    note = models.CharField("Note / actualité de la semaine", max_length=255, blank=True,
                            help_text="Ex : « premières tomates de la saison ! »")
    is_published = models.BooleanField("Publiée aux clients", default=True)

    class Meta:
        verbose_name = "Récolte hebdomadaire"
        verbose_name_plural = "Récoltes hebdomadaires"
        unique_together = ("producer", "week_start")
        ordering = ["-week_start"]

    def __str__(self):
        return f"Récolte du {self.week_start} — {self.producer.farm_name}"


class HarvestItem(models.Model):
    """Ligne de récolte : estimation indicative de quantité + prix.

    ⚠️ Les quantités saisies sont des ESTIMATIONS, pas un stock :
    elles informent le client mais ne bloquent ni ne décomptent aucune
    commande. Seules les quantités livrées dans les paniers (V2) comptent.
    """

    harvest = models.ForeignKey(HarvestWeek, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="harvest_items")
    quantity_estimate = models.DecimalField("Quantité estimée", max_digits=8, decimal_places=2)
    unit_price = models.DecimalField("Prix unitaire (€)", max_digits=6, decimal_places=2)

    class Meta:
        verbose_name = "Ligne de récolte (estimation)"
        unique_together = ("harvest", "product")

    def __str__(self):
        return f"{self.product.name} ~{self.quantity_estimate} @ {self.unit_price}€"


class DeliveryPoint(models.Model):
    """Point de livraison ou de mise à disposition des paniers."""

    producer = models.ForeignKey(Producer, on_delete=models.CASCADE, related_name="delivery_points")
    name = models.CharField("Nom", max_length=150, help_text="Ex : Marché de X, AMAP Y, Ferme")
    address = models.CharField("Adresse", max_length=255)
    city = models.CharField("Ville", max_length=100)
    zip_code = models.CharField("Code postal", max_length=10)
    note = models.TextField("Précisions", blank=True)

    class Meta:
        verbose_name = "Point de livraison"
        ordering = ["city", "name"]

    def __str__(self):
        return f"{self.name} ({self.city})"


class DeliverySlot(models.Model):
    """Créneau récurrent : jour, horaires, fréquence, capacité."""

    class Frequency(models.TextChoices):
        WEEKLY = "W", "Chaque semaine"
        BIWEEKLY = "B", "Une semaine sur deux"
        MONTHLY = "M", "Une fois par mois"

    producer = models.ForeignKey(Producer, on_delete=models.CASCADE, related_name="delivery_slots")
    delivery_point = models.ForeignKey(DeliveryPoint, on_delete=models.CASCADE,
                                       related_name="slots", blank=True, null=True)
    day_of_week = models.PositiveSmallIntegerField(
        "Jour",
        choices=[(1, "Lundi"), (2, "Mardi"), (3, "Mercredi"), (4, "Jeudi"),
                 (5, "Vendredi"), (6, "Samedi"), (7, "Dimanche")],
    )
    start_time = models.TimeField("Début")
    end_time = models.TimeField("Fin")
    frequency = models.CharField("Fréquence", max_length=1,
                                 choices=Frequency.choices, default=Frequency.WEEKLY)
    capacity = models.PositiveSmallIntegerField("Capacité (paniers/commandes)", default=10)

    class Meta:
        verbose_name = "Créneau"
        ordering = ["day_of_week", "start_time"]

    def __str__(self):
        return (f"{self.get_day_of_week_display()} {self.start_time}–{self.end_time} "
                f"({self.get_frequency_display()})")


class Order(models.Model):
    """Commande client, à valider par le maraîcher.

    NB V2 prévue : paniers numérotés (Basket n°1..X par client et par jour de
    livraison) ; seul le contenu livré des paniers est décompté et exportable
    en compta.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "À valider"
        VALIDATED = "VALIDATED", "Validée"
        REFUSED = "REFUSED", "Refusée"
        CANCELLED = "CANCELLED", "Annulée (client)"
        DONE = "DONE", "Livrée"

    producer = models.ForeignKey(Producer, on_delete=models.CASCADE, related_name="orders")
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name="orders")
    delivery_point = models.ForeignKey(DeliveryPoint, on_delete=models.SET_NULL,
                                       null=True, blank=True, related_name="orders")
    delivery_date = models.DateField("Date de livraison souhaitée")
    status = models.CharField("Statut", max_length=10, choices=Status.choices,
                              default=Status.PENDING, db_index=True)
    total = models.DecimalField("Total (€)", max_digits=8, decimal_places=2, default=0)
    note = models.TextField("Message du client", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    validated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Commande"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Commande #{self.pk} — {self.client} → {self.producer.farm_name}"


class OrderItem(models.Model):
    """Ligne de commande (prix et quantité figés à la commande)."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField("Quantité", max_digits=8, decimal_places=2)
    unit_price = models.DecimalField("Prix unitaire (€)", max_digits=6, decimal_places=2)

    def line_total(self):
        return self.quantity * self.unit_price
