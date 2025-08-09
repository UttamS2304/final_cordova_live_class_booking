# streamlit_app.py — FINAL Landing (polished)

import streamlit as st

# ---------- Global page config ----------
st.set_page_config(
    page_title="Cordova Slot Booking",
    page_icon="🗓️",
    layout="wide",
)

# ---------- Hide Streamlit & GitHub UI ----------
HIDE_UI = """
<style>
/* Hide Streamlit main menu, footer, and the little GitHub decoration */
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
[data-testid="stDecoration"] {display: none;}
</style>
"""
st.markdown(HIDE_UI, unsafe_allow_html=True)

# ---------- Hero / Header ----------
st.markdown(
    """
    <div style="text-align:center; margin-top: 10px;">
        <h1 style="margin-bottom: 0;">CORDOVA PUBLICATIONS</h1>
        <p style="font-size: 18px; color: #6b7280;">
            Live Classes & Product Training Booking Portal
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.write("")  # tiny spacer

# ---------- Two-card layout ----------
left, right = st.columns(2, gap="large")

# Common card style
CARD = """
<div style="
    border-radius: 16px;
    padding: 24px;
    background: var(--secondary-bg, #f7f7f9);
    box-shadow: 0 2px 12px rgba(0,0,0,0.06);
    border: 1px solid rgba(0,0,0,0.06);
    ">
    {content}
</div>
"""

with left:
    content = """
    <h3 style="margin-top:0;">📚 Salesperson Portal</h3>
    <p style="color:#6b7280;">
        Book <strong>Live Classes</strong> or <strong>Product Training</strong> sessions and
        view your personal <em>My Bookings</em>.
    </p>
    """
    st.markdown(CARD.format(content=content), unsafe_allow_html=True)
    col_btn, col_link = st.columns([1,1])
    with col_btn:
        go_sales = st.button("Go to Salesperson Portal ➜", use_container_width=True)
    with col_link:
        st.page_link("pages/1_Salesperson.py", label="Open Salesperson Page", icon="🧑‍💼")

with right:
    content = """
    <h3 style="margin-top:0;">🛠️ Admin Dashboard</h3>
    <p style="color:#6b7280;">
        View and filter all bookings, delete sessions (with cancellation emails), and
        manage <strong>Teacher Unavailability</strong>.
    </p>
    """
    st.markdown(CARD.format(content=content), unsafe_allow_html=True)
    col_btn, col_link = st.columns([1,1])
    with col_btn:
        go_admin = st.button("Go to Admin Dashboard ➜", use_container_width=True)
    with col_link:
        st.page_link("pages/2_Admin.py", label="Open Admin Page", icon="🔐")

# ---------- Button-based navigation (uses switch_page if available) ----------
def try_switch(page_path: str):
    # Streamlit 1.25+ exposes st.switch_page; fall back to page_link if missing
    if hasattr(st, "switch_page"):
        try:
            st.switch_page(page_path)
        except Exception:
            pass

if 'go_sales' in locals() and go_sales:
    try_switch("pages/1_Salesperson.py")

if 'go_admin' in locals() and go_admin:
    try_switch("pages/2_Admin.py")

# ---------- Helpful notes ----------
st.write("")
st.markdown(
    """
    <div style="text-align:center; color:#9aa0a6; font-size: 13px; margin-top: 6px;">
      Use the left sidebar to navigate at any time.
      Admin login uses the credentials stored in <em>Settings → Secrets</em>.
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown("<hr style='opacity:.15; margin-top: 20px;'>", unsafe_allow_html=True)
st.caption("Made by Utt@m for Cordova Publications 2025")
