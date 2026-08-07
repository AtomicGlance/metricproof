"""Command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .contract import audit_contract
from .report import render_json, render_markdown, render_text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="metricproof",
        description="Audit the assumptions behind business metrics.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show the installed MetricProof version and exit.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit = subparsers.add_parser("audit", help="Run a JSON analytical contract.")
    audit.add_argument("contract", help="Path to a contract JSON file.")
    audit.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
        help="Report format (default: text).",
    )
    audit.add_argument("--output", help="Optional report output path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = audit_contract(args.contract)
    except (OSError, ValueError) as exc:
        print(f"MetricProof configuration error: {exc}", file=sys.stderr)
        return 2

    renderers = {
        "text": render_text,
        "json": render_json,
        "markdown": render_markdown,
    }
    output = renderers[args.format](report)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
        print(f"Wrote {args.format} report to {output_path}")
    else:
        print(output, end="" if output.endswith("\n") else "\n")
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
