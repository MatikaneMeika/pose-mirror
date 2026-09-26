"""Export the index into a dependency-free bundle for redistribution.

Reads ``data/index/`` (embeddings.npz, manifest.json, thumbs/, format.json)
and writes a portable directory that any platform can parse without NumPy:

    <out>/
        vectors.f32le.bin   raw little-endian float32, row-major, N*66 values
        ids.json            ["000000", ...] aligned with the binary rows
        manifest.json       copy
        format.json         copy
        thumbs/             copy

Zip <out> and attach it to a GitHub Release; the Android client (or any
other) downloads and uses it as-is. See docs/INDEX_FORMAT.md.

Example:
    python -m posemirror.export_portable --index data/index --out dist/index-v1
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np

from .pose import project_root


def export_portable(index_dir: Path, out_dir: Path) -> dict:
    emb_path = index_dir / "embeddings.npz"
    if not emb_path.exists():
        raise SystemExit(f"no embeddings at {emb_path} (run build_index first)")
    out_dir.mkdir(parents=True, exist_ok=True)

    data = np.load(emb_path)
    ids = [str(i) for i in data["ids"]]
    vectors = np.ascontiguousarray(data["vectors"], dtype=np.float32)
    assert vectors.shape == (len(ids), 66), f"unexpected shape {vectors.shape}"

    (out_dir / "vectors.f32le.bin").write_bytes(vectors.tobytes(order="C"))
    (out_dir / "ids.json").write_text(json.dumps(ids))
    for name in ("manifest.json", "format.json"):
        src = index_dir / name
        if src.exists():
            shutil.copy2(src, out_dir / name)
    thumbs_src = index_dir / "thumbs"
    if thumbs_src.exists():
        shutil.copytree(thumbs_src, out_dir / "thumbs", dirs_exist_ok=True)

    return {"ids": len(ids), "bytes": vectors.nbytes, "out": str(out_dir)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Export portable index bundle")
    parser.add_argument("--index", default="data/index")
    parser.add_argument("--out", default="dist/index-v1")
    args = parser.parse_args()

    root = project_root()
    index_dir = Path(args.index)
    out_dir = Path(args.out)
    if not index_dir.is_absolute():
        index_dir = root / index_dir
    if not out_dir.is_absolute():
        out_dir = root / out_dir

    stats = export_portable(index_dir, out_dir)
    print(f"[export] {stats['ids']} vectors -> {stats['out']}")


if __name__ == "__main__":
    main()
