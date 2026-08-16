"""Fetch Steam's complete English visible labels into an audit-only cache."""
import concurrent.futures
import html
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as gifi  # noqa: E402

WORKERS = 6
OUTPUT = Path(gifi.app.root_path) / "data" / "steam_catalog_tag_labels_en.json"


def fetch(app_id):
    try:
        response = gifi.requests.get(
            f"{gifi.STEAM_STORE_BASE}/app/{app_id}/",
            params={"cc": "cn", "l": "english"},
            headers=gifi.STORE_HEADERS,
            cookies=gifi.STORE_COOKIES,
            timeout=12,
        )
        response.raise_for_status()
        labels = []
        for chunk in re.findall(r'<a[^>]*class="app_tag[^>]*>(.*?)</a>', response.text, re.S):
            label = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", chunk))).strip()
            if label and label not in labels:
                labels.append(label)
        return str(app_id), labels
    except Exception:  # noqa: BLE001
        return str(app_id), []


def main():
    games = gifi.get_store_catalog()
    try:
        cache = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        cache = {}
    pending = [game for game in games if len(cache.get(str(game["app_id"]), [])) < gifi.FULL_TAG_LABEL_COUNT]
    print(f"目录 {len(games)} 款，英文标签待扫描 {len(pending)} 款", flush=True)
    success = failed = 0
    started = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as executor:
        for app_id, labels in executor.map(lambda game: fetch(game["app_id"]), pending):
            if labels:
                cache[app_id] = labels
                success += 1
            else:
                failed += 1
            completed = success + failed
            if completed % 50 == 0 or completed == len(pending):
                print(f"  {completed}/{len(pending)} 成功 {success} 失败 {failed} {completed / max(time.time() - started, .001):.1f} 款/秒", flush=True)
    OUTPUT.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    print(f"完成：成功 {success}，失败 {failed}。仅写入 {OUTPUT.name}。", flush=True)


if __name__ == "__main__":
    main()
