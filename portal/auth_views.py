"""Vues d'authentification sur mesure (connexion par nom
d'utilisateur OU e-mail). Le reste du flux (déconnexion, réinitialisation
de mot de passe) reste fourni par django.contrib.auth.urls."""

from django.contrib.auth import views as auth_views

from .forms import ConnexionForm


def connexion(request):
    return auth_views.LoginView.as_view(
        template_name="registration/login.html",
        form_class=ConnexionForm,
        redirect_authenticated_user=True)(request)
