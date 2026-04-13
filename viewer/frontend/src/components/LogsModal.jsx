import { useState, useEffect, useRef } from "react";
import "./LogsModal.css";

export default function LogsModal({ onClose }) {
  const [lines, setLines] = useState([]);
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState(null);
  const [lmStatus, setLmStatus] = useState(null);
  const endRef = useRef(null);
  const esRef = useRef(null);
  const pollRef = useRef(null);

  // Close on Escape
  useEffect(() => {
    const handler = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  // Auto-scroll
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  // Fetch LM status
  function fetchLmStatus() {
    fetch("/api/lm/status")
      .then((r) => r.json())
      .then(setLmStatus)
      .catch(() => setLmStatus({ connected: false, url: null, model: null, last_request_at: null }));
  }

  // Connect to SSE stream
  function connectStream() {
    if (esRef.current) esRef.current.close();
    const es = new EventSource("/api/pipeline/stream");
    esRef.current = es;
    es.onmessage = (e) => {
      if (e.data === "__done__") {
        setRunning(false);
        es.close();
        esRef.current = null;
        return;
      }
      setLines((prev) => [...prev, e.data]);
    };
    es.onerror = () => {
      setRunning(false);
      es.close();
      esRef.current = null;
    };
  }

  // Initial load
  useEffect(() => {
    fetch("/api/pipeline/logs")
      .then((r) => r.json())
      .then((d) => {
        setLines(d.lines ?? []);
        setRunning(d.running ?? false);
        setLastRun(d.last_run ?? null);
        if (d.running) connectStream();
      })
      .catch(() => {});

    fetchLmStatus();

    // Poll LM status every 10s
    const lmInterval = setInterval(fetchLmStatus, 10_000);

    // Poll pipeline status every 5s to detect if it starts while modal is open
    pollRef.current = setInterval(() => {
      if (esRef.current) return; // already streaming
      fetch("/api/pipeline/status")
        .then((r) => r.json())
        .then((d) => {
          setRunning(d.running);
          setLastRun(d.last_run);
          if (d.running) connectStream();
        })
        .catch(() => {});
    }, 5_000);

    return () => {
      esRef.current?.close();
      clearInterval(lmInterval);
      clearInterval(pollRef.current);
    };
  }, []);

  function formatTime(iso) {
    if (!iso) return null;
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  }

  return (
    <div className="logs-overlay" onClick={onClose}>
      <div className="logs-modal" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="logs-modal-header">
          <span className="logs-modal-title">Pipeline Logs</span>
          <button className="logs-modal-close" onClick={onClose}>✕</button>
        </div>

        {/* LM Studio section */}
        <div className="lm-section">
          <div className="lm-section-title">LM Studio</div>
          {lmStatus === null ? (
            <div className="lm-row"><span className="logs-status-label">Loading...</span></div>
          ) : (
            <>
              <div className="lm-row">
                <span className={`lm-dot ${lmStatus.connected ? "connected" : "disconnected"}`} />
                <span className="lm-model">
                  {lmStatus.connected ? (lmStatus.model ?? "connected") : "Disconnected"}
                </span>
              </div>
              <div className="lm-meta">
                {lmStatus.url && (
                  <span className="lm-meta-line">URL: {lmStatus.url}</span>
                )}
                {lmStatus.last_request_at && (
                  <span className="lm-meta-line">
                    Last request: {formatTime(lmStatus.last_request_at)}
                  </span>
                )}
              </div>
            </>
          )}
        </div>

        {/* Pipeline status row */}
        <div className="logs-status-row">
          <span className={`logs-status-dot ${running ? "running" : "idle"}`} />
          <span className="logs-status-label">{running ? "Running..." : "Idle"}</span>
          {lastRun && !running && (
            <span className="logs-last-run">last: {formatTime(lastRun)}</span>
          )}
        </div>

        {/* Log terminal */}
        <div className="logs-terminal">
          {lines.length === 0 ? (
            <div className="logs-empty">No logs yet.</div>
          ) : (
            lines.map((line, i) => {
              const cls = line.includes("ERROR") || line.includes("error")
                ? "error"
                : "info";
              return <div key={i} className={`logs-line ${cls}`}>{line}</div>;
            })
          )}
          <div ref={endRef} />
        </div>
      </div>
    </div>
  );
}
