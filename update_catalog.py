import argparse
import json

from app import CATALOG_BATCH_SIZE, CATALOG_CANDIDATES_PATH, CATALOG_SNAPSHOT_PATH, backfill_catalog_review_counts_batch, backfill_catalog_tag_labels_batch, prepare_store_catalog_candidates, refresh_store_catalog, refresh_store_catalog_batch, verify_catalog_game_types_batch


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the China Steam catalog in resumable batches.")
    parser.add_argument("--prepare", action="store_true", help="Fetch and save the Steam source candidate manifest.")
    parser.add_argument("--progress", action="store_true", help="Print current catalog enrichment progress without changing data.")
    parser.add_argument("--batch-size", type=int, default=CATALOG_BATCH_SIZE, help="Number of pending candidates to enrich.")
    parser.add_argument("--verify-games", action="store_true", help="Verify legacy catalog entries and remove non-game Steam app types.")
    parser.add_argument("--backfill-labels", action="store_true", help="Retry readable Chinese labels for catalog entries that already have tag IDs.")
    parser.add_argument("--backfill-reviews", action="store_true", help="Fill global review counts and positive rates used as the popularity signal.")
    parser.add_argument("--full", action="store_true", help="Run the legacy full rebuild in one operation.")
    arguments = parser.parse_args()
    if arguments.progress:
        try:
            snapshot = json.loads(CATALOG_SNAPSHOT_PATH.read_text(encoding="utf-8"))
            candidates = json.loads(CATALOG_CANDIDATES_PATH.read_text(encoding="utf-8")).get("candidates", [])
        except (OSError, ValueError, TypeError) as error:
            raise SystemExit(f"无法读取目录进度：{error}")
        processed = len(snapshot.get("processed_candidate_ids", []))
        total = len(candidates)
        pending = snapshot.get("pending_candidates", max(0, total - processed))
        progress = 100 * processed / total if total else 0
        games = snapshot.get("games", [])
        labels = sum(bool(game.get("tag_labels")) for game in games)
        labels_pending = sum(bool(game.get("tag_ids")) and not bool(game.get("tag_labels")) for game in games)
        reviews_checked = sum(bool(game.get("review_checked")) for game in games)
        print(f"Processed: {processed}/{total} ({progress:.1f}%)")
        print(f"Pending: {pending}")
        print(f"Catalog games: {len(games)}")
        print(f"Games with readable labels: {labels}/{len(games)}")
        print(f"Readable labels pending backfill: {labels_pending}")
        print(f"Games with review counts checked: {reviews_checked}/{len(games)}")
    elif arguments.full:
        snapshot = refresh_store_catalog()
        print(f"Wrote {len(snapshot['games'])} China-store candidates to {CATALOG_SNAPSHOT_PATH}.")
    elif arguments.verify_games:
        snapshot, checked, removed = verify_catalog_game_types_batch(max(1, arguments.batch_size))
        print(f"Verified {checked} legacy entries, removed {removed} non-games; catalog now has {len(snapshot['games'])} games with {snapshot.get('game_type_verification_pending', 0)} pending.")
    elif arguments.backfill_labels:
        snapshot, checked, updated = backfill_catalog_tag_labels_batch(max(1, arguments.batch_size))
        print(f"Retried labels for {checked} games, filled {updated}; catalog now has {len(snapshot['games'])} games with {snapshot.get('tag_label_backfill_pending', 0)} pending.")
    elif arguments.backfill_reviews:
        snapshot, checked, updated = backfill_catalog_review_counts_batch(max(1, arguments.batch_size))
        print(f"Checked reviews for {checked} games, filled {updated}; {snapshot.get('review_backfill_pending', 0)} still pending.")
    elif arguments.prepare:
        snapshot = prepare_store_catalog_candidates()
        print(f"Wrote {len(snapshot['candidates'])} source candidates to {CATALOG_CANDIDATES_PATH}.")
    else:
        snapshot, processed, added = refresh_store_catalog_batch(max(1, arguments.batch_size))
        print(f"Processed {processed} candidates, added {added}; catalog now has {len(snapshot['games'])} games with {snapshot['pending_candidates']} pending.")