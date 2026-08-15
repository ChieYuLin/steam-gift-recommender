# Gift Scout Progress Log

Last updated: 2026-08-15

## Current Catalog Expansion

- Source manifest: 5,785 unique Steam app candidates.
- Sources are merged by Steam `app_id`; a game can belong to multiple categories.
- Source memberships in the current manifest:
  - `top_sellers`: 1,899
  - `specials`: 1,975
  - `highly_rated`: 1,967
  - `new_releases`: 1,266
- New-game requirement: a game must have a parseable Steam release date within the latest 31 days to remain in `new_releases`.
- Catalog inclusion requirements:
  - Steam `type == "game"`
  - A nonzero China-store current price
  - Genre metadata and Steam tag IDs
- DLC, season passes, music packs, demos, tools, and other non-game Steam app types have been removed from the existing catalog.
- Existing-catalog type verification completed: 507 / 507 remaining entries are Steam `game` entries.
- Batch enrichment is resumable. Each catalog batch processes up to 100 source candidates and atomically updates `data/store_catalog_cn.json`.
- Read-only progress command:

```bash
cd /pct_ids/users/z005a7xf/steam-gift-recommender
. .venv/bin/activate
python update_catalog.py --progress
```

- Readable tag names are collected separately from each game's Steam store page. Every catalog game has `tag_ids`; `tag_labels` can be backfilled without re-fetching price or game details:

```bash
python update_catalog.py --backfill-labels --batch-size 100
```

## Per-Search Recommendation Pipeline

One recommendation request has these stages.

1. Resolve the public Steam profile and fetch the owned library.
2. Apply hard candidate filters:
   - target user already owns the app
   - the app was shown earlier within the current store-priority category
   - candidate has excluded tags
   - candidate price is outside the selected budget
   - selected priority does not contain the candidate
   - `new_releases` additionally requires a valid release date within 31 days
3. Select up to 60 representative owned games after an engagement calculation.
4. Build a Golden Label preference profile from the top-ranked tags of representative games.
5. Score each eligible catalog candidate against that profile.
6. Apply confidence ordering, category priority rules, and weighted random selection for a four-game batch.
7. Fetch cached Steam review summaries only for the final displayed games, not for the entire catalog.

## Active Mathematical / Numeric Steps

There are 6 explicit numeric calculations in the current search path. Three are the main recommendation calculations; the others support evidence diversity, category exploration, or display.

### 1. Engagement score for owned games

For each eligible owned game, where $h$ is lifetime hours, $a$ is achievement completion fraction, $n$ is achievement count, and $d$ is days since last play:

$$
r_a = \min(1, n / 20)
$$

$$
c = a \cdot r_a
$$

$$
r_t = e^{-d / 180}
$$

$$
E = \log(1 + h) + 4c + 3r_t
$$

The achievement-completion coefficient is 4. The recent-play coefficient is 3, so a game played today receives a $+3$ recent-play contribution, while a game played 180 days ago receives approximately $+1.10$:

$$
3e^{-180/180} \approx 1.10
$$

Here, 180 is the exponential decay constant, not the literal half-life. The actual half-life is approximately $180\ln2 \approx 125$ days. This selects representative games without letting one old, idle game dominate solely because of playtime, while making recent play materially affect the ranking.

### 2. Representative-game stratification

The top engagement-scored games are selected across three playtime ranges:

- More than 120 hours: up to 20 games
- 10 to 120 hours: up to 25 games
- 2 to 10 hours: up to 15 games

The result is capped at 60 games. This is a numeric selection rule, not a score equation.

### 3. Golden Label candidate match score

For a candidate game:

- $N_2$: count of matched Level 2 core labels
- $N_s$: count of matched soft-preference labels
- $N_1$: count of matched Level 1 labels

$$
S = 6N_2 + 2N_s + N_1
$$

Only the candidate's first 5 tags can match Level 2 core labels; the first 10 tags can match Level 1 or soft labels. Each representative game contributes at most 3 Golden Labels.

