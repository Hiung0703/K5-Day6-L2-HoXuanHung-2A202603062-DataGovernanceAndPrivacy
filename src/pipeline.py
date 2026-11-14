"""Explainable, offline pipeline for T02 Raw QC Triage."""
from __future__ import annotations

import time
from collections.abc import Iterable

import numpy as np
import pandas as pd

from .common.contact_sheet import render_contact_sheet
from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.image_ops import brightness_stats, laplacian_variance, load_rgb, to_gray
from .common.manifest import verify_manifest
from .common.review import apply_overrides, load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track


def _blockiness(gray: np.ndarray) -> float:
    """Estimate JPEG 8-pixel blocking from boundary/interior gradient contrast."""
    dx = np.abs(np.diff(gray, axis=1))
    dy = np.abs(np.diff(gray, axis=0))
    if dx.shape[1] < 8 or dy.shape[0] < 8:
        return 0.0
    x_boundary = np.arange(dx.shape[1]) % 8 == 7
    y_boundary = np.arange(dy.shape[0]) % 8 == 7
    boundary = np.concatenate([dx[:, x_boundary].ravel(), dy[y_boundary, :].ravel()])
    interior = np.concatenate([dx[:, ~x_boundary].ravel(), dy[~y_boundary, :].ravel()])
    return float(np.median(boundary) - np.median(interior))


def _local_glare(rgb: np.ndarray, grid: tuple[int, int] = (6, 10)) -> float:
    """Return the strongest tile's saturated-pixel fraction to catch local glare."""
    gray = to_gray(rgb)
    h, w = gray.shape
    rows, cols = grid
    fractions = []
    for iy in range(rows):
        y0, y1 = iy * h // rows, (iy + 1) * h // rows
        for ix in range(cols):
            x0, x1 = ix * w // cols, (ix + 1) * w // cols
            tile = gray[y0:y1, x0:x1]
            if tile.size:
                fractions.append(float(np.mean(tile > 245)))
    return max(fractions, default=0.0)


def _extract_features(ctx: RunContext, images: pd.DataFrame) -> pd.DataFrame:
    started = time.perf_counter()
    rows = []
    for row in images.itertuples(index=False):
        path = ctx.input_dir / str(row.path)
        rgb = load_rgb(path)
        brightness = brightness_stats(rgb)
        rows.append({
            "image_id": str(row.image_id),
            "path": str(row.path),
            "camera_id": str(row.camera_id),
            "light": str(row.light),
            "split": str(row.split),
            "laplacian_variance": laplacian_variance(rgb),
            "mean_brightness": brightness["mean"],
            "dark_fraction": brightness["frac_dark"],
            "saturated_fraction": brightness["frac_saturated"],
            "local_glare": _local_glare(rgb),
            "jpeg_blockiness": _blockiness(to_gray(rgb)),
        })
    ctx.stats["feature_runtime_seconds"] = round(time.perf_counter() - started, 4)
    return pd.DataFrame(rows)


def _reference_rows(features: pd.DataFrame, row: pd.Series, column: str, dev_split: str) -> pd.Series:
    """Find a dev-only reference bucket, backing off when a slice is too small."""
    dev = features[features["split"] == dev_split]
    for keys in (("camera_id", "light"), ("camera_id",), ("light",), ()):
        subset = dev
        for key in keys:
            subset = subset[subset[key] == row[key]]
        values = subset[column]
        if len(values) >= 5:
            return values
    return dev[column]


def _robust_z(value: float, reference: Iterable[float], reverse: bool = False) -> float:
    values = np.asarray(list(reference), dtype=float)
    values = values[np.isfinite(values)]
    if not len(values):
        return 0.0
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    scale = 1.4826 * mad
    if scale < 1e-6:
        scale = float(np.std(values))
    if scale < 1e-6:
        scale = max(abs(median) * 0.05, 1.0)
    z = (median - value if reverse else value - median) / scale
    return float(np.clip(z, 0.0, 8.0))


