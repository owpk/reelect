import { useState, useEffect } from "react";
import LogsModal from "./LogsModal.jsx";
import "./PipelinePanel.css";

export default function PipelinePanel() {
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState(null);
  const [logsOpen, setLogsOpen] = useState(false);
  const [dlStats, setDlStats] = useState(null);

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

  // One final dl-stats fetch when run ends
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

  const phaseLabel =
    dlStats?.phase === "downloading" ? "Downloading..." :
    dlStats?.phase === "analyzing"   ? "Analyzing..."   : null;

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
        <button className="btn-run" onClick={handleRun} disabled={running}>
          {running ? "Running..." : "▶ Run pipeline"}
        </button>
        <button className="btn-logs-icon" onClick={() => setLogsOpen(true)} title="Show logs">
          📋
        </button>
      </div>

      {dlStats && (
        <div className="dl-stats">
          <div className="dl-stats-title">Download</div>
          <div className="dl-stats-row">
            <span className="dl-stats-label">Всего в архиве</span>
            <span className="dl-stats-value">{dlStats.total_archived} видео</span>
          </div>
          {!running && dlStats.session_downloaded > 0 && (
            <div className="dl-stats-row">
              <span className="dl-stats-label">Последний запуск</span>
              <span className="dl-stats-value">+{dlStats.session_downloaded} новых</span>
            </div>
          )}
          {running && dlStats.phase === "downloading" && (
            <div className="dl-stats-counter">
              {dlStats.session_downloaded} скачано
            </div>
          )}
          {running && phaseLabel && (
            <div className="dl-phase">{phaseLabel}</div>
          )}
        </div>
      )}

      {logsOpen && <LogsModal onClose={() => setLogsOpen(false)} />}
    </div>
  );
}
