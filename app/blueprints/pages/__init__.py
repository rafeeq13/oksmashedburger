"""Remaining storefront/account pages. These are converted from the approved
template and will be wired to real data (cart, checkout, orders, auth) in the
upcoming phases; for now they render the approved design under the new layout."""
from flask import Blueprint, render_template

bp = Blueprint("pages", __name__)

# Public pages that don't (yet) need auth. login/register/forgot are handled by
# the auth blueprint; account/orders/favorites by the account blueprint.
_ROUTES = {
    "/tracking": "tracking",
}


def _make(view_name, template):
    def view():
        return render_template(f"pages/{template}.html")
    view.__name__ = view_name
    return view


for path, name in _ROUTES.items():
    bp.add_url_rule(path, endpoint=name, view_func=_make(name, name))
