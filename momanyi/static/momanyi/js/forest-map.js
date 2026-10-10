// Map of every registered tree, grouped into clusters when zoomed out.
(function () {
    'use strict';

    var el = document.getElementById('forest-map');
    if (!el || typeof L === 'undefined') return;

    var apiUrl = el.dataset.apiUrl;
    var detailTemplate = el.dataset.detailTemplate; // e.g. /trees/__ID__/

    var map = L.map('forest-map').setView([0.2, 37.9], 6);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '\u00a9 OpenStreetMap contributors', maxZoom: 19
    }).addTo(map);

    var cluster = (typeof L.markerClusterGroup === 'function')
        ? L.markerClusterGroup({ chunkedLoading: true })
        : L.layerGroup();
    map.addLayer(cluster);

    function colour(status, verification) {
        if (status === 'dead') return '#d97706';
        return verification === 'verified' ? '#15803d' : '#4ade80';
    }

    function popup(p) {
        var box = document.createElement('div');
        var title = document.createElement('strong');
        title.textContent = p.tree_id;
        box.appendChild(title);
        [p.species, p.county + ' County', p.status + ', ' + p.verification].forEach(function (text) {
            var line = document.createElement('div');
            line.textContent = text;
            box.appendChild(line);
        });
        var link = document.createElement('a');
        link.href = detailTemplate.replace('__ID__', encodeURIComponent(p.tree_id));
        link.textContent = 'View details';
        box.appendChild(link);
        return box;
    }

    fetch(apiUrl, { credentials: 'same-origin' })
        .then(function (response) {
            if (!response.ok) throw new Error('Request failed');
            return response.json();
        })
        .then(function (geojson) {
            var bounds = [];
            geojson.features.forEach(function (f) {
                var lng = f.geometry.coordinates[0];
                var lat = f.geometry.coordinates[1];
                var marker = L.circleMarker([lat, lng], {
                    radius: 7, weight: 2, color: '#ffffff', fillOpacity: 0.95,
                    fillColor: colour(f.properties.status, f.properties.verification)
                });
                marker.bindPopup(popup(f.properties));
                cluster.addLayer(marker);
                bounds.push([lat, lng]);
            });
            if (bounds.length) map.fitBounds(bounds, { padding: [30, 30], maxZoom: 14 });
            var count = document.getElementById('map-count');
            if (count) count.textContent = geojson.features.length.toLocaleString();
        })
        .catch(function () {
            var count = document.getElementById('map-count');
            if (count) count.textContent = 'could not be loaded';
        });
})();
