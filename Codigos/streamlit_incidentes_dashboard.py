#!/usr/bin/env python3
"""
Dashboard Streamlit para incidentes.csv.

Ejecutar:
    streamlit run Codigos/streamlit_incidentes_dashboard.py
"""

from __future__ import annotations

import json
import time
import unicodedata
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "Results" / "News" / "Incidentes"
OSM_SEGMENTS_PATH = ROOT / "Data" / "Processed" / "osm_roads_san_salvador" / "osm_road_segments.csv"
OSM_DEPARTMENTS_DIR = ROOT / "Data" / "Processed" / "osm_roads_departments"
OSM_NATIONAL_SEGMENTS_PATH = ROOT / "Data" / "Processed" / "osm_roads_nacional" / "osm_road_segments.csv"
WAZE_JAMS_SEGMENTS_PATH = ROOT / "Results" / "Waze" / "Jams" / "waze_jams_osm_segments_enriched.csv"
WAZE_JAMS_UNIQUE_PATH = ROOT / "Results" / "Waze" / "Jams" / "waze_jams_unique_enriched.csv"
WAZE_JAMS_LAYERS_PATH = ROOT / "Results" / "Waze" / "Jams" / "waze_jams_corridor_layers.csv"
WAZE_ALERTS_POINTS_PATH = ROOT / "Results" / "Waze" / "Alerts" / "waze_alerts_unique_enriched.csv"
WAZE_ALERTS_LAYERS_PATH = ROOT / "Results" / "Waze" / "Alerts" / "waze_alerts_corridor_layers.csv"
WAZE_INTEGRATED_SUMMARY_PATH = ROOT / "Results" / "Waze" / "Integrated" / "waze_integrated_corridor_summary.csv"
WAZE_INTEGRATED_HOUR_PATH = ROOT / "Results" / "Waze" / "Integrated" / "waze_integrated_corridor_hour.csv"
SIMULATION_DATE = "2026-06-29"
EL_SALVADOR_TZ = "America/El_Salvador"

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

ANALYSIS_MODES = [
    "1. Estado de la red",
    "2. Congestion operacional",
    "3. Eventos Waze",
    "4. Relacion congestion-eventos",
    "5. Social / noticias",
    "6. Calidad y trazabilidad",
]

ALERT_GROUP_COLORS = {
    "ACCIDENTE": [220, 38, 38, 230],
    "CIERRE_VIAL": [17, 24, 39, 235],
    "TRAFICO_DETENIDO": [245, 158, 11, 225],
    "TRAFICO_PESADO": [234, 179, 8, 220],
    "CONGESTION_REPORTADA": [249, 115, 22, 220],
    "PELIGRO_EN_VIA": [168, 85, 247, 225],
    "BACHE": [120, 113, 108, 220],
    "OBRA_CARRIL_CERRADO": [14, 165, 233, 220],
    "VEHICULO_DETENIDO": [59, 130, 246, 220],
    "OBJETO_EN_VIA": [20, 184, 166, 220],
    "FALLA_SEMAFORO": [236, 72, 153, 225],
    "CLIMA_RIESGO": [6, 182, 212, 220],
}

QUADRANT_COLORS = {
    "ALTA_CONGESTION_ALTAS_ALERTAS": [220, 38, 38, 230],
    "ALTA_CONGESTION_BAJAS_ALERTAS": [37, 99, 235, 220],
    "BAJA_CONGESTION_ALTAS_ALERTAS": [245, 158, 11, 225],
    "BAJA_CONGESTION_BAJAS_ALERTAS": [100, 116, 139, 145],
}

QUADRANT_LABELS = {
    "ALTA_CONGESTION_ALTAS_ALERTAS": "Alta congestion + altas alertas",
    "ALTA_CONGESTION_BAJAS_ALERTAS": "Alta congestion + bajas alertas",
    "BAJA_CONGESTION_ALTAS_ALERTAS": "Baja congestion + altas alertas",
    "BAJA_CONGESTION_BAJAS_ALERTAS": "Baja congestion + bajas alertas",
}

TEMPORAL_STATE_COLORS = {
    "ALERTS_JAMS": [220, 38, 38, 230],
    "JAMS_ONLY": [37, 99, 235, 220],
    "ALERTS_ONLY": [245, 158, 11, 225],
    "NO_ACTIVITY": [100, 116, 139, 80],
}

TEMPORAL_STATE_LABELS = {
    "ALERTS_JAMS": "Alerts + jams",
    "JAMS_ONLY": "Jams sin alerts",
    "ALERTS_ONLY": "Alerts sin jams",
    "NO_ACTIVITY": "Sin actividad",
}

TEMPORAL_SOURCE_COLORS = {
    "Waze Jams": [220, 38, 38, 230],
    "Waze Alerts": [245, 158, 11, 225],
    "Noticias/incidentes": [37, 99, 235, 220],
    "Heatmap dinamico": [168, 85, 247, 190],
}

TEMPORAL_HEATMAP_COLORS = [
    [30, 64, 175, 35],
    [14, 165, 233, 95],
    [250, 204, 21, 165],
    [220, 38, 38, 235],
]

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


def normalize_key_text(value: object) -> str:
    if pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    for char in ["/", "-", "_", ",", ".", ":", ";", "(", ")", "[", "]"]:
        text = text.replace(char, " ")
    return " ".join(text.split())


def minute_label(minute_of_day: int | float) -> str:
    minute = int(minute_of_day)
    return f"{minute // 60:02d}:{minute % 60:02d}"


def temporal_window_bounds(
    current_minute: int,
    mode: str,
    window_minutes: int,
    frame_minutes: int,
) -> tuple[int, int, str]:
    if mode == "Acumulado hasta el momento":
        start_minute = 0
        label = f"00:00 - {minute_label(current_minute)}"
    elif mode == "Ventana movil":
        start_minute = max(0, current_minute - window_minutes)
        label = f"{minute_label(start_minute)} - {minute_label(current_minute)}"
    else:
        start_minute = max(0, current_minute - frame_minutes)
        label = f"{minute_label(start_minute)} - {minute_label(current_minute)}"
    return start_minute, current_minute, label


def filter_temporal_frame(
    data: pd.DataFrame,
    minute_col: str,
    start_minute: int,
    end_minute: int,
) -> pd.DataFrame:
    if data.empty or minute_col not in data.columns:
        return data.iloc[0:0].copy()
    minutes = pd.to_numeric(data[minute_col], errors="coerce")
    return data[minutes.between(start_minute, end_minute, inclusive="both")].copy()


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


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def interpolate_color(value: float, stops: list[tuple[float, list[int]]]) -> list[int]:
    value = clamp(float(value), 0.0, 1.0)
    for idx in range(len(stops) - 1):
        left_pos, left_color = stops[idx]
        right_pos, right_color = stops[idx + 1]
        if left_pos <= value <= right_pos:
            span = max(right_pos - left_pos, 1e-9)
            t = (value - left_pos) / span
            return [
                int(left_color[channel] + (right_color[channel] - left_color[channel]) * t)
                for channel in range(4)
            ]
    return stops[-1][1]


def metric_color(value: float, mode: str = "pressure") -> list[int]:
    palettes = {
        "pressure": [
            (0.00, [148, 163, 184, 80]),
            (0.35, [250, 204, 21, 150]),
            (0.65, [249, 115, 22, 205]),
            (1.00, [220, 38, 38, 235]),
        ],
        "jams": [
            (0.00, [59, 130, 246, 90]),
            (0.35, [34, 197, 94, 145]),
            (0.65, [245, 158, 11, 205]),
            (1.00, [220, 38, 38, 235]),
        ],
        "alerts": [
            (0.00, [148, 163, 184, 80]),
            (0.35, [168, 85, 247, 145]),
            (0.65, [236, 72, 153, 205]),
            (1.00, [220, 38, 38, 235]),
        ],
    }
    return interpolate_color(value, palettes.get(mode, palettes["pressure"]))


def robust_scale(series: pd.Series, lower: float = 0, upper_q: float = 0.95) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").fillna(0).clip(lower=lower)
    upper = values.quantile(upper_q)
    if pd.isna(upper) or upper <= 0:
        upper = values.max()
    if pd.isna(upper) or upper <= 0:
        return values * 0
    return (values / upper).clip(0, 1)


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


@st.cache_data(show_spinner=False)
def load_national_segments(major_only: bool = True) -> pd.DataFrame:
    if not OSM_NATIONAL_SEGMENTS_PATH.exists():
        return pd.DataFrame()
    segments = read_segments_file(OSM_NATIONAL_SEGMENTS_PATH, major_only)
    if segments.empty:
        return segments
    for col in ["length_m", "lanes", "maxspeed"]:
        if col in segments.columns:
            segments[col] = pd.to_numeric(segments[col], errors="coerce")
    segments["path"] = segments["geometry_json"].map(parse_path)
    segments["color"] = segments["highway"].map(lambda v: HIGHWAY_STYLES.get(v, {}).get("color", [100, 115, 130, 55]))
    segments["width"] = segments["highway"].map(lambda v: HIGHWAY_STYLES.get(v, {}).get("width", 0.65))
    segments["length_km"] = segments["length_m"] / 1000
    return segments.drop(columns=["geometry_json"])


