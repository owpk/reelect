import { useEffect, useState } from "react";
import LogsModal from "./LogsModal.jsx";
import "./PipelinePanel.css";
import SettingsModal from "./SettingsModal.jsx";

const MODES = {
  saved: {
    label: "Saved reels",
    button: "Run saved pipeline",
  },
  single: {
    label: "Direct link",
    button: "Run link",
  },
};

export default function PipelinePanel({ onFinished }) {
  const [mode, setMode] = useState("saved");
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState(null);
  const [activeMode, setActiveMode] = useState(null);
  const [phase, setPhase] = useState("idle");
  const [logsOpen, setLogsOpen] = useState(false);
  const [dlStats, setDlStats] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [singleUrl, setSingleUrl] = useState("");
  const [error, setError] = useState("");

  async function fetchStatus() {
    const response = await fetch("/api/pipeline/status");
    const data = await response.json();
    setRunning(Boolean(data.running));
    setLastRun(data.last_run ?? null);
    setActiveMode(data.mode ?? null);
    setPhase(data.phase ?? "idle");
    return data;
  }

  useEffect(() => {
    fetchStatus().catch(() => {});
  }, []);

  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => {
      fetchStatus()
        .then((data) => {
          if (!data.running) {
            onFinished?.();
            fetch("/api/pipeline/dl-stats")
              .then((r) => r.json())
              .then(setDlStats)
              .catch(() => {});
          }
        })
        .catch(() => {});
      fetch("/api/pipeline/dl-stats")
        .then((r) => r.json())
        .then(setDlStats)
        .catch(() => {});
    }, 3_000);
    return () => clearInterval(id);
  }, [running, onFinished]);

  useEffect(() => {
    if (running) return;
    fetch("/api/pipeline/dl-stats")
      .then((r) => r.json())
      .then(setDlStats)
      .catch(() => {});
  }, [running]);

  function isValidUrl(value) {
    return /^https?:/i.test(value.trim());
  }

  async function handleRunSaved() {
    try {
      setError("");
      const r = await fetch("/api/pipeline/run", { method: "POST" });
      const d = await r.json();
      if (d.status === "started" || d.status === "already_running") {
        setRunning(true);
        setActiveMode("saved");
        setPhase("downloading");
        setLogsOpen(true);
      }
    } catch (e) {
      console.error(e);
      setError("Failed to start saved pipeline.");
    }
  }

  async function handleRunSingle() {
    const normalizedUrl = singleUrl.trim();
    if (!isValidUrl(normalizedUrl)) {
      setError("Enter a valid URL.");
      return;
    }

    try {
      setError("");
      const response = await fetch("/api/pipeline/run-single", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: normalizedUrl }),
      });
      const data = await response.json();
      if (data.status === "started" || data.status === "already_running") {
        setRunning(true);
        setActiveMode("single");
        setPhase("downloading");
        setLogsOpen(true);
      } else {
        setError("Pipeline did not start.");
      }
    } catch (e) {
      console.error(e);
      setError("Failed to start direct link pipeline.");
    }
  }

  async function handleStop() {
    try {
      await fetch("/api/pipeline/stop", { method: "POST" });
    } catch (e) {
      console.error(e);
    }
  }

  const phaseLabel =
    phase === "downloading" ? "Загрузка..." :
    phase === "parsing"     ? "Подготовка..." :
    phase === "analyzing"   ? "Анализ..."   : null;
  const runningMode = activeMode ?? mode;
  const actionLabel = MODES[mode].button;

  return (
    <div className="pipeline">
      <div className="pipeline-title">Pipeline</div>
      <div className="pipeline-status">
        <span className={`status-dot ${running ? "running" : "idle"}`} />
        <span className="status-label">{running ? "Running..." : "Idle"}</span>
      </div>
      <div className="pipeline-mode-switch">
        {Object.entries(MODES).map(([key, definition]) => (
          <button
            key={key}
            className={`pipeline-mode-chip ${mode === key ? "active" : ""}`}
            onClick={() => setMode(key)}
            disabled={running}
          >
            {definition.label}
          </button>
        ))}
      </div>
      {lastRun && !running && (
        <span className="last-run">last: {new Date(lastRun).toLocaleString()}</span>
      )}
      {runningMode && (
        <span className="pipeline-meta">
          mode: {runningMode} {phaseLabel ? `• ${phaseLabel}` : ""}
        </span>
      )}

      {mode === "single" && (
        <div className="pipeline-direct">
          <label className="pipeline-input-label" htmlFor="single-reel-url">
            Instagram reel URL
          </label>
          <input
            id="single-reel-url"
            className="pipeline-input"
            value={singleUrl}
            disabled={running}
            placeholder="https://www.instagram.com/reel/..."
            onChange={(e) => setSingleUrl(e.target.value)}
          />
        </div>
      )}

      <div className="pipeline-actions">
        {running ? (
          <button className="btn-stop" onClick={handleStop}>■ Stop</button>
        ) : (
          <button
            className="btn-run"
            onClick={mode === "saved" ? handleRunSaved : handleRunSingle}
          >
            ▶ {actionLabel}
          </button>
        )}
        <button className="btn-logs-icon" onClick={() => setLogsOpen(true)} title="Show logs">
          📋
        </button>
        <button className="btn-settings-icon" onClick={() => setSettingsOpen(true)} title="Settings">
          ⚙️
        </button>
      </div>
      {error && <div className="pipeline-error">{error}</div>}

      {dlStats && (
        <div className="dl-stats">
          {/* Download section */}
          <div className="dl-stats-section">
            <div className="dl-stats-title">Загрузка</div>
            <div className="dl-stats-row">
              <span className="dl-stats-label">Скачано</span>
              <span className={`dl-stats-value${phase === "downloading" ? " active" : ""}`}>
                {dlStats.session_downloaded} новых
              </span>
            </div>
            <div className="dl-stats-row">
              <span className="dl-stats-label">В архиве</span>
              <span className="dl-stats-value">{dlStats.total_archived}</span>
            </div>
          </div>

          {/* Analyze section */}
          <div className="dl-stats-section">
            <div className="dl-stats-title">Анализ</div>
            <div className="dl-stats-row">
              <span className="dl-stats-label">Проанализировано</span>
              <span className={`dl-stats-value${phase === "analyzing" ? " active" : ""}`}>
                {dlStats.analyzed} / {dlStats.total_videos}
              </span>
            </div>
          </div>

          {/* Phase label while running */}
          {running && phaseLabel && (
            <div className="dl-phase">{phaseLabel}</div>
          )}
        </div>
      )}

      {logsOpen && <LogsModal onClose={() => setLogsOpen(false)} />}
      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
    </div>
  );
}
