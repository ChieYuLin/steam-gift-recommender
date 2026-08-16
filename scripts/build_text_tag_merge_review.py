"""Build a review-only list of proposed official Steam text-tag cleanups."""
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "data" / "steam_text_tag_catalog.json"
POLICY = ROOT / "golden_labels" / "steam_text_policy.json"
OUTPUT = ROOT / "golden_labels" / "text_tag_merge_review.json"

# Only direct aliases or clearly subordinate forms. Nothing here is automatically
# applied to the runtime policy; every item is meant for human review.
PROPOSALS = [
    ("Local Multiplayer", "Multiplayer", "subtype", "本地多人是多人游戏的场景，不应与多人重复计分"),
    ("Asynchronous Multiplayer", "Multiplayer", "subtype", "异步多人是多人游戏的联网形式"),
    ("Massively Multiplayer", "Multiplayer", "subtype", "大型多人在线是多人游戏的规模形式"),
    ("Party", "Party Game", "alias", "社交聚会是 Party Game 的简写"),
    ("Naval", "Naval Combat", "subtype", "海军是海战玩法的更泛表述"),
    ("Party-Based RPG", "RPG", "subtype", "团队角色扮演是角色扮演的队伍结构"),
    ("2D Platformer", "Platformer", "subtype", "二维平台是平台游戏的画面维度"),
    ("3D Platformer", "Platformer", "subtype", "三维平台是平台游戏的画面维度"),
    ("Turn-Based Combat", "Turn-Based", "subtype", "回合制战斗是回合制节奏，不与回合制战略混同"),
    ("Real-Time with Pause", "Strategic Command", "merged", "即时战略、即时战术、大战略合并为战略指挥"),
    ("Real Time Tactics", "Strategic Command", "merged", "即时战略、即时战术、大战略合并为战略指挥"),
    ("Grand Strategy", "Strategic Command", "merged", "即时战略、即时战术、大战略合并为战略指挥"),
]

KEEP_SEPARATE = [
    ("Turn-Based Strategy", "Turn-Based Combat", "回合制战略偏决策/经营；回合制战斗偏战斗节奏，共现约50%，不安全合并"),
    ("Turn-Based Tactics", "Turn-Based Combat", "回合制战术是更具体的策略玩法，不与纯回合制战斗合并"),
    ("Tactical", "Tactical RPG", "战术标签覆盖范围远大于战术 RPG，不安全合并"),
    ("Horror", "Survival Horror", "恐怖与生存恐怖不等价"),
    ("Horror", "Psychological Horror", "恐怖与心理恐怖不等价"),
    ("Cartoon", "Cartoony", "低共现，卡通主题与卡通风格不稳定对应"),
    ("Resource Management", "Management", "资源管理是管理玩法子类，但覆盖过宽，建议独立审核"),
    ("Time Management", "Management", "时间管理是特定玩法循环，建议独立审核"),
    ("First-Person", "FPS", "第一人称不等于第一人称射击"),
    ("Third Person", "Third-Person Shooter", "第三人称不等于第三人称射击"),
    ("Hentai", "Anime Nudity", "两者虽相关但内容墙需更严格、不可简单同义"),
]

# These have meaningful gameplay or theme intent but need a later explicit
# weight/level decision; they should not silently become generic aliases.
REVIEW_AS_PREFERENCE = {
    "Horror": "恐怖类型广泛，建议单独决定软偏好或核心权重",
    "Tactical": "战术比战术角色扮演更宽，建议独立定级",
    "Resource Management": "资源管理有明确玩法意义，建议独立定级",
    "Time Management": "时间管理是特定玩法循环，建议独立定级",
    "War": "战争题材与军事相关但不等价，建议独立定级",
    "Magic": "魔法是高频题材，建议独立定级",
    "Dungeon Crawler": "地牢探索是明确玩法，建议独立定级",
    "Detective": "侦探是明确叙事/推理取向，建议独立定级",
    "Hack and Slash": "砍杀是明确战斗取向，建议独立定级",
    "Loot": "刷宝是明确奖励循环，建议独立定级",
    "Wargame": "战争游戏是军事题材的具体玩法，建议独立定级",
    "Isometric": "等角视角对部分玩家是显著视觉/操作偏好",
    "Walking Simulator": "步行模拟是明确叙事玩法，建议独立定级",
    "Point & Click": "点击冒险是明确交互玩法，建议独立定级",
    "Immersive Sim": "沉浸式模拟是明确玩法流派，建议独立定级",
    "Turn-Based Combat": "已合并到回合制；保留此条供审核确认",
    "Modern": "现代题材可作为软偏好，建议审核",
    "Crime": "犯罪题材可作为软偏好，建议审核",
    "Noir": "黑色电影题材可作为软偏好，建议审核",
    "Political Sim": "政治模拟是明确策略子类，建议独立定级",
    "Diplomacy": "外交是明确策略维度，建议独立定级",
    "Parkour": "跑酷是明确动作玩法，建议独立定级",
    "Mining": "采矿是明确循环玩法，建议独立定级",
    "Agriculture": "农业与农场模拟相关但不完全等价，建议审核",
    "Ninja": "忍者题材可作为软偏好，建议审核",
    "Samurai": "武士题材可作为软偏好，建议审核",
    "Tanks": "坦克是军事题材细分，建议审核",
    "Sniper": "狙击是射击子类，建议审核",
    "Naval": "已合并到海战；保留此条供审核确认",
    "Party": "已合并到社交聚会游戏；保留此条供审核确认",
}


def main():
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))["games"]
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    counts = Counter(label for game in catalog.values() for label in game["en"])
    chinese_counts = {}
    for game in catalog.values():
        for english, chinese in zip(game["en"], game["zh"]):
            chinese_counts.setdefault(english, Counter())[chinese] += 1
    managed = set().union(*map(set, policy["groups"].values()))

    merge = [
        {
            "tag": source,
            "chinese": next((chinese for game in catalog.values() for english, chinese in zip(game["en"], game["zh"]) if english == source), source),
            "game_count": counts[source],
            "merge_into": target,
            "type": kind,
            "reason": reason,
            "currently_managed": source in managed,
        }
        for source, target, kind, reason in PROPOSALS
        if source in counts
    ]
    keep = [
        {
            "left": left,
            "right": right,
            "left_game_count": counts[left],
            "right_game_count": counts[right],
            "reason": reason,
        }
        for left, right, reason in KEEP_SEPARATE
        if left in counts and right in counts
    ]
    merge_sources = {entry["tag"] for entry in merge}
    keep_sources = {entry["left"] for entry in keep}
    unmanaged = []
    for tag, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        if tag in managed:
            continue
        chinese = chinese_counts[tag].most_common(1)[0][0]
        if tag in merge_sources:
            action = "merge"
            reason = next(entry["reason"] for entry in merge if entry["tag"] == tag)
        elif tag in keep_sources:
            action = "keep_separate"
            reason = next(entry["reason"] for entry in keep if entry["left"] == tag)
        elif tag in REVIEW_AS_PREFERENCE:
            action = "review_as_preference"
            reason = REVIEW_AS_PREFERENCE[tag]
        else:
            action = "neutral"
            reason = "通用属性、技术/商店元数据或内容提示；默认不作为偏好加分"
        unmanaged.append({"tag": tag, "chinese": chinese, "game_count": count, "action": action, "reason": reason})
    output = {"merge_candidates": merge, "keep_separate": keep, "all_unmanaged_review": unmanaged}
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUTPUT}: {len(merge)} merge candidates, {len(keep)} keep-separate decisions, {len(unmanaged)} audited unmanaged tags")


if __name__ == "__main__":
    main()
