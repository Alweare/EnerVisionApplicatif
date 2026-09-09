import altair as alt
import pandas as pd
import streamlit as st

from formatting import (
    format_day_time,
    format_number,
    site_option_label,
)
from services.prediction_service import get_site_prediction
from services.site_service import get_sites


HISTORIQUE_COLOR = "#4c78a8"
PROJECTION_COLOR = "#f58518"

# 24 heures d'historique
HISTORY_HOURS = 24

# 48 heures de prévision maximum
FORECAST_HOURS = 48

# Un label toutes les 6 heures sur l'axe X
X_AXIS_INTERVAL_HOURS = 6


st.header("Prédictions")

sites = get_sites()

if not sites:
    st.warning("Aucun site associé à votre compte.")
    st.stop()

sites_by_id = {s["site_id"]: s for s in sites}

selected_site_id = st.selectbox(
    "Site",
    options=list(sites_by_id),
    format_func=lambda site_id: site_option_label(
        sites_by_id[site_id]
    ),
)


@st.fragment(run_every="60s")
def show_prediction(site_id: str) -> None:
    data = get_site_prediction(
        site_id,
        history_hours=HISTORY_HOURS,
    )

    if data is None:
        st.info("Aucune prédiction disponible pour ce site.")
        return

    prediction = data["prediction"]
    points = data.get("points", [])
    history = data.get("history", [])

    # ---------------------------------------------------------
    # Prochain pic prévu
    # ---------------------------------------------------------

    with st.container(border=True):
        st.caption("Prochain pic prévu")

        value_col, when_col = st.columns(
            [1, 2],
            vertical_alignment="center",
        )

        value_col.markdown(
            f"## {format_number(prediction.get('predicted_consumption_kw'), 'kW')}"
        )

        when_col.caption(
            f"estimé le {format_day_time(prediction.get('predicted_for'))}"
        )

    # ---------------------------------------------------------
    # Graphique historique + projection
    # ---------------------------------------------------------

    st.subheader("Consommation horaire — mesuré et prévu")

    hist_df = None
    frames = []

    # ---------------------------------------------------------
    # Historique
    # ---------------------------------------------------------

    if history:
        hist_df = pd.DataFrame(history).rename(
            columns={
                "measured_at": "ts",
                "consumption_kw": "kw",
            }
        )

        hist_df["ts"] = pd.to_datetime(
            hist_df["ts"],
            format="ISO8601",
        )

        hist_df["serie"] = "historique"

        frames.append(
            hist_df[
                [
                    "ts",
                    "kw",
                    "serie",
                ]
            ]
        )

    # ---------------------------------------------------------
    # Projection
    # ---------------------------------------------------------

    if points:
        proj_df = pd.DataFrame(points).rename(
            columns={
                "predicted_for": "ts",
                "predicted_consumption_kw": "kw",
            }
        )

        proj_df["ts"] = pd.to_datetime(
            proj_df["ts"],
            format="ISO8601",
        )

        proj_df["serie"] = "projection"

        # Limite l'affichage à 48 heures de projection
        if not proj_df.empty:
            forecast_start = proj_df["ts"].min()

            forecast_end = (
                forecast_start
                + pd.Timedelta(hours=FORECAST_HOURS)
            )

            proj_df = proj_df[
                proj_df["ts"] <= forecast_end
            ]

        # Relie la dernière mesure historique
        # au premier point de projection
        if hist_df is not None and not hist_df.empty:
            bridge = hist_df.iloc[[-1]].copy()
            bridge["serie"] = "projection"

            proj_df = pd.concat(
                [
                    bridge[
                        [
                            "ts",
                            "kw",
                            "serie",
                        ]
                    ],
                    proj_df[
                        [
                            "ts",
                            "kw",
                            "serie",
                        ]
                    ],
                ],
                ignore_index=True,
            )

        frames.append(
            proj_df[
                [
                    "ts",
                    "kw",
                    "serie",
                ]
            ]
        )

    # ---------------------------------------------------------
    # Construction du graphique
    # ---------------------------------------------------------

    if frames:
        df = pd.concat(
            frames,
            ignore_index=True,
        ).sort_values("ts")

        # Un repère toutes les 6 heures
        hour_ticks = pd.date_range(
            start=df["ts"].min().floor(
                f"{X_AXIS_INTERVAL_HOURS}h"
            ),
            end=df["ts"].max().ceil(
                f"{X_AXIS_INTERVAL_HOURS}h"
            ),
            freq=f"{X_AXIS_INTERVAL_HOURS}h",
        )

        try:
            chart = (
                alt.Chart(df)
                .mark_line(
                    strokeWidth=2,
                )
                .encode(
                    x=alt.X(
                        "ts:T",
                        title=None,
                        axis=alt.Axis(
                            values=list(hour_ticks),
                            format="%d/%m %Hh",
                            labelAngle=-45,
                            labelOverlap=True,
                            labelPadding=8,
                        ),
                    ),
                    y=alt.Y(
                        "kw:Q",
                        title="Consommation (kW)",
                        scale=alt.Scale(
                            zero=False,
                        ),
                    ),
                    color=alt.Color(
                        "serie:N",
                        scale=alt.Scale(
                            domain=[
                                "historique",
                                "projection",
                            ],
                            range=[
                                HISTORIQUE_COLOR,
                                PROJECTION_COLOR,
                            ],
                        ),
                        legend=alt.Legend(
                            title=None,
                            orient="top",
                        ),
                    ),
                    tooltip=[
                        alt.Tooltip(
                            "ts:T",
                            title="Date",
                            format="%d/%m/%Y",
                        ),
                        alt.Tooltip(
                            "ts:T",
                            title="Heure",
                            format="%H:%M",
                        ),
                        alt.Tooltip(
                            "kw:Q",
                            title="kW",
                            format=".1f",
                        ),
                        alt.Tooltip(
                            "serie:N",
                            title="Série",
                        ),
                    ],
                )
                .properties(
                    height=340,
                )
                .interactive()
            )

            st.altair_chart(
                chart,
                use_container_width=True,
            )

        except Exception:
            wide = df.pivot_table(
                index="ts",
                columns="serie",
                values="kw",
            )

            st.line_chart(
                wide,
                color=[
                    HISTORIQUE_COLOR,
                    PROJECTION_COLOR,
                ],
            )

    else:
        st.info("Pas de données à tracer.")


show_prediction(selected_site_id)