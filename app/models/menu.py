"""Menu: brand-level catalog (Category, Product, Variant, Addon) plus the
per-store link (StoreMenuItem) that gives each location its own menu with its
own prices and availability (SRS FR-3.1 / FR-3.2)."""
from app.extensions import db
from .base import TimestampMixin


class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False)   # "burgers"
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255))
    icon = db.Column(db.String(60))                                # font-awesome class suffix, e.g. "burger"
    image_url = db.Column(db.String(500))                          # category tile photo (falls back to icon)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    products = db.relationship("Product", back_populates="category", cascade="all, delete-orphan")


class Product(TimestampMixin, db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(120), unique=True, index=True, nullable=False)
    name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    base_price = db.Column(db.Numeric(8, 2), nullable=False)
    image_url = db.Column(db.String(500))          # real photo; falls back to placeholder if empty
    calories = db.Column(db.Integer)
    allergens = db.Column(db.JSON, default=list)   # ["gluten", "dairy"]
    tags = db.Column(db.JSON, default=list)        # ["popular", "spicy"]
    is_vegan = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    category = db.relationship("Category", back_populates="products")
    variants = db.relationship("ProductVariant", back_populates="product", cascade="all, delete-orphan")
    addons = db.relationship(
        "ProductAddon", back_populates="product", cascade="all, delete-orphan",
        order_by="ProductAddon.sort_order",
    )
    store_items = db.relationship("StoreMenuItem", back_populates="product", cascade="all, delete-orphan")


class ProductVariant(db.Model):
    """Size / patty options with a price delta (e.g. Single / Double / Triple)."""
    __tablename__ = "product_variants"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    price_delta = db.Column(db.Numeric(8, 2), default=0)
    is_default = db.Column(db.Boolean, default=False)
    product = db.relationship("Product", back_populates="variants")


class AddonLibrary(db.Model):
    """Brand-wide add-on catalog — create once, attach to any menu item."""
    __tablename__ = "addon_library"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    price = db.Column(db.Numeric(8, 2), default=0)
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    product_links = db.relationship("ProductAddon", back_populates="library")


class ProductAddon(db.Model):
    """Per-item link to a shared add-on (or a one-off extra)."""
    __tablename__ = "product_addons"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    library_id = db.Column(db.Integer, db.ForeignKey("addon_library.id"))
    name = db.Column(db.String(80), nullable=False)
    price = db.Column(db.Numeric(8, 2), default=0)
    is_required = db.Column(db.Boolean, default=False, nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    product = db.relationship("Product", back_populates="addons")
    library = db.relationship("AddonLibrary", back_populates="product_links")


class StoreMenuItem(db.Model):
    """The join that makes a product part of a specific store's menu, with an
    optional price override and per-store availability."""
    __tablename__ = "store_menu_items"
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey("stores.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    is_listed = db.Column(db.Boolean, default=True, nullable=False)   # on this store's menu at all?
    is_available = db.Column(db.Boolean, default=True, nullable=False)  # in stock right now (86'd if False)
    is_featured = db.Column(db.Boolean, default=False)
    price_override = db.Column(db.Numeric(8, 2))                       # None -> use product.base_price

    store = db.relationship("Store", back_populates="menu_items")
    product = db.relationship("Product", back_populates="store_items")

    __table_args__ = (
        db.UniqueConstraint("store_id", "product_id", name="uq_store_product"),
    )
