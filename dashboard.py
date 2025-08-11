# Dashboard.py — professional landing

import streamlit as st

st.set_page_config(page_title="Cordova Publication — Dashboard", page_icon="🗓️", layout="wide")

# Hide Streamlit/GitHub chrome + tighten spacing
st.markdown("""
<style>
#MainMenu, footer, header {visibility: hidden;}
[data-testid="stDecoration"] {display: none;}
.block-container {padding-top: 1.5rem; padding-bottom: 1.5rem; max-width: 1080px;}
button[kind="primary"] {font-weight: 600;}
.card {border:1px solid rgba(0,0,0,.08); border-radius:16px; padding:22px;}
.card:hover {box-shadow:0 4px 20px rgba(0,0,0,.06);}
.h-sub {color:#6b7280; margin-bottom:1.25rem;}
</style>
""", unsafe_allow_html=True)

# Header
st.markdown("<h1 style='margin:0'>Cordova Publication</h1>", unsafe_allow_html=True)
st.markdown("<div class='h-sub'>Live Class and Product Training Booking Portal</div>", unsafe_allow_html=True)

# Cards
col1, col2 = st.columns(2, gap="large")

with col1:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("📚 Salesperson Dashboard")
    st.caption("Book sessions and view your bookings.")
    if st.button("Open Salesperson Dashboard ➜", use_container_width=True):
        if hasattr(st, "switch_page"):
            st.switch_page("pages/1_Salesperson.py")
    st.markdown("</div>", unsafe_allow_html=True)

with col2:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.subheader("🛠️ Admin Dashboard")
    st.caption("Manage bookings and teacher availability.")
    if st.button("Open Admin Dashboard ➜", use_container_width=True):
        if hasattr(st, "switch_page"):
            st.switch_page("pages/2_Admin.py")
    st.markdown("</div>", unsafe_allow_html=True)

# Footer (copyright only)
st.markdown("<hr style='opacity:.15; margin-top: 24px;'>", unsafe_allow_html=True)
st.markdown(
    "<div style='text-align:center; color:#9aa0a6; font-size:12px;'>"
    "© Made by Uttam for Cordova Publication 2025. All rights reserved."
    "</div>",
    unsafe_allow_html=True,
)

