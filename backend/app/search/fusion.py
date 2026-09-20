from __future__ import annotations


def weighted_rrf(rankings: list[tuple[float, list[int]]], k: int = 60) -> dict[int, float]:
    scores: dict[int, float] = {}
    for weight, ranking in rankings:
        for rank, patent_id in enumerate(ranking, start=1):
            scores[patent_id] = scores.get(patent_id, 0.0) + weight / (k + rank)
    return scores