Confidence is derived from the same match counts:

- High: at least 2 Level 2 core matches
- Medium: 1 Level 2 core match plus at least 2 Level 1 matches
- Low: all other label-match cases

Low-confidence results are ordered after high and medium results, but remain available once stronger candidates are exhausted.

### 4. Fallback basic-type signal

This is used only if no usable Golden Label profile can be built. For a representative library game at playtime rank $q$ with $m$ lifetime minutes:

$$
w = \max(1, 8 - \lfloor q / 4 \rfloor) + \min(6, \lfloor m / 600 \rfloor)
$$

A keyword hit adds $w$ to one of the coarse types: RPG, action, simulation, strategy, indie, multiplayer, or adventure. A candidate fallback score is the sum of its matched type signals.

### 5. Evidence diversity weight

When selecting source games that explain a matched label or fallback type, an evidence game already shown $u$ times receives:

$$
w_e = \frac{1}{1 + u}
$$

This changes which owned games are cited as evidence across refreshes without changing the candidate's match score.

### 6. Final within-pool sampling weight

Candidates in the chosen category pool are sampled without replacement using:

$$
w_c = \max(1, S + 2)
$$

In balanced mode only, a new-release candidate has its sampling weight scaled by:

$$
w_{new} = 0.22 \cdot w_c
$$

This keeps balanced mode focused on established candidates while allowing a small amount of new-game exploration. New-game priority uses a separate composition rule: each four-game batch includes at least one and at most two games that are both recent and currently in the Steam top-seller list, when such games exist.

## Display-Only Calculation

Steam review positivity is calculated for final displayed games:

$$
P = 100 \cdot \frac{\text{positive reviews}}{\text{total reviews}}
$$

It maps to display labels such as `好评如潮`, `特别好评`, `多半好评`, `褒贬不一`, and `多半差评`. It currently informs display, not the recommendation score.

## External Requests Per Search

Typical uncached request path:

- Steam profile and owned library: 2 requests, plus vanity-ID resolution if needed
- Achievement summaries: up to the selected engagement-candidate set, concurrent and cached for 1 hour
- Owned-game tag pages: only missing representative-game tags, capped at 60 and cached locally
- Live top-seller page: only for `new_releases`, cached for 30 minutes
- Review summaries: only the final displayed games, usually up to 4 and cached for 6 hours

The catalog itself is read from the local snapshot; a normal recommendation request does not scan or re-fetch all catalog pages from Steam.

## Known Improvement Targets

- Use the expanding full `tag_id -> Chinese tag name` mapping to improve explanation quality.
- Revisit fixed Golden Label weights after the catalog and tag-label backfill complete.
- Consider adding review quality, price sensitivity, and category breadth as explicit ranking features rather than display-only metadata.
- Keep actual-game validation, China price availability, and recent-release date checks as hard filters.

## 2026-08-15 Session: Scoring Calibration, Tag Redundancy, and Batch Integrity

This session reworked how a raw match is turned into the number and rarity grade
shown on a card, removed several sources of score inflation, and fixed two bugs
that were introduced during the same session.

### Score scale: one yardstick for every mode

Previously each request calibrated the 0-100 scale on whatever candidate set it
happened to score. Gift mode scored the whole catalog, seed mode scored only the
gift giver's library, so an identical match read 99 in seed mode and 92 in gift
mode.

- `profile_depth_reference()` now scores the entire catalog for the active
  profile and returns the depth distribution used to calibrate both modes.
- It mirrors the scoring path exactly: outlier-tag filtering, banned-pair and
  audience-gate exclusion, per-group rank and match limits, family collapsing,
  Level 3 pair promotion, and the mismatch penalty. An earlier version skipped
  the last three steps, which biased the ceiling upward and pushed every gift
  mode card into the forties.
- Verified: across 7 profiles, every game that appeared in both modes received an
  identical percentage (0 mismatches). Single-game lookup already shared the gift
  mode path, so all three surfaces agree.
