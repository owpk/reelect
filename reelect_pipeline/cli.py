from __future__ import annotations

import argparse

from reelect_pipeline.bootstrap import build_orchestrator


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("run-saved")
    run_single = subparsers.add_parser("run-single")
    run_single.add_argument("url")
    subparsers.add_parser("parse-pending")
    subparsers.add_parser("analyze-pending")

    args = parser.parse_args()
    orchestrator = build_orchestrator()

    if args.command == "run-saved":
        print("STAGE: downloading", flush=True)
        manifests = orchestrator.download_saved_reels()
        print(f"Downloaded {len(manifests)} new reel(s)", flush=True)
        if not manifests:
            return
        print("STAGE: parsing", flush=True)
        manifests = orchestrator.parse_manifests(manifests)
        print("STAGE: analyzing", flush=True)
        orchestrator.analyze_manifests(manifests)
        return
    if args.command == "run-single":
        print("STAGE: downloading", flush=True)
        manifest = orchestrator.download_single_reel(args.url)
        print("STAGE: parsing", flush=True)
        manifest = orchestrator.parse_manifests([manifest])[0]
        print("STAGE: analyzing", flush=True)
        orchestrator.analyze_manifests([manifest])
        return
    if args.command == "parse-pending":
        orchestrator.run_parse_pending()
        return
    if args.command == "analyze-pending":
        orchestrator.run_analysis_pending()
        return
    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
