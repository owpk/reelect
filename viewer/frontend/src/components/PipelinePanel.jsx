import { useState, useEffect } from "react";
import LogsModal from "./LogsModal.jsx";
import SettingsModal from "./SettingsModal.jsx";
import "./PipelinePanel.css";

export default function PipelinePanel() {
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState(null);
  const [logsOpen, setLogsOpen] = useState(false);
  const [dlStats, setDlStats] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  // Initial status fetch
  useEffect(() => {
    fetch("/api/pipeline/status")
      .then((r) => r.json())
      .then((d) => { setRunning(d.running); setLastRun(d.last_run); })
      .catch(() => {});
  }, []);

  // Poll status + dl-stats every 3s while running
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => {
      fetch("/api/pipeline/status")
        .then((r) => r.json())
        .then((d) => {
          if (!d.running) {
            setRunning(false);
            setLastRun(d.last_run);
          }
        })
        .catch(() => {});
      fetch("/api/pipeline/dl-stats")
        .then((r) => r.json())
        .then(setDlStats)
        .catch(() => {});
    }, 3_000);
    return () => clearInterval(id);
  }, [running]);

  // Fetch dl-stats on mount and when run ends
  useEffect(() => {
    if (running) return;
    fetch("/api/pipeline/dl-stats")
      .then((r) => r.json())
      .then(setDlStats)
      .catch(() => {});
  }, [running]);

  async function handleRun() {
    try {
      const r = await fetch("/api/pipeline/run", { method: "POST" });
      const d = await r.json();
      if (d.status === "started" || d.status === "already_running") {
        setRunning(true);
        setLogsOpen(true);
      }
    } catch (e) {
      console.error(e);
    }
  }

  async function handleStop() {
    try {
      await fetch("/api/pipeline/stop", { method: "POST" });
    } catch (e) {
      console.error(e);
    }
  }

  const phase = dlStats?.phase;
  const phaseLabel =
    phase === "downloading" ? "Загрузка..." :
    phase === "analyzing"   ? "Анализ..."   : null;

  return (
    <div className="pipeline">
      <div className="pipeline-title">Pipeline</div>
      <div className="pipeline-status">
        <span className={`status-dot ${running ? "running" : "idle"}`} />
        <span className="status-label">{running ? "Running..." : "Idle"}</span>
      </div>
      {lastRun && !running && (
        <span className="last-run">last: {new Date(lastRun).toLocaleString()}</span>
      )}
      <div className="pipeline-actions">
        {running ? (
          <button className="btn-stop" onClick={handleStop}>■ Stop</button>
        ) : (
          <button className="btn-run" onClick={handleRun}>▶ Run pipeline</button>
        )}
        <button className="btn-logs-icon" onClick={() => setLogsOpen(true)} title="Show logs">
          📋
        </button>
        <button className="btn-settings-icon" onClick={() => setSettingsOpen(true)} title="Settings">
          ⚙️
        </button>
      </div>

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
