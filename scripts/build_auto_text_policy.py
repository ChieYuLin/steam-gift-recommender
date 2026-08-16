"""Generate rarity-weighted policy entries for all remaining official Steam tags."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "data" / "steam_text_tag_catalog.json"
TEXT_POLICY = ROOT / "golden_labels" / "steam_text_policy.json"
OUTPUT = ROOT / "golden_labels" / "auto_text_policy.json"

# These remain safety signals, not positive preferences.
SAFETY_TAGS = {"Sexual Content", "Adult Content", "Nudity", "Hentai", "Anime Nudity", "Gore", "Violent", "LGBTQ+"}
# These must not become recommendation candidates or evidence, even when rare.
TOOL_TAGS = {
    "Utilities", "Software", "Design & Illustration", "Animation & Modeling",
    "Game Development", "Programming", "Video Production", "Audio Production",
    "Photo Editing", "Software Training", "Desktop Companion", "Benchmark", "Hardware",
}


def weight_for(count):
    if count <= 5:
        return 10
    if count <= 15:
        return 9
    if count <= 40:
        return 8
    if count <= 100:
        return 7
    if count <= 250:
        return 6
    if count <= 500:
        return 5
    if count <= 1000:
        return 4
    return 3


def group_for(weight):
    if weight >= 8:
        return "level_3"
    if weight >= 4:
        return "level_2_core"
    return "soft_preference"


def main():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))["games"]
    text_policy = json.loads(TEXT_POLICY.read_text(encoding="utf-8"))
    managed = set().union(*map(set, text_policy["groups"].values()))
    aliases = set(text_policy.get("aliases", {}))
    counts = {}
    chinese = {}
    for game in catalog.values():
        for english, zh in zip(game["en"], game["zh"]):
            counts[english] = counts.get(english, 0) + 1
            chinese.setdefault(english, zh)

    tags = []
    excluded = []
    key = 9100000
    for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        if label in managed or label in aliases or label in SAFETY_TAGS:
            continue
        weight = weight_for(count)
        entry = {"key": key, "tag": label, "chinese": chinese[label], "game_count": count, "weight": weight, "group": group_for(weight)}
        if label in TOOL_TAGS:
            excluded.append(entry)
        else:
            tags.append(entry)
        key += 1

    output = {"version": 1, "tags": tags, "excluded": excluded}
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT}: {len(tags)} scoring tags, {len(excluded)} excluded tool tags")


if __name__ == "__main__":
    main()
