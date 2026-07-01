#!/usr/bin/env python3
"""
Dashboard Streamlit para incidentes.csv.

Ejecutar:
    streamlit run Codigos/streamlit_incidentes_dashboard.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "Results" / "News" / "Incidentes"
OSM_SEGMENTS_PATH = ROOT / "Data" / "Processed" / "osm_roads_san_salvador" / "osm_road_segments.csv"
OSM_DEPARTMENTS_DIR = ROOT / "Data" / "Processed" / "osm_roads_departments"
OSM_NATIONAL_SEGMENTS_PATH = ROOT / "Data" / "Processed" / "osm_roads_nacional" / "osm_road_segments.csv"

EVENTS_PATHS = [
    RESULTS_DIR / "eventos_incidentes_osm_nacional_enriched.csv",
    RESULTS_DIR / "eventos_incidentes_osm_enriched.csv",
]
EVENTS_PATH = next((path for path in EVENTS_PATHS if path.exists()), EVENTS_PATHS[0])
HEATMAP_PATH = RESULTS_DIR / "heatmap_weights_incidentes.csv"
MENTIONS_PATH = RESULTS_DIR / "base_menciones_incidentes_expandida.csv"
SNAPSHOTS_PATH = RESULTS_DIR / "base_engagement_snapshots.csv"
DAILY_PATH = RESULTS_DIR / "serie_temporal_eventos_incidentes.csv"
HOURLY_PATH = RESULTS_DIR / "serie_horaria_eventos_incidentes.csv"
ENGAGEMENT_SOURCE_PATH = RESULTS_DIR / "resumen_engagement_por_fuente_incidentes.csv"
DEPARTMENTS_PATH = RESULTS_DIR / "ranking_departamentos_incidentes.csv"
MUNICIPALITIES_PATH = RESULTS_DIR / "ranking_municipios_incidentes.csv"
CORRIDORS_PATH = RESULTS_DIR / "ranking_corredores_incidentes.csv"
CORRIDORS_NORM_PATH = RESULTS_DIR / "ranking_corredores_norm.csv"
CRITICAL_CORRIDORS_PATH = RESULTS_DIR / "analisis_corredores_criticos.csv"
SENSITIVITY_PATH = RESULTS_DIR / "sensibilidad_pesos_corredores.csv"
UNRESOLVED_SUMMARY_PATH = RESULTS_DIR / "resumen_unresolved_corridor_norm.csv"
UNRESOLVED_DETAIL_PATH = RESULTS_DIR / "analisis_unresolved_corridor_norm_detalle.csv"
EMPTY_CORRIDOR_DETAIL_PATH = RESULTS_DIR / "analisis_corridor_norm_vacio_detalle.csv"
UNNAMED_OSM_DETAIL_PATH = RESULTS_DIR / "investigacion_osm_sin_nombre_ref_detalle.csv"
UNNAMED_OSM_CANDIDATES_PATH = RESULTS_DIR / "investigacion_osm_sin_nombre_ref_candidatos.csv"
INTEGRITY_PATH = RESULTS_DIR / "diagnostico_integridad_incidentes.csv"
COORDS_PATH = RESULTS_DIR / "diagnostico_coordenadas_incidentes.csv"
FIG_EXECUTIVE_PATH = RESULTS_DIR / "fig_resumen_ejecutivo_incidentes.png"
FIG_CORRIDORS_PATH = RESULTS_DIR / "fig_corredores_sensibilidad_incidentes.png"
FIG_MAP_PATH = RESULTS_DIR / "fig_mapa_ejecutivo_incidentes.png"
MAP_CHART_HEIGHT_PX = 760


DEPARTMENT_SLUGS = {
    "AHUACHAPÁN": "ahuachapan",
    "CABAÑAS": "cabanas",
    "CHALATENANGO": "chalatenango",
    "CUSCATLÁN": "cuscatlan",
    "LA LIBERTAD": "la_libertad",
    "LA PAZ": "la_paz",
    "LA UNIÓN": "la_union",
    "MORAZÁN": "morazan",
    "SAN MIGUEL": "san_miguel",
    "SAN SALVADOR": "san_salvador",
    "SAN VICENTE": "san_vicente",
    "SANTA ANA": "santa_ana",
    "SONSONATE": "sonsonate",
    "USULUTÁN": "usulutan",
}


HIGHWAY_STYLES = {
    "motorway": {"color": [92, 213, 255, 230], "width": 3.1},
    "trunk": {"color": [94, 207, 255, 220], "width": 2.9},
    "primary": {"color": [116, 232, 205, 210], "width": 2.45},
    "secondary": {"color": [224, 224, 125, 195], "width": 2.0},
    "tertiary": {"color": [154, 205, 132, 170], "width": 1.55},
    "unclassified": {"color": [126, 161, 178, 125], "width": 1.1},
    "residential": {"color": [94, 143, 176, 115], "width": 0.95},
    "living_street": {"color": [86, 123, 150, 100], "width": 0.85},
    "service": {"color": [72, 100, 128, 85], "width": 0.72},
    "motorway_link": {"color": [92, 213, 255, 190], "width": 1.9},
    "trunk_link": {"color": [94, 207, 255, 190], "width": 1.9},
    "primary_link": {"color": [116, 232, 205, 175], "width": 1.55},
    "secondary_link": {"color": [224, 224, 125, 155], "width": 1.35},
    "tertiary_link": {"color": [154, 205, 132, 140], "width": 1.15},
}

DEFAULT_OSM_HIGHWAYS = [
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "tertiary",
    "unclassified",
    "residential",
    "living_street",
    "service",
    "motorway_link",
    "trunk_link",
    "primary_link",
    "secondary_link",
    "tertiary_link",
]

DEFAULT_MAJOR_HIGHWAYS = [
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "motorway_link",
    "trunk_link",
    "primary_link",
    "secondary_link",
]

POINT_COLORS = {
    "VALID_POINT": [49, 132, 206, 210],
    "VALID_POINT_REPEATED_COORDINATE": [245, 173, 85, 225],
    "MISSING_POINT": [140, 140, 140, 140],
    "OUTSIDE_EL_SALVADOR_BBOX": [218, 75, 75, 240],
    "LOW_GEO_CONFIDENCE_POINT": [188, 137, 211, 220],
}

SEVERITY_COLORS = {
    "FATALITY_REPORTED": [220, 38, 38, 235],
    "INJURY_REPORTED": [245, 158, 11, 225],
    "MATERIAL_DAMAGE_ONLY": [14, 165, 233, 210],
    "TRAFFIC_ACCIDENT_UNSPECIFIED": [37, 99, 235, 210],
    "ROAD_AFFECTATION": [22, 163, 74, 210],
    "OTHER_LOW_INFORMATION": [148, 163, 184, 190],
}

OSM_STATUS_COLORS = {
    "SPATIAL_OSM_HIGH": [34, 197, 94, 220],
    "SPATIAL_OSM_MEDIUM": [132, 204, 22, 220],
    "SPATIAL_OSM_LOW_REVIEW": [245, 158, 11, 225],
    "SPATIAL_OSM_DISTANCE_CONFLICT": [220, 38, 38, 235],
    "NO_COORDINATE_FOR_OSM": [148, 163, 184, 170],
    "NO_NEAR_OSM_SEGMENT": [249, 115, 22, 225],
    "INVALID_POINT_FOR_OSM": [190, 18, 60, 235],
}

RESOLUTION_COLORS = {
    "COMPATIBLE": [34, 197, 94, 220],
    "LOCAL_NAME_WITHIN_CORRIDOR": [20, 184, 166, 220],
    "INTERSECTION_ACCEPTED": [59, 130, 246, 220],
    "REVIEW_COORDINATE_OR_NAME": [245, 158, 11, 230],
    "UNRESOLVED": [220, 38, 38, 230],
}

BASEMAP_STYLES = {
    "Claro con etiquetas": "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
    "Oscuro con etiquetas": "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
    "Calles con etiquetas": "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json",
    "Sin mapa base": None,
}

HEATMAP_CONFIGS = {
    "eventos": {
        "title": "Heat eventos",
        "weight_col": "heat_weight_eventos",
        "unit": "eventos",
        "meaning": "concentracion espacial de eventos",
        "color_range": [[29, 78, 137, 25], [70, 140, 190, 85], [111, 185, 214, 145], [238, 245, 180, 205]],
    },
    "menciones": {
        "title": "Heat menciones",
        "weight_col": "heat_weight_menciones",
        "unit": "menciones",
        "meaning": "concentracion espacial de publicaciones asociadas",
        "color_range": [[44, 92, 66, 25], [81, 145, 98, 95], [156, 190, 110, 155], [244, 201, 93, 215]],
    },
    "impacto": {
        "title": "Heat impacto",
        "weight_col": "heat_weight_impacto_social",
        "unit": "puntos",
        "meaning": "concentracion espacial del impacto social ponderado",
        "color_range": [[82, 34, 59, 35], [154, 57, 78, 105], [222, 116, 83, 175], [255, 217, 102, 235]],
    },
}

SEVERITY_LABELS = {
    "FATALITY_REPORTED": "Fallecido reportado",
    "INJURY_REPORTED": "Lesionados reportados",
    "MATERIAL_DAMAGE_ONLY": "Danos materiales",
    "TRAFFIC_ACCIDENT_UNSPECIFIED": "Accidente sin detalle",
    "ROAD_AFFECTATION": "Afectacion vial",
    "OTHER_LOW_INFORMATION": "Baja informacion",
}

COORD_STATUS_LABELS = {
    "VALID_POINT": "Punto valido",
    "VALID_POINT_REPEATED_COORDINATE": "Punto valido repetido",
    "MISSING_POINT": "Sin coordenada",
    "OUTSIDE_EL_SALVADOR_BBOX": "Fuera de El Salvador",
    "LOW_GEO_CONFIDENCE_POINT": "Baja confianza geografica",
}

OSM_STATUS_LABELS = {
    "SPATIAL_OSM_HIGH": "Match OSM alto",
    "SPATIAL_OSM_MEDIUM": "Match OSM medio",
    "SPATIAL_OSM_LOW_REVIEW": "Match OSM bajo/revisar",
    "SPATIAL_OSM_DISTANCE_CONFLICT": "Distancia OSM conflictiva",
    "NO_COORDINATE_FOR_OSM": "Sin coordenada para OSM",
    "NO_NEAR_OSM_SEGMENT": "Sin segmento OSM cercano",
    "INVALID_POINT_FOR_OSM": "Punto invalido para OSM",
}

RESOLUTION_LABELS = {
    "COMPATIBLE": "Compatible",
    "LOCAL_NAME_WITHIN_CORRIDOR": "Nombre local dentro del corredor",
    "INTERSECTION_ACCEPTED": "Interseccion aceptada",
    "REVIEW_COORDINATE_OR_NAME": "Revisar coordenada o nombre",
    "UNRESOLVED": "No resuelto",
}

ROAD_TYPE_LABELS = {
    "LOCAL_RESIDENCIAL": "Local residencial",
    "ARTERIAL_PRINCIPAL": "Arterial principal",
    "SERVICIO_ACCESO": "Servicio/acceso",
    "ARTERIAL_SECUNDARIA": "Arterial secundaria",
    "COLECTORA": "Colectora",
    "NACIONAL_ESTRUCTURANTE": "Nacional estructurante",
    "NO_CLASIFICADA_OSM": "No clasificada OSM",
}

HIGHWAY_LABELS = {
    "motorway": "Autopista",
    "trunk": "Troncal",
    "primary": "Primaria",
    "secondary": "Secundaria",
    "tertiary": "Terciaria",
    "unclassified": "No clasificada",
    "residential": "Residencial",
    "living_street": "Calle local",
    "service": "Servicio/acceso",
    "motorway_link": "Rampa autopista",
    "trunk_link": "Rampa troncal",
    "primary_link": "Rampa primaria",
    "secondary_link": "Rampa secundaria",
    "tertiary_link": "Rampa terciaria",
}

ROBUSTNESS_LABELS = {
    "ROBUSTO": "Robusto",
    "DEPENDIENTE_DEL_ENFOQUE": "Dependiente del enfoque",
    "NO_PRIORITARIO": "No prioritario",
    "INTERMEDIO": "Intermedio",
}

SOURCE_SCOPE_LABELS = {
    "DEPARTMENT": "Red departamental",
    "NATIONAL": "Red nacional",
    "AMSS": "Red AMSS",
    "SIN_FUENTE_OSM": "Sin fuente OSM",
}

AMSS_VIEW_STATE = pdk.ViewState(latitude=13.705, longitude=-89.205, zoom=10.7, pitch=0, bearing=0)


st.set_page_config(page_title="Incidentes viales - tablero", layout="wide")


def require_outputs() -> None:
    if not EVENTS_PATH.exists():
        st.error(
            "No existen resultados de incidentes. Ejecuta primero: "
            "`make run-incidentes-analysis`"
        )
        st.stop()


def parse_path(value: str) -> list[list[float]]:
    coords = json.loads(value)
    return [[float(lon), float(lat)] for lon, lat in coords]


def deck_records(data: pd.DataFrame, columns: list[str]) -> list[dict]:
    unique = data.loc[:, ~data.columns.duplicated()].copy()
    clean = unique[[column for column in columns if column in unique.columns]].copy()
    return json.loads(clean.to_json(orient="records"))


@st.cache_data(show_spinner=False)
def load_events() -> pd.DataFrame:
    events = pd.read_csv(EVENTS_PATH)
    events["datetime_dt"] = pd.to_datetime(events["datetime"], errors="coerce")
    events["event_date_dt"] = events["datetime_dt"].dt.date
    events["latitude_num"] = pd.to_numeric(events["latitude_num"], errors="coerce")
    events["longitude_num"] = pd.to_numeric(events["longitude_num"], errors="coerce")
    for col in ["coordinate_pair_present", "coordinate_inside_sv_bbox", "repeated_coordinate_flag"]:
        if col in events.columns:
            events[col] = events[col].map(lambda value: str(value).strip().lower() == "true")
    for col in [
        "mentions",
        "latest_likes",
        "latest_comments",
        "latest_shares",
        "latest_quotes",
        "latest_views",
        "impact_social_score",
        "engagement_mentions",
        "metric_score_0_100",
        "event_hour",
        "severity_score",
        "nearest_osm_distance_m",
        "fatality_flag",
        "injury_flag",
        "vulnerable_user_flag",
        "heavy_vehicle_flag",
    ]:
        if col in events.columns:
            events[col] = pd.to_numeric(events[col], errors="coerce").fillna(0)
    events["heat_weight_eventos"] = 1
    events["heat_weight_menciones"] = events["mentions"].clip(lower=0)
    events["heat_weight_impacto_social"] = events["impact_social_score"].clip(lower=0)
    events["point_color"] = events["coordinate_quality_status"].map(
        lambda v: POINT_COLORS.get(str(v), [80, 130, 170, 190])
    )
    events["point_radius"] = (
        4
        + events["impact_social_score"].fillna(0).clip(lower=0).pow(0.5) * 0.45
        + events["mentions"].fillna(0).clip(lower=0) * 0.15
    ).clip(lower=4, upper=18)
    return events


@st.cache_data(show_spinner=False)
def load_heatmap() -> pd.DataFrame:
    df = pd.read_csv(HEATMAP_PATH)
    df["datetime_dt"] = pd.to_datetime(df["datetime"], errors="coerce")
    df["event_date_dt"] = df["datetime_dt"].dt.date
    return df


@st.cache_data(show_spinner=False)
def load_optional_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def show_image(path: Path, caption: str | None = None) -> None:
    if path.exists():
        st.image(str(path), caption=caption, width="stretch")


def label_value(value: object, labels: dict[str, str]) -> str:
    if pd.isna(value):
        return "Sin dato"
    text = str(value)
    return labels.get(text, text.replace("_", " ").title())


def label_series(series: pd.Series, labels: dict[str, str]) -> pd.Series:
    return series.fillna("Sin dato").map(lambda value: label_value(value, labels))


def pct(part: int | float, total: int | float) -> str:
    if not total:
        return "0%"
    return f"{part / total:.0%}"


def metric_row(metrics: list[tuple[str, str, str | None]]) -> None:
    columns = st.columns(len(metrics))
    for column, (label, value, delta) in zip(columns, metrics):
        column.metric(label, value, delta=delta)


def readable_count_table(series: pd.Series, labels: dict[str, str], value_name: str = "eventos") -> pd.DataFrame:
    table = series.value_counts(dropna=False).rename_axis("categoria").reset_index(name=value_name)
    table["categoria"] = table["categoria"].map(lambda value: label_value(value, labels))
    return table


def render_swatch_legend(title: str, items: list[tuple[str, list[int]]]) -> None:
    swatches = "".join(
        '<div style="display:flex; align-items:center; gap:0.45rem; margin:0.25rem 0;">'
        f'<span style="display:inline-block; width:0.85rem; height:0.85rem; border-radius:0.2rem; background:{rgba_css(color)}; border:1px solid rgba(148,163,184,0.65);"></span>'
        f'<span>{html_escape(label)}</span>'
        "</div>"
        for label, color in items
    )
    st.markdown(
        f"""
        <div style="border:1px solid rgba(148,163,184,0.28); border-radius:8px; padding:0.75rem; min-height:10rem;">
          <div style="font-weight:700; margin-bottom:0.4rem;">{html_escape(title)}</div>
          <div style="font-size:0.86rem;">{swatches}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def html_escape(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def read_segments_file(path: Path, major_only: bool) -> pd.DataFrame:
    usecols = [
        "source_department",
        "source_department_slug",
        "osm_way_id",
        "name",
        "ref",
        "highway",
        "oneway",
        "lanes",
        "maxspeed",
        "surface",
        "length_m",
        "road_type_category",
        "geometry_json",
    ]
    segments = pd.read_csv(path, usecols=lambda col: col in usecols, low_memory=False)
    if major_only and "highway" in segments.columns:
        segments = segments[segments["highway"].isin(DEFAULT_MAJOR_HIGHWAYS)].copy()
    segments["osm_source_file"] = str(path)
    return segments


@st.cache_data(show_spinner=False)
def load_segments(department_norm_values: tuple[str, ...] = (), major_only: bool = True) -> pd.DataFrame:
    paths: list[Path] = []
    for department in department_norm_values:
        slug = DEPARTMENT_SLUGS.get(str(department).strip().upper())
        if not slug:
            continue
        path = OSM_DEPARTMENTS_DIR / slug / "osm_road_segments.csv"
        if path.exists():
            paths.append(path)
    if not paths and OSM_NATIONAL_SEGMENTS_PATH.exists() and department_norm_values:
        paths.append(OSM_NATIONAL_SEGMENTS_PATH)
    if not paths and OSM_SEGMENTS_PATH.exists():
        paths.append(OSM_SEGMENTS_PATH)
    if not paths:
        return pd.DataFrame()
    frames = [read_segments_file(path, major_only) for path in paths]
    segments = pd.concat(frames, ignore_index=True)
    if "osm_way_id" in segments.columns:
        segments = segments.drop_duplicates(subset=["osm_way_id", "highway", "name", "ref"])
    if segments.empty:
        return pd.DataFrame()
    for col in ["length_m", "lanes", "maxspeed"]:
        if col in segments.columns:
            segments[col] = pd.to_numeric(segments[col], errors="coerce")
    segments["path"] = segments["geometry_json"].map(parse_path)
    segments["color"] = segments["highway"].map(lambda v: HIGHWAY_STYLES.get(v, {}).get("color", [100, 115, 130, 55]))
    segments["width"] = segments["highway"].map(lambda v: HIGHWAY_STYLES.get(v, {}).get("width", 0.65))
    segments["length_km"] = segments["length_m"] / 1000
    bounds = pd.DataFrame(
        [
            {
                "min_lon": min(point[0] for point in path),
                "max_lon": max(point[0] for point in path),
                "min_lat": min(point[1] for point in path),
                "max_lat": max(point[1] for point in path),
            }
            for path in segments["path"]
        ],
        index=segments.index,
    )
    segments = pd.concat([segments, bounds], axis=1)
    return segments.drop(columns=["geometry_json"])


def filter_events(events: pd.DataFrame) -> pd.DataFrame:
    with st.sidebar:
        st.header("Filtros")
        min_date = events["event_date_dt"].min()
        max_date = events["event_date_dt"].max()
        st.caption("Filtros principales para territorio, tiempo, severidad y corredor.")
        date_range = st.date_input("Rango de fechas", value=(min_date, max_date), min_value=min_date, max_value=max_date)
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
        else:
            start_date = end_date = date_range

        hour_range = st.slider("Hora del evento", 0, 23, (0, 23))

        incidents = sorted(events["incident"].dropna().unique().tolist())
        selected_incidents = st.multiselect("Tipo de incidente", incidents, default=incidents)

        departments = sorted(events["department_norm"].fillna("SIN_DEPTO").replace("", "SIN_DEPTO").unique().tolist())
        selected_departments = st.multiselect("Departamento", departments, default=departments)

        municipalities = sorted(events["municipality_norm"].fillna("SIN_MUNICIPIO").replace("", "SIN_MUNICIPIO").unique().tolist())
        selected_municipalities = st.multiselect("Municipio", municipalities, default=municipalities)

        corridors = sorted(
            events["corridor_norm"].fillna("SIN_CORREDOR").replace("", "SIN_CORREDOR").unique().tolist()
            if "corridor_norm" in events.columns
            else ["SIN_CORREDOR"]
        )
        selected_corridors = st.multiselect("Corredor normalizado", corridors, default=corridors)

        severities = sorted(events["severity_class"].fillna("SIN_SEVERIDAD").replace("", "SIN_SEVERIDAD").unique().tolist())
        selected_severities = st.multiselect(
            "Severidad",
            severities,
            default=severities,
            format_func=lambda value: label_value(value, SEVERITY_LABELS),
        )

        with st.expander("Filtros avanzados", expanded=False):
            resolutions = sorted(events["text_osm_resolution"].fillna("SIN_RESOLUCION").replace("", "SIN_RESOLUCION").unique().tolist())
            selected_resolutions = st.multiselect(
                "Resolucion texto-OSM",
                resolutions,
                default=resolutions,
                format_func=lambda value: label_value(value, RESOLUTION_LABELS),
            )

            sources = sorted(events["source"].fillna("SIN_FUENTE").replace("", "SIN_FUENTE").unique().tolist())
            selected_sources = st.multiselect("Fuente principal", sources, default=sources)

            coord_statuses = sorted(events["coordinate_quality_status"].dropna().unique().tolist())
            selected_coord = st.multiselect(
                "Estado de coordenada",
                coord_statuses,
                default=coord_statuses,
                format_func=lambda value: label_value(value, COORD_STATUS_LABELS),
            )

            osm_statuses = sorted(events["osm_match_status"].dropna().unique().tolist())
            selected_osm = st.multiselect(
                "Estado OSM",
                osm_statuses,
                default=osm_statuses,
                format_func=lambda value: label_value(value, OSM_STATUS_LABELS),
            )

    filtered = events.copy()
    filtered["department_filter"] = filtered["department_norm"].fillna("SIN_DEPTO").replace("", "SIN_DEPTO")
    filtered["municipality_filter"] = filtered["municipality_norm"].fillna("SIN_MUNICIPIO").replace("", "SIN_MUNICIPIO")
    filtered["corridor_filter"] = filtered["corridor_norm"].fillna("SIN_CORREDOR").replace("", "SIN_CORREDOR")
    filtered["severity_filter"] = filtered["severity_class"].fillna("SIN_SEVERIDAD").replace("", "SIN_SEVERIDAD")
    filtered["resolution_filter"] = filtered["text_osm_resolution"].fillna("SIN_RESOLUCION").replace("", "SIN_RESOLUCION")
    filtered["source_filter"] = filtered["source"].fillna("SIN_FUENTE").replace("", "SIN_FUENTE")
    filtered = filtered[
        (filtered["event_date_dt"] >= start_date)
        & (filtered["event_date_dt"] <= end_date)
        & (filtered["event_hour"].fillna(-1).between(hour_range[0], hour_range[1]))
        & (filtered["incident"].isin(selected_incidents))
        & (filtered["department_filter"].isin(selected_departments))
        & (filtered["municipality_filter"].isin(selected_municipalities))
        & (filtered["corridor_filter"].isin(selected_corridors))
        & (filtered["severity_filter"].isin(selected_severities))
        & (filtered["resolution_filter"].isin(selected_resolutions))
        & (filtered["source_filter"].isin(selected_sources))
        & (filtered["coordinate_quality_status"].isin(selected_coord))
        & (filtered["osm_match_status"].isin(selected_osm))
    ]
    return filtered


def view_state(data: pd.DataFrame) -> pdk.ViewState:
    points = data[data["coordinate_inside_sv_bbox"] == True]
    if points.empty:
        return pdk.ViewState(latitude=13.70, longitude=-89.20, zoom=8)
    return pdk.ViewState(
        latitude=float(points["latitude_num"].mean()),
        longitude=float(points["longitude_num"].mean()),
        zoom=8.2,
        pitch=0,
        bearing=0,
    )


def osm_view_state(segments: pd.DataFrame) -> pdk.ViewState:
    if segments.empty:
        return pdk.ViewState(latitude=13.70, longitude=-89.20, zoom=11.4, pitch=0, bearing=0)
    return pdk.ViewState(
        latitude=float((segments["min_lat"].min() + segments["max_lat"].max()) / 2),
        longitude=float((segments["min_lon"].min() + segments["max_lon"].max()) / 2),
        zoom=11.4,
        pitch=0,
        bearing=0,
    )


def style_segments(data: pd.DataFrame, opacity: float, width_scale: float) -> pd.DataFrame:
    styled = data.copy()
    styled["render_color"] = styled["color"].map(
        lambda color: [int(color[0]), int(color[1]), int(color[2]), max(20, min(255, int(color[3] * opacity)))]
    )
    styled["render_width"] = styled["width"] * width_scale
    styled["highway_label"] = styled["highway"].map(lambda value: label_value(value, HIGHWAY_LABELS))
    return styled


def color_for_category(value: object, palette: dict[str, list[int]], fallback: list[int]) -> list[int]:
    return palette.get(str(value), fallback)


def style_points(data: pd.DataFrame, color_by: str, size_by: str) -> pd.DataFrame:
    styled = data.copy()
    if color_by == "Severidad":
        styled["point_color"] = styled["severity_class"].map(lambda value: color_for_category(value, SEVERITY_COLORS, [80, 130, 170, 190]))
    elif color_by == "Estado OSM":
        styled["point_color"] = styled["osm_match_status"].map(lambda value: color_for_category(value, OSM_STATUS_COLORS, [80, 130, 170, 190]))
    elif color_by == "Resolucion texto-OSM":
        styled["point_color"] = styled["text_osm_resolution"].map(lambda value: color_for_category(value, RESOLUTION_COLORS, [80, 130, 170, 190]))
    else:
        styled["point_color"] = styled["coordinate_quality_status"].map(lambda value: color_for_category(value, POINT_COLORS, [80, 130, 170, 190]))

    if size_by == "Menciones":
        value = styled["mentions"].fillna(0).clip(lower=0)
        styled["point_radius"] = (5 + value.pow(0.7) * 1.4).clip(5, 22)
    elif size_by == "Severidad":
        value = styled["severity_score"].fillna(0).clip(lower=0)
        styled["point_radius"] = (5 + value * 12).clip(5, 22)
    else:
        value = styled["impact_social_score"].fillna(0).clip(lower=0)
        styled["point_radius"] = (5 + value.pow(0.5) * 0.55).clip(5, 22)
    styled["severity_label"] = label_series(styled["severity_class"], SEVERITY_LABELS)
    styled["coord_label"] = label_series(styled["coordinate_quality_status"], COORD_STATUS_LABELS)
    styled["osm_label"] = label_series(styled["osm_match_status"], OSM_STATUS_LABELS)
    styled["resolution_label"] = label_series(styled["text_osm_resolution"], RESOLUTION_LABELS)
    return styled


def path_layer(data: pd.DataFrame) -> pdk.Layer:
    return pdk.Layer(
        "PathLayer",
        data=deck_records(
            data,
            [
                "path",
                "render_color",
                "render_width",
                "name",
                "ref",
                "highway",
                "oneway",
                "lanes",
                "maxspeed",
                "surface",
                "road_type_category",
                "highway_label",
                "length_km",
                "osm_source_file",
            ],
        ),
        id="osm-base",
        get_path="path",
        get_color="render_color",
        get_width="render_width",
        width_units="pixels",
        rounded=True,
        pickable=True,
        auto_highlight=True,
    )


def scatter_layer(data: pd.DataFrame) -> pdk.Layer:
    points = data[data["coordinate_pair_present"] == True].copy()
    return pdk.Layer(
        "ScatterplotLayer",
        data=deck_records(
            points,
            [
                "longitude_num",
                "latitude_num",
                "point_color",
                "point_radius",
                "ticketNumber",
                "datetime",
                "incident",
                "department",
                "municipality",
                "mentions",
                "latest_views",
                "latest_shares",
                "impact_social_score",
                "coord_label",
                "osm_label",
                "nearest_osm_name",
                "nearest_osm_ref",
                "corridor_norm",
                "severity_label",
                "resolution_label",
                "corridor_resolution_confidence",
                "nearest_osm_source_scope",
            ],
        ),
        id="event-points",
        get_position="[longitude_num, latitude_num]",
        get_fill_color="point_color",
        get_radius="point_radius",
        radius_units="pixels",
        stroked=True,
        get_line_color=[255, 255, 255, 190],
        line_width_min_pixels=1,
        pickable=True,
        auto_highlight=True,
    )


def highlight_unresolved_layer(data: pd.DataFrame) -> pdk.Layer:
    points = data[
        (data["coordinate_pair_present"] == True)
        & (
            data["text_osm_resolution"].eq("UNRESOLVED")
            | data["corridor_norm"].fillna("").astype(str).str.strip().eq("")
        )
    ].copy()
    points["highlight_color"] = [255, 255, 255, 235]
    points["highlight_radius"] = 13
    return pdk.Layer(
        "ScatterplotLayer",
        data=deck_records(
            points,
            [
                "longitude_num",
                "latitude_num",
                "highlight_color",
                "highlight_radius",
                "ticketNumber",
                "datetime",
                "department",
                "municipality",
                "address",
                "corridor_norm",
                "text_osm_resolution",
                "osm_match_status",
            ],
        ),
        id="unresolved-highlight",
        get_position="[longitude_num, latitude_num]",
        get_fill_color="highlight_color",
        get_radius="highlight_radius",
        radius_units="pixels",
        stroked=True,
        get_line_color=[220, 38, 38, 240],
        line_width_min_pixels=2,
        pickable=True,
        auto_highlight=True,
    )


def heatmap_layer(data: pd.DataFrame, weight_col: str, layer_id: str, color_range: list[list[int]], radius: int) -> pdk.Layer:
    points = data[data["coordinate_inside_sv_bbox"] == True].copy()
    return pdk.Layer(
        "HeatmapLayer",
        data=deck_records(points, ["longitude_num", "latitude_num", weight_col]),
        id=layer_id,
        get_position="[longitude_num, latitude_num]",
        get_weight=weight_col,
        radius_pixels=radius,
        intensity=1,
        threshold=0.03,
        color_range=color_range,
    )


def rgba_css(color: list[int]) -> str:
    alpha = max(float(color[3]) / 255, 0.42) if len(color) > 3 else 1
    return f"rgba({color[0]}, {color[1]}, {color[2]}, {alpha:.2f})"


def fmt_heat_value(value: float) -> str:
    if pd.isna(value):
        return "0"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if abs(value) >= 10:
        return f"{value:,.1f}"
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def heatmap_cell_values(data: pd.DataFrame, weight_col: str, cell_degrees: float = 0.005) -> pd.Series:
    points = data[data["coordinate_inside_sv_bbox"] == True].copy()
    if points.empty or weight_col not in points.columns:
        return pd.Series(dtype=float)
    points["__heat_weight"] = pd.to_numeric(points[weight_col], errors="coerce").fillna(0)
    points = points[points["__heat_weight"] > 0].copy()
    if points.empty:
        return pd.Series(dtype=float)
    points["__heat_cell_lon"] = (points["longitude_num"] // cell_degrees).astype(int)
    points["__heat_cell_lat"] = (points["latitude_num"] // cell_degrees).astype(int)
    return points.groupby(["__heat_cell_lon", "__heat_cell_lat"])["__heat_weight"].sum()


def heatmap_reference_card(config: dict, values: pd.Series) -> str:
    colors = config["color_range"]
    gradient = ", ".join(
        f"{rgba_css(color)} {round(idx * 100 / max(len(colors) - 1, 1))}%"
        for idx, color in enumerate(colors)
    )
    if values.empty:
        ranges = ["sin datos"] * 4
        total = "0"
        cells = 0
        max_value = "0"
    else:
        breaks = values.quantile([0, 0.25, 0.5, 0.75, 1]).tolist()
        ranges = [
            f"{fmt_heat_value(breaks[idx])} - {fmt_heat_value(breaks[idx + 1])}"
            for idx in range(4)
        ]
        total = fmt_heat_value(float(values.sum()))
        cells = int(values.count())
        max_value = fmt_heat_value(float(values.max()))

    labels = ["Bajo", "Medio bajo", "Medio alto", "Alto"]
    swatches = "".join(
        '<div style="display:flex; align-items:center; gap:0.45rem; margin-top:0.35rem;">'
        f'<span style="display:inline-block; width:0.85rem; height:0.85rem; border-radius:0.2rem; background:{rgba_css(colors[idx])}; border:1px solid rgba(255,255,255,0.35);"></span>'
        f'<span style="min-width:5.2rem; color:#e5e7eb;">{labels[idx]}</span>'
        f'<span style="color:#cbd5e1;">{ranges[idx]} {config["unit"]}</span>'
        "</div>"
        for idx in range(4)
    )
    return (
        '<div style="border:1px solid rgba(148,163,184,0.35); border-radius:8px; padding:0.85rem; background:rgba(15,23,42,0.44); min-height:17rem;">'
        f'<div style="font-weight:700; color:#f8fafc; margin-bottom:0.15rem;">{config["title"]}</div>'
        f'<div style="font-size:0.84rem; color:#cbd5e1; min-height:2.7rem;">{config["meaning"]}</div>'
        f'<div style="height:0.85rem; border-radius:999px; background:linear-gradient(90deg, {gradient}); margin:0.65rem 0 0.35rem 0; border:1px solid rgba(255,255,255,0.16);"></div>'
        '<div style="display:flex; justify-content:space-between; font-size:0.78rem; color:#cbd5e1;"><span>menor</span><span>mayor</span></div>'
        f'<div style="margin-top:0.55rem; font-size:0.82rem;">{swatches}</div>'
        '<div style="margin-top:0.65rem; padding-top:0.55rem; border-top:1px solid rgba(148,163,184,0.25); font-size:0.8rem; color:#cbd5e1;">'
        f'Total visible: <b style="color:#f8fafc;">{total} {config["unit"]}</b><br/>'
        f'Max. celda: <b style="color:#f8fafc;">{max_value} {config["unit"]}</b><br/>'
        f'Celdas con datos: <b style="color:#f8fafc;">{cells}</b>'
        "</div>"
        "</div>"
    )


def render_heatmap_reference(data: pd.DataFrame, active_heatmaps: list[str]) -> None:
    with st.expander("Referencia de mapas de calor", expanded=bool(active_heatmaps)):
        st.caption(
            "Los colores representan intensidad relativa sobre los datos filtrados. "
            "Los rangos se calculan agregando pesos en celdas aproximadas de 500 m; "
            "la visualizacion exacta del heatmap puede variar con el zoom y el radio seleccionado."
        )
        if not active_heatmaps:
            st.info("Activa una capa de calor para ver su escala de colores y valores observados.")
            return
        columns = st.columns(len(active_heatmaps))
        for column, key in zip(columns, active_heatmaps):
            config = HEATMAP_CONFIGS[key]
            values = heatmap_cell_values(data, config["weight_col"])
            column.markdown(heatmap_reference_card(config, values), unsafe_allow_html=True)


def map_tab(events: pd.DataFrame, filtered: pd.DataFrame) -> None:
    department_values = tuple(
        sorted(
            {
                str(value)
                for value in filtered.get("department_norm", pd.Series(dtype=str)).dropna().unique()
                if str(value).strip() and str(value).strip() != "SIN_DEPTO"
            }
        )
    )
    st.subheader("Mapa PVN: red vial, incidentes y mapas de calor")
    st.caption(
        "Explora la Presion Vial Noticiosa desde tres capas: eventos individuales, "
        "red vial OSM e intensidad espacial por eventos, menciones o impacto social."
    )

    focus = st.radio(
        "Vista inicial",
        options=["AMSS / San Salvador", "Incidentes filtrados", "Red vial OSM filtrada"],
        index=0,
        horizontal=True,
    )

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    show_osm = c1.toggle("Red vial OSM", value=True)
    show_points = c2.toggle("Puntos", value=True)
    show_unresolved = c3.toggle("No resueltos", value=False)
    show_heat_events = c4.toggle("Heat eventos", value=False)
    show_heat_mentions = c5.toggle("Heat menciones", value=False)
    show_heat_impact = c6.toggle("Heat impacto", value=True)

    control_a, control_b, control_c, control_d = st.columns(4)
    basemap_label = control_a.selectbox(
        "Mapa base",
        options=list(BASEMAP_STYLES.keys()),
        index=0,
    )
    road_density = control_b.segmented_control(
        "Red vial",
        options=["Vias principales", "Toda la red"],
        default="Vias principales",
    )
    point_color_by = control_c.segmented_control(
        "Color puntos",
        options=["Coordenada", "Severidad", "Estado OSM", "Resolucion texto-OSM"],
        default="Severidad",
    )
    point_size_by = control_d.segmented_control(
        "Tamano puntos",
        options=["Impacto social", "Menciones", "Severidad"],
        default="Impacto social",
    )
    major_only = road_density == "Vias principales"
    segments = load_segments(department_values, major_only=major_only)
    styled_filtered = style_points(filtered, point_color_by, point_size_by)

    default_road_classes = []
    if not segments.empty:
        default_road_classes = [value for value in DEFAULT_OSM_HIGHWAYS if value in set(segments["highway"].dropna())]
    road_classes = default_road_classes
    road_opacity = 1.0
    road_width = 2.2
    radius = 55
    with st.expander("Configuracion avanzada de capas", expanded=False):
        if not segments.empty:
            road_classes = st.multiselect(
                "Tipos de via OSM en la capa base",
                options=sorted(segments["highway"].dropna().unique().tolist()),
                default=default_road_classes,
                format_func=lambda value: label_value(value, HIGHWAY_LABELS),
            )
            road_c1, road_c2 = st.columns(2)
            road_opacity = road_c1.slider("Opacidad red vial", 0.2, 1.0, 1.0, 0.05)
            road_width = road_c2.slider("Grosor red vial", 0.5, 3.0, 2.2, 0.05)
        radius = st.slider("Radio del heatmap", 20, 120, 55)

    active_heatmaps = []
    if show_heat_events:
        active_heatmaps.append("eventos")
    if show_heat_mentions:
        active_heatmaps.append("menciones")
    if show_heat_impact:
        active_heatmaps.append("impacto")

    layers: list[pdk.Layer] = []
    visible_segments = pd.DataFrame()
    if show_heat_events:
        config = HEATMAP_CONFIGS["eventos"]
        layers.append(
            heatmap_layer(
                filtered,
                config["weight_col"],
                "heat-events",
                config["color_range"],
                radius,
            )
        )
    if show_heat_mentions:
        config = HEATMAP_CONFIGS["menciones"]
        layers.append(
            heatmap_layer(
                filtered,
                config["weight_col"],
                "heat-mentions",
                config["color_range"],
                radius,
            )
        )
    if show_heat_impact:
        config = HEATMAP_CONFIGS["impacto"]
        layers.append(
            heatmap_layer(
                filtered,
                config["weight_col"],
                "heat-impact",
                config["color_range"],
                radius,
            )
        )
    if show_osm and not segments.empty:
        visible_segments = segments[segments["highway"].isin(road_classes)].copy()
        if len(visible_segments) > 35000:
            visible_segments = visible_segments.sort_values("length_m", ascending=False).head(35000).copy()
        visible_segments = style_segments(visible_segments, road_opacity, road_width)
        layers.append(path_layer(visible_segments))
    if show_points:
        layers.append(scatter_layer(styled_filtered))
    if show_unresolved:
        layers.append(highlight_unresolved_layer(styled_filtered))

    tooltip = {
        "html": """
        <b>{ticketNumber}</b><br/>
        {datetime}<br/>
        {incident}<br/>
        {municipality}, {department}<br/>
        severidad: {severity_label}<br/>
        menciones: {mentions}<br/>
        views: {latest_views}<br/>
        shares: {latest_shares}<br/>
        impacto: {impact_social_score}<br/>
        coord: {coord_label}<br/>
        OSM: {osm_label}<br/>
        corredor: {corridor_norm}<br/>
        via OSM: {nearest_osm_name} {nearest_osm_ref}<br/>
        fuente OSM: {nearest_osm_source_scope}<br/>
        resolucion: {resolution_label} ({corridor_resolution_confidence})<br/>
        <hr/>
        <b>{name}</b> {ref}<br/>
        tipo OSM: {highway_label}<br/>
        sentido: {oneway}<br/>
        carriles: {lanes}<br/>
        velocidad: {maxspeed}<br/>
        superficie: {surface}<br/>
        longitud segmento: {length_km} km
        """,
        "style": {"backgroundColor": "#111827", "color": "white"},
    }

    if focus == "AMSS / San Salvador":
        initial_view = AMSS_VIEW_STATE
    elif focus == "Red vial OSM filtrada" and show_osm and not visible_segments.empty:
        initial_view = osm_view_state(visible_segments)
    else:
        initial_view = view_state(styled_filtered)

    deck_kwargs = {
        "initial_view_state": initial_view,
        "layers": layers,
        "tooltip": tooltip,
    }
    selected_basemap = BASEMAP_STYLES[basemap_label]
    if selected_basemap:
        deck_kwargs["map_style"] = selected_basemap

    st.pydeck_chart(pdk.Deck(**deck_kwargs), width="stretch", height=MAP_CHART_HEIGHT_PX)

    with st.expander("Leyendas de lectura", expanded=False):
        legend_a, legend_b, legend_c = st.columns(3)
        with legend_a:
            render_swatch_legend(
                "Color de puntos por severidad",
                [
                    (label_value(key, SEVERITY_LABELS), color)
                    for key, color in SEVERITY_COLORS.items()
                ],
            )
        with legend_b:
            render_swatch_legend(
                "Red vial OSM",
                [
                    (label_value(key, HIGHWAY_LABELS), HIGHWAY_STYLES[key]["color"])
                    for key in ["trunk", "primary", "secondary", "tertiary", "residential", "service"]
                    if key in HIGHWAY_STYLES
                ],
            )
        with legend_c:
            st.markdown("**Lectura metodologica**")
            st.caption(
                "Los puntos representan eventos deduplicados. El tamano depende de la variable seleccionada "
                "(impacto social, menciones o severidad). Los mapas de calor no son siniestralidad oficial: "
                "representan intensidad relativa dentro del filtro actual."
            )

    render_heatmap_reference(filtered, active_heatmaps)

    if show_osm and not visible_segments.empty:
        source_files = visible_segments.get("osm_source_file", pd.Series(dtype=str)).nunique()
        st.caption(
            "Capa vial base OSM: "
            f"{len(visible_segments):,} segmentos visibles, "
            f"{visible_segments['length_km'].sum():,.1f} km de red. "
            f"fuentes cargadas: {source_files}."
        )
        with st.expander("Resumen de la red vial base OSM"):
            road_summary = (
                visible_segments.groupby("highway", dropna=False)
                .agg(
                    segmentos=("osm_way_id", "count"),
                    km=("length_km", "sum"),
                    vias_con_nombre=("name", lambda s: int(s.fillna("").astype(str).str.strip().ne("").sum())),
                    vias_oneway=("oneway", lambda s: int(s.fillna("").astype(str).str.lower().eq("yes").sum())),
                    carriles_promedio=("lanes", "mean"),
                    velocidad_promedio=("maxspeed", "mean"),
                )
                .reset_index()
                .sort_values("km", ascending=False)
            )
            road_summary["tipo_via"] = road_summary["highway"].map(lambda value: label_value(value, HIGHWAY_LABELS))
            road_summary = road_summary[
                ["tipo_via", "segmentos", "km", "vias_con_nombre", "vias_oneway", "carriles_promedio", "velocidad_promedio"]
            ]
            st.dataframe(road_summary, width="stretch", hide_index=True)

    event_cols = [
        "ticketNumber",
        "datetime",
        "incident",
        "department",
        "department_norm",
        "municipality",
        "municipality_norm",
        "address",
        "corridor_candidate",
        "corridor_norm",
        "text_osm_resolution",
        "mentions",
        "latest_views",
        "latest_shares",
        "impact_social_score",
        "coordinate_quality_status",
        "osm_match_status",
    ]
    with st.expander("Detalle de eventos filtrados en el mapa", expanded=False):
        detail = filtered[[col for col in event_cols if col in filtered.columns]].sort_values("impact_social_score", ascending=False).copy()
        if "coordinate_quality_status" in detail.columns:
            detail["coordinate_quality_status"] = label_series(detail["coordinate_quality_status"], COORD_STATUS_LABELS)
        if "osm_match_status" in detail.columns:
            detail["osm_match_status"] = label_series(detail["osm_match_status"], OSM_STATUS_LABELS)
        if "text_osm_resolution" in detail.columns:
            detail["text_osm_resolution"] = label_series(detail["text_osm_resolution"], RESOLUTION_LABELS)
        st.dataframe(detail, width="stretch", hide_index=True)


def summary_tab(events: pd.DataFrame, filtered: pd.DataFrame) -> None:
    st.subheader("Resumen analitico de la PVN")
    st.caption(
        "Estado general del conjunto filtrado: volumen noticioso, severidad, viabilidad geoespacial "
        "y capacidad de asociacion evento-via."
    )
    total = max(len(filtered), 1)
    osm_high_medium = int(filtered["osm_match_status"].isin(["SPATIAL_OSM_HIGH", "SPATIAL_OSM_MEDIUM"]).sum())
    corridor_count = int(filtered["corridor_norm"].fillna("").astype(str).str.strip().ne("").sum())
    unresolved_count = int(filtered["text_osm_resolution"].eq("UNRESOLVED").sum())
    severe_count = int(filtered["severity_class"].isin(["FATALITY_REPORTED", "INJURY_REPORTED"]).sum())

    st.markdown("**Cobertura analitica**")
    metric_row(
        [
            ("Eventos", f"{len(filtered):,}", "deduplicados"),
            ("Menciones", f"{int(filtered['mentions'].sum()):,}", "publicaciones"),
            ("Impacto social", f"{filtered['impact_social_score'].sum():,.0f}", "ponderado"),
            ("Eventos severos", f"{severe_count:,}", pct(severe_count, total)),
        ]
    )
    st.markdown("**Viabilidad metodologica**")
    metric_row(
        [
            ("Coord. validas SV", f"{int(filtered['coordinate_inside_sv_bbox'].sum()):,}", pct(int(filtered["coordinate_inside_sv_bbox"].sum()), total)),
            ("OSM alto/medio", f"{osm_high_medium:,}", pct(osm_high_medium, total)),
            ("Con corredor", f"{corridor_count:,}", pct(corridor_count, total)),
            ("No resueltos", f"{unresolved_count:,}", pct(unresolved_count, total)),
        ]
    )

    fig_a, fig_b = st.columns([1.1, 1])
    with fig_a:
        show_image(FIG_EXECUTIVE_PATH)
    with fig_b:
        show_image(FIG_CORRIDORS_PATH)

    c1, c2, c3 = st.columns(3)
    c1.markdown("**Calidad geografica**")
    c1.bar_chart(readable_count_table(filtered["coordinate_quality_status"], COORD_STATUS_LABELS).set_index("categoria"))
    c2.markdown("**Resolucion texto-OSM**")
    c2.bar_chart(readable_count_table(filtered["text_osm_resolution"], RESOLUTION_LABELS).set_index("categoria"))
    c3.markdown("**Severidad preliminar**")
    c3.bar_chart(readable_count_table(filtered["severity_class"], SEVERITY_LABELS).set_index("categoria"))

    st.markdown("**Resultados principales del filtro actual**")
    r1, r2 = st.columns(2)
    with r1:
        st.markdown("Top departamentos")
        departments = (
            filtered.groupby("department_norm", dropna=False)
            .agg(eventos=("uuid", "count"), menciones=("mentions", "sum"), impacto=("impact_social_score", "sum"))
            .reset_index()
            .sort_values(["eventos", "impacto"], ascending=False)
            .head(8)
        )
        st.dataframe(departments, width="stretch", hide_index=True)
    with r2:
        st.markdown("Top corredores")
        corridors = filtered[filtered["corridor_norm"].fillna("").astype(str).str.strip().ne("")].copy()
        corridor_summary = (
            corridors.groupby("corridor_norm", dropna=False)
            .agg(eventos=("uuid", "count"), menciones=("mentions", "sum"), impacto=("impact_social_score", "sum"))
            .reset_index()
            .sort_values(["eventos", "impacto"], ascending=False)
            .head(8)
        )
        st.dataframe(corridor_summary, width="stretch", hide_index=True)

    with st.expander("Eventos con mayor score exploratorio", expanded=False):
        top_events = filtered.sort_values("metric_score_0_100", ascending=False)[
            [
                "ticketNumber",
                "datetime",
                "incident",
                "department_norm",
                "municipality_norm",
                "mentions",
                "corridor_norm",
                "text_osm_resolution",
                "impact_social_score",
                "metric_score_0_100",
                "metric_category",
            ]
        ].head(20).copy()
        top_events["text_osm_resolution"] = label_series(top_events["text_osm_resolution"], RESOLUTION_LABELS)
        st.dataframe(top_events, width="stretch", hide_index=True)


def temporal_tab(events: pd.DataFrame, filtered: pd.DataFrame) -> None:
    st.subheader("Historico temporal")
    st.caption(
        "Esta vista valida la capacidad temporal del tablero. La ventana actual es corta, "
        "por lo que no debe interpretarse como tendencia estructural."
    )
    daily = (
        filtered.groupby("event_date", dropna=False)
        .agg(
            events=("uuid", "count"),
            mentions=("mentions", "sum"),
            views=("latest_views", "sum"),
            shares=("latest_shares", "sum"),
            impact_social=("impact_social_score", "sum"),
        )
        .reset_index()
    )
    hourly = (
        filtered.groupby("event_hour", dropna=False)
        .agg(
            events=("uuid", "count"),
            mentions=("mentions", "sum"),
            views=("latest_views", "sum"),
            shares=("latest_shares", "sum"),
            impact_social=("impact_social_score", "sum"),
        )
        .reset_index()
    )

    c1, c2 = st.columns(2)
    c1.line_chart(daily.set_index("event_date")[["events", "mentions"]])
    c2.line_chart(daily.set_index("event_date")[["views", "shares", "impact_social"]])
    st.bar_chart(hourly.set_index("event_hour")[["events", "mentions"]])

    snapshots = load_optional_csv(SNAPSHOTS_PATH)
    if not snapshots.empty:
        snapshots["captured_at_dt"] = pd.to_datetime(snapshots["captured_at"], errors="coerce")
        snapshots["captured_hour"] = snapshots["captured_at_dt"].dt.hour
        snap_hour = snapshots.groupby("captured_hour", dropna=False).agg(
            snapshots=("mention_id", "count"),
            views=("views", lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum()),
            likes=("likes", lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum()),
            shares=("shares", lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum()),
        )
        st.bar_chart(snap_hour[["snapshots", "views", "shares"]])


def engagement_tab(filtered: pd.DataFrame) -> None:
    st.subheader("Engagement e impacto social")
    st.caption(
        "Mide la amplificacion noticiosa/social de los eventos. Esta dimension diferencia la PVN "
        "de un conteo puramente vial."
    )
    total = max(len(filtered), 1)
    metric_row(
        [
            ("Menciones", f"{int(filtered['mentions'].sum()):,}", "publicaciones"),
            ("Views", f"{int(filtered['latest_views'].sum()):,}", "ultimo snapshot"),
            ("Likes", f"{int(filtered['latest_likes'].sum()):,}", "ultimo snapshot"),
            ("Shares", f"{int(filtered['latest_shares'].sum()):,}", "ultimo snapshot"),
            ("Impacto social", f"{filtered['impact_social_score'].sum():,.0f}", "ponderado"),
            ("Eventos con engagement", f"{int((filtered['impact_social_score'] > 0).sum()):,}", pct(int((filtered["impact_social_score"] > 0).sum()), total)),
        ]
    )

    source_summary = load_optional_csv(ENGAGEMENT_SOURCE_PATH)
    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown("**Fuentes segun base expandida**")
        if not source_summary.empty:
            st.dataframe(source_summary, width="stretch", hide_index=True)
            st.bar_chart(source_summary.set_index("source")[["menciones", "eventos"]])
        else:
            st.info("No existe resumen de fuentes expandido.")
    with c2:
        st.markdown("**Fuentes en eventos filtrados**")
        source_filtered = (
            filtered.groupby("source", dropna=False)
            .agg(
                eventos=("uuid", "count"),
                menciones=("mentions", "sum"),
                views=("latest_views", "sum"),
                likes=("latest_likes", "sum"),
                shares=("latest_shares", "sum"),
                impacto=("impact_social_score", "sum"),
            )
            .reset_index()
            .sort_values("menciones", ascending=False)
        )
        st.dataframe(source_filtered, width="stretch", hide_index=True)
        if not source_filtered.empty:
            st.bar_chart(source_filtered.set_index("source")[["menciones", "impacto"]])

    st.markdown("**Eventos con mayor amplificacion social**")
    top_social_cols = [
        "ticketNumber",
        "datetime",
        "department_norm",
        "municipality_norm",
        "address",
        "corridor_norm",
        "severity_class",
        "mentions",
        "latest_views",
        "latest_likes",
        "latest_shares",
        "impact_social_score",
    ]
    top_social = filtered[[col for col in top_social_cols if col in filtered.columns]].sort_values("impact_social_score", ascending=False).head(30).copy()
    if "severity_class" in top_social.columns:
        top_social["severity_class"] = label_series(top_social["severity_class"], SEVERITY_LABELS)
    st.dataframe(top_social, width="stretch", hide_index=True)


def ranking_tab(filtered: pd.DataFrame) -> None:
    st.subheader("Rankings")
    option = st.radio(
        "Ranking",
        options=["Eventos", "Departamentos", "Municipios", "Corredores", "Fuentes"],
        index=0,
        horizontal=True,
    )
    if option == "Eventos":
        st.dataframe(
            filtered.sort_values("impact_social_score", ascending=False)[
                [
                    "ticketNumber",
                    "datetime",
                    "department",
                    "municipality",
                    "address",
                    "mentions",
                    "latest_likes",
                    "latest_comments",
                    "latest_shares",
                    "latest_quotes",
                    "latest_views",
                    "impact_social_score",
                    "metric_score_0_100",
                ]
            ].head(50),
            width="stretch",
            hide_index=True,
        )
    elif option == "Departamentos":
        grouped = filtered.groupby("department_norm").agg(
            events=("uuid", "count"),
            mentions=("mentions", "sum"),
            views=("latest_views", "sum"),
            shares=("latest_shares", "sum"),
            impact_social=("impact_social_score", "sum"),
            avg_metric=("metric_score_0_100", "mean"),
        ).reset_index().sort_values("impact_social", ascending=False)
        st.dataframe(grouped, width="stretch", hide_index=True)
    elif option == "Municipios":
        grouped = filtered.groupby(["department_norm", "municipality_norm"]).agg(
            events=("uuid", "count"),
            mentions=("mentions", "sum"),
            views=("latest_views", "sum"),
            shares=("latest_shares", "sum"),
            impact_social=("impact_social_score", "sum"),
            avg_metric=("metric_score_0_100", "mean"),
        ).reset_index().sort_values("impact_social", ascending=False)
        st.dataframe(grouped, width="stretch", hide_index=True)
    elif option == "Corredores":
        corridor_col = "corridor_norm" if "corridor_norm" in filtered.columns else "corridor_candidate"
        grouped = filtered[filtered[corridor_col].fillna("").astype(str).str.len() > 0].groupby(corridor_col).agg(
            events=("uuid", "count"),
            mentions=("mentions", "sum"),
            views=("latest_views", "sum"),
            shares=("latest_shares", "sum"),
            impact_social=("impact_social_score", "sum"),
            avg_metric=("metric_score_0_100", "mean"),
            osm_high_medium=("osm_match_status", lambda s: int(s.isin(["SPATIAL_OSM_HIGH", "SPATIAL_OSM_MEDIUM"]).sum())),
        ).reset_index().sort_values("impact_social", ascending=False)
        st.dataframe(grouped, width="stretch", hide_index=True)
    else:
        source_summary = load_optional_csv(ENGAGEMENT_SOURCE_PATH)
        st.dataframe(source_summary, width="stretch", hide_index=True)


def corridors_tab(filtered: pd.DataFrame) -> None:
    st.subheader("Corredores: recurrencia, criticidad y robustez")
    st.caption(
        "Analiza la PVN por corredor funcional normalizado. El score es exploratorio: "
        "sirve para priorizar corredores candidatos, no como KPI final."
    )
    show_image(FIG_CORRIDORS_PATH)

    corridor_col = "corridor_norm" if "corridor_norm" in filtered.columns else "corridor_candidate"
    corridor_events = filtered[filtered[corridor_col].fillna("").astype(str).str.strip().ne("")].copy()
    if corridor_events.empty:
        st.info("No hay eventos con corredor en el filtro actual.")
        return

    grouped = (
        corridor_events.groupby(corridor_col, dropna=False)
        .agg(
            events=("uuid", "count"),
            mentions=("mentions", "sum"),
            impact_social=("impact_social_score", "sum"),
            severity_sum=("severity_score", "sum"),
            fatality_events=("fatality_flag", "sum"),
            injury_events=("injury_flag", "sum"),
            vulnerable_events=("vulnerable_user_flag", "sum"),
            osm_high_medium=("osm_match_status", lambda s: int(s.isin(["SPATIAL_OSM_HIGH", "SPATIAL_OSM_MEDIUM"]).sum())),
            review_events=("text_osm_resolution", lambda s: int((s == "REVIEW_COORDINATE_OR_NAME").sum())),
            unresolved_events=("text_osm_resolution", lambda s: int((s == "UNRESOLVED").sum())),
            avg_distance_m=("nearest_osm_distance_m", "mean"),
        )
        .reset_index()
        .sort_values(["events", "impact_social"], ascending=False)
    )
    grouped = grouped.rename(columns={corridor_col: "corridor"})

    rank_metric = st.radio(
        "Ordenar corredores por",
        options=["Eventos", "Menciones", "Impacto social", "Severidad", "Score exploratorio"],
        horizontal=True,
    )
    critical = load_optional_csv(CRITICAL_CORRIDORS_PATH)
    if rank_metric == "Score exploratorio" and not critical.empty:
        grouped = grouped.merge(
            critical[["corridor_norm", "corridor_criticality_score"]],
            left_on="corridor",
            right_on="corridor_norm",
            how="left",
        ).drop(columns=["corridor_norm"], errors="ignore")
        sort_col = "corridor_criticality_score"
    else:
        sort_col = {
            "Eventos": "events",
            "Menciones": "mentions",
            "Impacto social": "impact_social",
            "Severidad": "severity_sum",
        }[rank_metric]
    grouped = grouped.sort_values(sort_col, ascending=False)

    c1, c2 = st.columns([1.05, 1])
    with c1:
        st.markdown("**Ranking del filtro actual**")
        visible_cols = [
            col
            for col in [
                "corridor",
                "events",
                "mentions",
                "impact_social",
                "severity_sum",
                "fatality_events",
                "injury_events",
                "vulnerable_events",
                "osm_high_medium",
                "avg_distance_m",
                "corridor_criticality_score",
            ]
            if col in grouped.columns
        ]
        st.dataframe(grouped[visible_cols].head(30), width="stretch", hide_index=True)
    with c2:
        chart_cols = [col for col in ["events", "mentions", "osm_high_medium"] if col in grouped.columns]
        chart = grouped.head(12).set_index("corridor")[chart_cols]
        st.bar_chart(chart)

    sensitivity = load_optional_csv(SENSITIVITY_PATH)
    if not sensitivity.empty:
        st.markdown("**Robustez por escenarios de pesos**")
        selected_class = st.multiselect(
            "Clasificacion de robustez",
            sorted(sensitivity["clasificacion_robustez"].dropna().unique().tolist()),
            default=sorted(sensitivity["clasificacion_robustez"].dropna().unique().tolist()),
            format_func=lambda value: label_value(value, ROBUSTNESS_LABELS),
        )
        visible = sensitivity[sensitivity["clasificacion_robustez"].isin(selected_class)].sort_values(
            ["frecuencia_top_5", "ranking_promedio"], ascending=[False, True]
        ).copy()
        visible["clasificacion_robustez"] = label_series(visible["clasificacion_robustez"], ROBUSTNESS_LABELS)
        st.dataframe(
            visible,
            width="stretch",
            hide_index=True,
        )
    if not critical.empty:
        with st.expander("Score exploratorio completo de corredores"):
            st.dataframe(critical, width="stretch", hide_index=True)


def unresolved_tab(filtered: pd.DataFrame) -> None:
    st.subheader("No resueltos y recuperacion")
    summary = load_optional_csv(UNRESOLVED_SUMMARY_PATH)
    detail = load_optional_csv(UNRESOLVED_DETAIL_PATH)
    empty = load_optional_csv(EMPTY_CORRIDOR_DETAIL_PATH)
    unnamed = load_optional_csv(UNNAMED_OSM_DETAIL_PATH)
    candidates = load_optional_csv(UNNAMED_OSM_CANDIDATES_PATH)

    unresolved_filtered = filtered[filtered["text_osm_resolution"].eq("UNRESOLVED")].copy()
    empty_filtered = filtered[filtered["corridor_norm"].fillna("").astype(str).str.strip().eq("")].copy()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("UNRESOLVED", f"{len(unresolved_filtered):,}")
    c2.metric("Sin corridor_norm", f"{len(empty_filtered):,}")
    c3.metric("Con coord. SV", f"{int(unresolved_filtered['coordinate_inside_sv_bbox'].sum()):,}")
    c4.metric("Impacto", f"{unresolved_filtered['impact_social_score'].sum():,.0f}")

    if not summary.empty:
        st.markdown("**Causas diagnosticadas**")
        st.dataframe(summary, width="stretch", hide_index=True)
        chart = summary.groupby("unresolved_cause", dropna=False)["events"].sum().sort_values(ascending=False)
        st.bar_chart(chart)

    if not detail.empty:
        st.markdown("**Detalle de casos UNRESOLVED**")
        causes = sorted(detail["unresolved_cause"].dropna().unique().tolist()) if "unresolved_cause" in detail.columns else []
        selected_causes = st.multiselect("Causa", causes, default=causes)
        visible = detail[detail["unresolved_cause"].isin(selected_causes)].copy() if selected_causes else detail
        st.dataframe(
            visible[
                [
                    col
                    for col in [
                        "ticketNumber",
                        "datetime",
                        "department_norm",
                        "municipality_norm",
                        "address",
                        "corridor_norm",
                        "unresolved_cause",
                        "recommended_action",
                        "coordinate_quality_status",
                        "osm_match_status",
                        "mentions",
                        "impact_social_score",
                        "severity_class",
                    ]
                    if col in visible.columns
                ]
            ].sort_values("impact_social_score", ascending=False),
            width="stretch",
            hide_index=True,
        )

    if not unnamed.empty:
        st.markdown("**Investigacion nearest named OSM**")
        status_options = sorted(unnamed["nearest_named_status"].dropna().unique().tolist())
        selected_status = st.multiselect("Estado candidato OSM nombrado", status_options, default=status_options)
        unnamed_visible = unnamed[unnamed["nearest_named_status"].isin(selected_status)].copy()
        st.dataframe(
            unnamed_visible[
                [
                    col
                    for col in [
                        "ticketNumber",
                        "department_norm",
                        "municipality_norm",
                        "address",
                        "candidate_name",
                        "candidate_ref",
                        "candidate_highway",
                        "candidate_road_type",
                        "candidate_distance_m",
                        "nearest_named_status",
                        "text_clues",
                        "investigation_note",
                        "impact_social_score",
                        "severity_class",
                    ]
                    if col in unnamed_visible.columns
                ]
            ].sort_values(["candidate_distance_m", "impact_social_score"], ascending=[True, False]),
            width="stretch",
            hide_index=True,
        )

    if not candidates.empty:
        with st.expander("Todos los candidatos OSM nombrados por caso"):
            st.dataframe(candidates, width="stretch", hide_index=True)


def osm_tab(filtered: pd.DataFrame) -> None:
    st.subheader("OSM / Vias: asociacion evento-via")
    st.caption(
        "Evalua que tan bien los incidentes georreferenciados se conectan con la infraestructura vial OSM "
        "y que tipo de via concentra eventos, menciones e impacto."
    )
    coverage = load_optional_csv(RESULTS_DIR / "diagnostico_cobertura_osm_departamental.csv")
    osm_type = load_optional_csv(RESULTS_DIR / "ranking_tipo_via_osm_nacional.csv")
    total = max(len(filtered), 1)
    high_medium = int(filtered["osm_match_status"].isin(["SPATIAL_OSM_HIGH", "SPATIAL_OSM_MEDIUM"]).sum())
    no_coord = int(filtered["osm_match_status"].eq("NO_COORDINATE_FOR_OSM").sum())
    avg_distance = filtered.loc[
        filtered["nearest_osm_distance_m"].notna() & filtered["osm_match_status"].isin(["SPATIAL_OSM_HIGH", "SPATIAL_OSM_MEDIUM"]),
        "nearest_osm_distance_m",
    ].mean()

    metric_row(
        [
            ("OSM alto/medio", f"{high_medium:,}", pct(high_medium, total)),
            ("Sin coordenada OSM", f"{no_coord:,}", pct(no_coord, total)),
            ("Distancia media", f"{avg_distance:,.1f} m" if pd.notna(avg_distance) else "Sin dato", "alto/medio"),
            ("Tipos de via", f"{filtered['nearest_osm_road_type'].dropna().nunique():,}", "OSM"),
        ]
    )

    c1, c2 = st.columns([1, 1])
    with c1:
        show_image(FIG_MAP_PATH)
    with c2:
        source_scope = label_series(
            filtered["nearest_osm_source_scope"].fillna("SIN_FUENTE_OSM").replace("", "SIN_FUENTE_OSM"),
            SOURCE_SCOPE_LABELS,
        ).value_counts()
        match_status = label_series(filtered["osm_match_status"], OSM_STATUS_LABELS).value_counts()
        st.markdown("**Fuente OSM usada**")
        st.bar_chart(source_scope)
        st.markdown("**Estado de match OSM**")
        st.bar_chart(match_status)

    if not osm_type.empty:
        st.markdown("**Tipo de via OSM asociado**")
        visible_osm_type = osm_type.copy()
        visible_osm_type["nearest_osm_road_type"] = label_series(visible_osm_type["nearest_osm_road_type"], ROAD_TYPE_LABELS)
        st.dataframe(visible_osm_type, width="stretch", hide_index=True)
        chart = visible_osm_type.set_index("nearest_osm_road_type")[["events", "mentions"]]
        st.bar_chart(chart)
    if not coverage.empty:
        st.markdown("**Cobertura departamental descargada**")
        c_metrics = st.columns(3)
        c_metrics[0].metric("Departamentos OK", f"{int((coverage['status'] == 'OK').sum()):,}")
        c_metrics[1].metric("Segmentos OSM", f"{int(coverage['segments'].sum()):,}")
        c_metrics[2].metric("Km acumulados", f"{coverage['length_km'].sum():,.1f}")
        st.dataframe(coverage, width="stretch", hide_index=True)


def quality_tab(events: pd.DataFrame, filtered: pd.DataFrame) -> None:
    st.subheader("Calidad del dato y brechas metodologicas")
    st.caption(
        "Diagnostica que tan confiables son los resultados: coordenadas, repeticion, match OSM, "
        "resolucion texto-via y causas de casos no resueltos."
    )
    coord_valid = int(filtered["coordinate_inside_sv_bbox"].sum())
    repeated_count = int(filtered["repeated_coordinate_flag"].sum()) if "repeated_coordinate_flag" in filtered.columns else 0
    missing_count = int(filtered["coordinate_quality_status"].eq("MISSING_POINT").sum())
    unresolved_count = int(filtered["text_osm_resolution"].eq("UNRESOLVED").sum())
    metric_row(
        [
            ("Coord. validas SV", f"{coord_valid:,}", pct(coord_valid, max(len(filtered), 1))),
            ("Coordenadas repetidas", f"{repeated_count:,}", pct(repeated_count, max(len(filtered), 1))),
            ("Sin coordenada", f"{missing_count:,}", pct(missing_count, max(len(filtered), 1))),
            ("No resueltos", f"{unresolved_count:,}", pct(unresolved_count, max(len(filtered), 1))),
        ]
    )

    c1, c2 = st.columns(2)
    coords = load_optional_csv(COORDS_PATH).copy()
    if not coords.empty and "coordinate_quality_status" in coords.columns:
        coords["coordinate_quality_status"] = label_series(coords["coordinate_quality_status"], COORD_STATUS_LABELS)
    c1.markdown("**Diagnostico de coordenadas**")
    c1.dataframe(coords, width="stretch", hide_index=True)
    c2.markdown("**Diagnostico de integridad**")
    c2.dataframe(load_optional_csv(INTEGRITY_PATH), width="stretch", hide_index=True)

    summary = load_optional_csv(UNRESOLVED_SUMMARY_PATH)
    detail = load_optional_csv(UNRESOLVED_DETAIL_PATH)
    unnamed = load_optional_csv(UNNAMED_OSM_DETAIL_PATH)
    candidates = load_optional_csv(UNNAMED_OSM_CANDIDATES_PATH)

    if not summary.empty:
        st.markdown("**Causas de no resolucion**")
        st.dataframe(summary, width="stretch", hide_index=True)
        chart = summary.groupby("unresolved_cause", dropna=False)["events"].sum().sort_values(ascending=False)
        st.bar_chart(chart)

    with st.expander("Coordenadas fuera de El Salvador", expanded=False):
        outside = events[events["coordinate_quality_status"] == "OUTSIDE_EL_SALVADOR_BBOX"][
            [
                "ticketNumber",
                "datetime",
                "department",
                "department_norm",
                "municipality",
                "municipality_norm",
                "latitude_num",
                "longitude_num",
                "address",
                "observation",
            ]
        ]
        st.dataframe(outside, width="stretch", hide_index=True)

    with st.expander("Coordenadas repetidas", expanded=False):
        repeated = events[events["repeated_coordinate_flag"] == True][
            [
                "coordinate_key_6dec",
                "coordinate_reuse_count",
                "ticketNumber",
                "datetime",
                "department",
                "department_norm",
                "municipality",
                "municipality_norm",
                "address",
                "impact_social_score",
            ]
        ].sort_values(["coordinate_reuse_count", "coordinate_key_6dec"], ascending=[False, True])
        st.dataframe(repeated, width="stretch", hide_index=True)

    with st.expander("Sin coordenada", expanded=False):
        missing = events[events["coordinate_quality_status"] == "MISSING_POINT"][
            [
                "ticketNumber",
                "datetime",
                "department",
                "department_norm",
                "municipality",
                "municipality_norm",
                "address",
                "corridor_candidate",
                "mentions",
                "impact_social_score",
            ]
        ].sort_values("impact_social_score", ascending=False)
        st.dataframe(missing, width="stretch", hide_index=True)

    if not detail.empty:
        with st.expander("Detalle de casos no resueltos", expanded=False):
            st.dataframe(detail, width="stretch", hide_index=True)

    if not unnamed.empty:
        with st.expander("Investigacion OSM sin nombre/ref", expanded=False):
            st.dataframe(unnamed, width="stretch", hide_index=True)

    if not candidates.empty:
        with st.expander("Candidatos OSM nombrados por caso", expanded=False):
            st.dataframe(candidates, width="stretch", hide_index=True)


def detail_tab(filtered: pd.DataFrame) -> None:
    st.subheader("Detalle de eventos filtrados")
    st.caption(
        "Tabla operativa para revisar, ordenar y exportar los eventos que explican los resultados del tablero."
    )
    detail_cols = [
        "ticketNumber",
        "datetime",
        "incident",
        "department_norm",
        "municipality_norm",
        "address",
        "corridor_norm",
        "severity_class",
        "mentions",
        "latest_views",
        "latest_likes",
        "latest_shares",
        "impact_social_score",
        "coordinate_quality_status",
        "osm_match_status",
        "text_osm_resolution",
        "nearest_osm_name",
        "nearest_osm_ref",
        "nearest_osm_road_type",
        "nearest_osm_distance_m",
        "metric_score_0_100",
        "metric_category",
    ]
    visible = filtered[[col for col in detail_cols if col in filtered.columns]].sort_values(
        ["impact_social_score", "mentions"], ascending=False
    ).copy()
    for col, labels in [
        ("severity_class", SEVERITY_LABELS),
        ("coordinate_quality_status", COORD_STATUS_LABELS),
        ("osm_match_status", OSM_STATUS_LABELS),
        ("text_osm_resolution", RESOLUTION_LABELS),
        ("nearest_osm_road_type", ROAD_TYPE_LABELS),
    ]:
        if col in visible.columns:
            visible[col] = label_series(visible[col], labels)

    st.download_button(
        "Descargar eventos filtrados CSV",
        data=visible.to_csv(index=False).encode("utf-8"),
        file_name="eventos_filtrados_pvn.csv",
        mime="text/csv",
    )
    st.dataframe(visible, width="stretch", hide_index=True)


def main() -> None:
    require_outputs()
    events = load_events()
    filtered = filter_events(events)

    st.title("Dashboard analitico de Presion Vial Noticiosa")
    st.caption(
        "Base principal: Data/News/incidentes.csv. POC para analizar eventos viales noticiosos, "
        "asociacion evento-via, corredores, temporalidad, engagement y calidad del dato."
    )

    tabs = st.tabs(["Resumen", "Mapa PVN", "Corredores", "Temporal", "Engagement", "OSM / Vias", "Calidad", "Detalle"])
    with tabs[0]:
        summary_tab(events, filtered)
    with tabs[1]:
        map_tab(events, filtered)
    with tabs[2]:
        corridors_tab(filtered)
    with tabs[3]:
        temporal_tab(events, filtered)
    with tabs[4]:
        engagement_tab(filtered)
    with tabs[5]:
        osm_tab(filtered)
    with tabs[6]:
        quality_tab(events, filtered)
    with tabs[7]:
        detail_tab(filtered)


if __name__ == "__main__":
    main()
