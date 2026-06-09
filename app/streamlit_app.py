import streamlit as st
import threading
import uvicorn
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

st.set_page_config(
    page_title="WindSite India v4",
    page_icon="W",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
#MainMenu {visibility: hidden;}
header {visibility: hidden;}
footer {visibility: hidden;}
.stApp {background: #050709; padding: 0 !important;}
.block-container {padding: 0 !important; max-width: 100% !important;}
</style>
""", unsafe_allow_html=True)

API_PORT = 8000


@st.cache_resource
def start_fastapi():
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    already_running = sock.connect_ex(('localhost', API_PORT)) == 0
    sock.close()
    if already_running:
        return True
    from app.main import app as fastapi_app
    from fastapi.responses import HTMLResponse

    html_path = Path(__file__).parent / "frontend" / "windsite_v4.html"
    with open(str(html_path), "r", encoding="utf-8", errors="replace") as f:
        html_content = f.read()

    # On Streamlit Cloud the browser must use relative URLs
    # FastAPI serves /dashboard and all /api/* routes
    # The HTML must call window.location.origin to find the API
    html_content = html_content.replace(
        "<script>",
        """<script>
window.WINDSITE_API_BASE = (
    window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : window.location.origin
);
""",
        1
    )

    @fastapi_app.get("/dashboard", response_class=HTMLResponse)
    def dashboard():
        return HTMLResponse(content=html_content)

    def run():
        uvicorn.run(
            fastapi_app,
            host="0.0.0.0",
            port=API_PORT,
            log_level="warning"
        )

    t = threading.Thread(target=run, daemon=True)
    t.start()
    time.sleep(5)
    return True


start_fastapi()

# On Streamlit Cloud, show the dashboard via st.components.v1.html
# The HTML itself calls window.location.origin for API
HTML_FILE = Path(__file__).parent / "frontend" / "windsite_v4.html"

if not HTML_FILE.exists():
    st.error("HTML not found: " + str(HTML_FILE))
    st.stop()

with open(str(HTML_FILE), "r", encoding="utf-8", errors="replace") as f:
    html_content = f.read()

# Inject API base URL detection
html_content = html_content.replace(
    "<script>",
    """<script>
window.WINDSITE_API_BASE = (
    window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : window.location.origin
);
""",
    1
)

st.components.v1.html(html_content, height=960, scrolling=False)