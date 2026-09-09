from __future__ import annotations

import argparse
import logging
import os
import sys

from prediction.retrain.orchestrator import train_if_needed
from prediction.training.pipeline import run_training_pipeline

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def _run_train() -> int:
    try:
        result = run_training_pipeline(trigger_source="cli_train")
    except Exception:
        logger.exception("train command failed", extra={"event": "training_failed"})
        return 1

    logger.info(
        "train command finished",
        extra={
            "event": "train_command_finished",
            "run_id": result.run_id,
            "model_version": result.model_version,
            "mae": result.mae,
            "baseline_mae": result.baseline_mae,
            "promoted": result.promoted,
        },
    )
    return 0


def _run_train_if_needed() -> int:
    try:
        decision, result = train_if_needed()
    except Exception:
        logger.exception("train-if-needed command failed", extra={"event": "training_failed"})
        return 1

    logger.info(
        "train-if-needed command finished",
        extra={
            "event": "train_if_needed_command_finished",
            "should_retrain": decision.should_retrain,
            "retrain_reason": ",".join(decision.reasons) if decision.reasons else "none",
            "promoted": result.promoted if result is not None else None,
        },
    )
    return 0


def _run_serve() -> int:
    import uvicorn

    uvicorn.run(
        "prediction.api.app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m prediction.main")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("train")
    subparsers.add_parser("train-if-needed")
    subparsers.add_parser("serve")

    args = parser.parse_args(argv)

    if args.command == "train":
        return _run_train()
    if args.command == "train-if-needed":
        return _run_train_if_needed()
    return _run_serve()


if __name__ == "__main__":
    sys.exit(main())