@st.cache_data(show_spinner=False)
def load_osm_segments_by_keys(keys: tuple[str, ...], major_only: bool = True) -> pd.DataFrame:
    if not keys or not OSM_NATIONAL_SEGMENTS_PATH.exists():
        return pd.DataFrame()
    key_set = set(str(key) for key in keys if str(key).strip())
    usecols = [
        "source_department",
        "osm_way_id",
        "name",
        "ref",
        "highway",
        "oneway",
        "lanes",
        "maxspeed",
        "surface",
        "length_m",
        "road_key_norm",
        "road_type_category",
        "geometry_json",
    ]
    segments = pd.read_csv(OSM_NATIONAL_SEGMENTS_PATH, usecols=lambda col: col in usecols, low_memory=False)
    segments = segments[segments["road_key_norm"].astype(str).isin(key_set)].copy()
    if major_only and "highway" in segments.columns:
        segments = segments[segments["highway"].isin(DEFAULT_MAJOR_HIGHWAYS)].copy()
    if segments.empty:
        return segments
    for col in ["length_m", "lanes", "maxspeed"]:
        if col in segments.columns:
            segments[col] = pd.to_numeric(segments[col], errors="coerce")
    segments["path"] = segments["geometry_json"].map(parse_path)
    segments["length_km"] = segments["length_m"] / 1000
    segments["color"] = segments["highway"].map(lambda v: HIGHWAY_STYLES.get(v, {}).get("color", [100, 115, 130, 55]))
    segments["width"] = segments["highway"].map(lambda v: HIGHWAY_STYLES.get(v, {}).get("width", 0.65))
    return segments.drop(columns=["geometry_json"])


@st.cache_data(show_spinner=False)
def load_waze_jam_segments() -> pd.DataFrame:
    if not WAZE_JAMS_SEGMENTS_PATH.exists():
        return pd.DataFrame()
    segments = pd.read_csv(WAZE_JAMS_SEGMENTS_PATH, low_memory=False)
    if segments.empty:
        return segments
    for col in [
        "length_m",
        "jams_count_total",
        "corridor_delay_burden",
        "corridor_congestion_load",
        "corridor_speed_collapse_rate",
        "active_congestion_hours",
        "corridor_jam_pressure_score",
    ]:
        if col in segments.columns:
            segments[col] = pd.to_numeric(segments[col], errors="coerce").fillna(0)
    segments["path"] = segments["geometry_json"].map(parse_path)
    segments["length_km"] = segments["length_m"] / 1000
    return segments.drop(columns=["geometry_json"])


@st.cache_data(show_spinner=False)
def load_waze_alert_points() -> pd.DataFrame:
    if not WAZE_ALERTS_POINTS_PATH.exists():
        return pd.DataFrame()
    alerts = pd.read_csv(WAZE_ALERTS_POINTS_PATH, low_memory=False)
    for col in [
        "lon",
        "lat",
        "event_hour",
        "cluster_report_count",
        "severity_proxy",
        "alert_impact_score",
        "nearest_osm_distance_m",
    ]:
        if col in alerts.columns:
            alerts[col] = pd.to_numeric(alerts[col], errors="coerce")
    alerts = alerts[alerts["lon"].notna() & alerts["lat"].notna()].copy()
    alerts["alert_color"] = alerts["alert_group"].map(lambda value: ALERT_GROUP_COLORS.get(str(value), [100, 116, 139, 190]))
    alerts["alert_radius"] = (5 + alerts["alert_impact_score"].fillna(0).clip(lower=0).pow(0.55) * 0.75).clip(5, 24)
    return alerts


@st.cache_data(show_spinner=False)
def load_waze_alert_corridor_layers() -> pd.DataFrame:
    return load_optional_csv(WAZE_ALERTS_LAYERS_PATH)


@st.cache_data(show_spinner=False)
def load_integrated_summary() -> pd.DataFrame:
    return load_optional_csv(WAZE_INTEGRATED_SUMMARY_PATH)


@st.cache_data(show_spinner=False)
def load_integrated_hour() -> pd.DataFrame:
    return load_optional_csv(WAZE_INTEGRATED_HOUR_PATH)


@st.cache_data(show_spinner=False)
def load_temporal_jams() -> pd.DataFrame:
    if not WAZE_JAMS_UNIQUE_PATH.exists():
        return pd.DataFrame()
    jams = pd.read_csv(WAZE_JAMS_UNIQUE_PATH, low_memory=False)
    if jams.empty:
        return jams
    time_source = "datetime_local" if "datetime_local" in jams.columns else "ts_first"
    local_time = pd.to_datetime(jams[time_source], errors="coerce", utc=True).dt.tz_convert(EL_SALVADOR_TZ)
    jams["temporal_datetime_local"] = local_time.dt.strftime("%Y-%m-%d %H:%M:%S")
    jams["temporal_date_local"] = local_time.dt.strftime("%Y-%m-%d")
    jams["temporal_minute_of_day"] = (local_time.dt.hour * 60 + local_time.dt.minute).astype("Int64")
    jams = jams[jams["temporal_date_local"].eq(SIMULATION_DATE) & jams["temporal_minute_of_day"].notna()].copy()
    numeric_cols = [
        "delay_mean",
        "delay_max",
        "length_km",
        "congestion_load",
        "jam_intensity_score",
        "congestion_reliability_proxy",
        "speed_mean",
        "speed_min",
        "level_mean",
        "level_max",
        "records_per_uuid",
    ]
    for col in numeric_cols:
        if col in jams.columns:
            jams[col] = pd.to_numeric(jams[col], errors="coerce").fillna(0)
    for col in ["severe_jam_flag", "extreme_jam_flag", "speed_collapse_flag"]:
        if col in jams.columns:
            jams[col] = jams[col].map(lambda value: str(value).strip().lower() == "true")
    corridor_text = jams.get("corridor_norm_waze", pd.Series(index=jams.index, dtype=object)).fillna("")
    fallback_text = jams.get("street_norm", pd.Series(index=jams.index, dtype=object)).fillna("")
    corridor_text = corridor_text.where(corridor_text.astype(str).str.upper().ne("UNRESOLVED"), fallback_text)
    jams["corridor_norm_key"] = corridor_text.map(normalize_key_text)
    jams["corridor_name"] = jams.get("corridor_norm_waze", pd.Series(index=jams.index, dtype=object)).fillna(
        jams.get("street_modal", pd.Series(index=jams.index, dtype=object))
    )
    jams = jams[jams["corridor_norm_key"].ne("") & jams["corridor_norm_key"].ne("unresolved")].copy()
    return jams


@st.cache_data(show_spinner=False)
def load_temporal_alerts() -> pd.DataFrame:
    alerts = load_waze_alert_points().copy()
    if alerts.empty:
        return alerts
    local_time = pd.to_datetime(alerts["datetime_local"], errors="coerce", utc=True).dt.tz_convert(EL_SALVADOR_TZ)
    alerts["temporal_datetime_local"] = local_time.dt.strftime("%Y-%m-%d %H:%M:%S")
    alerts["temporal_date_local"] = local_time.dt.strftime("%Y-%m-%d")
    alerts["temporal_minute_of_day"] = (local_time.dt.hour * 60 + local_time.dt.minute).astype("Int64")
    alerts = alerts[alerts["temporal_date_local"].eq(SIMULATION_DATE) & alerts["temporal_minute_of_day"].notna()].copy()
    for col in ["is_critical_alert", "is_safety_alert", "is_operational_alert"]:
        if col in alerts.columns:
            alerts[col] = alerts[col].map(lambda value: str(value).strip().lower() == "true")
    alerts["corridor_norm_key"] = alerts.get("corridor_norm_alert", pd.Series(index=alerts.index, dtype=object)).map(normalize_key_text)
    return alerts


def load_temporal_news(events: pd.DataFrame) -> pd.DataFrame:
    news = events.copy()
    local_time = pd.to_datetime(news["datetime"], errors="coerce")
    news["temporal_datetime_local"] = local_time.dt.strftime("%Y-%m-%d %H:%M:%S")
    news["temporal_date_local"] = local_time.dt.strftime("%Y-%m-%d")
    news["temporal_minute_of_day"] = (local_time.dt.hour * 60 + local_time.dt.minute).astype("Int64")
    news = news[news["temporal_date_local"].eq(SIMULATION_DATE) & news["temporal_minute_of_day"].notna()].copy()
    news["corridor_norm_key"] = news.get("corridor_norm", pd.Series(index=news.index, dtype=object)).map(normalize_key_text)
    news["temporal_news_color"] = [[37, 99, 235, 225] for _ in range(len(news))]
    if "severity_class" in news.columns:
        news["temporal_news_color"] = news["severity_class"].map(lambda value: SEVERITY_COLORS.get(str(value), [37, 99, 235, 225]))
    news["temporal_news_radius"] = (
        5
        + news.get("impact_social_score", pd.Series(0, index=news.index)).fillna(0).clip(lower=0).pow(0.5) * 0.45
        + news.get("mentions", pd.Series(0, index=news.index)).fillna(0).clip(lower=0) * 0.15
    ).clip(5, 22)
    return news


