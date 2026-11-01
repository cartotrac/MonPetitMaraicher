from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Product


class ProducerRegisterForm(UserCreationForm):
    """Inscription maraîcher : compte utilisateur + profil exploitation."""

    farm_name = forms.CharField(label="Nom de l'exploitation", max_length=150)
    siret = forms.CharField(label="SIRET", max_length=14, required=False)
    certification = forms.ChoiceField(label="Mode de production", choices=[
        ("AB", "Agriculture Biologique (AB)"),
        ("PERMA", "Permaculture"),
        ("PAYSAN", "Agriculture paysanne"),
        ("RAISONNE", "Agriculture raisonnée"),
        ("CONV", "Conventionnelle"),
    ])
    logo = forms.ImageField(label="Logo miniature", required=False)
    description = forms.CharField(label="Présentation", widget=forms.Textarea,
                                  required=False)
    address = forms.CharField(label="Adresse", max_length=255, required=False)
    city = forms.CharField(label="Ville", max_length=100, required=False)
    zip_code = forms.CharField(label="Code postal", max_length=10, required=False)
    department = forms.CharField(label="Département (ex : 44)", max_length=3,
                                  required=False)
    phone = forms.CharField(label="Téléphone", max_length=20, required=False)
    latitude = forms.FloatField(label="Latitude (optionnel, pour la carte)",
                                required=False)
    longitude = forms.FloatField(label="Longitude (optionnel, pour la carte)",
                                 required=False)

    class Meta:
        model = User
        fields = ("username", "email", "first_name")

    def save(self, commit=True):
        from .models import Producer
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
            Producer.objects.create(
                user=user,
                farm_name=self.cleaned_data["farm_name"],
                siret=self.cleaned_data.get("siret", ""),
                certification=self.cleaned_data["certification"],
                logo=self.cleaned_data.get("logo"),
                description=self.cleaned_data.get("description", ""),
                address=self.cleaned_data.get("address", ""),
                city=self.cleaned_data.get("city", ""),
                zip_code=self.cleaned_data.get("zip_code", ""),
                department=self.cleaned_data.get("department", ""),
                phone=self.cleaned_data.get("phone", ""),
                latitude=self.cleaned_data.get("latitude"),
                longitude=self.cleaned_data.get("longitude"))
        return user


class ClientRegisterForm(UserCreationForm):
    phone = forms.CharField(label="Téléphone", max_length=20, required=False)

    class Meta:
        model = User
        fields = ("username", "email", "first_name")

    def save(self, commit=True):
        from .models import ClientProfile
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
            ClientProfile.objects.create(user=user,
                                         phone=self.cleaned_data.get("phone", ""))
        return user


class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = ["name", "category", "description", "image", "unit", "is_active"]
        labels = {"name": "Nom", "category": "Catégorie",
                  "description": "Description", "image": "Photo",
                  "unit": "Unité de vente", "is_active": "Actif"}
