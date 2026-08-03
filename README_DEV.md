# OK Smashed Burger — Platform (Development)

Flask **modular monolith** per the SRS (§2.5, §3). Multi-location: **each store owns
its own menu and its own integrations**. The approved static template has been
converted to server-rendered **Jinja2** — the design is unchanged.

> The original approved static template is preserved at the repo root (`index.html`,
> `menu.html`, … and `assets/`) as the visual reference. The live app lives under `app/`.

---

## Run it (Docker — recommended)

Requires **Docker Desktop**. Postgres, Redis and the app all run in containers — you
don't need Python or a database installed on your machine.

```bash
cp .env.example .env          # adjust secrets if you like
docker compose up --build
```

On first boot the web container waits for Postgres, creates the tables, and seeds
**two locations each with their own menu + integrations**. Then open:

- Storefront:  http://localhost:8000/
- Menu (per selected store): http://localhost:8000/menu
- A specific store's menu:   http://localhost:8000/menu/center-city  ·  /menu/fishtown
- Locations:  http://localhost:8000/locations
- Health:     http://localhost:8000/healthz

Seeded admin: `admin@oksmashedburger.com` / `admin123` (change on first login).

### Run locally without Docker — quick SQLite mode (no Postgres/Redis needed)
Good for a fast smoke test. Rate limiting falls back to in-memory and payments/Uber
run in demo mode.
```bash
python -m venv .venv
.venv/Scripts/python -m pip install Flask Flask-SQLAlchemy Flask-Migrate Flask-JWT-Extended Flask-Limiter argon2-cffi python-dotenv email-validator
# PowerShell:  $env:DATABASE_URL="sqlite:///dev.db"; $env:DEMO_PAYMENTS="true"; $env:SECRET_KEY="dev"; $env:JWT_SECRET_KEY="dev"
.venv/Scripts/python -m flask --app wsgi db-create
.venv/Scripts/python -m flask --app wsgi seed
.venv/Scripts/python -m flask --app wsgi run --port 8000
```

### Run locally with Postgres/Redis (closer to prod)
```bash
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg2://oksb:oksb@localhost:5432/oksb
flask --app wsgi db-create && flask --app wsgi seed && flask --app wsgi run --port 8000
```

> **Validated:** the full flow has been run and smoke-tested (SQLite): storefront +
> per-store menus (Center City vs Fishtown prices/86/listing), auth (login/register/
> guards/CSRF), cart → checkout → per-store Stripe (demo) → order-confirmed, KDS bump
> → status advance, per-store dispatch (**CC → Uber Direct, Fishtown → own driver**),
> driver pickup/deliver, and the admin dashboard — all 200/302, no 500s.

---

## Multi-location: "own menu + own integrations"

| Concept | Where |
|---|---|
| A location | `Store` (`app/models/store.py`) |
| **Its own menu** | `StoreMenuItem` — links a brand catalog `Product` to a store with a **per-store price override + availability** (`is_listed`, `is_available`, `price_override`). `Store.effective_menu()` builds the store's live menu. |
| **Its own integrations** | `StoreIntegration` — one row per provider (`stripe`, `square`, `uber_direct`, …) with a JSON `config` holding that store's own keys, and an `enabled` flag. |

The seed demonstrates it:
- **Center City** — full menu; Stripe/Square/Uber Direct all connected (own keys).
- **Fishtown** — its *own* menu (no Mushroom Swiss, Buffalo Chicken 86'd/sold-out,
  a cheaper Classic Double), Stripe/Square with **different** accounts, and **Uber
  Direct disabled** (uses its own drivers). Compare `/menu/center-city` vs `/menu/fishtown`.

---

## Project layout

```
app/
  __init__.py         app factory, blueprint registration, template context, CLI
  config.py           env-driven config
  extensions.py       db, migrate, jwt, limiter (SocketIO/Celery added in Ops phase)
  helpers.py          current-store resolution
  models/             user(RBAC) · store/hours/zones/integrations · menu(category/product/store_menu_item)
  blueprints/
    website/          home, about, contact, faq, deals, rewards, gift-cards
    stores/           locator + set-location
    menu/             per-store menu + item detail
    pages/            cart, checkout, tracking, account, orders, auth … (design in place; data wired next)
  templates/          Jinja2 (layouts/base.html, partials/header|footer|location_modal, + pages)
  static/             css/style.css · js/app.js (interactions) · img/
seed_data.py (app/)   roles, admin, catalog, 2 stores w/ own menu + integrations
requirements.txt · Dockerfile · docker-compose.yml · docker-entrypoint.sh · .env.example
```

---

## What's built (Phase 1a) & what's next

**Done — Phase 1a (storefront):** project scaffold, multi-location + menu + per-store
integrations data model, seed, DB-driven storefront (home, locations, per-store menu,
item), template fully converted to Jinja2 with server-rendered header/footer/modal.

