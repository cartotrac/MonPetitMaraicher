from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Exploitant, Produit, ProfilClient


class InscriptionExploitantForm(UserCreationForm):
    """Inscription exploitant : compte utilisateur + profil exploitation."""

    nom_ferme = forms.CharField(label="Nom de l'exploitation", max_length=150)
    siret = forms.CharField(label="SIRET", max_length=14, required=False)
    mode_production = forms.ChoiceField(label="Mode de production", choices=[
        ("AB", "Agriculture Biologique (AB)"),
        ("PERMA", "Permaculture"),
        ("PAYSAN", "Agriculture paysanne"),
        ("RAISONNE", "Agriculture raisonnée"),
        ("CONV", "Conventionnelle"),
    ])
    logo = forms.ImageField(label="Logo miniature", required=False)
    description = forms.CharField(label="Présentation", widget=forms.Textarea,
                                  required=False)
    adresse = forms.CharField(label="Adresse", max_length=255, required=False)
    ville = forms.CharField(label="Ville", max_length=100, required=False)
    code_postal = forms.CharField(label="Code postal", max_length=10,
                                  required=False)
    departement = forms.CharField(label="Département (ex : 44)", max_length=3,
                                  required=False)
    telephone = forms.CharField(label="Téléphone", max_length=20, required=False)
    latitude = forms.FloatField(label="Latitude (optionnel, pour la carte)",
                                required=False)
    longitude = forms.FloatField(label="Longitude (optionnel, pour la carte)",
                                 required=False)

    class Meta:
        model = User
        fields = ("username", "email", "first_name")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
            Exploitant.objects.create(
                user=user,
                nom_ferme=self.cleaned_data["nom_ferme"],
                siret=self.cleaned_data.get("siret", ""),
                mode_production=self.cleaned_data["mode_production"],
                logo=self.cleaned_data.get("logo"),
                description=self.cleaned_data.get("description", ""),
                adresse=self.cleaned_data.get("adresse", ""),
                ville=self.cleaned_data.get("ville", ""),
                code_postal=self.cleaned_data.get("code_postal", ""),
                departement=self.cleaned_data.get("departement", ""),
                telephone=self.cleaned_data.get("telephone", ""),
                latitude=self.cleaned_data.get("latitude"),
                longitude=self.cleaned_data.get("longitude"))
        return user


class InscriptionClientForm(UserCreationForm):
    telephone = forms.CharField(label="Téléphone", max_length=20, required=False)

    class Meta:
        model = User
        fields = ("username", "email", "first_name")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        if commit:
            user.save()
            ProfilClient.objects.create(
                user=user,
                telephone=self.cleaned_data.get("telephone", ""))
        return user


class ProduitForm(forms.ModelForm):
    class Meta:
        model = Produit
        fields = ["nom", "categorie", "description", "illustration",
                  "unite_vente", "prix", "actif"]
        labels = {"nom": "Nom", "categorie": "Catégorie",
                  "description": "Description", "illustration": "Photo",
                  "unite_vente": "Unité de vente",
                  "prix": "Prix de référence (€)",
                  "actif": "Actif"}
