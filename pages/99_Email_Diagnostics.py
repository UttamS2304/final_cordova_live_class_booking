import streamlit as st, smtplib, ssl

st.set_page_config(page_title="Email Diagnostics", page_icon="✉️", layout="wide")
st.title("✉️ Email Diagnostics")

# Check required secrets
required = ["EMAIL_HOST","EMAIL_PORT","EMAIL_USER","EMAIL_PASS"]
missing = [k for k in required if k not in st.secrets]
if missing:
    st.error(f"Missing secrets: {', '.join(missing)}")
    st.stop()

host = st.secrets["EMAIL_HOST"]
port = int(st.secrets["EMAIL_PORT"])
user = st.secrets["EMAIL_USER"]
pwd  = st.secrets["EMAIL_PASS"]
use_tls = str(st.secrets.get("EMAIL_USE_TLS","true")).lower() == "true"

to = st.text_input("Send test to", value=st.secrets.get("ADMIN_EMAIL",""))
subject = st.text_input("Subject", "SMTP test from Streamlit")
body = st.text_area("Body", "Hello from Streamlit SMTP test.")

if st.button("Send Test Email", type="primary"):
    msg = f"Subject: {subject}\r\nFrom: {user}\r\nTo: {to}\r\n\r\n{body}"
    try:
        if use_tls:
            with smtplib.SMTP(host, port, timeout=15) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(user, pwd)
                s.sendmail(user, [to], msg)
        else:
            with smtplib.SMTP_SSL(host, port, timeout=15) as s:
                s.login(user, pwd)
                s.sendmail(user, [to], msg)
        st.success("✅ Test email sent. Check the inbox (and Spam).")
    except Exception as e:
        st.exception(e)
