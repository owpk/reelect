import PipelinePanel from "./PipelinePanel.jsx";
import "./Sidebar.css";

const CATEGORY_COLORS = {
  cooking: "#f97316",
  travel: "#06b6d4",
  fitness: "#22c55e",
  tech: "#6366f1",
  comedy: "#eab308",
  art: "#ec4899",
  news: "#94a3b8",
  music: "#a78bfa",
  education: "#14b8a6",
  lifestyle: "#f43f5e",
};

export function categoryColor(cat) {
  return CATEGORY_COLORS[cat] || "#888";
}

export default function Sidebar({
  categories,
  total,
  selected,
  onSelect,
  onPipelineFinished,
}) {
  const sorted = Object.entries(categories).sort((a, b) => b[1] - a[1]);

  return (
    <aside className="sidebar">
      <div className="sidebar-title">Categories</div>
      <button
        className={`cat-item ${selected === "all" ? "active" : ""}`}
        onClick={() => onSelect("all")}
      >
        <span className="cat-dot" style={{ background: "#888" }} />
        <span className="cat-name">All</span>
        <span className="cat-count">{total}</span>
      </button>
      {sorted.map(([cat, count]) => (
        <button
          key={cat}
          className={`cat-item ${selected === cat ? "active" : ""}`}
          onClick={() => onSelect(cat)}
        >
          <span className="cat-dot" style={{ background: categoryColor(cat) }} />
          <span className="cat-name">{cat}</span>
          <span className="cat-count">{count}</span>
        </button>
      ))}
      <div className="sidebar-divider" />
      <PipelinePanel onFinished={onPipelineFinished} />
    </aside>
  );
}
