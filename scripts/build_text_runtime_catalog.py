"""Create the runtime text-tag catalog from the audited official Steam pages.

The result is keyed by app id and contains ordered English strategy tags and
Chinese display tags. It deliberately has no Steam tag ids.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIT = ROOT / "data" / "steam_text_tag_rebuild_audit.json"
OUTPUT = ROOT / "data" / "steam_text_tag_catalog.json"


def main():
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    games = {}
    for app_id, entry in audit["games"].items():
        if entry.get("error") or not entry.get("en") or not entry.get("zh"):
            continue
        games[app_id] = {
            "name": entry["name"],
            "en": entry["en"],
            "zh": entry["zh"],
        }
    output = {
        "version": 1,
        "source": "Official Steam app_tag pages fetched with age-confirmation cookies",
        "games": games,
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT}: {len(games)} games")


if __name__ == "__main__":
    main()
