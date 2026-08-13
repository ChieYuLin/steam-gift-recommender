# Golden Label Standard

This directory contains the curated Steam-label policy used by the gift recommender. It is deliberately separate from `../steam_label_gold_standard.txt`, which remains the original human review source.

## Label roles

- `level_1`: broad or combination gameplay labels. They widen the candidate pool but do not independently create a strong recommendation.
- `level_2_core`: specific gameplay labels. At least two shared labels are required for a high-confidence recommendation.
- `soft_preference`: theme, aesthetic, setting, or presentation labels. They only break ties after gameplay matches.
- `exclude`: labels that must not be used as preference signals or recommended as games.

## Scoring experiment

For an owned game and a candidate game:

```text
score = 6 * shared_level_2_core + 2 * shared_soft_preference + shared_level_1
```

Confidence rules:

```text
high:   shared_level_2_core >= 2
medium: shared_level_2_core == 1 and shared_level_1 >= 2
low:    no shared_level_2_core; do not place in primary recommendations
```

## Representative owned games

Before applying the label score, the app ranks meaningful-playtime owned games by:

```text
engagement = log(1 + hours) + 2 * reliable_completion + recency
```

Achievement completion is discounted for games with very few achievements and is only used to choose representative owned games. It does not directly change the candidate-game label score.

## Steam tag rank

Steam returns tags in relevance order. Core Level 2 matches are only eligible when the tag appears in a game's first 5 Steam tags. Level 1 and soft-preference labels are only eligible in the first 10. This prevents a low-ranked generic tag from defining a game's identity.

## Files

- `label_policy.json`: machine-readable policy and the initial agreed label IDs.
- `changes_2026-08-13.md`: decision log for the first review pass.
- `../steam_label_gold_standard.txt`: unmodified source list supplied for review.
