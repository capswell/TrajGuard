"""Atomic outputs, source fingerprints, chunked image copying with no decoding."""
import hashlib
import json
import os
from pathlib import Path
import uuid

import h5py
import numpy as np


def fingerprint(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path, content):
    path = Path(path)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(content, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def copy_images(source, parent, name, indices, chunk_frames):
    shape = (len(indices), *source.shape[1:])
    # Variable-length payload arrays need h5py's original dtype and per-frame copies.
    variable = h5py.check_dtype(vlen=source.dtype) is not None
    if variable:
        target = parent.create_dataset(name, shape=shape, dtype=source.dtype)
        for dst, src in enumerate(indices):
            target[dst] = source[int(src)]
    else:
        chunks = (min(chunk_frames, len(indices)), *source.shape[1:])
        target = parent.create_dataset(name, shape=shape, dtype=source.dtype, chunks=chunks, compression="lzf")
        for start in range(0, len(indices), chunk_frames):
            rows = indices[start:start+chunk_frames]
            # Preserve repeated selections from lower-rate cameras without h5py fancy-index restrictions.
            target[start:start+len(rows)] = np.stack([source[int(i)] for i in rows])
    for key, value in source.attrs.items():
        target.attrs[key] = value
    target.attrs["storage_kind"] = "raw_pixels" if source.ndim == 4 else "encoded_payload_unvalidated"
    return target


def write_episode(path, episode, aligned, config, provenance):
    path = Path(path)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with h5py.File(temporary, "w") as target:
            target.attrs["schema_version"] = "trajguard/1"
            target.attrs["provenance"] = json.dumps(provenance, ensure_ascii=False)
            target.attrs["alignment"] = json.dumps(aligned["metadata"])
            target.attrs["state_kind"] = episode.state_kind
            target.attrs["state_unit"] = config.state_unit
            target.create_dataset("state", data=aligned["state"])
            target.create_dataset("actions", data=aligned["actions"])
            target.create_dataset("instruction", data=episode.instruction, dtype=h5py.string_dtype())
            if aligned["timestamps"] is not None:
                target.create_dataset("timestamps", data=aligned["timestamps"])
            mapping = target.create_group("source_indices")
            mapping.create_dataset("state_previous", data=aligned["state_previous_indices"])
            mapping.create_dataset("action_previous", data=aligned["action_previous_indices"])
            # Retain original time arrays so interpolation brackets can be reconstructed.
            if episode.state_time is not None:
                target.create_dataset("source_times/state", data=episode.state_time)
                target.create_dataset("source_times/action", data=episode.action_time)
            images = target.create_group("images")
            for name, source in episode.cameras.items():
                indices = aligned["camera_indices"][name]
                copied = copy_images(source, images, name, indices, config.chunk_frames)
                copied.attrs["decoded_color_order"] = config.decoded_color_order
                mapping.create_dataset(f"images/{name}", data=indices)
                if episode.camera_times[name] is not None:
                    target.create_dataset(f"source_times/images/{name}", data=episode.camera_times[name])
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
