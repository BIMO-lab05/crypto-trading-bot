"""CD-05 ML-on variant tests.

Run only with `pytest -m ml_on` AND with the stack booted under ENABLE_ML_PREDICTIONS=true.
Default suite runs ML-off (matches Phase 1 D-10 stack-default). This variant asserts model
loading and the prediction surface — it does NOT re-validate edge. V0 finding (chance-level
on log-returns) stands; edge re-validation is Phase 5.

Usage:
    pytest tests/integration/test_ml_on_variant.py -m ml_on
"""

import pytest


@pytest.mark.ml_on
@pytest.mark.asyncio
async def test_ml_models_loaded(bootstrap_stack, services_config, http_client):
    """ML-on variant: GRU prediction returns non-default confidence (model is loaded).

    confidence=0.0 is the sentinel value that means model file missing or not loaded.
    Any non-zero confidence means inference ran. Edge is NOT validated here (CD-05).
    """
    url = f"{services_config['ml_prediction']}/api/v1/predictions/SOLUSDT"
    r = await http_client.get(url, timeout=10.0)
    assert r.status_code == 200, f"ml_prediction failed: {r.status_code} {r.text}"
    body = r.json()
    prediction = body.get("prediction") or {}
    confidence = float(prediction.get("confidence", 0.0))
    # Default-confidence sentinel is 0.0 — that means model file missing or not loaded.
    # Non-zero confidence means inference ran. Edge is NOT validated here (CD-05).
    assert confidence != 0.0, (
        "ml_prediction returned confidence=0.0 — model file missing or stale. "
        "Re-train via scripts/train_ml.* and restart ml-prediction-service. "
        "(See RUNBOOK.md § Stale in-memory ML model.)"
    )


@pytest.mark.ml_on
@pytest.mark.asyncio
async def test_ml_prediction_endpoint_alive(
    bootstrap_stack, services_config, http_client
):
    """ML-on variant: prediction endpoint returns the documented shape.

    Checks response envelope only — does not assert on confidence value.
    This test runs regardless of model state (confidence=0.0 is still valid here).
    """
    url = f"{services_config['ml_prediction']}/api/v1/predictions/SOLUSDT"
    r = await http_client.get(url, timeout=10.0)
    assert r.status_code == 200
    body = r.json()
    assert "prediction" in body, f"missing 'prediction' key: {body}"
    pred = body["prediction"]
    # Documented surface: confidence scalar present.
    assert "confidence" in pred, f"missing 'prediction.confidence': {body}"
