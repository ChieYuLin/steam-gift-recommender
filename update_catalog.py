from app import CATALOG_SNAPSHOT_PATH, refresh_store_catalog


if __name__ == "__main__":
    snapshot = refresh_store_catalog()
    print(f"Wrote {len(snapshot['games'])} China-store candidates to {CATALOG_SNAPSHOT_PATH}.")