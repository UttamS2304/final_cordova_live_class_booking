import streamlit as st

st.set_page_config(page_title="Admin Dashboard", page_icon="🔐", layout="wide")

# --- admin gate ---
def admin_logged_in():
    return st.session_state.get("role") == "admin"

def admin_login_form():
    st.title("Admin Login")
    with st.form("admin_login", clear_on_submit=False):
        u = st.text_input("Username", autocomplete="username")
        p = st.text_input("Password", type="password", autocomplete="current-password")
        ok = st.form_submit_button("Login")
    if ok:
        if u == st.secrets.get("ADMIN_USERNAME") and p == st.secrets.get("ADMIN_PASSWORD"):
            st.session_state["role"] = "admin"
            st.success("Logged in as Admin.")
            st.rerun()
        else:
            st.error("Invalid admin credentials.")

if not admin_logged_in():
    admin_login_form()
    st.stop()

with st.sidebar:
    if st.button("Logout", use_container_width=True):
        st.session_state.clear()
        st.success("Logged out.")
        st.rerun()

st.title("Admin Dashboard")
st.info("Admin lock works. Next we’ll add tables, delete booking, and teacher availability.")
