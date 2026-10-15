"""Failure isolation, bounded process pool, checksum-based resume and manifests."""
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time

import h5py

from . import __version__
from .adapters import InvalidEpisode, episodes, read_episode
from .alignment import align
from .config import Config
from .quality import quality
from .report import render_report
from .resources import peak_rss_bytes
from .storage import atomic_json, fingerprint, write_episode


def process_job(job):
    started = time.perf_counter()
    result = {key: job[key] for key in ("id", "source", "episode", "signature")}
    config = Config(**job["config"]).validate()
    try:
        with h5py.File(job["source"], "r") as handle:
            episode = read_episode(handle[job["episode"]], config)
            status, findings, metrics = quality(episode.state, episode.actions, episode.state_time, config)
            result.update(status=status, findings=findings, metrics=metrics,
                          state_kind=episode.state_kind, time_sources=episode.time_sources)
            if status == "accepted":
                aligned = align(episode, config)
                result["alignment"] = aligned["metadata"]
                # Ensure sampling has not removed all motion from the exported sequence.
                status, aligned_findings, aligned_metrics = quality(aligned["state"], aligned["actions"], aligned["timestamps"], config)
                result.update(status=status, findings=aligned_findings, aligned_metrics=aligned_metrics)
                if status == "accepted":
                    artifact = Path(job["output"]) / "episodes" / f"{job['id']}-{job['signature'][:16]}.hdf5"
                    artifact.parent.mkdir(exist_ok=True)
                    provenance = {"source": job["source"], "source_sha256": job["source_sha256"], "episode": job["episode"], "signature": job["signature"], "version": __version__, "config": job["config"], "time_sources": episode.time_sources}
                    write_episode(artifact, episode, aligned, config, provenance)
                    result.update(artifact=str(artifact), artifact_sha256=fingerprint(artifact), output_bytes=artifact.stat().st_size,
                                  exported_frames=len(aligned["state"]))
        # Input SHA256 was recorded at discovery; reject modification during a worker read.
        if Path(job["source"]).stat().st_mtime_ns != job["source_mtime_ns"]:
            raise RuntimeError("Source modified during processing; rerun on a stable snapshot")
    except InvalidEpisode as error:
        result.update(status="rejected", findings=[{"rule": "schema_or_timing", "severity": "reject", "message": str(error), "frames": []}])
    except Exception as error:
        result.update(status="failed", findings=[{"rule": "processing_error", "severity": "error", "message": f"{type(error).__name__}: {error}", "frames": []}])
        result.pop("artifact", None)
    result["processing_seconds"] = time.perf_counter()-started
    result["worker_peak_rss_bytes"] = peak_rss_bytes()
    return result


def discover(input_path, output, config):
    root = Path(input_path).resolve()
    if not root.exists():
        raise ValueError(f"Input does not exist: {root}")
    if root.is_dir() and (output == root or root in output.parents):
        raise ValueError("Output must be outside the input tree to prevent ingesting generated data")
    files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.suffix.lower() in (".h5", ".hdf5"))
    if not files:
        raise ValueError("No HDF5 files found")
    jobs = []
    errors = {}
    for file in files:
        identity = hashlib.sha256(str(file).encode()).hexdigest()[:16]
        try:
            before = file.stat()
            digest = fingerprint(file)
            with h5py.File(file, "r") as handle:
                groups = episodes(handle)
            if not groups:
                raise InvalidEpisode("No episode groups")
            if file.stat().st_mtime_ns != before.st_mtime_ns:
                raise ValueError("Source changed during discovery")
            for group in groups:
                key = hashlib.sha256(f"{file}|{group}".encode()).hexdigest()[:20]
                signature = hashlib.sha256(json.dumps([__version__, digest, group, asdict(config)], sort_keys=True).encode()).hexdigest()
                jobs.append({"id": key, "source": str(file), "episode": group, "source_sha256": digest,
                             "source_mtime_ns": before.st_mtime_ns, "signature": signature,
                             "config": asdict(config), "output": str(output)})
        except Exception as error:
            errors[identity] = {"id": identity, "source": str(file), "episode": "unknown", "status": "failed", "signature": "",
                                "findings": [{"rule": "discovery_error", "message": f"{type(error).__name__}: {error}", "severity": "error", "frames": []}]}
    return jobs, errors


def resumable(previous, job):
    if not previous or previous.get("signature") != job["signature"] or previous.get("status") not in ("accepted", "review", "rejected"):
        return False
    if previous["status"] == "accepted":
        artifact = Path(previous.get("artifact", ""))
        return artifact.is_file() and fingerprint(artifact) == previous.get("artifact_sha256")
    return True


def run(input_path, output_path, config, workers=1, resume=False):
    if workers < 1:
        raise ValueError("workers must be >=1")
    config.validate()
    output = Path(output_path).resolve()
    output.mkdir(parents=True, exist_ok=True)
    lock = output / ".trajguard.lock"
    try:
        stream = lock.open("x")
    except FileExistsError:
        raise ValueError("Output is locked by another run (after a crash, remove .trajguard.lock after confirming no run is active)")
    try:
        with stream:
            stream.write("TrajGuard processing lock\n")
        started = time.perf_counter()
        old_path = output / "manifest.json"
        old = json.loads(old_path.read_text(encoding="utf-8")) if resume and old_path.exists() else {}
        jobs, errors = discover(input_path, output, config)
        manifest = {"schema_version": "trajguard-manifest/1", "version": __version__, "config": asdict(config), "jobs": errors,
                    "resumed": 0, "processed": 0, "workers": workers}
        pending = []
        for job in jobs:
            previous = old.get("jobs", {}).get(job["id"])
            if resume and resumable(previous, job):
                manifest["jobs"][job["id"]] = previous
                manifest["resumed"] += 1
            else:
                pending.append(job)
        atomic_json(old_path, manifest)
        def record(result):
            manifest["jobs"][result["id"]] = result
            manifest["processed"] += 1
            atomic_json(old_path, manifest)
        if workers == 1:
            for job in pending:
                record(process_job(job))
        elif pending:
            # At most 2*workers tasks in flight, including process-pool serialization.
            with ProcessPoolExecutor(max_workers=min(workers, len(pending))) as pool:
                iterator = iter(pending)
                futures = {}
                for _ in range(min(workers*2, len(pending))):
                    job = next(iterator)
                    futures[pool.submit(process_job, job)] = job
                while futures:
                    completed, _ = wait(futures, return_when=FIRST_COMPLETED)
                    for future in completed:
                        job = futures.pop(future)
                        try:
                            record(future.result())
                        except Exception as error:
                            record({"id": job["id"], "source": job["source"], "episode": job["episode"], "signature": job["signature"], "status": "failed", "findings": [{"rule": "worker_error", "message": str(error), "severity": "error", "frames": []}]})
                        following = next(iterator, None)
                        if following:
                            futures[pool.submit(process_job, following)] = following
        manifest["wall_seconds"] = time.perf_counter()-started
        manifest["accepted_frames"] = sum(j.get("exported_frames", 0) for j in manifest["jobs"].values() if j["status"] == "accepted")
        atomic_json(old_path, manifest)
        render_report(manifest, output / "report.html")
        atomic_json(output / "review_queue.json", [item for item in manifest["jobs"].values() if item["status"] in ("review", "rejected", "failed")])
        return manifest
    finally:
        lock.unlink(missing_ok=True)
