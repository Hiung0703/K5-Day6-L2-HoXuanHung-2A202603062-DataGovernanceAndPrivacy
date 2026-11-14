"""Single global Laplacian-variance baseline required by T02."""
from __future__ import annotations

import pandas as pd

from ..common.contact_sheet import render_contact_sheet
from ..common.context import RunContext
from ..common.decision import Decision, write_decision
from ..common.image_ops import laplacian_variance, load_rgb
from ..common.manifest import verify_manifest
from ..common.review import make_review_queue, write_review_queue
from ..metrics.tracks import get_track


def run(ctx: RunContext) -> None:
    if ctx.track != "t02":
        raise ValueError("Laplacian baseline is defined for T02 only")
    spec = get_track(ctx.track)
    manifest_path = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest_path) if manifest_path.exists() else [{"problem": "no_manifest"}]
    if problems:
        raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    images_path = ctx.input_dir / "images.csv"
    if not images_path.exists():
        raise FileNotFoundError(f"T02 images metadata not found: {images_path}")
    images = pd.read_csv(images_path)
    required = {"image_id", "path", "light", "split"}
    missing = sorted(required - set(images.columns))
    if missing:
        raise ValueError(f"T02 images.csv missing required columns: {missing}")

    # Lower Laplacian variance means less sharp and therefore more suspicious.
    images["score"] = [
        -laplacian_variance(load_rgb(ctx.input_dir / str(path))) for path in images["path"]
    ]
    images["reason"] = "global Laplacian variance (lower sharpness = higher suspicion)"
    budget = int(ctx.param("budget", 20))
    queue = make_review_queue(
        images, "image_id", "score", budget, reason_col="reason", slice_col="light", evidence_col="path"
    )
    write_review_queue(queue, ctx.out("review_queue.csv"))
    render_contact_sheet(
        queue, ctx.out("contact_sheet.html"), image_root=ctx.input_dir,
        title=f"T02 Laplacian baseline review queue — {ctx.run_name}",
    )
    images[["image_id", "score"]].to_csv(ctx.out(spec.pred_file), index=False)
    owner = str(ctx.config.get("owner", "")).strip()
    if not owner or owner.startswith("TODO"):
        owner = "T02 QA Lead"  # Replace with the named reviewer before formal submission.
    write_decision(
        Decision(
            status="HOLD", reason_code="BASELINE_REQUIRES_REVIEW",
            reason="Baseline rankings are advisory; a reviewer must inspect the flagged images.",
            owner=owner, scope=ctx.track,
            evidence=[str(ctx.out(spec.pred_file)), str(ctx.out("review_queue.csv"))],
            metrics={"n_items": len(images), "review_budget": budget},
        ),
        ctx.out("decision.json"), ctx.out("decision_log.csv"),
    )
