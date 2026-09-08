"""CLI: remove sandbox customer/transactional data before production launch."""
from app import create_app
from app.services.test_data_cleanup import clean_test_data


def main():
    app = create_app()
    with app.app_context():
        counts = clean_test_data()
        for key, n in counts.items():
            print(f"  {key}: {n}")
        print("[ok] production cleanup complete")


if __name__ == "__main__":
    main()
