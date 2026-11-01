from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("", views.home, name="home"),
    path("recherche/", views.producer_search, name="producer_search"),
    path("carte/exploitants.json", views.producteurs_geojson,
         name="producers_geojson"),
    path("exploitants/", views.home, name="producer_list"),
    path("exploitant/<slug:slug>/", views.producer_detail,
         name="producer_detail"),

    # Authentification / inscription
    path("inscription/exploitant/", views.register_exploitant,
         name="register_producer"),
    path("inscription/client/", views.register_client,
         name="register_client"),

    # Espace pro
    path("espace-pro/", views.dashboard, name="dashboard"),
    path("espace-produits/ajouter/", views.produit_creer,
         name="product_create"),
    path("espace-produits/<int:pk>/modifier/", views.produit_modifier,
         name="product_edit"),
    path("espace-recolte/", views.harvest_manage, name="harvest_manage"),
    path("espace-recolte/<int:semaine_id>/", views.harvest_manage,
         name="harvest_manage"),
    path("espace-commandes/", views.order_list, name="order_list"),
    path("espace-commandes/<str:statut>/", views.order_list,
         name="order_list_filtered"),
    path("espace-commandes/<int:commande_id>/decision/", views.order_validate,
         name="order_validate"),

    # Espace client
    path("commander/<slug:slug>/", views.order_create, name="order_create"),
    path("mes-commandes/", views.my_orders, name="my_orders"),
    path("mes-commandes/<int:commande_id>/annuler/", views.order_cancel,
         name="order_cancel"),
]