def summarize_temporal_jams(jams_visible: pd.DataFrame, top_n: int) -> pd.DataFrame:
    if jams_visible.empty:
        return pd.DataFrame()
    grouped = (
        jams_visible.groupby("corridor_norm_key", dropna=False)
        .agg(
            corridor_name=("corridor_name", "first"),
            visible_jams=("uuid", "count"),
            visible_delay_min=("delay_mean", "sum"),
            visible_congestion_load=("congestion_load", "sum"),
            visible_jam_intensity=("jam_intensity_score", "mean"),
            visible_length_km=("length_km", "sum"),
            visible_speed_min=("speed_min", "min"),
            visible_speed_avg=("speed_mean", "mean"),
            visible_active_minutes=("temporal_minute_of_day", "nunique"),
            severe_jams=("severe_jam_flag", "sum"),
            extreme_jams=("extreme_jam_flag", "sum"),
            speed_collapse_jams=("speed_collapse_flag", "sum"),
            reliability_avg=("congestion_reliability_proxy", "mean"),
        )
        .reset_index()
    )
    count_score = robust_scale(grouped["visible_jams"])
    delay_score = robust_scale(grouped["visible_delay_min"])
    load_score = robust_scale(grouped["visible_congestion_load"])
    intensity_score = robust_scale(grouped["visible_jam_intensity"])
    grouped["temporal_jam_pressure"] = (
        100 * (0.30 * count_score + 0.30 * delay_score + 0.25 * load_score + 0.15 * intensity_score)
    ).round(3)
    return grouped.sort_values("temporal_jam_pressure", ascending=False).head(top_n)


def build_temporal_corridor_ranking(
    jam_summary: pd.DataFrame,
    alerts_visible: pd.DataFrame,
    news_visible: pd.DataFrame,
) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if not jam_summary.empty:
        frames.append(
            jam_summary[
                [
                    "corridor_norm_key",
                    "corridor_name",
                    "visible_jams",
                    "visible_delay_min",
                    "visible_congestion_load",
                    "temporal_jam_pressure",
                ]
            ].copy()
        )
    if not alerts_visible.empty:
        alert_grouped = (
            alerts_visible[alerts_visible["corridor_norm_key"].ne("")]
            .groupby("corridor_norm_key", dropna=False)
            .agg(
                corridor_name=("corridor_norm_alert", "first"),
                visible_alerts=("uuid", "count"),
                alert_impact=("alert_impact_score", "sum"),
                critical_alerts=("is_critical_alert", "sum"),
            )
            .reset_index()
        )
        frames.append(alert_grouped)
    if not news_visible.empty:
        news_grouped = (
            news_visible[news_visible["corridor_norm_key"].ne("")]
            .groupby("corridor_norm_key", dropna=False)
            .agg(
                corridor_name=("corridor_norm", "first"),
                visible_news=("uuid", "count"),
                news_impact=("impact_social_score", "sum"),
                news_mentions=("mentions", "sum"),
            )
            .reset_index()
        )
        frames.append(news_grouped)
    if not frames:
        return pd.DataFrame()
    ranking = frames[0]
    for frame in frames[1:]:
        ranking = ranking.merge(frame, on="corridor_norm_key", how="outer", suffixes=("", "_alt"))
        if "corridor_name_alt" in ranking.columns:
            ranking["corridor_name"] = ranking["corridor_name"].fillna(ranking["corridor_name_alt"])
            ranking = ranking.drop(columns=["corridor_name_alt"])
    for col in [
        "visible_jams",
        "visible_delay_min",
        "visible_congestion_load",
        "temporal_jam_pressure",
        "visible_alerts",
        "alert_impact",
        "critical_alerts",
        "visible_news",
        "news_impact",
        "news_mentions",
    ]:
        if col not in ranking.columns:
            ranking[col] = 0
        ranking[col] = pd.to_numeric(ranking[col], errors="coerce").fillna(0)
    ranking["dynamic_corridor_pressure"] = (
        100
        * (
            0.45 * robust_scale(ranking["temporal_jam_pressure"])
            + 0.35 * robust_scale(ranking["alert_impact"])
            + 0.20 * robust_scale(ranking["news_impact"])
        )
    ).round(3)
    return ranking.sort_values("dynamic_corridor_pressure", ascending=False)


def style_metric_segments(
    data: pd.DataFrame,
    value_col: str,
    width_col: str | None,
    color_mode: str,
    max_width: float = 8.0,
    min_width: float = 1.5,
    score_scale: bool = False,
) -> pd.DataFrame:
    if data.empty:
        return data
    styled = data.copy()
    values = pd.to_numeric(styled[value_col], errors="coerce").fillna(0)
    scaled = (values / 100).clip(0, 1) if score_scale else robust_scale(values)
    styled["render_color"] = scaled.map(lambda value: metric_color(float(value), color_mode))
    if width_col and width_col in styled.columns:
        width_scaled = robust_scale(styled[width_col])
    else:
        width_scaled = scaled
    styled["render_width"] = (min_width + width_scaled * (max_width - min_width)).clip(min_width, max_width)
    styled["metric_value"] = values.round(3)
    styled["metric_name"] = value_col
    styled["highway_label"] = styled.get("highway", pd.Series(index=styled.index, dtype=object)).map(
        lambda value: label_value(value, HIGHWAY_LABELS)
    )
    return styled


def style_quadrant_segments(data: pd.DataFrame) -> pd.DataFrame:
    styled = data.copy()
    styled["render_color"] = styled["quadrant"].map(lambda value: QUADRANT_COLORS.get(str(value), [100, 116, 139, 120]))
    styled["render_width"] = (1.8 + robust_scale(styled["integrated_corridor_pressure"]) * 5.5).clip(1.8, 7.5)
    styled["quadrant_label"] = styled["quadrant"].map(lambda value: label_value(value, QUADRANT_LABELS))
    styled["highway_label"] = styled.get("highway", pd.Series(index=styled.index, dtype=object)).map(
        lambda value: label_value(value, HIGHWAY_LABELS)
    )
    return styled


def style_temporal_segments(data: pd.DataFrame) -> pd.DataFrame:
    styled = data.copy()
    def state(row: pd.Series) -> str:
        if bool(row.get("has_jam")) and bool(row.get("has_alert")):
            return "ALERTS_JAMS"
        if bool(row.get("has_jam")):
            return "JAMS_ONLY"
        if bool(row.get("has_alert")):
            return "ALERTS_ONLY"
        return "NO_ACTIVITY"

    styled["temporal_state"] = styled.apply(state, axis=1)
    styled["temporal_state_label"] = styled["temporal_state"].map(lambda value: label_value(value, TEMPORAL_STATE_LABELS))
    styled["render_color"] = styled["temporal_state"].map(lambda value: TEMPORAL_STATE_COLORS.get(str(value), [100, 116, 139, 90]))
    styled["render_width"] = (1.8 + robust_scale(styled["integrated_corridor_hour_pressure"]) * 5.5).clip(1.8, 7.5)
    styled["highway_label"] = styled.get("highway", pd.Series(index=styled.index, dtype=object)).map(
        lambda value: label_value(value, HIGHWAY_LABELS)
    )
    return styled


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


def path_view_state(segments: pd.DataFrame, fallback_zoom: float = 8.2) -> pdk.ViewState:
    if segments.empty or "path" not in segments.columns:
        return pdk.ViewState(latitude=13.70, longitude=-89.20, zoom=fallback_zoom, pitch=0, bearing=0)
    points: list[list[float]] = []
    for path in segments["path"].head(6000):
        if isinstance(path, list):
            points.extend(path)
    if not points:
        return pdk.ViewState(latitude=13.70, longitude=-89.20, zoom=fallback_zoom, pitch=0, bearing=0)
    lons = [point[0] for point in points]
    lats = [point[1] for point in points]
    return pdk.ViewState(
        latitude=float((min(lats) + max(lats)) / 2),
        longitude=float((min(lons) + max(lons)) / 2),
        zoom=fallback_zoom,
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


def analytical_path_layer(data: pd.DataFrame, layer_id: str) -> pdk.Layer:
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
                "highway_label",
                "oneway",
                "lanes",
                "maxspeed",
                "surface",
                "length_km",
                "road_type_category",
                "corridor_name",
                "corridor_norm_waze",
                "corridor_norm_alert",
                "corridor_norm_key",
                "road_key_norm",
                "integrated_corridor_pressure",
                "integrated_corridor_hour_pressure",
                "jam_pressure_norm",
                "alert_pressure_norm",
                "corridor_event_congestion_coupling",
                "integration_priority",
                "quadrant_label",
                "temporal_state_label",
                "event_hour",
                "jam_count",
                "alert_count",
                "same_hour_overlap_count",
                "integrated_active_hours",
                "corridor_jam_pressure_score",
                "jams_count_total",
                "corridor_delay_burden",
                "corridor_congestion_load",
                "corridor_speed_collapse_rate",
                "active_congestion_hours",
                "corridor_alert_pressure",
                "alerts_count_total",
                "reports_count_total",
                "corridor_alert_impact",
                "active_alert_hours",
                "temporal_jam_pressure",
                "visible_jams",
                "visible_delay_min",
                "visible_congestion_load",
                "visible_jam_intensity",
                "visible_active_minutes",
                "severe_jams",
                "extreme_jams",
                "speed_collapse_jams",
                "metric_name",
                "metric_value",
            ],
        ),
        id=layer_id,
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


