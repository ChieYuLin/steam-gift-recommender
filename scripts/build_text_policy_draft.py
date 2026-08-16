"""Build a non-runtime text-label policy draft from the current id policy.

This does not change recommendations. It provides a reviewable shadow policy for
moving scoring from Steam's incomplete tag ids to the full visible tag names.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as gifi  # noqa: E402

GROUPS = ("level_3", "level_2_core", "soft_preference", "level_1")
OUTPUT = Path(__file__).resolve().parent.parent / "golden_labels" / "text_label_policy.draft.json"
WEIGHT_LABEL_OVERRIDES = {
    "4604": "黑暗奇幻", "122": "角色扮演", "1742": "剧情丰富", "1684": "奇幻",
    "3920": "烹饪", "91114": "商店管理", "10397": "网络梗",
    "9000001": "类塞尔达", "9000002": "类宝可梦", "4252": "风格化",
    "4195": "卡通风格", "97376": "温馨惬意", "17894": "猫",
    "4231": "动作角色扮演", "31579": "乙女", "42804": "动作类 Rogue",
    "4711": "重玩价值", "97070": "刺客", "1687": "潜行",
    "1663": "第一人称射击", "3814": "第三人称射击", "620519": "英雄射击",
    "1774": "射击", "1664": "解谜", "5537": "平台解谜", "6129": "逻辑",
    "3964": "像素图形", "4726": "可爱", "4106": "动作冒险",
    "1738": "隐藏物体", "5186": "心理",
}


def label_for(tag_id, names, fallback):
    return names.get(int(tag_id), fallback)


def main():
    policy = gifi.load_label_policy()
    names = gifi.get_catalog_tag_name_map()
    output = {
        "status": "shadow-only; not loaded by runtime scoring",
        "source_policy_version": policy.get("version"),
        "groups": {
            group: [label_for(tag_id, names, fallback) for tag_id, fallback in policy[group].items()]
            for group in GROUPS
        },
        "weights": {
            WEIGHT_LABEL_OVERRIDES.get(tag_id, label_for(tag_id, names, tag_id)): weight
            for tag_id, weight in policy.get("tag_weights", {}).items()
        },
        "families": [
            {
                "name": family["name"],
                "tags": [label_for(tag_id, names, tag_id) for tag_id in family["tags"]],
            }
            for family in policy.get("tag_match_families", [])
        ],
        "level_3_pairs": [
            {
                "name": pair["name"],
                "tags": [label_for(tag_id, names, tag_id) for tag_id in pair["tags"]],
                **({"min": pair["min"]} if "min" in pair else {}),
            }
            for pair in policy.get("level_3_pairs", [])
        ],
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT}")
    for group, tags in output["groups"].items():
        print(f"  {group}: {len(tags)} text labels")
    print(f"  weights: {len(output['weights'])}, families: {len(output['families'])}, pairs: {len(output['level_3_pairs'])}")


if __name__ == "__main__":
    main()
