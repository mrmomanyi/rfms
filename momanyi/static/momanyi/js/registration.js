// Tree registration page: location tools, uniqueness check and form validation.
(function () {
    'use strict';

    var form = document.getElementById('tree-registration-form');
    if (!form) return;

    var CHECK_URL = form.dataset.checkUrl;
    var SUBCOUNTIES_URL = form.dataset.subcountiesUrl;
    var DEFAULT_CENTER = [-0.0236, 37.9062];   // Kenya
    var DEFAULT_ZOOM = 6;

    var map = null;
    var marker = null;

    function $(id) { return document.getElementById(id); }

    // ---------- helpers ----------
    function showToast(message, type) {
        var colours = {
            success: ['#dcfce7', '#14532d', '#15803d'],
            error: ['#fee2e2', '#b91c1c', '#b91c1c'],
            warning: ['#fef3c7', '#92400e', '#d97706'],
            info: ['#dbeafe', '#1e3a8a', '#2563eb']
        };
        var c = colours[type] || colours.info;
        var div = document.createElement('div');
        div.className = 'toast';
        div.setAttribute('role', 'status');
        div.textContent = message;
        div.style.background = c[0];
        div.style.color = c[1];
        div.style.borderLeftColor = c[2];
        document.body.appendChild(div);
        setTimeout(function () { if (div.parentNode) div.parentNode.removeChild(div); }, 4000);
    }

    function getCookie(name) {
        var value = null;
        document.cookie.split(';').forEach(function (part) {
            part = part.trim();
            if (part.indexOf(name + '=') === 0) value = decodeURIComponent(part.substring(name.length + 1));
        });
        return value;
    }

    function setLoader(show, text) {
        var loader = $('map-loader');
        if (!loader) return;
        loader.style.display = show ? 'flex' : 'none';
        if (text) loader.querySelector('p').textContent = text;
    }

    // ---------- validation state ----------
    function setValidation(message, type) {
        var box = $('coordinate-validation-status');
        var icons = { success: '\u2705', error: '\u274c', warning: '\u26a0\ufe0f', loading: '\u23f3' };
        box.className = 'validation-box status-' + type;
        box.querySelector('.validation-icon').textContent = icons[type] || '\u26a0\ufe0f';
        box.querySelector('.validation-text').textContent = message;
    }

    function setCheck(id, ok, text) {
        var li = $(id);
        li.textContent = (ok ? '\u2705 ' : '\u274c ') + text;
    }

    function value(id) { return ($(id).value || '').trim(); }

    function checkFormValidity() {
        var coordsOk = $('coords-validated').value === 'true';
        var speciesOk = !!value('species');
        var locationOk = !!(value('county') && value('subcounty') && value('plot-name') &&
                            value('forest-category') && value('tree-status'));
        var contributorOk = !!(value('contributor-type') && value('contributor-name'));
        var latLngOk = !!(value('latitude') && value('longitude'));

        setCheck('check-coords', coordsOk, 'Coordinates validated (unique location)');
        setCheck('check-species', speciesOk, 'Tree species selected');
        setCheck('check-location', locationOk, 'Location information complete');
        setCheck('check-contributor', contributorOk, 'Contributor information complete');

        var all = coordsOk && speciesOk && locationOk && contributorOk && latLngOk;
        $('register-btn').disabled = !all;
        return all;
    }

    function invalidateCoordinates() {
        $('coords-validated').value = 'false';
        setValidation('Coordinates changed. Please validate.', 'warning');
    }

    // ---------- map ----------
    function updateMapLocation(lat, lng) {
        if (!map) return;
        map.setView([lat, lng], Math.max(16, map.getZoom()));
        if (!marker) {
            marker = L.marker([lat, lng], { draggable: true, title: 'Tree location' }).addTo(map);
            marker.on('dragend', function () {
                var p = marker.getLatLng();
                updateFinalCoordinates(p.lat, p.lng);
                getAddressDetails(p.lat, p.lng);
            });
        } else {
            marker.setLatLng([lat, lng]);
        }
        $('map-lat').textContent = lat.toFixed(6);
        $('map-lng').textContent = lng.toFixed(6);
    }

    function updateFinalCoordinates(lat, lng) {
        $('latitude').value = lat.toFixed(6);
        $('longitude').value = lng.toFixed(6);
        $('current-coords').textContent = lat.toFixed(6) + ', ' + lng.toFixed(6);
        $('manual-latitude').value = lat.toFixed(6);
        $('manual-longitude').value = lng.toFixed(6);
        invalidateCoordinates();
        checkFormValidity();
    }

    function setLocation(lat, lng) {
        updateMapLocation(lat, lng);
        updateFinalCoordinates(lat, lng);
        getAddressDetails(lat, lng);
    }

    function getAddressDetails(lat, lng) {
        var url = 'https://nominatim.openstreetmap.org/reverse?format=json&lat=' + lat +
                  '&lon=' + lng + '&zoom=18&addressdetails=1&accept-language=en';
        fetch(url)
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data || !data.display_name) return;
                $('address-text').textContent = data.display_name;
                var a = data.address || {};
                var parts = [];
                if (a.road) parts.push('Road: ' + a.road);
                if (a.suburb) parts.push('Suburb: ' + a.suburb);
                var place = a.city || a.town || a.village;
                if (place) parts.push('Place: ' + place);
                if (a.county) parts.push('County: ' + a.county);
                $('place-details').textContent = parts.join(' | ');
            })
            .catch(function () { /* the address is optional */ });
    }

    function initMap() {
        if (typeof L === 'undefined') {
            $('map').textContent = 'The map could not be loaded. You can still enter coordinates by hand.';
            return;
        }
        map = L.map('map').setView(DEFAULT_CENTER, DEFAULT_ZOOM);

        var street = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '\u00a9 OpenStreetMap contributors', maxZoom: 19
        });
        var satellite = L.tileLayer(
            'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            { attribution: '\u00a9 Esri', maxZoom: 19 });
        street.addTo(map);

        $('toggle-satellite').addEventListener('change', function () {
            if (this.checked) { map.removeLayer(street); satellite.addTo(map); }
            else { map.removeLayer(satellite); street.addTo(map); }
        });
        $('zoom-in-btn').addEventListener('click', function () { map.zoomIn(); });
        $('zoom-out-btn').addEventListener('click', function () { map.zoomOut(); });
        $('reset-view-btn').addEventListener('click', function () { map.setView(DEFAULT_CENTER, DEFAULT_ZOOM); });

        map.on('click', function (e) { setLocation(e.latlng.lat, e.latlng.lng); });
        map.on('mousemove', function (e) {
            $('cursor-coords').textContent = e.latlng.lat.toFixed(6) + ', ' + e.latlng.lng.toFixed(6);
        });
    }

    // ---------- location methods ----------
    function initTabs() {
        var tabs = document.querySelectorAll('.method-tab');
        var panels = document.querySelectorAll('.method-panel');
        tabs.forEach(function (tab) {
            tab.addEventListener('click', function () {
                tabs.forEach(function (t) { t.classList.remove('active'); t.setAttribute('aria-selected', 'false'); });
                panels.forEach(function (p) { p.classList.remove('active'); });
                tab.classList.add('active');
                tab.setAttribute('aria-selected', 'true');
                $('method-' + tab.dataset.method).classList.add('active');
                if (map) setTimeout(function () { map.invalidateSize(); }, 50);
            });
        });
    }

    function initSearch() {
        var input = $('location-search');

        function render(results, query) {
            var box = $('search-results');
            box.textContent = '';
            box.style.display = 'block';
            if (!results.length) {
                var none = document.createElement('div');
                none.className = 'search-result';
                none.textContent = 'No results for "' + query + '". Try a different search.';
                box.appendChild(none);
                return;
            }
            results.forEach(function (result) {
                var parts = result.display_name.split(',');
                var row = document.createElement('div');
                row.className = 'search-result';
                row.tabIndex = 0;
                var title = document.createElement('strong');
                title.textContent = parts[0];
                var rest = document.createElement('small');
                rest.textContent = parts.slice(1).join(',').trim();
                row.appendChild(title);
                row.appendChild(rest);
                function choose() {
                    box.style.display = 'none';
                    input.value = result.display_name;
                    setLocation(parseFloat(result.lat), parseFloat(result.lon));
                    showToast('Location set: ' + parts[0], 'success');
                }
                row.addEventListener('click', choose);
                row.addEventListener('keydown', function (e) { if (e.key === 'Enter') choose(); });
                box.appendChild(row);
            });
        }

        function search() {
            var query = input.value.trim();
            if (!query) return;
            setLoader(true, 'Searching\u2026');
            fetch('https://nominatim.openstreetmap.org/search?format=json&q=' + encodeURIComponent(query) +
                  '&countrycodes=ke&limit=8&accept-language=en')
                .then(function (r) { return r.json(); })
                .then(function (data) { setLoader(false); render(data, query); })
                .catch(function () { setLoader(false); showToast('Search failed. Please try again.', 'error'); });
        }

        $('search-btn').addEventListener('click', search);
        input.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); search(); } });
        document.querySelectorAll('.chip').forEach(function (chip) {
            chip.addEventListener('click', function () { input.value = chip.dataset.place; search(); });
        });
    }

    function initGPS() {
        function start() {
            if (!navigator.geolocation) { showToast('This device does not support GPS.', 'error'); return; }
            setLoader(true, 'Getting your location\u2026');
            navigator.geolocation.getCurrentPosition(function (pos) {
                setLoader(false);
                setLocation(pos.coords.latitude, pos.coords.longitude);
                $('accuracy-value').textContent = 'Accuracy: ' + Math.round(pos.coords.accuracy) + ' m';
                $('gps-quality-text').textContent = 'Location found';
                showToast('Current location detected.', 'success');
            }, function (error) {
                setLoader(false);
                var text = 'GPS error. Use the coordinates method instead.';
                if (error.code === error.PERMISSION_DENIED) text = 'Location access denied. Use the coordinates method.';
                else if (error.code === error.TIMEOUT) text = 'GPS timed out. Try again outdoors.';
                $('gps-quality-text').textContent = text;
                showToast(text, 'error');
            }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
        }
        $('current-location-btn').addEventListener('click', start);
    }

    function initManual() {
        function apply() {
            var lat = parseFloat($('manual-latitude').value);
            var lng = parseFloat($('manual-longitude').value);
            if (isNaN(lat) || isNaN(lng)) { showToast('Enter both latitude and longitude as numbers.', 'warning'); return; }
            if (lat < -90 || lat > 90 || lng < -180 || lng > 180) { showToast('Those coordinates are out of range.', 'error'); return; }
            setLocation(lat, lng);
            showToast('Coordinates applied.', 'success');
            document.querySelector('.method-tab[data-method="map"]').click();
        }
        $('apply-coords-btn').addEventListener('click', apply);
        ['manual-latitude', 'manual-longitude'].forEach(function (id) {
            $(id).addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); apply(); } });
        });
        $('clear-coords-btn').addEventListener('click', function () {
            $('manual-latitude').value = '';
            $('manual-longitude').value = '';
        });
        $('paste-coords-btn').addEventListener('click', function () {
            if (!navigator.clipboard) { showToast('Paste is not available here. Type the values.', 'warning'); return; }
            navigator.clipboard.readText().then(function (text) {
                var parts = text.split(/[,;\s]+/).filter(Boolean);
                var lat = parseFloat(parts[0]);
                var lng = parseFloat(parts[1]);
                if (parts.length >= 2 && !isNaN(lat) && !isNaN(lng)) {
                    $('manual-latitude').value = lat;
                    $('manual-longitude').value = lng;
                    showToast('Coordinates pasted.', 'success');
                } else {
                    showToast('The clipboard does not contain coordinates.', 'warning');
                }
            }).catch(function () { showToast('Could not read the clipboard.', 'error'); });
        });
    }

    function initLocationButtons() {
        $('clear-location-btn').addEventListener('click', function () {
            ['latitude', 'longitude', 'manual-latitude', 'manual-longitude'].forEach(function (id) { $(id).value = ''; });
            $('current-coords').textContent = '0.000000, 0.000000';
            $('address-text').textContent = 'No location selected';
            $('place-details').textContent = '';
            if (marker && map) { map.removeLayer(marker); marker = null; }
            invalidateCoordinates();
            checkFormValidity();
        });
        $('copy-coords-btn').addEventListener('click', function () {
            var text = value('latitude') + ', ' + value('longitude');
            if (!navigator.clipboard) { showToast('Copy is not available here.', 'warning'); return; }
            navigator.clipboard.writeText(text)
                .then(function () { showToast('Coordinates copied.', 'success'); })
                .catch(function () { showToast('Could not copy.', 'error'); });
        });
    }

    // ---------- uniqueness check ----------
    function validateCoordinates() {
        var lat = value('latitude');
        var lng = value('longitude');
        if (!lat || !lng) { setValidation('Please set the location first.', 'warning'); return; }
        setValidation('Checking this location\u2026', 'loading');

        fetch(CHECK_URL, {
            method: 'POST',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
            body: JSON.stringify({ latitude: lat, longitude: lng })
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            $('coords-validated').value = data.available ? 'true' : 'false';
            setValidation(data.message, data.available ? (data.status === 'warning' ? 'warning' : 'success') : 'error');
            checkFormValidity();
        })
        .catch(function () { setValidation('Could not check the location. Please try again.', 'error'); });
    }

    // ---------- county -> sub-county ----------
    function loadSubcounties(selectedId) {
        var county = $('county');
        var sub = $('subcounty');
        sub.textContent = '';
        var first = document.createElement('option');
        first.value = '';
        first.textContent = 'Select Sub-County';
        sub.appendChild(first);
        sub.disabled = true;

        if (!county.value) { checkFormValidity(); return Promise.resolve(); }

        return fetch(SUBCOUNTIES_URL + '?county_id=' + encodeURIComponent(county.value))
            .then(function (r) {
                if (!r.ok) throw new Error('Request failed');
                return r.json();
            })
            .then(function (data) {
                data.subcounties.forEach(function (item) {
                    var option = document.createElement('option');
                    option.value = item.id;
                    option.textContent = item.name;
                    if (selectedId && String(item.id) === String(selectedId)) option.selected = true;
                    sub.appendChild(option);
                });
                sub.disabled = data.subcounties.length === 0;
                if (!data.subcounties.length) showToast('No sub-counties found for this county.', 'warning');
                checkFormValidity();
            })
            .catch(function () { showToast('Could not load sub-counties.', 'error'); });
    }

    // ---------- start up ----------
    document.addEventListener('DOMContentLoaded', function () {
        initTabs();
        try { initMap(); } catch (err) { console.error('Map failed to start:', err); }
        initSearch();
        initGPS();
        initManual();
        initLocationButtons();

        $('validate-coords-btn').addEventListener('click', validateCoordinates);
        $('county').addEventListener('change', function () { loadSubcounties(null); });

        ['subcounty', 'plot-name', 'species', 'forest-category', 'tree-status',
         'contributor-type', 'contributor-name'].forEach(function (id) {
            $(id).addEventListener('change', checkFormValidity);
            $(id).addEventListener('input', checkFormValidity);
        });

        form.addEventListener('submit', function (e) {
            if (!checkFormValidity()) {
                e.preventDefault();
                showToast('Please complete all the checks first.', 'error');
                return;
            }
            var button = $('register-btn');
            setTimeout(function () { button.disabled = true; button.textContent = 'Registering\u2026'; }, 0);
        });

        // Restore the form after the server sent it back with an error
        var restoreSub = $('subcounty').dataset.selected;
        var pending = $('county').value ? loadSubcounties(restoreSub) : Promise.resolve();
        pending.then(function () {
            var lat = parseFloat(value('latitude'));
            var lng = parseFloat(value('longitude'));
            if (!isNaN(lat) && !isNaN(lng)) {
                updateMapLocation(lat, lng);
                $('current-coords').textContent = lat.toFixed(6) + ', ' + lng.toFixed(6);
                setValidation('Please validate the location again.', 'warning');
            }
            checkFormValidity();
        });
    });
})();
