/* Google Places (Legacy API), one native input + custom suggestion list */
(function () {
  "use strict";

  function parseComponents(components) {
    var out = { line1: "", line2: "", city: "", state: "", zip: "" };
    var num = "";
    var route = "";
    (components || []).forEach(function (c) {
      var types = c.types || [];
      var long = c.longText || c.long_name || "";
      var short = c.shortText || c.short_name || "";
      if (types.indexOf("street_number") >= 0) num = long;
      if (types.indexOf("route") >= 0) route = long;
      if (types.indexOf("subpremise") >= 0) out.line2 = long;
      if (types.indexOf("locality") >= 0) out.city = long;
      if (types.indexOf("postal_town") >= 0 && !out.city) out.city = long;
      if (types.indexOf("sublocality") >= 0 && !out.city) out.city = long;
      if (types.indexOf("administrative_area_level_1") >= 0) out.state = short || long;
      if (types.indexOf("postal_code") >= 0) out.zip = long;
    });
    out.line1 = (num + " " + route).trim();
    if (!out.line1 && route) out.line1 = route;
    return out;
  }

  function setVal(root, name, value) {
    var el = root.querySelector('[name="' + name + '"]');
    if (el) el.value = value || "";
  }

  function showStatus(root, msg, isError) {
    var el = root.querySelector("[data-address-maps-status]");
    if (!el) return;
    el.textContent = msg || "";
    el.classList.toggle("d-none", !msg);
    el.classList.toggle("text-ok-red", !!isError);
    el.classList.toggle("text-muted-warm", !isError);
  }

  function fillFromPlace(root, place, search) {
    if (!place) return;
    var formatted = place.formatted_address || place.formattedAddress || "";
    var parsed = parseComponents(place.address_components || place.addressComponents);
    if (!parsed.line1 && formatted) {
      setVal(root, "address_line1", formatted.split(",")[0] || "");
    } else {
      setVal(root, "address_line1", parsed.line1);
    }
    setVal(root, "address_line2", parsed.line2);
    setVal(root, "address_city", parsed.city);
    setVal(root, "address_state", parsed.state);
    setVal(root, "address_zip", parsed.zip);

    var loc = place.geometry ? place.geometry.location : place.location;
    if (loc) {
      setVal(root, "address_lat", String(typeof loc.lat === "function" ? loc.lat() : loc.lat));
      setVal(root, "address_lng", String(typeof loc.lng === "function" ? loc.lng() : loc.lng));
    }
    if (search && formatted) search.value = formatted;
    root.querySelectorAll("[data-address-field]").forEach(function (el) {
      el.dispatchEvent(new Event("input", { bubbles: true }));
    });
    root.dispatchEvent(new CustomEvent("ok-address-filled", { bubbles: true }));
    showStatus(root, "");
  }

  function refererHelp() {
    return "Google Maps blocked this site. In Google Cloud Console → Credentials, add referrer: "
      + window.location.protocol + "//" + window.location.host + "/*";
  }

  function loadMaps(apiKey) {
    if (window.google && window.google.maps && window.google.maps.places) {
      return Promise.resolve();
    }
    return new Promise(function (resolve, reject) {
      var id = "ok-gmaps-script";
      var existing = document.getElementById(id);
      if (existing) {
        existing.addEventListener("load", resolve);
        existing.addEventListener("error", reject);
        return;
      }
      window.okMapsReady = function () {
        delete window.okMapsReady;
        resolve();
      };
      window.gm_authFailure = function () {
        var msg = refererHelp();
        document.querySelectorAll("[data-address-autocomplete]").forEach(function (root) {
          showStatus(root, msg, true);
        });
        if (window.OK && OK.toast) OK.toast(msg);
      };
      var s = document.createElement("script");
      s.id = id;
      s.async = true;
      s.src = "https://maps.googleapis.com/maps/api/js?key="
        + encodeURIComponent(apiKey) + "&libraries=places&callback=okMapsReady";
      s.onerror = function () { reject(new Error("maps_script")); };
      document.head.appendChild(s);
    });
  }

  function attachAutocomplete(root, search, list) {
    var service = new google.maps.places.AutocompleteService();
    var placesService = new google.maps.places.PlacesService(document.createElement("div"));

    var timer = null;
    var active = -1;
    var items = [];

    function hideList() {
      list.classList.add("d-none");
      list.innerHTML = "";
      items = [];
      active = -1;
    }

    function pick(prediction) {
      if (!prediction || !prediction.place_id) return;
      hideList();
      placesService.getDetails({
        placeId: prediction.place_id,
        fields: ["address_components", "formatted_address", "geometry"]
      }, function (place, status) {
        if (status === google.maps.places.PlacesServiceStatus.OK && place) {
          fillFromPlace(root, place, search);
        } else {
          showStatus(root, "Could not read that address. Try again.", true);
        }
      });
    }

    function renderSuggestions(predictions) {
      list.innerHTML = "";
      items = predictions || [];
      active = -1;
      if (!items.length) {
        hideList();
        return;
      }
      items.forEach(function (prediction, idx) {
        var li = document.createElement("li");
        li.setAttribute("role", "option");
        li.textContent = prediction.description || "";
        li.addEventListener("mousedown", function (e) {
          e.preventDefault();
          pick(prediction);
        });
        list.appendChild(li);
      });
      list.classList.remove("d-none");
    }

    function fetchSuggestions(q) {
      service.getPlacePredictions({
        input: q,
        componentRestrictions: { country: "us" }
      }, function (predictions, status) {
        if ((search.value || "").trim() !== q) return;
        if (status === google.maps.places.PlacesServiceStatus.OK || status === google.maps.places.PlacesServiceStatus.ZERO_RESULTS) {
          renderSuggestions(predictions || []);
        } else {
          hideList();
        }
      });
    }

    search.addEventListener("input", function () {
      var raw = search.value || "";
      var q = raw.trim();
      if (timer) clearTimeout(timer);
      if (q.length < 3) {
        hideList();
        return;
      }
      timer = setTimeout(function () { fetchSuggestions(q); }, 220);
    });

    search.addEventListener("keydown", function (e) {
      if (list.classList.contains("d-none") || !items.length) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        active = Math.min(active + 1, items.length - 1);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        active = Math.max(active - 1, 0);
      } else if (e.key === "Enter" && active >= 0) {
        e.preventDefault();
        var p = items[active];
        if (p) pick(p);
        return;
      } else if (e.key === "Escape") {
        hideList();
        return;
      } else {
        return;
      }
      Array.prototype.forEach.call(list.children, function (li, i) {
        li.classList.toggle("is-active", i === active);
      });
    });

    document.addEventListener("click", function (e) {
      if (!root.contains(e.target)) hideList();
    });

    showStatus(root, "Start typing to search addresses.");
  }

  function attachLocationSearch(search, list, onPlace) {
    var service = new google.maps.places.AutocompleteService();
    var placesService = new google.maps.places.PlacesService(document.createElement("div"));
    var timer = null;
    var active = -1;
    var items = [];
    var lastLen = 0;
    var seq = 0;
    // Philly metro | local results return faster than a country-wide search
    var locBias = { north: 40.25, south: 39.75, east: -74.85, west: -75.55 };

    function hideList() {
      list.classList.add("d-none");
      list.innerHTML = "";
      items = [];
      active = -1;
    }

    function pick(prediction) {
      if (!prediction || !prediction.place_id) return;
      hideList();
      placesService.getDetails({
        placeId: prediction.place_id,
        fields: ["address_components", "formatted_address", "geometry"]
      }, function (place, status) {
        if (status === google.maps.places.PlacesServiceStatus.OK && place) {
          onPlace(place);
        }
      });
    }

    function renderSuggestions(predictions) {
      list.innerHTML = "";
      items = predictions || [];
      active = -1;
      if (!items.length) {
        hideList();
        return;
      }
      items.forEach(function (prediction) {
        var li = document.createElement("li");
        li.setAttribute("role", "option");
        li.textContent = prediction.description || "";
        li.addEventListener("mousedown", function (e) {
          e.preventDefault();
          pick(prediction);
        });
        list.appendChild(li);
      });
      list.classList.remove("d-none");
    }

    function fetchSuggestions(q) {
      var my = ++seq;
      service.getPlacePredictions({
        input: q,
        componentRestrictions: { country: "us" },
        locationBias: locBias,
        types: ["geocode"]
      }, function (predictions, status) {
        if (my !== seq) return;
        if ((search.value || "").trim() !== q) return;
        if (status === google.maps.places.PlacesServiceStatus.OK || status === google.maps.places.PlacesServiceStatus.ZERO_RESULTS) {
          renderSuggestions(predictions || []);
        } else {
          hideList();
        }
      });
    }

    search.addEventListener("input", function () {
      delete search.dataset.locZip;
      delete search.dataset.locQuery;
      delete search.dataset.locLat;
      delete search.dataset.locLng;
      var q = (search.value || "").trim();
      if (timer) clearTimeout(timer);
      if (q.length < 2) {
        hideList();
        lastLen = q.length;
        return;
      }
      var pasted = q.length - lastLen > 1;
      lastLen = q.length;
      if (pasted) fetchSuggestions(q);
      else timer = setTimeout(function () { fetchSuggestions(q); }, 50);
    });

    search.addEventListener("keydown", function (e) {
      if (list.classList.contains("d-none") || !items.length) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        active = Math.min(active + 1, items.length - 1);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        active = Math.max(active - 1, 0);
      } else if (e.key === "Enter" && active >= 0) {
        e.preventDefault();
        var p = items[active];
        if (p) pick(p);
        return;
      } else if (e.key === "Escape") {
        hideList();
        return;
      } else {
        return;
      }
      Array.prototype.forEach.call(list.children, function (li, i) {
        li.classList.toggle("is-active", i === active);
      });
    });

    document.addEventListener("click", function (e) {
      if (!list.contains(e.target) && e.target !== search) hideList();
    });
  }

  function initLocationPicker(root) {
    if (!root || root._locInit) return;
    var apiKey = root.getAttribute("data-maps-key");
    var search = root.querySelector("[data-loc-search]");
    var list = root.querySelector("[data-loc-predictions]");
    if (!apiKey || !search || !list) return;
    root._locInit = true;
    loadMaps(apiKey).then(function () {
      attachLocationSearch(search, list, function (place) {
        var formatted = place.formatted_address || "";
        var parsed = parseComponents(place.address_components || place.addressComponents);
        search.value = formatted;
        if (parsed.zip) search.dataset.locZip = parsed.zip;
        search.dataset.locQuery = formatted.toLowerCase();
        var loc = place.geometry && place.geometry.location;
        if (loc) {
          search.dataset.locLat = String(typeof loc.lat === "function" ? loc.lat() : loc.lat);
          search.dataset.locLng = String(typeof loc.lng === "function" ? loc.lng() : loc.lng);
        }
        document.dispatchEvent(new CustomEvent("ok-loc-search"));
      });
    }).catch(function () {
      /* manual ZIP / address entry still works via Find */
    });
  }

  function reverseGeocode(apiKey, lat, lng) {
    return loadMaps(apiKey).then(function () {
      return new Promise(function (resolve, reject) {
        if (!window.google || !google.maps || !google.maps.Geocoder) {
          reject(new Error("no geocoder"));
          return;
        }
        var geocoder = new google.maps.Geocoder();
        geocoder.geocode({ location: { lat: lat, lng: lng } }, function (results, status) {
          if (status === "OK" && results && results[0]) {
            resolve(results[0].formatted_address || "");
          } else {
            reject(new Error(status || "geocode failed"));
          }
        });
      });
    });
  }

  function useDeviceLocation(root, btn) {
    if (!navigator.geolocation) {
      showStatus(root, "Location is not available in this browser.", true);
      return;
    }
    var apiKey = root.getAttribute("data-maps-key");
    var search = root.querySelector("[data-address-search]");
    if (!apiKey) {
      showStatus(root, "Address search is not configured for this store.", true);
      return;
    }
    var original = btn ? btn.innerHTML : "";
    if (btn) {
      btn.setAttribute("aria-busy", "true");
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Locating…';
    }
    navigator.geolocation.getCurrentPosition(function (pos) {
      var lat = pos.coords.latitude, lng = pos.coords.longitude;
      loadMaps(apiKey).then(function () {
        var geocoder = new google.maps.Geocoder();
        geocoder.geocode({ location: { lat: lat, lng: lng } }, function (results, status) {
          if (status === "OK" && results && results[0]) {
            fillFromPlace(root, results[0], search);
          } else {
            if (search) search.value = "Your location";
            setVal(root, "address_lat", String(lat));
            setVal(root, "address_lng", String(lng));
            root.dispatchEvent(new CustomEvent("ok-address-filled", { bubbles: true }));
          }
          if (btn) { btn.removeAttribute("aria-busy"); btn.innerHTML = original; }
        });
      }).catch(function () {
        if (btn) { btn.removeAttribute("aria-busy"); btn.innerHTML = original; }
        showStatus(root, "Could not load maps for your location.", true);
      });
    }, function () {
      if (btn) { btn.removeAttribute("aria-busy"); btn.innerHTML = original; }
      showStatus(root, "Could not get your location. Please allow access and try again.", true);
    }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 });
  }

  function initRoot(root) {
    if (!root || root._addrInit) return;
    var apiKey = root.getAttribute("data-maps-key");
    var search = root.querySelector("[data-address-search]");
    var list = root.querySelector("[data-address-predictions]");
    if (!apiKey || !search || !list) return;
    root._addrInit = true;

    var geoBtn = root.querySelector("[data-address-geo]");
    if (geoBtn) {
      geoBtn.addEventListener("click", function (e) {
        e.preventDefault();
        useDeviceLocation(root, geoBtn);
      });
    }

    loadMaps(apiKey).then(function () {
      attachAutocomplete(root, search, list);
    }).catch(function () {
      showStatus(root, "Could not load Google Maps. Check the API key and enable Maps JavaScript API + Places API.", true);
    });
  }

  function boot() {
    document.querySelectorAll("[data-address-autocomplete]").forEach(initRoot);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  window.OK = window.OK || {};
  window.OK.initAddressAutocomplete = initRoot;
  window.OK.initLocationPicker = initLocationPicker;
  window.OK.preloadMaps = function (apiKey) { return apiKey ? loadMaps(apiKey) : Promise.resolve(); };
  window.OK.reverseGeocode = reverseGeocode;
})();
