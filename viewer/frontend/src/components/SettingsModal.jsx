import { useState, useEffect } from "react";
import "./SettingsModal.css";

const CONFIG_FIELDS = [
  {
    key: "LLM_BASE_URL",
    label: "LLM Base URL",
    placeholder: "http://host.docker.internal:1234/v1",
    description: "OpenAI-compatible endpoint (LM Studio, OpenRouter, Ollama)",
  },
  {
    key: "LLM_MODEL",
    label: "LLM Model",
    placeholder: "qwen2.5-vl-7b-instruct",
    description: "Model name (must match provider exactly)",
  },
  {
    key: "LLM_API_KEY",
    label: "LLM API Key",
    placeholder: "Optional - only if required",
    description: "API key for authenticated providers (OpenRouter, etc.)",
    type: "password",
  },
  {
    key: "LLM_CONCURRENCY",
    label: "LLM Concurrency",
    placeholder: "1",
    description: "Max concurrent LLM requests",
    type: "number",
  },
  {
    key: "LLM_NATIVE_VIDEO",
    label: "Native Video",
    type: "boolean",
    description: "Send full video instead of frames (requires video-capable model)",
  },
  {
    key: "LLM_THINKING_BUDGET",
    label: "Thinking Budget",
    placeholder: "512",
    description: "Reasoning token limit (-1 for unlimited, 0 to disable)",
    type: "number",
  },
  {
    key: "LLM_MAX_TOKENS_VISUAL",
    label: "Max Tokens (Visual)",
    placeholder: "4096",
    description: "Max tokens for visual/frame description",
    type: "number",
  },
  {
    key: "LLM_MAX_TOKENS_METADATA",
    label: "Max Tokens (Metadata)",
    placeholder: "8192",
    description: "Max tokens for metadata + actionable extraction",
    type: "number",
  },
  {
    key: "MAX_WORKERS",
    label: "Max Workers",
    placeholder: "3",
    description: "Parallel video analysis workers (whisper + ffmpeg)",
    type: "number",
  },
  {
    key: "INSTAGRAM_USERNAME",
    label: "Instagram Username",
    placeholder: "your_instagram_handle",
    description: "Your Instagram handle for downloading",
  },
];

export default function SettingsModal({ onClose }) {
  const [config, setConfig] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then((data) => {
        setConfig(data);
        setLoading(false);
      })
      .catch(() => {
        setError("Failed to load configuration");
        setLoading(false);
      });
  }, []);

  const handleChange = (key, value) => {
    setConfig((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
    setError(null);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const r = await fetch("/api/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ config }),
      });
      if (r.ok) {
        setSaved(true);
        setTimeout(() => onClose(), 1000);
      } else {
        const d = await r.json();
        setError(d.detail || "Failed to save configuration");
      }
    } catch (e) {
      setError("Failed to save configuration");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="overlay">
        <div className="modal">
          <div className="modal-content">
            <p>Loading...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="overlay">
      <div className="modal modal-settings">
        <button className="modal-close" onClick={onClose}>×</button>
        <div className="modal-content">
          <div className="settings-header">
            <h2>Settings</h2>
            {saved && <span className="saved-badge">Saved!</span>}
          </div>
          {error && <div className="error-message">{error}</div>}

          <div className="settings-fields">
            {CONFIG_FIELDS.map(({ key, label, placeholder, description, type }) => (
              <div key={key} className="settings-field">
                <label className="settings-label" htmlFor={key}>
                  {label}
                </label>
                {type === "boolean" ? (
                  <label className="toggle">
                    <input
                      type="checkbox"
                      id={key}
                      checked={config[key] === "true"}
                      onChange={(e) =>
                        handleChange(key, e.target.checked ? "true" : "false")
                      }
                    />
                    <span className="toggle-slider" />
                  </label>
                ) : (
                  <input
                    type={type || "text"}
                    id={key}
                    className="settings-input"
                    value={config[key] || ""}
                    onChange={(e) => handleChange(key, e.target.value)}
                    placeholder={placeholder}
                  />
                )}
                {description && (
                  <span className="settings-description">{description}</span>
                )}
              </div>
            ))}
          </div>

          <div className="settings-actions">
            <button className="btn-cancel" onClick={onClose}>
              Cancel
            </button>
            <button className="btn-save" onClick={handleSave} disabled={saving}>
              {saving ? "Saving..." : "Save Changes"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
