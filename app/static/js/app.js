/* =========================================================
   OK Smashed Burger | front-end interactions (Flask build)
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
  function isMenuMobileViewport() {
    return !!(window.matchMedia && window.matchMedia("(max-width: 767px)").matches);
  }

  /** Sticky chrome above menu category sections (mobile vs desktop). */
  function menuCategoryScrollOffset() {
    var mobile = isMenuMobileViewport();
    var gap = mobile ? 6 : 12;
    var total = gap;
    var hdr = document.getElementById("okHeader");
    if (hdr) total += hdr.getBoundingClientRect().height;
    if (mobile) {
      var promo = document.querySelector(".ok-mob-promo-strip");
      if (promo) {
        var pr = promo.getBoundingClientRect();
        if (pr.height > 0 && pr.bottom > 0) total += pr.height;
      }
    }
    var stick = document.querySelector(".ok-menu-stick");
    if (stick) total += stick.getBoundingClientRect().height;
    return total;
  }

  function scrollToMenuSection(el) {
    if (!el) return;
    var offset = menuCategoryScrollOffset();
    var rect = el.getBoundingClientRect();
    var startY = window.scrollY || window.pageYOffset;
    var y = startY + rect.top - offset;
    var maxY = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
    y = Math.max(0, Math.min(y, maxY));

    if (isMenuMobileViewport()) {
      // Last categories (e.g. Dessert): never snap to page bottom / footer.
      if (y >= maxY - 4) {
        var want = startY + rect.top - offset;
        if (rect.top >= offset - 8 && rect.top <= offset + 48) return;
        y = Math.min(want, maxY);
        if (want > maxY && rect.top < window.innerHeight * 0.85) {
          y = Math.max(0, Math.min(startY + rect.top - offset, maxY));
        }
      }
    }

    var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      window.scrollTo(0, y);
      return;
    }
    animateScrollTo(y, isMenuMobileViewport() ? 480 : 680);
  }

  function smoothScrollToEl(el) {
    if (!el) return;
    if (el.hasAttribute("data-menu-section")) {
      scrollToMenuSection(el);
      return;
    }
    var y = window.scrollY + el.getBoundingClientRect().top - stickyOffset();
    animateScrollTo(y, 900);
  }

  function initAccountNav() {
    var nav = document.querySelector(".ok-account-nav");
    if (!nav) return;
    var onAccount = !!document.querySelector("[data-account-nav-page]");
    var sections = ["addresses", "profile"];

    function scrollerEl() {
      return nav.closest(".ok-account-nav-shell") || nav;
    }

    function revealTab(link) {
      if (!link || window.matchMedia("(min-width: 992px)").matches) return;
      var scroller = scrollerEl();
      var pad = 12;
      var peek = 56;
      var max = Math.max(0, scroller.scrollWidth - scroller.clientWidth);
      var linkLeft = link.offsetLeft;
      if (scroller !== nav) {
        linkLeft = link.getBoundingClientRect().left - scroller.getBoundingClientRect().left + scroller.scrollLeft;
      }
      var next = link.nextElementSibling;
      while (next && !next.classList.contains("ok-account-nav__link")) next = next.nextElementSibling;
      var left = linkLeft - pad;
      if (next) {
        var showNext = linkLeft + link.offsetWidth + peek - scroller.clientWidth;
        if (showNext > scroller.scrollLeft) left = Math.min(max, showNext);
        else if (linkLeft < scroller.scrollLeft + pad) left = Math.max(0, linkLeft - pad);
      } else {
        left = Math.min(max, linkLeft + link.offsetWidth + pad - scroller.clientWidth);
      }
      scroller.scrollTo({ left: Math.max(0, left), behavior: "smooth" });
    }

    function setActiveTab(tab) {
      var activeLink = null;
      nav.querySelectorAll(".ok-account-nav__link").forEach(function (link) {
        var on = !!(tab && link.dataset.accountTab === tab);
        link.classList.toggle("is-active", on);
        if (on) {
          link.setAttribute("aria-current", "page");
          activeLink = link;
        } else {
          link.removeAttribute("aria-current");
        }
      });
      if (activeLink) requestAnimationFrame(function () { revealTab(activeLink); });
    }

    function tabFromHash() {
      var hash = (location.hash || "").replace("#", "");
      return sections.indexOf(hash) >= 0 ? hash : "";
    }

    nav.addEventListener("click", function (e) {
      var link = e.target.closest(".ok-account-nav__link");
      if (!link) return;
      if (onAccount && link.dataset.accountTab) {
        setActiveTab(link.dataset.accountTab);
      }
      requestAnimationFrame(function () { revealTab(link); });
    });

    if (onAccount) {
      setActiveTab(tabFromHash());
      window.addEventListener("hashchange", function () { setActiveTab(tabFromHash()); });
      var hash = tabFromHash();
      if (hash && document.getElementById(hash)) {
        requestAnimationFrame(function () {
          smoothScrollToEl(document.getElementById(hash));
        });
      }
    } else {
      var current = nav.querySelector(".ok-account-nav__link.is-active");
      if (current) requestAnimationFrame(function () { revealTab(current); });
    }
  }

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
     glyph is swapped for the matching Lucide symbol from the inline sprite , 
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

  var OK_PROMO_SUBSCRIBE_TOAST_KEY = "okPromoSubscribeToast";

  function queuePromoSubscribeToast(msg) {
    try {
      if (msg) sessionStorage.setItem(OK_PROMO_SUBSCRIBE_TOAST_KEY, msg);
    } catch (err) {}
  }

  function flushPromoSubscribeToast() {
    try {
      var path = (window.location.pathname || "").replace(/\/+$/, "") || "/";
      if (path !== "/deals") return;
      var msg = sessionStorage.getItem(OK_PROMO_SUBSCRIBE_TOAST_KEY);
      if (!msg) return;
      sessionStorage.removeItem(OK_PROMO_SUBSCRIBE_TOAST_KEY);
      toast(msg);
    } catch (err) {}
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
    if (d.name != null) {
      document.querySelectorAll("[data-store-name]:not([data-deals-page]), [data-pickup-name]").forEach(function (el) { el.textContent = d.name; });
    }
    if (d.address != null) {
      document.querySelectorAll("[data-store-address], [data-pickup-address]").forEach(function (el) { el.textContent = d.address; });
    }
    if (d.phone != null) {
      document.querySelectorAll("[data-pickup-phone]").forEach(function (el) { el.textContent = d.phone; });
      document.querySelectorAll("[data-pickup-phone-wrap]").forEach(function (el) {
        el.classList.toggle("d-none", !d.phone);
      });
    }
    highlightStore(_storeSlug);
    // Session is saved only after select-store returns (detail.ok). Refresh the
    // deals grid then so it matches the newly chosen location.
    if (d.ok && document.querySelector("[data-deals-page]")) refreshDealsPage(d);
  });

  var _dealsRefreshSeq = 0;

  function refreshDealsPage(storeDetail) {
    var page = document.querySelector("[data-deals-page]");
    if (!page) return;
    var root = document.getElementById("deals-grid-root");
    if (!root) return;
    var label = document.getElementById("deals-store-label");
    if (label && storeDetail && storeDetail.name) label.textContent = "Offers at " + storeDetail.name;
    var seq = ++_dealsRefreshSeq;
    var slug = (storeDetail && storeDetail.slug) || _storeSlug || "";
    var url = "/deals/partial";
    if (slug) url += "?store=" + encodeURIComponent(slug);
    fetch(url, {
      credentials: "same-origin",
      cache: "no-store",
      headers: { "X-Requested-With": "fetch" },
    })
      .then(function (r) {
        if (!r.ok) throw new Error("deals partial failed");
        return r.text();
      })
      .then(function (html) {
        if (seq !== _dealsRefreshSeq) return;
        root.innerHTML = html;
        var countEl = document.getElementById("deals-offer-count");
        if (countEl) {
          var n = root.querySelectorAll(".ok-dealcard").length;
          countEl.textContent = n + " offer" + (n === 1 ? "" : "s") + " available";
        }
        if (typeof hydratePlaceholders === "function") hydratePlaceholders(root);
        if (typeof modernIcons === "function") modernIcons(root);
      })
      .catch(function () {
        if (seq !== _dealsRefreshSeq) return;
        if ((location.pathname || "").replace(/\/$/, "") === "/deals") location.reload();
      });
  }

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
          if (d.cart_unavailable && d.cart_unavailable.length) {
            var msg = "These items aren't available at " + (d.name || "this location") + ": "
              + d.cart_unavailable.join(", ")
              + ". Please choose items from this location's menu.";
            if (window.OK && OK.toast) OK.toast(msg);
            else alert(msg);
          }
          // Menu is rendered per store on the server | reload once the session
          // store is saved. Deals refresh via ok:store + refreshDealsPage().
          var path = (location.pathname || "").replace(/\/$/, "");
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

  function ensureLocAutocomplete(done) {
    var roots = document.querySelectorAll("[data-loc-autocomplete]");
    if (!roots.length) { if (done) done(); return; }
    var mapsKey = roots[0].getAttribute("data-maps-key");
    if (!mapsKey) { if (done) done(); return; }
    function ready() {
      if (window.OK && OK.initLocationPicker) {
        document.querySelectorAll("[data-loc-autocomplete]").forEach(function (root) {
          OK.initLocationPicker(root);
        });
      }
      if (done) done();
    }
    if (document.querySelector('script[src*="address-autocomplete.js"]') && window.OK && OK.initLocationPicker) {
      if (window.OK.preloadMaps) OK.preloadMaps(mapsKey).then(ready);
      else ready();
      return;
    }
    var s = document.createElement("script");
    s.src = "/static/js/address-autocomplete.js";
    s.onload = ready;
    s.onerror = function () { if (done) done(); };
    document.head.appendChild(s);
  }

  function openLocation(open) {
    var m = document.getElementById("locModal"), b = document.getElementById("locBackdrop");
    if (!m) return;
    if (open && typeof locStep === "function") locStep(1);  // always start at "find a store"
    if (open && _storeSlug) highlightStore(_storeSlug);      // reflect the current choice
    if (open) {
      ensureLocAutocomplete(function () {
        var inp = document.getElementById("locZip");
        if (inp) inp.focus();
      });
    }
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
    // the sheet is its own request, so edit mode has to travel with it , 
    // otherwise its labels come back as plain text and cannot be clicked
    fetch("/item/" + encodeURIComponent(slug) + "/modal"
            + (document.getElementById("okIeBar") ? "?edit=1" : ""),
          { headers: { "X-Requested-With": "fetch" } })
      .then(function (r) { return r.ok ? r.text() : null; })
      .then(function (html) { body.innerHTML = html !== null ? html : '<p class="py-8 text-center text-slate">Could not load this item.</p>'; initReadMore(body); ; if (window.okIeRefresh) window.okIeRefresh(body); })
      .catch(function () { body.innerHTML = '<p class="py-8 text-center text-slate">Could not load this item.</p>'; });
  }

  /* ---------- read more / read less | inline expand / collapse ---------- */
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
    if (document.body.dataset.lockStore) return;
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
    selectStore(card.dataset.locPick, {
      name: card.dataset.locName,
      city: card.dataset.city,
      zip: card.dataset.zip,
      address: card.dataset.address,
      phone: card.dataset.phone || "",
      open_now: card.dataset.openNow === "1",
      can_order: card.dataset.canOrder === "1",
      scheduling_open: card.dataset.schedulingOpen === "1",
      avg_prep_minutes: card.dataset.avgPrep ? parseInt(card.dataset.avgPrep, 10) : undefined,
      today_hours: card.dataset.todayHours || "",
    });
    // the location is the thing the visitor came here to change, so close on
    // pick rather than pushing them through a second step
    openLocation(false);
    locStep(1);
  }
  function locMiles(la1, lo1, la2, lo2) {
    var R = 3958.8, r = Math.PI / 180;
    var dLa = (la2 - la1) * r, dLo = (lo2 - lo1) * r;
    var a = Math.sin(dLa / 2) * Math.sin(dLa / 2) +
      Math.cos(la1 * r) * Math.cos(la2 * r) * Math.sin(dLo / 2) * Math.sin(dLo / 2);
    return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }
  function locStoreCoords(card) {
    var la = parseFloat(card.dataset.lat), lo = parseFloat(card.dataset.lng);
    if (isNaN(la) || isNaN(lo)) return { lat: NaN, lng: NaN };
    if (Math.abs(la) > 90 && Math.abs(lo) <= 90) return { lat: lo, lng: la };
    return { lat: la, lng: lo };
  }
  function locSortPageByDistance(userLat, userLng, cards) {
    var list = document.getElementById("locList");
    if (!list || isNaN(userLat) || isNaN(userLng)) return null;
    var nearest = null, nearestDist = Infinity;
    cards.forEach(function (c) {
      var sc = locStoreCoords(c);
      var lbl = c.querySelector("[data-distance-label]");
      if (isNaN(sc.lat) || isNaN(sc.lng)) {
        delete c.dataset.dist;
        if (lbl) { lbl.textContent = ""; lbl.style.display = "none"; }
        return;
      }
      var d = locMiles(userLat, userLng, sc.lat, sc.lng);
      c.dataset.dist = String(d);
      if (lbl) {
        lbl.textContent = d < 0.05 ? "You're here" : d.toFixed(1) + " mi away";
        lbl.style.display = "";
      }
      if (d < nearestDist) { nearestDist = d; nearest = c; }
    });
    cards.slice().sort(function (a, b) {
      return (parseFloat(a.dataset.dist) || Infinity) - (parseFloat(b.dataset.dist) || Infinity);
    }).forEach(function (c) { list.appendChild(c); });
    return nearest;
  }
  function locSearchContext() {
    var pageRoot = document.getElementById("locPageFind");
    if (pageRoot) {
      return {
        onPage: true,
        el: pageRoot.querySelector("[data-loc-search]"),
        cards: Array.prototype.slice.call(document.querySelectorAll("#locList [data-loc]")),
        mapsRoot: pageRoot.querySelector("[data-loc-autocomplete]") || pageRoot,
      };
    }
    var m = document.getElementById("locModal");
    return {
      onPage: false,
      el: document.getElementById("locZip"),
      cards: m ? Array.prototype.slice.call(m.querySelectorAll("[data-loc-pick]")) : [],
      mapsRoot: m ? m.querySelector("[data-loc-autocomplete]") : null,
    };
  }

  function locRevealOnPage(card) {
    if (!card) return;
    card.scrollIntoView({ behavior: "smooth", block: "center" });
    card.classList.add("ok-ring-2", "ring-okyellow");
    setTimeout(function () {
      card.classList.remove("ok-ring-2", "ring-okyellow");
    }, 3200);
  }

  function locFind() {
    var ctx = locSearchContext();
    var el = ctx.el;
    var zip = (el && el.dataset.locZip) || ((el && el.value) || "").trim();
    if (!zip && !(el && el.dataset.locLat && el.dataset.locLng)) { if (el) el.focus(); return; }
    var cards = ctx.cards;
    if (!cards.length) return;
    var lat = el && parseFloat(el.dataset.locLat);
    var lng = el && parseFloat(el.dataset.locLng);
    if (!isNaN(lat) && !isNaN(lng)) {
      var nearest = ctx.onPage
        ? locSortPageByDistance(lat, lng, cards)
        : (function () {
          var best = null, bestDist = Infinity;
          cards.forEach(function (c) {
            var sc = locStoreCoords(c);
            if (isNaN(sc.lat) || isNaN(sc.lng)) return;
            var d = locMiles(lat, lng, sc.lat, sc.lng);
            if (d < bestDist) { bestDist = d; best = c; }
          });
          return best;
        })();
      if (nearest) {
        if (ctx.onPage) locRevealOnPage(nearest);
        else locPick(nearest);
        return;
      }
    }
    var q = (el && el.dataset.locQuery) || zip.toLowerCase(), best = null;
    cards.forEach(function (c) { if (!best && (c.dataset.zips || "").split(",").indexOf(zip) !== -1) best = c; });
    if (!best) cards.forEach(function (c) { if (!best && (c.dataset.zip || "") === zip) best = c; });
    if (!best) cards.forEach(function (c) { if (!best && (c.dataset.search || "").indexOf(q) !== -1) best = c; });
    if (!best && /^\d{3}/.test(zip)) cards.forEach(function (c) { if (!best && (c.dataset.zip || "").slice(0, 3) === zip.slice(0, 3)) best = c; });
    if (!best) { if (window.OK && OK.toast) OK.toast("No store matches that address"); return; }
    if (ctx.onPage) locRevealOnPage(best);
    else locPick(best);
  }
  function locGeoFail(msg) {
    if (window.OK && OK.toast) OK.toast(msg);
    else alert(msg);
  }
  function locUseCurrentPosition(btn) {
    if (!navigator.geolocation) {
      locGeoFail("Location is not available in this browser.");
      return;
    }
    var pageFind = document.getElementById("locPageFind");
    var root = (btn && btn.closest("[data-loc-autocomplete]"))
      || (pageFind && btn && pageFind.contains(btn) ? pageFind : null);
    var el = (root && root.querySelector("[data-loc-search]")) || document.getElementById("locZip");
    if (!el) return;
    var original = btn ? btn.innerHTML : "";
    if (btn) {
      btn.setAttribute("aria-busy", "true");
      btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Locating…';
    }
    ensureLocAutocomplete(function () {
    navigator.geolocation.getCurrentPosition(function (pos) {
      var lat = pos.coords.latitude, lng = pos.coords.longitude;
      el.dataset.locLat = String(lat);
      el.dataset.locLng = String(lng);
      delete el.dataset.locZip;
      el.dataset.locQuery = "your location";
      function done(label) {
        if (label) el.value = label;
        if (btn) { btn.removeAttribute("aria-busy"); btn.innerHTML = original; }
        locFind();
      }
      var mapsRoot = (root && root.getAttribute("data-maps-key") ? root : null)
        || document.querySelector("[data-loc-autocomplete][data-maps-key]");
      var mapsKey = mapsRoot && mapsRoot.getAttribute("data-maps-key");
      if (mapsKey && window.OK && OK.reverseGeocode) {
        OK.reverseGeocode(mapsKey, lat, lng).then(function (label) {
          done(label || "Your location");
        }).catch(function () { done("Your location"); });
        return;
      }
      done("Your location");
    }, function () {
      if (btn) { btn.removeAttribute("aria-busy"); btn.innerHTML = original; }
      locGeoFail("Could not get your location. Please allow access and try again.");
    }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 });
    });
  }

  function wire() {
    modernIcons();

    document.addEventListener("ok-loc-search", function () { locFind(); });
    ensureLocAutocomplete();
    function bindLocEnter(inp) {
      if (!inp || inp._okLocEnter) return;
      inp._okLocEnter = true;
      inp.addEventListener("keydown", function (e) {
        if (e.key === "Enter") { e.preventDefault(); locFind(); }
      });
    }
    bindLocEnter(document.getElementById("locZip"));
    bindLocEnter(document.getElementById("locSearch"));

    var hd = document.getElementById("okHeader");
    if (hd) window.addEventListener("scroll", function () { hd.classList.toggle("is-scrolled", window.scrollY > 8); });

    var searchBox = document.getElementById("okSearch");
    function openSearch(open) {
      if (!searchBox) return;
      searchBox.classList.toggle("is-open", open);
      if (open) { var i = searchBox.querySelector("[data-search-input]"); if (i) setTimeout(function () { i.focus(); }, 40); }
    }
    if (searchBox) searchBox.addEventListener("focusout", function (e) { if (!searchBox.contains(e.relatedTarget)) openSearch(false); });

    // Checkout: address fields are required for delivery only.
    (function () {
      var row = document.querySelector("[data-address-row]");
      if (!row) return;
      var fields = row.querySelectorAll("[data-address-field]");
      var radios = document.querySelectorAll('input[name="order_type"]');
      function sync() {
        var picked = document.querySelector('input[name="order_type"]:checked');
        var delivery = !picked || picked.value === "delivery";
        fields.forEach(function (el) {
          if (el.hasAttribute("data-addr-required")) {
            if (delivery) el.setAttribute("required", "");
            else el.removeAttribute("required");
          }
        });
        row.classList.toggle("d-none", !delivery);
      }
      fields.forEach(function (el) {
        if (el.hasAttribute("required")) el.setAttribute("data-addr-required", "");
      });
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

    // ── FAQ help-center search + topic chips ─────────────────────────────
    var faqRoot = document.querySelector("[data-faq-page]");
    var faqSearchInput = faqRoot ? faqRoot.querySelector("[data-faq-search]") : null;
    var faqEmpty = faqRoot ? faqRoot.querySelector("[data-faq-empty]") : null;
    var faqGroupFilter = "";

    function applyFaqView() {
      if (!faqRoot) return;
      var items = faqRoot.querySelectorAll("[data-faq-group]");
      var chips = faqRoot.querySelectorAll("[data-faq-filter]");
      var q = (faqSearchInput ? faqSearchInput.value : "").trim().toLowerCase();
      var shown = 0;
      var matchingGroups = {};

      items.forEach(function (item) {
        var blob = (item.getAttribute("data-search") || "").toLowerCase();
        if (!blob) {
          var qEl = item.querySelector(".acc-q");
          var aEl = item.querySelector(".acc-a");
          blob = ((qEl ? qEl.textContent : "") + " " + (aEl ? aEl.textContent : "")).toLowerCase();
        }
        var group = item.getAttribute("data-faq-group") || "";
        var hitSearch = !q || blob.indexOf(q) !== -1;
        var hitGroup = !faqGroupFilter || group === faqGroupFilter;
        var show = q ? hitSearch : hitGroup;

        item.style.display = show ? "" : "none";
        if (show) shown++;
        if (q) {
          item.classList.toggle("is-open", hitSearch);
          if (hitSearch) matchingGroups[group] = true;
        }
      });

      chips.forEach(function (chip) {
        var g = chip.getAttribute("data-faq-filter");
        if (q) {
          chip.classList.toggle("is-active", g !== "" && !!matchingGroups[g]);
        } else {
          chip.classList.toggle("is-active", g === faqGroupFilter);
        }
      });

      if (faqEmpty) faqEmpty.classList.toggle("d-none", shown !== 0);
    }

    if (faqSearchInput) {
      faqSearchInput.addEventListener("input", applyFaqView);
      faqSearchInput.addEventListener("keydown", function (e) { if (e.key === "Enter") e.preventDefault(); });
    }
    if (faqRoot) {
      document.addEventListener("click", function (e) {
        if (e.target.closest("[data-faq-search-btn]")) {
          e.preventDefault();
          applyFaqView();
          if (faqSearchInput) faqSearchInput.focus();
        }
      });
    }

    if (catbar) {
      catbar.addEventListener("mouseleave", function () { openMenuSearch(false); });
      catbar.addEventListener("focusout", function (e) { if (!catbar.contains(e.relatedTarget)) openMenuSearch(false); });
    }

    document.addEventListener("click", function (e) {
      var openT = e.target.closest("[data-open]"), closeT = e.target.closest("[data-close]");
      if (openT) {
        e.preventDefault();
        if (openT.dataset.open === "drawer") openDrawer(true);
        if (openT.dataset.open === "location") {
          if (document.body.dataset.lockStore) return;
          _locNext = openT.getAttribute("data-loc-next") || null;
          openLocation(true);
        }
      }
      if (closeT) { if (closeT.dataset.close === "drawer") openDrawer(false); if (closeT.dataset.close === "location") { _locNext = null; openLocation(false); } if (closeT.dataset.close === "item") openItem(false); }

      // read more / less | handle BEFORE data-item so it doesn't open the modal
      var rmT = e.target.closest("[data-rm-toggle]");
      if (rmT) { e.preventDefault(); e.stopPropagation(); toggleReadMore(rmT); return; }

      var itemT = e.target.closest("[data-item]");
      if (itemT) { e.preventDefault(); loadItem(itemT.dataset.item); return; }

      var locPickEl = e.target.closest("[data-loc-pick]");
      if (locPickEl) { e.preventDefault(); locPick(locPickEl); return; }
      if (e.target.closest("[data-loc-find]")) { e.preventDefault(); locFind(); return; }
      var locGeo = e.target.closest("[data-loc-geo]");
      if (locGeo) { e.preventDefault(); locUseCurrentPosition(locGeo); return; }
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
        if (row.dataset.required === "1" && n > 0) row.classList.remove("is-invalid");
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
      if (chip && !chip.hasAttribute("data-faq-filter")) {
        if (chip.dataset.multi === undefined) chip.parentElement.querySelectorAll(".chip").forEach(function (c) { c.classList.remove("is-active"); });
        chip.classList.toggle("is-active");
        recalcItem(chip.closest("[data-item-form]"));
      }

      // order-type segmented toggle (delivery / pickup), switches live, no reload
      var otBtn = e.target.closest("[data-ordertype]");
      if (otBtn) {
        if (otBtn.disabled || otBtn.getAttribute("aria-disabled") === "true") return;
        var otGroup = otBtn.closest("[data-ordertype-group]");
        var otVal = otBtn.getAttribute("data-ordertype");
        function styleOrderTypeButtons(activeBtn) {
          if (!otGroup) return;
          var cartPill = otGroup.closest("[data-cart-summary]");
          otGroup.querySelectorAll("[data-ordertype]").forEach(function (x) {
            var on = x === activeBtn;
            x.classList.toggle("is-active", on);
            if (cartPill) {
              x.classList.toggle("bg-ink", on);
              x.classList.toggle("text-white", on);
              x.classList.toggle("ok-shadow-md", on);
              x.classList.toggle("text-ink", !on);
              x.classList.remove("text-muted-warm");
            } else {
              x.classList.toggle("text-muted-warm", !on);
            }
          });
        }
        styleOrderTypeButtons(otBtn);
        fetch("/api/order-type/" + encodeURIComponent(otVal), { credentials: "same-origin" })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (!d || !d.ok) return;
            if (d.cart && window.OK && OK.updateCartSummary) OK.updateCartSummary(d.cart);
          })
          .catch(function () {});
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

      // FAQ category chips | filter by topic, or highlight topics during search.
      var faqChip = e.target.closest("[data-faq-filter]");
      if (faqChip) {
        faqGroupFilter = faqChip.getAttribute("data-faq-filter") || "";
        if (faqSearchInput) faqSearchInput.value = "";
        applyFaqView();
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
      var invalid = false;
      form.querySelectorAll("[data-addon][data-required]").forEach(function (row) {
        var n = parseInt((row.querySelector("[data-acount]") || {}).textContent, 10) || 0;
        var bad = n < 1;
        row.classList.toggle("is-invalid", bad);
        if (bad) invalid = true;
      });
      if (invalid) return;
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
        .catch(function () { toast("Could not add, please try again"); })
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

  var OK_DEALS_PROMO_DISMISS_MS = 15 * 60 * 1000;

  function okDealsPromoSubKey(dismissKey) {
    return dismissKey + ":subscribed";
  }

  function okDealsPromoSubscribedThisSession(dismissKey) {
    try {
      return sessionStorage.getItem(okDealsPromoSubKey(dismissKey)) === "1";
    } catch (err) {
      return false;
    }
  }

  function okDealsPromoMarkSubscribed(dismissKey) {
    try {
      sessionStorage.setItem(okDealsPromoSubKey(dismissKey), "1");
    } catch (err) {}
  }

  function okDealsPromoDismissedRecently(storageKey) {
    try {
      var raw = sessionStorage.getItem(storageKey);
      if (!raw) return false;
      var ts = raw === "1" ? 0 : parseInt(raw, 10);
      if (!ts || isNaN(ts)) {
        sessionStorage.removeItem(storageKey);
        return false;
      }
      if (Date.now() - ts < OK_DEALS_PROMO_DISMISS_MS) return true;
      sessionStorage.removeItem(storageKey);
      return false;
    } catch (err) {
      return false;
    }
  }

  function okDealsPromoShouldSkip(dismissKey) {
    if (okDealsPromoSubscribedThisSession(dismissKey)) return true;
    return okDealsPromoDismissedRecently(dismissKey);
  }

  function okDealsPromoDismissKeyForSlug(slug) {
    return "okDealsPromoDismiss" + (slug ? ":" + slug : "");
  }

  var _promoAfterLocationSlug = null;
  var _promoBlockedUntilStorePick = false;

  function locModalOpenForPromo() {
    var m = document.getElementById("locModal");
    if (!m) return false;
    if (m.classList.contains("is-open")) return true;
    return m.style.visibility === "visible" && m.style.pointerEvents !== "none";
  }

  function openDealsPromoPopElement(pop, delayMs, afterStorePick) {
    if (!pop) return;
    if (!afterStorePick && _promoBlockedUntilStorePick) return;
    var wait = delayMs == null ? 400 : delayMs;
    function go() {
      if (!afterStorePick && _promoBlockedUntilStorePick) return;
      if (locModalOpenForPromo()) {
        setTimeout(go, 120);
        return;
      }
      var sk = okDealsPromoDismissKeyForSlug(_storeSlug || pop.getAttribute("data-store-slug") || "");
      if (okDealsPromoShouldSkip(sk)) return;
      setTimeout(function () {
        pop.removeAttribute("hidden");
        pop.setAttribute("aria-hidden", "false");
        requestAnimationFrame(function () {
          requestAnimationFrame(function () { pop.classList.add("is-open"); });
        });
        lockScroll(true);
      }, wait);
    }
    go();
  }

  function ensureDealsPromoPopAfterStorePick(detail) {
    if (!detail || !detail.slug) return;
    if (_promoAfterLocationSlug === detail.slug) return;
    _promoAfterLocationSlug = detail.slug;
    _promoBlockedUntilStorePick = false;
    document.body.setAttribute("data-needs-location", "0");

    function mountAndOpen(node) {
      if (!node) return;
      node.setAttribute("data-store-slug", detail.slug);
      if (!node._okPromoInit) initDealsPromoPopup();
      initPromoSubscribeAjax();
      openDealsPromoPopElement(node, 300, true);
    }

    var pop = document.getElementById("okDealsPromoPopup");
    if (pop) {
      mountAndOpen(pop);
      return;
    }
    fetch("/api/deals-promo-popup", {
      credentials: "same-origin",
      cache: "no-store",
      headers: { "X-Requested-With": "fetch" },
    })
      .then(function (r) {
        if (r.status === 204) return "";
        if (!r.ok) return "";
        return r.text();
      })
      .then(function (html) {
        if (!(html || "").trim()) return;
        var wrap = document.createElement("div");
        wrap.innerHTML = html.trim();
        mountAndOpen(wrap.firstElementChild);
      })
      .catch(function () {});
  }

  function okDealsPromoCloseUi(pop) {
    if (!pop) return;
    pop.classList.remove("is-open");
    pop.setAttribute("aria-hidden", "true");
    lockScroll(false);
    setTimeout(function () {
      if (!pop.classList.contains("is-open")) pop.setAttribute("hidden", "");
    }, 300);
  }

  function initDealsPromoPopup() {
    var pop = document.getElementById("okDealsPromoPopup");
    if (!pop || pop._okPromoInit) return;
    pop._okPromoInit = true;
    var isEdit = /(?:\?|&)edit=1(?:&|$)/.test(window.location.search || "");

    function promoDismissKey() {
      var s = _storeSlug || pop.getAttribute("data-store-slug") || "";
      return okDealsPromoDismissKeyForSlug(s);
    }
    function openPop() {
      openDealsPromoPopElement(pop, 0);
    }
    function closePop(remember) {
      pop.classList.remove("is-open");
      pop.setAttribute("aria-hidden", "true");
      lockScroll(false);
      if (remember && !isEdit) {
        try { sessionStorage.setItem(promoDismissKey(), String(Date.now())); } catch (err) {}
      }
      setTimeout(function () {
        if (!pop.classList.contains("is-open")) pop.setAttribute("hidden", "");
      }, 300);
    }

    pop.addEventListener("click", function (e) {
      if (e.target.closest("[data-deals-promo-close]")) {
        e.preventDefault();
        closePop(true);
      }
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && pop.classList.contains("is-open")) closePop(true);
    });

    var shop = pop.querySelector(".ok-offer-modal__shop");
    if (shop && !shop.dataset.okPromoNav) {
      shop.dataset.okPromoNav = "1";
      shop.addEventListener("click", function (e) {
        if (shop.onclick) return;
        var href = shop.getAttribute("href");
        if (!href) return;
        try {
          var dest = new URL(href, window.location.origin);
          if (dest.origin === window.location.origin && dest.pathname === window.location.pathname) {
            e.preventDefault();
            closePop(true);
          }
        } catch (err) {}
      });
    }

    if (isEdit || pop.classList.contains("is-open")) {
      openPop();
      return;
    }

    var autoOnPage = pop.getAttribute("data-promo-auto-open") !== "0";

    if (!autoOnPage) return;

    if (okDealsPromoShouldSkip(promoDismissKey())) return;
    if (locModalOpenForPromo()) {
      setTimeout(function () { openDealsPromoPopElement(pop, 400); }, 200);
      return;
    }
    setTimeout(openPop, 700);
  }

  function initPromoSubscribeAjax() {
    var forms = document.querySelectorAll(".ok-offer-modal__form, form.ok-deals-promo-sub");
    forms.forEach(function (form) {
      if (form._okSubAjax || form.getAttribute("onclick")) return;
      form._okSubAjax = true;
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        var btn = form.querySelector('button[type="submit"], .ok-offer-modal__submit');
        if (btn) btn.disabled = true;
        var fd = new FormData(form);
        fetch(form.getAttribute("action") || "/subscribe", {
          method: "POST",
          body: fd,
          credentials: "same-origin",
          headers: { "X-Requested-With": "XMLHttpRequest" },
        })
          .then(function (res) {
            return res.json().then(function (data) {
              if (!res.ok) throw data;
              return data;
            });
          })
          .then(function (data) {
            var pop = document.getElementById("okDealsPromoPopup");
            var slug = (fd.get("store_slug") || "").toString().trim();
            if (pop) slug = pop.getAttribute("data-store-slug") || slug;
            var sk = okDealsPromoDismissKeyForSlug(slug);
            okDealsPromoMarkSubscribed(sk);

            var msg = (data && data.message) || "You're on the list!";
            form.reset();
            okDealsPromoCloseUi(pop);

            var dest = data && data.redirect;
            if (dest) {
              queuePromoSubscribeToast(msg);
              window.location.assign(dest);
            } else {
              toast(msg);
            }
          })
          .catch(function (err) {
            var msg = (err && err.message) || "Could not subscribe. Try again.";
            toast(msg);
          })
          .finally(function () {
            if (btn) btn.disabled = false;
          });
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    flushPromoSubscribeToast();
    hydratePlaceholders(document);
    wire();
    initReadMore(document);
    initAccountNav();
    initDealsPromoPopup();
    initPromoSubscribeAjax();
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
  // hidden, but CSS transitions + transitionend pause | that used to let the
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

  function updateCartSummary(c) {
    var root = document.querySelector("[data-cart-summary]");
    if (!root || !c) return;
    function money(n) { return "$" + (Number(n) || 0).toFixed(2); }
    var sub = root.querySelector("[data-cart-subtotal]");
    if (sub) sub.textContent = money(c.subtotal);
    var tax = root.querySelector("[data-cart-tax]");
    if (tax) tax.textContent = money(c.tax);
    var taxRate = root.querySelector("[data-cart-tax-rate]");
    if (taxRate) taxRate.textContent = String(Math.round((Number(c.tax_rate) || 0) * 1000) / 10);
    var discRow = root.querySelector("[data-cart-discount-row]");
    var disc = root.querySelector("[data-cart-discount]");
    if (discRow && disc) {
      var dAmt = Number(c.order_discount) || 0;
      discRow.classList.toggle("d-none", dAmt <= 0);
      disc.textContent = "−" + money(dAmt);
    }
    var delRow = root.querySelector("[data-cart-delivery-row]");
    var delFee = root.querySelector("[data-cart-delivery-fee]");
    if (delRow && delFee) {
      var isDel = c.order_type === "delivery";
      delRow.classList.toggle("d-none", !isDel);
      if (isDel) {
        delFee.innerHTML = c.delivery_free
          ? '<span class="text-ok-green">FREE</span>'
          : money(c.delivery_fee);
      }
    }
    var gcRow = root.querySelector("[data-cart-giftcard-row]");
    var gc = root.querySelector("[data-cart-giftcard]");
    if (gcRow && gc) {
      var gAmt = Number(c.giftcard_applied) || 0;
      gcRow.classList.toggle("d-none", gAmt <= 0);
      gc.textContent = "−" + money(gAmt);
    }
    var total = root.querySelector("[data-cart-total]");
    if (total) total.textContent = money(c.total);
  }

  window.OK = { toast: toast, hydratePlaceholders: hydratePlaceholders, placeholder: makePlaceholder, icons: function () {}, openLocation: function () { openLocation(true); }, selectStore: selectStore, refreshDealsPage: refreshDealsPage, openItemModal: function (slug) { loadItem(slug); }, showModal: showModal, updateCartSummary: updateCartSummary };
})();