- Cost: one extra full-catalog depth pass, about 200 ms per request.

### Score scale: shape

- `MATCH_DEPTH_FLOOR` (2.6) replaced the previous fixed reference depth of 4.6.
  The old fixed top meant no profile could reach the upper end of the scale;
  measured maximum reachable depths were 2.25 to 3.4, so SR (78) was unreachable
  and every user sat at 40-70 permanently.
- The ceiling is now the profile's own reachable maximum times
  `MATCH_CEILING_HEADROOM` (1.12), floored at `MATCH_DEPTH_FLOOR` so a nearly
  empty profile cannot call its best guess a perfect match.
- `MATCH_PERCENT_SPREAD` (1.5) stretches positions around
  `MATCH_PERCENT_PIVOT` (0.4). Real match depths bunch into a narrow band, so a
  plain linear map produced "everything is 60-ish". Standard deviation of shown
  scores rose from 8.0 to 12.6.
- Parameters were chosen by sweeping spread 1.5/1.8/2.2 against baseline anchor
  30/40. Higher spreads widened the range only by forcing the top band to 100,
  which inflated UR to 10-14% and destroyed the rarity pyramid.

### Rarity grades

- Rarity is read directly off the displayed percentage, so a high score can never
  be labelled common: UR >= 95, SSR >= 88, SR >= 78, R >= 65, N below.
  An earlier design derived the grade from absolute depth while the number came
  from a relative distribution, which produced cards reading "83 points, N".
- The grade and its explanation are computed server-side and sent as
  `match_tier` / `match_tier_note`; the frontend no longer infers grades.

### Rarity pacing and guarantees

- `SR_PITY_CARDS` (12) and `SSR_PITY_CARDS` (36): if the window is about to pass
  without that grade, an eligible card claims a slot, and the pool is topped up
  from `ranked` if nothing in the pool qualifies.
- `SSR_EARLIEST_CARD` (8) and `UR_EARLIEST_CARD` (20) hold the top grades back
  from the opening pages; `MAX_HIGH_TIER_PER_BATCH` (1) prevents clustering.
  Guarantees override pacing, so a pity draw is never blocked.
- Before this, the first page contained an SSR or UR in 6 of 6 test runs, because
  the adaptive ceiling means page one always shows the deepest matches available.

### Tag redundancy: no more double counting

Card games routinely carry `卡牌战斗`, `牌组构建`, `卡牌游戏` and collected three
separate core matches for what is one taste.

- Redundant groups were identified from catalog co-occurrence rather than by
  hand: pairs where each tag appears in at least 50% of the other's games.
  Measured: 卡牌游戏 x 牌组构建 64%, 合作 x 在线合作 58%, 回合战略 x 回合制战术
  57%, 合作 x 多人 57%, 增量 x 挂机游戏 55%, 牌组构建 x 卡牌战斗 53%,
  棋盘游戏 x 桌上游戏 50%.
- `tag_match_families` grew from one family to five; a family scores once, using
  the member ranked highest on that candidate's store page.

### Mismatch penalty

A football game could reach a respectable score for someone who dislikes sport,
purely from generic multiplayer tags.

- `uninterested_tags()` returns the candidate's headline tags (rank <= 6) that
  are recognised gameplay tags, absent from the target's profile, and not
  semantically covered by it.
- `mismatch_factor()` shrinks depth by `MISMATCH_WEIGHT` (0.22) times the sum of
  `tag_rank_factor(rank) ** 3`, floored at `MISMATCH_MIN_FACTOR` (0.45). The cubic
  term concentrates the penalty on tags in the first two positions.
- Applied identically in scoring and in the calibration reference; applying it in
  only one place would break cross-mode parity.
- Measured on 开球! REMATCH: 40 -> 20 points for a profile with no sport history,
  while a sport-playing profile rose to 45.

### Semantic overlap in "not interested" hints

