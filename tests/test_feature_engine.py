from src.analytics.feature_engine import (
    compute_collocations,
    compute_feature_metrics,
    extract_kwic,
)


def test_kwic_windows_and_collocation_counts():
    passages = [
        "Coverture bound wife and husband under property law.",
        "Coverture limited property ownership for the wife.",
    ]
    lines = extract_kwic(passages, ["coverture"], window=5)
    assert len(lines) == 2
    assert "husband" in lines[0]
    assert "wife" in lines[0]
    collocations = compute_collocations(passages, "coverture", top_k=5)
    assert collocations["property"] >= 1
    assert collocations["wife"] >= 1


def test_feature_metrics_are_keyed_by_slice():
    metrics = compute_feature_metrics(
        {
            "slice_1": ["Coverture shaped property and legal duty."],
            "slice_2": ["Shared property and equal legal standing."],
        },
        ["legal_standing"],
    )
    assert set(metrics) == {"slice_1", "slice_2"}
    assert "legal_standing" in metrics["slice_1"]
    assert "stance_distribution" in metrics["slice_2"]
