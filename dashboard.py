# Dashboard.py — minimal professional landing

import streamlit as st

st.set_page_config(page_title="Dashboard", page_icon="🗓️", layout="wide")

# Hide Streamlit/GitHub chrome
st.markdown("""
<style>
#MainMenu, footer, header {visibility: hidden;}
[data-testid="stDecoration"] {display: none;}
/* tighten page */
.block-container {padding-top: 1.5rem; padding-bottom: 1.5rem;}
/* buttons */
button[kind="primary"] {font-weight: 600;}
</style>
""", unsafe_allow_html=True)

# Header
st.markdown(
    "<h1 style='margin:0'>CORDOVA PUBLICATIONS</h1>"
    "<div style='color:#6b7280; margin-bottom:1.25rem'>Session Booking Portal</div>",
    unsafe_allow_html=True,
)

col1, col2 = st.columns(2, gap="large")

with col1:
    with st.container(border=True):
        st.subheader("📚 Salesperson Portal", anchor=False)
        st.caption("Book sessions and view your bookings.")
        if st.button("Open Salesperson Portal ➜", use_container_width=True):
            if hasattr(st, "switch_page"):
                st.switch_page("pages/1_Salesperson.py")

with col2:
    with st.container(border=True):
        st.subheader("🛠️ Admin Dashboard", anchor=False)
        st.caption("Manage bookings and teacher availability.")
        if st.button("Open Admin Dashboard ➜", use_container_width=True):
            if hasattr(st, "switch_page"):
                st.switch_page("pages/2_Admin.py")
