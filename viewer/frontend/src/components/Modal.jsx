import { useEffect } from "react";
import { categoryColor } from "./Sidebar.jsx";
import "./Modal.css";

export default function Modal({ video, onClose }) {
  useEffect(() => {
    const handler = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div className="overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>✕</button>

        <div className="modal-video">
          {video.has_video && (
            <video
              src={`/api/videos/${video.id}/stream`}
              controls
              autoPlay
              muted
              loop
              playsInline
            />
          )}
        </div>

        <div className="modal-content">
          <div className="modal-header">
            <span
              className="modal-badge"
              style={{ background: categoryColor(video.category) }}
            >
              {video.category}
            </span>
            <span className="modal-date">
              {new Date(video.analyzed_at).toLocaleDateString()}
            </span>
          </div>

          <p className="modal-summary">{video.summary}</p>

          {video.tags?.length > 0 && (
            <div className="modal-tags">
              {video.tags.map((t) => (
                <span key={t} className="tag">#{t}</span>
              ))}
            </div>
          )}

          {video.transcript && (
            <section className="modal-section">
              <h3>Transcript</h3>
              <p>{video.transcript}</p>
            </section>
          )}

          {video.visual_description && (
            <section className="modal-section">
              <h3>Visual</h3>
              <p>{video.visual_description}</p>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
