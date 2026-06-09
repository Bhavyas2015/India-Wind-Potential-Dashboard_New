import streamlit as st
import threading
import uvicorn
import sys
import time
import asyncio
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
HTML_FILE = Path(__file__).parent / "frontend" / "windsite_v4.html"


@st.cache_resource
def start_fastapi():
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('localhost', API_PORT))
    sock.close()
    if result == 0:
        return True
    from app.main import app as fastapi_app
    from fastapi.responses import HTMLResponse

    html_path = Path(__file__).parent / "frontend" / "windsite_v4.html"
    with open(str(html_path), "r", encoding="utf-8", errors="replace") as f:
        html_content = f.read()

    app_url = st.context.headers.get("host", "localhost")
    is_cloud = "streamlit.app" in app_url or "streamlit.io" in app_url
    if is_cloud:
        api_base = "https://" + app_url.replace("8501", str(API_PORT))
    else:
        api_base = "http://localhost:" + str(API_PORT)

    html_content = html_content.replace(
        "<script>",
        '<script>window.WINDSITE_API_BASE="' + api_base + '";',
        1
    )

    @fastapi_app.get("/dashboard", response_class=HTMLResponse)
    def dashboard():
        return HTMLResponse(content=html_content)

    def run():
        uvicorn.run(fastapi_app, host="0.0.0.0", port=API_PORT, log_level="warning")

    t = threading.Thread(target=run, daemon=True)
    t.start()
    time.sleep(3)
    return True


start_fastapi()

if not HTML_FILE.exists():
    st.error("HTML not found: " + str(HTML_FILE))
    st.stop()

with open(str(HTML_FILE), "r", encoding="utf-8", errors="replace") as f:
    html_content = f.read()

app_url = st.context.headers.get("host", "localhost")
is_cloud = "streamlit.app" in app_url

if is_cloud:
    api_base = "https://" + app_url.split(":")[0] + ":8000"
else:
    api_base = "http://localhost:" + str(API_PORT)

html_content = html_content.replace(
    "<script>",
    '<script>window.WINDSITE_API_BASE="' + api_base + '";',
    1
)

st.components.v1.html(html_content, height=960, scrolling=False)
