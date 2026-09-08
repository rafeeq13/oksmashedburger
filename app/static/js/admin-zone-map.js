(function () {
  var mapInstance = null;
  var marker = null;
  var circles = [];
  var mapData = null;

  function clearMap() {
    circles.forEach(function (c) { c.setMap(null); });
    circles = [];
    if (marker) { marker.setMap(null); marker = null; }
    mapInstance = null;
  }

  function loadMaps(apiKey) {
    if (window.google && window.google.maps) return Promise.resolve();
    return new Promise(function (resolve, reject) {
      var id = "ok-gmaps-script";
      var existing = document.getElementById(id);
      if (existing) {
        if (window.google && window.google.maps) { resolve(); return; }
        existing.addEventListener("load", resolve);
        existing.addEventListener("error", reject);
        return;
      }
      window.okMapsReady = function () { delete window.okMapsReady; resolve(); };
      var s = document.createElement("script");
      s.id = id;
      s.async = true;
      s.src = "https://maps.googleapis.com/maps/api/js?key="
        + encodeURIComponent(apiKey) + "&callback=okMapsReady";
      s.onerror = function () { reject(new Error("maps")); };
      document.head.appendChild(s);
    });
  }

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function storeCenter(data) {
    if (data.lat == null || data.lng == null) return null;
    var lat = Number(data.lat);
    var lng = Number(data.lng);
    if (!isFinite(lat) || !isFinite(lng)) return null;
    return { lat: lat, lng: lng };
  }

  function updatePinForm(center) {
    var latEl = document.getElementById("adminZoneMapLat");
    var lngEl = document.getElementById("adminZoneMapLng");
    if (latEl) latEl.value = center.lat.toFixed(6);
    if (lngEl) lngEl.value = center.lng.toFixed(6);
  }

  function setPinCenter(center) {
    if (!marker || !mapInstance) return;
    marker.setPosition(center);
    circles.forEach(function (c) { c.setCenter(center); });
    updatePinForm(center);
  }

  function drawCircles(map, center, zones) {
    circles.forEach(function (c) { c.setMap(null); });
    circles = [];
    (zones || []).forEach(function (z) {
      var miles = parseFloat(z.radius_miles) || 0;
      if (miles <= 0) return;
      var circle = new google.maps.Circle({
        map: map,
        center: center,
        radius: miles * 1609.344,
        strokeColor: z.color || "#E0A200",
        strokeOpacity: 0.9,
        strokeWeight: 2,
        fillColor: z.color || "#E0A200",
        fillOpacity: 0.14,
      });
      circles.push(circle);
    });
  }

  function fitZoneBounds(center, zones) {
    if (!mapInstance) return;
    var bounds = new google.maps.LatLngBounds();
    bounds.extend(center);
    (zones || []).forEach(function (z) {
      var miles = parseFloat(z.radius_miles) || 0;
      if (miles <= 0) return;
      var circle = circles.find(function (c) {
        return Math.abs(c.getRadius() - miles * 1609.344) < 1;
      });
      if (circle) bounds.union(circle.getBounds());
    });
    if ((zones || []).length && circles.length) {
      mapInstance.fitBounds(bounds, 20);
      google.maps.event.addListenerOnce(mapInstance, "idle", function () {
        var z = mapInstance.getZoom();
        if (typeof z === "number") mapInstance.setZoom(Math.min(z + 2, 16));
      });
    } else {
      mapInstance.setZoom(14);
    }
  }

  function drawZoneMap(el, data, center) {
    clearMap();
    mapData = data;
    mapInstance = new google.maps.Map(el, {
      center: center,
      zoom: 12,
      mapTypeControl: false,
      streetViewControl: false,
      fullscreenControl: true,
    });
    marker = new google.maps.Marker({
      position: center,
      map: mapInstance,
      title: data.name || "",
      draggable: true,
      cursor: "grab",
    });
    if (data.address) {
      var info = new google.maps.InfoWindow({
        content: '<div style="max-width:240px;line-height:1.4">'
          + '<div style="font-weight:600">' + escapeHtml(data.name || "Store") + '</div>'
          + '<div style="font-size:12px;color:#555;margin-top:4px">' + escapeHtml(data.address) + '</div>'
          + '<div style="font-size:11px;color:#888;margin-top:6px">Drag the pin or click the map</div>'
          + '</div>',
      });
      info.open({ map: mapInstance, anchor: marker });
      marker.addListener("click", function () {
        info.open({ map: mapInstance, anchor: marker });
      });
    }
    drawCircles(mapInstance, center, data.zones);
    fitZoneBounds(center, data.zones);
    updatePinForm(center);

    marker.addListener("dragend", function () {
      var pos = marker.getPosition();
      setPinCenter({ lat: pos.lat(), lng: pos.lng() });
    });
    mapInstance.addListener("click", function (e) {
      setPinCenter({ lat: e.latLng.lat(), lng: e.latLng.lng() });
    });
  }

  function initAdminZoneMap() {
    var el = document.getElementById("adminZoneMap");
    var dataEl = document.getElementById("adminZoneMapData");
    if (!el || !dataEl) return;
    var key = el.getAttribute("data-maps-key");
    if (!key) return;

    var data;
    try { data = JSON.parse(dataEl.textContent); } catch (e) { return; }

    loadMaps(key).then(function () {
      var center = storeCenter(data);
      if (center) {
        drawZoneMap(el, data, center);
        return;
      }
      var query = data.geocode_query || data.address;
      if (!query) return;
      var geocoder = new google.maps.Geocoder();
      geocoder.geocode({ address: query }, function (results, status) {
        if (status !== "OK" || !results || !results[0]) return;
        var loc = results[0].geometry.location;
        drawZoneMap(el, data, { lat: loc.lat(), lng: loc.lng() });
      });
    }).catch(function () {});
  }

  window.initAdminZoneMap = initAdminZoneMap;
})();
