"""Email blocklist — stop repeat sends to bad addresses."""
import pytest
from dotenv import load_dotenv

load_dotenv()

from app import create_app
from app.extensions import db
from app.models.site import SiteSetting
from app.services.email_delivery import block, is_blocked, note_failure, should_skip, unblock


@pytest.fixture(scope="module")
def app():
    application = create_app()
    application.config["TESTING"] = True
    return application


def test_permanent_failure_blocks_address(app):
    with app.app_context():
        unblock("bad@oksmashedburger.com")
        assert not is_blocked("bad@oksmashedburger.com")
        note_failure("bad@oksmashedburger.com", "550 5.1.1 User unknown")
        assert is_blocked("bad@oksmashedburger.com")
        assert should_skip("bad@oksmashedburger.com")
        unblock("bad@oksmashedburger.com")


def test_temporary_failure_does_not_block(app):
    with app.app_context():
        addr = "retry@example.com"
        unblock(addr)
        note_failure(addr, "421 4.7.0 try again later")
        assert not is_blocked(addr)
        unblock(addr)


def test_mailer_skips_blocked_business_inbox(app):
    with app.app_context():
        from app.models.store import Store
        from app.services.mailer import business_inbox

        store = Store.query.first()
        if not store:
            pytest.skip("no store")
        old = store.email
        test_addr = "blocked-inbox@test.local"
        block(test_addr, "test")
        store.email = test_addr
        assert business_inbox(store) == ""
        store.email = old
        unblock(test_addr)
        db.session.commit()
