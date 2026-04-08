import VideoCard from "./VideoCard.jsx";
import "./VideoGrid.css";

export default function VideoGrid({ videos, onSelect }) {
  return (
    <div className="grid-scroll">
      <div className="grid">
        {videos.map((v) => (
          <VideoCard key={v.id} video={v} onSelect={onSelect} />
        ))}
      </div>
    </div>
  );
}
