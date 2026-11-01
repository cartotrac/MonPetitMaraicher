from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("", views.home, name="home"),
    path("recherche/", views.producer_search, name="producer_search"),
    path("carte/producteurs.json", views.producers_geojson, name="producers_geojson"),
    path("maraichers/", views.home, name="producer_list"),
    path("maraicher/<slug:slug>/", views.producer_detail, name="producer_detail"),

    # Authentification / inscription
    path("inscription/maraicher/", views.register_producer, name="register_producer"),
    path("inscription/client/", views.register_client, name="register_client"),

    # Espace pro
    path("espace-pro/", views.dashboard, name="dashboard"),
    path("espace-produits/ajouter/", views.product_create, name="product_create"),
    path("espace-produits/<int:pk>/modifier/", views.product_edit, name="product_edit"),
    path("espace-recolte/", views.harvest_manage, name="harvest_manage"),
    path("espace-recolte/<int:harvest_id>/", views.harvest_manage",
         name="harvest_manage"),
    path("espace-commandes/", views.order_list, name="order_list"),
    path("espace-commandes/<str:status>/", views.order_list, name="order_list_filtered"),
    path("espace-commandes/<int:order_id>/decision/", views.order_validate,
         name="order_validate"),

    # Espace client
    path("commander/<slug:slug>/", views.order_create, name="order_create"),
    path("mes-commandes/", views.my_orders, name="my_orders"),
    path("mes-commandes/<int:order_id>/annuler/", views.order_cancel,
         name="order_cancel"),
]
