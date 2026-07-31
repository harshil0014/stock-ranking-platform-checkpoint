"""Installed ``stock-research`` command line interface."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
from typing import Any, Sequence

import pandas as pd

from stock_research.adapters import (
    convert_qlib_predictions, research_v2_to_signals
)
from stock_research.comparison import compare_evaluations
from stock_research.contracts import (
    validate_feature_panel, validate_labels, validate_signals, validate_split
)
from stock_research.environment import inspect_environment
from stock_research.evaluation import EvaluationProtocol, evaluate_signals
from stock_research.manifests import (
    create_manifest, load_manifest, transition_manifest, validate_manifest,
    write_manifest,
)
from stock_research.fingerprints import fingerprint_file
from stock_research.registry import validate_registry
from stock_research.qlib_reproduction import (
    QlibLinearReproductionConfig,
    plan_qlib_linear_reproduction,
    run_qlib_linear_reproduction,
)
from stock_research.qlib_lightgbm_reproduction import (
    QlibLightGBMReproductionConfig,
    plan_qlib_lightgbm_reproduction,
    run_qlib_lightgbm_reproduction,
)
from stock_research.qlib_doubleensemble_reproduction import (
    QlibDoubleEnsembleReproductionConfig,
    plan_qlib_doubleensemble_reproduction,
    run_qlib_doubleensemble_reproduction,
)


DEFAULT_REGISTRY = Path("research/registry/open_source_registry.json")


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(value: Any, path: Path | None) -> None:
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if path is None:
        print(payload, end="")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        print(path)


def _protocol(raw: dict[str, Any]) -> EvaluationProtocol:
    return EvaluationProtocol(
        label_name=raw["label_name"],
        label_definition=raw["label_definition"],
        label_dataset_fingerprint=raw["label_dataset_fingerprint"],
        train_start=raw["train"]["start"],
        train_end=raw["train"]["end"],
        validation_start=raw["validation"]["start"],
        validation_end=raw["validation"]["end"],
        test_start=raw["test"]["start"],
        test_end=raw["test"]["end"],
        purge_days=raw["purge_days"],
        embargo_days=raw["embargo_days"],
        evaluation_frequency=raw["evaluation_frequency"],
        metric_definitions=raw["metric_definitions"],
        annualization_factor=raw.get("annualization_factor"),
        minimum_cross_sectional_observations=raw[
            "minimum_cross_sectional_observations"
        ],
        test_universe_policy=raw["test_universe_policy"],
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stock-research",
        description="Offline, Qlib-independent quant research controls.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    registry = commands.add_parser("registry-validate")
    registry.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)

    environment = commands.add_parser("environment-inspect")
    environment.add_argument("--output", type=Path)

    contract = commands.add_parser("contract-validate")
    contract.add_argument(
        "--kind", required=True, choices=("features", "labels", "signals", "split")
    )
    contract.add_argument("--input", required=True, type=Path)
    contract.add_argument("--output", type=Path)
    contract.add_argument("--registry", type=Path)

    rv2 = commands.add_parser("signal-export-research-v2")
    rv2.add_argument("--input", required=True, type=Path)
    rv2.add_argument("--output", required=True, type=Path)
    rv2.add_argument("--run-id")

    qlib = commands.add_parser("signal-convert-qlib")
    qlib.add_argument("--input", required=True, type=Path)
    qlib.add_argument("--mapping", required=True, type=Path)
    qlib.add_argument("--output", required=True, type=Path)
    qlib.add_argument("--drop-report", type=Path)
    qlib.add_argument("--model-id", required=True)
    qlib.add_argument("--run-id", required=True)
    qlib.add_argument("--upstream-model-id")
    qlib.add_argument("--upstream-run-id")
    qlib.add_argument("--allow-unsafe-pickle", action="store_true")
    qlib.add_argument("--drop-unmapped", action="store_true")

    create = commands.add_parser("manifest-create")
    create.add_argument("--spec", required=True, type=Path)
    create.add_argument("--output", required=True, type=Path)

    show = commands.add_parser("manifest-show")
    show.add_argument("--manifest", required=True, type=Path)

    validate = commands.add_parser("manifest-validate")
    validate.add_argument("--manifest", required=True, type=Path)
    validate.add_argument("--directory", type=Path)

    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--signals", required=True, type=Path)
    evaluate.add_argument("--labels", required=True, type=Path)
    evaluate.add_argument("--protocol", required=True, type=Path)
    evaluate.add_argument("--model-configuration-fingerprint", required=True)
    evaluate.add_argument("--dataset-fingerprints", type=Path)
    evaluate.add_argument("--provenance", type=Path)
    evaluate.add_argument("--manifest", type=Path)
    evaluate.add_argument("--output-dir", required=True, type=Path)

    compare = commands.add_parser("compare")
    compare.add_argument("--evaluations", required=True, nargs="+", type=Path)
    compare.add_argument("--output", required=True, type=Path)

    reproduce = commands.add_parser("reproduce-qlib-linear")
    reproduce.add_argument("--seed", type=int, default=20260730)
    reproduce.add_argument(
        "--output-root", type=Path,
        default=Path("research/generated/qlib-linear"),
    )
    reproduce.add_argument(
        "--qlib-interpreter", type=Path,
        default=Path(".venv-qlib/Scripts/python.exe"),
    )
    reproduce.add_argument(
        "--environment-report", type=Path,
        default=Path("research/generated/qlib-environment-verified.json"),
    )
    reproduce.add_argument("--batch-id")
    reproduce.add_argument("--dry-run", action="store_true")
    reproduce.add_argument(
        "--discard-failed-artifacts", action="store_true"
    )

    lightgbm = commands.add_parser("reproduce-qlib-lightgbm")
    lightgbm.add_argument("--seed", type=int, default=20260730)
    lightgbm.add_argument("--reruns", type=int, default=2)
    lightgbm.add_argument(
        "--reproducibility-tolerance", type=float, default=1e-12
    )
    lightgbm.add_argument(
        "--output-root", type=Path,
        default=Path("research/generated/qlib-lightgbm"),
    )
    lightgbm.add_argument(
        "--frozen-linear-batch", type=Path,
        default=Path(
            "research/generated/qlib-linear/final-locked-20260731"
        ),
    )
    lightgbm.add_argument(
        "--qlib-interpreter", type=Path,
        default=Path(".venv-qlib/Scripts/python.exe"),
    )
    lightgbm.add_argument(
        "--environment-report", type=Path,
        default=Path("research/generated/qlib-environment-verified.json"),
    )
    lightgbm.add_argument(
        "--frozen-specification", type=Path,
        default=Path(
            "research/specifications/qlib_lightgbm_frozen_protocol.json"
        ),
    )
    lightgbm.add_argument("--batch-id")
    lightgbm.add_argument("--dry-run", action="store_true")
    lightgbm.add_argument(
        "--discard-failed-artifacts", action="store_true"
    )
    lightgbm.add_argument(
        "--resume-completed-run-one", action="store_true",
        help=(
            "resume product post-processing after a verified successful "
            "run-01 subprocess without retraining it"
        ),
    )

    doubleensemble = commands.add_parser(
        "reproduce-qlib-doubleensemble"
    )
    doubleensemble.add_argument("--seed", type=int, default=20260730)
    doubleensemble.add_argument("--reruns", type=int, default=2)
    doubleensemble.add_argument(
        "--reproducibility-tolerance", type=float, default=1e-12
    )
    doubleensemble.add_argument(
        "--output-root", type=Path,
        default=Path("research/generated/qlib-doubleensemble"),
    )
    doubleensemble.add_argument(
        "--frozen-linear-batch", type=Path,
        default=Path(
            "research/generated/qlib-linear/final-locked-20260731"
        ),
    )
    doubleensemble.add_argument(
        "--accepted-lightgbm-batch", type=Path,
        default=Path(
            "research/generated/qlib-lightgbm/"
            "official-local-recorder-opt-in-20260731"
        ),
    )
    doubleensemble.add_argument(
        "--qlib-interpreter", type=Path,
        default=Path(".venv-qlib/Scripts/python.exe"),
    )
    doubleensemble.add_argument(
        "--environment-report", type=Path,
        default=Path("research/generated/qlib-environment-verified.json"),
    )
    doubleensemble.add_argument(
        "--frozen-specification", type=Path,
        default=Path(
            "research/specifications/"
            "qlib_doubleensemble_frozen_protocol.json"
        ),
    )
    doubleensemble.add_argument("--batch-id")
    doubleensemble.add_argument("--dry-run", action="store_true")
    doubleensemble.add_argument(
        "--discard-failed-artifacts", action="store_true"
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.command == "registry-validate":
        registry = validate_registry(args.registry)
        print(f"Valid registry: {len(registry.entries)} entries ({args.registry})")
    elif args.command == "environment-inspect":
        _write_json(inspect_environment(), args.output)
    elif args.command == "contract-validate":
        if args.kind == "split":
            validated = validate_split(_json(args.input)).as_dict()
            _write_json(validated, args.output)
            return 0
        frame = pd.read_csv(args.input, dtype=str)
        if args.kind == "features":
            validated_frame = validate_feature_panel(frame)
        elif args.kind == "labels":
            validated_frame = validate_labels(frame)
        else:
            models = (
                validate_registry(args.registry).model_ids
                if args.registry else None
            )
            validated_frame = validate_signals(frame, models)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            validated_frame.to_csv(args.output, index=False)
        print(f"Valid {args.kind}: {len(validated_frame)} rows")
    elif args.command == "signal-export-research-v2":
        signals = research_v2_to_signals(pd.read_csv(args.input), run_id=args.run_id)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        signals.to_csv(args.output, index=False)
        print(f"Signals: {args.output} ({len(signals)} rows)")
    elif args.command == "signal-convert-qlib":
        signals, dropped = convert_qlib_predictions(
            args.input, args.mapping, model_id=args.model_id, run_id=args.run_id,
            upstream_model_id=args.upstream_model_id,
            upstream_run_id=args.upstream_run_id,
            allow_unsafe_pickle=args.allow_unsafe_pickle,
            drop_unmapped=args.drop_unmapped,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        signals.to_csv(args.output, index=False)
        if args.drop_report:
            args.drop_report.parent.mkdir(parents=True, exist_ok=True)
            dropped.to_csv(args.drop_report, index=False)
        print(f"Signals: {args.output} ({len(signals)} rows, {len(dropped)} dropped)")
    elif args.command == "manifest-create":
        spec = _json(args.spec)
        manifest = create_manifest(**spec)
        write_manifest(manifest, args.output)
        print(f"Manifest: {args.output}")
    elif args.command == "manifest-show":
        _write_json(load_manifest(args.manifest), None)
    elif args.command == "manifest-validate":
        manifest = _json(args.manifest)
        validate_manifest(manifest, manifest_directory=args.directory)
        print(f"Valid manifest: {args.manifest}")
    elif args.command == "evaluate":
        source_manifest = load_manifest(args.manifest) if args.manifest else None
        running_manifest = (
            transition_manifest(source_manifest, "running")
            if source_manifest else None
        )
        protocol = _protocol(_json(args.protocol))
        try:
            if source_manifest and (
                source_manifest["evaluation_protocol_fingerprint"]
                != protocol.fingerprint
            ):
                raise ValueError(
                    "manifest evaluation_protocol_fingerprint does not match protocol"
                )
            if source_manifest and (
                source_manifest["model_configuration_fingerprint"]
                != args.model_configuration_fingerprint
            ):
                raise ValueError(
                    "manifest model_configuration_fingerprint does not match"
                )
            result = evaluate_signals(
                pd.read_csv(args.signals, dtype={"as_of_date": str}),
                pd.read_csv(args.labels, dtype={
                    "as_of_date": str, "label_end_date": str
                }),
                protocol,
                model_configuration_fingerprint=args.model_configuration_fingerprint,
                dataset_fingerprints=(
                    _json(args.dataset_fingerprints)
                    if args.dataset_fingerprints else {}
                ),
                provenance=_json(args.provenance) if args.provenance else {},
                output_dir=args.output_dir,
            )
            if source_manifest and (
                result.summary["model_id"] != source_manifest["model_id"]
                or result.summary["run_id"] != source_manifest["run_id"]
            ):
                raise ValueError("signal model_id/run_id does not match manifest")
        except Exception as exc:
            if running_manifest:
                failed = transition_manifest(
                    running_manifest, "failed",
                    failure_reason=f"{type(exc).__name__}: {exc}",
                )
                write_manifest(
                    failed, args.output_dir / "experiment_manifest.json"
                )
            raise
        if running_manifest:
            artifact_paths = [
                args.output_dir / "evaluation_summary.json",
                args.output_dir / "daily_ic.csv",
                args.output_dir / "daily_rank_ic.csv",
                args.output_dir / "coverage_report.csv",
            ]
            completed = transition_manifest(
                running_manifest,
                "completed",
                evaluation_artifacts=[
                    {"path": str(path), "sha256": fingerprint_file(path)}
                    for path in artifact_paths
                ],
            )
            write_manifest(
                completed, args.output_dir / "experiment_manifest.json"
            )
        print(
            f"Evaluation: {args.output_dir} "
            f"({result.summary['valid_ic_dates']} valid IC dates)"
        )
    elif args.command == "compare":
        result = compare_evaluations(args.evaluations, output_path=args.output)
        print(f"Comparison: {args.output} ({len(result)} models)")
    elif args.command == "reproduce-qlib-linear":
        config = QlibLinearReproductionConfig(
            seed=args.seed,
            output_root=args.output_root,
            qlib_interpreter=args.qlib_interpreter,
            environment_report=args.environment_report,
            keep_failed_artifacts=not args.discard_failed_artifacts,
            batch_id=args.batch_id,
        )
        if args.dry_run:
            plan = plan_qlib_linear_reproduction(config)
            print(json.dumps({
                **asdict(plan),
                "output_directory": str(plan.output_directory),
                "commands": [list(command) for command in plan.commands],
                "dry_run": True,
                "artifacts_written": False,
                "training_performed": False,
            }, indent=2, sort_keys=True, allow_nan=False, default=str))
        else:
            result = run_qlib_linear_reproduction(config)
            print(
                f"Qlib Linear reproduction: {result.directory} "
                f"({len(result.runs)} runs, reproducible)"
            )
    elif args.command == "reproduce-qlib-lightgbm":
        config = QlibLightGBMReproductionConfig(
            seed=args.seed,
            reruns=args.reruns,
            reproducibility_tolerance=args.reproducibility_tolerance,
            output_root=args.output_root,
            frozen_linear_batch=args.frozen_linear_batch,
            qlib_interpreter=args.qlib_interpreter,
            environment_report=args.environment_report,
            frozen_specification=args.frozen_specification,
            batch_id=args.batch_id,
            keep_failed_artifacts=not args.discard_failed_artifacts,
            resume_completed_run_one=args.resume_completed_run_one,
        )
        if args.dry_run:
            plan = plan_qlib_lightgbm_reproduction(config)
            print(json.dumps({
                **asdict(plan),
                "output_directory": str(plan.output_directory),
                "selected_source_run": str(plan.selected_source_run),
                "commands": [list(command) for command in plan.commands],
                "dry_run": True,
                "artifacts_written": False,
                "training_performed": False,
            }, indent=2, sort_keys=True, allow_nan=False, default=str))
        else:
            result = run_qlib_lightgbm_reproduction(config)
            print(
                f"Qlib LightGBM reproduction: {result.directory} "
                f"({len(result.runs)} runs, reproducible)"
            )
    elif args.command == "reproduce-qlib-doubleensemble":
        config = QlibDoubleEnsembleReproductionConfig(
            seed=args.seed,
            reruns=args.reruns,
            reproducibility_tolerance=args.reproducibility_tolerance,
            output_root=args.output_root,
            frozen_linear_batch=args.frozen_linear_batch,
            accepted_lightgbm_batch=args.accepted_lightgbm_batch,
            qlib_interpreter=args.qlib_interpreter,
            environment_report=args.environment_report,
            frozen_specification=args.frozen_specification,
            batch_id=args.batch_id,
            keep_failed_artifacts=not args.discard_failed_artifacts,
        )
        if args.dry_run:
            plan = plan_qlib_doubleensemble_reproduction(config)
            print(json.dumps({
                **asdict(plan),
                "output_directory": str(plan.output_directory),
                "selected_source_run": str(plan.selected_source_run),
                "selected_lightgbm_run": str(plan.selected_lightgbm_run),
                "commands": [list(command) for command in plan.commands],
                "dry_run": True,
                "artifacts_written": False,
                "training_performed": False,
            }, indent=2, sort_keys=True, allow_nan=False, default=str))
        else:
            result = run_qlib_doubleensemble_reproduction(config)
            print(
                f"Qlib DoubleEnsemble reproduction: {result.directory} "
                f"({len(result.runs)} runs, reproducible)"
            )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        return _run(parser.parse_args(argv))
    except (
        ValueError, TypeError, RuntimeError, OSError, KeyError, json.JSONDecodeError,
        pd.errors.ParserError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
