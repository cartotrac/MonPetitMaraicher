/* Carte Leaflet de la page de recherche : affiche les RESULTATS FILTRES.
   Les données viennent du bloc json_script "donnees-carte" du template. */

var CAT_STYLES = {
  AB:       { color: "#1b5e20", label: "Agriculture Biologique (AB)" },
  PERMA:    { color: "#6a1b9a", label: "Permaculture" },
  PAYSAN:   { color: "#f9a825", label: "Agriculture paysanne" },
  RAISONNE: { color: "#0277bd", label: "Agriculture raisonnée" },
  CONV:     { color: "#546e7a", label: "Conventionnelle" }
};

var bloc = document.getElementById("donnees-carte");
var carte = L.map("carte-recherche").setView([46.6, 2.4], 6);

L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 18,
  attribution: "&copy; <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a>"
}).addTo(carte);

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

exploitants.forEach(function (e) {
  present[e.mode_production] = true;
  var style = CAT_STYLES[e.mode_production] || CAT_STYLES.CONV;
  var marker = L.circleMarker([e.latitude, e.longitude], {
    radius: 8,
    color: "#fff",
    weight: 1.5,
    fillColor: style.color,
    fillOpacity: 0.85
  }).bindPopup(
    "<strong>" + e.nom_ferme + "</strong><br>" + (e.ville || "") +
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
