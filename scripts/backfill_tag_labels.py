"""Refetch full tag lists for catalogue games whose store page returned too few.

The store page hands out a trimmed tag set behind the age gate, so anything
violent or mature came back with seven tags instead of twenty.
"""
import concurrent.futures
import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as gift  # noqa: E402

WORKERS = 6
progress_lock = threading.Lock()


def main():
    snapshot = json.loads(gift.CATALOG_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    games = snapshot.get("games", [])
    cache = gift.load_catalog_tag_label_cache()

    pending = [
        game for game in games
        if len(game.get("tag_labels") or []) < gift.FULL_TAG_LABEL_COUNT
        and len(cache.get(str(game["app_id"])) or []) < gift.FULL_TAG_LABEL_COUNT
    ]
    print(f"快照共 {len(games)} 款，待抓取 {len(pending)} 款", flush=True)

    def work(game):
        try:
            return str(game["app_id"]), gift.fetch_app_tag_labels(game["app_id"])
        except Exception:  # noqa: BLE001 - one bad page must not stop the run
            return str(game["app_id"]), None

    done = failed = 0
    started = time.time()
    if pending:
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for app_id, labels in pool.map(work, pending):
                with progress_lock:
                    if labels:
                        cache[app_id] = labels
                        done += 1
                    else:
                        failed += 1
                    total = done + failed
                    if total % 25 == 0 or total == len(pending):
                        rate = total / max(1e-9, time.time() - started)
                        print(f"  {total}/{len(pending)}  成功 {done}  失败 {failed}  {rate:.1f} 款/秒", flush=True)
        gift.CATALOG_TAG_LABEL_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    # The catalogue is served from the snapshot, so the cache has to be folded back in.
    merged = 0
    for game in games:
        labels = cache.get(str(game["app_id"]))
        if labels and len(labels) > len(game.get("tag_labels") or []):
            game["tag_labels"] = labels
            merged += 1
    snapshot["games"] = games
    gift.CATALOG_SNAPSHOT_PATH.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    print(f"抓取成功 {done}，失败 {failed}，写回快照 {merged} 款", flush=True)

    still = [g for g in games if len(g.get("tag_labels") or []) < gift.FULL_TAG_LABEL_COUNT]
    print(f"标签仍不足 {gift.FULL_TAG_LABEL_COUNT} 个的：{len(still)} 款", flush=True)


if __name__ == "__main__":
    main()