**Done — Phase 1b (auth & RBAC):** real login / register (Argon2) / logout / password-
reset stub; signed HTTP-only session; CSRF protection on all POST forms; `current_user`
in every template; `login_required` + `roles_required(...)` decorators; `/account`,
`/orders`, `/favorites` protected; account page shows the signed-in user's real
name/email/points. New customers get 100 welcome points.

Try it: register at `/register`, or sign in with the seeded admin
`admin@oksmashedburger.com` / `admin123`, then visit `/account`; `/logout` to sign out.

**Done — Phase 1c (cart, checkout & per-store payments):** session cart (add from
menu/item/home with variants + add-ons + notes, edit qty, remove); checkout with
order-type, contact, tip, and card/cash; server-side totals using **the current
store's tax rate + delivery fee**; order creation (`Order`/`OrderItem`/`Payment`);
loyalty points earned; guest checkout supported. Payments route through **each
store's own Stripe account** (`app/integrations/stripe_gateway.py` reads that store's
`StoreIntegration` keys) — an order at Center City charges Center City's account,
Fishtown charges Fishtown's. `DEMO_PAYMENTS=true` (default) simulates the charge so
the flow works today; set it `false` + add real keys per store to go live.

Try it: open `/menu`, add a few items, go to `/cart`, then `/checkout` → Place Order
→ `/order-confirmed` shows your real order number, items and totals.

**Done — Phase 1d (order management, KDS & live tracking):** order lifecycle
(placed→confirmed→preparing→ready→out-for-delivery→completed / cancelled), order-type
aware. **Kitchen Display System** at `/kds` (staff-role-scoped) — that store's live
queue with aging timers, item modifiers/notes, **bump-to-advance**, 4s auto-refresh,
corporate store switcher. Customer **tracking** (`/tracking`, `/tracking/<number>`)
wired to real status (6-stage stepper), **polls a JSON status API every 3s** so it
updates live when the kitchen bumps it. `/orders` shows the user's real active/past
orders. Seed adds staff (`kitchen@`/`manager@` · `*123`) + 3 live demo orders.

Try it: place an order → open `/tracking`. In another browser sign in as
`manager@oksmashedburger.com` / `manager123` → **KDS** (header) → **Bump** → the
customer tracker advances within seconds.

> Real-time uses reliable polling (works with the standard server). Swapping in
> **Flask-SocketIO** websockets (SRS §8.1) is a drop-in next-pass upgrade (needs a
> gevent async worker — a deploy-config change).

**Done — Phase 1e (admin / store management):** role-scoped admin at `/admin`
(super_admin / franchise_owner / store_manager). A store_manager is pinned to their
store; corporate can switch stores. Sections: **Dashboard** (orders today, active,
paid revenue, recent), **Menu** (this location's own menu — list/unlist, 86/available,
per-store price override, saved to `StoreMenuItem`), **Integrations** (this location's
own Stripe/Square/Uber Direct/Google/Twilio/SendGrid keys + enable toggle, saved to
`StoreIntegration`), and **Orders** (store order table). "Admin" + "KDS" buttons show
in the header for staff. This is the management layer for *each location's own menu &
own integrations*.

Try it: sign in as `manager@oksmashedburger.com` / `manager123` → **Admin** (header)
→ Menu (toggle an item's availability — it changes on the storefront) and Integrations
(edit this store's Stripe keys).

**Done — Phase 1f (delivery management):** own-fleet `Driver`s + `Delivery` records.
When a delivery order is bumped to *out for delivery* in KDS it **auto-dispatches per
store**: if the store has **Uber Direct enabled** (its own keys) it dispatches to Uber
Direct; otherwise it assigns one of the store's **own drivers** (`app/services/delivery.py`).
The tracking page shows the driver card (call) or the Uber Direct tracking link; admin
orders show the delivery channel. A **driver app** at `/driver` (role `driver`) lists
assigned deliveries with navigate + *picked up* / *delivered* (proof of delivery) —
marking delivered completes the order. Seed adds a driver login and a live own-fleet
delivery. Demonstrates per-store routing: **Center City → Uber Direct**, **Fishtown →
own driver** (Uber disabled).

Try it: sign in `driver@oksmashedburger.com` / `driver123` → **Driver** (header) to see
the seeded Fishtown delivery; mark it picked up → delivered.

**Next increments (mapped to SRS §11):**
1. **Loyalty, promotions, gift cards, reviews.**
2. **Reporting/analytics** (Chart.js) across store/franchise/brand.
3. **Inventory & suppliers** (SRS §4.13).
4. **Alembic migrations** (replace `db-create`), Celery workers, S3/R2 uploads, CI/CD, Flask-SocketIO websockets.

> Auth is session-based for the server-rendered web (secure, simple). The installed
> Flask-JWT-Extended is reserved for the versioned REST API (`/api/*`, SRS §5.4).