- `get_tag_overlap_map()` treats two tags as interchangeable when at least 60% of
  the games carrying one also carry the other, ignoring partners that appear on
  more than 20% of the catalog. Without that guard `单人` (77.6% of the catalog)
  suppressed every hint.
- Chinese tag names are also checked for containment, so 回合制战斗 counts as
  covered by 回合制 even where co-occurrence is weak.
- The card no longer reports 牌组构建式类 Rogue as a mismatch for a player who
  already likes 牌组构建 and 类 Rogue.

### Passive playtime

Idle games and desktop companions accumulate wall-clock hours while nobody is
playing them, which made 生物收集 the strongest directed tag for a user who had
never opened those games.

- `passive_playtime_tags` (桌面伴侣, 挂机游戏, 增量, 实用工具) trigger
  `PASSIVE_PLAYTIME_FACTOR` (0.2) when present in a game's first
  `PASSIVE_PLAYTIME_RANK_LIMIT` (5) tags.
- The core-tag eligibility threshold uses the discounted hours as well.
- Evidence cards show a `挂机时长已折算` note when a cited game was discounted.
- Effect: 生物收集 fell from full weight (10.0) to 2.2.

### Directed tags scale continuously

The previous rule demoted an unconfirmed Level 3 tag outright, a cliff between
one and two supporting games and no difference between two and ten.

- `confirm_level_3_tags()` was removed. `level_3_confirmation()` scales the tag
  by summed engagement of games where it is a defining tag (rank <= 5),
  normalised against `LEVEL_3_MIN_CONFIRMING_SOURCES` top games, with a floor of
  `LEVEL_3_UNCONFIRMED_FLOOR` (0.4).
- Measured for one tag: 1 game / 5h -> 2.6, 1 game / 100h -> 3.5,
  3 games / 20h -> 6.7, 5 games / 100h -> 10.0 (full weight).
- Removing the layer swap also eliminated a crash class: a demoted tag used to
  move to `level_2_core` while its name stayed registered under `level_3`,
  raising `KeyError` during serialisation.

### Audience gating is now permanent

- Owning an audience-specific game no longer unlocks that category. Previously a
  single romance visual novel in a large library opened the entire gated set;
  raising the threshold to two was rejected as arbitrary.
- Verified: with 0, 1, and 4 matching games in the library, 48-card runs returned
  0 gated recommendations in all three cases.
- Single-game lookup still scores and explains a gated title.

### Popularity and acclaim in selection

Scoring stays purely about taste; recognition only decides which of several good
matches gets the slot.

- `popularity_factor()` combines review count against
  `well_known_review_count`, positive rate above `ACCLAIM_MIN_POSITIVE_RATE`
  (80), `TOP_SELLER_BONUS` (1.3) and `FRESH_AND_POPULAR_BONUS` (1.4).
- Weighting alone could not surface titles that never entered the pool, so each
  batch tops the pool up to `POOL_WELL_KNOWN_TARGET` (8) recognisable games drawn
  from the top `WELL_KNOWN_TOPUP_DEPTH` (80) by score, and guarantees
  `MIN_WELL_KNOWN_PER_BATCH` (2) per page.
- Share of shown cards with >= 5,000 reviews rose from 29% to 55%.

### Bugs found and fixed

- **Duplicate cards on one page.** 193 catalog games belong to both a storefront
  category and the new-release list, so the pool held two copies. The pool is now
  deduplicated by `app_id`.
- **Batches returning three cards.** The per-batch constraints overwrote `pool`,
  permanently discarding candidates that were merely deferred. Constraints are
  now evaluated as a per-slot view over an intact pool. 72 test batches returned
  four cards each.
- **SSR/UR flooding after that fix.** The new view fell back to the unrestricted
  pool whenever every candidate was blocked, which is common when a profile's top
  candidates are all high grade. The fallback now prefers the lowest available
  grade.
- **Duplicate tag definition.** `1199779 撤离射击` was defined in both
  `level_2_core` and `level_3`, the only such tag. It scored twice and counted as
  two independent pieces of evidence. A per-game guard now prevents any tag from
  being counted in two layers.
