import { useState, useEffect, useMemo, useCallback } from "react";
import Sidebar from "./components/Sidebar.jsx";
import VideoGrid from "./components/VideoGrid.jsx";
import Modal from "./components/Modal.jsx";
import "./App.css";

export default function App() {
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [category, setCategory] = useState("all");
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);

  async function loadVideos() {
    setLoading(true);
    try {
      const response = await fetch("/api/videos");
      const data = await response.json();
      setVideos(data);
    } catch {
      setVideos([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadVideos();
  }, []);

  const handleDelete = useCallback(async (videoId) => {
    try {
      await fetch(`/api/videos/${videoId}`, { method: "DELETE" });
      setVideos((prev) => prev.filter((v) => v.id !== videoId));
    } catch (err) {
      console.error("Failed to delete video:", err);
    }
  }, []);

  const handleRegenerate = useCallback(async (videoId) => {
    try {
      await fetch(`/api/videos/${videoId}/regenerate`, { method: "POST" });
      // Reload videos to show updated data
      await loadVideos();
    } catch (err) {
      console.error("Failed to regenerate video:", err);
    }
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

  useEffect(() => {
    if (!selected) {
      return;
    }
    const updatedSelected = videos.find((video) => video.id === selected.id);
    if (!updatedSelected) {
      setSelected(null);
      return;
    }
    if (updatedSelected !== selected) {
      setSelected(updatedSelected);
    }
  }, [videos, selected]);

  return (
    <div className="layout">
      <Sidebar
        categories={categories}
        total={videos.length}
        selected={category}
        onSelect={setCategory}
        onPipelineFinished={loadVideos}
      />
      <main className="main">
        <header className="header">
          <h1 className="title">🎬 Reelect Library</h1>
          <input
            className="search"
            placeholder="Search by summary, transcript or tag..."
            value={query}
            onChange={(e) => setQuery(e.target)}
          />
        </header>
        {loading ? (
          <p className="empty">Loading...</p>
        ) : filtered.length === 0 ? (
          <p className="empty">No videos found.</p>
        ) : (
          <VideoGrid
            videos={filtered}
            onSelect={setSelected}
            onDelete={handleDelete}
            onRegenerate={handleRegenerate}
          />
        )}
      </main>
      {selected && <Modal video={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
