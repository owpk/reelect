import { useRef, useCallback } from "react";
import { categoryColor } from "./Sidebar.jsx";
import "./VideoCard.css";

const ACTIONABLE_ICON = {
  recipe: "🍳",
  guide: "📋",
  recommendation: "🎬",
  resource: "🔗",
};

export default function VideoCard({ video, onSelect, onDelete, onRegenerate }) {
  const videoRef = useRef(null);
  const { actionable } = video;

  const handleMouseEnter = () => videoRef.current?.play();
  const handleMouseLeave = () => {
    const v = videoRef.current;
    if (!v) return;
    v.pause();
    v.currentTime = 0;
  };

  const handleDelete = useCallback((e) => {
    e.stopPropagation();
    onDelete?.(video.id);
  }, [onDelete, video.id]);

  const handleRegenerate = useCallback((e) => {
    e.stopPropagation();
    onRegenerate?.(video.id);
  }, [onRegenerate, video.id]);

  return (
    <div
      className="card"
      onClick={() => onSelect(video)}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <div className="card-video">
        {video.has_video ? (
          <video
            ref={videoRef}
            src={`/api/videos/${video.id}/stream`}
            muted
            loop
            playsInline
            preload="metadata"
          />
        ) : (
          <div className="card-no-video">No video</div>
        )}
        <span
          className="card-badge"
          style={{ background: categoryColor(video.category) }}
        >
          {video.category}
        </span>
      </div>

      <div className="card-body">
        {actionable ? (
          <div className="card-actionable">
            <div className="actionable-header">
              <span className="actionable-icon">{ACTIONABLE_ICON[actionable.type] ?? "✦"}</span>
              <span className="actionable-type">{actionable.type}</span>
              <span className="actionable-title">{actionable.title}</span>
            </div>
            <p className="actionable-preview">{actionable.content}</p>
          </div>
        ) : (
          <p className="card-summary">{video.summary}</p>
        )}

        {video.tags?.length > 0 && (
          <div className="card-tags">
            {video.tags.map((t) => (
              <span key={t} className="tag">#{t}</span>
            ))}
          </div>
        )}

        <div className="card-actions">
          <button className="card-action-btn delete" onClick={handleDelete}>
            🗑️ Delete
          </button>
          <button className="card-action-btn regenerate" onClick={handleRegenerate}>
            🔄 Regenerate
          </button>
        </div>
      </div>
    </div>
  );
}
