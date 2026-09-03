"""Apply premium HTML design to all email templates in the database."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.models import email_templates as et


def main():
    app = create_app()
    with app.app_context():
        count = et.apply_premium_email_designs(force=True)
        print("Updated %d email template designs." % count)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
