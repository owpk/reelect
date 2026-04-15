from pathlib import Path

from reelect_pipeline.manifest_store import list_manifests, load_manifest, save_manifest
from reelect_pipeline.models import ReelManifest


def test_save_manifest_writes_next_to_video(tmp_path: Path):
    video_path = tmp_path / "clip.mp4"
    video_path.write_bytes(b"video")

    manifest = ReelManifest(
        id="clip",
        source_type="single",
        source_url="https://example.test/reel/clip",
        video_path=video_path,
    )

    manifest_path = save_manifest(manifest)
    loaded = load_manifest(manifest_path)

    assert manifest_path == tmp_path / "clip.manifest.json"
    assert loaded.id == "clip"
    assert loaded.video_path == video_path


def test_list_manifests_backfills_manifest_for_existing_video(tmp_path: Path):
    raw_root = tmp_path / "saved_videos" / "raw"
    account_dir = raw_root / "instagram" / "author"
    account_dir.mkdir(parents=True)
    video_path = account_dir / "legacy.mp4"
    video_path.write_bytes(b"video")

    manifests = list_manifests(raw_root)

    assert len(manifests) == 1
    assert manifests[0].id == "legacy"
    assert (account_dir / "legacy.manifest.json").exists()
