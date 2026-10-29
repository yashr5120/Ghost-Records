"""Settings Page - Configure local Ollama connection, verify Gemma model, and view diagnostics."""

import streamlit as st

from ghost_records.ai.ollama_client import get_ai_client
from ghost_records.config import CONFIG
from ghost_records.database import init_db
from ghost_records.ui_utils import render_header, render_sidebar

st.set_page_config(
    page_title="Settings | Ghost Records",
    page_icon="👻",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()
render_sidebar()
render_header("System Settings & Local AI Diagnostics", "Configure local inference parameters and inspect security boundaries.")

# --- SECTION 1: Local AI Configuration ---
st.subheader("🤖 Local AI Engine (Ollama)")
st.caption(
    "Ghost Records uses local open-weight LLMs via Ollama. No data is sent over the internet or to external cloud APIs."
)

col_cfg1, col_cfg2 = st.columns(2)

with col_cfg1:
    endpoint_input = st.text_input(
        "Local Ollama Endpoint",
        value=st.session_state.get("custom_ollama_endpoint", CONFIG.ollama_base_url),
        help="Default is http://localhost:11434",
    )
    if endpoint_input != CONFIG.ollama_base_url:
        st.session_state["custom_ollama_endpoint"] = endpoint_input

with col_cfg2:
    # Check connection first to discover available models
    client_probe = get_ai_client()
    probe_status = client_probe.check_connection()
    available_models = probe_status.get("available_models", [])

    model_options = available_models if available_models else ["gemma4:e4b", "gemma4:e2b"]
    default_model = (
        CONFIG.ollama_model
        if CONFIG.ollama_model in model_options
        else (model_options[0] if model_options else "gemma4:e4b")
    )

    selected_model = st.selectbox(
        "AI Model",
        model_options,
        index=model_options.index(default_model) if default_model in model_options else 0,
        help="Select an installed open-weight model for local forensic explanations.",
    )

# Connection Status Panel
client = get_ai_client(model=selected_model)
status = client.check_connection()

st.markdown("<br>", unsafe_allow_html=True)
c_stat1, c_stat2, c_stat3 = st.columns(3)

with c_stat1:
    if status["online"]:
        st.success(f"● Ollama Daemon: Online\n\nEndpoint: {status['endpoint']}")
    else:
        st.error(f"○ Ollama Daemon: Offline\n\n{status['error']}")

with c_stat2:
    if status["model_installed"]:
        st.success(f"● Model '{selected_model}': Installed")
    else:
        st.warning(f"▲ Model '{selected_model}': Not Found Locally")

with c_stat3:
    st.info(f"Available Models ({len(status['available_models'])}):\n\n{', '.join(status['available_models']) or 'None'}")

# Live Test Local AI Action
st.markdown("<br>", unsafe_allow_html=True)
if st.button("🧪 Test Local AI Inference", type="primary"):
    with st.spinner(f"Sending test prompt to local {selected_model}..."):
        test_result = client.test_inference("In one sentence, why is database referential integrity important?")
        if test_result["success"]:
            st.success(
                f"✅ Local Inference Succeeded in {test_result['latency_seconds']} seconds!\n\n"
                f"**Response:** {test_result['response']}"
            )
        else:
            st.error(f"❌ Inference Test Failed: {test_result['error']}")

# Setup Instructions for Offline / First Time Use
with st.expander("ℹ️ How to Set Up Ollama & Gemma Locally"):
    st.markdown(
        """
        1. **Install Ollama**: Download from [ollama.com](https://ollama.com) and install for your OS.
        2. **Start Daemon**: Ensure `ollama serve` is running.
        3. **Run or Reuse Model**:
           ```bash
           # Check available models
           ollama list

           # Run with installed model (e.g. gemma4:e4b)
           ollama run gemma4:e4b
           ```
        4. **Zero Cloud Telemetry**: Ghost Records makes requests strictly to `http://localhost:11434`.
        """
    )

# --- SECTION 2: Storage & Privacy Invariants ---
st.markdown("---")
st.subheader("🔒 Privacy Architecture & Storage Paths")

c_path1, c_path2 = st.columns(2)
with c_path1:
    st.markdown(f"**Data Directory:** `{CONFIG.data_dir}`")
    st.markdown(f"**Metadata SQLite DB:** `{CONFIG.metadata_db_path}`")
    st.markdown(f"**Uploads Directory:** `{CONFIG.uploads_dir}`")
with c_path2:
    st.markdown(f"**Derived Copies Directory:** `{CONFIG.derived_dir}`")
    st.markdown(f"**Reports Directory:** `{CONFIG.reports_dir}`")
    st.markdown(f"**Max Upload Size:** `{CONFIG.max_upload_size_mb} MB`")

st.markdown("<br>", unsafe_allow_html=True)
st.markdown(
    """
    <div style="background: rgba(63, 185, 80, 0.08); border: 1px solid rgba(63, 185, 80, 0.3); border-radius: 6px; padding: 14px;">
        <div style="font-size: 13px; font-weight: 700; color: #3fb950;">PRIVACY & LOCAL-FIRST GUARANTEE</div>
        <div style="font-size: 12px; color: #c9d1d9; margin-top: 4px;">
            Ghost Records is built for confidential databases.
            Audit scans are executed 100% deterministically in local memory.
            AI inference occurs entirely on your hardware via local Ollama.
            No cloud APIs, no external telemetry, and no raw dataset logging.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
