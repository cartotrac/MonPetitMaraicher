/* Carte Leaflet de la page de recherche : affiche les RESULTATS FILTRES.
   Les données viennent du bloc json_script "donnees-carte" du template.

   Fonds de carte (sans cle, conformes aux conditions d'utilisation — les
   tuiles OpenStreetMap directes renvoient 403 aux serveurs benevoles) :
   - Plan    : CARTO Voyager (basemap CARTO/OSM)
   - Ortho   : Esri World Imagery (photographies aeriennes)

   Superpositions administratives (chargees a la demande, au premier
   affichage uniquement) :
   - Regions, Departements : france-geojson (gregoiredavid)
   Les departements (numero + nom) portent une etiquette permanente,
   revelee au-dela d'un seuil de zoom.
*/

var CAT_STYLES = {
  AB:       { color: "#1b5e20", label: "Agriculture Biologique (AB)" },
  PERMA:    { color: "#6a1b9a", label: "Permaculture" },
  PAYSAN:   { color: "#f9a825", label: "Agriculture paysanne" },
  RAISONNE: { color: "#0277bd", label: "Agriculture raisonnée" },
  CONV:     { color: "#546e7a", label: "Conventionnelle" }
};

var bloc = document.getElementById("donnees-carte");
var carte = L.map("carte-recherche").setView([46.6, 2.4], 6);

/* ------------------------------------------------------------------ fonds */
/* Fond « Plan » : Plan IGN V2 (Géoplateforme IGN, données ouvertes, WMTS
   SANS clé — plus fiable que les tuiles OSM directes qui renvoient 403).
   Même source que le Géoportail : data.geopf.fr. */
var fondPlan = L.tileLayer(
  "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0" +
  "&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&STYLE=normal&FORMAT=image/png" +
  "&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}", {
    maxZoom: 19,
    attribution: "Plan IGN V2 &copy; <a href=\"https://www.geoportail.gouv.fr/\">IGN</a>"
  });

var fondOrtho = L.tileLayer(
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 19,
    attribution: "Esri, Maxar, Earthstar Geographics"
  });

fondPlan.addTo(carte);

/* ------------------------------------------- superpositions administratives */
var FOND_ADMIN = "https://raw.githubusercontent.com/gregoiredavid/france-geojson/master/";

var COUCHES_ADMIN = {
  "Régions": {
    url: FOND_ADMIN + "regions.geojson",
    style: { color: "#8e24aa", weight: 2, fill: false, opacity: 0.9 }
  },
  "Départements": {
    url: FOND_ADMIN + "departements.geojson",
    style: { color: "#1565c0", weight: 1.5, fill: false, opacity: 0.8 },
    etiquette: "dep"      // numéro + nom affichés au-delà du zoom label
  }
};

/* Zoom minimum à partir duquel chaque couche administrative devient
   disponible : en dessous, elle est grisée dans le contrôle et son
   chargement est refusé. (La couche Communes a été retirée : trop
   lourde, et le fond Plan IGN suffit à identifier les communes.) */
var SEUILS = { "Régions": 0, "Départements": 6 };
/* Zoom minimum pour afficher les étiquettes (noms) des couches actives */
var SEUILS_LABELS = { "dep": 8 };

var couchesAdmin = {};
Object.keys(COUCHES_ADMIN).forEach(function (nom) {
  couchesAdmin[nom] = L.layerGroup();
});

// Un seul contrôle de couches : fonds (plan/ortho) + superpositions
L.control.layers(
  { "Plan": fondPlan, "Ortho (vue aérienne)": fondOrtho },
  couchesAdmin,
  { position: "topleft" }
).addTo(carte);

// Disponibilité d'une couche selon le zoom courant
function coucheDisponible(nom) {
  var seuil = SEUILS[nom] || 0;
  return carte.getZoom() >= seuil;
}

// Griser / dégriser les cases des couches administratives dans le contrôle
function majCouleurs() {
  document.querySelectorAll(".leaflet-control-layers-overlays label").forEach(function (lab) {
    var texte = (lab.textContent || "").trim();
    Object.keys(COUCHES_ADMIN).forEach(function (nom) {
      if (texte.indexOf(nom) === -1) return;
      var input = lab.querySelector("input");
      if (!input) return;
      if (coucheDisponible(nom)) {
        input.disabled = false;
        lab.style.opacity = 1;
        lab.title = "";
      } else {
        input.disabled = true;
        lab.style.opacity = 0.45;
        lab.title = "Disponible à partir du zoom " + (SEUILS[nom] || 0);
        // retirer la couche si elle était affichée
        if (input.checked && carte.hasLayer(couchesAdmin[nom])) {
          carte.removeLayer(couchesAdmin[nom]);
        }
      }
    });
  });
}

// Afficher / masquer les étiquettes (noms) selon le zoom et l'activation
function majLabels() {
  var conteneur = carte.getContainer();
  ["dep"].forEach(function (cle) {
    var nomCouche = "Départements";
    var actif = carte.hasLayer(couchesAdmin[nomCouche])
      && carte.getZoom() >= (SEUILS_LABELS[cle] || 0);
    conteneur.classList.toggle("labels-" + cle + "-on", actif);
  });
}