def waze_alert_scatter_layer(data: pd.DataFrame) -> pdk.Layer:
    return pdk.Layer(
        "ScatterplotLayer",
        data=deck_records(
            data,
            [
                "lon",
                "lat",
                "alert_color",
                "alert_radius",
                "uuid",
                "datetime_local",
                "event_hour",
                "type",
                "subtype",
                "alert_group",
                "city",
                "street",
                "cluster_report_count",
                "severity_proxy",
                "alert_impact_score",
                "corridor_norm_alert",
                "osm_match_status",
                "nearest_osm_distance_m",
            ],
        ),
        id="waze-alert-points",
        get_position="[lon, lat]",
        get_fill_color="alert_color",
        get_radius="alert_radius",
        radius_units="pixels",
        stroked=True,
        get_line_color=[255, 255, 255, 180],
        line_width_min_pixels=1,
        pickable=True,
        auto_highlight=True,
    )


def temporal_news_scatter_layer(data: pd.DataFrame) -> pdk.Layer:
    points = data[
        data["coordinate_pair_present"].eq(True)
        & data["longitude_num"].notna()
        & data["latitude_num"].notna()
    ].copy()
    return pdk.Layer(
        "ScatterplotLayer",
        data=deck_records(
            points,
            [
                "longitude_num",
                "latitude_num",
                "temporal_news_color",
                "temporal_news_radius",
                "ticketNumber",
                "temporal_datetime_local",
                "incident",
                "department_norm",
                "municipality_norm",
                "address",
                "corridor_norm",
                "mentions",
                "impact_social_score",
                "severity_class",
                "osm_match_status",
                "nearest_osm_distance_m",
            ],
        ),
        id="temporal-news-points",
        get_position="[longitude_num, latitude_num]",
        get_fill_color="temporal_news_color",
        get_radius="temporal_news_radius",
        radius_units="pixels",
        stroked=True,
        get_line_color=[255, 255, 255, 190],
        line_width_min_pixels=1,
        pickable=True,
        auto_highlight=True,
    )


def temporal_heatmap_layer(data: pd.DataFrame, radius: int) -> pdk.Layer:
    return pdk.Layer(
        "HeatmapLayer",
        data=deck_records(data, ["lon", "lat", "heat_weight"]),
        id="temporal-dynamic-heatmap",
        get_position="[lon, lat]",
        get_weight="heat_weight",
        radius_pixels=radius,
        intensity=1,
        threshold=0.03,
        color_range=TEMPORAL_HEATMAP_COLORS,
    )


