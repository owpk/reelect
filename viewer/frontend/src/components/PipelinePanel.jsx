import { useState, useEffect, useRef } from "react";
import "./PipelinePanel.css";

export default function PipelinePanel() {
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState(null);
  const [logs, setLogs] = useState([]);
  const [open, setOpen] = useState(false);
  const logsEndRef = useRef(null);
  const esRef = useRef(null);

  useEffect(() => {
    fetch("/api/pipeline/status")
      .then((r) => r.json())
      .then((d) => { setRunning(d.running); setLastRun(d.last_run); })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);

  function startStream() {
    if (esRef.current) esRef.current.close();
    setLogs([]);
    setOpen(true);

    const es = new EventSource("/api/pipeline/stream");
    esRef.current = es;

    es.onmessage = (e) => {
      if (e.data === "__done__") {
        setRunning(false);
        es.close();
        return;
      }
      setLogs((prev) => [...prev, e.data]);
    };
    es.onerror = () => { setRunning(false); es.close(); };
  }

  async function handleRun() {
    try {
      const r = await fetch("/api/pipeline/run", { method: "POST" });
      const d = await r.json();
      if (d.status === "started" || d.status === "already_running") {
        setRunning(true);
        startStream();
      }
    } catch (e) {
      console.error(e);
    }
  }

  return (
    <div className="pipeline">
      <div className="pipeline-bar">
        <div className="pipeline-status">
          <span className={`status-dot ${running ? "running" : "idle"}`} />
          <span className="status-label">{running ? "Running..." : "Idle"}</span>
          {lastRun && !running && (
            <span className="last-run">
              last: {new Date(lastRun).toLocaleString()}
            </span>
          )}
        </div>
        <div className="pipeline-actions">
          {logs.length > 0 && (
            <button className="btn-logs" onClick={() => setOpen((o) => !o)}>
              {open ? "Hide logs" : "Show logs"}
            </button>
          )}
          <button className="btn-run" onClick={handleRun} disabled={running}>
            {running ? "Running..." : "▶ Run pipeline"}
          </button>
        </div>
      </div>

      {open && logs.length > 0 && (
        <div className="log-terminal">
          {logs.map((line, i) => (
            <div key={i} className="log-line">{line}</div>
          ))}
          <div ref={logsEndRef} />
        </div>
      )}
    </div>
  );
}
