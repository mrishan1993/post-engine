from __future__ import annotations

from typing import Any

from verification_engine.schemas import ActualSnapshot, PredictionSnapshot, RootCauseAnalysis


def diagnose(
    prediction: PredictionSnapshot,
    actual: ActualSnapshot,
    *,
    metric_rows: list[dict[str, Any]],
) -> RootCauseAnalysis:
    """Probabilistic failure taxonomy — association, not causation."""
    qa = actual.qa_score
    views_row = next((m for m in metric_rows if m.get("metric") == "views"), None)
    viral_row = next(
        (m for m in metric_rows if m.get("metric") in {"viral_target", "virality"}), None
    )

    taxonomy: list[str] = []
    contributing: list[str] = []
    primary_type = "within_expected_range"
    primary_conf = 0.5
    model_err_conf = 0.3

    # Execution vs model split
    execution_bad = qa is not None and qa < 0.7
    overpredicted = False
    underpredicted = False
    if views_row and views_row.get("relative_error") is not None:
        rel = float(views_row["relative_error"])
        if rel < -0.3:
            overpredicted = True
        elif rel > 0.3:
            underpredicted = True

    if viral_row and viral_row.get("outcome") is False and (viral_row.get("predicted_value") or 0) >= 0.7:
        overpredicted = True
        taxonomy.append("MODEL_OVERCONFIDENCE")
    if viral_row and viral_row.get("outcome") is True and (viral_row.get("predicted_value") or 1) <= 0.45:
        underpredicted = True
        taxonomy.append("MODEL_UNDERCONFIDENCE")

    if execution_bad and overpredicted:
        primary_type = "execution_failure"
        primary_conf = 0.82
        model_err_conf = 0.18
        contributing.extend(["VISUAL_QUALITY", "CHARACTER_MISMATCH"])
        taxonomy.append("EXECUTION_FAILURE")
    elif overpredicted and not execution_bad:
        primary_type = "prediction_model_error"
        primary_conf = 0.74
        model_err_conf = 0.74
        # Signal hints from prediction.signals (association only)
        signals = prediction.signals or {}
        if float(signals.get("trend_velocity") or 0) > 0.85:
            taxonomy.append("TREND_FALSE_SIGNAL")
            contributing.append("trend_signal_may_be_overweighted")
        if float(signals.get("hook_strength") or 0) < 0.5:
            taxonomy.append("HOOK_WEAK")
        if not taxonomy:
            taxonomy.append("FEATURE_MISWEIGHT")
    elif underpredicted:
        primary_type = "prediction_model_error"
        primary_conf = 0.7
        model_err_conf = 0.7
        taxonomy.append("MODEL_UNDERCONFIDENCE")
        contributing.append("breakout_underestimated")
    else:
        primary_type = "aligned"
        primary_conf = 0.8
        model_err_conf = 0.2

    # Segment tags as soft context
    segs = prediction.segments or {}
    if segs.get("character"):
        contributing.append(f"character={segs['character']}")
    if segs.get("hook_type"):
        contributing.append(f"hook_type={segs['hook_type']}")

    return RootCauseAnalysis(
        primary={"type": primary_type, "confidence": round(primary_conf, 2)},
        contributing_factors=contributing,
        prediction_model_error={"confidence": round(model_err_conf, 2)},
        taxonomy_codes=list(dict.fromkeys(taxonomy)),
        note="Association-based diagnosis; not causal proof",
    )


def build_learning_signals(
    prediction: PredictionSnapshot,
    actual: ActualSnapshot,
    *,
    metric_rows: list[dict[str, Any]],
    diagnosis: RootCauseAnalysis,
    confidence_label: str,
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    viral = next((m for m in metric_rows if m.get("metric") in {"viral_target", "virality"}), None)
    eng = next((m for m in metric_rows if m.get("metric") == "engagement"), None)

    error_payload = {}
    for m in metric_rows:
        if m.get("relative_error") is not None:
            error_payload[m["metric"]] = m["relative_error"]

    signals.append(
        {
            "signal_type": "prediction_error_vector",
            "signal_value": {
                "content_id": prediction.content_id,
                "prediction_id": prediction.id,
                "outcome": "success"
                if viral and viral.get("outcome") is True
                else "failure"
                if viral and viral.get("outcome") is False
                else "unknown",
                "confidence_label": confidence_label,
                "prediction_error": error_payload,
                "segments": prediction.segments,
            },
            "confidence": 0.8,
        }
    )

    # Signal association notes (not causal)
    for name, value in (prediction.signals or {}).items():
        observed = "high" if (viral and viral.get("outcome")) else "low"
        signals.append(
            {
                "signal_type": "signal_association",
                "signal_value": {
                    "signal": name,
                    "predicted_effect": "high" if float(value) >= 0.75 else "medium" if float(value) >= 0.5 else "low",
                    "observed_association": observed,
                    "note": "association in this sample only",
                },
                "confidence": 0.55,
            }
        )

    if diagnosis.taxonomy_codes:
        signals.append(
            {
                "signal_type": "failure_diagnosis",
                "signal_value": {
                    "primary": diagnosis.primary,
                    "taxonomy": diagnosis.taxonomy_codes,
                    "contributing": diagnosis.contributing_factors,
                },
                "confidence": float(diagnosis.primary.get("confidence") or 0.5),
            }
        )

    # Segment calibration hint
    if confidence_label in {"overconfident", "underconfident"}:
        segs = prediction.segments or {}
        signals.append(
            {
                "signal_type": "segment_calibration_hint",
                "signal_value": {
                    "label": confidence_label,
                    "platform": segs.get("platform"),
                    "character": segs.get("character"),
                    "hook_type": segs.get("hook_type"),
                    "story_type": segs.get("story_type"),
                    "engagement_error": eng.get("relative_error") if eng else None,
                },
                "confidence": 0.66,
            }
        )

    return signals
