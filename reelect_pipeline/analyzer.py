from __future__ import annotations

import base64
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

from reelect_pipeline.manifest_store import save_manifest
from reelect_pipeline.models import ReelManifest
from reelect_pipeline.settings import PipelineSettings

LM_STATUS_FILE = Path("/tmp/lm_status.json")
PROMPTS_DIR = Path("/app/prompts")


class ReelAnalyzer:
    def __init__(self, settings: PipelineSettings, meta_root: Path) -> None:
        self.settings = settings
        self.meta_root = meta_root
        self._client: OpenAI | None = None
        self._semaphore = threading.Semaphore(settings.llm_concurrency)
        self._prompt_template = self._load_prompt_template()

    def analyze_media(self, manifest: ReelManifest) -> ReelManifest:
        transcript = self._read_transcript(manifest)
        frame_paths = self._read_frame_paths(manifest)
        payload = self._normalize_model_payload(
            self._call_model(
                transcript=transcript,
                frame_paths=frame_paths,
                video_path=manifest.video_path,
            )
        )

        analyzed_at = datetime.now(timezone.utc).isoformat()
        result = {
            "id": manifest.id,
            "filename": str(manifest.video_path),
            "analyzed_at": analyzed_at,
            "transcript": transcript,
            **payload,
        }

        self.meta_root.mkdir(parents=True, exist_ok=True)
        meta_path = self.meta_root / f"{manifest.id}.json"
        meta_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        manifest.analysis.status = "completed"
        manifest.analysis.meta_output_path = str(meta_path)
        manifest.analysis.analyzed_at = analyzed_at
        manifest.analysis.model = self.settings.llm_model
        save_manifest(manifest)
        return manifest

    def _read_transcript(self, manifest: ReelManifest) -> str:
        transcript_path = manifest.parse.transcript_path
        if not transcript_path:
            return ""
        path = Path(transcript_path)
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def _read_frame_paths(self, manifest: ReelManifest) -> list[Path]:
        frames_dir = manifest.parse.frames_dir
        if not frames_dir:
            return []
        path = Path(frames_dir)
        if not path.exists():
            return []
        return sorted(path.glob("frame_*.jpg"))

    def _call_model(
        self, transcript: str, frame_paths: list[Path], video_path: Path
    ) -> dict[str, object] | str:
        self._write_lm_request_time()
        messages = [
            {
                "role": "user",
                "content": self._build_content(
                    transcript=transcript,
                    frame_paths=frame_paths,
                    video_path=video_path,
                ),
            }
        ]

        extra_body = None
        if self.settings.llm_thinking_budget >= 0:
            extra_body = {
                "thinking": {
                    "type": "enabled",
                    "budget_tokens": self.settings.llm_thinking_budget,
                }
            }

        with self._semaphore:
            response = self._get_client().chat.completions.create(
                model=self.settings.llm_model,
                messages=messages,
                max_tokens=self.settings.llm_max_tokens_metadata,
                extra_body=extra_body,
            )

        content = response.choices[0].message.content
        if isinstance(content, list):
            text = "".join(
                item.get("text", "") for item in content if isinstance(item, dict)
            ).strip()
        else:
            text = (content or "").strip()

        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    def _build_content(
        self, transcript: str, frame_paths: list[Path], video_path: Path
    ) -> list[dict[str, object]]:
        prompt = self._build_prompt(transcript)
        if self.settings.llm_native_video:
            return [
                {
                    "type": "video_url",
                    "video_url": {
                        "url": (
                            "data:video/mp4;base64,"
                            + base64.standard_b64encode(video_path.read_bytes()).decode()
                        )
                    },
                },
                {"type": "text", "text": prompt},
            ]

        content: list[dict[str, object]] = []
        for frame_path in frame_paths:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": (
                            "data:image/jpeg;base64,"
                            + base64.standard_b64encode(frame_path.read_bytes()).decode()
                        )
                    },
                }
            )
        content.append({"type": "text", "text": prompt})
        return content

    def _load_prompt_template(self) -> str:
        lang = self.settings.lang if self.settings.lang in ("en", "ru") else "en"
        prompt_path = PROMPTS_DIR / lang / "prompt.txt"
        if prompt_path.exists():
            return prompt_path.read_text(encoding="utf-8")
        # Fallback to English
        return (PROMPTS_DIR / "en" / "prompt.txt").read_text(encoding="utf-8")

    def _build_prompt(self, transcript: str) -> str:
        transcript_block = transcript if transcript else "(no speech detected)"
        return self._prompt_template.format(transcript=transcript_block)

    def _normalize_model_payload(self, payload: dict[str, object] | str) -> dict[str, object]:
        if isinstance(payload, dict):
            return payload
        return {
            "summary": str(payload)[:300],
            "category": "other",
            "tags": [],
            "actionable": None,
        }

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                base_url=self.settings.llm_base_url,
                api_key=self.settings.llm_api_key or "not-needed",
            )
        return self._client

    def _write_lm_request_time(self) -> None:
        LM_STATUS_FILE.write_text(
            json.dumps({"last_request_at": datetime.now(timezone.utc).isoformat()}),
            encoding="utf-8",
        )