def combined_temporal_heat_points(alerts_visible: pd.DataFrame, news_visible: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if not alerts_visible.empty:
        alerts = alerts_visible[["lon", "lat", "alert_impact_score"]].copy()
        alerts = alerts.rename(columns={"alert_impact_score": "heat_weight"})
        alerts["heat_weight"] = pd.to_numeric(alerts["heat_weight"], errors="coerce").fillna(1).clip(lower=1)
        frames.append(alerts)
    if not news_visible.empty:
        news = news_visible[["longitude_num", "latitude_num", "impact_social_score", "mentions"]].copy()
        news = news.rename(columns={"longitude_num": "lon", "latitude_num": "lat", "impact_social_score": "heat_weight"})
        news["heat_weight"] = pd.to_numeric(news["heat_weight"], errors="coerce").fillna(0)
        news["heat_weight"] = news["heat_weight"].where(news["heat_weight"] > 0, pd.to_numeric(news["mentions"], errors="coerce").fillna(1))
        news["heat_weight"] = news["heat_weight"].clip(lower=1)
        frames.append(news[["lon", "lat", "heat_weight"]])
    if not frames:
        return pd.DataFrame(columns=["lon", "lat", "heat_weight"])
    heat = pd.concat(frames, ignore_index=True)
    return heat[heat["lon"].notna() & heat["lat"].notna()].copy()


def point_view_state_from_frames(frames: list[pd.DataFrame], fallback_zoom: float = 8.2) -> pdk.ViewState:
    lons: list[float] = []
    lats: list[float] = []
    for frame in frames:
        if frame.empty:
            continue
        lon_col = "lon" if "lon" in frame.columns else "longitude_num" if "longitude_num" in frame.columns else None
        lat_col = "lat" if "lat" in frame.columns else "latitude_num" if "latitude_num" in frame.columns else None
        if not lon_col or not lat_col:
            continue
        lon_values = pd.to_numeric(frame[lon_col], errors="coerce")
        lat_values = pd.to_numeric(frame[lat_col], errors="coerce")
        valid = lon_values.notna() & lat_values.notna()
        lons.extend(lon_values[valid].astype(float).tolist())
        lats.extend(lat_values[valid].astype(float).tolist())
    if not lons or not lats:
        return pdk.ViewState(latitude=13.70, longitude=-89.20, zoom=fallback_zoom, pitch=0, bearing=0)
    return pdk.ViewState(
        latitude=float((min(lats) + max(lats)) / 2),
        longitude=float((min(lons) + max(lons)) / 2),
        zoom=fallback_zoom,
        pitch=0,
        bearing=0,
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
    st.subheader("Mapa de movilidad: red vial, Waze, alertas e incidentes")
    st.caption(
        "Vista narrativa por modos. Cada modo responde una pregunta distinta para evitar saturar el mapa "
        "y leer la red vial como un sistema de corredores con presion operacional, eventos y senal social."
    )

    mode = st.radio("Modo de analisis", options=ANALYSIS_MODES, index=0, horizontal=True)
    base_controls = st.columns([1.15, 1, 1, 1])
    basemap_label = base_controls[0].selectbox("Mapa base", options=list(BASEMAP_STYLES.keys()), index=0)
    show_osm_base = base_controls[1].toggle("Red OSM tenue", value=True)
    road_density = base_controls[2].segmented_control(
        "Red base",
        options=["Vias principales", "Toda la red"],
        default="Vias principales",
    )
    focus = base_controls[3].segmented_control(
        "Encuadre",
        options=["AMSS", "Capa activa", "Incidentes"],
        default="Capa activa",
    )
    major_only = road_density == "Vias principales"

    segments = load_segments(department_values, major_only=major_only)
    default_road_classes = [value for value in DEFAULT_MAJOR_HIGHWAYS if not segments.empty and value in set(segments["highway"].dropna())]
    if not default_road_classes and not segments.empty:
        default_road_classes = sorted(segments["highway"].dropna().unique().tolist())[:6]

    road_opacity = 0.34
    road_width = 1.2
    with st.expander("Ajustes globales de visualizacion", expanded=False):
        if not segments.empty:
            road_classes = st.multiselect(
                "Tipos de via en red base",
                options=sorted(segments["highway"].dropna().unique().tolist()),
                default=default_road_classes,
                format_func=lambda value: label_value(value, HIGHWAY_LABELS),
            )
        else:
            road_classes = []
        road_c1, road_c2 = st.columns(2)
        road_opacity = road_c1.slider("Opacidad red base", 0.05, 0.75, road_opacity, 0.05)
        road_width = road_c2.slider("Grosor red base", 0.4, 2.0, road_width, 0.05)

    layers: list[pdk.Layer] = []
    visible_segments = pd.DataFrame()
    active_segments = pd.DataFrame()
    active_heatmaps: list[str] = []
    side_tables: list[tuple[str, pd.DataFrame]] = []
    legend_blocks: list[tuple[str, list[tuple[str, list[int]]]]] = []
    mode_note = ""

    if show_osm_base and not segments.empty:
        visible_segments = segments[segments["highway"].isin(road_classes)].copy() if road_classes else segments.copy()
        if len(visible_segments) > 35000:
            visible_segments = visible_segments.sort_values("length_m", ascending=False).head(35000).copy()
        visible_segments = style_segments(visible_segments, road_opacity, road_width)
        layers.append(path_layer(visible_segments))

    if mode.startswith("1."):
        st.markdown("**Estado de la red**")
        st.caption("Corredores coloreados por presion integrada PIEC-Waze. Esta es la vista de entrada para priorizar la red.")
        integrated = load_integrated_summary()
        if integrated.empty:
            st.warning("No existen resultados integrados Waze. Ejecuta `make run-waze-integrated-analysis`.")
        else:
            c1, c2, c3 = st.columns(3)
            min_score = c1.slider("Umbral PIEC-Waze", 0, 100, 55)
            top_n = c2.slider("Top corredores", 10, 200, 60, 5)
            width_by = c3.selectbox("Grosor por", ["integrated_active_hours", "same_hour_overlap_count"], index=0)
            selected = (
                integrated[integrated["corridor_key"].ne("unresolved")]
                .query("integrated_corridor_pressure >= @min_score")
                .sort_values("integrated_corridor_pressure", ascending=False)
                .head(top_n)
                .copy()
            )
            osm = load_osm_segments_by_keys(tuple(selected["corridor_key"].astype(str).tolist()), major_only=major_only)
            active_segments = osm.merge(selected, left_on="road_key_norm", right_on="corridor_key", how="inner")
            active_segments = style_metric_segments(
                active_segments,
                "integrated_corridor_pressure",
                width_by,
                "pressure",
                score_scale=True,
                min_width=2.0,
                max_width=8.5,
            )
            if not active_segments.empty:
                layers.append(analytical_path_layer(active_segments, "piec-waze-corridors"))
            mode_note = "PIEC-Waze integra presion por jams, presion por alerts, coincidencia temporal y confiabilidad."
            side_tables.append(
                (
                    "Top corredores PIEC-Waze",
                    selected[
                        [
                            "corridor_name",
                            "integrated_corridor_pressure",
                            "jam_pressure_norm",
                            "alert_pressure_norm",
                            "corridor_event_congestion_coupling",
                            "integration_priority",
                        ]
                    ].head(15),
                )
            )
            legend_blocks.append(
                (
                    "PIEC-Waze",
                    [
                        ("Baja", [148, 163, 184, 100]),
                        ("Moderada", [250, 204, 21, 165]),
                        ("Alta", [249, 115, 22, 210]),
                        ("Critica", [220, 38, 38, 235]),
                    ],
                )
            )

    elif mode.startswith("2."):
        st.markdown("**Congestion operacional Waze Jams**")
        st.caption("Corredores y segmentos coloreados por variables operacionales de congestion, sin usar alertas ni noticias.")
        jams = load_waze_jam_segments()
        if jams.empty:
            st.warning("No existen resultados Waze Jams.")
        else:
            metric_options = {
                "Score de presion jam": "corridor_jam_pressure_score",
                "Demora acumulada": "corridor_delay_burden",
                "Carga de congestion": "corridor_congestion_load",
                "Colapso de velocidad": "corridor_speed_collapse_rate",
                "Jams totales": "jams_count_total",
            }
            c1, c2, c3 = st.columns(3)
            metric_label = c1.selectbox("Variable operacional", list(metric_options.keys()), index=0)
            metric_col = metric_options[metric_label]
            top_n = c2.slider("Top corredores/segmentos", 20, 250, 90, 10)
            min_value = c3.slider("Umbral percentil visual", 0, 100, 0)
            ranked_keys = (
                jams.groupby("corridor_norm_key", dropna=False)[metric_col]
                .max()
                .sort_values(ascending=False)
            )
            if min_value > 0:
                ranked_keys = ranked_keys[ranked_keys >= ranked_keys.quantile(min_value / 100)]
            selected_keys = ranked_keys.head(top_n).index.astype(str).tolist()
            active_segments = jams[jams["corridor_norm_key"].astype(str).isin(selected_keys)].copy()
            active_segments = style_metric_segments(
                active_segments,
                metric_col,
                "corridor_congestion_load" if metric_col != "corridor_congestion_load" else "corridor_delay_burden",
                "jams",
                score_scale=metric_col == "corridor_jam_pressure_score",
                min_width=1.8,
                max_width=8.0,
            )
            if not active_segments.empty:
                layers.append(analytical_path_layer(active_segments, "waze-jams-pressure"))
            mode_note = "Esta vista separa la dimension operacional: demora, recurrencia, extension y baja velocidad."
            side_tables.append(
                (
                    f"Top por {metric_label}",
                    active_segments.drop_duplicates("corridor_norm_key")[
                        [
                            "corridor_norm_key",
                            "corridor_jam_pressure_score",
                            "jams_count_total",
                            "corridor_delay_burden",
                            "corridor_congestion_load",
                            "active_congestion_hours",
                        ]
                    ].sort_values(metric_col, ascending=False).head(15),
                )
            )
            legend_blocks.append(
                (
                    "Presion operacional",
                    [
                        ("Baja", [59, 130, 246, 110]),
                        ("Media", [34, 197, 94, 150]),
                        ("Alta", [245, 158, 11, 205]),
                        ("Critica", [220, 38, 38, 235]),
                    ],
                )
            )

    elif mode.startswith("3."):
        st.markdown("**Eventos Waze Alerts**")
        st.caption("Puntos reportados por usuarios y, opcionalmente, corredores con presion por alertas.")
        alerts = load_waze_alert_points()
        if alerts.empty:
            st.warning("No existen resultados Waze Alerts.")
        else:
            c1, c2, c3, c4 = st.columns(4)
            hour_range = c1.slider("Hora alerts", 0, 23, (0, 23))
            groups = sorted(alerts["alert_group"].dropna().unique().tolist())
            selected_groups = c2.multiselect("Tipo de alerta", groups, default=groups[:])
            min_impact = c3.slider("Impacto minimo", 0, 100, 0)
            show_alert_corridors = c4.toggle("Presion por corredor", value=True)
            filtered_alerts = alerts[
                alerts["event_hour"].fillna(-1).between(hour_range[0], hour_range[1])
                & alerts["alert_group"].isin(selected_groups)
                & alerts["alert_impact_score"].fillna(0).ge(min_impact)
            ].copy()
            if show_alert_corridors:
                alert_layers = load_waze_alert_corridor_layers()
                selected_layers = alert_layers.sort_values("corridor_alert_pressure", ascending=False).head(80)
                osm = load_osm_segments_by_keys(tuple(selected_layers["corridor_norm_key"].astype(str).tolist()), major_only=major_only)
                corridor_segments = osm.merge(selected_layers, left_on="road_key_norm", right_on="corridor_norm_key", how="inner")
                corridor_segments = style_metric_segments(
                    corridor_segments,
                    "corridor_alert_pressure",
                    "active_alert_hours",
                    "alerts",
                    score_scale=True,
                    min_width=1.6,
                    max_width=7.0,
                )
                if not corridor_segments.empty:
                    active_segments = corridor_segments
                    layers.append(analytical_path_layer(corridor_segments, "waze-alert-corridors"))
            if not filtered_alerts.empty:
                layers.append(waze_alert_scatter_layer(filtered_alerts))
            mode_note = "Los puntos explican eventos reportados; la linea opcional resume presion de alerts por corredor."
            side_tables.append(
                (
                    "Alertas visibles por tipo",
                    filtered_alerts.groupby("alert_group", dropna=False)
                    .agg(alertas=("uuid", "count"), impacto=("alert_impact_score", "sum"), reportes=("cluster_report_count", "sum"))
                    .reset_index()
                    .sort_values("impacto", ascending=False),
                )
            )
            legend_blocks.append(("Tipos de alertas", [(key.replace("_", " ").title(), color) for key, color in ALERT_GROUP_COLORS.items()]))

    elif mode.startswith("4."):
        st.markdown("**Relacion congestion-eventos**")
        st.caption("Distingue corredores acoplados, congestion sin alertas y eventos sin congestion proporcional.")
        view_kind = st.segmented_control("Vista", ["Cuadrantes por corredor", "Coincidencia por hora"], default="Cuadrantes por corredor")
        integrated = load_integrated_summary()
        if integrated.empty:
            st.warning("No existen resultados integrados.")
        elif view_kind == "Cuadrantes por corredor":
            c1, c2 = st.columns([1.4, 1])
            quadrants = sorted(integrated["quadrant"].dropna().unique().tolist())
            selected_quadrants = c1.multiselect(
                "Cuadrantes",
                quadrants,
                default=[q for q in quadrants if q != "BAJA_CONGESTION_BAJAS_ALERTAS"],
                format_func=lambda value: label_value(value, QUADRANT_LABELS),
            )
            top_n = c2.slider("Top corredores por presion integrada", 20, 200, 90, 10)
            selected = (
                integrated[integrated["corridor_key"].ne("unresolved") & integrated["quadrant"].isin(selected_quadrants)]
                .sort_values("integrated_corridor_pressure", ascending=False)
                .head(top_n)
                .copy()
            )
            osm = load_osm_segments_by_keys(tuple(selected["corridor_key"].astype(str).tolist()), major_only=major_only)
            active_segments = osm.merge(selected, left_on="road_key_norm", right_on="corridor_key", how="inner")
            active_segments = style_quadrant_segments(active_segments)
            if not active_segments.empty:
                layers.append(analytical_path_layer(active_segments, "integrated-quadrants"))
            side_tables.append(
                (
                    "Cuadrantes visibles",
                    selected.groupby("quadrant", dropna=False)
                    .agg(corredores=("corridor_key", "count"), presion_promedio=("integrated_corridor_pressure", "mean"))
                    .reset_index()
                    .assign(cuadrante=lambda df: df["quadrant"].map(lambda value: label_value(value, QUADRANT_LABELS)))
                    [["cuadrante", "corredores", "presion_promedio"]],
                )
            )
            legend_blocks.append(("Cuadrantes", [(label_value(key, QUADRANT_LABELS), color) for key, color in QUADRANT_COLORS.items()]))
        else:
            integrated_hour = load_integrated_hour()
            if integrated_hour.empty:
                st.warning("No existe panel integrado corredor-hora.")
            else:
                c1, c2, c3 = st.columns(3)
                selected_hour = c1.slider("Hora", 0, 23, 17)
                state_options = ["ALERTS_JAMS", "JAMS_ONLY", "ALERTS_ONLY"]
                selected_states = c2.multiselect(
                    "Tipo de coincidencia",
                    state_options,
                    default=state_options,
                    format_func=lambda value: label_value(value, TEMPORAL_STATE_LABELS),
                )
                top_n = c3.slider("Top corredor-hora", 20, 200, 100, 10)
                hour_df = integrated_hour[
                    integrated_hour["corridor_key"].ne("unresolved") & integrated_hour["event_hour"].eq(selected_hour)
                ].copy()
                hour_df = style_temporal_segments(hour_df)
                hour_df = (
                    hour_df[hour_df["temporal_state"].isin(selected_states)]
                    .sort_values("integrated_corridor_hour_pressure", ascending=False)
                    .head(top_n)
                )
                osm = load_osm_segments_by_keys(tuple(hour_df["corridor_key"].astype(str).tolist()), major_only=major_only)
                active_segments = osm.merge(hour_df, left_on="road_key_norm", right_on="corridor_key", how="inner")
                active_segments = style_temporal_segments(active_segments)
                if not active_segments.empty:
                    layers.append(analytical_path_layer(active_segments, "integrated-temporal-overlap"))
                side_tables.append(
                    (
                        f"Coincidencia hora {selected_hour:02d}:00",
                        hour_df[
                            [
                                "corridor_name",
                                "temporal_state_label",
                                "integrated_corridor_hour_pressure",
                                "jam_count",
                                "alert_count",
                                "operational_congestion_pressure",
                                "critical_alert_pressure",
                            ]
                        ].head(20),
                    )
                )
                legend_blocks.append(("Coincidencia temporal", [(label_value(key, TEMPORAL_STATE_LABELS), color) for key, color in TEMPORAL_STATE_COLORS.items() if key != "NO_ACTIVITY"]))
        mode_note = "Esta vista explica si la presion vial viene de congestion, eventos reportados o de ambas fuentes."

    elif mode.startswith("5."):
        st.markdown("**Social / noticias**")
        st.caption("Incidentes noticiosos sobre la red vial. Esta vista mantiene la PVN como capa social complementaria.")
        c1, c2, c3, c4 = st.columns(4)
        point_color_by = c1.segmented_control("Color puntos", ["Severidad", "Estado OSM", "Resolucion texto-OSM"], default="Severidad")
        point_size_by = c2.segmented_control("Tamano puntos", ["Impacto social", "Menciones", "Severidad"], default="Impacto social")
        show_points = c3.toggle("Puntos noticias", value=True)
        heat_choice = c4.selectbox("Heatmap", ["Sin heatmap", "Impacto social", "Eventos", "Menciones"], index=1)
        radius = st.slider("Radio heatmap", 20, 120, 55)
        styled_filtered = style_points(filtered, point_color_by, point_size_by)
        if heat_choice != "Sin heatmap":
            key = {"Impacto social": "impacto", "Eventos": "eventos", "Menciones": "menciones"}[heat_choice]
            config = HEATMAP_CONFIGS[key]
            active_heatmaps.append(key)
            layers.append(heatmap_layer(filtered, config["weight_col"], f"heat-{key}", config["color_range"], radius))
        if show_points:
            layers.append(scatter_layer(styled_filtered))
        active_segments = visible_segments
        mode_note = "Noticias e incidentes muestran amplificacion social; no equivalen a siniestralidad total."
        side_tables.append(
            (
                "Top eventos por impacto social",
                filtered[
                    [
                        col
                        for col in [
                            "ticketNumber",
                            "datetime",
                            "incident",
                            "department_norm",
                            "municipality_norm",
                            "corridor_norm",
                            "mentions",
                            "impact_social_score",
                            "severity_class",
                        ]
                        if col in filtered.columns
                    ]
                ].sort_values("impact_social_score", ascending=False).head(20),
            )
        )
        legend_blocks.append(("Severidad noticias", [(label_value(key, SEVERITY_LABELS), color) for key, color in SEVERITY_COLORS.items()]))

    else:
        st.markdown("**Calidad y trazabilidad**")
        st.caption("Vista de auditoria: coordenadas, match OSM, resolucion texto-via y casos que requieren revision.")
        c1, c2, c3 = st.columns(3)
        quality_color = c1.segmented_control("Color puntos", ["Estado OSM", "Resolucion texto-OSM", "Coordenada"], default="Estado OSM")
        show_unresolved = c2.toggle("Resaltar no resueltos", value=True)
        only_problematic = c3.toggle("Solo problematicos", value=True)
        color_map = {"Estado OSM": "Estado OSM", "Resolucion texto-OSM": "Resolucion texto-OSM", "Coordenada": "Coordenada"}
        quality_points = filtered.copy()
        if only_problematic:
            quality_points = quality_points[
                quality_points["text_osm_resolution"].eq("UNRESOLVED")
                | quality_points["osm_match_status"].isin(["SPATIAL_OSM_LOW_REVIEW", "SPATIAL_OSM_DISTANCE_CONFLICT", "NO_COORDINATE_FOR_OSM", "NO_NEAR_OSM_SEGMENT"])
                | quality_points["coordinate_quality_status"].isin(["MISSING_POINT", "OUTSIDE_EL_SALVADOR_BBOX", "LOW_GEO_CONFIDENCE_POINT"])
            ].copy()
        styled_quality = style_points(quality_points, color_map[quality_color], "Impacto social")
        layers.append(scatter_layer(styled_quality))
        if show_unresolved:
            layers.append(highlight_unresolved_layer(styled_quality))
        active_segments = visible_segments
        mode_note = "Esta vista no prioriza criticidad; prioriza trazabilidad y brechas de asociacion espacial."
        side_tables.append(
            (
                "Casos visibles para revision",
                quality_points[
                    [
                        col
                        for col in [
                            "ticketNumber",
                            "datetime",
                            "department_norm",
                            "municipality_norm",
                            "address",
                            "corridor_norm",
                            "coordinate_quality_status",
                            "osm_match_status",
                            "text_osm_resolution",
                            "nearest_osm_distance_m",
                        ]
                        if col in quality_points.columns
                    ]
                ].head(40),
            )
        )
        legend_blocks.append(("Estado OSM", [(label_value(key, OSM_STATUS_LABELS), color) for key, color in OSM_STATUS_COLORS.items()]))

    tooltip = {
        "html": """
        <b>{corridor_name}</b>{corridor_norm_waze}{corridor_norm_alert}<br/>
        PIEC: {integrated_corridor_pressure} | hora: {event_hour}<br/>
        jams: {jam_count}{jams_count_total} | alerts: {alert_count}{alerts_count_total}<br/>
        presion jams: {jam_pressure_norm} | presion alerts: {alert_pressure_norm}<br/>
        acoplamiento: {corridor_event_congestion_coupling}<br/>
        cuadrante: {quadrant_label} | estado: {temporal_state_label}<br/>
        prioridad: {integration_priority}<br/>
        metrica: {metric_name} = {metric_value}<br/>
        demora: {corridor_delay_burden} | carga: {corridor_congestion_load}<br/>
        <hr/>
        <b>{name}</b> {ref}<br/>
        tipo OSM: {highway_label}<br/>
        sentido: {oneway} | carriles: {lanes} | velocidad: {maxspeed}<br/>
        longitud segmento: {length_km} km<br/>
        <hr/>
        <b>{ticketNumber}{uuid}</b><br/>
        {datetime}{datetime_local}<br/>
        {incident}{alert_group} {subtype}<br/>
        corredor: {corridor_norm}{corridor_norm_alert}<br/>
        impacto: {impact_social_score}{alert_impact_score}<br/>
        OSM: {osm_label}{osm_match_status} | distancia: {nearest_osm_distance_m} m
        """,
        "style": {"backgroundColor": "#111827", "color": "white"},
    }

    if focus == "AMSS":
        initial_view = AMSS_VIEW_STATE
    elif focus == "Incidentes":
        initial_view = view_state(filtered)
    elif not active_segments.empty:
        initial_view = path_view_state(active_segments, fallback_zoom=8.4)
    elif not visible_segments.empty:
        initial_view = path_view_state(visible_segments, fallback_zoom=10.8)
    else:
        initial_view = view_state(filtered)

    deck_kwargs = {"initial_view_state": initial_view, "layers": layers, "tooltip": tooltip}
    selected_basemap = BASEMAP_STYLES[basemap_label]
    if selected_basemap:
        deck_kwargs["map_style"] = selected_basemap
    st.pydeck_chart(pdk.Deck(**deck_kwargs), width="stretch", height=MAP_CHART_HEIGHT_PX)

    if mode_note:
        st.info(mode_note)

    if legend_blocks:
        with st.expander("Leyenda del modo actual", expanded=True):
            columns = st.columns(min(len(legend_blocks), 3))
            for idx, (title, items) in enumerate(legend_blocks):
                with columns[idx % len(columns)]:
                    render_swatch_legend(title, items)

    render_heatmap_reference(filtered, active_heatmaps)

    if side_tables:
        with st.expander("Tablas de apoyo del modo actual", expanded=False):
            for title, table in side_tables:
                st.markdown(f"**{title}**")
                st.dataframe(table, width="stretch", hide_index=True)

    if show_osm_base and not visible_segments.empty:
        st.caption(
            "Red vial base OSM tenue: "
            f"{len(visible_segments):,} segmentos visibles, "
            f"{visible_segments['length_km'].sum():,.1f} km. "
            "Las capas analiticas se dibujan encima de esta referencia."
        )


def temporal_evolution_tab(events: pd.DataFrame) -> None:
    st.subheader("Evolución temporal")
    st.caption(
        "Simulación histórica tipo tiempo real para el 2026-06-29. "
        "No reemplaza el mapa analítico: reproduce cómo aparecen, se acumulan o salen de ventana "
        "Waze Jams, Waze Alerts y noticias/incidentes sobre la red OSM."
    )

    jams = load_temporal_jams()
    alerts = load_temporal_alerts()
    news = load_temporal_news(events)

    if "temporal_current_minute" not in st.session_state:
        st.session_state["temporal_current_minute"] = 17 * 60

    time_options = list(range(0, 24 * 60, 5))
    st.session_state["temporal_current_minute"] = min(
        time_options,
        key=lambda value: abs(value - int(st.session_state["temporal_current_minute"])),
    )

    nav_cols = st.columns([0.8, 0.8, 1, 1, 1, 1])
    if nav_cols[0].button("<< 15 min"):
        st.session_state["temporal_current_minute"] = max(0, st.session_state["temporal_current_minute"] - 15)
        st.rerun()
    if nav_cols[1].button("+15 min >>"):
        st.session_state["temporal_current_minute"] = min(23 * 60 + 55, st.session_state["temporal_current_minute"] + 15)
        st.rerun()
    autoplay = nav_cols[2].toggle("Play automatico", value=False)
    speed = nav_cols[3].selectbox("Velocidad", ["1x", "2x", "5x", "10x"], index=1)
    play_step = nav_cols[4].selectbox("Paso", [5, 15, 30, 60], index=1, format_func=lambda value: f"{value} min")
    loop_playback = nav_cols[5].toggle("Reiniciar al final", value=True)

    control_cols = st.columns([1.5, 1.1, 1.1, 1.1])
    current_minute = control_cols[0].select_slider(
        "Momento de simulación",
        options=time_options,
        value=st.session_state["temporal_current_minute"],
        format_func=minute_label,
    )
    st.session_state["temporal_current_minute"] = current_minute
    temporal_mode = control_cols[1].selectbox(
        "Modo temporal",
        ["Acumulado hasta el momento", "Ventana movil", "Eventos nuevos"],
        index=1,
    )
    window_minutes = control_cols[2].selectbox(
        "Ventana movil",
        [15, 30, 60, 180],
        index=2,
        format_func=lambda value: f"{value} min",
    )
    frame_minutes = control_cols[3].selectbox(
        "Intervalo eventos nuevos",
        [5, 10, 15, 30],
        index=2,
        format_func=lambda value: f"{value} min",
    )

    start_minute, end_minute, window_label = temporal_window_bounds(
        current_minute,
        temporal_mode,
        window_minutes,
        frame_minutes,
    )

    layer_options = [
        "Red vial base OSM",
        "Waze Jams",
        "Waze Alerts",
        "Noticias/incidentes",
        "Heatmap dinamico",
    ]
    map_cols = st.columns([1.2, 1.1, 1.1, 1.1])
    selected_layers = map_cols[0].multiselect(
        "Capas",
        layer_options,
        default=["Red vial base OSM", "Waze Jams", "Waze Alerts", "Noticias/incidentes"],
    )
    basemap_label = map_cols[1].selectbox("Mapa base", options=list(BASEMAP_STYLES.keys()), index=0, key="temporal_basemap")
    base_scope = map_cols[2].selectbox(
        "Red base",
        ["San Salvador", "Nacional principal", "Solo corredores activos"],
        index=0,
    )
    focus = map_cols[3].selectbox("Encuadre", ["AMSS", "Capa activa", "Eventos visibles"], index=1)

    settings_cols = st.columns([1, 1, 1])
    major_only = settings_cols[0].toggle("Solo vías principales", value=True)
    top_jam_corridors = settings_cols[1].slider("Top corredores jam", 20, 250, 90, 10)
    heat_radius = settings_cols[2].slider("Radio heatmap dinámico", 20, 120, 55, 5)

    jams_visible = filter_temporal_frame(jams, "temporal_minute_of_day", start_minute, end_minute)
    alerts_visible = filter_temporal_frame(alerts, "temporal_minute_of_day", start_minute, end_minute)
    news_visible = filter_temporal_frame(news, "temporal_minute_of_day", start_minute, end_minute)
    jam_summary = summarize_temporal_jams(jams_visible, top_jam_corridors)
    dynamic_ranking = build_temporal_corridor_ranking(jam_summary, alerts_visible, news_visible)

    st.info(
        f"Fecha simulada: {SIMULATION_DATE}. Momento: {minute_label(current_minute)}. "
        f"Ventana visible: {window_label}. Modo: {temporal_mode}."
    )

    total_delay = jams_visible["delay_mean"].sum() if "delay_mean" in jams_visible.columns else 0
    critical_alerts = int(alerts_visible["is_critical_alert"].sum()) if "is_critical_alert" in alerts_visible.columns else 0
    active_corridors = int(dynamic_ranking["corridor_norm_key"].nunique()) if not dynamic_ranking.empty else 0
    top_corridor = "Sin actividad"
    if not dynamic_ranking.empty:
        top_corridor = str(dynamic_ranking.iloc[0].get("corridor_name") or dynamic_ranking.iloc[0].get("corridor_norm_key"))

    metric_row(
        [
            ("Jams visibles", f"{len(jams_visible):,}", "registros únicos"),
            ("Delay visible", f"{total_delay:,.1f} min", "proxy"),
            ("Alerts visibles", f"{len(alerts_visible):,}", f"{critical_alerts:,} críticas"),
            ("Noticias visibles", f"{len(news_visible):,}", "incidentes"),
            ("Corredores activos", f"{active_corridors:,}", "con señal"),
            ("Mayor presión", top_corridor[:32], None),
        ]
    )

    layers: list[pdk.Layer] = []
    base_segments = pd.DataFrame()
    jam_segments = pd.DataFrame()

    if "Red vial base OSM" in selected_layers and base_scope != "Solo corredores activos":
        if base_scope == "Nacional principal":
            base_segments = load_national_segments(major_only=major_only)
        else:
            base_segments = load_segments(("SAN SALVADOR",), major_only=major_only)
        if not base_segments.empty:
            if len(base_segments) > 40000:
                base_segments = base_segments.sort_values("length_m", ascending=False).head(40000).copy()
            base_segments = style_segments(base_segments, 0.24, 1.0)
            layers.append(path_layer(base_segments))

    if "Waze Jams" in selected_layers and not jam_summary.empty:
        osm = load_osm_segments_by_keys(tuple(jam_summary["corridor_norm_key"].astype(str).tolist()), major_only=major_only)
        if not osm.empty:
            jam_segments = osm.merge(jam_summary, left_on="road_key_norm", right_on="corridor_norm_key", how="inner")
            jam_segments = style_metric_segments(
                jam_segments,
                "temporal_jam_pressure",
                "visible_delay_min",
                "jams",
                score_scale=True,
                min_width=2.0,
                max_width=8.5,
            )
            layers.append(analytical_path_layer(jam_segments, "temporal-waze-jams"))

    if "Waze Alerts" in selected_layers and not alerts_visible.empty:
        layers.append(waze_alert_scatter_layer(alerts_visible))

    if "Noticias/incidentes" in selected_layers and not news_visible.empty:
        layers.append(temporal_news_scatter_layer(news_visible))

    heat_points = combined_temporal_heat_points(
        alerts_visible if "Waze Alerts" in selected_layers else alerts_visible.iloc[0:0],
        news_visible if "Noticias/incidentes" in selected_layers else news_visible.iloc[0:0],
    )
    if "Heatmap dinamico" in selected_layers and not heat_points.empty:
        layers.insert(0, temporal_heatmap_layer(heat_points, heat_radius))

    tooltip = {
        "html": """
        <b>{corridor_name}</b><br/>
        presión jam: {temporal_jam_pressure}<br/>
        jams visibles: {visible_jams} | delay: {visible_delay_min} min<br/>
        carga: {visible_congestion_load} | intensidad: {visible_jam_intensity}<br/>
        severos: {severe_jams} | extremos: {extreme_jams}<br/>
        <hr/>
        <b>{name}</b> {ref}<br/>
        tipo OSM: {highway_label}<br/>
        sentido: {oneway} | carriles: {lanes} | velocidad: {maxspeed}<br/>
        <hr/>
        <b>{uuid}{ticketNumber}</b><br/>
        {temporal_datetime_local}<br/>
        {alert_group}{incident} {subtype}<br/>
        corredor: {corridor_norm_alert}{corridor_norm}<br/>
        impacto: {alert_impact_score}{impact_social_score}<br/>
        menciones/reportes: {mentions}{cluster_report_count}<br/>
        OSM: {osm_match_status} | distancia: {nearest_osm_distance_m} m
        """,
        "style": {"backgroundColor": "#111827", "color": "white"},
    }

    if focus == "AMSS":
        initial_view = AMSS_VIEW_STATE
    elif focus == "Eventos visibles":
        initial_view = point_view_state_from_frames([alerts_visible, news_visible], fallback_zoom=8.4)
    elif not jam_segments.empty:
        initial_view = path_view_state(jam_segments, fallback_zoom=8.1 if base_scope == "Nacional principal" else 10.5)
    elif not base_segments.empty:
        initial_view = path_view_state(base_segments, fallback_zoom=10.5)
    else:
        initial_view = point_view_state_from_frames([alerts_visible, news_visible], fallback_zoom=8.4)

    deck_kwargs = {"initial_view_state": initial_view, "layers": layers, "tooltip": tooltip}
    selected_basemap = BASEMAP_STYLES[basemap_label]
    if selected_basemap:
        deck_kwargs["map_style"] = selected_basemap
    st.pydeck_chart(pdk.Deck(**deck_kwargs), width="stretch", height=MAP_CHART_HEIGHT_PX)

    with st.expander("Leyenda y lectura del mapa temporal", expanded=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            render_swatch_legend(
                "Capas temporales",
                [(label, color) for label, color in TEMPORAL_SOURCE_COLORS.items()],
            )
        with c2:
            render_swatch_legend(
                "Presión Waze Jams",
                [
                    ("Baja", [59, 130, 246, 110]),
                    ("Media", [34, 197, 94, 150]),
                    ("Alta", [245, 158, 11, 205]),
                    ("Crítica", [220, 38, 38, 235]),
                ],
            )
        with c3:
            render_swatch_legend(
                "Tipos Waze Alerts",
                [(key.replace("_", " ").title(), color) for key, color in ALERT_GROUP_COLORS.items()],
            )
        st.caption(
            "Jams se representan como corredores OSM activados por los registros Waze visibles. "
            "Alerts y noticias se representan como puntos. El heatmap dinámico combina impacto de alerts "
            "y presión social/noticiosa visible en la ventana."
        )

    table_tabs = st.tabs(["Ranking dinámico", "Tipos de alerta", "Territorio noticias", "Eventos visibles", "Validación temporal"])
    with table_tabs[0]:
        st.markdown("**Corredores activos en la ventana visible**")
        if dynamic_ranking.empty:
            st.info("No hay corredores activos en la ventana seleccionada.")
        else:
            st.dataframe(
                dynamic_ranking[
                    [
                        "corridor_name",
                        "dynamic_corridor_pressure",
                        "visible_jams",
                        "visible_delay_min",
                        "visible_alerts",
                        "alert_impact",
                        "critical_alerts",
                        "visible_news",
                        "news_impact",
                        "news_mentions",
                    ]
                ].head(30),
                width="stretch",
                hide_index=True,
            )
    with table_tabs[1]:
        if alerts_visible.empty:
            st.info("No hay alertas visibles.")
        else:
            alert_summary = (
                alerts_visible.groupby("alert_group", dropna=False)
                .agg(
                    alerts=("uuid", "count"),
                    reports=("cluster_report_count", "sum"),
                    impact=("alert_impact_score", "sum"),
                    critical=("is_critical_alert", "sum"),
                )
                .reset_index()
                .sort_values("impact", ascending=False)
            )
            st.dataframe(alert_summary, width="stretch", hide_index=True)
    with table_tabs[2]:
        if news_visible.empty:
            st.info("No hay noticias/incidentes visibles.")
        else:
            territory = (
                news_visible.groupby(["department_norm", "municipality_norm"], dropna=False)
                .agg(
                    eventos=("uuid", "count"),
                    menciones=("mentions", "sum"),
                    impacto=("impact_social_score", "sum"),
                )
                .reset_index()
                .sort_values(["eventos", "impacto"], ascending=False)
            )
            st.dataframe(territory, width="stretch", hide_index=True)
    with table_tabs[3]:
        event_frames: list[pd.DataFrame] = []
        if not alerts_visible.empty:
            alert_detail = alerts_visible[
                [
                    col
                    for col in [
                        "temporal_datetime_local",
                        "alert_group",
                        "type",
                        "subtype",
                        "city",
                        "street",
                        "corridor_norm_alert",
                        "alert_impact_score",
                        "cluster_report_count",
                        "osm_match_status",
                    ]
                    if col in alerts_visible.columns
                ]
            ].copy()
            alert_detail.insert(0, "fuente", "Waze Alert")
            event_frames.append(alert_detail)
        if not news_visible.empty:
            news_detail = news_visible[
                [
                    col
                    for col in [
                        "temporal_datetime_local",
                        "incident",
                        "department_norm",
                        "municipality_norm",
                        "address",
                        "corridor_norm",
                        "mentions",
                        "impact_social_score",
                        "osm_match_status",
                    ]
                    if col in news_visible.columns
                ]
            ].copy()
            news_detail.insert(0, "fuente", "Noticia/incidente")
            event_frames.append(news_detail)
        if not event_frames:
            st.info("No hay puntos visibles en la ventana seleccionada.")
        else:
            st.dataframe(pd.concat(event_frames, ignore_index=True).head(80), width="stretch", hide_index=True)
    with table_tabs[4]:
        validation = pd.DataFrame(
            [
                {
                    "fuente": "Waze Jams",
                    "registros_usados": len(jams),
                    "fecha_usada": SIMULATION_DATE,
                    "min_hora": minute_label(int(jams["temporal_minute_of_day"].min())) if not jams.empty else "Sin datos",
                    "max_hora": minute_label(int(jams["temporal_minute_of_day"].max())) if not jams.empty else "Sin datos",
                    "criterio": "registros únicos procesados; geometría por corredor OSM",
                },
                {
                    "fuente": "Waze Alerts",
                    "registros_usados": len(alerts),
                    "fecha_usada": SIMULATION_DATE,
                    "min_hora": minute_label(int(alerts["temporal_minute_of_day"].min())) if not alerts.empty else "Sin datos",
                    "max_hora": minute_label(int(alerts["temporal_minute_of_day"].max())) if not alerts.empty else "Sin datos",
                    "criterio": "puntos con coordenadas y timestamp local",
                },
                {
                    "fuente": "Noticias/incidentes",
                    "registros_usados": len(news),
                    "fecha_usada": SIMULATION_DATE,
                    "min_hora": minute_label(int(news["temporal_minute_of_day"].min())) if not news.empty else "Sin datos",
                    "max_hora": minute_label(int(news["temporal_minute_of_day"].max())) if not news.empty else "Sin datos",
                    "criterio": "solo incidentes.csv filtrado a 2026-06-29; no se usa ultimas_100_noticias.csv",
                },
            ]
        )
        st.dataframe(validation, width="stretch", hide_index=True)
        st.caption(
            "Supuesto temporal: Waze se interpreta en America/El_Salvador; las noticias se tratan como hora local "
            "porque su campo datetime no trae zona horaria explícita."
        )

    if autoplay:
        delay_seconds = {"1x": 1.2, "2x": 0.75, "5x": 0.35, "10x": 0.15}[speed]
        time.sleep(delay_seconds)
        next_minute = current_minute + int(play_step)
        if next_minute > 23 * 60 + 55:
            next_minute = 0 if loop_playback else 23 * 60 + 55
        st.session_state["temporal_current_minute"] = next_minute
        st.rerun()


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

    tabs = st.tabs(
        [
            "Resumen",
            "Mapa PVN",
            "Evolución temporal",
            "Corredores",
            "Temporal",
            "Engagement",
            "OSM / Vias",
            "Calidad",
            "Detalle",
        ]
    )
    with tabs[0]:
        summary_tab(events, filtered)
    with tabs[1]:
        map_tab(events, filtered)
    with tabs[2]:
        temporal_evolution_tab(events)
    with tabs[3]:
        corridors_tab(filtered)
    with tabs[4]:
        temporal_tab(events, filtered)
    with tabs[5]:
        engagement_tab(filtered)
    with tabs[6]:
        osm_tab(filtered)
    with tabs[7]:
        quality_tab(events, filtered)
    with tabs[8]:
        detail_tab(filtered)


if __name__ == "__main__":
    main()
