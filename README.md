# OK Smashed Burger — Website Template (Layout Prototype)

A clickable, front-end **dummy template** for the OK Smashed Burger ordering platform, built for **client layout sign-off**. It covers the complete customer-facing website — from the homepage all the way through the **live order-tracking** page.

> **Status:** Layout / design prototype only. No backend, no real payments, no live data. Once the layout is approved, these pages become the front-end for the real Flask / Jinja2 build described in the SRS (the Tailwind classes carry over directly).

---

## How to view it

Just open **`index.html`** in any modern browser (double-click it), then click around — every page links to the others.

> The template loads Tailwind and Google Fonts from a CDN, so keep an internet connection when viewing. (In the production build these get bundled locally per the SRS stack.)

---

## Pages included (complete customer website)

| # | Page | File | Purpose |
|---|------|------|---------|
| 1 | Home | `index.html` | Deal-forward landing, location/order-type, best-sellers, categories |
| 2 | Locations | `locations.html` | Store locator with map, hours, distance |
| 3 | Menu | `menu.html` | Category browse, filters, quick-add |
| 4 | Item detail | `item.html` | Customizer: sizes, add-ons, combos, quantity |
| 5 | Cart | `cart.html` | Line items, promo, tips, totals |
| 6 | Checkout | `checkout.html` | Single-screen: address, time, contact, payment |
| 7 | Order confirmed | `order-confirmed.html` | Success + bridge to tracking |
| 8 | **Order tracker** | `tracking.html` | **Animated live status, driver map, ETA** |
| 9 | Deals | `deals.html` | Offers, BOGO, promo codes |
| 10 | Rewards | `rewards.html` | Loyalty points, tiers, referrals |
| 11 | Gift cards | `gift-cards.html` | Buy / send / check balance |
| 12 | Account | `account.html` | Dashboard, addresses, payment methods |
| 13 | Orders | `orders.html` | Active / past / scheduled orders |
| 14 | Favorites | `favorites.html` | Saved items + one-tap reorder |
| 15 | Login | `login.html` | Sign in + social login |
| 16 | Register | `register.html` | Create account |
| 17 | Forgot password | `forgot-password.html` | Password reset |
| 18 | About | `about.html` | Brand story, team, franchising |
| 19 | Contact | `contact.html` | Contact form + map |
| 20 | FAQ | `faq.html` | Help center accordion |

## Not included yet (separate internal suites)
These are staff-facing operational tools from the SRS, not part of the public website layout — available as a **second batch** on request:
- Admin / Franchise / Store dashboards (SRS §4.16)
- Kitchen Display System — KDS (SRS §4.7)
- Driver app view (SRS §4.8)

---

## Brand system (from SRS §9.2)

| Token | Hex | Role |
|-------|-----|------|
| OK Yellow | `#FFC72C` | Primary — CTAs, badges, highlights (never used for text) |
| Pure White | `#FFFFFF` | Backgrounds, cards |
| Jet Black | `#141414` | Text, headers, accent |
| Amber | `#E0A200` | Hover / pressed |
| Soft Yellow | `#FFF3CC` | Section tints, chips |
| Slate Grey | `#6B6B6B` | Secondary text |
| Success Green | `#2E7D32` | Confirmed / in-stock |
| Alert Red | `#C62828` | Errors / sold-out |

- **Fonts:** Poppins (display/headings), Inter (body/UI).
- **Type scale (consistent across all pages):** `.ok-display` (hero titles) → `.ok-h1` (page titles) → `.ok-h2` (section headings) → `.ok-h3` (card titles) → `.ok-eyebrow` (small labels) / `.ok-lead` (intro text). Use these instead of ad-hoc `text-*` sizes so hierarchy stays uniform.
- **Copy:** no unverified superlative or ranking claims (e.g. "#1", "best in Philly") — keep marketing copy factual until the client provides real figures.
- **Accessibility:** yellow is fills-only; text is jet/slate on white for WCAG AA contrast.

---

## Project structure

```
oksmashedburger/
├── index.html … faq.html        # 20 pages
├── assets/
│   ├── css/style.css            # design-system component classes
│   ├── js/app.js                # shared header/footer + placeholders + interactions
│   └── img/
│       ├── logo.svg             # on-brand stand-in logo
│       └── logo.png             # ← DROP YOUR REAL LOGO HERE (see below)
├── OK_Smashed_Burger_SRS.docx   # source requirements
└── README.md
```

### Shared components
The header, footer, mobile drawer, and store-locator modal are defined **once** in `assets/js/app.js` and injected into every page (`<div id="site-header"></div>` / `<div id="site-footer"></div>`). Change them in one place → all pages update.

### Using the real logo
The header/footer reference `assets/img/logo.png` and automatically fall back to the bundled `logo.svg` stand-in. **To use the official logo, just save it as `assets/img/logo.png`** — no code changes needed.

### Images
Every `<img data-ph="…" data-ph-type="…">` is filled at runtime by `app.js`:
- **Food / hero** → real stock photos from Unsplash, chosen per item label from curated, on-brand pools (burgers, fries, shakes, chicken, salads, drinks, desserts).
- **Avatars** (reviews/account) → pravatar.
- **Maps** (tracking/locations/contact) → a branded SVG map (a real map needs a Google Maps API key — added in the production build).
- If any photo fails to load, it automatically falls back to an on-brand SVG placeholder, so nothing ever breaks.

To use the client's own photography later, either drop real files in `assets/img/` and set the `<img src="…">` directly, or edit the curated `PHOTOS` pools in `assets/js/app.js`. (Photos load from Unsplash's CDN, so keep an internet connection when reviewing.)

### Icons
UI icons use [Font Awesome 6 (free)](https://fontawesome.com/) — the CSS is auto-loaded by `app.js`. To place an icon anywhere, write `<i class="fa-solid fa-icon-name"></i>` (or `fa-brands fa-…` for social/brand icons). Add `class="… icon-lg"` or `icon-xl` to enlarge; icons otherwise scale with the surrounding font size. The injected header/footer build icons via a small name→class map (`ICMAP`) in `app.js`.

---

## What's interactive in the demo
Mobile menu drawer · store-locator modal · order-type & filter chips · quantity steppers · add-to-cart toasts & live cart badge · tabbed sections · FAQ accordion · and the **self-advancing order tracker** on `tracking.html`.

*These are front-end demos only — real logic (payments, auth, live tracking, etc.) is implemented in the production Flask build.*
