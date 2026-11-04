/* Carte de localisation par clic (Leaflet) — utilisée sur la fiche
   exploitation (latitude/longitude) et les points de livraison.
   - Un élément avec data-pick-map devient une carte : le clic (ou le
     déplacement du marqueur) renseigne les champs inputs pointés par
     data-lat-input / data-lon-input.
   - Un bouton avec data-geocoder interroge Nominatim (OSM) à partir
     des champs adresse / code postal / ville, et positionne le marqueur
     (les champs lat/lon sont mis à jour automatiquement). */
(function () {
  "use strict";

  var FOND_IGN = "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile" +
    "&VERSION=1.0.0&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&STYLE=normal" +
    "&FORMAT=image/png&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}";

  function valeur(id) {
    var el = document.getElementById(id);
    return el ? (el.value || "").trim() : "";
  }

  function nombre(valeur) {
    var n = parseFloat(valeur);
    return isNaN(n) ? null : n;
  }

  function initCarte(carteEl) {
    var latIn = document.getElementById(carteEl.dataset.latInput);
    var lonIn = document.getElementById(carteEl.dataset.lonInput);
    if (!latIn || !lonIn) return;

    var lat = nombre(latIn.value), lon = nombre(lonIn.value);
    var position = (lat !== null && lon !== null)
      ? [lat, lon] : [46.6, 2.4];
    var zoomInitial = (lat !== null && lon !== null) ? 15 : 6;

    var carte = L.map(carteEl.id).setView(position, zoomInitial);
    L.tileLayer(FOND_IGN, {
      maxZoom: 19,
      attribution: "Plan IGN V2 &copy; <a href=\"https://www.geoportail.gouv.fr/\">IGN</a>"
    }).addTo(carte);

    var marqueur = L.marker(position, { draggable: true }).addTo(carte);
    if (lat === null || lon === null) marqueur.setOpacity(0.55);

    function appliquer(lat, lon, silencieux) {
      latIn.value = lat.toFixed(6);
      lonIn.value = lon.toFixed(6);
      marqueur.setLatLng([lat, lon]);
      marqueur.setOpacity(1);
      if (!silencieux) carte.panTo([lat, lon]);
    }

    carte.on("click", function (e) {
      appliquer(e.latlng.lat, e.latlng.lng);
    });
    marqueur.on("dragend", function () {
      var p = marqueur.getLatLng();
      appliquer(p.lat, p.lng);
    });
    latIn.addEventListener("change", function () {
      var a = nombre(latIn.value), o = nombre(lonIn.value);
      if (a !== null && o !== null) appliquer(a, o);
    });
    lonIn.addEventListener("change", function () {
      var a = nombre(latIn.value), o = nombre(lonIn.value);
      if (a !== null && o !== null) appliquer(a, o);
    });

    carteEl._pickMap = { carte: carte, marqueur: marqueur, appliquer: appliquer };
  }

  function initGeocodage(bouton) {
    bouton.addEventListener("click", function () {
      var adresse = valeur(bouton.dataset.adresse);
      var cp = valeur(bouton.dataset.cp);
      var ville = valeur(bouton.dataset.ville);
      var requete = [adresse, cp, ville].filter(Boolean).join(", ");
      if (!requete) {
        alert("Renseignez d'abord l'adresse (ou ville / code postal).");
        return;
      }
      bouton.disabled = true;
      bouton.textContent = "⏳ Recherche…";
      fetch("https://nominatim.openstreetmap.org/search?format=json&limit=1" +
            "&countrycodes=fr&addressdetails=0&q=" +
            encodeURIComponent(requete))
        .then(function (r) { return r.json(); })
        .then(function (res) {
          bouton.disabled = false;
          bouton.textContent = bouton.dataset.libelle || "📍 Localiser";
          if (!res.length) {
            alert("Adresse introuvable : précisez ou cliquez directement sur la carte.");
            return;
          }
          var lat = parseFloat(res[0].lat), lon = parseFloat(res[0].lon);
          var carteEl = bouton.dataset.carte
            ? document.getElementById(bouton.dataset.carte) : null;
          if (carteEl && carteEl._pickMap) {
            carteEl._pickMap.appliquer(lat, lon);
            carteEl._pickMap.carte.setView([lat, lon], 17);
          } else {
            var latIn = document.getElementById(bouton.dataset.lat);
            var lonIn = document.getElementById(bouton.dataset.lon);
            if (latIn) latIn.value = lat.toFixed(6);
            if (lonIn) lonIn.value = lon.toFixed(6);
            // data-submit : envoyer le formulaire parent juste après
            // le géocodage (ex : enregistrer la position d'un point)
            if (bouton.dataset.submit && bouton.closest("form")) {
              bouton.closest("form").submit();
            }
          }
        })
        .catch(function () {
          bouton.disabled = false;
          bouton.textContent = bouton.dataset.libelle || "📍 Localiser";
          alert("Géocodage indisponible : cliquez directement sur la carte.");
        });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-pick-map]").forEach(initCarte);
    document.querySelectorAll("[data-geocoder]").forEach(initGeocodage);
  });
})();
