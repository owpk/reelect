import { useState, useEffect, useMemo } from "react";
import Sidebar from "./components/Sidebar.jsx";
import VideoGrid from "./components/VideoGrid.jsx";
import Modal from "./components/Modal.jsx";
import PipelinePanel from "./components/PipelinePanel.jsx";
import "./App.css";

export default function App() {
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    fetch("/api/videos")
      .then((r) => r.json())
      .then((data) => { setVideos(data); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const filtered = useMemo(() => {
    return videos.filter((v) => {
      const matchCat = category === "all" || v.category === category;
      const q = query.toLowerCase();
      const matchQuery =
        !q ||
        v.summary?.toLowerCase().includes(q) ||
        v.transcript?.toLowerCase().includes(q) ||
        v.tags?.some((t) => t.toLowerCase().includes(q));
      return matchCat && matchQuery;
    });
  }, [videos, category, query]);

  const categories = useMemo(() => {
    const counts = {};
    videos.forEach((v) => {
      counts[v.category] = (counts[v.category] || 0) + 1;
    });
    return counts;
  }, [videos]);

  return (
    <div className="layout">
      <Sidebar
        categories={categories}
        total={videos.length}
        selected={category}
        onSelect={setCategory}
      />
      <main className="main">
        <header className="header">
          <h1 className="title">🎬 Saved Reels</h1>
          <input
            className="search"
            placeholder="Search by summary, transcript or tag..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </header>
        {loading ? (
          <p className="empty">Loading...</p>
        ) : filtered.length === 0 ? (
          <p className="empty">No videos found.</p>
        ) : (
          <VideoGrid videos={filtered} onSelect={setSelected} />
        )}
      </main>
      <PipelinePanel />
      {selected && <Modal video={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
