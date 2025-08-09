# Dashboard.py — professional landing (pure Streamlit, fast)

import streamlit as st

st.set_page_config(page_title="Dashboard", page_icon="🗓️", layout="wide")

# Hide Streamlit chrome (menu/footer/GitHub)
st.markdown("""
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
header {visibility: hidden;}
[data-testid="stDecoration"] {display: none;}
</style>
""", unsafe_allow_html=True)

# Header
st.title("CORDOVA PUBLICATIONS")
st.caption("Live Classes & Product Training Booking Portal")

# Cards row
left, right = st.columns(2, gap="large")

with left:
    st.container(border=True)
    st.subheader("📚 Salesperson Portal")
    st.write("Book **Live Classes** or **Product Training** and view your **My Bookings**.")
    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("Go to Salesperson Portal ➜", use_container_width=True):
            if hasattr(st, "switch_page"):
                st.switch_page("pages/1_Salesperson.py")
    with c2:
        st.page_link("pages/1_Salesperson.py", label="Open Salesperson Page", icon="🧑‍💼")

with right:
    st.container(border=True)
    st.subheader("🛠️ Admin Dashboard")
    st.write("View & filter all bookings, delete sessions (with emails), and manage **Teacher Unavailability**.")
    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("Go to Admin Dashboard ➜", use_container_width=True):
            if hasattr(st, "switch_page"):
                st.switch_page("pages/2_Admin.py")
    with c2:
        st.page_link("pages/2_Admin.py", label="Open Admin Page", icon="🔐")

st.divider()
st.caption("Tip: Admin login uses the credentials stored in **Settings → Secrets**.")
st.caption("Made by Utt@m for Cordova Publications 2025")
