from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from reelect_pipeline.models import AnalysisState, ParseState, ReelManifest


def manifest_path_for(video_path: Path) -> Path:
    return video_path.with_suffix(".manifest.json")


def save_manifest(manifest: ReelManifest) -> Path:
    path = manifest_path_for(manifest.video_path)
    payload = asdict(manifest)
    payload["video_path"] = str(manifest.video_path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_manifest(path: Path) -> ReelManifest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ReelManifest(
        id=payload["id"],
        source_type=payload["source_type"],
        source_url=payload["source_url"],
        video_path=Path(payload["video_path"]),
        shortcode=payload.get("shortcode"),
        downloaded_at=payload.get("downloaded_at"),
        download=payload.get("download", {"status": "completed", "gallery_dl_metadata": {}}),
        parse=ParseState(**payload.get("parse", {})),
        analysis=AnalysisState(**payload.get("analysis", {})),
    )


def list_manifests(raw_root: Path, meta_root: Path | None = None) -> list[ReelManifest]:
    if not raw_root.exists():
        return []
    manifests_by_id = {
        path.stem.removesuffix(".manifest"): load_manifest(path)
        for path in sorted(raw_root.rglob("*.manifest.json"))
    }

    for video_path in sorted(raw_root.rglob("*.mp4")):
        if video_path.stem in manifests_by_id:
            continue
        manifest = ReelManifest(
            id=video_path.stem,
            source_type="legacy",
            source_url="",
            video_path=video_path,
        )
        if meta_root is not None:
            meta_path = meta_root / f"{video_path.stem}.json"
            if meta_path.exists():
                manifest.analysis.status = "completed"
                manifest.analysis.meta_output_path = str(meta_path)
        save_manifest(manifest)
        manifests_by_id[manifest.id] = manifest

    return list(manifests_by_id.values())
