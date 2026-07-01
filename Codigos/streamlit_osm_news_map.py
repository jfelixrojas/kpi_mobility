#!/usr/bin/env python3
"""
Visor interactivo Streamlit para la red vial OSM y corredores extraidos
desde noticias.

Ejecutar:
    streamlit run Codigos/streamlit_osm_news_map.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT / "Data" / "Processed" / "osm_roads_san_salvador"
RESULTS_DIR = ROOT / "Results" / "News"

SEGMENTS_PATH = PROCESSED_DIR / "osm_road_segments.csv"
CATALOG_PATH = RESULTS_DIR / "osm_road_catalog.csv"
MATCHES_PATH = RESULTS_DIR / "road_text_matches.csv"

HIGHWAY_STYLES = {
    "motorway": {"color": [90, 215, 255, 235], "width": 3.1},
    "trunk": {"color": [88, 210, 255, 230], "width": 3.0},
    "primary": {"color": [128, 224, 255, 215], "width": 2.5},
    "secondary": {"color": [182, 230, 138, 195], "width": 2.0},
    "tertiary": {"color": [109, 208, 182, 165], "width": 1.45},
    "unclassified": {"color": [112, 135, 154, 105], "width": 1.1},
    "residential": {"color": [74, 111, 145, 82], "width": 0.85},
    "living_street": {"color": [64, 95, 123, 70], "width": 0.75},
    "service": {"color": [51, 71, 94, 58], "width": 0.65},
    "motorway_link": {"color": [90, 215, 255, 210], "width": 2.0},
    "trunk_link": {"color": [88, 210, 255, 210], "width": 2.0},
    "primary_link": {"color": [128, 224, 255, 190], "width": 1.7},
    "secondary_link": {"color": [182, 230, 138, 165], "width": 1.5},
    "tertiary_link": {"color": [109, 208, 182, 140], "width": 1.25},
}

MATCH_COLORS = {
    "TEXT_MATCH_ACCEPTED": [255, 207, 90, 245],
    "TEXT_MATCH_REVIEW": [255, 123, 114, 235],
    "WEAK_TEXT_MATCH_REVIEW": [195, 133, 255, 220],
}

DEFAULT_HIGHWAYS = [
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "residential",
    "living_street",
]


st.set_page_config(
    page_title="Red vial OSM + noticias",
    layout="wide",
)


def parse_path(value: str) -> list[list[float]]:
    coords = json.loads(value)
    return [[float(lon), float(lat)] for lon, lat in coords]


@st.cache_data(show_spinner=False)
def load_segments() -> pd.DataFrame:
    segments = pd.read_csv(SEGMENTS_PATH)
    segments["path"] = segments["geometry_json"].map(parse_path)
    segments["color"] = segments["highway"].map(lambda v: HIGHWAY_STYLES.get(v, {}).get("color", [100, 120, 140, 80]))
    segments["width"] = segments["highway"].map(lambda v: HIGHWAY_STYLES.get(v, {}).get("width", 0.8))
    segments["length_km"] = segments["length_m"] / 1000
    return segments.drop(columns=["geometry_json"])


@st.cache_data(show_spinner=False)
def load_catalog() -> pd.DataFrame:
    return pd.read_csv(CATALOG_PATH)


@st.cache_data(show_spinner=False)
def load_matches() -> pd.DataFrame:
    matches = pd.read_csv(MATCHES_PATH)
    matches["matched_road_key_norm"] = matches["matched_road_key_norm"].fillna("")
    return matches


def selected_match_segments(
    segments: pd.DataFrame,
    matches: pd.DataFrame,
    statuses: list[str],
    candidates: list[str],
) -> pd.DataFrame:
    selected = matches[matches["match_status"].isin(statuses)].copy()
    if candidates:
        selected = selected[selected["road_name_candidate"].isin(candidates)]
    selected = selected[selected["matched_road_key_norm"].astype(str).str.len() > 0]
    if selected.empty:
        return pd.DataFrame()

    grouped = (
        selected.groupby("matched_road_key_norm", dropna=False)
        .agg(
            news_candidates=("road_name_candidate", lambda s: "; ".join(sorted(set(map(str, s))))),
            match_statuses=("match_status", lambda s: "; ".join(sorted(set(map(str, s))))),
            news_events=("news_events", "sum"),
            text_match_score=("text_match_score", "max"),
        )
        .reset_index()
    )
    status_priority = {
        "TEXT_MATCH_ACCEPTED": 3,
        "TEXT_MATCH_REVIEW": 2,
        "WEAK_TEXT_MATCH_REVIEW": 1,
    }

    def best_status(value: str) -> str:
        statuses_found = [part.strip() for part in value.split(";")]
        return max(statuses_found, key=lambda status: status_priority.get(status, 0))

    grouped["best_match_status"] = grouped["match_statuses"].map(best_status)
    grouped["match_color"] = grouped["best_match_status"].map(lambda s: MATCH_COLORS.get(s, [255, 255, 255, 220]))
    grouped["match_width"] = grouped["best_match_status"].map(
        lambda s: 5.2 if s == "TEXT_MATCH_ACCEPTED" else 4.4 if s == "TEXT_MATCH_REVIEW" else 3.6
    )

    highlighted = segments.merge(
        grouped,
        how="inner",
        left_on="road_key_norm",
        right_on="matched_road_key_norm",
    )
    highlighted["color"] = highlighted["match_color"]
    highlighted["width"] = highlighted["match_width"]
    return highlighted


def map_view_state(segments: pd.DataFrame) -> pdk.ViewState:
    points = [point for path in segments["path"].head(5000) for point in path]
    if not points:
        return pdk.ViewState(latitude=13.6929, longitude=-89.2182, zoom=10)
    lons = [point[0] for point in points]
    lats = [point[1] for point in points]
    return pdk.ViewState(
        latitude=(min(lats) + max(lats)) / 2,
        longitude=(min(lons) + max(lons)) / 2,
        zoom=9.3,
        pitch=0,
        bearing=0,
    )


def path_layer(data: pd.DataFrame, layer_id: str, pickable: bool = True) -> pdk.Layer:
    return pdk.Layer(
        "PathLayer",
        data=data,
        id=layer_id,
        get_path="path",
        get_color="color",
        get_width="width",
        width_units="pixels",
        rounded=True,
        pickable=pickable,
        auto_highlight=True,
    )


segments = load_segments()
catalog = load_catalog()
matches = load_matches()

st.title("Red vial OSM + corredores mencionados en noticias")
st.caption(
    "Datos OSM descargados con Overpass API y enriquecidos con atributos viales. "
    "La correlacion noticia-via es textual; la validacion espacial requiere geocodificacion."
)

with st.sidebar:
    st.header("Capas")
    show_base = st.checkbox("Red vial base OSM", value=True)
    show_matches = st.checkbox("Corredores de noticias", value=True)

    highway_options = sorted(segments["highway"].dropna().unique().tolist())
    selected_highways = st.multiselect(
        "Tipos highway OSM",
        options=highway_options,
        default=[h for h in DEFAULT_HIGHWAYS if h in highway_options],
    )

    status_options = [
        "TEXT_MATCH_ACCEPTED",
        "TEXT_MATCH_REVIEW",
        "WEAK_TEXT_MATCH_REVIEW",
    ]
    selected_statuses = st.multiselect(
        "Estado del match noticia-via",
        options=status_options,
        default=["TEXT_MATCH_ACCEPTED", "TEXT_MATCH_REVIEW"],
    )

    available_candidates = (
        matches[matches["match_status"].isin(selected_statuses)]["road_name_candidate"]
        .dropna()
        .sort_values()
        .unique()
        .tolist()
    )
    selected_candidates = st.multiselect(
        "Filtrar corredores de noticias",
        options=available_candidates,
        default=[],
        placeholder="Todos",
    )

    text_filter = st.text_input("Buscar via OSM", value="")

filtered_segments = segments[segments["highway"].isin(selected_highways)].copy()
if text_filter.strip():
    query = text_filter.strip().lower()
    filtered_segments = filtered_segments[
        filtered_segments["road_key_norm"].astype(str).str.lower().str.contains(query, na=False)
        | filtered_segments["name"].astype(str).str.lower().str.contains(query, na=False)
        | filtered_segments["ref"].astype(str).str.lower().str.contains(query, na=False)
    ]

highlight_segments = (
    selected_match_segments(segments, matches, selected_statuses, selected_candidates)
    if show_matches
    else pd.DataFrame()
)

metric_cols = st.columns(5)
metric_cols[0].metric("Segmentos OSM visibles", f"{len(filtered_segments):,}")
metric_cols[1].metric("Corredores OSM", f"{len(catalog):,}")
metric_cols[2].metric("Longitud visible km", f"{filtered_segments['length_km'].sum():,.1f}")
metric_cols[3].metric("Corredores noticia visibles", f"{highlight_segments['road_key_norm'].nunique() if not highlight_segments.empty else 0:,}")
metric_cols[4].metric("Segmentos resaltados", f"{len(highlight_segments):,}")

layers = []
if show_base and not filtered_segments.empty:
    layers.append(path_layer(filtered_segments, "red-vial-base"))
if show_matches and not highlight_segments.empty:
    layers.append(path_layer(highlight_segments, "corredores-noticias"))

tooltip = {
    "html": """
    <b>{name}</b><br/>
    ref: {ref}<br/>
    highway: {highway}<br/>
    tipo: {road_type_category}<br/>
    sentido: {oneway}<br/>
    carriles: {lanes}<br/>
    velocidad: {maxspeed}<br/>
    longitud km: {length_km}<br/>
    noticia: {news_candidates}<br/>
    match: {match_statuses}
    """,
    "style": {
        "backgroundColor": "#07111c",
        "color": "#eaf8ff",
        "fontSize": "12px",
    },
}

deck = pdk.Deck(
    layers=layers,
    initial_view_state=map_view_state(segments),
    map_style=None,
    tooltip=tooltip,
)

st.pydeck_chart(deck, width="stretch", height=720)

with st.expander("Datos fuente y lectura metodologica"):
    st.markdown(
        f"""
**Fuente OSM:** `{SEGMENTS_PATH}`  
**Catalogo de corredores:** `{CATALOG_PATH}`  
**Match noticias-vias:** `{MATCHES_PATH}`

- Cada linea base es un `way` de OSM.
- Cada corredor OSM agrupa muchos `ways` con nombre o referencia normalizada.
- Los colores de la red base representan la jerarquia `highway` de OSM.
- Los corredores resaltados vienen del match textual entre noticias y el catalogo OSM.
- Este visor permite inspeccion, no sustituye la geocodificacion ni el map matching espacial evento-segmento.
"""
    )

with st.expander("Corredores de noticias"):
    visible_matches = matches[matches["match_status"].isin(selected_statuses)].copy()
    if selected_candidates:
        visible_matches = visible_matches[visible_matches["road_name_candidate"].isin(selected_candidates)]
    st.dataframe(
        visible_matches[
            [
                "road_name_candidate",
                "news_events",
                "matched_osm_name",
                "matched_refs",
                "predominant_highway",
                "predominant_road_type",
                "segment_count",
                "length_km",
                "text_match_score",
                "match_status",
            ]
        ],
        width="stretch",
        hide_index=True,
    )
