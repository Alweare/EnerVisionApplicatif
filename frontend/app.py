import streamlit as st

st.set_page_config(page_title="EnerVision", page_icon="⚡", layout="wide")
st.title("EnerVision — Dashboard")

dashboard_page = st.Page("pages/Dashboard.py", title="Dashboard", default=True)
alertes_page = st.Page("pages/Alertes.py", title="Alertes")

pg = st.navigation([dashboard_page, alertes_page])
pg.run()