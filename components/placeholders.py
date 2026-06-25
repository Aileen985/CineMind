# components/placeholders.py
"""
占位图和常量
"""
import base64

# ---------- 本地占位图 ----------
NO_POSTER_SVG = """<svg xmlns="http://www.w3.org/2000/svg" width="200" height="300" viewBox="0 0 200 300">
    <rect width="200" height="300" fill="#2a2f4e"/>
    <text x="50%" y="50%" font-family="Arial" font-size="24" fill="#98a1c3" text-anchor="middle" dy=".3em">🎬 暂无海报</text>
</svg>"""
NO_POSTER_URL = "data:image/svg+xml;base64," + base64.b64encode(NO_POSTER_SVG.encode()).decode()

# ---------- 骨架屏 ----------
SKELETON_CSS = """
<style>
.skeleton-message {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 12px;
    background: #1a1e2c;
    border-radius: 12px;
    border: 1px solid #252838;
    animation: pulse 1.5s ease-in-out infinite;
}
.skeleton-text {
    height: 14px;
    border-radius: 4px;
    background: #2a2f4e;
}
.skeleton-text.short { width: 60%; }
.skeleton-text.medium { width: 80%; }
.skeleton-card {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    margin-top: 8px;
}
.skeleton-card-item {
    aspect-ratio: 2/3;
    background: #2a2f4e;
    border-radius: 8px;
}
@keyframes pulse {
    0% { opacity: 0.6; }
    50% { opacity: 1; }
    100% { opacity: 0.6; }
}
</style>
"""