// Les couches administratives se chargent au premier affichage seulement,
// et uniquement si le zoom est suffisant
carte.on("overlayadd", function (e) {
  var conf = COUCHES_ADMIN[e.name];
  if (!conf || conf.chargee) return;
  if (!coucheDisponible(e.name)) {
    // zoom insuffisant : décocher immédiatement, la couche reste grisé
    conf.grisee = true;
    majCouleurs();
    return;
  }
  conf.chargee = true;
  fetch(conf.url).then(function (r) { return r.json(); }).then(function (data) {
    var geo = L.geoJSON(data, {
      style: conf.style,
      onEachFeature: function (feature, couche) {
        var props = feature.properties || {};
        var nom = props.nom || props.NOM || props.code || props.CODE || "";
        if (nom) {
          couche.bindPopup("<strong>" + nom + "</strong>");
        }
        // Étiquette permanente : masquée par défaut (classe CSS) et
        // révélée par majLabels au-delà du seuil de zoom de sa couche.
        if (conf.etiquette) {
          var etiquette = nom;
          if (conf.etiquette === "dep") {
            var code = props.code || props.CODE || props.code_dep || "";
            etiquette = (code ? code + " — " : "") + nom;
          }
          couche.bindTooltip(etiquette, {
            permanent: true,
            direction: "center",
            className: "label-admin label-" + conf.etiquette
          });
        }
      }
    });
    couchesAdmin[e.name].addLayer(geo);
    majLabels();
  }).catch(function () {
    conf.chargee = false;  // permet de retenter en recochant la couche
  });
});

carte.on("zoomend", function () { majCouleurs(); majLabels(); });
carte.on("overlayremove", majLabels);
carte.whenReady(majCouleurs);

/* --------------------------------------------------------------- legende */
var legend = L.control({ position: "bottomright" });
legend.onAdd = function () {
  var div = L.DomUtil.create("div", "map-legend");
  for (var key in CAT_STYLES) {
    var style = CAT_STYLES[key];
    div.innerHTML +=
      '<label><input type="checkbox" checked data-cat="' + key + '">' +
      '<span class="legend-dot" style="background:' + style.color + '"></span>' +
      style.label + "</label>";
  }
  return div;
};
legend.addTo(carte);

var markers = [];
var present = {};
var exploitants = JSON.parse(bloc.textContent);
var ACTIVITES = {
  "MARAICHER": "🥬 Maraîcher·ère",
  "ARBORICULTEUR": "🍎 Arboriculteur·rice",
  "ELEVEUR": "🐄 Éleveur·euse",
  "FROMAGER": "🧀 Fromager·ère",
  "APICULTEUR": "🍯 Apiculteur·rice",
  "AUTRE": "🌾 Autre production locale"
};

exploitants.forEach(function (e) {
  present[e.mode_production] = true;
  var style = CAT_STYLES[e.mode_production] || CAT_STYLES.CONV;
  var activite = ACTIVITES[e.activite] || "";
  var marker = L.circleMarker([e.latitude, e.longitude], {
    radius: 8,
    color: "#fff",
    weight: 1.5,
    fillColor: style.color,
    fillOpacity: 0.85
  }).bindPopup(
    "<strong>" + e.nom_ferme + "</strong>" +
    (activite ? '<br><span class="muted">' + activite + "</span>" : "") +
    "<br>" + (e.ville || "") +
    '<br><a href="' + e.url + '">Voir la ferme →</a>'
  );
  marker._category = e.mode_production;
  markers.push(marker);
  carte.addLayer(marker);
});

// Ne cocher dans la légende que les modes réellement présents
document.querySelectorAll(".map-legend input").forEach(function (cb) {
  if (!present[cb.dataset.cat]) {
    cb.checked = false;
    cb.disabled = true;
    cb.parentElement.style.opacity = 0.4;
  }
});

// Cadrer la carte sur les résultats
if (exploitants.length) {
  var bornes = [];
  exploitants.forEach(function (e) { bornes.push([e.latitude, e.longitude]); });
  carte.fitBounds(bornes, { padding: [30, 30], maxZoom: 12 });
}

function applyFilters() {
  var enabled = {};
  document.querySelectorAll(".map-legend input").forEach(function (cb) {
    enabled[cb.dataset.cat] = cb.checked;
  });
  markers.forEach(function (m) {
    if (enabled[m._category]) {
      if (!carte.hasLayer(m)) carte.addLayer(m);
    } else if (carte.hasLayer(m)) {
      carte.removeLayer(m);
    }
  });
}

document.addEventListener("change", function (e) {
  if (e.target.closest && e.target.closest(".map-legend")) applyFilters();
});

document.getElementById("btn-geoloc").addEventListener("click", function () {
  if (!navigator.geolocation) {
    alert("La géolocalisation n'est pas supportée par votre navigateur.");
    return;
  }
  navigator.geolocation.getCurrentPosition(
    function (pos) {
      carte.setView([pos.coords.latitude, pos.coords.longitude], 11);
      L.circleMarker([pos.coords.latitude, pos.coords.longitude], {
        radius: 6, color: "#c62828", fillColor: "#ef5350", fillOpacity: 0.9
      }).addTo(carte).bindPopup("Vous êtes ici").openPopup();
    },
    function () { alert("Position non disponible."); },
    { timeout: 10000 }
  );
});
