import { useRef } from "react";
import { categoryColor } from "./Sidebar.jsx";
import "./VideoCard.css";

const ACTIONABLE_ICON = {
  recipe: "🍳",
  guide: "📋",
  recommendation: "🎬",
  resource: "🔗",
};

export default function VideoCard({ video, onSelect }) {
  const videoRef = useRef(null);
  const { actionable } = video;

  const handleMouseEnter = () => videoRef.current?.play();
  const handleMouseLeave = () => {
    const v = videoRef.current;
    if (!v) return;
    v.pause();
    v.currentTime = 0;
  };

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
      </div>
    </div>
  );
}
