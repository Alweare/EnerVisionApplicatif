import altair as alt
import pandas as pd
import streamlit as st

from formatting import (
    format_date_fr,
    format_number,
    format_time_of_day,
    site_option_label,
)
from services.prediction_service import get_site_prediction
from services.site_service import get_sites

HISTORIQUE_COLOR = "#4c78a8"
PROJECTION_COLOR = "#f58518"

st.header("Prédictions")

sites = get_sites()

if not sites:
    st.warning("Aucun site associé à votre compte.")
    st.stop()

sites_by_id = {s["site_id"]: s for s in sites}
selected_site_id = st.selectbox(
    "Site",
    options=list(sites_by_id),
    format_func=lambda site_id: site_option_label(sites_by_id[site_id]),
)

data = get_site_prediction(selected_site_id)

if data is None:
    st.info("Aucune prédiction disponible pour ce site.")
    st.stop()

prediction = data["prediction"]
model = data.get("model")
history = data.get("history", [])


# --- Pic prévu ---------------------------------------------------------
with st.container(border=True):
    st.caption("Pic prévu")
    value_col, when_col = st.columns([1, 2], vertical_alignment="center")
    value_col.markdown(
        f"## {format_number(prediction.get('predicted_consumption_kw'), 'kW')}"
    )
    when_col.caption(f"estimé à {format_time_of_day(prediction.get('predicted_for'))}")


# --- Historique + projection ----------------------------------------
st.subheader("Historique + projection")

if history:
    hist_df = (
        pd.DataFrame(history)[["measurement_date", "consumption_kw"]]
        .dropna()
        .assign(measurement_date=lambda df: pd.to_datetime(df["measurement_date"]))
    )
    hist_layer = (
        alt.Chart(hist_df)
        .mark_line(color=HISTORIQUE_COLOR)
        .encode(
            x=alt.X("measurement_date:T", title=None),
            y=alt.Y("consumption_kw:Q", title="kW"),
            tooltip=["measurement_date:T", "consumption_kw:Q"],
        )
    )

    pred_df = pd.DataFrame(
        [
            {
                "predicted_for": pd.to_datetime(prediction["predicted_for"]),
                "predicted_consumption_kw": prediction.get("predicted_consumption_kw"),
            }
        ]
    )
    pred_layer = (
        alt.Chart(pred_df)
        .mark_point(color=PROJECTION_COLOR, size=140, filled=True)
        .encode(
            x="predicted_for:T",
            y="predicted_consumption_kw:Q",
            tooltip=["predicted_for:T", "predicted_consumption_kw:Q"],
        )
    )

    st.altair_chart(hist_layer + pred_layer, use_container_width=True)
    st.caption(
        f":blue[—] historique  ·  :orange[●] projection (pic prévu)"
    )
else:
    st.info("Pas d'historique de mesures pour tracer la courbe.")


# --- Modèle ----------------------------------------------------------
if model:
    st.caption(
        f"Modèle entraîné le {format_date_fr(model.get('trained_at'))} — "
        f"{model.get('algorithm') or '—'}"
    )
