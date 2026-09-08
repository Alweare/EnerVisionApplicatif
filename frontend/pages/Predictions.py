import altair as alt
import pandas as pd
import streamlit as st

from formatting import (
    format_date_fr,
    format_day_time,
    format_number,
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


@st.fragment(run_every="60s")
def show_prediction(site_id: str) -> None:
    data = get_site_prediction(site_id)

    if data is None:
        st.info("Aucune prédiction disponible pour ce site.")
        return

    prediction = data["prediction"]
    points = data.get("points", [])
    model = data.get("model")
    history = data.get("history", [])

    # --- Prochain pic prévu ------------------------------------------
    with st.container(border=True):
        st.caption("Prochain pic prévu")
        value_col, when_col = st.columns([1, 2], vertical_alignment="center")
        value_col.markdown(
            f"## {format_number(prediction.get('predicted_consumption_kw'), 'kW')}"
        )
        when_col.caption(
            f"estimé le {format_day_time(prediction.get('predicted_for'))}"
        )

    # --- Historique + projection horaire ---------------------------
    st.subheader("Historique + projection")

    frames = []
    if history:
        hist_df = pd.DataFrame(history)[["measurement_date", "consumption_kw"]].dropna()
        hist_df = hist_df.rename(
            columns={"measurement_date": "ts", "consumption_kw": "kw"}
        )
        hist_df["serie"] = "historique"
        frames.append(hist_df)
    if points:
        proj_df = pd.DataFrame(points).rename(
            columns={"predicted_for": "ts", "predicted_consumption_kw": "kw"}
        )
        proj_df["serie"] = "projection"
        frames.append(proj_df[["ts", "kw", "serie"]])

    if frames:
        df = pd.concat(frames, ignore_index=True)
        # `history` a des microsecondes, `points` non -> format ISO8601 mixte.
        df["ts"] = pd.to_datetime(df["ts"], format="ISO8601")
        df = df.sort_values("ts")

        try:
            chart = (
                alt.Chart(df)
                .mark_line()
                .encode(
                    x=alt.X(
                        "ts:T",
                        title=None,
                        axis=alt.Axis(
                            tickCount="hour",  # une graduation par heure
                            format="%Hh",
                            labelAngle=-45,
                        ),
                    ),
                    y=alt.Y("kw:Q", title="kW"),
                    color=alt.Color(
                        "serie:N",
                        scale=alt.Scale(
                            domain=["historique", "projection"],
                            range=[HISTORIQUE_COLOR, PROJECTION_COLOR],
                        ),
                        legend=alt.Legend(title=None, orient="top"),
                    ),
                    tooltip=["ts:T", "kw:Q", "serie:N"],
                )
                .properties(height=340)
            )
            st.altair_chart(chart, use_container_width=True)
        except Exception:  # noqa: BLE001 - repli si le rendu Altair échoue
            wide = df.pivot_table(index="ts", columns="serie", values="kw")
            st.line_chart(wide, color=[HISTORIQUE_COLOR, PROJECTION_COLOR])
    else:
        st.info("Pas de données à tracer.")

    # --- Modèle ----------------------------------------------------
    if model:
        st.caption(
            f"Modèle entraîné le {format_date_fr(model.get('trained_at'))} — "
            f"{model.get('algorithm') or '—'}"
        )


show_prediction(selected_site_id)
