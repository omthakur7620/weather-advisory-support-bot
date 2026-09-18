from __future__ import annotations

import sys
import uuid
from pathlib import Path

# ------------------------------------------------------------
# Make project root importable when Streamlit runs this file.
# ------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from backend.app.runner import WeatherAdvisoryRunner


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Weather Advisory",
    page_icon="🌦️",
    layout="centered",
    initial_sidebar_state="collapsed",
)


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }

.stApp {
    background:
        radial-gradient(circle at 8% 5%, rgba(96,165,250,0.14), transparent 30%),
        radial-gradient(circle at 92% 8%, rgba(52,211,153,0.12), transparent 28%),
        linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
}

.block-container { max-width: 860px; padding-top: 1.6rem; padding-bottom: 2.5rem; }

#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }

/* ---------- HEADER ---------- */
.app-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 0.35rem 0 1.6rem 0;
    border-bottom: 1px solid rgba(148,163,184,0.18);
    margin-bottom: 1.4rem;
}
.brand { display: flex; align-items: center; gap: 13px; }
.brand-logo {
    width: 46px; height: 46px; border-radius: 14px;
    display: flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg, #dbeafe, #dcfce7);
    border: 1px solid rgba(59,130,246,0.15);
    font-size: 23px;
    box-shadow: 0 6px 20px rgba(15,23,42,0.08);
}
.brand-name { color: #0f2942; font-size: 19px; font-weight: 800; line-height: 1.25; letter-spacing: -0.3px; }
.brand-caption { color: #7b93ab; font-size: 13px; font-weight: 500; margin-top: 2px; }
.live-pill {
    display: flex; align-items: center; gap: 7px;
    padding: 7px 13px; border-radius: 999px;
    background: rgba(255,255,255,0.9); border: 1px solid #e2e8f0;
    color: #486581; font-size: 12.5px; font-weight: 600;
    box-shadow: 0 2px 8px rgba(15,23,42,0.04);
}
.live-dot {
    width: 7px; height: 7px; border-radius: 50%; background: #22c55e;
    box-shadow: 0 0 0 4px rgba(34,197,94,0.14);
    animation: pulse 2s ease-in-out infinite;
}

/* ---------- WELCOME ---------- */
.welcome { text-align: center; padding: 3rem 1rem 2.4rem; animation: welcomeIn 0.5s ease-out; }
.welcome-logo {
    width: 74px; height: 74px; margin: 0 auto 1.3rem;
    display: flex; align-items: center; justify-content: center;
    border-radius: 22px;
    background: linear-gradient(145deg, #e0f2fe, #ecfdf5);
    border: 1px solid rgba(59,130,246,0.12);
    font-size: 35px;
    box-shadow: 0 14px 32px rgba(15,23,42,0.09);
}
.welcome-title { color: #0f2942; font-size: 30px; font-weight: 800; letter-spacing: -0.7px; margin-bottom: 0.6rem; }
.welcome-description { max-width: 540px; margin: 0 auto; color: #587187; font-size: 15.5px; line-height: 1.75; }

/* ---------- CHAT ---------- */
[data-testid="stChatMessage"] {
    animation: messageIn 0.28s ease-out;
    border-radius: 16px !important;
    padding: 0.9rem 1.1rem !important;
    margin-bottom: 0.35rem;
    border: 1px solid rgba(226,232,240,0.7);
}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] { color: #1e2f42; font-size: 15.5px; line-height: 1.75; }
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p { margin-bottom: 0.5rem; }
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] li { font-size: 15.5px; line-height: 1.7; }
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) { background: linear-gradient(135deg, #eff6ff, #f0fdf9); }
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) { background: rgba(255,255,255,0.85); box-shadow: 0 4px 14px rgba(15,23,42,0.04); }

/* ---------- POLICY TRACE ---------- */
.trace {
    margin: -0.15rem 0 1.2rem 3.3rem;
    padding: 10px 14px; border-radius: 10px;
    background: rgba(255,255,255,0.75);
    border: 1px solid #e6edf3; border-left: 3px solid #60a5fa;
    color: #7b93ab; font-size: 12.5px; line-height: 1.6;
    animation: fadeIn 0.3s ease-out;
}
.trace strong { color: #2c5282; font-weight: 700; }

/* ---------- SUGGESTIONS ---------- */
.suggestion-label {
    color: #7b93ab; font-size: 12.5px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.4px;
    margin: 0.6rem 0 0.6rem;
}

.stButton > button {
    width: 100%; min-height: 46px; border-radius: 12px;
    border: 1px solid #dce6ef; background: rgba(255,255,255,0.9);
    color: #33556e; font-size: 13.5px; font-weight: 600;
    transition: transform 0.18s ease, border-color 0.18s ease, background 0.18s ease, box-shadow 0.18s ease;
}
.stButton > button:hover {
    transform: translateY(-2px); border-color: #93c5fd; background: #ffffff;
    box-shadow: 0 8px 20px rgba(15,23,42,0.08); color: #1d4ed8;
}
.stButton > button:active { transform: translateY(0); }

/* ---------- CHAT INPUT ---------- */
[data-testid="stChatInput"] { padding-top: 0.6rem; }
[data-testid="stChatInput"] > div {
    border-radius: 16px !important;
    border: 1px solid #d8e3ec !important;
    background: rgba(255,255,255,0.97) !important;
    box-shadow: 0 10px 30px rgba(15,23,42,0.08) !important;
    transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
}
[data-testid="stChatInput"] > div:focus-within {
    border-color: #7cb0e8 !important;
    box-shadow: 0 0 0 3px rgba(59,130,246,0.1), 0 10px 30px rgba(15,23,42,0.08) !important;
}
[data-testid="stChatInput"] textarea { color: #1e2f42 !important; font-size: 15px !important; }
[data-testid="stChatInput"] textarea::placeholder { color: #a6bccd !important; }

.stSpinner > div { font-size: 14px !important; color: #486581 !important; }

/* ---------- FOOTER ---------- */
.footer { text-align: center; padding-top: 1.6rem; color: #a6bccd; font-size: 11.5px; font-weight: 500; }

/* ---------- ANIMATIONS ---------- */
@keyframes welcomeIn { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: translateY(0); } }
@keyframes messageIn { from { opacity: 0; transform: translateY(7px); } to { opacity: 1; transform: translateY(0); } }
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.55; } }

/* ---------- MOBILE ---------- */
@media (max-width: 640px) {
    .block-container { padding-left: 1rem; padding-right: 1rem; }
    .welcome { padding-top: 2.2rem; }
    .welcome-title { font-size: 24px; }
    .welcome-description { font-size: 14px; }
    .brand-name { font-size: 16px; }
    .live-pill { font-size: 11px; padding: 6px 10px; }
    .trace { margin-left: 0; font-size: 11.5px; }
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] { font-size: 14.5px; }
}
</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# SESSION STATE
# ============================================================

if "runner" not in st.session_state:
    st.session_state.runner = WeatherAdvisoryRunner()

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "messages" not in st.session_state:
    st.session_state.messages = []


runner = st.session_state.runner


# ============================================================
# HEADER
# ============================================================

st.markdown(
    """
<div class="app-header">

<div class="brand">

<div class="brand-logo">🌦️</div>

<div>
<div class="brand-name">Weather Advisory</div>
<div class="brand-caption">Outdoor Safety Support Bot</div>
</div>

</div>

<div class="live-pill">
<span class="live-dot"></span>
Live weather
</div>

</div>
""",
    unsafe_allow_html=True,
)


# ============================================================
# WELCOME SCREEN
# ============================================================

if not st.session_state.messages:

    st.markdown(
        """
<div class="welcome">

<div class="welcome-logo">🌤️</div>

<div class="welcome-title">
Weather Advisory Support
</div>

<div class="welcome-description">
Ask about an outdoor activity, location, or time.
I'll check live weather and apply the relevant
safety policy before giving guidance.
</div>

</div>
""",
        unsafe_allow_html=True,
    )


# ============================================================
# CHAT HISTORY
# ============================================================

for message in st.session_state.messages:

    role = message["role"]

    avatar = "🧑" if role == "user" else "🌦️"

    with st.chat_message(
        role,
        avatar=avatar,
    ):
        st.markdown(message["content"])

    # --------------------------------------------------------
    # Show traceability information for assistant responses.
    # --------------------------------------------------------

    if role == "assistant":

        trace = message.get("trace")

        if trace and trace.get("weather"):

            weather = trace.get("weather") or {}
            weather_items = []

            if weather.get("temperature_c") is not None:
                weather_items.append(f"{weather['temperature_c']}°C")

            if weather.get("wind_speed_kmh") is not None:
                weather_items.append(f"Wind {weather['wind_speed_kmh']} km/h")

            if weather.get("precipitation_mm") is not None:
                weather_items.append(f"Rain {weather['precipitation_mm']} mm")

            if weather.get("precipitation_probability") is not None:
                weather_items.append(
                    f"Rain chance {weather['precipitation_probability']}%"
                )

            if weather.get("uv_index") is not None:
                weather_items.append(f"UV {weather['uv_index']}")

            weather_text = " · ".join(weather_items)

            if trace.get("matched"):
                policy_text = (
                    f"<strong>Policy</strong> &nbsp; "
                    f"{trace.get('sop_id', 'Unknown')}"
                    f" &nbsp;&nbsp;•&nbsp;&nbsp; "
                    f"<strong>Severity</strong> &nbsp; "
                    f"{trace.get('severity', 'Unknown')}"
                )
            else:
                policy_text = (
                    "<strong>Policy</strong> &nbsp; "
                    "No specific SOP matched this request"
                )

            st.markdown(
                f"""
<div class="trace">
{policy_text}
&nbsp;&nbsp;•&nbsp;&nbsp;
<strong>Weather</strong>
&nbsp; {weather_text}
</div>
""",
                unsafe_allow_html=True,
            )


# ============================================================
# QUICK PROMPTS
# ============================================================

if not st.session_state.messages:

    st.markdown(
        '<div class="suggestion-label">Try asking</div>',
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)

    with col1:
        cycling_clicked = st.button(
            "🚴 Cycling in Pune",
            use_container_width=True,
        )

    with col2:
        hiking_clicked = st.button(
            "🥾 Hiking today",
            use_container_width=True,
        )

    with col3:
        picnic_clicked = st.button(
            "🧺 Picnic this evening",
            use_container_width=True,
        )

else:

    cycling_clicked = False
    hiking_clicked = False
    picnic_clicked = False


# ============================================================
# CHAT INPUT
# ============================================================

prompt = st.chat_input(
    "Ask about outdoor weather safety..."
)


# Quick prompt handling.

if cycling_clicked:
    prompt = "Can I go cycling in Pune?"

elif hiking_clicked:
    prompt = "Is hiking safe today in Pune?"

elif picnic_clicked:
    prompt = "Is today evening good for a picnic in Pune?"


# ============================================================
# PROCESS MESSAGE
# ============================================================

if prompt:

    prompt = prompt.strip()

    if prompt:

        # ----------------------------------------------------
        # Add user message.
        # ----------------------------------------------------

        st.session_state.messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

        with st.chat_message(
            "user",
            avatar="🧑",
        ):
            st.markdown(prompt)

        # ----------------------------------------------------
        # Run LangGraph backend.
        # ----------------------------------------------------

        with st.chat_message(
            "assistant",
            avatar="🌦️",
        ):

            with st.spinner(
                "Checking live weather..."
            ):

                result = runner.run(
                    session_id=st.session_state.session_id,
                    user_message=prompt,
                )

            response = result.get(
                "response",
                "I couldn't process that request.",
            )

            st.markdown(response)

        # ----------------------------------------------------
        # Save assistant response and trace.
        # ----------------------------------------------------

        sop_result = result.get(
            "sop_result"
        ) or {}

        trace = {
            "matched": sop_result.get(
                "matched",
                False,
            ),
            "sop_id": sop_result.get(
                "sop_id"
            ),
            "severity": sop_result.get(
                "severity"
            ),
            "weather": result.get(
                "weather"
            ),
        }

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": response,
                "trace": trace,
            }
        )

        # Rerun so the complete conversation is rendered
        # consistently.
        st.rerun()


# ============================================================
# FOOTER
# ============================================================

st.markdown(
    """
<div class="footer">
Live weather via Open-Meteo
&nbsp; • &nbsp;
Guidance determined by configured SOPs
</div>
""",
    unsafe_allow_html=True,
)