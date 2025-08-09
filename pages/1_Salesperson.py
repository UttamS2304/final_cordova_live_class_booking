import streamlit as st

st.set_page_config(page_title="Salesperson Portal", page_icon="🧑‍💼", layout="wide")

# --- simple session login ---
def salesperson_logged_in():
    return st.session_state.get("role") == "sales" and st.session_state.get("salesperson_email")

def salesperson_login_form():
    st.title("Salesperson Login")
    with st.form("sp_login", clear_on_submit=False):
        name  = st.text_input("Your Name")
        phone = st.text_input("Your Phone Number")
        email = st.text_input("Your Email")
        ok = st.form_submit_button("Login")
    if ok:
        if not name or not phone or not email:
            st.error("Please fill name, phone and email.")
        else:
            st.session_state["role"] = "sales"
            st.session_state["salesperson_name"] = name
            st.session_state["salesperson_number"] = phone
            st.session_state["salesperson_email"] = email
            st.success(f"Welcome, {name}!")
            st.rerun()

if not salesperson_logged_in():
    salesperson_login_form()
    st.stop()

with st.sidebar:
    st.caption(f"Logged in as: {st.session_state.get('salesperson_name')}")
    if st.button("Logout", use_container_width=True):
        st.session_state.clear()
        st.success("Logged out.")
        st.rerun()

st.title("Salesperson Portal")
st.info("Login works. Next step we'll add the booking form + My Bookings table.")
