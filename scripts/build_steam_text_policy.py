"""Create the runtime-ready Steam text-label policy from the legacy id policy.

The output uses full English labels read from official Steam pages, never the
incomplete data-ds-tagids list. It is not yet loaded by app.py; validation comes
before replacing the id-based scoring path.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app as gifi  # noqa: E402

GROUPS = ("level_3", "level_2_core", "soft_preference", "level_1")
OUTPUT = Path(gifi.app.root_path) / "golden_labels" / "steam_text_policy.json"

# Steam's English page spelling for rules whose legacy policy used Chinese names
# or a slightly different community spelling.
ALIASES = {
    "少女游戏": "Otome", "撤离射击": "Extraction Shooter", "足球": "Football (Soccer)",
    "篮球": "Basketball", "竞速": "Racing", "精确平台": "Precision Platformer",
    "社交聚会游戏": "Party Game", "海战": "Naval Combat", "恐龙": "Dinosaurs",
    "超级英雄": "Superhero", "复古射击": "Boomer Shooter", "逆弹幕射击": "Bullet Heaven",
    "武术": "Martial Arts", "清版射击": "Beat 'em up", "合作": "Co-op",
    "玩家对战": "PvP", "本地合作": "Local Co-Op", "在线合作": "Online Co-Op",
    "多人": "Multiplayer", "音乐": "Music", "挂机游戏": "Idler", "增量": "Incremental",
    "生物收集": "Creature Collector", "选择取向": "Choices Matter", "女性主角": "Female Protagonist",
    "第一人称射击": "FPS", "第三人称射击": "Third-Person Shooter",
    "英雄射击": "Hero Shooter", "射击": "Shooter", "角色扮演": "RPG",
    "实时": "Real-Time", "调查": "Colorful", "烹饪": "Cooking", "商店管理": "Shop Keeper",
    "网络梗": "Memes", "温馨惬意": "Wholesome", "猫": "Cats", "刺客": "Assassins",
    "潜行": "Stealth", "解谜": "Puzzle", "平台解谜": "Puzzle Platformer", "逻辑": "Logic",
    "像素图形": "Pixel Graphics", "可爱": "Cute", "动作冒险": "Action-Adventure",
    "隐藏物体": "Hidden Object", "心理": "Psychological", "文字游戏": "Word Game",
    "互动小说": "Interactive Fiction", "基于文字": "Text-Based", "剧情丰富": "Story Rich",
    "黑暗奇幻": "Dark Fantasy", "奇幻": "Fantasy", "动作角色扮演": "Action RPG",
    "风格化": "Stylized", "卡通风格": "Cartoony", "重玩价值": "Replay Value",
    "类塞尔达": "Zelda-like", "类宝可梦": "Pokemon-like", "动画": "Anime",
    "氛围": "Atmospheric", "类魂系列": "Souls-like", "类银河战士恶魔城": "Metroidvania",
    "工作模拟": "Job Simulator", "农场模拟": "Farming Sim", "生活模拟": "Life Sim",
    "农场管理": "Farming", "开放世界生存制作": "Open World Survival Craft",
    "基地建设": "Base Building", "制作": "Crafting", "钓鱼": "Fishing", "密室逃脱": "Escape Room",
    "策略角色扮演": "Strategy RPG", "电脑角色扮演": "CRPG", "日系角色扮演": "JRPG",
    "大型多人在线角色扮演": "MMORPG", "即时战略": "Real-Time with Pause",
    "即时战术": "Real Time Tactics", "回合战略": "Turn-Based Strategy",
    "回合制战术": "Turn-Based Tactics", "大战略": "Grand Strategy", "4X": "4X",
    "塔防": "Tower Defense", "自动战斗": "Auto Battler", "殖民模拟": "Colony Sim",
    "城市营造": "City Builder", "自动化": "Automation", "汽车模拟": "Automobile Sim",
    "太空模拟": "Space Sim", "医疗模拟": "Medical Sim", "疫情模拟": "Outbreak Sim",
    "库存管理": "Inventory Management", "视觉小说": "Visual Novel", "恋爱模拟": "Dating Sim",
    "生存恐怖": "Survival Horror", "心理恐怖": "Psychological Horror", "惊悚": "Thriller",
    "超自然": "Supernatural", "洛夫克拉夫特式": "Lovecraftian", "狩猎": "Hunting",
    "飞行": "Flight", "火车": "Trains", "帆船": "Sailing", "潜艇": "Submarine",
    "推箱子": "Sokoban", "社交推理": "Social Deduction", "三消": "Match 3",
    "节奏": "Rhythm", "赌博": "Gambling", "扑克": "Poker", "麻将": "Mahjong",
    "国际象棋": "Chess", "棋盘游戏": "Board Game", "桌上游戏": "Tabletop",
    "悬疑": "Mystery", "2D": "2D", "3D": "3D", "独立": "Indie",
    "单人": "Singleplayer", "冒险": "Adventure", "动作": "Action", "休闲": "Casual",
    "模拟": "Simulation", "策略": "Strategy", "体育": "Sports", "生存": "Survival",
    "平台游戏": "Platformer", "沙盒": "Sandbox", "探索": "Exploration", "开放世界": "Open World",
    "建造": "Building", "管理": "Management", "驾驶": "Driving", "回合制": "Turn-Based",
    "类 Rogue": "Roguelike", "轻度 Rogue": "Roguelite",
    "Computer RPG": "CRPG", "Farming Management": "Farming", "First-Person Shooter": "FPS",
    "Hand-Drawn": "Hand-drawn", "Real Time": "Real-Time", "Real-Time Strategy": "Real-Time with Pause",
    "Real-Time Tactics": "Real Time Tactics", "Retro Shooter": "Boomer Shooter",
    "Reverse Bullet Hell": "Bullet Heaven", "Role-Playing": "RPG", "Sci-Fi": "Sci-fi",
    "Shopkeeper": "Shop Keeper", "Vampire": "Vampires", "Black Comedy": "Dark Comedy", "Assassin": "Assassins",
}

# These are official Steam text labels that intentionally collapse to a simpler
# preference concept. They are only used for matching; raw text remains intact
# for display and audit.
TEXT_CLEAN_ALIASES = {
    "Local Multiplayer": "Multiplayer",
    "Asynchronous Multiplayer": "Multiplayer",
    "Massively Multiplayer": "Multiplayer",
    "Party": "Party Game",
    "Naval": "Naval Combat",
    "Party-Based RPG": "RPG",
    "2D Platformer": "Platformer",
    "3D Platformer": "Platformer",
    "Turn-Based Combat": "Turn-Based",
    "Real-Time with Pause": "Strategic Command",
    "Real Time Tactics": "Strategic Command",
    "Grand Strategy": "Strategic Command",
}

TEXT_EXTRA_RULES = {}


def canonical(name):
    return ALIASES.get(name, name)


def convert_tags(tag_ids, policy, names):
    return list(dict.fromkeys(canonical(policy[str(tag_id)]) for tag_id in tag_ids if str(tag_id) in policy))


def main():
    legacy = gifi.load_label_policy()
    english_cache = json.loads((Path(gifi.app.root_path) / "data" / "steam_catalog_tag_labels_en.json").read_text(encoding="utf-8"))
    vocabulary = {label for labels in english_cache.values() for label in labels}
    rule_keys = {}
    for group in GROUPS:
        for tag_id, legacy_name in legacy[group].items():
            label = canonical(legacy_name)
            # Prefer the id with an explicit weight when old policy aliases
            # collapse onto one official Steam label (notably Puzzle).
            existing = rule_keys.get(label)
            if existing is None or (tag_id in legacy.get("tag_weights", {}) and existing not in legacy.get("tag_weights", {})):
                rule_keys[label] = int(tag_id)
    for label, rule in TEXT_EXTRA_RULES.items():
        rule_keys[label] = rule["key"]
    groups = {
        group: list(dict.fromkeys(TEXT_CLEAN_ALIASES.get(tag, tag) for tag in convert_tags(legacy[group].keys(), legacy[group], None)))
        for group in GROUPS
    }
    for label, rule in TEXT_EXTRA_RULES.items():
        groups[rule["group"]].append(label)
    weights = {
        canonical(legacy_name): weight
        for tag_id, weight in legacy.get("tag_weights", {}).items()
        for legacy_name in [legacy["level_3"].get(tag_id) or legacy["level_2_core"].get(tag_id) or legacy["soft_preference"].get(tag_id) or legacy["level_1"].get(tag_id) or tag_id]
    }
    weights.update({label: rule["weight"] for label, rule in TEXT_EXTRA_RULES.items()})
    output = {
        "version": 1,
        "source": "Official Steam full English app_tag labels",
        "groups": groups,
        "weights": weights,
        "rule_keys": rule_keys,
        "aliases": TEXT_CLEAN_ALIASES,
        "families": [{"name": family["name"], "tags": [canonical(legacy["level_3"].get(tag_id) or legacy["level_2_core"].get(tag_id) or legacy["soft_preference"].get(tag_id) or legacy["level_1"].get(tag_id) or tag_id) for tag_id in family["tags"]]} for family in legacy.get("tag_match_families", [])],
        "level_3_pairs": [{"name": pair["name"], "tags": [canonical(legacy["level_3"].get(tag_id) or legacy["level_2_core"].get(tag_id) or legacy["soft_preference"].get(tag_id) or legacy["level_1"].get(tag_id) or tag_id) for tag_id in pair["tags"]], **({"min": pair["min"]} if "min" in pair else {})} for pair in legacy.get("level_3_pairs", [])],
        "level_3_pair_weights": legacy.get("level_3_pair_weights", {}),
    }
    missing = sorted({tag for group in output["groups"].values() for tag in group if tag not in vocabulary and not tag.startswith(("Zelda-", "Pokemon-"))})
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT}")
    print(f"Vocabulary {len(vocabulary)}, strategy labels {sum(len(group) for group in output['groups'].values())}, missing {len(missing)}")
    if missing:
        print("Missing:", ", ".join(missing))


if __name__ == "__main__":
    main()
