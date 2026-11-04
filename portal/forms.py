from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import (Annonce, Bulletin, Categorie, Exploitant, Produit,
                    ProfilClient, SemaineRecolte)


class InscriptionExploitantForm(UserCreationForm):
    """Inscription exploitant simplifiée : compte + ferme minimale.
    Nom de la ferme, activité et localisation à la création ; tout le
    reste (SIRET, mode de production, logo, description, téléphone,
    réseaux…) se complète ensuite dans la page ⚙️ Paramètres."""

    nom_ferme = forms.CharField(label="Nom de l'exploitation",
                                max_length=150)
    activite = forms.ChoiceField(
        label="Activité", choices=Exploitant.Activite.choices,
        initial=Exploitant.Activite.MARAICHER)
    ville = forms.CharField(label="Ville", max_length=100, required=False)
    code_postal = forms.CharField(label="Code postal", max_length=10,
                                  required=False)
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
            code_postal = self.cleaned_data.get("code_postal", "") or ""
            Exploitant.objects.create(
                user=user,
                nom_ferme=self.cleaned_data["nom_ferme"],
                activite=self.cleaned_data.get(
                    "activite", Exploitant.Activite.MARAICHER),
                ville=self.cleaned_data.get("ville", ""),
                code_postal=code_postal,
                departement=code_postal[:2] if len(code_postal) >= 2 else "",
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
    image_externe = forms.URLField(
        label="Lien photo externe (drive, cloud, réseau — rien n'est "
              "hébergé sur le portail)", required=False)

    class Meta:
        model = Produit
        fields = ["nom", "categorie", "description", "illustration",
                  "unite_vente", "prix", "actif"]
        labels = {"nom": "Nom", "categorie": "Catégorie",
                  "description": "Description", "illustration": "Photo",
                  "unite_vente": "Unité de vente",
                  "prix": "Prix de référence (€)",
                  "actif": "Actif"}

    def __init__(self, *args, exploitant=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Les catégories sont propres à chaque exploitant (issue #5).
        if exploitant is not None:
            self.fields["categorie"].queryset = Categorie.objects.filter(
                exploitant=exploitant)
        else:
            self.fields["categorie"].queryset = Categorie.objects.none()
        if self.instance and self.instance.pk:
            self.fields["image_externe"].initial = (
                self.instance.attributs or {}).get("image_url", "")


class ProfilExploitantForm(forms.ModelForm):
    """Édition de sa fiche par un maraîcher (badge SIRET inclus)."""
    logo_externe = forms.URLField(
        label="Lien logo externe (drive, cloud, réseau — alternative au "
              "fichier : rien n'est hébergé sur le portail)", required=False)
    site_web = forms.URLField(
        label="Site web de l'exploitation", required=False)
    facebook = forms.URLField(label="Page Facebook", required=False)
    instagram = forms.URLField(label="Compte Instagram", required=False)
    field_order = ["nom_ferme", "activite", "siret", "mode_production",
                   "logo", "logo_externe", "description", "adresse", "ville",
                   "code_postal", "departement", "telephone", "latitude",
                   "longitude", "est_demo", "mode_fonctionnement"]

    class Meta:
        model = Exploitant
        fields = ["nom_ferme", "activite", "siret", "mode_production",
                  "logo", "description", "adresse", "ville", "code_postal",
                  "departement", "telephone", "latitude", "longitude",
                  "est_demo", "mode_fonctionnement"]
        labels = {"nom_ferme": "Nom de l'exploitation",
                  "activite": "Activité",
                  "siret": "SIRET (14 chiffres)",
                  "mode_production": "Mode de production",
                  "logo": "Logo miniature (fichier)",
                  "description": "Présentation",
                  "departement": "Département (auto si vide : 2 premiers chiffres du code postal)",
                  "latitude": "Latitude (optionnel, pour la carte)",
                  "longitude": "Longitude (optionnel, pour la carte)",
                  "est_demo": "Exploitation de démonstration",
                  "mode_fonctionnement": "Mode de fonctionnement"}
        help_texts = {"est_demo": (
            "Cochez pour marquer cette exploitation comme fictive "
            "(test, formation, démo) : un badge 🧪 DÉMO la distingue "
            "sur le portail.")}


class ProfilPersonnelForm(forms.Form):
    """Informations personnelles du compte individuel (client, maraîcher
    propriétaire ou membre d'une équipe) : prénom, nom, e-mail, téléphone,
    photo (lien externe)."""

    prenom = forms.CharField(label="Prénom", max_length=150, required=False)
    nom = forms.CharField(label="Nom", max_length=150, required=False)
    email = forms.EmailField(label="E-mail")
    telephone = forms.CharField(label="Téléphone", max_length=20,
                                required=False)
    photo_externe = forms.URLField(
        label="Photo de profil externe (drive, cloud, réseau — rien "
              "n'est hébergé sur le portail)", required=False)


class BulletinForm(forms.ModelForm):
    """Newsletter / bulletin diffusé aux clients d'une exploitation."""

    class Meta:
        model = Bulletin
        fields = ["semaine", "objet", "corps"]
        labels = {"semaine": "Récolte liée (optionnel)",
                  "objet": "Objet du message",
                  "corps": "Message"}

    def __init__(self, *args, exploitant=None, **kwargs):
        super().__init__(*args, **kwargs)
        if exploitant is not None:
            self.fields["semaine"].queryset = SemaineRecolte.objects.filter(
                exploitant=exploitant).order_by("-lundi")
        else:
            self.fields["semaine"].queryset = (
                SemaineRecolte.objects.none())


class AnnonceForm(forms.ModelForm):
    """Annonce ponctuelle (« paniers disponibles », …)."""

    class Meta:
        model = Annonce
        fields = ["objet", "corps"]
        labels = {"objet": "Objet de l'annonce", "corps": "Annonce"}


class MessagerieForm(forms.Form):
    """Serveur d'envoi d'e-mails et passerelle SMS de l'exploitation
    (page Paramètres, propriétaire). Le SMTP propre à l'exploitation
    est utilisé pour la diffusion des publications ; la passerelle SMS
    servira aux envois de disponibilité hebdo des produits. Tout champ
    laissé vide retire le paramètre correspondant."""

    email_host = forms.CharField(
        label="Serveur SMTP (ex : smtp.alwaysdata.com)", required=False)
    email_port = forms.IntegerField(
        label="Port SMTP (25 par défaut)", required=False,
        min_value=1, max_value=65535)
    email_user = forms.CharField(label="Utilisateur SMTP", required=False)
    email_password = forms.CharField(
        label="Mot de passe SMTP", required=False,
        widget=forms.PasswordInput(render_value=True))
    email_tls = forms.BooleanField(
        label="Connexion chiffrée (STARTTLS)", required=False)
    email_from = forms.EmailField(
        label="Adresse d'expédition (« From »)", required=False)
    sms_url = forms.URLField(
        label="Passerelle SMS — URL de l'API (ex : https://api…/messages)",
        required=False)
    sms_cle = forms.CharField(
        label="Passerelle SMS — clé / jeton d'API", required=False,
        widget=forms.PasswordInput(render_value=True))
    sms_expediteur = forms.CharField(
        label="Passerelle SMS — nom d'expéditeur (11 caractères max)",
        required=False, max_length=11)
    sms_dispo_hebdo = forms.BooleanField(
        label="Envoyer chaque semaine la disponibilité des produits par SMS",
        required=False)
