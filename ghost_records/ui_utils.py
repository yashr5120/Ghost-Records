"""UI utilities and styling for Ghost Records dark forensic investigation theme."""

import streamlit as st

from ghost_records.ai.ollama_client import get_ai_client
from ghost_records.database import init_db


def apply_custom_styles() -> None:
    """Inject custom CSS for dark forensic investigation workspace aesthetic."""
    st.markdown(
        """
        <style>
        /* Base typography & containers */
        @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }
        code, pre, .mono-font {
            font-family: 'JetBrains Mono', monospace !important;
        }

        /* Top Header & Branding */
        .ghost-header {
            display: flex;
            align-items: center;
            gap: 14px;
            padding: 16px 20px;
            background: linear-gradient(135deg, #161b22 0%, #0d1117 100%);
            border: 1px solid #30363d;
            border-radius: 10px;
            margin-bottom: 24px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }
        .ghost-logo {
            font-size: 28px;
            line-height: 1;
        }
        .ghost-title {
            margin: 0;
            font-size: 22px;
            font-weight: 700;
            color: #f0f6fc;
            letter-spacing: -0.5px;
        }
        .ghost-tagline {
            margin: 0;
            font-size: 13px;
            color: #d97706;
            font-weight: 500;
        }

        /* Metric Cards */
        .metric-card {
            background-color: #161b22;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 16px 20px;
            text-align: left;
            transition: border-color 0.2s ease;
        }
        .metric-card:hover {
            border-color: #d97706;
        }
        .metric-val {
            font-size: 28px;
            font-weight: 700;
            color: #f0f6fc;
            line-height: 1.2;
            font-family: 'JetBrains Mono', monospace;
        }
        .metric-lbl {
            font-size: 13px;
            color: #8b949e;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-top: 4px;
        }

        /* Severity Badges */
        .badge {
            display: inline-block;
            padding: 2px 10px;
            font-size: 11px;
            font-weight: 600;
            border-radius: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .badge-critical {
            background-color: rgba(248, 81, 73, 0.15);
            color: #ff7b72;
            border: 1px solid rgba(248, 81, 73, 0.4);
        }
        .badge-high {
            background-color: rgba(210, 153, 34, 0.15);
            color: #f0883e;
            border: 1px solid rgba(210, 153, 34, 0.4);
        }
        .badge-medium {
            background-color: rgba(217, 119, 6, 0.15);
            color: #f59e0b;
            border: 1px solid rgba(217, 119, 6, 0.4);
        }
        .badge-low {
            background-color: rgba(88, 166, 255, 0.15);
            color: #58a6ff;
            border: 1px solid rgba(88, 166, 255, 0.4);
        }
        .badge-info {
            background-color: rgba(139, 148, 158, 0.15);
            color: #8b949e;
            border: 1px solid rgba(139, 148, 158, 0.4);
        }
        .badge-success {
            background-color: rgba(63, 185, 80, 0.15);
            color: #3fb950;
            border: 1px solid rgba(63, 185, 80, 0.4);
        }

        /* Evidence Box */
        .evidence-box {
            background-color: #0d1117;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 12px 16px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            color: #c9d1d9;
            overflow-x: auto;
        }

        /* Forensic Card */
        .forensic-card {
            background: #161b22;
            border: 1px solid #30363d;
            border-left: 4px solid #d97706;
            border-radius: 6px;
            padding: 16px;
            margin-bottom: 16px;
        }

        /* AI Explanation Box */
        .ai-box {
            background: rgba(217, 119, 6, 0.05);
            border: 1px solid rgba(217, 119, 6, 0.3);
            border-radius: 8px;
            padding: 16px;
            margin-top: 12px;
        }

        /* Streamlit overrides */
        .stButton>button {
            border-radius: 6px;
            font-weight: 600;
        }
        div[data-testid="stSidebarNav"] {
            padding-top: 1rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar() -> None:
    """Render common sidebar with status, branding, and local model indicator."""
    init_db()

    with st.sidebar:
        st.markdown(
            """
            <div style="padding: 10px 0 16px 0; border-bottom: 1px solid #30363d;">
                <div style="font-size: 20px; font-weight: 700; color: #f0f6fc;">
                    👻 Ghost Records
                </div>
                <div style="font-size: 12px; color: #d97706; font-weight: 500;">
                    Local-First AI Data Quality Auditor
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("<br>", unsafe_allow_html=True)

        # Local AI Status Pill
        client = get_ai_client()
        status = client.check_connection()

        if status["online"]:
            if status["model_installed"]:
                st.markdown(
                    f"""
                    <div style="background: rgba(63, 185, 80, 0.1); border: 1px solid rgba(63, 185, 80, 0.4); border-radius: 6px; padding: 10px; margin-bottom: 16px;">
                        <div style="font-size: 11px; color: #3fb950; font-weight: 700; text-transform: uppercase;">● Local AI Online</div>
                        <div style="font-size: 13px; color: #f0f6fc; font-weight: 600; margin-top: 2px;">{status['configured_model']}</div>
                        <div style="font-size: 11px; color: #8b949e;">Ollama @ {status['endpoint']}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"""
                    <div style="background: rgba(210, 153, 34, 0.1); border: 1px solid rgba(210, 153, 34, 0.4); border-radius: 6px; padding: 10px; margin-bottom: 16px;">
                        <div style="font-size: 11px; color: #f0883e; font-weight: 700; text-transform: uppercase;">▲ Model Missing</div>
                        <div style="font-size: 12px; color: #f0f6fc;">Configured: {status['configured_model']}</div>
                        <div style="font-size: 11px; color: #8b949e;">Installed: {', '.join(status['available_models']) or 'None'}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.markdown(
                """
                <div style="background: rgba(248, 81, 73, 0.1); border: 1px solid rgba(248, 81, 73, 0.4); border-radius: 6px; padding: 10px; margin-bottom: 16px;">
                    <div style="font-size: 11px; color: #ff7b72; font-weight: 700; text-transform: uppercase;">○ Local AI Offline</div>
                    <div style="font-size: 12px; color: #8b949e; margin-top: 2px;">Ollama not detected. Deterministic scanning remains 100% functional.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.caption("Privacy Invariant: 100% Local Inference. Zero Cloud API Keys. Zero Telemetry.")
        st.divider()

        st.markdown(
            """
            <div style="font-size: 11px; color: #8b949e;">
                v0.1.0 • Built for Hacktoberfest<br>
                Open-Weight AI Data Forensics
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_header(title: str, subtitle: str) -> None:
    """Render consistent page header."""
    apply_custom_styles()
    st.markdown(
        f"""
        <div class="ghost-header">
            <div class="ghost-logo">👻</div>
            <div>
                <h1 class="ghost-title">{title}</h1>
                <div class="ghost-tagline">{subtitle}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