def _score_features(ctx: RunContext, features: pd.DataFrame) -> pd.DataFrame:
    dev_split = str(ctx.param("dev_split", "dev"))
    dev = features[features["split"] == dev_split]
    if dev.empty:
        raise ValueError(f"no rows in dev split {dev_split!r}; cannot calibrate T02 scores")
    if (features["split"] == "eval").sum() == 0:
        raise ValueError("T02 input has no eval rows")

    feature_columns = {
        "blur_score": ("laplacian_variance", True),
        "dark_score": ("mean_brightness", True),
        "glare_score": ("local_glare", False),
        "compression_score": ("jpeg_blockiness", False),
    }
    weights = ctx.param("feature_weights", {}) or {}
    scored = features.copy()
    for score_col, (feature_col, reverse) in feature_columns.items():
        scores = []
        for _, row in features.iterrows():
            reference = _reference_rows(features, row, feature_col, dev_split)
            scores.append(_robust_z(float(row[feature_col]), reference, reverse=reverse))
        scored[score_col] = scores

    default_weights = {"blur_score": 1.0, "dark_score": 0.8, "glare_score": 0.9, "compression_score": 0.6}
    for column, weight in weights.items():
        if column in default_weights:
            default_weights[column] = float(weight)
    scored["score"] = sum(scored[column] * weight for column, weight in default_weights.items())
    component_names = {
        "blur_score": "blur", "dark_score": "dark", "glare_score": "glare",
        "compression_score": "compression",
    }
    threshold = float(ctx.param("recapture_score_threshold", 2.0))
    strongest = scored[list(component_names)].idxmax(axis=1).map(component_names)
    scored["pred_defect_type"] = np.where(scored["score"] >= threshold, strongest, "none")
    scored["pred_action"] = np.where(scored["score"] >= threshold, "RECAPTURE", "KEEP")
    scored["reason"] = scored.apply(
        lambda r: f"{r['pred_defect_type']} anomaly (score={r['score']:.2f})", axis=1
    )
    return scored


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    images_path = ctx.input_dir / "images.csv"
    if not images_path.exists():
        raise FileNotFoundError(f"T02 images metadata not found: {images_path}")
    images = pd.read_csv(images_path)
    required = {"image_id", "path", "camera_id", "light", "split"}
    missing = sorted(required - set(images.columns))
    if missing:
        raise ValueError(f"T02 images.csv missing required columns: {missing}")
    if images["image_id"].duplicated().any():
        raise ValueError("T02 images.csv contains duplicate image_id values")
    if not images["split"].isin({"dev", "eval"}).all():
        raise ValueError("T02 split values must be dev or eval")
    return {"manifest": pd.read_csv(manifest), "images": images}


# ---------------------------------------------------------------- 02 process
def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    if ctx.track != "t02":
        raise ValueError(f"src.pipeline implements T02 only; configured track is {ctx.track}")
    features = _extract_features(ctx, data["images"])
    scored = _score_features(ctx, features)
    return scored[[
        "image_id", "score", "pred_defect_type", "pred_action", "reason", "camera_id", "light", "path",
        "blur_score", "dark_score", "glare_score", "compression_score",
    ]]


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    budget = int(ctx.param("budget", 20))
    q = make_review_queue(
        scored, id_col="image_id", score_col="score", budget=budget,
        reason_col="reason", action_col="pred_action", slice_col="light", evidence_col="path",
    )
    write_review_queue(q, ctx.out("review_queue.csv"))
    ctx.stats["review_budget"] = budget
    ctx.stats["review_queue_size"] = len(q)
    ctx.stats["review_queue_ids"] = q["item_id"].astype(str).tolist()
    render_contact_sheet(
        q, ctx.out("contact_sheet.html"), image_root=ctx.input_dir,
        title=f"T02 Raw QC review queue — {ctx.run_name}",
    )
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    if not reviewed_path.exists():
        ctx.stats["n_reviewed"] = 0
        return scored

    reviewed = load_review_decisions(reviewed_path)
    queue_ids = set(queue["item_id"].astype(str))
    foreign_ids = set(reviewed["item_id"].astype(str)) - queue_ids
    if foreign_ids:
        raise ValueError(f"review file contains item_id values outside the current queue: {sorted(foreign_ids)[:5]}")
    if reviewed["item_id"].astype(str).duplicated().any():
        raise ValueError("review file contains duplicate item_id decisions")

    reviewed = reviewed.copy()
    allowed_actions = {"KEEP", "RECAPTURE", "HOLD"}
    for index, row in reviewed.iterrows():
        decision = row["reviewer_decision"]
        override = str(row["override_value"]).strip().upper()
        if decision == "reject" and not override:
            reviewed.loc[index, "override_value"] = "KEEP"
        elif decision == "escalate" and not override:
            reviewed.loc[index, "override_value"] = "HOLD"
        elif decision == "edit" and not override:
            raise ValueError(f"review edit for {row['item_id']} requires override_value KEEP/RECAPTURE/HOLD")
        elif override and override not in allowed_actions:
            raise ValueError(f"invalid T02 override {override!r} for {row['item_id']}; expected {sorted(allowed_actions)}")
        if ctx.audit:
            ctx.audit.log(
                actor=row["reviewer"], action=f"review:{decision}", item_id=row["item_id"],
                before=None, after=reviewed.loc[index, "override_value"] or "unchanged",
                reason=row["review_note"],
            )

    override_rows = reviewed.copy()
    override_rows.loc[override_rows["reviewer_decision"] == "escalate", "reviewer_decision"] = "edit"
    final = apply_overrides(scored, override_rows, "image_id", "pred_action", audit=ctx.audit)
    ctx.stats["n_reviewed"] = int((reviewed["reviewer_decision"] != "skip").sum())
    return final


