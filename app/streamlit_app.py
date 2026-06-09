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
API_BASE = "http://localhost:" + str(API_PORT)
HTML_FILE = Path(__file__).parent / "frontend" / "windsite_v4.html"


@st.cache_resource
def start_fastapi():
    from app.main import app as fastapi_app
    from fastapi.responses import HTMLResponse

    html_path = Path(__file__).parent / "frontend" / "windsite_v4.html"
    with open(str(html_path), "r", encoding="utf-8", errors="replace") as f:
        html_content = f.read()
    html_content = html_content.replace(
        "<script>",
        '<script>window.WINDSITE_API_BASE="http://localhost:' + str(API_PORT) + '";',
        1
    )

    @fastapi_app.get("/dashboard", response_class=HTMLResponse)
    def dashboard():
        return HTMLResponse(content=html_content)

    def run():
        uvicorn.run(fastapi_app, host="0.0.0.0", port=API_PORT, log_level="warning")

    t = threading.Thread(target=run, daemon=True)
    t.start()
    time.sleep(5)
    return True


with st.spinner("Starting WindSite backend..."):
    start_fastapi()

st.iframe(
    src=API_BASE + "/dashboard",
    height=960
)