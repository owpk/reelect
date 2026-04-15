from pathlib import Path

from reelect_pipeline.settings import PipelineSettings, load_pipeline_settings


def test_load_pipeline_settings_reads_values_from_env_file(tmp_path: Path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "INSTAGRAM_USERNAME=test_user\n"
        "MAX_WORKERS=5\n"
        "LLM_BASE_URL=http://example.test/v1\n"
        "LLM_MODEL=test-model\n",
        encoding="utf-8",
    )

    settings = load_pipeline_settings(env_file)

    assert isinstance(settings, PipelineSettings)
    assert settings.instagram_username == "test_user"
    assert settings.max_workers == 5
    assert settings.llm_base_url == "http://example.test/v1"
    assert settings.llm_model == "test-model"
