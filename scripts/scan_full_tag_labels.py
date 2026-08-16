"""Fetch Steam's full visible tag names for audit without altering recommendation data."""
import concurrent.futures
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as gift  # noqa: E402

WORKERS = 6


def main():
    snapshot = json.loads(gift.CATALOG_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    games = snapshot.get("games", [])
    cache = gift.load_catalog_tag_label_cache()
    pending = [
        game for game in games
        if len(cache.get(str(game["app_id"])) or []) < gift.FULL_TAG_LABEL_COUNT
    ]
    print(f"目录 {len(games)} 款，待扫描 {len(pending)} 款", flush=True)

    def fetch(game):
        try:
            return str(game["app_id"]), gift.fetch_app_tag_labels(game["app_id"])
        except Exception:  # noqa: BLE001
            return str(game["app_id"]), []

    success = failed = 0
    started = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as executor:
        for app_id, labels in executor.map(fetch, pending):
            if labels:
                cache[app_id] = labels
                success += 1
            else:
                failed += 1
            completed = success + failed
            if completed % 25 == 0 or completed == len(pending):
                elapsed = max(time.time() - started, 0.001)
                print(f"  {completed}/{len(pending)} 成功 {success} 失败 {failed} {completed / elapsed:.1f} 款/秒", flush=True)

    gift.CATALOG_TAG_LABEL_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    print(f"扫描完成：成功 {success}，失败 {failed}；未修改目录快照或评分数据。", flush=True)


if __name__ == "__main__":
    main()
