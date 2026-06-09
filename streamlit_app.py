import streamlit as st
import threading
import uvicorn
import sys
import time
import socket
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

    html_content = html_content.replace(
        "<script>",
        "<script>window.WINDSITE_API_BASE='';",
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

st.components.v1.html(
    """
    <style>
    body { margin: 0; padding: 0; background: #050709; }
    iframe { border: none; }
    </style>
    <iframe src="/dashboard" style="width:100%;height:960px;border:none;"></iframe>
    """,
    height=960
)

