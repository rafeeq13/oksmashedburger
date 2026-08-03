/* =========================================================
   OK Smashed Burger — Template runtime
   Injects shared header/footer, generates branded placeholder
   images, loads Font Awesome icons, and wires up demo interactions.
   No backend — this is a layout prototype for client sign-off.
   ========================================================= */
(function () {
  "use strict";

  var NAV = [
    { label: "Menu", href: "menu.html" },
    { label: "Deals", href: "deals.html", hot: true },
    { label: "Rewards", href: "rewards.html" },
    { label: "Gift Cards", href: "gift-cards.html" },
    { label: "Locations", href: "locations.html" }
  ];

  var current = (location.pathname.split("/").pop() || "index.html").toLowerCase();

  // Icon name -> Font Awesome class map (shared with the page markup)
  var ICMAP = {
    "arrow-left":"fa-solid fa-arrow-left","arrow-right":"fa-solid fa-arrow-right","arrow-up":"fa-solid fa-arrow-up","arrow-down":"fa-solid fa-arrow-down",
    "baby":"fa-solid fa-baby","beef":"fa-solid fa-burger","bell":"fa-solid fa-bell","bike":"fa-solid fa-bicycle","briefcase":"fa-solid fa-briefcase",
    "building-2":"fa-solid fa-building","cake":"fa-solid fa-cake-candles","calendar":"fa-solid fa-calendar-days","car":"fa-solid fa-car",
    "check":"fa-solid fa-check","check-check":"fa-solid fa-check-double","check-circle":"fa-solid fa-circle-check","chef-hat":"fa-solid fa-kitchen-set",
    "chevron-down":"fa-solid fa-chevron-down","chevron-right":"fa-solid fa-chevron-right","clock":"fa-solid fa-clock","compass":"fa-solid fa-compass",
    "credit-card":"fa-solid fa-credit-card","cup-soda":"fa-solid fa-glass-water","dollar-sign":"fa-solid fa-dollar-sign","drumstick":"fa-solid fa-drumstick-bite",
    "egg":"fa-solid fa-egg","egg-fried":"fa-solid fa-egg","flame":"fa-solid fa-fire","gift":"fa-solid fa-gift","ham":"fa-solid fa-bacon",
    "hand":"fa-solid fa-hand","heart":"fa-solid fa-heart","help-circle":"fa-solid fa-circle-question","home":"fa-solid fa-house","info":"fa-solid fa-circle-info",
    "layout-dashboard":"fa-solid fa-gauge-high","leaf":"fa-solid fa-leaf","life-buoy":"fa-solid fa-life-ring","lightbulb":"fa-solid fa-lightbulb",
    "link":"fa-solid fa-link","lock":"fa-solid fa-lock","log-out":"fa-solid fa-right-from-bracket","mail":"fa-solid fa-envelope","map":"fa-solid fa-map",
    "map-pin":"fa-solid fa-location-dot","medal":"fa-solid fa-medal","menu":"fa-solid fa-bars","message-circle":"fa-solid fa-comment",
    "navigation":"fa-solid fa-location-arrow","package":"fa-solid fa-box","palette":"fa-solid fa-palette","party-popper":"fa-solid fa-hands-clapping",
    "pencil":"fa-solid fa-pencil","phone":"fa-solid fa-phone","receipt":"fa-solid fa-receipt","salad":"fa-solid fa-bowl-food","search":"fa-solid fa-magnifying-glass",
    "send":"fa-solid fa-paper-plane","shopping-bag":"fa-solid fa-bag-shopping","shopping-basket":"fa-solid fa-basket-shopping","shopping-cart":"fa-solid fa-cart-shopping",
    "sliders-horizontal":"fa-solid fa-sliders","smartphone":"fa-solid fa-mobile-screen-button","sparkles":"fa-solid fa-wand-magic-sparkles","star":"fa-solid fa-star",
    "store":"fa-solid fa-store","tag":"fa-solid fa-tag","target":"fa-solid fa-bullseye","thumbs-up":"fa-solid fa-thumbs-up","trash-2":"fa-solid fa-trash",
    "trophy":"fa-solid fa-trophy","triangle-alert":"fa-solid fa-triangle-exclamation","alert-triangle":"fa-solid fa-triangle-exclamation","truck":"fa-solid fa-truck",
    "user":"fa-solid fa-user","users":"fa-solid fa-users","utensils":"fa-solid fa-utensils","wallet":"fa-solid fa-wallet","wheat":"fa-solid fa-wheat-awn",
    "x":"fa-solid fa-xmark","zap":"fa-solid fa-bolt",
    "apple":"fa-brands fa-apple","facebook":"fa-brands fa-facebook-f","instagram":"fa-brands fa-instagram","twitter":"fa-brands fa-x-twitter","youtube":"fa-brands fa-youtube","music":"fa-brands fa-tiktok"
  };
  // small helper: a Font Awesome icon
  function ic(name, cls) { return '<i class="' + (ICMAP[name] || "fa-solid fa-circle") + (cls ? " " + cls : "") + '"></i>'; }

  // combined height of the sticky bars that pin to the top (header + any sub-bar),
  // using each bar's *pinned* position so it's correct even before it sticks.
  function stickyOffset() {
    var maxBottom = 0;
    document.querySelectorAll('.ok-header, [class*="sticky"]').forEach(function (s) {
      var cs = window.getComputedStyle(s);
      if (cs.position !== "sticky" && cs.position !== "fixed") return;
      var h = s.getBoundingClientRect().height;
      if (h === 0 || h > window.innerHeight * 0.4) return;   // skip hidden / tall sticky panels (sidebars, cards)
      var topVal = parseFloat(cs.top);
      if (isNaN(topVal) || topVal > 150) return;             // only bars that pin in the top region
      var bottom = topVal + h;
      if (bottom > maxBottom) maxBottom = bottom;
    });
    return maxBottom + 0;   // heading sits flush against the sticky bar
  }
  // custom slow, eased scroll (browser's native "smooth" is fixed-speed and quicker)
  function animateScrollTo(toY, duration) {
    var root = document.documentElement;
    var startY = window.scrollY || window.pageYOffset;
    var maxY = Math.max(0, root.scrollHeight - window.innerHeight);
    toY = Math.max(0, Math.min(toY, maxY));
    var dist = toY - startY;
    if (Math.abs(dist) < 2) return;
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) { window.scrollTo(0, toY); return; }
    var prev = root.style.scrollBehavior;
    root.style.scrollBehavior = "auto";   // don't fight the CSS scroll-smooth
    var startT = null;
    function ease(t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; } // easeInOutCubic
    function step(ts) {
      if (startT === null) startT = ts;
      var p = Math.min(1, (ts - startT) / duration);
      window.scrollTo(0, startY + dist * ease(p));
      if (p < 1) requestAnimationFrame(step);
      else root.style.scrollBehavior = prev;
    }
    requestAnimationFrame(step);
  }
  function smoothScrollToEl(el) {
    animateScrollTo(window.scrollY + el.getBoundingClientRect().top - stickyOffset(), 900);
  }

  /* ---------- Font Awesome loader ---------- */
  // Font Awesome renders icons purely via CSS, so no JS re-render step is needed.
  function loadFontAwesome() {
    if (document.getElementById("fa-css")) return;
    var l = document.createElement("link");
    l.id = "fa-css"; l.rel = "stylesheet"; l.crossOrigin = "anonymous";
    l.href = "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.2/css/all.min.css";
    (document.head || document.documentElement).appendChild(l);
  }
  loadFontAwesome();
  function renderIcons() { /* no-op: Font Awesome renders via CSS */ }

  /* ---------- Branded placeholder image generator ---------- */
  // Usage: <img data-ph="Classic Smash" data-ph-type="food" data-ph-ratio="4/3">
  function svgURI(svg) { return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg); }
  var PALETTE = ["#FFC72C", "#FFE08A", "#FFD75E", "#F4B23E", "#FFF3CC"];
  function hash(str) { var h = 0; for (var i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) & 0xffffff; return h; }

  function burgerGlyph(x, y, s) {
    return (
      '<g transform="translate(' + x + ' ' + y + ') scale(' + s + ')" opacity="0.92">' +
      '<ellipse cx="0" cy="30" rx="52" ry="10" fill="rgba(20,20,20,.08)"/>' +
      '<rect x="-46" y="6" width="92" height="14" rx="7" fill="#7a4a24"/>' +
      '<path d="M-48 4 q10 -12 20 -5 q9 -10 19 -4 q11 -10 21 -3 q11 -8 18 3 q6 9 -6 12 h-84 q-10 -4 -8 -13z" fill="#3fa845"/>' +
      '<ellipse cx="0" cy="-12" rx="50" ry="20" fill="#F4B23E"/>' +
      '<ellipse cx="0" cy="-16" rx="50" ry="17" fill="#FFC72C"/>' +
      '<circle cx="-22" cy="-20" r="2" fill="#fff6da"/><circle cx="-2" cy="-24" r="2" fill="#fff6da"/>' +
      '<circle cx="18" cy="-20" r="2" fill="#fff6da"/><circle cx="30" cy="-14" r="2" fill="#fff6da"/>' +
      "</g>"
    );
  }

  function makePlaceholder(label, type, w, h) {
    w = w || 600; h = h || 450;
    var bg = PALETTE[hash(label || "ok") % PALETTE.length];
    var s = "";
    if (type === "avatar") {
      var initial = (label || "?").trim().charAt(0).toUpperCase();
      s = '<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '">' +
        '<rect width="100%" height="100%" fill="#141414"/>' +
        '<text x="50%" y="54%" font-family="Poppins,Arial" font-weight="800" font-size="' + (w * 0.5) + '" fill="#FFC72C" text-anchor="middle" dominant-baseline="middle">' + initial + "</text></svg>";
      return svgURI(s);
    }
    if (type === "map") {
      s = '<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '">' +
        '<rect width="100%" height="100%" fill="#eef1ee"/>' +
        '<g stroke="#dfe4df" stroke-width="10">' +
        '<path d="M0 90 H' + w + '"/><path d="M0 210 H' + w + '"/><path d="M0 330 H' + w + '"/>' +
        '<path d="M120 0 V' + h + '"/><path d="M360 0 V' + h + '"/><path d="M560 0 V' + h + '"/></g>' +
        '<path d="M60 ' + (h - 40) + ' Q' + (w * 0.4) + ' ' + (h * 0.3) + ' ' + (w - 70) + ' 70" fill="none" stroke="#FFC72C" stroke-width="8" stroke-linecap="round" stroke-dasharray="2 16"/>' +
        '<g transform="translate(60 ' + (h - 40) + ')"><circle r="12" fill="#141414"/><circle r="5" fill="#fff"/></g>' +
        '<g transform="translate(' + (w - 70) + ' 70)"><path d="M0 -34 C18 -34 26 -20 26 -8 C26 8 0 30 0 30 C0 30 -26 8 -26 -8 C-26 -20 -18 -34 0 -34Z" fill="#E11B22"/><circle cy="-8" r="9" fill="#fff"/></g>' +
        "</svg>";
      return svgURI(s);
    }
    var showGlyph = type !== "banner";
    s = '<svg xmlns="http://www.w3.org/2000/svg" width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '">' +
      '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">' +
      '<stop offset="0" stop-color="' + bg + '"/><stop offset="1" stop-color="#FFF3CC"/></linearGradient></defs>' +
      '<rect width="100%" height="100%" fill="url(#g)"/>' +
      '<text x="26" y="' + (h - 26) + '" font-family="Poppins,Arial" font-weight="800" font-size="20" fill="#141414" opacity="0.55">OK · ' +
      escapeXml(label || "") + "</text>" +
      (showGlyph ? burgerGlyph(w / 2, h / 2 - 10, Math.min(w, h) / 130) : "") +
      '<text x="' + (w - 20) + '" y="34" text-anchor="end" font-family="Poppins,Arial" font-weight="800" font-size="16" fill="#141414" opacity="0.25">IMAGE PLACEHOLDER</text>' +
      "</svg>";
    return svgURI(s);
  }
  function escapeXml(s) { return String(s).replace(/[<>&]/g, function (c) { return { "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c]; }); }

  // Curated, on-brand stock photos (Unsplash) chosen per placeholder label/type.
  // Deterministic per label; branded SVG stays as an automatic fallback on load error.
  var PHOTOS = {
    burger:  ["1568901346375-23c9450c58cd", "1571091718767-18b5b1457add", "1550547660-d9450f859349", "1586190848861-99aa4a171e90", "1594212699903-ec8a3eca50f5"],
    fries:   ["1573080496219-bb080dd4f877", "1630384060421-cb20d0e0649d", "1585109649139-366815a0d713"],
    shake:   ["1572490122747-3968b75cc699", "1568901839119-631418a3910d", "1553787499-6f9133860278"],
    chicken: ["1626645738196-c2a7c87a8f58", "1562967914-608f82629710", "1513639776629-7b61b0ac49cb"],
    salad:   ["1512621776951-a57141f2eefd", "1540189549336-e6e99c3679fe"],
    drink:   ["1554866585-cd94860890b7"],
    dessert: ["1499636136210-6f4ee915583e", "1551024506-0bccd828d307"],
    meal:    ["1513104890138-7c749659a591", "1550317138-10000687a72b"],
    hero:    ["1552566626-52f8b828add9", "1517248135467-4c7edcad34c4"]
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
    if (type === "map") return null;   // keep the branded SVG map (real maps need an API key)
    var pool = PHOTOS[photoCategory(label, type)] || PHOTOS.burger;
    var id = pool[Math.abs(hash(label || "ok")) % pool.length];
    return "https://images.unsplash.com/photo-" + id + "?w=" + w + "&h=" + h + "&fit=crop&q=70";
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
      if (real) {
        img.onerror = function () { img.onerror = null; img.src = fallback; };
        img.src = real;
      } else {
        img.src = fallback;
      }
    });
  }

  /* ---------- Header ---------- */
  function headerHTML() {
    var links = NAV.map(function (n) {
      var active = current === n.href ? " is-active" : "";
      return '<a href="' + n.href + '" class="nav-link' + active + '">' + n.label +
        (n.hot ? ' <span class="badge badge-deal" style="font-size:.6rem;padding:.12rem .4rem">HOT</span>' : "") + "</a>";
    }).join("");
    var mobileLinks = NAV.map(function (n) {
      return '<a href="' + n.href + '" class="block py-3 text-lg font-semibold border-b border-[var(--ok-line)]">' + n.label + "</a>";
    }).join("");

    return (
      '<div class="bg-jet text-white text-center text-xs md:text-sm py-2 px-3 font-medium flex items-center justify-center gap-1.5">' +
      ic("flame", "text-okyellow") + ' Free delivery on your first order over $20 · Use code <span class="text-okyellow font-bold">OKFIRST</span></div>' +
      '<header class="ok-header" id="okHeader"><div class="ok-container">' +
      '<div class="flex items-center gap-3 md:gap-6 h-16 md:h-20">' +
      // logo
      '<a href="index.html" class="flex items-center shrink-0" aria-label="OK Smashed Burger home">' +
      '<img src="assets/img/logo.png" onerror="this.onerror=null;this.src=\'assets/img/logo.svg\'" alt="OK Smashed Burger" class="h-11 md:h-14 w-auto"></a>' +
      // location pill
      '<button data-open="location" class="hidden md:flex items-center gap-2 text-left px-3 py-1.5 rounded-full hover:bg-softyellow transition shrink-0 whitespace-nowrap">' +
      '<span class="text-okamber">' + ic("map-pin", "icon-lg") + '</span><span class="leading-tight"><span class="block text-[.65rem] text-slate uppercase font-semibold">Delivery to</span>' +
      '<span class="flex items-center gap-1 text-sm font-bold">Philadelphia · 19107 ' + ic("chevron-down") + "</span></span></button>" +
      // nav (left-aligned, never wraps)
      '<nav class="hidden lg:flex items-center gap-5 xl:gap-7">' + links + "</nav>" +
      // actions (pushed to the right edge)
      '<div class="flex items-center gap-1 md:gap-2 ml-auto shrink-0">' +
      // collapsible search
      '<div class="hdr-search hidden md:block" id="okSearch">' +
      '<button type="button" data-search-open class="search-toggle w-10 h-10 rounded-full hover:bg-softyellow grid place-items-center" aria-label="Search menu" title="Search menu">' + ic("search", "icon-lg") + "</button>" +
      '<div class="search-panel"><div class="flex items-center gap-2 bg-white rounded-full border-2 border-jet shadow-lg pl-4 pr-1.5 py-1.5 w-[clamp(240px,34vw,440px)]">' +
      '<span class="text-slate">' + ic("search") + "</span>" +
      '<input data-search-input type="search" placeholder="Search the menu…" class="bg-transparent text-sm w-full focus:outline-none py-1">' +
      '<button type="button" data-search-close class="w-8 h-8 grid place-items-center rounded-full text-slate hover:bg-softyellow shrink-0" aria-label="Close search">' + ic("x") + "</button></div></div></div>" +
      // account
      '<a href="account.html" class="hidden sm:grid place-items-center w-10 h-10 rounded-full hover:bg-softyellow" title="Account" aria-label="Account">' + ic("user", "icon-lg") + "</a>" +
      // cart
      '<a href="cart.html" class="relative grid place-items-center w-10 h-10 rounded-full hover:bg-softyellow" title="Cart" aria-label="Cart">' + ic("shopping-bag", "icon-lg") +
      '<span id="cartCount" class="absolute -top-0.5 -right-0.5 bg-okred text-white text-[.65rem] font-bold w-5 h-5 grid place-items-center rounded-full">3</span></a>' +
      '<a href="menu.html" class="btn btn-primary btn-sm hidden sm:inline-flex ml-1">Order Now</a>' +
      '<button data-open="drawer" class="lg:hidden grid place-items-center w-10 h-10 rounded-full hover:bg-softyellow" aria-label="Menu">' + ic("menu", "icon-lg") + "</button>" +
      "</div></div></div></header>" +
      // mobile drawer
      '<div class="drawer-backdrop" data-close="drawer"></div>' +
      '<aside class="drawer" id="okDrawer" aria-label="Mobile menu">' +
      '<div class="flex items-center justify-between mb-4">' +
      '<img src="assets/img/logo.png" onerror="this.onerror=null;this.src=\'assets/img/logo.svg\'" class="h-12" alt="OK Smashed Burger">' +
      '<button data-close="drawer" class="w-9 h-9 rounded-full hover:bg-softyellow grid place-items-center" aria-label="Close">' + ic("x", "icon-lg") + "</button></div>" +
      '<div class="flex items-center gap-2 bg-softyellow rounded-full px-3 py-2 mb-4"><span>' + ic("search") + '</span><input placeholder="Search menu…" class="bg-transparent text-sm w-full focus:outline-none"></div>' +
      mobileLinks +
      '<a href="account.html" class="block py-3 text-lg font-semibold border-b border-[var(--ok-line)]">My Account</a>' +
      '<a href="orders.html" class="block py-3 text-lg font-semibold border-b border-[var(--ok-line)]">My Orders</a>' +
      '<a href="menu.html" class="btn btn-primary btn-block mt-5">Order Now</a>' +
      '<button data-open="location" class="btn btn-secondary btn-block mt-3">' + ic("map-pin") + " Change Location</button>" +
      "</aside>"
    );
  }

  /* ---------- Footer ---------- */
  function footerHTML() {
    var col = function (title, items) {
      return '<div><h4 class="font-display font-bold mb-3 text-white">' + title + "</h4><ul class=\"space-y-2\">" +
        items.map(function (i) { return '<li><a href="' + i[1] + '" class="text-white/70 hover:text-okyellow text-sm">' + i[0] + "</a></li>"; }).join("") + "</ul></div>";
    };
    return (
      '<footer class="bg-jet text-white mt-8">' +
      '<div class="border-b border-white/10"><div class="ok-container py-8 flex flex-col md:flex-row items-center justify-between gap-4">' +
      '<div><h3 class="font-display text-xl font-bold flex items-center gap-2">Get the good stuff first ' + ic("beef", "text-okyellow") + "</h3>" +
      '<p class="text-white/70 text-sm">Exclusive deals, new drops & rewards — straight to your inbox.</p></div>' +
      '<form class="flex gap-2 w-full md:w-auto" onsubmit="return false"><input type="email" placeholder="you@email.com" class="ok-input md:w-64 text-jet"><button class="btn btn-primary">Subscribe</button></form>' +
      "</div></div>" +
      '<div class="ok-container py-12 grid grid-cols-2 md:grid-cols-5 gap-8">' +
      '<div class="col-span-2 md:col-span-1">' +
      '<img src="assets/img/logo.png" onerror="this.onerror=null;this.src=\'assets/img/logo.svg\'" class="h-16 mb-3" alt="OK Smashed Burger">' +
      '<p class="text-white/60 text-sm mb-4">Real smashed burgers, fast. Philadelphia\'s neighborhood burger joint.</p>' +
      '<div class="flex gap-2">' +
      '<a href="#" aria-label="Instagram" class="w-9 h-9 grid place-items-center rounded-full bg-white/10 hover:bg-okyellow hover:text-jet">' + ic("instagram", "icon-lg") + "</a>" +
      '<a href="#" aria-label="Facebook" class="w-9 h-9 grid place-items-center rounded-full bg-white/10 hover:bg-okyellow hover:text-jet">' + ic("facebook", "icon-lg") + "</a>" +
      '<a href="#" aria-label="YouTube" class="w-9 h-9 grid place-items-center rounded-full bg-white/10 hover:bg-okyellow hover:text-jet">' + ic("youtube", "icon-lg") + "</a>" +
      "</div></div>" +
      col("Order", [["Menu", "menu.html"], ["Deals & Offers", "deals.html"], ["Locations", "locations.html"], ["Gift Cards", "gift-cards.html"], ["Track Order", "tracking.html"]]) +
      col("Company", [["About Us", "about.html"], ["Careers", "about.html"], ["Franchising", "about.html"], ["Contact", "contact.html"], ["Blog", "about.html"]]) +
      col("Account", [["Sign In", "login.html"], ["Register", "register.html"], ["My Orders", "orders.html"], ["Rewards", "rewards.html"], ["Favorites", "favorites.html"]]) +
      col("Support", [["Help / FAQ", "faq.html"], ["Order Issues", "contact.html"], ["Allergen Info", "faq.html"], ["Accessibility", "faq.html"]]) +
      "</div>" +
      '<div class="border-t border-white/10"><div class="ok-container py-5 flex flex-col md:flex-row items-center justify-between gap-3 text-white/50 text-xs">' +
      '<p>© 2026 OK Smashed Burger · OK Brands, Philadelphia. All rights reserved.</p>' +
      '<div class="flex items-center gap-4"><a href="#" class="hover:text-okyellow">Privacy</a><a href="#" class="hover:text-okyellow">Terms</a><a href="#" class="hover:text-okyellow">CCPA</a>' +
      '<span class="ml-2 flex items-center gap-1.5 tracking-widest">' + ic("credit-card") + " VISA · MC · AMEX · APPLE PAY</span></div>" +
      "</div></div></footer>"
    );
  }

  /* ---------- Location modal ---------- */
  function locationModalHTML() {
    var stores = [
      ["Center City", "1520 Chestnut St, 19102", "0.4 mi", true],
      ["Fishtown", "1201 Frankford Ave, 19125", "1.8 mi", true],
      ["University City", "3720 Spruce St, 19104", "2.3 mi", true],
      ["South Philly", "1801 S Broad St, 19148", "3.1 mi", false]
    ];
    return (
      '<div class="drawer-backdrop" data-close="location" id="locBackdrop"></div>' +
      '<div id="locModal" class="fixed inset-0 z-[80] grid place-items-center p-4 pointer-events-none opacity-0 transition-opacity">' +
      '<div class="ok-card w-full max-w-lg p-6 pointer-events-auto max-h-[90vh] overflow-y-auto">' +
      '<div class="flex items-center justify-between mb-4"><h3 class="ok-h2 text-xl">Choose your store</h3>' +
      '<button data-close="location" class="w-9 h-9 rounded-full hover:bg-softyellow grid place-items-center" aria-label="Close">' + ic("x", "icon-lg") + "</button></div>" +
      '<div class="flex gap-2 mb-4"><div class="flex items-center gap-2 ok-input"><span class="text-slate">' + ic("map-pin") + '</span><input class="w-full focus:outline-none" placeholder="Enter address or ZIP" value="19107"></div><button class="btn btn-dark">Find</button></div>' +
      '<div class="flex gap-2 mb-4" data-chip-group><button class="chip is-active flex-1 justify-center">' + ic("car") + ' Delivery</button><button class="chip flex-1 justify-center">' + ic("shopping-bag") + ' Pickup</button><button class="chip flex-1 justify-center">' + ic("utensils") + ' Dine-in</button></div>' +
      stores.map(function (st) {
        return '<button class="w-full text-left ok-card ok-card-hover p-4 mb-2 flex items-center justify-between ' + (st[3] ? "" : "opacity-60") + '">' +
          '<div><div class="font-bold">OK Smashed Burger — ' + st[0] + '</div><div class="text-sm text-slate">' + st[1] + '</div>' +
          '<div class="flex items-center gap-1.5 text-xs mt-1 ' + (st[3] ? "text-okgreen" : "text-okred") + ' font-semibold">' +
          '<span class="status-dot" style="background:' + (st[3] ? "#2E7D32" : "#C62828") + '"></span>' + (st[3] ? "Open · ~25 min" : "Closed · opens 11:00") + "</div></div>" +
          '<div class="text-right shrink-0 ml-3"><div class="badge badge-soft">' + st[2] + "</div>" + (st[3] ? '<div class="text-okamber mt-2 flex justify-end">' + ic("arrow-right", "icon-lg") + "</div>" : "") + "</div></button>";
      }).join("") +
      "</div></div>"
    );
  }

  /* ---------- Interactions ---------- */
  function toast(msg) {
    var wrap = document.getElementById("ok-toast-wrap");
    if (!wrap) { wrap = document.createElement("div"); wrap.id = "ok-toast-wrap"; document.body.appendChild(wrap); }
    var t = document.createElement("div");
    t.className = "ok-toast"; t.innerHTML = '<span class="tick">' + ic("check-circle") + "</span> " + msg;
    wrap.appendChild(t);
    setTimeout(function () { t.style.opacity = "0"; t.style.transition = "opacity .3s"; setTimeout(function () { t.remove(); }, 300); }, 2200);
  }

  function openDrawer(open) {
    document.getElementById("okDrawer").classList.toggle("is-open", open);
    document.querySelector('.drawer-backdrop[data-close="drawer"]').classList.toggle("is-open", open);
  }
  function openLocation(open) {
    var m = document.getElementById("locModal"), b = document.getElementById("locBackdrop");
    if (!m) return;
    m.style.opacity = open ? "1" : "0";
    m.style.pointerEvents = open ? "auto" : "none";
    b.classList.toggle("is-open", open);
  }

  function wire() {
    var hd = document.getElementById("okHeader");
    if (hd) window.addEventListener("scroll", function () { hd.classList.toggle("is-scrolled", window.scrollY > 8); });

    // collapsible header search
    var searchBox = document.getElementById("okSearch");
    function openSearch(open) {
      if (!searchBox) return;
      searchBox.classList.toggle("is-open", open);
      if (open) { var inp = searchBox.querySelector("[data-search-input]"); if (inp) setTimeout(function () { inp.focus(); }, 40); }
    }
    // collapse when focus leaves the search entirely
    if (searchBox) searchBox.addEventListener("focusout", function (e) {
      if (!searchBox.contains(e.relatedTarget)) openSearch(false);
    });

    // inline collapsible search on the menu category bar
    var catbar = document.getElementById("menuCatbar");
    function openMenuSearch(open) {
      if (!catbar) return;
      catbar.classList.toggle("is-searching", open);
      if (open) { var i = catbar.querySelector("[data-msearch-input]"); if (i) setTimeout(function () { i.focus(); }, 40); }
    }
    if (catbar) {
      catbar.addEventListener("mouseleave", function () { openMenuSearch(false); });
      catbar.addEventListener("focusout", function (e) { if (!catbar.contains(e.relatedTarget)) openMenuSearch(false); });
    }

    document.addEventListener("click", function (e) {
      var openT = e.target.closest("[data-open]"), closeT = e.target.closest("[data-close]");
      if (openT) { e.preventDefault(); if (openT.dataset.open === "drawer") openDrawer(true); if (openT.dataset.open === "location") openLocation(true); }
      if (closeT) { if (closeT.dataset.close === "drawer") openDrawer(false); if (closeT.dataset.close === "location") openLocation(false); }

      // header search open / close / click-away
      if (e.target.closest("[data-search-open]")) { e.preventDefault(); openSearch(true); }
      else if (e.target.closest("[data-search-close]")) { e.preventDefault(); openSearch(false); }
      else if (searchBox && searchBox.classList.contains("is-open") && !e.target.closest("#okSearch")) { openSearch(false); }

      // menu category-bar search open / close
      if (e.target.closest("[data-msearch-open]")) { e.preventDefault(); openMenuSearch(true); }
      else if (e.target.closest("[data-msearch-close]")) { e.preventDefault(); openMenuSearch(false); }

      var qBtn = e.target.closest(".qty button");
      if (qBtn) {
        var span = qBtn.parentElement.querySelector("span");
        var v = parseInt(span.textContent, 10) || 0;
        v += qBtn.dataset.step === "-" ? -1 : 1; if (v < 1) v = 1;
        span.textContent = v;
      }

      var chip = e.target.closest("[data-chip-group] .chip");
      if (chip) {
        if (chip.dataset.multi === undefined) chip.parentElement.querySelectorAll(".chip").forEach(function (c) { c.classList.remove("is-active"); });
        chip.classList.toggle("is-active");
      }

      var addBtn = e.target.closest("[data-add-cart]");
      if (addBtn) {
        e.preventDefault();
        var cc = document.getElementById("cartCount");
        if (cc) cc.textContent = (parseInt(cc.textContent, 10) || 0) + 1;
        toast((addBtn.dataset.addCart || "Item") + " added to cart");
      }

      var accQ = e.target.closest(".acc-q");
      if (accQ) accQ.parentElement.classList.toggle("is-open");

      var tabBtn = e.target.closest("[data-tab]");
      if (tabBtn) {
        var group = tabBtn.closest("[data-tab-group]");
        var name = tabBtn.dataset.tab;
        group.querySelectorAll("[data-tab]").forEach(function (b) { b.classList.toggle("is-active", b === tabBtn); });
        group.querySelectorAll("[data-panel]").forEach(function (p) { p.classList.toggle("hidden", p.dataset.panel !== name); });
      }

      // smooth-scroll any same-page CTA to its section, offset for the sticky bars
      var anchor = e.target.closest('a[href^="#"]');
      if (anchor) {
        var href = anchor.getAttribute("href");
        e.preventDefault();
        var id = href.length > 1 ? decodeURIComponent(href.slice(1)) : "";
        var target = id && document.getElementById(id);
        if (target) {
          smoothScrollToEl(target);
          if (history.replaceState) history.replaceState(null, "", href);
        }
      }
    });

    document.addEventListener("keydown", function (e) { if (e.key === "Escape") { openDrawer(false); openLocation(false); openSearch(false); openMenuSearch(false); } });
  }

  /* ---------- Boot ---------- */
  function inject(id, html) { var el = document.getElementById(id); if (el) el.outerHTML = html; }

  document.addEventListener("DOMContentLoaded", function () {
    inject("site-header", '<div id="site-header-mount"></div>');
    var h = document.getElementById("site-header-mount"); if (h) h.outerHTML = headerHTML() + locationModalHTML();
    var f = document.getElementById("site-footer"); if (f) f.outerHTML = footerHTML();
    hydratePlaceholders(document);
    wire();
  });

  // expose helpers for page scripts
  window.OK = { toast: toast, hydratePlaceholders: hydratePlaceholders, placeholder: makePlaceholder, icons: renderIcons };
})();
