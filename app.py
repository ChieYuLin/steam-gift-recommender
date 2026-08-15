import html
import json
import math
import os
import random
import re
import time
import uuid
from threading import Lock
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from time import monotonic, sleep
from urllib.parse import urlparse

import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

STEAM_API_BASE = "https://api.steampowered.com"
STEAM_STORE_BASE = "https://store.steampowered.com"
STORE_HEADERS = {"User-Agent": "Gift Scout/1.0 (+local Steam gift recommender)"}
STORE_CACHE_SECONDS = 1800
CATALOG_SNAPSHOT_PATH = Path(app.root_path) / "data" / "store_catalog_cn.json"
CATALOG_CANDIDATES_PATH = Path(app.root_path) / "data" / "store_catalog_candidates_cn.json"
LABEL_POLICY_PATH = Path(app.root_path) / "golden_labels" / "label_policy.json"
APP_TAG_CACHE_PATH = Path(app.root_path) / "data" / "steam_app_tag_cache.json"
ACHIEVEMENT_CACHE_PATH = Path(app.root_path) / "data" / "steam_achievement_cache.json"
FEEDBACK_PATH = Path(app.root_path) / "data" / "feedback.jsonl"
FEEDBACK_IMAGE_DIR = Path(app.root_path) / "data" / "feedback_images"
FEEDBACK_MAX_MESSAGE_CHARS = 4000
FEEDBACK_MAX_IMAGE_BYTES = 4 * 1024 * 1024
feedback_lock = Lock()
APP_NAME_CACHE_PATH = Path(app.root_path) / "data" / "steam_app_name_cn.json"
CATALOG_TAG_LABEL_CACHE_PATH = Path(app.root_path) / "data" / "steam_catalog_tag_labels_cn.json"
store_catalog_cache = {"modified_at": None, "games": [], "tag_name_ids": {}}
live_top_seller_cache = {"updated_at": 0, "app_ids": set()}
SEARCH_PAGE_SIZE = 50
SEARCH_PAGE_DELAY_SECONDS = 1.5
TOP_SELLER_PAGE_COUNT = 40
POPULAR_NEW_PAGE_COUNT = 15
RECENT_RELEASE_PAGE_COUNT = 20
SPECIALS_PAGE_COUNT = 40
MIN_CATALOG_SIZE = 150
TARGET_CATALOG_SIZE = 3000
CATALOG_BATCH_SIZE = 100
NEW_RELEASE_WINDOW_DAYS = 31
PREFERENCE_GAME_LIMIT = 120
MIN_PREFERENCE_PLAYTIME_MINUTES = 120
MAX_LABELS_PER_REPRESENTATIVE_GAME = 5
# Tag IDs are resolved from the full page tag list (~18 per game), so these
# windows now bind meaningfully instead of covering everything available.
CORE_TAG_RANK_LIMIT = 10
SOFT_TAG_RANK_LIMIT = 10
LEVEL_3_TAG_RANK_LIMIT = 10
CORE_TAG_MATCH_LIMIT = 5
LEVEL_1_TAG_MATCH_LIMIT = 5
SOFT_TAG_MATCH_LIMIT = 5
# Counting matches alone produces a coarse integer score where many candidates
# tie. Weighting each match by where the tag sits on the candidate's own store
# page separates "this is what the game is about" from "the game also has this".
TAG_RANK_DECAY_PER_POSITION = 0.05
MIN_TAG_RANK_FACTOR = 0.5
# A tag backed by several deeply played games is a stronger preference signal
# than one backed by a single lightly played game.
TAG_EVIDENCE_BREADTH_TARGET = 3
TAG_STRENGTH_BASE = 0.35
TAG_STRENGTH_BREADTH_WEIGHT = 0.35
TAG_STRENGTH_DEPTH_WEIGHT = 0.3
# A Level 3 tag carries nearly double the weight of a core tag, so one side label
# on one lightly played game must not unlock it. Rather than demoting the tag
# outright, its weight scales with how much play actually backs it up: only the
# games where it is a defining tag count, and both their number and their hours.
LEVEL_3_CONFIRMING_RANK_LIMIT = 5
LEVEL_3_MIN_CONFIRMING_SOURCES = 2
LEVEL_3_UNCONFIRMED_FLOOR = 0.4
# Idle games and desktop companions run in the background, so Steam records wall
# clock time rather than time TA chose to spend. Their hours are discounted so
# owning a shelf of them cannot outrank a game actually played.
PASSIVE_PLAYTIME_RANK_LIMIT = 5
PASSIVE_PLAYTIME_FACTOR = 0.2
# Cited games should be ones the gift giver actually remembers, so evidence is
# drawn super-linearly towards the more deeply played sources of a tag.
EVIDENCE_ENGAGEMENT_EXPONENT = 2
# The Level 3 layer holds only two tags so far, and its 10-point weight lets one
# of them fill a whole batch.
MAX_SAME_LEVEL_3_TAG_PER_BATCH = 2
# A well-known title gets up to this much extra pull in the draw, so batches are
# not filled with obscure games that happen to carry a dense tag list.
POPULARITY_WEIGHT_CEILING = 4.0
# Recognisable titles are prioritised on every page, not just the opening ones.
# The top-up is drawn from the high-scoring end so chasing popularity cannot pull
# in a well-known game that barely matches.
POOL_WELL_KNOWN_TARGET = 8
MIN_WELL_KNOWN_PER_BATCH = 2
WELL_KNOWN_TOPUP_DEPTH = 80
FRESH_AND_POPULAR_BONUS = 1.4
TOP_SELLER_BONUS = 1.3
# Below this a game is not something to hand someone as a present.
ACCLAIM_MIN_POSITIVE_RATE = 80
ACCLAIM_WEIGHT = 1.5
LEVEL_3_WINDOW_CARDS = 8
MAX_LEVEL_3_CARDS_PER_WINDOW = 1
# A couple of hints are enough to explain a middling score without turning the
# card into a list of everything the game is not.
MAX_MATCH_GAPS = 2
# Only headline tags count as a mismatch worth mentioning.
GAP_TAG_RANK_LIMIT = 6
# A game leading with tastes the target does not share is a worse gift than its
# incidental tag overlap suggests, and the higher those tags sit the worse it is.
MISMATCH_WEIGHT = 0.22
MISMATCH_RANK_EXPONENT = 3
MISMATCH_MIN_FACTOR = 0.45
# Two tags mean much the same thing when most games carrying one carry the other.
TAG_OVERLAP_MIN_SHARE = 0.6
TAG_OVERLAP_MIN_GAMES = 8
TAG_OVERLAP_MAX_PARTNER_SHARE = 0.2
# A run of ordinary cards should still owe the gift giver a standout, so a tier
# that has not appeared within its window is forced into the next batch.
SR_PITY_CARDS = 12
SSR_PITY_CARDS = 36
# Front-loading the best cards leaves nothing to discover, so at most one high
# grade per page and the very top grade only after the opening pages.
MAX_HIGH_TIER_PER_BATCH = 1
SSR_EARLIEST_CARD = 8
UR_EARLIEST_CARD = 20
# One narrow taste in the library should not turn a whole batch into the same
# genre, which is how a single dating sim produced four visual novel cards.
MAX_SAME_CORE_TAG_PER_BATCH = 2
# Citing the same owned game on back-to-back cards reads as thin research.
EVIDENCE_REUSE_LOOKBACK = 2
# Within one card the opposite is true: one owned game explaining several matched
# tags is stronger evidence than three games explaining one tag each.
EVIDENCE_SAME_CARD_BONUS = 25
# The raw score has no natural ceiling and its absolute size depends on how many
# tags a profile happens to carry, so a fixed divisor made every result look the
# same. The 0-100 scale is instead anchored to this user's own score spread.
MATCH_PERCENT_BASELINE_PERCENTILE = 30
# Seed mode scores only the gift giver's own library, so a percentile tuned for the
# 3000-game catalogue would leave almost nothing above the baseline and report 0
# for most cards. Keep a minimum number of candidates above it.
MATCH_PERCENT_MIN_ABOVE_BASELINE = 24
# Each confidence tier owns a band, so a glance at the number tells the depth of
# the match instead of every card landing in the same narrow range.
# The number reports how deep the overlap actually is, not how a game ranks among
# whatever else was available: two core tags always reads in the forties whether
# the pool is the whole catalogue or one small library.
# A fixed depth-to-percent table always drifts: one profile tops out at depth 4,
# another at 7, so both squeeze into a narrow slice. The scale is anchored to
# this profile's own distribution instead.
MATCH_PERCENT_BASELINE_ANCHOR = 40
# The best match found is not a perfect match, so the top of the scale sits just
# above anything the catalogue actually offers and 100 stays out of reach.
MATCH_CEILING_HEADROOM = 1.12
MATCH_CEILING_PERCENTILE = 99.5
# Without a fixed reference the scale would stretch to whatever this library can
# reach, handing the top grade to every profile's best result. This is the depth
# that reads as an outstanding match, so weak profiles top out lower.
# A small or scattered library simply cannot reach deep matches, so pinning the
# top of the scale to a fixed depth left those users permanently in the forties.
# The scale follows what this profile can actually reach; the floor only stops a
# nearly empty profile from calling its best guess a perfect match.
MATCH_DEPTH_FLOOR = 2.6
# The scale is built on the two deep layers. Broad-taste-only matches would all
# read a flat zero, so they get a small band of their own below the main scale.
DEPTH_GROUP_WEIGHT = {"level_3": 2.0, "level_2_core": 1.0}
# Above 1 the strongest matches dominate, so hitting two tags squarely beats
# brushing five. At 1 this reduces to the old plain sum.
MATCH_DEPTH_CONCENTRATION = 2.0
SHALLOW_GROUP_WEIGHT = {"soft_preference": 1 / 3, "level_1": 1 / 6}
SHALLOW_MAX_PERCENT = 22
SHALLOW_FULL_CREDIT = 1.2
# Candidate depths bunch together, so differences are amplified around the level
# a typical shown card reaches.
MATCH_PERCENT_PIVOT = 0.4
MATCH_PERCENT_SPREAD = 1.5
# Rarity is read straight off the number on the card, so a high score can never
# be labelled common. Each entry is (minimum percent, name, explanation).
MATCH_RARITY_TIERS = [
    (95, "UR", "\u5b9d\u85cf\u7ea7\uff1a\u591a\u4e2a\u62db\u724c\u73a9\u6cd5\u6df1\u5ea6\u91cd\u5408"),
    (88, "SSR", "\u6781\u54c1\uff1a\u62db\u724c\u73a9\u6cd5\u52a0\u591a\u5904\u6838\u5fc3\u91cd\u5408"),
    (78, "SR", "\u7a00\u6709\uff1a\u591a\u4e2a\u6838\u5fc3\u73a9\u6cd5\u91cd\u5408"),
    (65, "R", "\u826f\u54c1\uff1a\u6709\u5c11\u91cf\u6838\u5fc3\u91cd\u5408"),
    (0, "N", "\u666e\u901a\uff1a\u4e3b\u8981\u662f\u5bbd\u6cdb\u7c7b\u578b\u91cd\u5408"),
]
ACHIEVEMENT_CACHE_SECONDS = 3600
REVIEW_CACHE_SECONDS = 21600
achievement_cache = {}
achievement_cache_dirty = set()
review_cache = {}
catalog_tag_label_cache_lock = Lock()
CATALOG = [
    {"app_id": 413150, "name": "Stardew Valley", "genres": ["indie", "simulation", "rpg"], "price_note": "通常价格亲民", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/413150/header.jpg"},
    {"app_id": 1245620, "name": "ELDEN RING", "genres": ["action", "rpg"], "price_note": "适合大作预算", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1245620/header.jpg"},
    {"app_id": 1145360, "name": "Hades", "genres": ["action", "indie", "rpg"], "price_note": "中等价位", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1145360/header.jpg"},
    {"app_id": 413410, "name": "Doom", "genres": ["action"], "price_note": "经常参加促销", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/413410/header.jpg"},
    {"app_id": 1091500, "name": "Cyberpunk 2077", "genres": ["action", "rpg"], "price_note": "适合大作预算", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1091500/header.jpg"},
    {"app_id": 1150690, "name": "OMORI", "genres": ["indie", "rpg"], "price_note": "通常价格亲民", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1150690/header.jpg"},
    {"app_id": 1086940, "name": "Baldur's Gate 3", "genres": ["adventure", "rpg", "strategy"], "price_note": "适合大作预算", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1086940/header.jpg"},
    {"app_id": 526870, "name": "Satisfactory", "genres": ["simulation", "strategy"], "price_note": "中等价位", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/526870/header.jpg"},
    {"app_id": 367520, "name": "Hollow Knight", "genres": ["action", "indie"], "price_note": "通常价格亲民", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/367520/header.jpg"},
    {"app_id": 359550, "name": "Tom Clancy's Rainbow Six Siege", "genres": ["action", "multiplayer"], "price_note": "经常参加促销", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/359550/header.jpg"},
    {"app_id": 292030, "name": "The Witcher 3: Wild Hunt", "genres": ["adventure", "rpg"], "price_note": "经常参加促销", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/292030/header.jpg"},
    {"app_id": 1222670, "name": "The Sims 4", "genres": ["simulation"], "price_note": "可免费开始体验", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1222670/header.jpg"},
    {"app_id": 239140, "name": "Dying Light", "genres": ["action", "rpg"], "price_note": "经常参加促销", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/239140/header.jpg"},
    {"app_id": 105600, "name": "Terraria", "genres": ["action", "indie", "simulation"], "price_note": "通常价格亲民", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/105600/header.jpg"},
    {"app_id": 620, "name": "Portal 2", "genres": ["adventure", "puzzle"], "price_note": "经常参加促销", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/620/header.jpg"},
    {"app_id": 271590, "name": "Grand Theft Auto V", "genres": ["action", "multiplayer"], "price_note": "适合大作预算", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/271590/header.jpg"},
    {"app_id": 440, "name": "Team Fortress 2", "genres": ["action", "multiplayer"], "price_note": "可免费开始体验", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/440/header.jpg"},
    {"app_id": 255710, "name": "Cities: Skylines", "genres": ["simulation", "strategy"], "price_note": "经常参加促销", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/255710/header.jpg"},
    {"app_id": 881100, "name": "Noita", "genres": ["action", "indie"], "price_note": "通常价格亲民", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/881100/header.jpg"},
    {"app_id": 1174180, "name": "Red Dead Redemption 2", "genres": ["action", "adventure"], "price_note": "适合大作预算", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1174180/header.jpg"},
    {"app_id": 1222140, "name": "Detroit: Become Human", "genres": ["adventure", "story"], "price_note": "中等价位", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/1222140/header.jpg"},
    {"app_id": 632360, "name": "Risk of Rain 2", "genres": ["action", "indie", "multiplayer"], "price_note": "中等价位", "image": "https://cdn.cloudflare.steamstatic.com/steam/apps/632360/header.jpg"},
]

GENRE_NAMES = {
    "动作": "action", "action": "action", "角色扮 演": "rpg", "角色扮演": "rpg", "rpg": "rpg",
    "模拟": "simulation", "simulation": "simulation", "策略": "strategy", "strategy": "strategy",
    "独立": "indie", "indie": "indie", "冒险": "adventure", "adventure": "adventure",
    "多人": "multiplayer", "大型多人在线": "multiplayer", "massively multiplayer": "multiplayer",
}


def extract_steam_id(profile_input):
    value = profile_input.strip()
    if re.fullmatch(r"\d{17}", value):
        return value

    parsed = urlparse(value if "://" in value else f"https://{value}")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "profiles" and re.fullmatch(r"\d{17}", parts[1]):
        return parts[1]
    if len(parts) >= 2 and parts[0] == "id":
        return {"vanity": parts[1]}
    raise ValueError("请输入 17 位 SteamID，或 steamcommunity.com/id/... / profiles/... 个人资料链接。")


def steam_get(path, params):
    response = requests.get(f"{STEAM_API_BASE}{path}", params=params, timeout=12)
    response.raise_for_status()
    return response.json()


def resolve_steam_id(profile_input, api_key):
    identifier = extract_steam_id(profile_input)
    if isinstance(identifier, str):
        return identifier
    payload = steam_get(
        "/ISteamUser/ResolveVanityURL/v1/",
        {"key": api_key, "vanityurl": identifier["vanity"]},
    )
    steam_id = payload.get("response", {}).get("steamid")
    if not steam_id:
        raise ValueError("无法找到该 Steam 个人资料。请确认链接或 SteamID 是否正确。")
    return steam_id


def get_profile_and_library(steam_id, api_key):
    profile_data = steam_get(
        "/ISteamUser/GetPlayerSummaries/v2/", {"key": api_key, "steamids": steam_id}
    )
    players = profile_data.get("response", {}).get("players", [])
    if not players:
        raise ValueError("无法读取该 Steam 个人资料。")
    if players[0].get("communityvisibilitystate") != 3:
        raise ValueError("此个人资料不是公开状态，Steam 不允许读取其拥有的游戏。")

    library_data = steam_get(
        "/IPlayerService/GetOwnedGames/v1/",
        {"key": api_key, "steamid": steam_id, "include_appinfo": "true", "include_played_free_games": "true"},
    )
    games = library_data.get("response", {}).get("games")
    if games is None:
        raise ValueError("Steam 未返回游戏库；请确认该用户的“游戏详情”隐私设置为公开。")
    return players[0], games


def format_price(price_in_fen):
    return f"¥{price_in_fen / 100:.2f}"


def get_game_price(game):
    if "final_price" in game:
        return game["final_price"] / 100
    match = re.search(r"¥([0-9.]+)", game.get("price_note", ""))
    return float(match.group(1)) if match else None


@lru_cache(maxsize=8192)
def parse_release_date(release_date):
    for date_format in ("%d %b, %Y", "%b %d, %Y", "%Y 年 %m 月 %d 日", "%Y年%m月%d日"):
        try:
            return datetime.strptime(release_date, date_format).replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            continue
    return None


def is_recent_release(release_date, now=None):
    released_at = parse_release_date(release_date)
    if not released_at:
        return False
    now = now or datetime.now(timezone.utc)
    return now - timedelta(days=NEW_RELEASE_WINDOW_DAYS) <= released_at <= now + timedelta(days=1)


def store_json(path, params):
    last_error = None
    # Five attempts with a growing pause could stall a request for over a minute
    # when Steam throttles, which reads as a hang rather than a slow lookup.
    for attempt in range(3):
        try:
            response = requests.get(f"{STEAM_STORE_BASE}{path}", params=params, headers=STORE_HEADERS, timeout=8)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                return payload
            raise ValueError("Steam 返回的不是 JSON 对象。")
        except (requests.RequestException, ValueError, TypeError) as error:
            last_error = error
            if attempt < 2:
                sleep(0.8 * (attempt + 1))
    raise requests.RequestException(f"Steam 商店请求失败：{last_error}")


def get_store_game_details(item, source, category_id, include_reviews=True, store_categories=None):
    app_id = item["id"]
    tag_ids = item.get("tag_ids") or fetch_app_tags_and_name(app_id)[0]
    tag_labels = get_catalog_tag_labels(app_id)
    payload = store_json("/api/appdetails", {"appids": app_id, "cc": "cn", "l": "schinese"})
    entry = payload.get(str(app_id), {})
    data = entry.get("data", {}) if entry.get("success") else {}
    if data.get("type") != "game":
        return None
    genres = [GENRE_NAMES.get(genre["description"].lower(), genre["description"].lower()) for genre in data.get("genres", [])]
    if not genres:
        return None
    price_overview = data.get("price_overview", {})
    original_price = item.get("original_price", price_overview.get("initial", 0))
    final_price = item.get("final_price", price_overview.get("final", 0))
    if not final_price:
        return None
    discount_percent = item.get("discount_percent", price_overview.get("discount_percent", 0))
    review_count = 0
    positive_rate = None
    if include_reviews:
        review_summary = store_json(
            f"/appreviews/{app_id}", {"json": 1, "language": "schinese", "purchase_type": "all", "num_per_page": 0}
        ).get("query_summary", {})
        review_count = review_summary.get("total_reviews", 0)
        positive_rate = round(100 * review_summary.get("total_positive", 0) / review_count) if review_count else None
    price_note = f"中国区现价 {format_price(final_price)}"
    if discount_percent:
        price_note += f"，限时 {discount_percent}% 折扣（原价 {format_price(original_price)}）"
    release_date = data.get("release_date", {}).get("date", "发售日期待定")
    categories = set(store_categories or [category_id])
    if "new_releases" in categories and not is_recent_release(release_date):
        categories.remove("new_releases")
    if not categories:
        return None
    primary_category = category_id if category_id in categories else sorted(categories)[0]
    return {
        "app_id": app_id,
        "name": data.get("name", item.get("name", f"Steam App {app_id}")),
        "game_type": data["type"],
        "genres": genres,
        "tag_ids": tag_ids,
        "tag_labels": tag_labels,
        "final_price": final_price,
        "original_price": original_price,
        "discount_percent": discount_percent,
        "price_note": price_note,
        "image": item.get("header_image", data.get("header_image", "")),
        "store_source": source,
        "store_category": primary_category,
        "store_categories": sorted(categories),
        "release_date": release_date,
        "positive_rate": positive_rate,
        "review_count": review_count,
    }


def get_store_search_items(search_params, page_count):
    items = {}
    failed_pages = []
    for page in range(page_count):
        if page:
            sleep(SEARCH_PAGE_DELAY_SECONDS)
        try:
            payload = store_json(
                "/search/results/",
                {
                    "query": "", "start": page * SEARCH_PAGE_SIZE, "count": SEARCH_PAGE_SIZE,
                    "dynamic_data": "", "infinite": 1, "cc": "cn", **search_params,
                },
            )
        except requests.RequestException:
            failed_pages.append(page)
            continue
        page_items = re.findall(
            r'data-ds-appid=\\?"(\d+)"[^>]*data-ds-tagids=\\?"(\[[^\"]+\])',
            payload.get("results_html", ""),
        )
        for app_id, tag_ids in page_items:
            items.setdefault(int(app_id), {"id": int(app_id), "tag_ids": json.loads(tag_ids)})
    return list(items.values()), failed_pages


def get_live_top_seller_ids():
    if monotonic() - live_top_seller_cache["updated_at"] < STORE_CACHE_SECONDS:
        return live_top_seller_cache["app_ids"]
    try:
        items, _ = get_store_search_items({"filter": "topsellers"}, 1)
        app_ids = {item["id"] for item in items}
    except requests.RequestException:
        return live_top_seller_cache["app_ids"]
    live_top_seller_cache.update(updated_at=monotonic(), app_ids=app_ids)
    return app_ids


def collect_store_candidates():
    data = store_json("/api/featuredcategories/", {"cc": "cn", "l": "schinese"})
    source_names = {"top_sellers": "中国区热销", "specials": "中国区优惠", "new_releases": "中国区新品"}
    candidates = {}

    def add_candidate(item, source, category_id, include_reviews):
        existing = candidates.get(item["id"])
        if existing:
            existing["categories"].add(category_id)
            existing["include_reviews"] = existing["include_reviews"] or include_reviews
            existing["item"].setdefault("tag_ids", item.get("tag_ids", []))
            return
        candidates[item["id"]] = {
            "item": item,
            "source": source,
            "primary_category": category_id,
            "categories": {category_id},
            "include_reviews": include_reviews,
        }

    for category_id, source in source_names.items():
        for item in data.get(category_id, {}).get("items", []):
            if item.get("type") in (0, "app"):
                add_candidate(item, source, category_id, True)
    backup_sources = [
        ("top_sellers", "中国区热销", {"filter": "topsellers"}, TOP_SELLER_PAGE_COUNT),
        ("highly_rated", "高评价精选", {"sort_by": "Reviews_DESC", "supportedlang": "schinese"}, SPECIALS_PAGE_COUNT),
        ("specials", "中国区优惠", {"specials": 1}, SPECIALS_PAGE_COUNT),
        ("new_releases", "中国区热门新品", {"filter": "popularnew", "sort_by": "Released_DESC", "os": "win"}, POPULAR_NEW_PAGE_COUNT),
        ("new_releases", "中国区最新发售", {"sort_by": "Released_DESC", "os": "win"}, RECENT_RELEASE_PAGE_COUNT),
    ]
    for category_id, source, search_params, page_count in backup_sources:
        items, _ = get_store_search_items(search_params, page_count)
        for item in items:
            add_candidate(item, source, category_id, False)
    return [
        {
            "item": candidate["item"],
            "source": candidate["source"],
            "primary_category": candidate["primary_category"],
            "categories": sorted(candidate["categories"]),
            "include_reviews": candidate["include_reviews"],
        }
        for candidate in candidates.values()
    ]


def prepare_store_catalog_candidates():
    candidates = collect_store_candidates()
    snapshot = {"generated_at": datetime.now(timezone.utc).isoformat(), "candidates": candidates}
    CATALOG_CANDIDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = CATALOG_CANDIDATES_PATH.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    temporary_path.replace(CATALOG_CANDIDATES_PATH)
    return snapshot


def load_store_catalog_candidates():
    try:
        return json.loads(CATALOG_CANDIDATES_PATH.read_text(encoding="utf-8")).get("candidates", [])
    except (OSError, ValueError, TypeError):
        return []


def load_catalog_tag_label_cache():
    try:
        return json.loads(CATALOG_TAG_LABEL_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def fetch_app_tag_labels(app_id):
    page = requests.get(
        f"{STEAM_STORE_BASE}/app/{app_id}/",
        params={"cc": "cn", "l": "schinese"},
        headers=STORE_HEADERS,
        timeout=12,
    )
    page.raise_for_status()
    labels = [
        re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", label)).strip()
        for label in re.findall(r'<a[^>]*class="app_tag[^>]*>(.*?)</a>', page.text, re.S)
    ]
    return list(dict.fromkeys(label for label in labels if label))


def get_catalog_tag_labels(app_id):
    with catalog_tag_label_cache_lock:
        cache = load_catalog_tag_label_cache()
        cached = cache.get(str(app_id))
        if cached:
            return cached
    try:
        labels = fetch_app_tag_labels(app_id)
    except requests.RequestException:
        return []
    if labels:
        with catalog_tag_label_cache_lock:
            cache = load_catalog_tag_label_cache()
            cache[str(app_id)] = labels
            CATALOG_TAG_LABEL_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            CATALOG_TAG_LABEL_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return labels


def build_store_catalog(candidates=None):
    candidates = candidates if candidates is not None else collect_store_candidates()
    games = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(
                get_store_game_details,
                candidate["item"],
                candidate["source"],
                candidate["primary_category"],
                candidate["include_reviews"],
                candidate["categories"],
            )
            for candidate in candidates
        ]
        for future in as_completed(futures):
            try:
                game = future.result()
                if game and game.get("tag_ids"):
                    games.append(game)
            except (requests.RequestException, ValueError, TypeError, AttributeError):
                continue
    return games


def refresh_store_catalog():
    games = build_store_catalog()
    if len(games) < MIN_CATALOG_SIZE:
        raise RuntimeError(f"只获取到 {len(games)} 个有效商店条目，保留现有缓存。")
    CATALOG_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {"generated_at": datetime.now(timezone.utc).isoformat(), "games": games}
    temporary_path = CATALOG_SNAPSHOT_PATH.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    temporary_path.replace(CATALOG_SNAPSHOT_PATH)
    store_catalog_cache.update(modified_at=CATALOG_SNAPSHOT_PATH.stat().st_mtime, games=games)
    return snapshot


def get_store_app_type(app_id):
    payload = store_json("/api/appdetails", {"appids": app_id, "cc": "cn", "l": "schinese"})
    entry = payload.get(str(app_id), {})
    data = entry.get("data", {}) if entry.get("success") else {}
    return data.get("type")


def verify_catalog_game_types_batch(batch_size=CATALOG_BATCH_SIZE):
    try:
        snapshot = json.loads(CATALOG_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        games = snapshot.get("games", [])
    except (OSError, ValueError, TypeError):
        raise RuntimeError("当前目录快照不可读取，无法验证 Steam 内容类型。")

    pending_games = [game for game in games if game.get("game_type") != "game"][:batch_size]
    if not pending_games:
        return snapshot, 0, 0

    verified_types = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(get_store_app_type, game["app_id"]): game["app_id"] for game in pending_games}
        for future in as_completed(futures):
            app_id = futures[future]
            try:
                verified_types[app_id] = future.result()
            except requests.RequestException:
                continue

    verified_game_ids = {app_id for app_id, game_type in verified_types.items() if game_type == "game"}
    verified_non_game_ids = {app_id for app_id, game_type in verified_types.items() if game_type and game_type != "game"}
    updated_games = []
    for game in games:
        app_id = game["app_id"]
        if app_id in verified_non_game_ids:
            continue
        if app_id in verified_game_ids:
            updated_games.append({**game, "game_type": "game"})
        else:
            updated_games.append(game)

    snapshot.update(
        generated_at=datetime.now(timezone.utc).isoformat(),
        games=updated_games,
        game_type_verification_pending=sum(game.get("game_type") != "game" for game in updated_games),
    )
    temporary_path = CATALOG_SNAPSHOT_PATH.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    temporary_path.replace(CATALOG_SNAPSHOT_PATH)
    store_catalog_cache.update(modified_at=CATALOG_SNAPSHOT_PATH.stat().st_mtime, games=updated_games)
    return snapshot, len(verified_types), len(verified_non_game_ids)


def backfill_catalog_tag_labels_batch(batch_size=CATALOG_BATCH_SIZE):
    try:
        snapshot = json.loads(CATALOG_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        games = snapshot.get("games", [])
    except (OSError, ValueError, TypeError):
        raise RuntimeError("当前目录快照不可读取，无法回填中文标签。")

    pending_games = [game for game in games if game.get("tag_ids") and not game.get("tag_labels")][:batch_size]
    if not pending_games:
        return snapshot, 0, 0

    labels_by_app_id = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(get_catalog_tag_labels, game["app_id"]): game["app_id"] for game in pending_games}
        for future in as_completed(futures):
            app_id = futures[future]
            try:
                labels = future.result()
            except requests.RequestException:
                continue
            if labels:
                labels_by_app_id[app_id] = labels

    updated_games = [
        {**game, "tag_labels": labels_by_app_id[game["app_id"]]} if game["app_id"] in labels_by_app_id else game
        for game in games
    ]
    snapshot.update(
        generated_at=datetime.now(timezone.utc).isoformat(),
        games=updated_games,
        tag_label_backfill_pending=sum(bool(game.get("tag_ids")) and not bool(game.get("tag_labels")) for game in updated_games),
    )
    temporary_path = CATALOG_SNAPSHOT_PATH.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    temporary_path.replace(CATALOG_SNAPSHOT_PATH)
    store_catalog_cache.update(modified_at=CATALOG_SNAPSHOT_PATH.stat().st_mtime, games=updated_games)
    return snapshot, len(pending_games), len(labels_by_app_id)


def fetch_global_review_counts(app_id):
    # "all" languages, because this is a fame signal rather than a China-store signal.
    summary = store_json(
        f"/appreviews/{app_id}", {"json": 1, "language": "all", "purchase_type": "all", "num_per_page": 0}
    ).get("query_summary", {})
    total = summary.get("total_reviews", 0) or 0
    positive = summary.get("total_positive", 0) or 0
    return total, (round(100 * positive / total) if total else None)


def backfill_catalog_review_counts_batch(batch_size=CATALOG_BATCH_SIZE):
    try:
        snapshot = json.loads(CATALOG_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        games = snapshot.get("games", [])
    except (OSError, ValueError, TypeError):
        raise RuntimeError("当前目录快照不可读取，无法回填评测数量。")

    pending_games = [game for game in games if not game.get("review_checked")][:batch_size]
    if not pending_games:
        return snapshot, 0, 0

    reviews_by_app_id = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(fetch_global_review_counts, game["app_id"]): game["app_id"] for game in pending_games}
        for future in as_completed(futures):
            app_id = futures[future]
            try:
                reviews_by_app_id[app_id] = future.result()
            except (requests.RequestException, ValueError, TypeError):
                continue

    updated_games = [
        {
            **game,
            "review_count": reviews_by_app_id[game["app_id"]][0],
            "positive_rate": reviews_by_app_id[game["app_id"]][1],
            "review_checked": True,
        }
        if game["app_id"] in reviews_by_app_id else game
        for game in games
    ]
    snapshot.update(
        generated_at=datetime.now(timezone.utc).isoformat(),
        games=updated_games,
        review_backfill_pending=sum(not game.get("review_checked") for game in updated_games),
    )
    temporary_path = CATALOG_SNAPSHOT_PATH.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    temporary_path.replace(CATALOG_SNAPSHOT_PATH)
    store_catalog_cache.update(modified_at=CATALOG_SNAPSHOT_PATH.stat().st_mtime, games=updated_games)
    return snapshot, len(pending_games), len(reviews_by_app_id)


def merged_game_has_labels(games, app_id):
    return any(game.get("app_id") == app_id and bool(game.get("tag_labels")) for game in games)

def refresh_store_catalog_batch(batch_size=CATALOG_BATCH_SIZE):
    candidates = load_store_catalog_candidates()
    if not candidates:
        prepare_store_catalog_candidates()
        candidates = load_store_catalog_candidates()
    if not candidates:
        raise RuntimeError("未能获取 Steam 商店候选清单。")
    try:
        existing_snapshot = json.loads(CATALOG_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        existing_games = existing_snapshot.get("games", [])
        processed_candidate_ids = set(existing_snapshot.get("processed_candidate_ids", []))
    except (OSError, ValueError, TypeError):
        existing_games = []
        processed_candidate_ids = set()
    existing_ids = {game.get("app_id") for game in existing_games}
    pending = [
        candidate for candidate in candidates
        if candidate["item"]["id"] not in processed_candidate_ids
        and (candidate["item"]["id"] not in existing_ids
        or not merged_game_has_labels(existing_games, candidate["item"]["id"])
        )
    ]
    batch = pending[:batch_size]
    added_games = build_store_catalog(batch)
    merged_games = {game["app_id"]: game for game in existing_games}
    merged_games.update({game["app_id"]: game for game in added_games})
    processed_candidate_ids.update(candidate["item"]["id"] for candidate in batch)
    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "games": list(merged_games.values()),
        "catalog_target": TARGET_CATALOG_SIZE,
        "candidate_count": len(candidates),
        "pending_candidates": max(0, len(pending) - len(batch)),
        "processed_candidate_ids": sorted(processed_candidate_ids),
    }
    temporary_path = CATALOG_SNAPSHOT_PATH.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    temporary_path.replace(CATALOG_SNAPSHOT_PATH)
    store_catalog_cache.update(modified_at=CATALOG_SNAPSHOT_PATH.stat().st_mtime, games=snapshot["games"])
    return snapshot, len(batch), len(added_games)


def build_tag_name_id_map(games):
    # Steam's data-ds-tagids attribute stops at 7 entries while the page lists ~20
    # tag names. Those first 7 are positionally aligned with the names, so they
    # yield a name to ID dictionary that can resolve the remaining names.
    votes = defaultdict(Counter)
    for game in games:
        for tag_id, label in zip(game.get("tag_ids") or [], game.get("tag_labels") or []):
            votes[label][tag_id] += 1
    return {label: counts.most_common(1)[0][0] for label, counts in votes.items()}


def get_tag_name_id_map():
    get_store_catalog()
    return store_catalog_cache["tag_name_ids"]


@lru_cache(maxsize=1)
def get_tag_overlap_map(catalog_size):
    """Tags that almost always travel together, keyed by tag id.

    A compound tag like deck-building roguelike is not a new interest for
    someone who already likes deck-building and roguelikes, so it must not be
    reported as something the target dislikes.
    """
    counts = Counter()
    together = defaultdict(Counter)
    for game in get_store_catalog():
        tag_ids = set(game.get("tag_ids", []))
        for tag_id in tag_ids:
            counts[tag_id] += 1
            for other in tag_ids:
                if other != tag_id:
                    together[tag_id][other] += 1
    names = get_catalog_tag_name_map()
    overlap = {
        tag_id: {
            other for other, shared in partners.items()
            if shared / counts[tag_id] >= TAG_OVERLAP_MIN_SHARE
            # A tag on three quarters of the catalogue co-occurs with everything
            # and says nothing about meaning.
            and counts[other] / catalog_size < TAG_OVERLAP_MAX_PARTNER_SHARE
        }
        for tag_id, partners in together.items()
        if counts[tag_id] >= TAG_OVERLAP_MIN_GAMES
    }
    # Chinese tag names spell the relation out: turn-based combat is turn-based.
    # Co-occurrence alone misses these when the narrower tag is rare.
    for tag_id, name in names.items():
        for other, other_name in names.items():
            if tag_id != other and len(other_name) >= 2 and other_name in name:
                overlap.setdefault(tag_id, set()).add(other)
                overlap.setdefault(other, set()).add(tag_id)
    return overlap


def resolve_full_tag_ids(tag_ids, tag_labels, name_map):
    tag_ids = tag_ids or []
    resolved = []
    for index, label in enumerate(tag_labels or []):
        tag_id = tag_ids[index] if index < len(tag_ids) else name_map.get(label)
        if tag_id and tag_id not in resolved:
            resolved.append(tag_id)
    for tag_id in tag_ids:
        if tag_id not in resolved:
            resolved.append(tag_id)
    return resolved


def get_store_catalog():
    if not CATALOG_SNAPSHOT_PATH.exists():
        return CATALOG
    modified_at = CATALOG_SNAPSHOT_PATH.stat().st_mtime
    if store_catalog_cache["modified_at"] == modified_at:
        return store_catalog_cache["games"]
    try:
        snapshot = json.loads(CATALOG_SNAPSHOT_PATH.read_text(encoding="utf-8"))
        games = snapshot.get("games", [])
        if len(games) < MIN_CATALOG_SIZE:
            return CATALOG
        name_map = build_tag_name_id_map(games)
        games = [
            {**game, "tag_ids": resolve_full_tag_ids(game.get("tag_ids"), game.get("tag_labels"), name_map)}
            for game in games
        ]
        store_catalog_cache.update(modified_at=modified_at, games=games, tag_name_ids=name_map)
        return games
    except (OSError, ValueError, TypeError):
        return CATALOG


def load_label_policy():
    with LABEL_POLICY_PATH.open(encoding="utf-8") as policy_file:
        return json.load(policy_file)


def load_tag_cache():
    try:
        return json.loads(APP_TAG_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def load_name_cache():
    try:
        return json.loads(APP_NAME_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def get_catalog_localized_names():
    return {
        int(game["app_id"]): game["name"]
        for game in get_store_catalog()
        if game.get("app_id") is not None and game.get("name")
    }


def fetch_app_tags_and_name(app_id):
    page = requests.get(
        f"{STEAM_STORE_BASE}/app/{app_id}/",
        params={"cc": "cn", "l": "schinese"},
        headers=STORE_HEADERS,
        timeout=10,
    )
    page.raise_for_status()
    match = re.search(r'data-ds-tagids="\[([0-9,]+)\]', page.text)
    tag_ids = [int(tag_id) for tag_id in match.group(1).split(",")] if match else []
    labels = [
        re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", label)).strip()
        for label in re.findall(r'<a[^>]*class="app_tag[^>]*>(.*?)</a>', page.text, re.S)
    ]
    labels = list(dict.fromkeys(label for label in labels if label))
    tag_ids = resolve_full_tag_ids(tag_ids, labels, get_tag_name_id_map())
    # og:title survives the age-gate interstitial, where the tag markup is absent.
    title = re.search(r'<meta\s+property="og:title"\s+content="([^"]+)"', page.text)
    name = re.sub(r"^Steam\s*\u4e0a\u7684\s*", "", html.unescape(title.group(1)).strip()) if title else ""
    # A discounted page titles itself "buy X, save N%" instead of naming the game.
    name = re.sub(r"^\u5728\s*Steam\s*\u4e0a\u8d2d\u4e70\s*(.+?)\s*\u7acb\u7701\s*\d+%$", r"\1", name)
    # A delisted or region-locked app redirects to the storefront home page.
    if name in {"Steam Store", "Steam \u5546\u5e97", "Welcome to Steam"}:
        name = ""
    return tag_ids, name


def fetch_achievement_summary(api_key, steam_id, app_id):
    payload = steam_get(
        "/ISteamUserStats/GetPlayerAchievements/v1/",
        {"key": api_key, "steamid": steam_id, "appid": app_id},
    )
    achievements = payload.get("playerstats", {}).get("achievements", [])
    if not achievements:
        return None
    completed = sum(achievement.get("achieved", 0) for achievement in achievements)
    total = len(achievements)
    return {"completed": completed, "total": total, "ratio": completed / total}


def get_achievement_summary(api_key, steam_id, app_id):
    cache_key = (steam_id, app_id)
    cached = achievement_cache.get(cache_key)
    if cached and time.time() - cached["updated_at"] < ACHIEVEMENT_CACHE_SECONDS:
        return cached["summary"]
    try:
        summary = fetch_achievement_summary(api_key, steam_id, app_id)
    except requests.RequestException:
        summary = None
    achievement_cache[cache_key] = {"updated_at": time.time(), "summary": summary}
    achievement_cache_dirty.add(cache_key)
    return summary


def load_achievement_cache():
    # Held on disk because a restart otherwise re-fetches an achievement call per
    # representative game, which is the slowest part of a first lookup.
    try:
        stored = json.loads(ACHIEVEMENT_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    fresh = {}
    for key, entry in stored.items():
        steam_id, _, app_id = key.partition(":")
        if app_id.isdigit() and time.time() - entry["updated_at"] < ACHIEVEMENT_CACHE_SECONDS:
            fresh[(steam_id, int(app_id))] = entry
    return fresh


def save_achievement_cache():
    if not achievement_cache_dirty:
        return
    achievement_cache_dirty.clear()
    payload = {
        f"{steam_id}:{app_id}": entry
        for (steam_id, app_id), entry in achievement_cache.items()
        if time.time() - entry["updated_at"] < ACHIEVEMENT_CACHE_SECONDS
    }
    ACHIEVEMENT_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACHIEVEMENT_CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


achievement_cache.update(load_achievement_cache())


def get_review_summary(app_id):
    cached = review_cache.get(app_id)
    if cached and monotonic() - cached["updated_at"] < REVIEW_CACHE_SECONDS:
        return cached["summary"]
    try:
        query_summary = store_json(
            f"/appreviews/{app_id}", {"json": 1, "language": "all", "purchase_type": "all", "num_per_page": 0}
        ).get("query_summary", {})
        review_count = query_summary.get("total_reviews", 0)
        summary = {
            "review_count": review_count,
            "positive_rate": round(100 * query_summary.get("total_positive", 0) / review_count) if review_count else None,
        }
    except requests.RequestException:
        summary = None
    review_cache[app_id] = {"updated_at": monotonic(), "summary": summary}
    return summary


def select_engagement_candidates(games):
    eligible_games = [game for game in games if game.get("playtime_forever", 0) >= MIN_PREFERENCE_PLAYTIME_MINUTES]
    if not eligible_games:
        # A lightly played library still describes a taste; falling through to the
        # keyword-only path would throw that away entirely.
        eligible_games = [game for game in games if game.get("playtime_forever", 0) > 0]
    by_time = sorted(eligible_games, key=lambda game: game.get("playtime_forever", 0), reverse=True)[:80]
    mid_length = sorted(
        [game for game in eligible_games if 600 <= game.get("playtime_forever", 0) <= 7200],
        key=lambda game: game.get("playtime_forever", 0),
        reverse=True,
    )[:60]
    short_length = sorted(
        [game for game in eligible_games if MIN_PREFERENCE_PLAYTIME_MINUTES <= game.get("playtime_forever", 0) < 600],
        key=lambda game: game.get("playtime_forever", 0),
        reverse=True,
    )[:30]
    recent = sorted(eligible_games, key=lambda game: game.get("rtime_last_played", 0), reverse=True)[:30]
    candidates = {game["appid"]: game for game in by_time + mid_length + short_length + recent}
    return list(candidates.values())


def select_representative_games(games):
    # Short games can no longer define a core preference, so the extra capacity
    # goes to long and mid-length games where the evidence pool was thinnest.
    buckets = [
        (lambda game: game.get("playtime_forever", 0) > 7200, 45),
        (lambda game: 600 <= game.get("playtime_forever", 0) <= 7200, 55),
        (lambda game: MIN_PREFERENCE_PLAYTIME_MINUTES <= game.get("playtime_forever", 0) < 600, 20),
    ]
    selected = []
    selected_ids = set()
    for predicate, limit in buckets:
        bucket = sorted(
            (game for game in games if predicate(game) and game["appid"] not in selected_ids),
            key=lambda game: game["engagement_score"],
            reverse=True,
        )[:limit]
        selected.extend(bucket)
        selected_ids.update(game["appid"] for game in bucket)
    if len(selected) < PREFERENCE_GAME_LIMIT:
        remaining = sorted(
            (game for game in games if game["appid"] not in selected_ids),
            key=lambda game: game["engagement_score"],
            reverse=True,
        )[:PREFERENCE_GAME_LIMIT - len(selected)]
        selected.extend(remaining)
    return selected


def calculate_engagement(game, achievement_summary, now, engagement_config):
    hours = game.get("playtime_forever", 0) / 60 * game.get("playtime_factor", 1.0)
    completion = 0
    if achievement_summary:
        reliability = min(1, achievement_summary["total"] / engagement_config["achievement_reliability_total"])
        # Visual novels and dating sims hand out a full achievement set in a few
        # hours, which otherwise let them outrank hundred-hour games.
        playtime_reliability = min(1, hours / engagement_config["achievement_reliability_hours"])
        completion = achievement_summary["ratio"] * reliability * playtime_reliability
    last_played = game.get("rtime_last_played", 0)
    days_since_played = max(0, (now - last_played) / 86400) if last_played else 3650
    recency = math.exp(-days_since_played / engagement_config["recency_half_life_days"])
    return math.log1p(hours) + engagement_config["achievement_weight"] * completion + engagement_config["recency_weight"] * recency


def enrich_preference_games_with_tags(games):
    preference_games = games[:PREFERENCE_GAME_LIMIT]
    cache = load_tag_cache()
    names = load_name_cache()
    catalog_names = get_catalog_localized_names()
    for game in preference_games:
        game["display_name"] = catalog_names.get(int(game["appid"]), "")
    # Empty entries were commonly written during transient Steam rate limits.
    # Retry them on later requests rather than treating a failed fetch as data.
    missing_ids = [
        game["appid"] for game in preference_games
        if not cache.get(str(game["appid"]))
        or not (game["display_name"] or names.get(str(game["appid"])))
    ]
    if missing_ids:
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(fetch_app_tags_and_name, app_id): app_id for app_id in missing_ids}
            for future in as_completed(futures):
                app_id = futures[future]
                try:
                    tag_ids, store_name = future.result()
                except requests.RequestException:
                    continue
                if tag_ids:
                    cache[str(app_id)] = tag_ids
                if store_name:
                    names[str(app_id)] = store_name
        APP_TAG_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        APP_TAG_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        APP_NAME_CACHE_PATH.write_text(json.dumps(names, ensure_ascii=False), encoding="utf-8")
    for game in preference_games:
        game["tag_ids"] = cache.get(str(game["appid"]), [])
        game["display_name"] = game["display_name"] or names.get(str(game["appid"])) or game.get("name", "")
    return preference_games


def build_label_profile(games, policy, steam_id=None, api_key=None):
    candidate_games = select_engagement_candidates(games)
    now = datetime.now(timezone.utc).timestamp()
    engagement_config = policy["scoring"]["engagement"]
    chinese_tag_names = get_catalog_tag_name_map()
    if steam_id and api_key:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(get_achievement_summary, api_key, steam_id, game["appid"]): game
                for game in candidate_games
            }
            for future in as_completed(futures):
                game = futures[future]
                game["achievement_summary"] = future.result()
    tag_cache = load_tag_cache()
    passive_tags = {int(tag_id) for tag_id in policy.get("passive_playtime_tags", {})}
    for game in candidate_games:
        cached_tags = game.get("tag_ids") or tag_cache.get(str(game["appid"]), [])
        game["playtime_factor"] = (
            PASSIVE_PLAYTIME_FACTOR
            if passive_tags & set(cached_tags[:PASSIVE_PLAYTIME_RANK_LIMIT])
            else 1.0
        )
        game["engagement_score"] = calculate_engagement(game, game.get("achievement_summary"), now, engagement_config)
    preference_games = select_representative_games(candidate_games)
    save_achievement_cache()
    preference_games = enrich_preference_games_with_tags(preference_games)
    policy_groups = {
        group: {
            int(tag_id): chinese_tag_names.get(int(tag_id), english_name)
            for tag_id, english_name in policy[group].items()
        }
        for group in ("level_1", "level_2_core", "level_3", "soft_preference")
    }
    profile = {group: {} for group in policy_groups}
    ignored_preference_tags = {
        int(tag_id) for section in ("hard_ignore_tags", "content_risk_tags")
        for tag_id in policy.get(section, {})
    }
    # Captured before the content-risk filter: a genuine otome player often owns
    # titles that carry risk tags, and they must still confirm that interest.
    library_tag_lists = [list(game.get("tag_ids", [])) for game in preference_games]
    preference_games = [
        game for game in preference_games
        if not (set(game.get("tag_ids", [])) & ignored_preference_tags)
    ]
    for game in preference_games:
        achievement_summary = game.get("achievement_summary")
        completion_percent = round(100 * achievement_summary["ratio"]) if achievement_summary else None
        evidence = {
            "app_id": game["appid"],
            "name": game.get("display_name") or game["name"],
            "hours": round(game.get("playtime_forever", 0) / 60, 1),
            "recently_played": bool(game.get("rtime_last_played", 0) and now - game["rtime_last_played"] <= 30 * 86400),
            "achievement_percent": completion_percent,
            "achievement_completed": achievement_summary["completed"] if achievement_summary else None,
            "achievement_total": achievement_summary["total"] if achievement_summary else None,
            "engagement_score": round(game["engagement_score"], 2),
            "passive_playtime": game.get("playtime_factor", 1.0) < 1,
        }
        labels_contributed = 0
        filtered_tag_ids = filter_outlier_tags(game.get("tag_ids", []), policy)
        # A game finished in a few hours shows a taste, but it should not define a
        # core gameplay preference: short completionist titles would otherwise
        # dominate the profile and pull the whole catalog toward their genre.
        # Level 3 tags are exempt because they are narrow, deliberate choices.
        may_define_core = evidence["hours"] * game.get("playtime_factor", 1.0) >= engagement_config["min_hours_for_core_tag"]
        # A tag listed in two policy layers would otherwise score the same game
        # twice and fake a second source backing that tag.
        counted_tag_ids = set()
        for group in ("level_3", "level_2_core", "level_1", "soft_preference"):
            if group == "level_2_core" and not may_define_core:
                continue
            labels = policy_groups[group]
            tag_limit = get_tag_rank_limit(group)
            for rank, tag_id in enumerate(filtered_tag_ids[:tag_limit], start=1):
                if tag_id in counted_tag_ids:
                    continue
                if tag_id in labels and labels_contributed < MAX_LABELS_PER_REPRESENTATIVE_GAME:
                    profile[group].setdefault(tag_id, []).append({**evidence, "tag_rank": rank})
                    counted_tag_ids.add(tag_id)
                    labels_contributed += 1
    # Raw tags of the representative games, used for gating checks so that a short
    # but genuine interest still counts even when it cannot define a core tag.
    return profile, policy_groups, len(preference_games), library_tag_lists


def build_preference_profile(games):
    ranked_games = sorted(games, key=lambda game: game.get("playtime_forever", 0), reverse=True)
    played_games = [game for game in ranked_games if game.get("playtime_forever", 0) >= MIN_PREFERENCE_PLAYTIME_MINUTES]
    preference_games = played_games[:PREFERENCE_GAME_LIMIT]
    catalog_names = get_catalog_localized_names()
    names = load_name_cache()
    signals = Counter()
    evidence = {}
    genre_keywords = {
        "rpg": ["elder", "witcher", "fallout", "persona", "final fantasy", "baldur", "cyberpunk", "divinity"],
        "action": ["doom", "counter", "call of duty", "souls", "devil may cry", "monster hunter", "yakuza"],
        "simulation": ["farm", "city", "simulator", "tycoon", "valley", "factorio", "house flipper"],
        "strategy": ["civilization", "total war", "strategy", "crusader", "xcom", "age of empires", "rimworld"],
        "indie": ["hollow knight", "terraria", "undertale", "celeste", "dead cells", "slay the spire"],
        "multiplayer": ["counter-strike", "dota", "apex", "overwatch", "rainbow six", "left 4 dead", "payday"],
        "adventure": ["tomb raider", "uncharted", "life is strange", "resident evil", "assassin"],
    }
    for rank, owned_game in enumerate(preference_games, start=1):
        name = owned_game.get("name", "")
        display_name = catalog_names.get(int(owned_game["appid"])) or names.get(str(owned_game["appid"])) or name
        minutes = owned_game.get("playtime_forever", 0)
        weight = max(1, 8 - rank // 4) + min(6, minutes // 600)
        for genre, keywords in genre_keywords.items():
            if any(keyword in name.lower() for keyword in keywords):
                signals[genre] += weight
                evidence.setdefault(genre, []).append({
                    "app_id": owned_game["appid"], "name": display_name, "hours": round(minutes / 60, 1)
                })
    return signals, evidence, len(preference_games)


def choose_evidence(evidence, genres, evidence_use_counts):
    selected = []
    for genre in genres:
        options = [game for game in evidence.get(genre, []) if game["app_id"] not in {item["app_id"] for item in selected}]
        if options:
            weights = [1 / (1 + evidence_use_counts.get(game["app_id"], 0)) for game in options]
            selected.append(random.choices(options, weights=weights, k=1)[0])
    return selected[:2]


def get_tag_rank_limit(group):
    if group == "level_2_core":
        return CORE_TAG_RANK_LIMIT
    if group == "level_3":
        return LEVEL_3_TAG_RANK_LIMIT
    return SOFT_TAG_RANK_LIMIT


def get_tag_match_limit(group):
    if group == "level_2_core":
        return CORE_TAG_MATCH_LIMIT
    if group == "level_1":
        return LEVEL_1_TAG_MATCH_LIMIT
    if group == "soft_preference":
        return SOFT_TAG_MATCH_LIMIT
    return None


def tag_rank_factor(rank):
    return max(MIN_TAG_RANK_FACTOR, 1 - TAG_RANK_DECAY_PER_POSITION * (rank - 1))


def build_tag_strength(label_profile):
    engagements = [
        item["engagement_score"]
        for group in label_profile.values()
        for sources in group.values()
        for item in (sources if isinstance(sources, list) else [sources])
    ]
    top_engagement = max(engagements) if engagements else 0
    strength = {}
    for group, tags in label_profile.items():
        for tag_id, sources in tags.items():
            sources = sources if isinstance(sources, list) else [sources]
            breadth = min(1.0, len(sources) / TAG_EVIDENCE_BREADTH_TARGET)
            # Summed rather than peak engagement, so a tag TA returns to across
            # several games outranks one backed by a single session.
            support = sum(item["engagement_score"] for item in sources)
            depth = min(1.0, support / (top_engagement * TAG_EVIDENCE_BREADTH_TARGET)) if top_engagement else 0
            value = (
                TAG_STRENGTH_BASE
                + TAG_STRENGTH_BREADTH_WEIGHT * breadth
                + TAG_STRENGTH_DEPTH_WEIGHT * depth
            )
            if group == "level_3":
                value *= level_3_confirmation(sources, top_engagement)
            strength[(group, tag_id)] = value
    return strength


def level_3_confirmation(sources, top_engagement):
    """Scale a narrow tag by how much repeated play actually backs it.

    Only games where it is a defining tag count, and their engagement is summed,
    so the weight climbs smoothly from a single short session to a real habit
    instead of flipping at a threshold.
    """
    confirming = [item for item in sources if item["tag_rank"] <= LEVEL_3_CONFIRMING_RANK_LIMIT]
    if not confirming or not top_engagement:
        return LEVEL_3_UNCONFIRMED_FLOOR
    support = sum(item["engagement_score"] for item in confirming)
    confirmation = min(1.0, support / (top_engagement * LEVEL_3_MIN_CONFIRMING_SOURCES))
    return LEVEL_3_UNCONFIRMED_FLOOR + (1 - LEVEL_3_UNCONFIRMED_FLOOR) * confirmation


def filter_outlier_tags(tag_ids, policy):
    # Name resolution can reintroduce a tag the raw id list already held, and a
    # duplicate would count as a second game backing that tag.
    filtered = list(dict.fromkeys(tag_ids))
    tag_set = set(filtered)
    for rule in policy.get("tag_ban_pairs", []):
        when_any = {int(tag_id) for tag_id in rule["when_any"]}
        with_any = {int(tag_id) for tag_id in rule["with_any"]}
        if tag_set & when_any and tag_set & with_any:
            ignored = {int(tag_id) for tag_id in rule["ignore"]}
            filtered = [tag_id for tag_id in filtered if tag_id not in ignored]
            tag_set = set(filtered)
    return filtered


def is_banned_candidate(tag_ids, policy):
    tag_set = set(tag_ids)
    return any(
        {int(tag_id) for tag_id in rule["when_all"]}.issubset(tag_set)
        for rule in policy.get("candidate_ban_pairs", [])
    )


def collapse_match_families(label_matches, candidate_tag_ids, policy):
    tag_to_group = {
        tag_id: group
        for group, tag_ids in label_matches.items()
        for tag_id in tag_ids
    }
    for family in policy.get("tag_match_families", []):
        family_matches = [tag_id for tag_id in family["tags"] if int(tag_id) in tag_to_group]
        if len(family_matches) <= 1:
            continue
        def priority(tag_id):
            numeric_tag_id = int(tag_id)
            group = tag_to_group[numeric_tag_id]
            return (policy["scoring"][f"{group}_weight"], -candidate_tag_ids.index(numeric_tag_id))
        retained_tag_id = max(family_matches, key=lambda tag_id: priority(int(tag_id)))
        for tag_id in family_matches:
            tag_id = int(tag_id)
            if tag_id != int(retained_tag_id):
                label_matches[tag_to_group[tag_id]].remove(tag_id)
    return label_matches


def get_catalog_tag_name_map():
    tag_names = {}
    for game in get_store_catalog():
        for tag_id, tag_name in zip(game.get("tag_ids", []), game.get("tag_labels", [])):
            tag_names.setdefault(tag_id, tag_name)
    return tag_names


def serialize_preference_tags(label_profile, policy_groups):
    ui_groups = {
        group_name: {int(tag_id) for tag_id in tag_ids}
        for group_name, tag_ids in policy_groups["preference_ui_groups"].items()
    }
    tags = []
    seen_tag_ids = set()
    for group in ("level_3", "level_2_core", "soft_preference", "level_1"):
        for tag_id in label_profile[group]:
            if tag_id in seen_tag_ids:
                continue
            seen_tag_ids.add(tag_id)
            tags.append(
                {
                    "tag_id": tag_id,
                    "name": policy_groups[group].get(tag_id) or find_tag_name(policy_groups, tag_id),
                    "group": group,
                    "ui_group": "和谁玩" if tag_id in ui_groups["和谁玩"] else ("最近玩" if any(item.get("recently_played") for item in label_profile[group][tag_id]) else "爱玩的"),
                    "source_count": len(label_profile[group][tag_id]),
                }
            )
    return tags


def spread_batch_evidence(selection, label_profile, evidence_use_counts):
    """Re-pick label evidence once the batch is final.

    Scoring runs before the batch is known, so every card would otherwise draw its
    evidence from the same use counts and cite the same owned game repeatedly.
    """
    batch_counts = Counter(evidence_use_counts)
    recent_app_ids = []
    for chosen in selection:
        details = chosen.get("matched_label_details") or {}
        card_app_ids = set()
        for group in ("level_3", "level_2_core", "level_1", "soft_preference"):
            for detail in details.get(group, []):
                options = label_profile[group].get(detail["tag_id"]) or []
                if isinstance(options, dict):
                    options = [options]
                if options:
                    blocked = set(recent_app_ids)
                    fresh = [item for item in options if item["app_id"] not in blocked]
                    choices = fresh or options
                    # A game already cited on this card is a coherent citation for
                    # a second tag it genuinely supports, so it is favoured rather
                    # than excluded. Repetition across cards is still penalised.
                    weights = [
                        item["engagement_score"]
                        * (EVIDENCE_SAME_CARD_BONUS if item["app_id"] in card_app_ids else 1)
                        / (1 + batch_counts[item["app_id"]]) ** 2
                        for item in choices
                    ]
                    if sum(weights) <= 0:
                        weights = [1] * len(choices)
                    detail["source_game"] = random.choices(choices, weights=weights, k=1)[0]
                source_id = detail["source_game"]["app_id"]
                # Only the first citation of a game on a card costs it budget, so
                # covering several tags does not push it out of later batches.
                if source_id not in card_app_ids:
                    batch_counts[source_id] += 1
                card_app_ids.add(source_id)
        recent_app_ids = (recent_app_ids + sorted(card_app_ids))[-EVIDENCE_REUSE_LOOKBACK * 3:]
        chosen["evidence_app_ids"] = sorted(card_app_ids | set(chosen.get("evidence_app_ids") or []))


def combine_match_depth(qualities):
    """Combine per-tag match qualities so precision outweighs breadth.

    A plain sum let a game that loosely touches five tags beat one that nails the
    two tags the player actually cares about. Raising each quality before adding
    lets the strongest matches dominate while more matches still help.
    """
    total = sum(quality ** MATCH_DEPTH_CONCENTRATION for quality in qualities)
    return total ** (1 / MATCH_DEPTH_CONCENTRATION) if total else 0.0


def uninterested_tags(tag_ids, profile_tag_ids, known_tag_ids, tag_overlap):
    """Headline tags of a candidate that the target's library shows no sign of."""
    return [
        (rank, tag_id)
        for rank, tag_id in enumerate(tag_ids[:GAP_TAG_RANK_LIMIT], start=1)
        if tag_id in known_tag_ids
        and tag_id not in profile_tag_ids
        and not (tag_overlap.get(tag_id, frozenset()) & profile_tag_ids)
    ]


def mismatch_factor(gaps):
    """Shrink a match when the game leads with tastes the target does not share.

    A football game can collect a decent score from generic multiplayer tags
    alone, which reads as a recommendation for someone who dislikes sport.
    """
    weighted = sum(tag_rank_factor(rank) ** MISMATCH_RANK_EXPONENT for rank, _ in gaps)
    return max(MISMATCH_MIN_FACTOR, 1 - MISMATCH_WEIGHT * weighted)


def profile_depth_reference(label_profile, tag_strength, policy, gate_filter=None):
    """Depths this profile can reach across the whole catalogue.

    Both modes calibrate on this, so the same match reads the same number
    whether it came from the store or from the gift giver's own library. It
    mirrors the scoring path step for step; skipping any step biased the scale.
    """
    profile_tag_ids = {
        tag_id for group in ("level_3", "level_2_core", "level_1", "soft_preference")
        for tag_id in label_profile[group]
    }
    known_tag_ids = {
        int(tag_id) for group in ("level_3", "level_2_core", "level_1", "soft_preference")
        for tag_id in policy[group]
    }
    tag_overlap = get_tag_overlap_map(len(get_store_catalog()))
    depths = []
    for game in get_store_catalog():
        tag_ids = filter_outlier_tags(game.get("tag_ids", []), policy)
        candidate_tags = set(tag_ids)
        if is_banned_candidate(candidate_tags, policy) or (gate_filter and gate_filter(tag_ids)):
            continue
        label_matches = {}
        for group in ("level_3", "level_1", "level_2_core", "soft_preference"):
            ranked = [tag_id for tag_id in tag_ids[:get_tag_rank_limit(group)] if tag_id in label_profile[group]]
            match_limit = get_tag_match_limit(group)
            label_matches[group] = ranked[:match_limit] if match_limit else ranked
        label_matches = collapse_match_families(label_matches, tag_ids, policy)
        label_matches, _ = promote_level_3_pairs(label_matches, policy)
        ranks = {tag_id: rank for rank, tag_id in enumerate(tag_ids, start=1)}
        depth = combine_match_depth([
            DEPTH_GROUP_WEIGHT[group]
            * tag_rank_factor(ranks.get(tag_id, 1))
            * tag_strength.get((group, tag_id), 1.0)
            for group in DEPTH_GROUP_WEIGHT
            for tag_id in label_matches[group]
        ])
        depth *= mismatch_factor(uninterested_tags(tag_ids, profile_tag_ids, known_tag_ids, tag_overlap))
        if depth > 0:
            depths.append(depth)
    return sorted(depths)


def assign_match_percent(results, reference_depths=None):
    """Map match depth onto 0-100 relative to what this profile can actually reach.

    Every shown card is already in the top fraction of the catalogue, so a fixed
    scale squeezed them all into a few points. The best reachable match anchors
    100 and a high percentile of the same user's own distribution anchors the
    lower end, which spreads the cards a gift giver actually sees.
    """
    depths = reference_depths or sorted(
        game.get("match_depth", 0.0) for game in results if game.get("match_depth", 0.0) > 0
    )
    ceiling = max(depths[-1] * MATCH_CEILING_HEADROOM, MATCH_DEPTH_FLOOR) if depths else 0
    by_percentile = round(len(depths) * MATCH_PERCENT_BASELINE_PERCENTILE / 100) - 1
    by_count = len(depths) - MATCH_PERCENT_MIN_ABOVE_BASELINE
    index = max(0, min(len(depths) - 1, by_percentile, by_count))
    baseline = depths[index] if depths else 0
    # An absolute rank keeps a low percentage readable: a game can sit below the
    # baseline and still be, say, 210th out of 3433 rather than simply "0".
    ordered = sorted(results, key=lambda game: -game["score"])
    for rank, game in enumerate(ordered, start=1):
        game["match_rank"] = rank
        game["match_total"] = len(ordered)
    for game in results:
        depth = game.get("match_depth", 0.0)
        if depth >= baseline and ceiling > baseline:
            position = (depth - baseline) / (ceiling - baseline)
            # Real matches crowd into a narrow band, so differences are pushed
            # away from the typical match. Clamping a straight stretch instead
            # flattened everything below the pivot onto the same number.
            if position < MATCH_PERCENT_PIVOT:
                position = MATCH_PERCENT_PIVOT * (position / MATCH_PERCENT_PIVOT) ** MATCH_PERCENT_SPREAD
            else:
                remainder = (1 - position) / (1 - MATCH_PERCENT_PIVOT)
                position = 1 - (1 - MATCH_PERCENT_PIVOT) * remainder ** MATCH_PERCENT_SPREAD
            percent = MATCH_PERCENT_BASELINE_ANCHOR + position * (100 - MATCH_PERCENT_BASELINE_ANCHOR)
        elif baseline > 0:
            percent = MATCH_PERCENT_BASELINE_ANCHOR * depth / baseline
        else:
            percent = 100 if depth > 0 else 0
        if depth <= 0:
            # Nothing deep matched, but a broad overlap is still worth more than
            # a blank zero, so those games share a small band of their own.
            percent = min(SHALLOW_MAX_PERCENT, SHALLOW_MAX_PERCENT * game.get("match_shallow", 0.0) / SHALLOW_FULL_CREDIT)
        game["match_percent"] = round(min(100, max(0, percent)))
        game["match_tier"], game["match_tier_note"] = next(
            (name, note) for minimum, name, note in MATCH_RARITY_TIERS if game["match_percent"] >= minimum
        )


def promote_level_3_pairs(label_matches, policy):
    """A pair like idle plus incremental only counts as a Level 3 signal together.

    On its own each tag stays a normal core tag, so a game that is merely idle
    does not borrow the weight of the much narrower combined taste.
    """
    promoted = []
    for pair in policy.get("level_3_pairs", []):
        tag_ids = [int(tag_id) for tag_id in pair["tags"]]
        if not all(tag_id in label_matches["level_2_core"] for tag_id in tag_ids):
            continue
        for tag_id in tag_ids:
            label_matches["level_2_core"].remove(tag_id)
        label_matches["level_3"].append(tag_ids[0])
        promoted.append((tag_ids[0], pair["name"]))
    return label_matches, dict(promoted)


def find_profile_sources(label_profile, tag_id):
    for group_sources in label_profile.values():
        if tag_id in group_sources:
            return group_sources[tag_id]
    return []


def find_tag_name(policy_groups, tag_id):
    for names in policy_groups.values():
        if isinstance(names, dict) and tag_id in names:
            return names[tag_id]
    return str(tag_id)


def recommend(games, excluded_ids=None, evidence_use_counts=None, priority="balanced", candidates=None, steam_id=None, api_key=None, active_tag_ids=None, include_preference_tags=False, single_candidate=False, excluded_tag_ids=None):
    owned_ids = {int(game["appid"]) for game in games if str(game.get("appid", "")).isdigit()}
    # Kept in display order so the batch position and what was shown recently can
    # both be recovered without the client sending extra state.
    shown_order = [int(app_id) for app_id in (excluded_ids or [])]
    excluded_ids = set(excluded_ids or [])
    evidence_use_counts = Counter(evidence_use_counts or {})
    signals, evidence, preference_sample_size = build_preference_profile(games)
    policy = load_label_policy()
    label_profile, policy_groups, tagged_preference_sample_size, library_tag_lists = build_label_profile(games, policy, steam_id, api_key)
    tag_strength = build_tag_strength(label_profile)
    preference_tags = serialize_preference_tags(label_profile, {**policy_groups, "preference_ui_groups": policy["preference_ui_groups"]})
    available_tag_ids = {tag["tag_id"] for tag in preference_tags}
    requested_tag_ids = []
    for tag_id in active_tag_ids or []:
        if str(tag_id).isdigit() and int(tag_id) in available_tag_ids and int(tag_id) not in requested_tag_ids:
            requested_tag_ids.append(int(tag_id))
    active_tag_ids = set(requested_tag_ids[:3])
    # Tags the gift giver ruled out: any candidate carrying one is dropped.
    rejected_tag_ids = {
        int(tag_id) for tag_id in (excluded_tag_ids or [])
        if str(tag_id).isdigit() and int(tag_id) in available_tag_ids
    } - active_tag_ids
    excluded_candidate_tags = {int(tag_id) for tag_id in policy["exclude_from_candidates"]}
    content_risk_tags = {int(tag_id) for tag_id in policy["content_risk_tags"]}
    # Audience-specific tag combinations are only acceptable when one of the
    # target user's own games carries the same combination. A shared generic tag
    # such as Visual Novel is otherwise enough to route otome titles to anyone.
    # within_rank keeps the rule on romance-first games: Persona 3 and Danganronpa
    # carry the same tags far down their tag list and must not be caught.
    gated_tag_rules = [
        ({int(tag_id) for tag_id in rule["when_all"]}, rule.get("within_rank"))
        for rule in policy.get("gated_tag_rules", [])
    ]

    def matches_gate(tag_ids, required, within_rank):
        return required <= set(tag_ids[:within_rank] if within_rank else tag_ids)

    # Owning such a game says nothing about wanting one as a gift, so the gate is
    # never unlocked by the library. A direct lookup still reports on the game.
    unconfirmed_gates = gated_tag_rules
    has_label_profile = any(label_profile[group] for group in label_profile)
    known_preference_tag_ids = {
        tag_id for group in ("level_3", "level_2_core", "level_1", "soft_preference")
        for tag_id in policy_groups[group]
    }
    tag_overlap = get_tag_overlap_map(len(get_store_catalog()))

    results = []
    candidate_list = candidates if candidates is not None else CATALOG
    candidate_count = len(candidate_list)
    for game in candidate_list:
        # A direct lookup should still report on a game the target already owns,
        # rather than filtering it out and looking like the query failed.
        is_focus = single_candidate and int(game["app_id"]) == int(single_candidate)
        if not is_focus and int(game["app_id"]) in owned_ids:
            continue
        # Games shown in an earlier batch still get scored, otherwise every batch
        # renormalises against a shrinking pool and the top card is always 100.
        already_shown = not is_focus and int(game["app_id"]) in excluded_ids
        filtered_tag_ids = filter_outlier_tags(game.get("tag_ids", []), policy)
        candidate_tags = set(filtered_tag_ids)
        banned = is_banned_candidate(candidate_tags, policy)
        if banned and not is_focus:
            continue
        if candidate_tags & excluded_candidate_tags:
            continue
        if not is_focus and candidate_tags & rejected_tag_ids:
            continue
        gated = any(matches_gate(filtered_tag_ids, required, within_rank) for required, within_rank in unconfirmed_gates)
        # A direct lookup is an inspection tool, so it still reports tags and a
        # score for gated games and only flags why they are never recommended.
        if gated and not is_focus:
            continue
        content_risk_matches = candidate_tags & content_risk_tags
        content_warning = bool(content_risk_matches)
        content_warning_text = (
            "潜在裸露或色情内容" if content_risk_matches - {44868}
            else "包含 LGBTQ+ 内容"
        ) if content_warning else ""
        label_matches = {}
        for group in ("level_3", "level_1", "level_2_core", "soft_preference"):
            tag_limit = get_tag_rank_limit(group)
            # Ordered by the candidate's own tag ranking, so a capped group keeps
            # the tags that are most prominent on that store page.
            ranked_matches = [tag_id for tag_id in filtered_tag_ids[:tag_limit] if tag_id in label_profile[group]]
            match_limit = get_tag_match_limit(group)
            label_matches[group] = ranked_matches[:match_limit] if match_limit else ranked_matches
        label_matches = collapse_match_families(label_matches, filtered_tag_ids, policy)
        label_matches, promoted_pair_names = promote_level_3_pairs(label_matches, policy)
        candidate_tag_ranks = {tag_id: rank for rank, tag_id in enumerate(filtered_tag_ids, start=1)}
        label_sources = {group: {} for group in ("level_3", "level_1", "level_2_core", "soft_preference")}
        for group in ("level_3", "level_2_core", "level_1", "soft_preference"):
            for tag_id in label_matches[group]:
                # A promoted pair keeps its evidence in the layer it came from.
                evidence_options = label_profile[group].get(tag_id) or find_profile_sources(label_profile, tag_id)
                if isinstance(evidence_options, dict):
                    evidence_options = [evidence_options]
                if not evidence_options:
                    continue
                # A source where the tag is a headline feature explains the match
                # far better than one where it sits eighth on the store page.
                evidence_weights = [
                    1 / ((1 + evidence_use_counts.get(item["app_id"], 0)) * item["tag_rank"])
                    for item in evidence_options
                ]
                label_sources[group][tag_id] = random.choices(evidence_options, weights=evidence_weights, k=1)[0]
        matched_label_details = {
            group: [
                {
                    "tag_id": tag_id,
                    "name": promoted_pair_names.get(tag_id) or policy_groups[group].get(tag_id) or find_tag_name(policy_groups, tag_id),
                    "source_game": label_sources[group][tag_id],
                    "candidate_tag_rank": game.get("tag_ids", []).index(tag_id) + 1,
                }
                for tag_id in label_matches[group]
                if tag_id in label_sources[group]
            ]
            for group in ("level_3", "level_1", "level_2_core", "soft_preference")
        }
        evidence_group = "level_3" if label_matches["level_3"] else ("level_2_core" if label_matches["level_2_core"] else ("level_1" if label_matches["level_1"] else "soft_preference"))
        match_evidence = []
        for tag_id in label_matches[evidence_group]:
            source_game = label_sources[evidence_group][tag_id]
            if source_game["app_id"] not in {item["app_id"] for item in match_evidence}:
                match_evidence.append(source_game)
        match_evidence = match_evidence[:2]
        use_label_score = has_label_profile and bool(candidate_tags)
        selected_tag_bonus = 0
        matched_active_tag_count = 0
        if use_label_score:
            selected_tag_bonus = policy["scoring"]["selected_tag_budget"] / len(active_tag_ids) if active_tag_ids else 0
            matched_active_tag_count = sum(
                tag_id in active_tag_ids
                for group in ("level_3", "level_2_core", "soft_preference", "level_1")
                for tag_id in label_matches[group]
            )
            score = sum(
                policy["scoring"][f"{group}_weight"]
                * tag_rank_factor(candidate_tag_ranks.get(tag_id, 1))
                * tag_strength.get((group, tag_id), 1.0)
                for group in ("level_3", "level_2_core", "soft_preference", "level_1")
                for tag_id in label_matches[group]
            ) + selected_tag_bonus * matched_active_tag_count
            if content_warning:
                score += policy["scoring"]["content_risk_penalty"]
            score = round(score, 1)
            matched_genres = []
            core_matches = len(label_matches["level_2_core"])
            level_1_matches = len(label_matches["level_1"])
            # A single narrow tag is a good hint but not proof of a deep match, so
            # the top tier needs breadth as well, and a narrow tag only counts
            # double once TA's library really backs it up.
            strong_matches = sum(
                2 * tag_strength.get(("level_3", tag_id), 1.0)
                for tag_id in label_matches["level_3"]
            ) + core_matches
            match_depth = combine_match_depth([
                DEPTH_GROUP_WEIGHT[group]
                * tag_rank_factor(candidate_tag_ranks.get(tag_id, 1))
                * tag_strength.get((group, tag_id), 1.0)
                for group in DEPTH_GROUP_WEIGHT
                for tag_id in label_matches[group]
            ])
            match_shallow = sum(
                SHALLOW_GROUP_WEIGHT[group]
                * tag_rank_factor(candidate_tag_ranks.get(tag_id, 1))
                * tag_strength.get((group, tag_id), 1.0)
                for group in SHALLOW_GROUP_WEIGHT
                for tag_id in label_matches[group]
            )
            # Prominent traits of this game that TA's library shows no interest in.
            # Restricted to tags the policy recognises as gameplay signals, so a
            # descriptive label like "cosy" is not reported as a mismatch.
            profile_tag_ids = {
                tag_id for group in ("level_3", "level_2_core", "level_1", "soft_preference")
                for tag_id in label_profile[group]
            }
            gaps = uninterested_tags(filtered_tag_ids, profile_tag_ids, known_preference_tag_ids, tag_overlap)
            match_depth *= mismatch_factor(gaps)
            match_gaps = [
                {
                    "name": find_tag_name(policy_groups, tag_id),
                    "rank": rank,
                }
                for rank, tag_id in gaps
            ][:MAX_MATCH_GAPS]
            if strong_matches >= policy["scoring"]["high_confidence_min_strength"]:
                confidence = "高"
            elif strong_matches >= policy["scoring"]["medium_confidence_min_strength"]:
                confidence = "中"
            else:
                confidence = "低"
        else:
            matched_genres = [genre for genre in game["genres"] if signals[genre] > 0]
            match_depth = 0.0
            match_shallow = 0.0
            match_gaps = []
            score = sum(signals[genre] for genre in game["genres"])
            if content_warning:
                score += policy["scoring"]["content_risk_penalty"]
            label_matches = {"level_3": [], "level_1": [], "level_2_core": [], "soft_preference": []}
            match_evidence = []
            matched_label_details = {"level_3": [], "level_1": [], "level_2_core": [], "soft_preference": []}
            confidence = "基础偏好"
        if matched_genres:
            reason = ""
        else:
            reason = f"这款{game['store_source'] if game.get('store_source') else '评价稳定的'}{game['genres'][0]}游戏，能为 TA 的游戏库补上一种新体验；{game['price_note']}。"
        results.append({
            **game,
            "score": score,
            "reason": reason,
            "matched_genres": matched_genres,
            "label_matches": label_matches,
            "matched_label_details": matched_label_details,
            "match_evidence": match_evidence[:2],
            "confidence": confidence,
            "content_warning": content_warning,
            "content_warning_text": content_warning_text,
            "match_depth": round(match_depth, 3),
            "match_shallow": round(match_shallow, 3),
            "match_gaps": match_gaps,
            "audience_gated": gated,
            "blocked_combination": banned,
            "already_shown": already_shown,
            "selected_tag_bonus": round(selected_tag_bonus * matched_active_tag_count, 2),
            "evidence_app_ids": [],
        })
    # One yardstick for both modes: the same match must read the same number
    # whether it came from the store catalogue or from a personal library.
    assign_match_percent(
        results,
        profile_depth_reference(
            label_profile,
            tag_strength,
            policy,
            lambda tag_ids: any(matches_gate(tag_ids, required, within) for required, within in unconfirmed_gates),
        ),
    )
    ranked = sorted((game for game in results if not game["already_shown"]), key=lambda game: -game["score"])
    confident_ranked = [game for game in ranked if game["confidence"] != "低"]
    if confident_ranked:
        # Preserve the quality bar for the first batch, but keep lower-confidence
        # related games available after a narrow priority pool is exhausted.
        ranked = confident_ranked + [game for game in ranked if game["confidence"] == "低"]
    if not ranked:
        if not candidate_count:
            raise ValueError("没有任何候选游戏可供挑选。请放宽预算范围后重试。")
        if not excluded_ids:
            raise ValueError("预算范围内的游戏 TA 几乎都已拥有。请放宽预算，或换一个商店优先级试试。")
        if priority == "top_sellers":
            raise ValueError("热销和高评价精选中都没有更多未展示的游戏。请重新开始查询或选择其他优先级。")
        raise ValueError("当前商店候选已全部看过。请稍后再试，或重新开始一次查询。")
    # Hot sellers are a shallow live storefront list. Once it is exhausted, fall
    # back to the deeper high-rated pool without relabeling those games as hot.
    def is_in_category(game, categories):
        return bool(set(game.get("store_categories", [game.get("store_category")])) & categories)

    def is_new_release(game):
        return is_recent_release(game.get("release_date"))

    def is_recent_top_seller(game):
        return is_new_release(game) and (
            is_in_category(game, {"top_sellers"}) or game["app_id"] in live_top_seller_ids
        )

    well_known_review_count = policy["scoring"].get("well_known_review_count", 5000)

    def is_well_known(game):
        return (game.get("review_count") or 0) >= well_known_review_count

    if single_candidate:
        # A direct lookup must not depend on which storefront list the game is in.
        category_ranked = ranked
        established = ranked
        new_releases = []
        using_new_release_fallback = False
        top_seller_new_releases = []
        pool = [game for game in ranked if int(game["app_id"]) == int(single_candidate)]
    elif priority == "top_sellers":
        category_ranked = [game for game in ranked if is_in_category(game, {"top_sellers", "highly_rated"})]
        if not category_ranked:
            raise ValueError("热销和高评价精选中都没有更多未展示的游戏。请重新开始查询或选择其他优先级。")
        pool = category_ranked[:12]
    elif priority == "new_releases":
        live_top_seller_ids = get_live_top_seller_ids()
        top_seller_new_releases = [game for game in ranked if is_recent_top_seller(game)]
        other_new_releases = [game for game in ranked if is_new_release(game) and not is_recent_top_seller(game)]
        category_ranked = top_seller_new_releases + other_new_releases
        pool = top_seller_new_releases[:12] + other_new_releases[:12]
        if not pool:
            raise ValueError("最近 31 天内没有更多未展示的新品。请重新开始本分类或选择其他优先级。")
        pool = pool[:12]
    elif priority != "balanced":
        category_ranked = [game for game in ranked if is_in_category(game, {priority})]
        if not category_ranked:
            raise ValueError("该商店分类中没有更多未展示的游戏。请重新开始查询或选择其他优先级。")
        pool = category_ranked[:12]
    else:
        established = [game for game in ranked if is_in_category(game, {"top_sellers", "specials", "highly_rated"})]
        established_ids = {game["app_id"] for game in established}
        new_releases = [game for game in ranked if is_new_release(game) and game["app_id"] not in established_ids]
        # Seed mode scores the gift giver's own library, whose games carry no
        # storefront category, so every candidate counts as established.
        if not established and not any(game.get("store_category") or game.get("store_categories") for game in ranked):
            established = ranked
        using_new_release_fallback = not established
        if using_new_release_fallback:
            # Some large libraries already contain every mature candidate. Offer a
            # small discovery batch instead of failing the first search outright.
            pool = new_releases[:12]
        else:
            # New releases are exploratory in balanced mode: no more than one per batch.
            pool = established[:12] + new_releases[:6]
        category_ranked = established + new_releases
    # A tag-only score favours obscure games with dense tag lists. Make sure every
    # batch can offer at least one title the gift giver is likely to recognise.
    # Weighting alone cannot surface a recognisable title that never made the pool,
    # so every batch gets more of them to choose from.
    if not single_candidate:
        pool_ids = {game["app_id"] for game in pool}
        missing = POOL_WELL_KNOWN_TARGET - sum(1 for game in pool if is_well_known(game))
        if missing > 0:
            pool += [
                game for game in category_ranked[:WELL_KNOWN_TOPUP_DEPTH]
                if is_well_known(game) and game["app_id"] not in pool_ids
            ][:missing]
    # A game can sit in a storefront list and be a new release at the same time,
    # and drawing it twice would put the same card on the page twice.
    pool = list({game["app_id"]: game for game in pool}.values())
    if single_candidate:
        target_count = min(1, len(pool))
    else:
        target_count = min(2, len(pool)) if priority == "balanced" and using_new_release_fallback else (min(4, len(established) + min(1, len(new_releases))) if priority == "balanced" else min(4, len(pool)))
    # A tag-only score favours obscure games with dense tag lists, so a title the
    # gift giver has actually heard of gets a better shot at every slot.
    scored_by_id = {int(game["app_id"]): game for game in results}
    tier_floor = {name: minimum for minimum, name, _ in MATCH_RARITY_TIERS}

    def cards_since(min_percent):
        count = 0
        for app_id in reversed(shown_order):
            if scored_by_id.get(app_id, {}).get("match_percent", 0) >= min_percent:
                break
            count += 1
        return count

    pity_due = []
    if not single_candidate:
        for tier_name, window in (("SSR", SSR_PITY_CARDS), ("SR", SR_PITY_CARDS)):
            floor = tier_floor[tier_name]
            if cards_since(floor) + target_count >= window:
                pity_due.append(floor)
                pool_ids = {game["app_id"] for game in pool}
                if not any(game["match_percent"] >= floor for game in pool):
                    pool += [
                        game for game in ranked
                        if game["match_percent"] >= floor and game["app_id"] not in pool_ids
                    ][:2]

    def popularity_factor(game):
        reviews = game.get("review_count") or 0
        recognition = min(1.0, math.log1p(reviews) / math.log1p(well_known_review_count))
        # Scoring stays purely about taste; being a game the gift giver has heard
        # of and can trust only decides which of the good matches gets the slot.
        acclaim = max(0.0, ((game.get("positive_rate") or 0) - ACCLAIM_MIN_POSITIVE_RATE) / (100 - ACCLAIM_MIN_POSITIVE_RATE))
        factor = 1 + POPULARITY_WEIGHT_CEILING * recognition + ACCLAIM_WEIGHT * min(1.0, acclaim)
        if is_in_category(game, {"top_sellers"}):
            factor *= TOP_SELLER_BONUS
        if is_new_release(game) and is_well_known(game):
            factor *= FRESH_AND_POPULAR_BONUS
        return factor

    weights = [
        max(1, game["score"] + 2)
        * popularity_factor(game)
        * (0.22 if priority == "balanced" and game.get("store_category") == "new_releases" else 1)
        for game in pool
    ]
    selection = []
    new_release_count = 0
    # One narrow taste per few pages: without this a tag like idle-plus-incremental
    # matches so much of its own genre that it fills the whole run.
    recent_level_3_cards = sum(
        1 for app_id in shown_order[-LEVEL_3_WINDOW_CARDS:]
        if scored_by_id.get(app_id, {}).get("label_matches", {}).get("level_3")
    )
    level_3_budget = max(0, MAX_LEVEL_3_CARDS_PER_WINDOW - recent_level_3_cards)
    new_release_top_seller_ids = {game["app_id"] for game in top_seller_new_releases} if priority == "new_releases" else set()

    def saturated_tags():
        blocked = set()
        if single_candidate:
            return blocked
        for group, per_batch_limit in (("level_3", MAX_SAME_LEVEL_3_TAG_PER_BATCH), ("level_2_core", MAX_SAME_CORE_TAG_PER_BATCH)):
            counts = Counter(tag_id for game in selection for tag_id in game["label_matches"][group])
            blocked |= {tag_id for tag_id, count in counts.items() if count >= per_batch_limit}
        return blocked

    while pool and len(selection) < target_count:
        remaining_slots = target_count - len(selection)
        # Preferences, not deletions: narrowing the pool itself dropped candidates
        # for good and could leave a batch short of four cards.
        blocked_tags = saturated_tags()
        high_selected = sum(1 for game in selection if game["match_percent"] >= tier_floor["SSR"])
        level_3_full = not single_candidate and sum(
            1 for game in selection if game["label_matches"]["level_3"]
        ) >= level_3_budget

        def acceptable(game):
            if single_candidate:
                return True
            if level_3_full and game["label_matches"]["level_3"]:
                return False
            if blocked_tags and (set(game["label_matches"]["level_3"]) | set(game["label_matches"]["level_2_core"])) & blocked_tags:
                return False
            if not pity_due:
                percent = game["match_percent"]
                if percent >= tier_floor["UR"] and len(shown_order) < UR_EARLIEST_CARD:
                    return False
                if percent >= tier_floor["SSR"] and (
                    len(shown_order) < SSR_EARLIEST_CARD or high_selected >= MAX_HIGH_TIER_PER_BATCH
                ):
                    return False
            return True

        allowed = [index for index, game in enumerate(pool) if acceptable(game)]
        if not allowed:
            # Everything was held back, which happens when the whole pool is high
            # grade. Falling back to the full pool would hand out a page of them,
            # so the least rare cards are taken instead.
            allowed = [index for index, game in enumerate(pool) if game["match_percent"] < tier_floor["SSR"]]
        if not allowed:
            allowed = [min(range(len(pool)), key=lambda index: pool[index]["match_percent"])]
        # A view over the full pool: candidates skipped this round stay available
        # for the next slot instead of being discarded.
        view = [pool[index] for index in allowed]
        view_weights = [weights[index] for index in allowed]
        well_known_indices = [index for index, game in enumerate(view) if is_well_known(game)]
        well_known_selected = sum(1 for game in selection if is_well_known(game))
        required_well_known = MIN_WELL_KNOWN_PER_BATCH
        # An owed tier claims a slot before anything else, and the highest owed
        # tier goes first because it also settles the lower one.
        owed = [
            floor for floor in pity_due
            if not any(game["match_percent"] >= floor for game in selection)
            and any(game["match_percent"] >= floor for game in view)
        ]
        if owed and remaining_slots <= len(owed):
            floor = max(owed)
            eligible = [index for index, game in enumerate(view) if game["match_percent"] >= floor]
            chosen = random.choices([view[index] for index in eligible], weights=[view_weights[index] for index in eligible], k=1)[0]
        elif well_known_indices and remaining_slots <= required_well_known - well_known_selected:
            chosen = random.choices([view[index] for index in well_known_indices], weights=[view_weights[index] for index in well_known_indices], k=1)[0]
        elif priority == "new_releases":
            selected_top_sellers = sum(game["app_id"] in new_release_top_seller_ids for game in selection)
            if selected_top_sellers == 0:
                eligible_indices = [index for index, game in enumerate(view) if game["app_id"] in new_release_top_seller_ids]
            elif selected_top_sellers >= 2:
                eligible_indices = [index for index, game in enumerate(view) if game["app_id"] not in new_release_top_seller_ids]
            else:
                eligible_indices = list(range(len(view)))
            if not eligible_indices:
                eligible_indices = list(range(len(view)))
            eligible_games = [view[index] for index in eligible_indices]
            eligible_weights = [view_weights[index] for index in eligible_indices]
            chosen = random.choices(eligible_games, weights=eligible_weights, k=1)[0]
        else:
            chosen = random.choices(view, weights=view_weights, k=1)[0]
        if chosen["label_matches"]["level_3"] or chosen["label_matches"]["level_2_core"] or chosen["label_matches"]["level_1"] or chosen["label_matches"]["soft_preference"]:
            def names(group):
                return "、".join(policy_groups[group][tag_id] for tag_id in chosen["label_matches"][group]) or "无"

            chosen["reason"] = (
                f"标签匹配分 {chosen['score']}（Level 3 {len(chosen['label_matches']['level_3'])}，核心 {len(chosen['label_matches']['level_2_core'])}，"
                f"软偏好 {len(chosen['label_matches']['soft_preference'])}，一级 {len(chosen['label_matches']['level_1'])}）；"
                f"核心：{names('level_2_core')}；{chosen['price_note']}。"
            )
        elif chosen["matched_genres"]:
            reason_evidence = choose_evidence(evidence, chosen["matched_genres"], evidence_use_counts)
            labels = "、".join(chosen["matched_genres"])
            if reason_evidence:
                examples = "、".join(f"{item['name']}（{item['hours']} 小时）" for item in reason_evidence)
                chosen["reason"] = f"高游玩时长游戏《{examples}》显示 TA 偏好{labels}体验；{chosen['price_note']}。"
            else:
                chosen["reason"] = f"TA 的代表游戏整体偏好{labels}体验；{chosen['price_note']}。"
            chosen["evidence_app_ids"] = [item["app_id"] for item in reason_evidence]
            evidence_use_counts.update(chosen["evidence_app_ids"])
        selection.append(chosen)
        if priority == "balanced" and is_in_category(chosen, {"new_releases"}):
            new_release_count += 1
        index = pool.index(chosen)
        pool.pop(index)
        weights.pop(index)
        if priority == "balanced" and not using_new_release_fallback and new_release_count >= 1:
            pool_and_weights = [(game, weight) for game, weight in zip(pool, weights) if not is_in_category(game, {"new_releases"})]
            pool = [game for game, _ in pool_and_weights]
            weights = [weight for _, weight in pool_and_weights]
    spread_batch_evidence(selection, label_profile, evidence_use_counts)
    result = selection, tagged_preference_sample_size or preference_sample_size
    if include_preference_tags:
        return *result, preference_tags, sorted(active_tag_ids), sorted(rejected_tag_ids)
    return result

def score_single_candidate(games, candidate, steam_id, api_key):
    """Score one specific game against the target user's profile.

    The whole catalogue is scored so the 0-100 value uses the same distribution
    as the recommendation cards, then only the requested game is returned.
    """
    try:
        catalog = get_store_catalog()
    except requests.RequestException:
        catalog = [candidate]
    if not any(int(game["app_id"]) == int(candidate["app_id"]) for game in catalog):
        catalog = [*catalog, candidate]
    selection, sample_size = recommend(
        games, priority="balanced", candidates=catalog, steam_id=steam_id, api_key=api_key,
        single_candidate=int(candidate["app_id"]),
    )
    if not selection:
        return None, sample_size
    return selection[0], sample_size


def find_catalog_game(query):
    catalog = get_store_catalog()
    app_id = extract_app_id(query)
    if app_id is not None:
        for game in catalog:
            if int(game["app_id"]) == app_id:
                return game, []
        return None, []
    needle = query.strip().casefold()
    if not needle:
        return None, []
    exact = [game for game in catalog if game["name"].casefold() == needle]
    if exact:
        return exact[0], []
    partial = [game for game in catalog if needle in game["name"].casefold()]
    partial.sort(key=lambda game: (len(game["name"]), -(game.get("review_count") or 0)))
    if len(partial) == 1:
        return partial[0], []
    return None, partial[:8]


def extract_app_id(query):
    match = re.search(r"/app/(\d+)", query) or re.fullmatch(r"\s*(\d{3,10})\s*", query)
    return int(match.group(1)) if match else None


@app.get("/")
def index():
    return render_template("index.html", server_managed_api_key=bool(os.environ.get("STEAM_API_KEY")))


@app.post("/api/recommendations")
def recommendations():
    payload = request.get_json(silent=True, force=True) or {}
    api_key = os.environ.get("STEAM_API_KEY") or payload.get("api_key", "").strip()
    if not api_key:
        return jsonify(error="请填写 Steam Web API 密钥，或在服务器设置 STEAM_API_KEY。"), 400

    profile_input = payload.get("profile", "")
    try:
        steam_id = resolve_steam_id(profile_input, api_key)
        profile, games = get_profile_and_library(steam_id, api_key)
        excluded_ids = [int(app_id) for app_id in payload.get("exclude_app_ids", []) if str(app_id).isdigit()]
        min_price = max(0, float(payload.get("min_price", 0)))
        max_price = max(min_price, float(payload.get("max_price", 9999)))
        evidence_use_counts = {
            int(app_id): int(count) for app_id, count in payload.get("evidence_use_counts", {}).items()
            if str(app_id).isdigit() and isinstance(count, int) and count >= 0
        }
        active_tag_ids = [int(tag_id) for tag_id in payload.get("active_tag_ids", []) if str(tag_id).isdigit()]
        excluded_tag_ids = [int(tag_id) for tag_id in payload.get("excluded_tag_ids", []) if str(tag_id).isdigit()]
        priority = payload.get("priority", "balanced")
        if priority not in {"balanced", "new_releases", "specials", "top_sellers"}:
            priority = "balanced"
        try:
            candidates = get_store_catalog()
        except requests.RequestException:
            candidates = CATALOG
        candidates = [
            game for game in candidates
            if (price := get_game_price(game)) is not None and min_price <= price <= max_price
        ]
        if not candidates:
            return jsonify(error=f"预算 {format_price(min_price)} 至 {format_price(max_price)} 之间没有任何在售游戏。请放宽预算范围。"), 404
        recycled = False
        try:
            recommendations, preference_sample_size, preference_tags, applied_tag_ids, applied_excluded_tag_ids = recommend(
                games, excluded_ids, evidence_use_counts, priority, candidates, steam_id, api_key,
                active_tag_ids, include_preference_tags=True, excluded_tag_ids=excluded_tag_ids,
            )
        except ValueError:
            if not excluded_ids:
                raise
            recommendations, preference_sample_size, preference_tags, applied_tag_ids, applied_excluded_tag_ids = recommend(
                games, [], evidence_use_counts, priority, candidates, steam_id, api_key,
                active_tag_ids, include_preference_tags=True, excluded_tag_ids=excluded_tag_ids,
            )
            recycled = True
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {executor.submit(get_review_summary, game["app_id"]): game for game in recommendations}
            for future in as_completed(futures):
                summary = future.result()
                if summary:
                    futures[future].update(summary)
        return jsonify(
            profile={"name": profile.get("personaname", "Steam 玩家"), "avatar": profile.get("avatarfull", "")},
            library_size=len(games),
            preference_sample_size=preference_sample_size,
            preference_tags=preference_tags,
            applied_tag_ids=applied_tag_ids,
            applied_excluded_tag_ids=applied_excluded_tag_ids,
            recommendations=recommendations,
            recycled=recycled,
        )
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except requests.RequestException:
        return jsonify(error="连接 Steam 时发生问题，请稍后重试。"), 502


@app.get("/api/game-suggest")
def game_suggest():
    query = (request.args.get("q") or "").strip()
    if len(query) < 1:
        return jsonify(suggestions=[])
    try:
        catalog = get_store_catalog()
    except requests.RequestException:
        return jsonify(suggestions=[])
    app_id = extract_app_id(query)
    if app_id is not None:
        matches = [game for game in catalog if int(game["app_id"]) == app_id]
    else:
        needle = query.casefold()
        matches = [game for game in catalog if needle in game["name"].casefold()]
        # Prefix matches first, then shorter names, then better known titles.
        matches.sort(key=lambda game: (
            not game["name"].casefold().startswith(needle),
            len(game["name"]),
            -(game.get("review_count") or 0),
        ))
    return jsonify(suggestions=[
        {
            "app_id": game["app_id"],
            "name": game["name"],
            "image": game.get("image", ""),
            "review_count": game.get("review_count") or 0,
        }
        for game in matches[:8]
    ])


@app.post("/api/game-score")
def game_score():
    payload = request.get_json(silent=True, force=True) or {}
    api_key = os.environ.get("STEAM_API_KEY") or payload.get("api_key", "").strip()
    if not api_key:
        return jsonify(error="请填写 Steam Web API 密钥，或在服务器设置 STEAM_API_KEY。"), 400
    query = (payload.get("query") or "").strip()
    if not query:
        return jsonify(error="请输入游戏名称、Steam 商店链接或 App ID。"), 400
    try:
        candidate, suggestions = find_catalog_game(query)
        if candidate is None:
            if suggestions:
                return jsonify(
                    error=f"找到 {len(suggestions)} 款名称相近的游戏，请选择其中一个再查询。",
                    suggestions=[{"app_id": game["app_id"], "name": game["name"]} for game in suggestions],
                ), 404
            return jsonify(error="商店目录里没有找到这款游戏。可以试试它在 Steam 上的原名（很多游戏没有官方中文名），或直接粘贴商店链接 / App ID。目录只收录有中国区售价的完整游戏，不含 DLC、免费游戏与软件。"), 404

        steam_id = resolve_steam_id(payload.get("profile", ""), api_key)
        profile, games = get_profile_and_library(steam_id, api_key)
        owned = int(candidate["app_id"]) in {int(game["appid"]) for game in games if str(game.get("appid", "")).isdigit()}
        scored, sample_size = score_single_candidate(games, candidate, steam_id, api_key)
        summary = get_review_summary(candidate["app_id"])
        if scored is None:
            fallback = {**candidate}
            if summary:
                fallback.update(summary)
            return jsonify(
                error="这款游戏面向特定受众，而 TA 的游戏库里没有同类作品，因此不会被推荐，也不计算匹配分。下面仍列出它的基本信息。",
                game=fallback,
                already_owned=owned,
            ), 200
        if summary:
            scored.update(summary)
        return jsonify(
            profile={"name": profile.get("personaname", "Steam 玩家")},
            preference_sample_size=sample_size,
            already_owned=owned,
            game=scored,
        )
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except requests.RequestException:
        return jsonify(error="连接 Steam 时发生问题，请稍后重试。"), 502


@app.post("/api/seed-recommendations")
def seed_recommendations():
    """Recommend games the gift giver already owns to a target friend."""
    payload = request.get_json(silent=True, force=True) or {}
    api_key = os.environ.get("STEAM_API_KEY") or payload.get("api_key", "").strip()
    if not api_key:
        return jsonify(error="请填写 Steam Web API 密钥，或在服务器设置 STEAM_API_KEY。"), 400
    try:
        owner_id = resolve_steam_id(payload.get("owner_profile", ""), api_key)
        target_id = resolve_steam_id(payload.get("profile", ""), api_key)
        if owner_id == target_id:
            return jsonify(error="两个资料指向同一个账号，请填入不同的个人资料。"), 400
        owner_profile, owner_games = get_profile_and_library(owner_id, api_key)
        target_profile, target_games = get_profile_and_library(target_id, api_key)

        catalog_by_id = {int(game["app_id"]): game for game in get_store_catalog()}
        target_owned = {int(game["appid"]) for game in target_games if str(game.get("appid", "")).isdigit()}
        played_owner_games = [
            game for game in owner_games
            if game.get("playtime_forever", 0) >= MIN_PREFERENCE_PLAYTIME_MINUTES
            and int(game["appid"]) not in target_owned
        ]
        played_owner_games.sort(key=lambda game: game.get("playtime_forever", 0), reverse=True)
        candidates = []
        for game in played_owner_games[:PREFERENCE_GAME_LIMIT]:
            entry = catalog_by_id.get(int(game["appid"]))
            if not entry:
                continue
            candidates.append({**entry, "owner_hours": round(game.get("playtime_forever", 0) / 60, 1)})
        if not candidates:
            return jsonify(
                error="你玩过、且 TA 还没有的游戏中，没有一款在当前商店目录里。目录只收录有中国区售价的完整游戏。"
            ), 404

        min_price = max(0, float(payload.get("min_price", 0)))
        max_price = max(min_price, float(payload.get("max_price", 9999)))
        candidates = [
            game for game in candidates
            if (price := get_game_price(game)) is not None and min_price <= price <= max_price
        ]
        if not candidates:
            return jsonify(error="符合条件的游戏都不在当前预算范围内，请放宽预算。"), 404

        excluded_ids = [int(app_id) for app_id in payload.get("exclude_app_ids", []) if str(app_id).isdigit()]
        evidence_use_counts = {
            int(app_id): int(count) for app_id, count in payload.get("evidence_use_counts", {}).items()
            if str(app_id).isdigit() and isinstance(count, int) and count >= 0
        }
        active_tag_ids = [int(tag_id) for tag_id in payload.get("active_tag_ids", []) if str(tag_id).isdigit()]
        excluded_tag_ids = [int(tag_id) for tag_id in payload.get("excluded_tag_ids", []) if str(tag_id).isdigit()]
        recycled = False
        try:
            recommendations, sample_size, preference_tags, applied_tag_ids, applied_excluded_tag_ids = recommend(
                target_games, excluded_ids, evidence_use_counts, "balanced", candidates, target_id, api_key,
                active_tag_ids, include_preference_tags=True, excluded_tag_ids=excluded_tag_ids,
            )
        except ValueError:
            if not excluded_ids:
                raise
            recommendations, sample_size, preference_tags, applied_tag_ids, applied_excluded_tag_ids = recommend(
                target_games, [], evidence_use_counts, "balanced", candidates, target_id, api_key,
                active_tag_ids, include_preference_tags=True, excluded_tag_ids=excluded_tag_ids,
            )
            recycled = True
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {executor.submit(get_review_summary, game["app_id"]): game for game in recommendations}
            for future in as_completed(futures):
                summary = future.result()
                if summary:
                    futures[future].update(summary)
        return jsonify(
            profile={"name": target_profile.get("personaname", "Steam 玩家"), "avatar": target_profile.get("avatarfull", "")},
            owner={"name": owner_profile.get("personaname", "你"), "playable_count": len(candidates)},
            library_size=len(target_games),
            preference_sample_size=sample_size,
            preference_tags=preference_tags,
            applied_tag_ids=applied_tag_ids,
            applied_excluded_tag_ids=applied_excluded_tag_ids,
            recommendations=recommendations,
            recycled=recycled,
        )
    except ValueError as error:
        return jsonify(error=str(error)), 400
    except requests.RequestException:
        return jsonify(error="连接 Steam 时发生问题，请稍后重试。"), 502


@app.post("/api/feedback")
def submit_feedback():
    message = (request.form.get("message") or "").strip()
    if not message:
        return jsonify(error="请先写下你的反馈内容。"), 400
    if len(message) > FEEDBACK_MAX_MESSAGE_CHARS:
        return jsonify(error=f"反馈内容请控制在 {FEEDBACK_MAX_MESSAGE_CHARS} 字以内。"), 400
    contact = (request.form.get("contact") or "").strip()[:120]
    anonymous = request.form.get("anonymous") == "true"

    saved_image = None
    upload = request.files.get("image")
    if upload and upload.filename:
        # Never trust the uploaded name or extension; decide both from the bytes.
        head = upload.read(FEEDBACK_MAX_IMAGE_BYTES + 1)
        if len(head) > FEEDBACK_MAX_IMAGE_BYTES:
            return jsonify(error="图片请控制在 4 MB 以内。"), 400
        extension = detect_image_extension(head)
        if not extension:
            return jsonify(error="只支持 PNG、JPEG、GIF 或 WebP 格式的图片。"), 400
        FEEDBACK_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        saved_image = f"{uuid.uuid4().hex}{extension}"
        (FEEDBACK_IMAGE_DIR / saved_image).write_bytes(head)

    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "message": message,
        "contact": "" if anonymous else contact,
        "anonymous": anonymous,
        "image": saved_image,
    }
    with feedback_lock:
        FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
        with FEEDBACK_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return jsonify(ok=True)


def detect_image_extension(data):
    signatures = (
        (b"\x89PNG\r\n\x1a\n", ".png"),
        (b"\xff\xd8\xff", ".jpg"),
        (b"GIF87a", ".gif"),
        (b"GIF89a", ".gif"),
    )
    for prefix, extension in signatures:
        if data.startswith(prefix):
            return extension
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


if __name__ == "__main__":
    app.run(debug=True)