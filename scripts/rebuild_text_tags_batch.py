"""Fetch one reviewable batch of official Steam full text tags.

Writes an audit-only Chinese/English pair cache. It never touches the active
recommendation snapshot or legacy tag ids.
"""
import concurrent.futures
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as gifi  # noqa: E402

BATCH_SIZE = 100
OUTPUT = Path(gifi.app.root_path) / "data" / "steam_text_tag_rebuild_audit.json"


def labels_for(app_id, language):
    response = gifi.requests.get(
        f"{gifi.STEAM_STORE_BASE}/app/{app_id}/",
        params={"cc": "cn", "l": language},
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
    return labels


def fetch(game):
    try:
        return str(game["app_id"]), {
            "name": game["name"],
            "zh": labels_for(game["app_id"], "schinese"),
            "en": labels_for(game["app_id"], "english"),
        }
    except Exception as error:  # noqa: BLE001
        return str(game["app_id"]), {"name": game["name"], "error": str(error)}


def main():
    catalog = sorted(gifi.get_store_catalog(), key=lambda game: -(game.get("review_count") or 0))
    try:
        audit = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        audit = {"version": 1, "batches": [], "games": {}}
    pending = [game for game in catalog if str(game["app_id"]) not in audit["games"]]
    batch = pending[:BATCH_SIZE]
    print(f"待重建 {len(pending)} 款；本批扫描 {len(batch)} 款", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        for app_id, result in executor.map(fetch, batch):
            audit["games"][app_id] = result
    audit["batches"].append([str(game["app_id"]) for game in batch])
    OUTPUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    successes = sum("error" not in audit["games"][str(game["app_id"])] for game in batch)
    print(f"本批完成：{successes}/{len(batch)} 成功；审计缓存现有 {len(audit['games'])} 款。", flush=True)


if __name__ == "__main__":
    main()
