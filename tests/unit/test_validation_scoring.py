import pandas as pd

from rasa.evaluation.tuning import validation_order


def test_validation_applies_inference_cold_start_weights_and_original_tie_order():
    frame = pd.DataFrame([
        {"product_id": "warm", "candidate_order": 1, "component_collaborative": 1.0, "component_content": 0.0},
        {"product_id": "cold", "candidate_order": 0, "component_collaborative": 0.0, "component_content": 1.0},
    ])
    weights = {"collaborative": .8, "content": .2}
    assert validation_order(frame, weights, 0, 3, 1) == ["cold"]
    assert validation_order(frame, weights, 3, 3, 1) == ["warm"]
    assert validation_order(frame, {"collaborative": .5, "content": .5}, 3, 3, 1) == ["cold"]
