"""Build the pose search index from images under data/raw/**.

For every image: detect a pose, normalize it to a unit vector, and store it
in ``data/index/embeddings.npz``. A ``manifest.json`` maps each id to its
source file and license metadata, and a 320px-max thumbnail is written to
``data/index/thumbs/`` for the web UI. Images with no detectable pose (or
fewer than 50% visible joints) are skipped and logged.

Example:
    python -m posemirror.build_index
    python -m posemirror.build_index --raw data/raw --index data/index
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from .pose import (
    INDEX_FORMAT_VERSION,
    ensure_model,
    extract_pose,
    normalize_pose,
    project_root,
)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def make_thumbnail(bgr: np.ndarray, dest: Path, max_side: int = 320) -> None:
    h, w = bgr.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    if scale < 1.0:
        bgr = cv2.resize(bgr, (int(w * scale), int(h * scale)),
                         interpolation=cv2.INTER_AREA)
    cv2.imwrite(str(dest), bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])


def load_sidecar(image_path: Path) -> dict:
    sidecar = image_path.with_suffix(".json")
    if sidecar.exists():
        try:
            return json.loads(sidecar.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def build_index(raw_dir: Path, index_dir: Path) -> dict:
    ensure_model()
    thumbs_dir = index_dir / "thumbs"
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    images = sorted(
        p for p in raw_dir.rglob("*")
        if p.suffix.lower() in IMAGE_EXTS and p.is_file()
    )
    print(f"[index] found {len(images)} images under {raw_dir}")

    ids, vectors, manifest = [], [], {}
    skipped: list[str] = []
    for i, path in enumerate(images):
        bgr = cv2.imread(str(path))
        if bgr is None:
            skipped.append(f"{path}: unreadable")
            continue
        try:
            landmarks = extract_pose(bgr)
        except Exception as exc:  # noqa: BLE001 - keep indexing on failures
            skipped.append(f"{path}: pose error {exc}")
            continue
        if landmarks is None:
            skipped.append(f"{path}: no person detected")
            continue
        vec = normalize_pose(landmarks)
        if vec is None:
            skipped.append(f"{path}: <50% joints visible or degenerate")
            continue

        entry_id = f"{len(ids):06d}"
        ids.append(entry_id)
        vectors.append(vec)
        make_thumbnail(bgr, thumbs_dir / f"{entry_id}.jpg")
        meta = load_sidecar(path)
        manifest[entry_id] = {
            "file": str(path.relative_to(raw_dir)),
            "source": meta.get("source_url", ""),
            "author": meta.get("author", ""),
            "license": meta.get("license", ""),
            "license_url": meta.get("license_url", ""),
            "title": meta.get("title", path.name),
            "width": int(bgr.shape[1]),
            "height": int(bgr.shape[0]),
            "indexed_at": datetime.now(timezone.utc).isoformat(),
        }
        if (i + 1) % 25 == 0:
            print(f"[index] processed {i + 1}/{len(images)} "
                  f"({len(ids)} indexed)")

    if vectors:
        np.savez_compressed(
            index_dir / "embeddings.npz",
            ids=np.array(ids),
            vectors=np.stack(vectors).astype(np.float32),
        )
    (index_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2)
    )
    # Version marker so future readers (e.g. the Android app) can verify
    # they understand this index layout. See docs/INDEX_FORMAT.md.
    (index_dir / "format.json").write_text(json.dumps({
        "index_version": INDEX_FORMAT_VERSION,
        "vector_dim": 66,
        "landmark_count": 33,
        "landmark_model": "mediapipe pose_landmarker_full",
        "normalization": {
            "origin": "midpoint of landmarks 23 and 24 (mid-hip)",
            "scale": "shoulder-hip distance, fallback max pairwise joint distance",
            "channels": ["x", "y"],
            "visibility_threshold": 0.5,
            "min_visible_ratio": 0.5,
            "output": "L2-normalized float32 unit vector",
        },
        "similarity": "cosine (dot product of unit vectors)",
    }, indent=2))
    (index_dir / "skipped.log").write_text("\n".join(skipped))
    return {"indexed": len(ids), "skipped": len(skipped), "total": len(images)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build pose search index")
    parser.add_argument("--raw", default="data/raw")
    parser.add_argument("--index", default="data/index")
    args = parser.parse_args()

    root = project_root()
    raw_dir = Path(args.raw)
    index_dir = Path(args.index)
    if not raw_dir.is_absolute():
        raw_dir = root / raw_dir
    if not index_dir.is_absolute():
        index_dir = root / index_dir
    if not raw_dir.exists():
        raise SystemExit(f"raw dir not found: {raw_dir} "
                         f"(run a crawler first, see README)")
    index_dir.mkdir(parents=True, exist_ok=True)

    stats = build_index(raw_dir, index_dir)
    print(f"[index] done: {stats['indexed']} indexed, "
          f"{stats['skipped']} skipped, {stats['total']} total")
    print(f"[index] wrote {index_dir / 'embeddings.npz'}")


if __name__ == "__main__":
    main()