# ---------------------------------------------------------------- 05 decide
def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    owner = str(ctx.config.get("owner", "")).strip()
    if not owner or owner.startswith("TODO"):
        owner = "T02 QA Lead"  # Replace with the named reviewer before formal submission.
    queue_size = int(ctx.stats.get("review_queue_size", 0))
    n_reviewed = int(ctx.stats.get("n_reviewed", 0))
    evidence = [str(ctx.out("ranked_review.csv")), str(ctx.out("review_queue.csv")), str(ctx.out("contact_sheet.html"))]
    audit_path = ctx.output_dir / "audit_log.jsonl"
    if audit_path.exists():
        evidence.append(str(audit_path))
    if n_reviewed < queue_size:
        return Decision(
            status="HOLD", reason_code="REVIEW_PENDING",
            reason=f"Human review is incomplete ({n_reviewed}/{queue_size} queue items reviewed).",
            owner=owner, scope=ctx.track, evidence=evidence,
            metrics={"reviewed": n_reviewed, "queue_size": queue_size},
        )
    queue_ids = set(ctx.stats.get("review_queue_ids", []))
    queue_final = final[final["image_id"].astype(str).isin(queue_ids)]
    if (queue_final["pred_action"] == "HOLD").any():
        return Decision(
            status="HOLD", reason_code="REVIEW_ESCALATED",
            reason="At least one reviewed item was escalated for further inspection.",
            owner=owner, scope=ctx.track, evidence=evidence,
            metrics={"reviewed": n_reviewed, "queue_size": queue_size},
        )
    if (queue_final["pred_action"] == "RECAPTURE").any():
        count = int((queue_final["pred_action"] == "RECAPTURE").sum())
        return Decision(
            status="REWORK", reason_code="RECAPTURE_REQUIRED",
            reason=f"{count} item(s) remain marked for recapture after human review.",
            owner=owner, scope=ctx.track, evidence=evidence,
            metrics={"recapture_items": count, "reviewed": n_reviewed, "queue_size": queue_size},
        )
    return Decision(
        status="GO", reason_code="REVIEW_QUEUE_CLEARED",
        reason="The review queue is complete and no items remain escalated or marked for recapture.",
        owner=owner, scope=ctx.track, evidence=evidence,
        metrics={"reviewed": n_reviewed, "queue_size": queue_size},
    )


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)
    columns = spec.pred_columns + [c for c in final.columns if c not in spec.pred_columns]
    final[columns].to_csv(ctx.out(spec.pred_file), index=False)
    write_decision(decide(ctx, final), ctx.out("decision.json"), ctx.out("decision_log.csv"))
