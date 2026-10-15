"""Offline candidate-label review. Never overwrite the original instruction."""
import json
from pathlib import Path

from .storage import atomic_json


def template(manifest_path, output):
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    candidates = [{"job_id": key, "signature": job["signature"], "candidate_instruction": "", "review_status": "uncertain", "reviewer": "", "provider": "manual", "model": "", "prompt_version": "", "notes": ""}
                  for key, job in manifest["jobs"].items() if job["status"] == "accepted"]
    atomic_json(output, candidates)
    return len(candidates)


def validate_labels(manifest_path, labels_path, output):
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    labels = json.loads(Path(labels_path).read_text(encoding="utf-8"))
    if not isinstance(labels, list):
        raise ValueError("Labels must be a JSON list")
    seen = set()
    for row in labels:
        expected = {"job_id", "signature", "candidate_instruction", "review_status", "reviewer", "provider", "model", "prompt_version", "notes"}
        if not isinstance(row, dict) or set(row) != expected or not all(isinstance(v, str) for v in row.values()):
            raise ValueError("Invalid label schema; use label-template")
        job = manifest["jobs"].get(row["job_id"])
        if row["job_id"] in seen or not job or job["status"] != "accepted" or row["signature"] != job["signature"]:
            raise ValueError("Duplicate, unknown, stale or non-accepted job reference")
        seen.add(row["job_id"])
        if row["review_status"] not in ("candidate", "reviewed", "uncertain"):
            raise ValueError("Unknown review status")
        if row["provider"] not in ("manual", "vlm"):
            raise ValueError("provider must be manual or vlm")
        if row["review_status"] in ("candidate", "reviewed") and not row["candidate_instruction"].strip():
            raise ValueError("Candidate/reviewed instruction must not be empty")
        if row["review_status"] == "reviewed" and not row["reviewer"].strip():
            raise ValueError("Reviewed labels require reviewer identity")
        if row["provider"] == "vlm" and (not row["model"].strip() or not row["prompt_version"].strip()):
            raise ValueError("VLM labels require model and prompt_version provenance")
    result = {"schema_version": "trajguard-labels/1", "labels": labels, "semantic_accuracy_verified": False,
              "note": "Schema/provenance validation only; original instructions are never overwritten. Reviewed status is a user declaration."}
    atomic_json(output, result)
    return len(labels)
