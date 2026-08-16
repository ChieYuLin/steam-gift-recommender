"""Export official Steam labels that have no current text-policy classification."""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "data" / "steam_text_tag_catalog.json"
POLICY = ROOT / "golden_labels" / "steam_text_policy.json"
AUTO_POLICY = ROOT / "golden_labels" / "auto_text_policy.json"
OUTPUT = ROOT / "golden_labels" / "unmanaged_steam_text_tags.json"


def main():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))["games"]
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    auto = json.loads(AUTO_POLICY.read_text(encoding="utf-8"))
    managed = set().union(*map(set, policy["groups"].values()))
    managed.update(entry["tag"] for entry in auto["tags"])
    managed.update(entry["tag"] for entry in auto["excluded"])
    managed.update(policy.get("aliases", {}))
    english_counts = Counter(label for game in catalog.values() for label in game["en"])
    chinese_counts = {}
    for game in catalog.values():
        for english, chinese in zip(game["en"], game["zh"]):
            chinese_counts.setdefault(english, Counter())[chinese] += 1
    tags = [
        {
            "tag": label,
            "chinese": chinese_counts[label].most_common(1)[0][0],
            "game_count": count,
        }
        for label, count in english_counts.items()
        if label not in managed
    ]
    tags.sort(key=lambda entry: (-entry["game_count"], entry["tag"]))
    OUTPUT.write_text(json.dumps({"count": len(tags), "tags": tags}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT}: {len(tags)} unmanaged official tags")


if __name__ == "__main__":
    main()