- **Tag-list duplicates.** `filter_outlier_tags()` deduplicates while preserving
  order, so name resolution cannot reintroduce a tag already present.
- **Discount page titles.** Store titles of the form
  `在 Steam 上购买 X 立省 N%` are reduced to the game name.
- **Achievement cache lost on restart.** The cache was memory-only, so every
  restart re-fetched an achievement call per representative game. It now persists
  to `data/steam_achievement_cache.json` with a one-hour lifetime.
- **Store retry storm.** `store_json()` used five attempts with 1.5s-6s backoff
  and a 12s timeout, up to a minute per call under throttling. Now three attempts,
  0.8s-1.6s backoff, 8s timeout.
- **Release-date parsing.** `parse_release_date()` is cached; it was parsing date
  strings for every catalog game on every request.

### Explanation surfaces

- Cards show a `TA 似乎不感兴趣` block listing headline tags the target shows no
  interest in, with the tag's rank on that game, styled like the general
  preference block but colour-inverted. The block is omitted when empty.
- Evidence selection favours sources where the matched tag ranks high on the
  cited game, so a tag is explained by a game that leads with it.
- Loading messages expanded from 10 to 22 and shuffled per request.

### Known limitations

- Scores are calibrated per profile, so they are not comparable between people.
  A player with concentrated taste has a higher reachable ceiling, so ordinary
  recommendations read lower: measured SR share ranges from 0% to 17% across
  eight profiles. Shown cards use 63-100% of the available scale depending on the
  profile.
- Seed mode scores are genuinely lower than gift mode because one personal
  library cannot match a 3,400-game catalog. This is intended.
- Testing used real catalog tag data with synthetic playtimes, so distribution
  shapes are reliable while individual game placements are not.

### Depth rewards precision, not breadth (late 2026-08-15)

A player whose favourite game is Hollow Knight saw it score 41. Investigation
showed the depth sum rewarded how many tags overlapped, not how well:

- Hollow Knight: 2 core matches, depth 1.06 -> 41 points
- Amnesia: 4 looser matches, depth 2.61 -> 79 points

`combine_match_depth()` now raises each per-tag quality to
`MATCH_DEPTH_CONCENTRATION` (2.0) before summing and takes the matching root, so
the strongest matches dominate while extra matches still help. At 1.0 it reduces
to the previous plain sum.

- Hollow Knight for a Metroidvania profile: 41 -> 95 (UR).
- Hollow Knight for a profile with no such history: 41, unchanged.
- `29482 类魂系列` and `1628 类银河战士恶魔城` moved from `level_2_core` to
  `level_3`; both are narrow, deliberate tastes. Level 3 now holds 16 tags.

Concentration shrinks absolute depths, so the scale needed recalibrating.
`MATCH_PERCENT_BASELINE_PERCENTILE` moved 90 -> 75 -> 30 across two sweeps
(percentile 60/45/30 against anchor 35/40). Without this the gift-mode median
fell to 55 with 85% N.

### Flat spot at exactly 40 points

`min(1, max(0, pivot + (position - pivot) * spread))` clamped every position
below 0.133 to zero, so every such game reported exactly
`MATCH_PERCENT_BASELINE_ANCHOR`. Seed mode candidates sit almost entirely in that
range, which is why no score above 40 was ever observed there. The stretch is now
a monotone power curve around the pivot with no flat region.

### Current distribution

24 profiles, 288 pages, 1,152 cards, gift mode:

- N 45.4%, R 43.5%, SR 9.4%, SSR 1.6%, UR 0.2%
- SSR on 14 of 288 pages, UR on 2 of 288 pages, best score 96
- Four cards per batch in all 48 measured batches
- Cross-mode parity: 16 shared games, 0 mismatches

Random profiles have diffuse taste by construction, so real users with focused
libraries should see high grades more often than these figures suggest.
