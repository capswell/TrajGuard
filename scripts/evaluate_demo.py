"""Controlled expected-status regression, not a real-world quality accuracy claim."""
import argparse
import json
from pathlib import Path


def evaluate(truth_path, manifest_path, output):
    truth = json.loads(Path(truth_path).read_text(encoding="utf-8"))
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    predictions = {Path(j["source"]).name: j["status"] for j in manifest["jobs"].values()}
    rows = [{"file": name, "expected": status, "actual": predictions.get(name), "matches": predictions.get(name) == status} for name, status in truth.items()]
    result = {"scope": "controlled synthetic expected-status check; not real-data precision/recall", "cases": rows, "matched": sum(row["matches"] for row in rows), "total": len(rows)}
    Path(output).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return int(result["matched"] != result["total"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--truth", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    raise SystemExit(evaluate(args.truth, args.manifest, args.output))
