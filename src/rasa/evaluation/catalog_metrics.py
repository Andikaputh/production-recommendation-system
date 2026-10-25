"""Catalog, personalization, diversity, and exposure metrics."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping

import numpy as np

from rasa.features.builder import ContentModel


def catalog_coverage(recommendations: Iterable[Iterable[str]], catalog_size: int) -> float:
    unique = {product_id for items in recommendations for product_id in items}
    return len(unique) / max(1, catalog_size)


def user_coverage(recommendations: Mapping[str, list[str]]) -> float:
    if not recommendations:
        return 0.0
    return sum(1 for items in recommendations.values() if items) / len(recommendations)


def intra_list_diversity(items: list[str], content: ContentModel) -> float:
    indices = [content.item_index[product_id] for product_id in items if product_id in content.item_index]
    if len(indices) < 2:
        return 0.0
    vectors = content.item_matrix[indices]
    similarity = (vectors @ vectors.T).toarray()
    n = len(indices)
    pairwise = (similarity.sum() - np.trace(similarity)) / (n * (n - 1))
    return float(max(0.0, min(1.0, 1.0 - pairwise)))


def novelty(items: list[str], popularity_counts: Mapping[str, int], n_interactions: int) -> float:
    if not items or n_interactions <= 0:
        return 0.0
    values = []
    for product_id in items:
        probability = max(popularity_counts.get(product_id, 0), 1) / n_interactions
        values.append(-np.log2(probability))
    return float(np.mean(values))


def long_tail_exposure(
    items: list[str],
    popularity_counts: Mapping[str, int],
    threshold: float,
) -> float:
    if not items:
        return 0.0
    return sum(1 for product_id in items if popularity_counts.get(product_id, 0) <= threshold) / len(items)


def gini_exposure(items: Iterable[str]) -> float:
    counts = np.asarray(list(Counter(items).values()), dtype=float)
    if counts.size == 0 or counts.sum() == 0:
        return 0.0
    counts = np.sort(counts)
    n = len(counts)
    index = np.arange(1, n + 1)
    return float((2 * np.sum(index * counts) / (n * counts.sum())) - (n + 1) / n)


def summarize_catalog_metrics(
    recommendations: Mapping[str, list[str]],
    *,
    content: ContentModel,
    popularity_counts: Mapping[str, int],
    n_interactions: int,
    catalog_size: int,
    long_tail_threshold: float,
) -> dict[str, float]:
    all_items = [product_id for items in recommendations.values() for product_id in items]
    distinct = list(dict.fromkeys(all_items))
    diversities = [intra_list_diversity(items, content) for items in recommendations.values() if items]
    novelties = [novelty(items, popularity_counts, n_interactions) for items in recommendations.values() if items]
    return {
        "catalog_coverage": catalog_coverage(recommendations.values(), catalog_size),
        "user_coverage": user_coverage(recommendations),
        "intra_list_diversity": float(np.mean(diversities)) if diversities else 0.0,
        "novelty": float(np.mean(novelties)) if novelties else 0.0,
        "long_tail_exposure": long_tail_exposure(distinct, popularity_counts, long_tail_threshold),
        "exposure_gini": gini_exposure(all_items),
        "distinct_items_exposed": float(len(distinct)),
    }
