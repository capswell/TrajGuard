import argparse
from collections import Counter
import json
import sys

from .config import Config
from .pipeline import run
from .labels import template, validate_labels


def main(argv=None):
    parser = argparse.ArgumentParser(description="TrajGuard: traceable trajectory quality gates")
    parser.add_argument("--version", action="version", version="TrajGuard 0.1.0")
    sub = parser.add_subparsers(dest="command", required=True)
    process = sub.add_parser("run", help="Validate, align, export and report")
    process.add_argument("--input", required=True)
    process.add_argument("--output", required=True)
    process.add_argument("--config", help="JSON configuration; unknown options are errors")
    process.add_argument("--workers", type=int, default=1)
    process.add_argument("--resume", action="store_true")
    label_template = sub.add_parser("label-template", help="Export offline review candidates for accepted jobs")
    label_template.add_argument("--manifest", required=True)
    label_template.add_argument("--output", required=True)
    labels = sub.add_parser("labels", help="Validate offline label schema and provenance")
    labels.add_argument("--manifest", required=True)
    labels.add_argument("--input", required=True)
    labels.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "label-template":
            print(json.dumps({"candidates": template(args.manifest, args.output)}))
            return 0
        if args.command == "labels":
            print(json.dumps({"validated": validate_labels(args.manifest, args.input, args.output)}))
            return 0
        manifest = run(args.input, args.output, Config.load(args.config), args.workers, args.resume)
        counts = Counter(job["status"] for job in manifest["jobs"].values())
        print(json.dumps({"counts": dict(counts), "processed": manifest["processed"], "resumed": manifest["resumed"], "wall_seconds": manifest["wall_seconds"]}, ensure_ascii=False))
        return 1 if counts["failed"] else 0
    except (ValueError, TypeError, OSError) as error:
        print(f"TrajGuard: {error}", file=sys.stderr)
        return 2
