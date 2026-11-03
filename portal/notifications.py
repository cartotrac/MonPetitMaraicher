"""Envois e-mail / SMS aux clients (issue #3) — zéro dépendance externe.

E-mail : SMTP configuré via variables d'environnement (EMAIL_HOST, etc.).
Sans EMAIL_HOST, Django journalise au lieu d'envoyer et l'interface
informe l'exploitant.

SMS : passerelle HTTP Free Mobile (notificationsAPI, identifiants dans
l'admin Django → Configuration messagerie). Les autres passerelles
(OVH, Twilio, HTTP perso) resteront à brancher en V2.

Modèles personnalisables par l'exploitant (ModeleMessage), avec défauts
embarqués et repli propre si le modèle personnalisé est cassé.
"""
import urllib.parse
import urllib.request

from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail

from .models import ConfigMessagerie, ModeleMessage, PreferenceContact

EMAILS_PAR_DEFAUT = {
    "CONFIRMATION_COMMANDE": {
        "objet": "Commande confirmée — {ferme}",
        "corps": ("Bonjour {client},\n\n"
                  "Votre commande est confirmée ! Elle sera préparée en "
                  "panier n°{numero} pour le {date}.\n\n"
                  "Total : {total} €\n\n"
                  "Merci de votre confiance,\n"
                  "{ferme}"),
    },
    "PANIER_PRET": {
        "objet": "Votre panier est prêt — {ferme}",
        "corps": ("Bonjour {client},\n\n"
                  "Votre panier n°{numero} est prêt ! Vous pouvez venir le "
                  "récupérer le {date}.\n\n"
                  "Total : {total} €\n\n"
                  "À bientôt,\n"
                  "{ferme}"),
    },
    "LIVRAISON_FAITE": {
        "objet": "Votre panier a été livré — {ferme}",
        "corps": ("Bonjour {client},\n\n"
                  "Votre panier n°{numero} du {date} a bien été livré. "
                  "Merci de votre confiance !\n\n"
                  "{ferme}"),
    },
}

SMS_PAR_DEFAUT = {
    "CONFIRMATION_COMMANDE": "Commande confirmee : panier n°{numero} pour le {date} — {ferme}",
    "PANIER_PRET": "Panier n°{numero} pret a recuperer le {date} — {ferme}",
    "LIVRAISON_FAITE": "Panier n°{numero} livre le {date} — merci ! {ferme}",
}


def _contexte(panier):
    return {
        "client": panier.nom_client,
        "ferme": panier.exploitant.nom_ferme,
        "numero": panier.numero,
        "date": panier.date_livraison.strftime("%d/%m/%Y"),
        "total": str(panier.total).replace(".", ","),
        "creneau": str(panier.creneau) if panier.creneau else "",
        "point": panier.point_livraison.nom if panier.point_livraison else "",
    }


def _modele(exploitant, type_msg, canal):
    """Modèle personnalisé actif s'il existe, sinon défaut embarqué."""
    perso = (ModeleMessage.objects
             .filter(exploitant=exploitant, type=type_msg, canal=canal,
                     actif=True).first())
    if canal == "SMS":
        defaut = SMS_PAR_DEFAUT.get(type_msg)
    else:
        defaut = EMAILS_PAR_DEFAUT.get(type_msg)
    if perso:
        return perso.objet or (defaut["objet"] if defaut else type_msg), perso.corps
    if defaut is None:
        return type_msg, ""
    return (defaut.get("objet", ""), defaut.get("corps", ""))


def envoyer_sms(exploitant, texte):
    """Envoi via la passerelle configurée par l'exploitant.
    Retourne (succes, message)."""
    cfg = ConfigMessagerie.objects.filter(exploitant=exploitant).first()
    if not cfg or not cfg.passerelle_sms or not cfg.config_sms:
        return False, ("non configuré (admin Django → Configuration "
                       "messagerie)")
    if cfg.passerelle_sms == ConfigMessagerie.PasserelleSMS.FREE:
        identifiant = str(cfg.config_sms.get("user", "")).strip()
        cle = str(cfg.config_sms.get("pass", "")).strip()
        if not identifiant or not cle:
            return False, "identifiants Free Mobile manquants"
        url = ("https://smsapi.free-mobile.fr/sendmsg?"
               + urllib.parse.urlencode(
                   {"user": identifiant, "pass": cle,
                    "msg": texte[:480]}))
        try:
            with urllib.request.urlopen(url, timeout=10) as reponse:
                if reponse.status == 200:
                    return True, "envoyé"
                return False, f"code HTTP {reponse.status}"
        except Exception as err:  # URLError, HTTPError, timeout
            return False, f"échec : {err}"
    return False, (f"passerelle {cfg.get_passerelle_sms_display()} "
                  "non implémentée en V1")


def notifier_client(request, panier, type_msg):
    """Notifie le client du panier selon son canal préféré (e-mail par
    défaut). Feedback via messages Django. Retourne True si envoyé."""
    pref = None
    if panier.client_id:
        pref = (PreferenceContact.objects
                .filter(exploitant=panier.exploitant, client=panier.client)
                .first())
    canal = pref.canal if pref else PreferenceContact.Canal.EMAIL
    objet_modele, corps_modele = _modele(panier.exploitant, type_msg, canal)
    ctx = _contexte(panier)
    try:
        objet = objet_modele.format(**ctx)
        corps = corps_modele.format(**ctx)
    except (KeyError, IndexError, ValueError):
        objet, corps = type_msg, ("(Modèle de message personnalisé "
                                  "invalide — corrigez-le dans l'admin.)")

    if canal == PreferenceContact.Canal.SMS:
        if not panier.telephone_client:
            messages.info(request, "Canal préféré SMS mais numéro absent : "
                          "aucun envoi effectué.")
            return False
        ok, info = envoyer_sms(panier.exploitant, corps)
        if ok:
            messages.success(request, "📱 SMS " + info + ".")
        else:
            messages.info(request, "SMS non envoyé : " + info + ".")
        return ok

    # Canal e-mail
    if not panier.email_client:
        messages.info(request, "E-mail du client absent : aucun envoi "
                      "effectué.")
        return False
    if not getattr(settings, "EMAIL_HOST", ""):
        messages.info(request, "E-mail non configuré : ajoutez EMAIL_HOST "
                      "(et identifiants) dans le .env puis redémarrez le "
                      "site. Rien n'a été envoyé.")
        return False
    try:
        send_mail(objet, corps, settings.DEFAULT_FROM_EMAIL,
                  [panier.email_client], fail_silently=False)
    except Exception as err:
        messages.info(request, f"Échec d'envoi e-mail : {err}")
        return False
    messages.success(request, "✉️ E-mail envoyé à " + panier.email_client + ".")
    return True
