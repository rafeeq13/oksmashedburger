/* =========================================================
   OK Smashed Burger — front-end interactions (Flask build)
   Header/footer are server-rendered (Jinja). This file only wires
   up interactions + fills decorative placeholder images.
   ========================================================= */
(function () {
  "use strict";

  /* ---------- sticky-aware smooth scroll for in-page CTAs ---------- */
  function stickyOffset() {
    var maxBottom = 0;
    document.querySelectorAll('.ok-header, [class*="sticky"]').forEach(function (s) {
      var cs = window.getComputedStyle(s);
      if (cs.position !== "sticky" && cs.position !== "fixed") return;
      var h = s.getBoundingClientRect().height;
      if (h === 0 || h > window.innerHeight * 0.4) return;
      var topVal = parseFloat(cs.top);
      if (isNaN(topVal) || topVal > 150) return;
      var bottom = topVal + h;
      if (bottom > maxBottom) maxBottom = bottom;
    });
    return maxBottom + 0;
  }
  function animateScrollTo(toY, duration) {
    var root = document.documentElement;
    var startY = window.scrollY || window.pageYOffset;
    var maxY = Math.max(0, root.scrollHeight - window.innerHeight);
    toY = Math.max(0, Math.min(toY, maxY));
    var dist = toY - startY;
    if (Math.abs(dist) < 2) return;
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) { window.scrollTo(0, toY); return; }
    var prev = root.style.scrollBehavior;
    root.style.scrollBehavior = "auto";
    var startT = null;
    function ease(t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }
    function step(ts) {
      if (startT === null) startT = ts;
      var p = Math.min(1, (ts - startT) / duration);
      window.scrollTo(0, startY + dist * ease(p));
      if (p < 1) requestAnimationFrame(step);
      else root.style.scrollBehavior = prev;
    }
    requestAnimationFrame(step);
  }
  function smoothScrollToEl(el) { animateScrollTo(window.scrollY + el.getBoundingClientRect().top - stickyOffset(), 900); }

  /* ---------- decorative placeholder images (data-ph) ---------- */
  function svgURI(s) { return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(s); }
  var PALETTE = ["#FFC72C", "#FFE08A", "#FFD75E", "#F4B23E", "#FFF3CC"];
  function hash(str) { var h = 0; for (var i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) & 0xffffff; return h; }
  function escapeXml(s) { return String(s).replace(/[<>&]/g, function (c) { return { "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]; }); }
  function burgerGlyph(x, y, s) {
    return '<g transform="translate(' + x + ' ' + y + ') scale(' + s + ')" opacity="0.92">' +
      '<ellipse cx="0" cy="30" rx="52" ry="10" fill="rgba(20,20,20,.08)"/>' +
      '<rect x="-46" y="6" width="92" height="14" rx="7" fill="#7a4a24"/>' +
      '<path d="M-48 4 q10 -12 20 -5 q9 -10 19 -4 q11 -10 21 -3 q11 -8 18 3 q6 9 -6 12 h-84 q-10 -4 -8 -13z" fill="#3fa845"/>' +
      '<ellipse cx="0" cy="-12" rx="50" ry="20" fill="#F4B23E"/><ellipse cx="0" cy="-16" rx="50" ry="17" fill="#FFC72C"/></g>';
  }
  function makePlaceholder(label, type, w, h) {
    w = w || 600; h = h || 450;
    var bg = PALETTE[hash(label || "ok") % PALETTE.length];
    if (type === "avatar") {
      var initial = (label || "?").trim().charAt(0).toUpperCase();
      return svgURI('<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '"><rect width="100%" height="100%" fill="#141414"/><text x="50%" y="54%" font-family="Poppins,Arial" font-weight="800" font-size="' + (w * 0.5) + '" fill="#FFC72C" text-anchor="middle" dominant-baseline="middle">' + initial + "</text></svg>");
    }
    if (type === "map") {
      return svgURI('<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '"><rect width="100%" height="100%" fill="#eef1ee"/><g stroke="#dfe4df" stroke-width="10"><path d="M0 90 H' + w + '"/><path d="M0 210 H' + w + '"/><path d="M120 0 V' + h + '"/><path d="M360 0 V' + h + '"/></g><path d="M60 ' + (h - 40) + ' Q' + (w * 0.4) + ' ' + (h * 0.3) + ' ' + (w - 70) + ' 70" fill="none" stroke="#FFC72C" stroke-width="8" stroke-linecap="round" stroke-dasharray="2 16"/><g transform="translate(' + (w - 70) + ' 70)"><path d="M0 -34 C18 -34 26 -20 26 -8 C26 8 0 30 0 30 C0 30 -26 8 -26 -8 C-26 -20 -18 -34 0 -34Z" fill="#E11B22"/><circle cy="-8" r="9" fill="#fff"/></g></svg>');
    }
    var showGlyph = type !== "banner";
    return svgURI('<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="' + bg + '"/><stop offset="1" stop-color="#FFF3CC"/></linearGradient></defs><rect width="100%" height="100%" fill="url(#g)"/><text x="26" y="' + (h - 26) + '" font-family="Poppins,Arial" font-weight="800" font-size="20" fill="#141414" opacity="0.55">OK · ' + escapeXml(label || "") + "</text>" + (showGlyph ? burgerGlyph(w / 2, h / 2 - 10, Math.min(w, h) / 130) : "") + "</svg>");
  }

  var PHOTOS = {
    burger: ["1568901346375-23c9450c58cd", "1571091718767-18b5b1457add", "1550547660-d9450f859349", "1586190848861-99aa4a171e90", "1594212699903-ec8a3eca50f5"],
    fries: ["1573080496219-bb080dd4f877", "1630384060421-cb20d0e0649d", "1585109649139-366815a0d713"],
    shake: ["1572490122747-3968b75cc699", "1568901839119-631418a3910d", "1553787499-6f9133860278"],
    chicken: ["1626645738196-c2a7c87a8f58", "1562967914-608f82629710", "1513639776629-7b61b0ac49cb"],
    salad: ["1512621776951-a57141f2eefd", "1540189549336-e6e99c3679fe"],
    drink: ["1554866585-cd94860890b7"], dessert: ["1499636136210-6f4ee915583e", "1551024506-0bccd828d307"],
    meal: ["1513104890138-7c749659a591", "1550317138-10000687a72b"], hero: ["1552566626-52f8b828add9", "1517248135467-4c7edcad34c4"]
  };
  function photoCategory(label, type) {
    var s = (label || "").toLowerCase();
    if (type === "hero" || type === "banner") return "hero";
    if (/frie|fry/.test(s)) return "fries";
    if (/shake|milkshake/.test(s)) return "shake";
    if (/chicken|buffalo|wing|nugget|crisp/.test(s)) return "chicken";
    if (/vegan|salad|veggie|leaf|plant/.test(s)) return "salad";
    if (/cookie|cake|dessert|sweet/.test(s)) return "dessert";
    if (/drink|cola|soda|cup|beverage/.test(s)) return "drink";
    if (/combo|feast|family|bundle|box|meal/.test(s)) return "meal";
    return "burger";
  }
  function realImageURL(label, type, w, h) {
    if (type === "avatar") return "https://i.pravatar.cc/240?u=" + encodeURIComponent(label || "ok");
    if (type === "map") return null;
    var pool = PHOTOS[photoCategory(label, type)] || PHOTOS.burger;
    return "https://images.unsplash.com/photo-" + pool[Math.abs(hash(label || "ok")) % pool.length] + "?w=" + w + "&h=" + h + "&fit=crop&q=70";
  }
  function hydratePlaceholders(root) {
    (root || document).querySelectorAll("img[data-ph]").forEach(function (img) {
      if (img.dataset.phDone) return;
      img.dataset.phDone = "1";
      var ratio = (img.dataset.phRatio || "4/3").split("/");
      var w = 800, h = Math.round((800 * (+ratio[1] || 3)) / (+ratio[0] || 4));
      var type = img.dataset.phType || "food";
      if (!img.getAttribute("alt")) img.alt = img.dataset.ph || "";
      var fallback = makePlaceholder(img.dataset.ph, type, w, h);
      var real = realImageURL(img.dataset.ph, type, w, h);
      if (real) { img.onerror = function () { img.onerror = null; img.src = fallback; }; img.src = real; }
      else img.src = fallback;
    });
  }

  /* ---------- modern icons ----------
     Font Awesome Solid is a heavy, filled set. Every fa-solid / fa-regular
     glyph is swapped for the matching Lucide symbol from the inline sprite —
     same meaning, modern stroke style. Brand marks (Instagram, Visa, Apple…)
     are left alone: Lucide ships none, so those stay on Font Awesome.
     Done here rather than across ~400 template usages so the mapping lives in
     one place and can be turned off in one line. */
  function modernIcons(root) {
    if (!document.getElementById("i-check")) return;      // sprite not on this page
    (root || document).querySelectorAll("i.fa-solid, i.fa-regular").forEach(function (el) {
      var name = null;
      el.classList.forEach(function (c) {
        if (c.indexOf("fa-") === 0 && c !== "fa-solid" && c !== "fa-regular" && !name) {
          name = c.slice(3);
        }
      });
      if (!name || !document.getElementById("i-" + name)) return;
      // Stars stay on Font Awesome. Lucide draws them stroke-only, so every
      // rating on the site rendered as a hollow outline instead of a solid
      // star. FA's fa-solid star is a filled shape, fa-regular the outline.
      if (name.indexOf("star") === 0) return;
      var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("class", "ok-i " + el.className.replace(/fa-[a-z0-9-]+/g, "").trim());
      svg.setAttribute("aria-hidden", "true");
      svg.setAttribute("focusable", "false");
      // An <svg> with no intrinsic size renders at 300x150 and wrecks the
      // layout. These are presentation attributes, so any width/height class
      // the element already carries still wins over them.
      svg.setAttribute("width", "1em");
      svg.setAttribute("height", "1em");
      var use = document.createElementNS("http://www.w3.org/2000/svg", "use");
      use.setAttribute("href", "#i-" + name);
      svg.appendChild(use);
      el.replaceWith(svg);
    });
  }

  /* ---------- toast ---------- */
  function toast(msg) {
    var wrap = document.getElementById("ok-toast-wrap");
    if (!wrap) { wrap = document.createElement("div"); wrap.id = "ok-toast-wrap"; document.body.appendChild(wrap); }
    var t = document.createElement("div");
    t.className = "ok-toast"; t.innerHTML = '<span class="tick"><i class="fa-solid fa-circle-check"></i></span> ' + msg;
    wrap.appendChild(t);
    setTimeout(function () { t.style.opacity = "0"; t.style.transition = "opacity .3s"; setTimeout(function () { t.remove(); }, 300); }, 2200);
  }

  /* ---------- overlays ---------- */
  // Keep the page behind an open overlay from scrolling. Counted, because the
  // location modal can be opened from inside the drawer.
  var _locks = 0;
  function lockScroll(on) {
    _locks = Math.max(0, _locks + (on ? 1 : -1));
    var locked = !!_locks;
    document.documentElement.style.overflow = locked ? "hidden" : "";
    document.body.style.overflow = locked ? "hidden" : "";
    // overflow:hidden alone still lets a touch scroll inside a modal chain out
    // to the page once the panel hits its end. overscroll-behavior stops that.
    document.documentElement.style.overscrollBehavior = locked ? "none" : "";
    document.body.style.overscrollBehavior = locked ? "none" : "";
  }

  function openDrawer(open) {
    var d = document.getElementById("okDrawer"); if (!d) return;
    if (d.classList.contains("is-open") !== open) lockScroll(open);
    d.classList.toggle("is-open", open);
    document.querySelector('.drawer-backdrop[data-close="drawer"]').classList.toggle("is-open", open);
  }
  // ---- current store, kept in sync EVERYWHERE without a reload ----
  var _storeSlug = null;
  function highlightStore(slug) {
    if (slug) _storeSlug = slug;
    document.querySelectorAll("[data-loc-pick]").forEach(function (btn) {
      // One state class, matching the template. It used to toggle
      // "border-okyellow" while the server rendered "border-yellow", so the
      // server's highlight was never cleared and two cards looked selected.
      var on = !!_storeSlug && btn.getAttribute("data-loc-pick") === _storeSlug;
      btn.classList.toggle("is-selected", on);
      btn.classList.remove("border-okyellow", "border-yellow");
    });
  }
  // A store was chosen anywhere (locations page, the modal, …). Reflect it on
  // every store indicator currently on the page: header label, store-name spots
  // and the modal highlight.
  document.addEventListener("ok:store", function (e) {
    var d = e.detail || {};
    if (d.slug) _storeSlug = d.slug;
    if (d.city != null && d.zip != null)
      document.querySelectorAll("[data-store-label]").forEach(function (el) { el.textContent = d.city + " · " + d.zip; });
    if (d.name != null)
      document.querySelectorAll("[data-store-name]").forEach(function (el) { el.textContent = d.name; });
    if (d.address != null)
      document.querySelectorAll("[data-store-address]").forEach(function (el) { el.textContent = d.address; });
    highlightStore(_storeSlug);
  });
  // Persist a store choice in the session, then announce it to the whole page.
  // `optimistic` (name/city/zip) updates the UI instantly before the request returns.
  function selectStore(slug, optimistic) {
    if (!slug) return;
    if (optimistic) document.dispatchEvent(new CustomEvent("ok:store", { detail: Object.assign({ slug: slug }, optimistic) }));
    return fetch("/api/select-store/" + encodeURIComponent(slug), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (d && d.ok) {
          document.dispatchEvent(new CustomEvent("ok:store", { detail: d }));
          // Menu is rendered per store on the server — reload once the session
          // store is saved so the grid matches the chosen location.
          var path = location.pathname || "";
          if (path === "/menu" || path.indexOf("/menu/") === 0) location.reload();
        }
        return d;
      })
      .catch(function () {});
  }

  /* ---------- shared popup show/hide ----------
     Every popup enters from the LEFT and leaves to the RIGHT. The direction
     cannot come from CSS alone: on close the panel would simply run back the
     way it came in, so the exit needs its own `.is-closing` state that is
     cleared once the transition has finished. */
  var MODAL_EXIT_MS = 430;      // must outlast the .4s exit transition
  function showModal(m, b, open) {
    if (!m) return;
    if ((m.style.visibility === "visible") !== open) lockScroll(open);
    if (open) {
      if (m._okHideT) { clearTimeout(m._okHideT); m._okHideT = null; }
      m.classList.remove("is-closing");
      m.style.visibility = "visible";
      m.style.pointerEvents = "auto";
      // TWO frames later: one rAF still lands in the same paint on some
      // machines, and the enter then jumps straight to the open state with no
      // visible travel. The second frame guarantees a painted "closed" state
      // to animate FROM.
      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          m.style.opacity = "1";
          m.classList.add("is-open");
        });
      });
    } else {
      m.classList.remove("is-open");
      m.classList.add("is-closing");
      m.style.opacity = "0";
      m.style.pointerEvents = "none";
      m._okHideT = setTimeout(function () {
        m.style.visibility = "hidden";
        m.classList.remove("is-closing");
        m._okHideT = null;
      }, MODAL_EXIT_MS);
    }
    if (b) b.classList.toggle("is-open", open);
  }

  function openLocation(open) {
    var m = document.getElementById("locModal"), b = document.getElementById("locBackdrop");
    if (!m) return;
    if (open && typeof locStep === "function") locStep(1);  // always start at "find a store"
    if (open && _storeSlug) highlightStore(_storeSlug);      // reflect the current choice
    showModal(m, b, open);
  }
  // When set (e.g. hero "Start Your Order"), picking a store goes here after close.
  var _locNext = null;
  function openItem(open) {
    var m = document.getElementById("itemModal"), b = document.getElementById("itemBackdrop");
    showModal(m, b, open);
  }
  function loadItem(slug) {
    var body = document.querySelector("#itemModal [data-item-body]");
    if (!body) return;
    body.innerHTML = '<div class="py-12 text-center text-slate"><i class="fa-solid fa-circle-notch fa-spin"></i> Loading…</div>';
    openItem(true);
    // the sheet is its own request, so edit mode has to travel with it —
    // otherwise its labels come back as plain text and cannot be clicked
    fetch("/item/" + encodeURIComponent(slug) + "/modal"
            + (document.getElementById("okIeBar") ? "?edit=1" : ""),
          { headers: { "X-Requested-With": "fetch" } })
      .then(function (r) { return r.ok ? r.text() : null; })
      .then(function (html) { body.innerHTML = html !== null ? html : '<p class="py-8 text-center text-slate">Could not load this item.</p>'; initReadMore(body); ; if (window.okIeRefresh) window.okIeRefresh(body); })
      .catch(function () { body.innerHTML = '<p class="py-8 text-center text-slate">Could not load this item.</p>'; });
  }

  /* ---------- read more / read less — inline expand / collapse ---------- */
  // Collapsed = one-line CSS truncate with the toggle inline right after it;
  // expanded = full text wraps, toggle flows after. Same classes every time so
  // every card behaves identically.
  function toggleReadMore(el) {
    var wrap = el.closest("[data-rm]"); if (!wrap) return;
    var txt = wrap.querySelector("[data-rm-text]"); if (!txt) return;
    if (wrap.getAttribute("data-expanded") === "1") {
      wrap.classList.add("d-flex", "align-items-baseline");
      txt.classList.add("text-truncate", "ok-min-w-0");
      el.textContent = el.getAttribute("data-more") || "Read more";
      wrap.setAttribute("data-expanded", "0");
    } else {
      wrap.classList.remove("d-flex", "align-items-baseline");
      txt.classList.remove("text-truncate", "ok-min-w-0");
      el.textContent = el.getAttribute("data-less") || "Read less";
      wrap.setAttribute("data-expanded", "1");
    }
  }
  // Hide the toggle when the text already fits on one line (nothing to expand).
  function initReadMore(root) {
    (root || document).querySelectorAll("[data-rm]").forEach(function (wrap) {
      var txt = wrap.querySelector("[data-rm-text]"), tog = wrap.querySelector("[data-rm-toggle]");
      if (!txt || !tog) return;
      tog.style.display = (wrap.getAttribute("data-expanded") !== "1" && txt.scrollWidth <= txt.clientWidth + 1) ? "none" : "";
    });
  }

  /* ---------- two-step location/service modal ---------- */
  function locSchedule(on) {
    var m = document.getElementById("locModal"); if (!m) return;
    var view = m.querySelector("[data-loc-typeview]"), panel = m.querySelector("[data-loc-schedpanel]");
    if (!view || !panel) return;
    // d-none, not "hidden": the panel is marked up with Bootstrap's class and
    // .hidden is defined nowhere, so this toggle used to do nothing at all and
    // the Schedule sub-panel never opened.
    view.classList.toggle("d-none", on);
    panel.classList.toggle("d-none", !on);
    panel.querySelectorAll("[data-loc-schedinput]").forEach(function (i) { i.disabled = !on; });
  }
  function locStep(n) {
    var m = document.getElementById("locModal"); if (!m) return;
    var s1 = m.querySelector('[data-loc-step="1"]'), s2 = m.querySelector('[data-loc-step="2"]');
    // d-none, not "hidden": the templates use Bootstrap and .hidden is not
    // defined anywhere, so this toggle used to be a no-op in both directions.
    if (s1) s1.classList.toggle("d-none", n !== 1);
    if (s2) s2.classList.toggle("d-none", n !== 2);
    locSchedule(false);
  }
  function locPick(card) {
    var m = document.getElementById("locModal"); if (!m || !card) return;
    var storeInput = m.querySelector("[data-loc-store]"), nameEl = m.querySelector("[data-loc-storename]");
    if (storeInput) storeInput.value = card.dataset.locPick || "";
    if (nameEl) nameEl.textContent = card.dataset.locName || "your store";
    var next = _locNext;
    _locNext = null;
    // Hero "Start Your Order" (and any opener with data-loc-next): set store then go there
    if (next && card.dataset.locPick) {
      window.location.href = "/set-location/" + encodeURIComponent(card.dataset.locPick)
        + "?next=" + encodeURIComponent(next);
      return;
    }
    // choosing a store in the modal selects it everywhere too (header, cards, …)
    selectStore(card.dataset.locPick, { name: card.dataset.locName, city: card.dataset.city, zip: card.dataset.zip, address: card.dataset.address });
    // the location is the thing the visitor came here to change, so close on
    // pick rather than pushing them through a second step
    openLocation(false);
    locStep(1);
  }
  function locFind() {
    var m = document.getElementById("locModal"); if (!m) return;
    var el = document.getElementById("locZip"), zip = ((el && el.value) || "").trim();
    if (!zip) { if (el) el.focus(); return; }
    var cards = Array.prototype.slice.call(m.querySelectorAll("[data-loc-pick]"));
    if (!cards.length) return;
    var q = zip.toLowerCase(), best = null;
    // exact delivery-zone ZIP first, then the store's own ZIP prefix,
    // then anything in the name/address, so a street number or a
    // neighbourhood name finds the right store too.
    cards.forEach(function (c) { if (!best && (c.dataset.zips || "").split(",").indexOf(zip) !== -1) best = c; });
    if (!best) cards.forEach(function (c) { if (!best && (c.dataset.zip || "") === zip) best = c; });
    if (!best) cards.forEach(function (c) { if (!best && (c.dataset.search || "").indexOf(q) !== -1) best = c; });
    if (!best && /^\d{3}/.test(zip)) cards.forEach(function (c) { if (!best && (c.dataset.zip || "").slice(0, 3) === zip.slice(0, 3)) best = c; });
    if (!best) { if (window.OK && OK.toast) OK.toast("No store matches that address"); return; }
    locPick(best);
  }

  function wire() {
    modernIcons();

    var hd = document.getElementById("okHeader");
    if (hd) window.addEventListener("scroll", function () { hd.classList.toggle("is-scrolled", window.scrollY > 8); });

    var searchBox = document.getElementById("okSearch");
    function openSearch(open) {
      if (!searchBox) return;
      searchBox.classList.toggle("is-open", open);
      if (open) { var i = searchBox.querySelector("[data-search-input]"); if (i) setTimeout(function () { i.focus(); }, 40); }
    }
    if (searchBox) searchBox.addEventListener("focusout", function (e) { if (!searchBox.contains(e.relatedTarget)) openSearch(false); });

    // Checkout: the address is required for delivery and meaningless for
    // pickup, so the attribute follows the order-type radios.
    (function () {
      var addr = document.querySelector("[data-address-field]");
      if (!addr) return;
      var radios = document.querySelectorAll('input[name="order_type"]');
      var row = document.querySelector("[data-address-row]");
      function sync() {
        var picked = document.querySelector('input[name="order_type"]:checked');
        var delivery = !picked || picked.value === "delivery";
        // required must come off with the field, or a pickup order can never
        // be submitted: browsers refuse to validate a hidden required input.
        addr.required = delivery;
        if (row) row.classList.toggle("d-none", !delivery);
      }
      radios.forEach(function (r) { r.addEventListener("change", sync); });
      sync();
    })();

    // Review form starts collapsed so the section stays a wall of reviews,
    // not a form. Opens on demand, and stays open if the server bounced the
    // submission back with an error.
    (function () {
      var form = document.querySelector("[data-review-form]");
      if (!form) return;
      function open() {
        form.classList.remove("d-none");
        var first = form.querySelector("input[name='name']");
        if (first) first.focus();
      }
      document.addEventListener("click", function (e) {
        if (e.target.closest("[data-review-open]")) { e.preventDefault(); open(); }
      });
      if (location.hash === "#reviews") open();
    })();

    var catbar = document.getElementById("menuCatbar");
    function openMenuSearch(open) {
      if (!catbar) return;
      catbar.classList.toggle("is-searching", open);
      if (open) { var i = catbar.querySelector("[data-msearch-input]"); if (i) setTimeout(function () { i.focus(); }, 40); }
    }

    // ── live menu filter ────────────────────────────────────────────────
    // The search fields used to only open and close. They filter now: every
    // card carries a lowercase data-search blob, so this is a substring test
    // per keystroke with no request and no re-render.
    var msInput = document.querySelector("[data-msearch-input]");
    var msEmpty = document.getElementById("menuNoResults");
    var msEcho = document.querySelector("[data-msearch-echo]");

    function filterMenu(q) {
      var items = document.querySelectorAll("[data-menu-item]");
      if (!items.length) return;
      q = (q || "").trim().toLowerCase();
      var shown = 0;
      items.forEach(function (el) {
        var hit = !q || (el.getAttribute("data-search") || "").indexOf(q) !== -1;
        el.style.display = hit ? "" : "none";
        if (hit) shown++;
      });
      // hide a whole category once every card inside it is filtered out
      document.querySelectorAll("[data-menu-section]").forEach(function (sec) {
        var any = Array.prototype.some.call(
          sec.querySelectorAll("[data-menu-item]"),
          function (el) { return el.style.display !== "none"; });
        sec.style.display = any ? "" : "none";
      });
      if (msEmpty) msEmpty.classList.toggle("d-none", shown !== 0);
      if (msEcho) msEcho.textContent = q ? '"' + q + '"' : "";
    }

    if (msInput) {
      msInput.addEventListener("input", function () { filterMenu(msInput.value); });
      msInput.addEventListener("keydown", function (e) { if (e.key === "Enter") e.preventDefault(); });
    }
    document.addEventListener("click", function (e) {
      if (e.target.closest("[data-msearch-clear]")) {
        if (msInput) msInput.value = "";
        filterMenu("");
      }
    });

    // arriving from the header search: /menu?q=shake
    var q0 = new URLSearchParams(window.location.search).get("q");
    if (q0 && document.querySelector("[data-menu-item]")) {
      if (msInput) msInput.value = q0;
      openMenuSearch(true);
      filterMenu(q0);
    }
    if (catbar) {
      catbar.addEventListener("mouseleave", function () { openMenuSearch(false); });
      catbar.addEventListener("focusout", function (e) { if (!catbar.contains(e.relatedTarget)) openMenuSearch(false); });
    }

    document.addEventListener("click", function (e) {
      var openT = e.target.closest("[data-open]"), closeT = e.target.closest("[data-close]");
      if (openT) { e.preventDefault(); if (openT.dataset.open === "drawer") openDrawer(true); if (openT.dataset.open === "location") { _locNext = openT.getAttribute("data-loc-next") || null; openLocation(true); } }
      if (closeT) { if (closeT.dataset.close === "drawer") openDrawer(false); if (closeT.dataset.close === "location") { _locNext = null; openLocation(false); } if (closeT.dataset.close === "item") openItem(false); }

      // read more / less — handle BEFORE data-item so it doesn't open the modal
      var rmT = e.target.closest("[data-rm-toggle]");
      if (rmT) { e.preventDefault(); e.stopPropagation(); toggleReadMore(rmT); return; }

      var itemT = e.target.closest("[data-item]");
      if (itemT) { e.preventDefault(); loadItem(itemT.dataset.item); return; }

      var locPickEl = e.target.closest("[data-loc-pick]");
      if (locPickEl) { e.preventDefault(); locPick(locPickEl); return; }
      if (e.target.closest("[data-loc-find]")) { e.preventDefault(); locFind(); return; }
      if (e.target.closest("[data-loc-back]")) { e.preventDefault(); locStep(1); return; }
      if (e.target.closest("[data-loc-schedule]")) { e.preventDefault(); locSchedule(true); return; }
      if (e.target.closest("[data-loc-schedback]")) { e.preventDefault(); locSchedule(false); return; }

      if (e.target.closest("[data-search-open]")) { e.preventDefault(); openSearch(true); }
      else if (e.target.closest("[data-search-close]")) { e.preventDefault(); openSearch(false); }
      else if (searchBox && searchBox.classList.contains("is-open") && !e.target.closest("#okSearch")) { openSearch(false); }

      if (e.target.closest("[data-msearch-open]")) { e.preventDefault(); openMenuSearch(true); }
      else if (e.target.closest("[data-msearch-close]")) { e.preventDefault(); openMenuSearch(false); }

      // add-on steppers: same pill as the item stepper but they may reach 0,
      // which is how "not on this burger" is expressed.
      var aBtn = e.target.closest("[data-astep]");
      if (aBtn) {
        var row = aBtn.closest("[data-addon]");
        var cSpan = row.querySelector("[data-acount]");
        var hidden = row.querySelector('input[type="hidden"]');
        var n = (parseInt(cSpan.textContent, 10) || 0) + (aBtn.dataset.astep === "-" ? -1 : 1);
        if (n < 0) n = 0;
        if (n > 20) n = 20;
        cSpan.textContent = n;
        if (hidden) hidden.value = n;
        row.classList.toggle("is-on", n > 0);
        recalcItem(aBtn.closest("[data-item-form]"));
      }

      var qBtn = !aBtn && e.target.closest(".qty button");
      if (qBtn) {
        var span = qBtn.parentElement.querySelector("span");
        var v = (parseInt(span.textContent, 10) || 0) + (qBtn.dataset.step === "-" ? -1 : 1);
        if (v < 1) v = 1;
        span.textContent = v;
        recalcItem(qBtn.closest("[data-item-form]"));
      }

      var chip = e.target.closest("[data-chip-group] .chip");
      if (chip) {
        if (chip.dataset.multi === undefined) chip.parentElement.querySelectorAll(".chip").forEach(function (c) { c.classList.remove("is-active"); });
        chip.classList.toggle("is-active");
        recalcItem(chip.closest("[data-item-form]"));
      }

      // order-type segmented toggle (delivery / pickup) — switches live, no reload
      var otBtn = e.target.closest("[data-ordertype]");
      if (otBtn) {
        var otGroup = otBtn.closest("[data-ordertype-group]");
        if (otGroup) otGroup.querySelectorAll("[data-ordertype]").forEach(function (x) {
          var on = x === otBtn;
          x.classList.toggle("bg-ink", on);
          x.classList.toggle("text-white", on);
          x.classList.toggle("text-ink", !on);
          x.classList.toggle("ok-shadow-md", on);
        });
        fetch("/api/order-type/" + encodeURIComponent(otBtn.getAttribute("data-ordertype")), { credentials: "same-origin" }).catch(function () {});
      }

      var addBtn = e.target.closest("[data-add-cart]");
      if (addBtn) { e.preventDefault(); var cc = document.getElementById("cartCount"); if (cc) cc.textContent = (parseInt(cc.textContent, 10) || 0) + 1; toast((addBtn.dataset.addCart || "Item") + " added to cart"); }

      // drawer nav group: one open at a time, so the drawer stays short
      var navGrp = e.target.closest("[data-navgroup]");
      if (navGrp) {
        var panel = document.getElementById(navGrp.getAttribute("aria-controls"));
        var open = navGrp.getAttribute("aria-expanded") === "true";
        navGrp.setAttribute("aria-expanded", open ? "false" : "true");
        if (panel) panel.classList.toggle("is-open", !open);
      }

      var accQ = e.target.closest(".acc-q");
      if (accQ) accQ.parentElement.classList.toggle("is-open");

      // FAQ category chips. They were decorative before — the sections are
      // data-driven now, so filtering is just matching one attribute.
      var faqChip = e.target.closest("[data-faq-filter]");
      if (faqChip) {
        var want = faqChip.getAttribute("data-faq-filter");
        document.querySelectorAll("[data-faq-filter]").forEach(function (b) {
          b.classList.toggle("is-active", b === faqChip);
        });
        document.querySelectorAll("[data-faq-group]").forEach(function (item) {
          item.style.display = (!want || item.getAttribute("data-faq-group") === want) ? "" : "none";
        });
      }

      var tabBtn = e.target.closest("[data-tab]");
      if (tabBtn) {
        var group = tabBtn.closest("[data-tab-group]"); var name = tabBtn.dataset.tab;
        group.querySelectorAll("[data-tab]").forEach(function (b) { b.classList.toggle("is-active", b === tabBtn); });
        // Panels are hidden with Bootstrap's .d-none; this used to toggle the
        // old Tailwind "hidden" class, so the tabs looked dead.
        group.querySelectorAll("[data-panel]").forEach(function (p) { p.classList.toggle("d-none", p.dataset.panel !== name); });
      }

      // Copy-to-clipboard (referral code). Falls back to execCommand where the
      // async clipboard API is unavailable (http origins, older browsers).
      var copyEl = e.target.closest("[data-copy]");
      if (copyEl) {
        e.preventDefault();
        var src = document.querySelector(copyEl.getAttribute("data-copy"));
        var text = src ? (src.textContent || "").trim() : "";
        if (text) {
          var done = function () { toast("Referral code copied"); };
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(done, function () { done(); });
          } else {
            var ta = document.createElement("textarea");
            ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
            document.body.appendChild(ta); ta.select();
            try { document.execCommand("copy"); } catch (err) {}
            document.body.removeChild(ta); done();
          }
        }
        return;
      }

      var anchor = e.target.closest('a[href^="#"]');
      if (anchor) {
        var href = anchor.getAttribute("href"); e.preventDefault();
        // If the target is a hidden tab panel, open its tab first, otherwise
        // we would scroll to an element that is still display:none.
        var pid = href.length > 1 ? decodeURIComponent(href.slice(1)) : "";
        var panel = pid && document.querySelector('[data-panel="' + pid + '"]');
        if (panel) {
          var tabBtn2 = document.querySelector('[data-tab="' + pid + '"]');
          if (tabBtn2) tabBtn2.click();
        }
        var id = href.length > 1 ? decodeURIComponent(href.slice(1)) : "";
        var target = id && document.getElementById(id);
        if (target) { smoothScrollToEl(target); if (history.replaceState) history.replaceState(null, "", href); }
      }
    });

    // One price, recomputed from the choices on screen: base + the selected
    // size + every add-on times how many of it, all multiplied by quantity.
    // The button is the only place a total is shown, so it cannot drift.
    function recalcItem(form) {
      if (!form) return;
      var total = parseFloat(form.dataset.base || "0") || 0;
      var variant = form.querySelector('input[name="variant_id"]:checked');
      if (variant) total += parseFloat(variant.dataset.delta || "0") || 0;
      form.querySelectorAll("[data-addon]").forEach(function (row) {
        var n = parseInt((row.querySelector("[data-acount]") || {}).textContent, 10) || 0;
        total += (parseFloat(row.dataset.price || "0") || 0) * n;
      });
      var qtySpan = form.querySelector(".qty:not(.qty-sm) span");
      total *= parseInt(qtySpan && qtySpan.textContent, 10) || 1;
      var out = form.querySelector("[data-total]");
      if (out) out.textContent = "$" + (total < 0 ? 0 : total).toFixed(2);
    }

    // a size chip checks its radio through the label, so recalc on change too
    document.addEventListener("change", function (e) {
      if (e.target.name === "variant_id") recalcItem(e.target.closest("[data-item-form]"));
    });

    // Quick-add modal form → add to cart without leaving the page.
    document.addEventListener("submit", function (e) {
      var form = e.target.closest("[data-item-form]");
      if (!form) return;
      e.preventDefault();
      var qtySpan = form.querySelector(".qty span");
      var fd = new FormData(form);
      if (qtySpan) fd.set("qty", parseInt(qtySpan.textContent, 10) || 1);
      var btn = form.querySelector('button[type="submit"]');
      if (btn) btn.disabled = true;
      fetch(form.getAttribute("action"), { method: "POST", body: fd, headers: { "X-Requested-With": "fetch" } })
        .then(function () {
          openItem(false);
          var cc = document.getElementById("cartCount");
          if (cc) cc.textContent = (parseInt(cc.textContent, 10) || 0) + (parseInt(fd.get("qty"), 10) || 1);
          toast("Added to cart");
        })
        .catch(function () { toast("Could not add — please try again"); })
        .finally(function () { if (btn) btn.disabled = false; });
    });

    document.addEventListener("keydown", function (e) { if (e.key === "Escape") { openDrawer(false); openLocation(false); openItem(false); openSearch(false); openMenuSearch(false); } });
  }

  /* ---------- admin data tables: filter + pagination ---------- */
  function enhanceTables() {
    document.querySelectorAll("table[data-table]").forEach(function (table) {
      var tbody = table.tBodies[0];
      if (!tbody || table.dataset.enhanced) return;
      table.dataset.enhanced = "1";
      var pageSize = parseInt(table.dataset.pageSize, 10) || 10;
      var rows = Array.prototype.filter.call(tbody.rows, function (r) {
        return !(r.cells.length === 1 && r.cells[0].hasAttribute("colspan"));  // skip empty-state row
      });
      if (!rows.length) return;
      var host = table.closest(".ok-card") || table;
      var colCount = (table.tHead && table.tHead.rows[0]) ? table.tHead.rows[0].cells.length : rows[0].cells.length;
      var st = { q: "", page: 1 };

      var bar = document.createElement("div");
      bar.className = "flex items-center gap-3 mb-3";
      bar.innerHTML = '<div class="flex items-center gap-2 ok-input py-1.5 max-w-xs"><i class="fa-solid fa-magnifying-glass text-slate"></i>' +
        '<input type="search" class="w-full bg-transparent focus:outline-none text-sm" placeholder="Filter this table…"></div>' +
        '<span class="text-xs text-slate" data-count></span>';
      var input = bar.querySelector("input"), countEl = bar.querySelector("[data-count]");
      host.parentNode.insertBefore(bar, host);

      var pager = document.createElement("div");
      pager.className = "flex flex-wrap items-center justify-between gap-3 mt-3 text-sm";
      host.parentNode.insertBefore(pager, host.nextSibling);

      var noMatch = document.createElement("tr");
      var td = document.createElement("td");
      td.colSpan = colCount; td.className = "p-6 text-center text-slate"; td.textContent = "No matches.";
      noMatch.appendChild(td); noMatch.style.display = "none"; tbody.appendChild(noMatch);

      function pbtn(label, page, disabled, active) {
        var b = document.createElement("button");
        b.type = "button"; b.className = "tbl-pagebtn" + (active ? " is-active" : "");
        b.innerHTML = label; b.disabled = !!disabled;
        if (!disabled && !active) b.addEventListener("click", function () { st.page = page; render(); });
        return b;
      }
      function render() {
        var q = st.q.toLowerCase().trim();
        var matched = q ? rows.filter(function (r) { return r.textContent.toLowerCase().indexOf(q) !== -1; }) : rows;
        var total = matched.length, pages = Math.max(1, Math.ceil(total / pageSize));
        if (st.page > pages) st.page = pages;
        var start = (st.page - 1) * pageSize, end = start + pageSize;
        rows.forEach(function (r) { r.style.display = "none"; });
        matched.slice(start, end).forEach(function (r) { r.style.display = ""; });
        noMatch.style.display = total ? "none" : "";
        countEl.textContent = total + (total === 1 ? " result" : " results");
        pager.innerHTML = "";
        if (pages > 1) {
          pager.style.display = "flex";
          var info = document.createElement("span"); info.className = "text-slate";
          info.textContent = "Showing " + (total ? start + 1 : 0) + "–" + Math.min(end, total) + " of " + total;
          var nav = document.createElement("div"); nav.className = "flex items-center gap-1";
          nav.appendChild(pbtn("‹", st.page - 1, st.page === 1));
          for (var i = 1; i <= pages; i++) {
            if (pages > 7 && i > 1 && i < pages && Math.abs(i - st.page) > 1) {
              if (i === 2 || i === pages - 1) { var el = document.createElement("span"); el.textContent = "…"; el.className = "px-1 text-slate"; nav.appendChild(el); }
              continue;
            }
            nav.appendChild(pbtn(String(i), i, false, i === st.page));
          }
          nav.appendChild(pbtn("›", st.page + 1, st.page === pages));
          pager.appendChild(info); pager.appendChild(nav);
        } else { pager.style.display = "none"; }
      }
      input.addEventListener("input", function () { st.q = input.value; st.page = 1; render(); });
      render();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    hydratePlaceholders(document);
    wire();
    initReadMore(document);
    // Admin tables are enhanced by DataTables (loaded in the admin layout).
  });
  window.addEventListener("resize", function () { initReadMore(document); });

  /* ---------- lightweight hover tooltip (tippy-style) for [data-tip] ---------- */
  (function () {
    var tip = null, host = null;
    function place(target) {
      if (!tip) return;
      var r = target.getBoundingClientRect(), tw = tip.offsetWidth, th = tip.offsetHeight;
      var margin = 8, pad = 8;
      var left = r.left + window.scrollX + r.width / 2 - tw / 2;
      left = Math.max(window.scrollX + pad, Math.min(left, window.scrollX + document.documentElement.clientWidth - tw - pad));
      var top = r.top + window.scrollY - th - margin, placeName = "top";
      if (r.top - th - margin < 0) { top = r.bottom + window.scrollY + margin; placeName = "bottom"; }
      tip.style.top = top + "px"; tip.style.left = left + "px";
      tip.setAttribute("data-place", placeName);
      // arrow points at the trigger's centre
      var arrow = r.left + window.scrollX + r.width / 2 - left;
      tip.style.setProperty("--tip-arrow", Math.max(12, Math.min(arrow, tw - 12)) + "px");
    }
    function show(target) {
      var text = target.getAttribute("data-tip");
      if (!text) return;
      hide();
      host = target;
      tip = document.createElement("div");
      tip.className = "ok-tip";
      tip.textContent = text;
      document.body.appendChild(tip);
      place(target);
      requestAnimationFrame(function () { if (tip) tip.classList.add("is-visible"); });
    }
    function hide() { if (tip) { tip.remove(); tip = null; host = null; } }
    document.addEventListener("mouseover", function (e) { var t = e.target.closest("[data-tip]"); if (t && t !== host) show(t); });
    document.addEventListener("mouseout", function (e) { var t = e.target.closest("[data-tip]"); if (t && host === t && !t.contains(e.relatedTarget)) hide(); });
    document.addEventListener("focusin", function (e) { var t = e.target.closest("[data-tip]"); if (t) show(t); });
    document.addEventListener("focusout", hide);
    window.addEventListener("scroll", function () { if (host) place(host); }, true);
    window.addEventListener("resize", hide);
  })();

  // ── Hero carousel ──────────────────────────────────────────────────────
  // Runs on any page that has #heroCarousel (section home OR a builder page).
  // Robust against tab backgrounding: setInterval keeps firing while a tab is
  // hidden, but CSS transitions + transitionend pause — that used to let the
  // slide counter run past the last slide and leave the hero on an empty
  // (black) frame. We skip advancing while hidden and self-correct on return.
  (function initHeroCarousel() {
    function start() {
      var root = document.getElementById("heroCarousel");
      if (!root || root._heroInit) return;
      var track = root.querySelector("[data-track]");
      if (!track) return;
      var n = track.children.length;
      if (n < 2) return;
      root._heroInit = true;
      var i = 0;
      track.appendChild(track.children[0].cloneNode(true));  // clone 1st for seamless wrap
      root.addEventListener("scroll", function () { root.scrollLeft = 0; });

      function snapToStart() {
        track.style.transition = "none";
        track.style.transform = "translateX(0%)";
        void track.offsetWidth;
        track.style.transition = "";
        i = 0;
      }
      track.addEventListener("transitionend", function (e) {
        if (e.propertyName === "transform" && i >= n) snapToStart();
      });
      document.addEventListener("visibilitychange", function () {
        if (!document.hidden && i > n) snapToStart();  // returned from background in a bad state
      });
      setInterval(function () {
        if (document.hidden) return;   // never advance while the tab is hidden
        if (i >= n) snapToStart();     // on the clone → reset before advancing
        i++;
        track.style.transform = "translateX(-" + (i * 100) + "%)";
      }, 8000);
    }
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
    else start();
  })();

  window.OK = { toast: toast, hydratePlaceholders: hydratePlaceholders, placeholder: makePlaceholder, icons: function () {}, openLocation: function () { openLocation(true); }, selectStore: selectStore, openItemModal: function (slug) { loadItem(slug); }, showModal: showModal };
})();
