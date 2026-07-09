#!/usr/bin/env python3
"""
Pipeline de analisis para Data/Waze/waze_alerts_2026-06-29.json.

Unidad metodologica:
- El uuid se usa como alerta unica porque el archivo ya viene deduplicado.
- cluster_report_count se interpreta como respaldo/corroboracion, no como conteo de vehiculos.
- La coordenada de la alerta es la fuente primaria para asociar a OSM.
- El texto vial se conserva como respaldo y como ayuda para corridor_norm funcional.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
from pyproj import Transformer
from scipy.spatial import cKDTree

from waze_jams_analysis_pipeline import (
    ROOT,
    alias_match,
    build_osm_lookup,
    compact_text,
    extract_route_refs,
    format_route_ref,
    infer_corridor_group,
    infer_road_scope,
    load_alias_lookup,
    normalize_road_text,
    normalize_route_ref,
    normalize_text,
    pct,
    resolve_corridor,
    robust_norm,
    title_case,
)


INPUT_JSON = ROOT / "Data" / "Waze" / "waze_alerts_2026-06-29.json"
RESULTS_DIR = ROOT / "Results" / "Waze" / "Alerts"
INFORME_DIR = ROOT / "Informes" / "Informe_4"
OSM_NATIONAL_SEGMENTS_PATH = ROOT / "Data" / "Processed" / "osm_roads_nacional" / "osm_road_segments.csv"
LOCAL_TZ = "America/El_Salvador"
TOTAL_HOURS = 24
EPS = 1e-9
SPATIAL_HIGH_M = 50.0
SPATIAL_MEDIUM_M = 150.0
SPATIAL_LOW_M = 500.0
GRID_SIZE_M = 1000.0


WKT_POINT_RE = re.compile(r"Point\((-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\)", re.I)


ALERT_TYPE_LABELS = {
    "ACCIDENT": "Accidente",
    "ROAD_CLOSED": "Cierre vial",
    "JAM": "Congestion reportada",
    "HAZARD": "Peligro vial",
}


SUBTYPE_LABELS = {
    "ACCIDENT_MAJOR": "Accidente mayor",
    "JAM_HEAVY_TRAFFIC": "Trafico pesado",
    "JAM_STAND_STILL_TRAFFIC": "Trafico detenido",
    "HAZARD_ON_SHOULDER_CAR_STOPPED": "Vehiculo detenido en hombro",
    "HAZARD_ON_ROAD_LANE_CLOSED": "Carril cerrado",
    "HAZARD_ON_ROAD_POT_HOLE": "Bache",
    "HAZARD_ON_ROAD": "Peligro en via",
    "HAZARD_ON_ROAD_CONSTRUCTION": "Construccion en via",
    "HAZARD_ON_ROAD_OBJECT": "Objeto en via",
    "HAZARD_ON_ROAD_CAR_STOPPED": "Vehiculo detenido en via",
    "HAZARD_WEATHER": "Clima",
    "HAZARD_WEATHER_FLOOD": "Inundacion",
    "HAZARD_WEATHER_FOG": "Neblina",
    "HAZARD_ON_ROAD_ICE": "Superficie deslizante",
    "HAZARD_ON_ROAD_TRAFFIC_LIGHT_FAULT": "Falla de semaforo",
}


def ensure_dirs() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    INFORME_DIR.mkdir(parents=True, exist_ok=True)


def load_alerts_json() -> tuple[pd.DataFrame, dict[str, Any]]:
    if not INPUT_JSON.exists():
        raise FileNotFoundError(f"No existe {INPUT_JSON}")
    with INPUT_JSON.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    records = payload.get("records", [])
    meta = {key: value for key, value in payload.items() if key != "records"}
    return pd.DataFrame(records), meta


def parse_wkt_point(value: Any) -> tuple[float, float]:
    text = "" if value is None else str(value)
    match = WKT_POINT_RE.search(text)
    if not match:
        return math.nan, math.nan
    return float(match.group(1)), float(match.group(2))


def classify_time_period(hour: int) -> str:
    if 0 <= hour <= 5:
        return "madrugada"
    if 6 <= hour <= 9:
        return "pico_manana"
    if 10 <= hour <= 11:
        return "media_manana"
    if 12 <= hour <= 13:
        return "mediodia"
    if 14 <= hour <= 16:
        return "tarde"
    if 17 <= hour <= 19:
        return "pico_tarde"
    return "noche"


def add_temporal_and_spatial_fields(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["datetime_utc"] = pd.to_datetime(out["ts"], errors="coerce", utc=True)
    out["datetime_local"] = out["datetime_utc"].dt.tz_convert(LOCAL_TZ)
    out["event_date_local"] = out["datetime_local"].dt.date.astype(str)
    out["event_hour"] = out["datetime_local"].dt.hour
    out["event_minute"] = out["datetime_local"].dt.minute
    out["time_period"] = out["event_hour"].fillna(-1).astype(int).map(classify_time_period)
    out["is_peak_morning"] = out["event_hour"].between(6, 9)
    out["is_peak_evening"] = out["event_hour"].between(17, 19)
    out["is_night"] = out["event_hour"].isin([20, 21, 22, 23, 0, 1, 2, 3, 4, 5])

    coords = out["geoWKT"].map(parse_wkt_point)
    out["lon"] = coords.map(lambda pair: pair[0])
    out["lat"] = coords.map(lambda pair: pair[1])
    out["cluster_lon"] = pd.to_numeric(out["cluster_center_lon"], errors="coerce")
    out["cluster_lat"] = pd.to_numeric(out["cluster_center_lat"], errors="coerce")
    out["has_valid_coordinate"] = out["lon"].between(-90.4, -87.5) & out["lat"].between(13.0, 14.7)

    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32616", always_xy=True)
    x, y = transformer.transform(out["lon"].fillna(0).to_numpy(), out["lat"].fillna(0).to_numpy())
    cx, cy = transformer.transform(out["cluster_lon"].fillna(0).to_numpy(), out["cluster_lat"].fillna(0).to_numpy())
    out["x_utm"] = x
    out["y_utm"] = y
    out["cluster_x_utm"] = cx
    out["cluster_y_utm"] = cy
    out["geo_cluster_distance_m"] = (
        (out["x_utm"] - out["cluster_x_utm"]) ** 2 + (out["y_utm"] - out["cluster_y_utm"]) ** 2
    ) ** 0.5

    out["cluster_start_utc"] = pd.to_datetime(out["cluster_start_ts"], errors="coerce", utc=True)
    out["cluster_last_utc"] = pd.to_datetime(out["cluster_last_ts"], errors="coerce", utc=True)
    out["cluster_duration_min"] = (
        (out["cluster_last_utc"] - out["cluster_start_utc"]).dt.total_seconds().fillna(0).clip(lower=0) / 60
    )
    return out


def write_field_diagnostics(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    total = len(df)
    for col in df.columns:
        null_count = int(df[col].isna().sum())
        blank_count = int((df[col].fillna("").astype(str).str.strip() == "").sum())
        rows.append(
            {
                "field": col,
                "dtype": str(df[col].dtype),
                "non_null": int(total - null_count),
                "null_count": null_count,
                "null_pct": pct(null_count, total),
                "blank_or_null_count": blank_count,
                "blank_or_null_pct": pct(blank_count, total),
                "unique_count": int(df[col].nunique(dropna=True)),
            }
        )
    diagnostics = pd.DataFrame(rows)
    diagnostics.to_csv(RESULTS_DIR / "diagnostico_campos_alerts.csv", index=False)
    return diagnostics


def write_initial_distributions(df: pd.DataFrame) -> None:
    hourly = df.groupby("event_hour", dropna=False).agg(
        alerts=("uuid", "nunique"),
        reports=("cluster_report_count", "sum"),
        avg_reliability=("reliability", "mean"),
        avg_report_rating=("reportRating", "mean"),
    ).reset_index()
    hourly.to_csv(RESULTS_DIR / "distribucion_horaria_alerts.csv", index=False)

    type_dist = df.groupby(["type", "subtype"], dropna=False).agg(
        alerts=("uuid", "nunique"),
        reports=("cluster_report_count", "sum"),
        avg_reliability=("reliability", "mean"),
        avg_report_rating=("reportRating", "mean"),
    ).reset_index().sort_values(["alerts", "reports"], ascending=False)
    type_dist.to_csv(RESULTS_DIR / "distribucion_tipo_alerta.csv", index=False)

    city_dist = df.groupby("city", dropna=False).agg(
        alerts=("uuid", "nunique"),
        reports=("cluster_report_count", "sum"),
    ).reset_index().sort_values("alerts", ascending=False)
    city_dist.to_csv(RESULTS_DIR / "distribucion_ciudad_alerts.csv", index=False)


def add_text_fields(alerts: pd.DataFrame) -> pd.DataFrame:
    out = alerts.copy()
    out["street_norm"] = out["street"].map(normalize_road_text)
    out["city_norm"] = out["city"].map(compact_text)
    out["road_text_combined"] = out["street_norm"].fillna("").map(compact_text)
    out["route_ref"] = out["street"].map(lambda value: ";".join(extract_route_refs(value)))
    out["has_street"] = out["street_norm"].fillna("").ne("")
    out["has_route_ref"] = out["route_ref"].fillna("").ne("")
    out[
        [
            "uuid",
            "street",
            "city",
            "street_norm",
            "city_norm",
            "road_text_combined",
            "route_ref",
            "has_street",
            "has_route_ref",
        ]
    ].to_csv(RESULTS_DIR / "waze_alerts_text_normalization.csv", index=False)
    return out


def subtype_text(row: pd.Series) -> str:
    subtype = str(row.get("subtype", "") or "").strip()
    alert_type = str(row.get("type", "") or "").strip()
    if subtype:
        return subtype
    return alert_type


def classify_alert_group(alert_type: str, subtype: str) -> str:
    t = str(alert_type or "").upper()
    s = str(subtype or "").upper()
    if t == "ACCIDENT":
        return "ACCIDENTE"
    if t == "ROAD_CLOSED":
        return "CIERRE_VIAL"
    if t == "JAM":
        if "STAND_STILL" in s:
            return "TRAFICO_DETENIDO"
        if "HEAVY" in s:
            return "TRAFICO_PESADO"
        return "CONGESTION_REPORTADA"
    if t == "HAZARD":
        if "POT_HOLE" in s:
            return "BACHE"
        if "LANE_CLOSED" in s or "CONSTRUCTION" in s:
            return "OBRA_CARRIL_CERRADO"
        if "CAR_STOPPED" in s:
            return "VEHICULO_DETENIDO"
        if "OBJECT" in s:
            return "OBJETO_EN_VIA"
        if "TRAFFIC_LIGHT" in s:
            return "FALLA_SEMAFORO"
        if "WEATHER" in s or "FLOOD" in s or "FOG" in s or "ICE" in s:
            return "CLIMA_RIESGO"
        return "PELIGRO_EN_VIA"
    return "OTRO"


def severity_from_type(alert_type: str, subtype: str) -> float:
    t = str(alert_type or "").upper()
    s = str(subtype or "").upper()
    if t == "ROAD_CLOSED":
        return 92.0
    if t == "ACCIDENT":
        return 88.0 if "MAJOR" not in s else 96.0
    if t == "JAM":
        if "STAND_STILL" in s:
            return 76.0
        if "HEAVY" in s:
            return 66.0
        return 56.0
    if t == "HAZARD":
        if "LANE_CLOSED" in s:
            return 72.0
        if "CONSTRUCTION" in s:
            return 62.0
        if "CAR_STOPPED" in s:
            return 58.0
        if "TRAFFIC_LIGHT" in s:
            return 64.0
        if "FLOOD" in s:
            return 78.0
        if "ICE" in s:
            return 70.0
        if "OBJECT" in s:
            return 55.0
        if "POT_HOLE" in s:
            return 48.0
        if "WEATHER" in s or "FOG" in s:
            return 52.0
        return 50.0
    return 35.0


def add_alert_classification(alerts: pd.DataFrame) -> pd.DataFrame:
    out = alerts.copy()
    out["alert_type_norm"] = out.apply(
        lambda row: ALERT_TYPE_LABELS.get(str(row.get("type", "")).upper(), title_case(row.get("type", ""))),
        axis=1,
    )
    out["alert_subtype_norm"] = out.apply(
        lambda row: SUBTYPE_LABELS.get(str(row.get("subtype", "")).upper(), title_case(subtype_text(row))),
        axis=1,
    )
    out["alert_group"] = out.apply(lambda row: classify_alert_group(row.get("type", ""), row.get("subtype", "")), axis=1)
    out["severity_base"] = out.apply(lambda row: severity_from_type(row.get("type", ""), row.get("subtype", "")), axis=1)
    cluster_boost = (robust_norm(out["cluster_report_count"], upper_quantile=0.99) * 8).fillna(0)
    out["severity_proxy"] = (out["severity_base"] + cluster_boost).clip(0, 100).round(3)
    return out


class OSMSpatialIndex:
    def __init__(self, segments: pd.DataFrame, transformer: Transformer) -> None:
        self.segments = segments.reset_index(drop=True)
        self.transformer = transformer
        mid_x: list[float] = []
        mid_y: list[float] = []
        x1s: list[float] = []
        y1s: list[float] = []
        x2s: list[float] = []
        y2s: list[float] = []
        seg_idx: list[int] = []

        for idx, geom_value in enumerate(self.segments["geometry_json"].fillna("")):
            try:
                coords = json.loads(geom_value)
            except Exception:
                continue
            if not isinstance(coords, list) or len(coords) < 2:
                continue
            try:
                lons = [float(pair[0]) for pair in coords]
                lats = [float(pair[1]) for pair in coords]
            except Exception:
                continue
            xs, ys = transformer.transform(lons, lats)
            for pos in range(len(xs) - 1):
                ax, ay, bx, by = float(xs[pos]), float(ys[pos]), float(xs[pos + 1]), float(ys[pos + 1])
                if ax == bx and ay == by:
                    continue
                mid_x.append((ax + bx) / 2)
                mid_y.append((ay + by) / 2)
                x1s.append(ax)
                y1s.append(ay)
                x2s.append(bx)
                y2s.append(by)
                seg_idx.append(idx)

        self.mid_x = pd.Series(mid_x, dtype="float64").to_numpy()
        self.mid_y = pd.Series(mid_y, dtype="float64").to_numpy()
        self.x1 = pd.Series(x1s, dtype="float64").to_numpy()
        self.y1 = pd.Series(y1s, dtype="float64").to_numpy()
        self.x2 = pd.Series(x2s, dtype="float64").to_numpy()
        self.y2 = pd.Series(y2s, dtype="float64").to_numpy()
        self.seg_idx = pd.Series(seg_idx, dtype="int64").to_numpy()
        self.tree = cKDTree(list(zip(self.mid_x, self.mid_y))) if len(self.mid_x) else None

    @staticmethod
    def _point_segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
        dx = bx - ax
        dy = by - ay
        denom = dx * dx + dy * dy
        if denom <= 0:
            return math.hypot(px - ax, py - ay)
        t = ((px - ax) * dx + (py - ay) * dy) / denom
        t = max(0.0, min(1.0, t))
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        return math.hypot(px - proj_x, py - proj_y)

    def nearest(self, lon: float, lat: float, k: int = 80) -> dict[str, Any]:
        if self.tree is None or pd.isna(lon) or pd.isna(lat):
            return {}
        px, py = self.transformer.transform(float(lon), float(lat))
        query_k = min(k, len(self.mid_x))
        _, candidate_idx = self.tree.query([px, py], k=query_k)
        if query_k == 1:
            candidate_idx = [int(candidate_idx)]
        best_piece = None
        best_distance = math.inf
        for idx in candidate_idx:
            idx = int(idx)
            dist = self._point_segment_distance(px, py, self.x1[idx], self.y1[idx], self.x2[idx], self.y2[idx])
            if dist < best_distance:
                best_distance = dist
                best_piece = idx
        if best_piece is None:
            return {}
        row = self.segments.iloc[int(self.seg_idx[best_piece])].to_dict()
        row["nearest_osm_distance_m"] = round(float(best_distance), 3)
        return row


def load_osm_spatial_index() -> OSMSpatialIndex:
    usecols = [
        "source_department",
        "source_department_slug",
        "osm_way_id",
        "name",
        "ref",
        "alt_name",
        "official_name",
        "highway",
        "oneway",
        "lanes",
        "maxspeed",
        "surface",
        "length_m",
        "name_norm",
        "ref_norm",
        "alt_name_norm",
        "official_name_norm",
        "road_key_norm",
        "road_type_category",
        "geometry_json",
    ]
    segments = pd.read_csv(OSM_NATIONAL_SEGMENTS_PATH, usecols=lambda col: col in usecols, low_memory=False)
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32616", always_xy=True)
    return OSMSpatialIndex(segments, transformer)


def osm_match_status(distance_m: float | None) -> tuple[str, float]:
    if distance_m is None or pd.isna(distance_m):
        return "NO_COORDINATE_FOR_OSM", 0.0
    if distance_m <= SPATIAL_HIGH_M:
        return "SPATIAL_HIGH", 1.0
    if distance_m <= SPATIAL_MEDIUM_M:
        return "SPATIAL_MEDIUM", 0.75
    if distance_m <= SPATIAL_LOW_M:
        return "SPATIAL_LOW_REVIEW", 0.45
    return "SPATIAL_FAR_REVIEW", 0.15


def spatial_quality(row: pd.Series) -> str:
    if not row.get("has_valid_coordinate", False):
        return "INVALID_OR_MISSING_COORDINATE"
    dist = float(row.get("geo_cluster_distance_m", 0) or 0)
    if dist <= 10:
        return "VALID_COORD_CLUSTER_ALIGNED"
    if dist <= 100:
        return "VALID_COORD_CLUSTER_OFFSET_SMALL"
    return "VALID_COORD_CLUSTER_OFFSET_REVIEW"


def resolve_text_corridor(
    street: Any,
    city: Any,
    osm_name_map: dict[str, str],
    osm_ref_map: dict[str, str],
    osm_names: set[str],
    osm_name_meta: dict[str, dict[str, Any]],
    osm_ref_meta: dict[str, dict[str, Any]],
    alias_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    street_norm = normalize_road_text(street)
    row = pd.Series(
        {
            "street_modal": street,
            "street_norm": street_norm,
            "start_node_norm": "",
            "end_node_norm": "",
            "city_norm": compact_text(city),
            "route_ref": ";".join(extract_route_refs(street)),
        }
    )
    return resolve_corridor(row, osm_name_map, osm_ref_map, osm_names, osm_name_meta, osm_ref_meta, alias_lookup)


def build_spatial_street(row: pd.Series) -> str:
    ref = str(row.get("nearest_osm_ref", "") or "").strip()
    name = str(row.get("nearest_osm_name", "") or "").strip()
    alt_name = str(row.get("nearest_osm_alt_name", "") or "").strip()
    official = str(row.get("nearest_osm_official_name", "") or "").strip()
    road_key = str(row.get("nearest_osm_road_key_norm", "") or "").strip()
    parts = [part for part in [ref, name, alt_name, official] if part and part.lower() != "nan"]
    if parts:
        return " / ".join(parts)
    if road_key and not compact_text(road_key).startswith("osm way"):
        return title_case(road_key)
    return ""


def add_osm_and_corridor_resolution(alerts: pd.DataFrame) -> pd.DataFrame:
    spatial_index = load_osm_spatial_index()
    osm_name_map, osm_ref_map, osm_names, osm_name_meta, osm_ref_meta = build_osm_lookup()
    alias_lookup = load_alias_lookup()

    nearest_rows: list[dict[str, Any]] = []
    for _, row in alerts.iterrows():
        if bool(row.get("has_valid_coordinate", False)):
            nearest = spatial_index.nearest(row.get("lon"), row.get("lat"))
        else:
            nearest = {}
        nearest_rows.append(
            {
                "nearest_osm_way_id": nearest.get("osm_way_id", ""),
                "nearest_osm_name": nearest.get("name", ""),
                "nearest_osm_ref": nearest.get("ref", ""),
                "nearest_osm_alt_name": nearest.get("alt_name", ""),
                "nearest_osm_official_name": nearest.get("official_name", ""),
                "nearest_osm_highway": nearest.get("highway", ""),
                "nearest_osm_road_type": nearest.get("road_type_category", ""),
                "nearest_osm_oneway": nearest.get("oneway", ""),
                "nearest_osm_lanes": nearest.get("lanes", ""),
                "nearest_osm_maxspeed": nearest.get("maxspeed", ""),
                "nearest_osm_surface": nearest.get("surface", ""),
                "nearest_osm_length_m": nearest.get("length_m", ""),
                "nearest_osm_road_key_norm": nearest.get("road_key_norm", ""),
                "nearest_osm_department": nearest.get("source_department", ""),
                "nearest_osm_distance_m": nearest.get("nearest_osm_distance_m", math.nan),
            }
        )

    nearest_df = pd.DataFrame(nearest_rows, index=alerts.index)
    out = pd.concat([alerts, nearest_df], axis=1)
    statuses = out["nearest_osm_distance_m"].map(lambda value: osm_match_status(value))
    out["osm_match_status"] = statuses.map(lambda pair: pair[0])
    out["osm_spatial_confidence_score"] = statuses.map(lambda pair: pair[1])
    out["spatial_quality"] = out.apply(spatial_quality, axis=1)

    text_payloads: list[dict[str, Any]] = []
    spatial_payloads: list[dict[str, Any]] = []
    final_rows: list[dict[str, Any]] = []
    for _, row in out.iterrows():
        text_res = resolve_text_corridor(
            row.get("street", ""),
            row.get("city", ""),
            osm_name_map,
            osm_ref_map,
            osm_names,
            osm_name_meta,
            osm_ref_meta,
            alias_lookup,
        )
        spatial_street = build_spatial_street(row)
        spatial_res = resolve_text_corridor(
            spatial_street,
            row.get("city", ""),
            osm_name_map,
            osm_ref_map,
            osm_names,
            osm_name_meta,
            osm_ref_meta,
            alias_lookup,
        )
        text_payloads.append({f"text_{key}": value for key, value in text_res.items()})
        spatial_payloads.append({f"spatial_{key}": value for key, value in spatial_res.items()})

        spatial_status = str(row.get("osm_match_status", ""))
        spatial_ok = spatial_status in {"SPATIAL_HIGH", "SPATIAL_MEDIUM", "SPATIAL_LOW_REVIEW"}
        spatial_resolved = spatial_res.get("corridor_match_status") == "RESOLVED"
        text_resolved = text_res.get("corridor_match_status") == "RESOLVED"
        text_conf = text_res.get("corridor_match_confidence", "UNRESOLVED")
        spatial_conf = spatial_res.get("corridor_match_confidence", "UNRESOLVED")

        source = "UNRESOLVED"
        detail = ""
        chosen = text_res
        if spatial_ok and spatial_resolved:
            chosen = spatial_res
            source = "SPATIAL_OSM"
            detail = f"{spatial_status}:{spatial_res.get('corridor_resolution_detail', '')}"
            if (
                text_resolved
                and text_conf == "HIGH"
                and compact_text(text_res.get("corridor_norm_waze", ""))
                != compact_text(spatial_res.get("corridor_norm_waze", ""))
            ):
                chosen = text_res
                source = "TEXT_FUNCTIONAL_WITH_SPATIAL_SUPPORT"
                detail = f"{spatial_status}:TEXT_HIGH_OSM_LOCAL_DIFFERENT"
        elif text_resolved:
            chosen = text_res
            source = "TEXT_FALLBACK"
            detail = text_res.get("corridor_resolution_detail", "")
        else:
            chosen = spatial_res if spatial_resolved else text_res
            source = "UNRESOLVED"
            detail = "NO_SPATIAL_OR_TEXT_CORRIDOR"

        refs = [ref for ref in str(row.get("route_ref", "")).split(";") if ref]
        corridor = chosen.get("corridor_norm_waze", "")
        method = chosen.get("corridor_match_method", "UNRESOLVED")
        alias_meta = None
        if not corridor and text_resolved:
            corridor = text_res.get("corridor_norm_waze", "")
        final_rows.append(
            {
                "corridor_norm_alert": corridor,
                "corridor_local_name_alert": row.get("nearest_osm_name")
                or row.get("nearest_osm_ref")
                or chosen.get("corridor_local_name_waze", ""),
                "corridor_group_alert": infer_corridor_group(corridor, method, refs, alias_meta),
                "road_scope_alert": infer_road_scope(corridor, method, refs, alias_meta),
                "corridor_match_source": source,
                "corridor_match_method": method,
                "corridor_match_confidence": chosen.get("corridor_match_confidence", "UNRESOLVED"),
                "corridor_match_status": chosen.get("corridor_match_status", "UNRESOLVED"),
                "corridor_resolution_detail": detail,
            }
        )

    out = pd.concat(
        [
            out,
            pd.DataFrame(text_payloads, index=out.index),
            pd.DataFrame(spatial_payloads, index=out.index),
            pd.DataFrame(final_rows, index=out.index),
        ],
        axis=1,
    )
    confidence_score = {"HIGH": 1.0, "MEDIUM": 0.66, "LOW": 0.33, "UNRESOLVED": 0.0}
    out["corridor_match_confidence_score"] = out["corridor_match_confidence"].map(confidence_score).fillna(0.0)
    out["corridor_norm_alert_group"] = out["corridor_norm_alert"].replace("", "UNRESOLVED").fillna("UNRESOLVED")
    out[
        [
            "uuid",
            "type",
            "subtype",
            "city",
            "street",
            "lon",
            "lat",
            "nearest_osm_distance_m",
            "osm_match_status",
            "nearest_osm_name",
            "nearest_osm_ref",
            "nearest_osm_highway",
            "nearest_osm_road_type",
            "nearest_osm_department",
            "text_corridor_norm_waze",
            "text_corridor_match_method",
            "spatial_corridor_norm_waze",
            "spatial_corridor_match_method",
            "corridor_norm_alert",
            "corridor_local_name_alert",
            "corridor_match_source",
            "corridor_match_method",
            "corridor_match_confidence",
            "corridor_resolution_detail",
        ]
    ].to_csv(RESULTS_DIR / "waze_alerts_osm_matches.csv", index=False)
    return out


def add_alert_metrics(alerts: pd.DataFrame) -> pd.DataFrame:
    out = alerts.copy()
    reliability_norm = pd.to_numeric(out["reliability"], errors="coerce").fillna(0).clip(0, 10) / 10
    rating_norm = pd.to_numeric(out["reportRating"], errors="coerce").fillna(0).clip(0, 5) / 5
    confidence_norm = pd.to_numeric(out["confidence"], errors="coerce").fillna(0).clip(0, 5) / 5
    cluster_norm = robust_norm(out["cluster_report_count"], upper_quantile=0.99)
    duration_norm = robust_norm(out["cluster_duration_min"], upper_quantile=0.99)
    out["alert_reliability_proxy"] = (
        100
        * (
            0.35 * reliability_norm
            + 0.20 * rating_norm
            + 0.20 * cluster_norm
            + 0.15 * out["osm_spatial_confidence_score"].fillna(0)
            + 0.10 * confidence_norm
        )
    ).round(3)
    out["alert_impact_score"] = (
        0.48 * out["severity_proxy"]
        + 0.22 * out["alert_reliability_proxy"]
        + 20 * 0.15 * cluster_norm
        + 20 * 0.10 * duration_norm
        + 20 * 0.05 * out["osm_spatial_confidence_score"].fillna(0)
    ).clip(0, 100).round(3)
    out["is_critical_alert"] = out["alert_group"].isin(["ACCIDENTE", "CIERRE_VIAL", "TRAFICO_DETENIDO"])
    out["is_safety_alert"] = out["alert_group"].isin(
        ["ACCIDENTE", "PELIGRO_EN_VIA", "BACHE", "VEHICULO_DETENIDO", "OBJETO_EN_VIA", "CLIMA_RIESGO"]
    )
    out["is_operational_alert"] = out["alert_group"].isin(
        ["CIERRE_VIAL", "TRAFICO_DETENIDO", "TRAFICO_PESADO", "OBRA_CARRIL_CERRADO", "FALLA_SEMAFORO"]
    )
    out = add_density_fields(out)
    out.to_csv(RESULTS_DIR / "waze_alerts_unique_enriched.csv", index=False)
    return out


def add_density_fields(alerts: pd.DataFrame) -> pd.DataFrame:
    out = alerts.copy()
    out["grid_x_1km"] = (out["x_utm"] // GRID_SIZE_M).astype(int)
    out["grid_y_1km"] = (out["y_utm"] // GRID_SIZE_M).astype(int)
    grid = out.groupby(["grid_x_1km", "grid_y_1km"], dropna=False).agg(
        alerts=("uuid", "nunique"),
        reports=("cluster_report_count", "sum"),
        impact_total=("alert_impact_score", "sum"),
        severity_avg=("severity_proxy", "mean"),
        x_center=("x_utm", "mean"),
        y_center=("y_utm", "mean"),
    ).reset_index()
    transformer = Transformer.from_crs("EPSG:32616", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(grid["x_center"].to_numpy(), grid["y_center"].to_numpy())
    grid["lon_center"] = lon
    grid["lat_center"] = lat
    grid["alert_density"] = (100 * robust_norm(grid["alerts"], upper_quantile=0.99)).round(3)
    grid["impact_density"] = (100 * robust_norm(grid["impact_total"], upper_quantile=0.99)).round(3)
    grid.to_csv(RESULTS_DIR / "waze_alerts_heatmap_grid.csv", index=False)
    out = out.merge(
        grid[["grid_x_1km", "grid_y_1km", "alerts", "reports", "alert_density", "impact_density"]].rename(
            columns={
                "alerts": "grid_alert_count",
                "reports": "grid_report_count",
                "alert_density": "alert_density",
                "impact_density": "impact_density",
            }
        ),
        on=["grid_x_1km", "grid_y_1km"],
        how="left",
    )
    return out


def build_corridor_hour_panel(alerts: pd.DataFrame) -> pd.DataFrame:
    panel = alerts.groupby(["corridor_norm_alert_group", "event_hour"], dropna=False).agg(
        alerts_count=("uuid", "nunique"),
        reports_count=("cluster_report_count", "sum"),
        impact_total=("alert_impact_score", "sum"),
        impact_avg=("alert_impact_score", "mean"),
        severity_avg=("severity_proxy", "mean"),
        severity_total=("severity_proxy", "sum"),
        reliability_avg=("alert_reliability_proxy", "mean"),
        accident_count=("alert_group", lambda s: int((s == "ACCIDENTE").sum())),
        closure_count=("alert_group", lambda s: int((s == "CIERRE_VIAL").sum())),
        hazard_count=("type", lambda s: int((s == "HAZARD").sum())),
        jam_alert_count=("type", lambda s: int((s == "JAM").sum())),
        critical_alert_count=("is_critical_alert", "sum"),
        safety_alert_count=("is_safety_alert", "sum"),
        operational_alert_count=("is_operational_alert", "sum"),
        high_spatial_count=("osm_match_status", lambda s: int(s.isin(["SPATIAL_HIGH", "SPATIAL_MEDIUM"]).sum())),
        unresolved_count=("corridor_match_status", lambda s: int((s == "UNRESOLVED").sum())),
    ).reset_index()
    panel = panel.rename(columns={"corridor_norm_alert_group": "corridor_norm_alert"})
    panel["critical_alert_rate"] = (panel["critical_alert_count"] / panel["alerts_count"].clip(lower=1)).round(4)
    panel["high_spatial_rate"] = (panel["high_spatial_count"] / panel["alerts_count"].clip(lower=1)).round(4)
    panel.to_csv(RESULTS_DIR / "waze_alerts_corridor_hour.csv", index=False)
    return panel


def build_corridor_summary(panel: pd.DataFrame, alerts: pd.DataFrame) -> pd.DataFrame:
    summary = panel.groupby("corridor_norm_alert", dropna=False).agg(
        alerts_count_total=("alerts_count", "sum"),
        reports_count_total=("reports_count", "sum"),
        active_alert_hours=("event_hour", "nunique"),
        corridor_alert_impact=("impact_total", "sum"),
        corridor_severity_avg=("severity_avg", "mean"),
        corridor_reliability_avg=("reliability_avg", "mean"),
        accident_count_total=("accident_count", "sum"),
        closure_count_total=("closure_count", "sum"),
        hazard_count_total=("hazard_count", "sum"),
        jam_alert_count_total=("jam_alert_count", "sum"),
        critical_alert_count_total=("critical_alert_count", "sum"),
        safety_alert_count_total=("safety_alert_count", "sum"),
        operational_alert_count_total=("operational_alert_count", "sum"),
        high_spatial_count_total=("high_spatial_count", "sum"),
        unresolved_count_total=("unresolved_count", "sum"),
    ).reset_index()
    summary["corridor_alert_recurrence"] = (summary["active_alert_hours"] / TOTAL_HOURS).round(4)
    summary["critical_alert_rate"] = (
        summary["critical_alert_count_total"] / summary["alerts_count_total"].clip(lower=1)
    ).round(4)
    summary["safety_alert_rate"] = (
        summary["safety_alert_count_total"] / summary["alerts_count_total"].clip(lower=1)
    ).round(4)
    summary["high_spatial_rate"] = (
        summary["high_spatial_count_total"] / summary["alerts_count_total"].clip(lower=1)
    ).round(4)

    peak = panel.sort_values(["corridor_norm_alert", "impact_total"], ascending=[True, False]).drop_duplicates(
        "corridor_norm_alert"
    )[["corridor_norm_alert", "event_hour", "impact_total"]]
    peak = peak.rename(columns={"event_hour": "peak_alert_hour", "impact_total": "peak_hour_impact"})
    summary = summary.merge(peak, on="corridor_norm_alert", how="left")

    pressure = (
        0.24 * robust_norm(summary["alerts_count_total"])
        + 0.24 * robust_norm(summary["corridor_alert_impact"])
        + 0.16 * robust_norm(summary["reports_count_total"])
        + 0.14 * robust_norm(summary["active_alert_hours"], upper_quantile=1.0)
        + 0.12 * robust_norm(summary["critical_alert_rate"], upper_quantile=1.0)
        + 0.10 * robust_norm(summary["corridor_reliability_avg"])
    )
    summary["corridor_alert_pressure"] = (100 * pressure).round(4)
    summary.loc[summary["corridor_norm_alert"].eq("UNRESOLVED"), "corridor_alert_pressure"] = 0.0

    type_mix = alerts.groupby("corridor_norm_alert_group")["alert_group"].nunique().reset_index(name="alert_group_diversity")
    type_mix = type_mix.rename(columns={"corridor_norm_alert_group": "corridor_norm_alert"})
    summary = summary.merge(type_mix, on="corridor_norm_alert", how="left")
    summary = summary.sort_values("corridor_alert_pressure", ascending=False)
    summary.to_csv(RESULTS_DIR / "waze_alerts_corridor_summary.csv", index=False)
    return summary


def build_quality_outputs(raw: pd.DataFrame, alerts: pd.DataFrame, summary: pd.DataFrame) -> pd.DataFrame:
    total_raw = len(raw)
    total_alerts = len(alerts)
    resolved = int(alerts["corridor_match_status"].eq("RESOLVED").sum())
    quality_rows = [
        ("raw_rows", total_raw, "Filas crudas del JSON."),
        ("unique_alerts_uuid", alerts["uuid"].nunique(), "Alertas unicas por uuid."),
        ("exact_duplicate_rows", int(raw.duplicated().sum()), "Duplicados exactos en filas crudas."),
        ("uuid_duplicate_rows", int(total_raw - raw["uuid"].nunique()), "Filas que exceden el conteo de uuid unico."),
        ("cluster_id_unique", raw["cluster_id"].nunique(), "Clusters unicos reportados por Waze."),
        ("cluster_report_count_total", int(alerts["cluster_report_count"].sum()), "Suma de reportes dentro de clusters."),
        ("street_empty_count", int(alerts["street_norm"].eq("").sum()), "Alertas sin street despues de normalizacion."),
        ("street_empty_pct", pct(int(alerts["street_norm"].eq("").sum()), total_alerts), "Porcentaje de alertas sin street."),
        ("city_null_count", int(alerts["city"].isna().sum()), "Alertas sin ciudad."),
        ("city_null_pct", pct(int(alerts["city"].isna().sum()), total_alerts), "Porcentaje de alertas sin ciudad."),
        ("valid_coordinate_count", int(alerts["has_valid_coordinate"].sum()), "Alertas con coordenada plausible en El Salvador."),
        ("valid_coordinate_pct", pct(int(alerts["has_valid_coordinate"].sum()), total_alerts), "Porcentaje con coordenada plausible."),
        ("spatial_high_count", int(alerts["osm_match_status"].eq("SPATIAL_HIGH").sum()), "Match OSM espacial <= 50 m."),
        ("spatial_medium_count", int(alerts["osm_match_status"].eq("SPATIAL_MEDIUM").sum()), "Match OSM espacial <= 150 m."),
        ("spatial_low_review_count", int(alerts["osm_match_status"].eq("SPATIAL_LOW_REVIEW").sum()), "Match OSM espacial <= 500 m."),
        ("spatial_far_review_count", int(alerts["osm_match_status"].eq("SPATIAL_FAR_REVIEW").sum()), "Match OSM espacial > 500 m."),
        ("corridor_assigned_count", resolved, "Alertas con corredor resuelto."),
        ("corridor_assigned_pct", pct(resolved, total_alerts), "Porcentaje de alertas con corredor resuelto."),
        ("unresolved_count", int(alerts["corridor_match_status"].eq("UNRESOLVED").sum()), "Alertas sin corredor final."),
        ("critical_alert_count", int(alerts["is_critical_alert"].sum()), "Alertas criticas: accidente, cierre o trafico detenido."),
        ("safety_alert_count", int(alerts["is_safety_alert"].sum()), "Alertas de seguridad vial."),
    ]
    quality = pd.DataFrame(quality_rows, columns=["metric", "value", "description"])
    quality.to_csv(RESULTS_DIR / "waze_alerts_quality_diagnostics.csv", index=False)

    unresolved = alerts[alerts["corridor_match_status"].eq("UNRESOLVED")].copy()
    unresolved[
        [
            "uuid",
            "event_hour",
            "type",
            "subtype",
            "alert_group",
            "city",
            "street",
            "lon",
            "lat",
            "osm_match_status",
            "nearest_osm_distance_m",
            "alert_impact_score",
            "severity_proxy",
        ]
    ].sort_values("alert_impact_score", ascending=False).to_csv(RESULTS_DIR / "waze_alerts_unresolved_corridors.csv", index=False)

    impact_p99 = alerts["alert_impact_score"].quantile(0.99)
    report_p99 = alerts["cluster_report_count"].quantile(0.99)
    extreme = alerts[
        (alerts["alert_impact_score"] >= impact_p99)
        | (alerts["cluster_report_count"] >= report_p99)
        | alerts["is_critical_alert"]
        | alerts["osm_match_status"].isin(["SPATIAL_LOW_REVIEW", "SPATIAL_FAR_REVIEW"])
    ].copy()
    extreme[
        [
            "uuid",
            "event_hour",
            "type",
            "subtype",
            "alert_group",
            "city",
            "street",
            "corridor_norm_alert",
            "osm_match_status",
            "nearest_osm_distance_m",
            "cluster_report_count",
            "severity_proxy",
            "alert_reliability_proxy",
            "alert_impact_score",
        ]
    ].sort_values("alert_impact_score", ascending=False).to_csv(RESULTS_DIR / "waze_alerts_extreme_cases.csv", index=False)
    return quality


def build_conflicts(alerts: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    impact_p90 = float(alerts["alert_impact_score"].quantile(0.90))

    def add_issue(row: pd.Series, issue_type: str, reason: str) -> None:
        rows.append(
            {
                "uuid": row.get("uuid", ""),
                "event_hour": row.get("event_hour", ""),
                "type": row.get("type", ""),
                "subtype": row.get("subtype", ""),
                "alert_group": row.get("alert_group", ""),
                "city": row.get("city", ""),
                "street": row.get("street", ""),
                "route_ref": row.get("route_ref", ""),
                "lon": row.get("lon", ""),
                "lat": row.get("lat", ""),
                "nearest_osm_distance_m": row.get("nearest_osm_distance_m", ""),
                "osm_match_status": row.get("osm_match_status", ""),
                "nearest_osm_name": row.get("nearest_osm_name", ""),
                "nearest_osm_ref": row.get("nearest_osm_ref", ""),
                "text_corridor_norm": row.get("text_corridor_norm_waze", ""),
                "spatial_corridor_norm": row.get("spatial_corridor_norm_waze", ""),
                "corridor_norm_alert": row.get("corridor_norm_alert_group", ""),
                "corridor_match_source": row.get("corridor_match_source", ""),
                "corridor_match_confidence": row.get("corridor_match_confidence", ""),
                "alert_impact_score": row.get("alert_impact_score", ""),
                "issue_type": issue_type,
                "issue_reason": reason,
            }
        )

    for _, row in alerts.iterrows():
        text_corridor = compact_text(row.get("text_corridor_norm_waze", ""))
        spatial_corridor = compact_text(row.get("spatial_corridor_norm_waze", ""))
        if row.get("corridor_norm_alert_group", "") == "UNRESOLVED":
            add_issue(row, "UNRESOLVED", "No se pudo asociar la alerta a corredor.")
            if float(row.get("alert_impact_score", 0) or 0) >= impact_p90:
                add_issue(row, "UNRESOLVED_HIGH_IMPACT", "Alerta no resuelta con impacto alto.")
        if row.get("osm_match_status") in {"SPATIAL_LOW_REVIEW", "SPATIAL_FAR_REVIEW"}:
            add_issue(row, "LOW_SPATIAL_CONFIDENCE", "La coordenada queda lejos de la via OSM mas cercana.")
        if text_corridor and spatial_corridor and text_corridor != spatial_corridor:
            add_issue(row, "TEXT_OSM_CORRIDOR_MISMATCH", "El corredor textual y el corredor espacial OSM no coinciden.")
        if pd.isna(row.get("city")):
            add_issue(row, "MISSING_CITY", "La alerta no trae ciudad aunque si tiene coordenada.")
        if not row.get("has_street", False):
            add_issue(row, "MISSING_STREET", "La alerta no trae street; depende de la coordenada para OSM.")
        if row.get("corridor_match_confidence") == "LOW" and float(row.get("alert_impact_score", 0) or 0) >= impact_p90:
            add_issue(row, "LOW_CONFIDENCE_HIGH_IMPACT", "Alerta de alto impacto con baja confianza de corredor.")

    conflicts = pd.DataFrame(rows)
    if not conflicts.empty:
        conflicts = conflicts.sort_values(["issue_type", "alert_impact_score"], ascending=[True, False])
    conflicts.to_csv(RESULTS_DIR / "waze_alerts_corridor_conflicts.csv", index=False)
    return conflicts


def top_tables(alerts: pd.DataFrame, summary: pd.DataFrame) -> None:
    summary.sort_values("corridor_alert_pressure", ascending=False).head(30).to_csv(
        RESULTS_DIR / "top_corredores_por_alert_pressure.csv", index=False
    )
    summary.sort_values("corridor_alert_impact", ascending=False).head(30).to_csv(
        RESULTS_DIR / "top_corredores_por_alert_impact.csv", index=False
    )
    alerts.sort_values("alert_impact_score", ascending=False).head(75).to_csv(
        RESULTS_DIR / "top_alertas_por_impacto.csv", index=False
    )
    alerts.groupby(["alert_group", "alert_type_norm", "alert_subtype_norm"], dropna=False).agg(
        alerts=("uuid", "nunique"),
        reports=("cluster_report_count", "sum"),
        impact_total=("alert_impact_score", "sum"),
        severity_avg=("severity_proxy", "mean"),
        reliability_avg=("alert_reliability_proxy", "mean"),
    ).reset_index().sort_values("alerts", ascending=False).to_csv(RESULTS_DIR / "ranking_tipos_alerta.csv", index=False)


def save_barh(df: pd.DataFrame, x: str, y: str, title: str, path: Path, xlabel: str, color: str = "#2563eb") -> None:
    plot_df = df[[x, y]].dropna().head(15).iloc[::-1]
    fig, ax = plt.subplots(figsize=(11, 7))
    ax.barh(plot_df[y], plot_df[x], color=color)
    ax.set_title(title, loc="left", fontweight="bold")
    ax.set_xlabel(xlabel)
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def generate_figures(alerts: pd.DataFrame, panel: pd.DataFrame, summary: pd.DataFrame) -> None:
    hourly = alerts.groupby("event_hour").agg(
        alerts=("uuid", "nunique"),
        reports=("cluster_report_count", "sum"),
        impact=("alert_impact_score", "sum"),
        critical=("is_critical_alert", "sum"),
    ).reindex(range(24), fill_value=0)

    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.plot(hourly.index, hourly["alerts"], marker="o", color="#2563eb", label="Alertas")
    ax.plot(hourly.index, hourly["critical"], marker="o", color="#dc2626", label="Criticas")
    ax.set_title("Alertas Waze por hora", loc="left", fontweight="bold")
    ax.set_xlabel("Hora local")
    ax.set_ylabel("Alertas")
    ax.set_xticks(range(24))
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig_alerts_por_hora.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.plot(hourly.index, hourly["impact"], marker="o", color="#7c3aed")
    ax.set_title("Impacto agregado de alertas por hora", loc="left", fontweight="bold")
    ax.set_xlabel("Hora local")
    ax.set_ylabel("Suma alert_impact_score")
    ax.set_xticks(range(24))
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig_alert_impact_por_hora.png", dpi=180)
    plt.close(fig)

    group_counts = alerts["alert_group"].value_counts().reset_index()
    group_counts.columns = ["alert_group", "alerts"]
    save_barh(group_counts, "alerts", "alert_group", "Ranking de grupos de alerta", RESULTS_DIR / "fig_alerts_por_tipo.png", "Alertas", "#f59e0b")

    save_barh(
        summary.sort_values("corridor_alert_pressure", ascending=False),
        "corridor_alert_pressure",
        "corridor_norm_alert",
        "Top corredores por presion de alertas",
        RESULTS_DIR / "fig_top_corredores_alert_pressure.png",
        "Score 0-100",
        "#dc2626",
    )

    top_corridors = summary.head(20)["corridor_norm_alert"].tolist()
    matrix = panel[panel["corridor_norm_alert"].isin(top_corridors)].pivot_table(
        index="corridor_norm_alert", columns="event_hour", values="impact_total", aggfunc="sum", fill_value=0
    )
    for hour in range(24):
        if hour not in matrix.columns:
            matrix[hour] = 0
    matrix = matrix[range(24)]
    fig, ax = plt.subplots(figsize=(13, 8))
    im = ax.imshow(matrix.values, aspect="auto", cmap="magma")
    ax.set_title("Matriz corredor-hora por impacto de alertas", loc="left", fontweight="bold")
    ax.set_xlabel("Hora local")
    ax.set_ylabel("Corredor")
    ax.set_xticks(range(24))
    ax.set_yticks(range(len(matrix.index)))
    ax.set_yticklabels(matrix.index)
    fig.colorbar(im, ax=ax, label="Impacto total")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig_heatmap_corredor_hora_alerts.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 8))
    hb = ax.hexbin(alerts["lon"], alerts["lat"], gridsize=42, cmap="inferno", mincnt=1)
    ax.set_title("Mapa de calor de alertas Waze", loc="left", fontweight="bold")
    ax.set_xlabel("Longitud")
    ax.set_ylabel("Latitud")
    fig.colorbar(hb, ax=ax, label="Cantidad de alertas")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig_mapa_calor_alertas.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 8))
    hb = ax.hexbin(alerts["lon"], alerts["lat"], C=alerts["alert_impact_score"], reduce_C_function=sum, gridsize=42, cmap="viridis", mincnt=1)
    ax.set_title("Mapa de calor por impacto de alertas", loc="left", fontweight="bold")
    ax.set_xlabel("Longitud")
    ax.set_ylabel("Latitud")
    fig.colorbar(hb, ax=ax, label="Suma de impacto")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig_mapa_calor_impacto_alertas.png", dpi=180)
    plt.close(fig)

    status_counts = alerts["osm_match_status"].value_counts().reset_index()
    status_counts.columns = ["osm_match_status", "alerts"]
    save_barh(
        status_counts,
        "alerts",
        "osm_match_status",
        "Calidad de match espacial OSM",
        RESULTS_DIR / "fig_calidad_osm_alerts.png",
        "Alertas",
        "#10b981",
    )


def prepare_map_layers(alerts: pd.DataFrame, summary: pd.DataFrame) -> None:
    points = []
    for _, row in alerts.iterrows():
        if pd.isna(row.get("lon")) or pd.isna(row.get("lat")):
            continue
        props = {
            "uuid": row.get("uuid", ""),
            "type": row.get("type", ""),
            "subtype": row.get("subtype", ""),
            "alert_group": row.get("alert_group", ""),
            "city": row.get("city", ""),
            "street": row.get("street", ""),
            "event_hour": None if pd.isna(row.get("event_hour")) else int(row.get("event_hour")),
            "cluster_report_count": int(row.get("cluster_report_count", 0) or 0),
            "severity_proxy": float(row.get("severity_proxy", 0) or 0),
            "alert_impact_score": float(row.get("alert_impact_score", 0) or 0),
            "corridor_norm_alert": row.get("corridor_norm_alert", ""),
            "osm_match_status": row.get("osm_match_status", ""),
            "nearest_osm_distance_m": float(row.get("nearest_osm_distance_m", 0) or 0),
        }
        points.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(row["lon"]), float(row["lat"])]},
                "properties": props,
            }
        )
    geojson = {"type": "FeatureCollection", "features": points}
    (RESULTS_DIR / "waze_alerts_points.geojson").write_text(json.dumps(geojson, ensure_ascii=False), encoding="utf-8")

    layer = summary[summary["corridor_norm_alert"].ne("UNRESOLVED")].copy()
    layer["corridor_norm_key"] = layer["corridor_norm_alert"].map(compact_text)
    layer[
        [
            "corridor_norm_alert",
            "corridor_norm_key",
            "alerts_count_total",
            "reports_count_total",
            "corridor_alert_impact",
            "active_alert_hours",
            "critical_alert_rate",
            "high_spatial_rate",
            "corridor_alert_pressure",
        ]
    ].to_csv(RESULTS_DIR / "waze_alerts_corridor_layers.csv", index=False)


def write_diagnostics_report(
    meta: dict[str, Any],
    raw: pd.DataFrame,
    alerts: pd.DataFrame,
    summary: pd.DataFrame,
    quality: pd.DataFrame,
    conflicts: pd.DataFrame,
) -> None:
    lines: list[str] = []
    lines.append("Resultados del analisis Waze Alerts")
    lines.append("=" * 42)
    lines.append("")
    lines.append("Fuente")
    lines.append("------")
    for key in ["source", "project", "dataset", "table", "date", "tz", "record_count", "deduped_by_uuid", "geowkt_included"]:
        if key in meta:
            lines.append(f"- {key}: {meta[key]}")
    lines.append("")
    lines.append("Decision metodologica")
    lines.append("---------------------")
    lines.append(
        "El uuid se usa como alerta unica. cluster_report_count mide respaldo/corroboracion del cluster, "
        "no vehiculos. La coordenada es la fuente principal de asociacion OSM."
    )
    lines.append("")
    lines.append("Resumen general")
    lines.append("---------------")
    lines.append(f"- Filas crudas: {len(raw):,}")
    lines.append(f"- Alertas unicas por uuid: {alerts['uuid'].nunique():,}")
    lines.append(f"- Clusters unicos: {alerts['cluster_id'].nunique():,}")
    lines.append(f"- Suma cluster_report_count: {int(alerts['cluster_report_count'].sum()):,}")
    datetime_local = pd.to_datetime(alerts["datetime_local"], errors="coerce")
    lines.append(f"- Rango local: {datetime_local.min()} a {datetime_local.max()}")
    lines.append(f"- Coordenadas validas: {int(alerts['has_valid_coordinate'].sum()):,} ({pct(int(alerts['has_valid_coordinate'].sum()), len(alerts))}%)")
    lines.append(f"- Corredores resueltos: {int(alerts['corridor_match_status'].eq('RESOLVED').sum()):,} ({pct(int(alerts['corridor_match_status'].eq('RESOLVED').sum()), len(alerts))}%)")
    lines.append("")
    lines.append("Tipos de alerta")
    lines.append("---------------")
    for group, count in alerts["alert_group"].value_counts().head(12).items():
        lines.append(f"- {group}: {count:,}")
    lines.append("")
    lines.append("Horas criticas")
    lines.append("--------------")
    hourly = alerts.groupby("event_hour").agg(
        alerts=("uuid", "nunique"),
        reports=("cluster_report_count", "sum"),
        impact=("alert_impact_score", "sum"),
        critical=("is_critical_alert", "sum"),
    ).reset_index()
    for _, row in hourly.sort_values("impact", ascending=False).head(8).iterrows():
        lines.append(
            f"- Hora {int(row['event_hour']):02d}: {int(row['alerts']):,} alertas, "
            f"{int(row['reports']):,} reportes cluster, impacto {row['impact']:,.1f}, criticas {int(row['critical']):,}"
        )
    lines.append("")
    lines.append("Top corredores por presion de alertas")
    lines.append("-------------------------------------")
    ranked = summary[summary["corridor_norm_alert"].ne("UNRESOLVED")].copy()
    for _, row in ranked.head(15).iterrows():
        lines.append(
            f"- {row['corridor_norm_alert']}: score {row['corridor_alert_pressure']:.2f}, "
            f"alertas {int(row['alerts_count_total']):,}, reportes {int(row['reports_count_total']):,}, "
            f"impacto {row['corridor_alert_impact']:,.1f}, horas activas {int(row['active_alert_hours'])}"
        )
    lines.append("")
    lines.append("Calidad")
    lines.append("-------")
    for _, row in quality.iterrows():
        lines.append(f"- {row['metric']}: {row['value']} ({row['description']})")
    if not conflicts.empty:
        lines.append("")
        lines.append("Conflictos de asociacion")
        lines.append("------------------------")
        for issue, count in conflicts["issue_type"].value_counts().head(12).items():
            lines.append(f"- {issue}: {count:,}")
    lines.append("")
    lines.append("Potencial analitico")
    lines.append("-------------------")
    lines.append(
        "Alerts aporta una senal de eventos viales reportados por usuarios: accidentes, peligros, cierres, "
        "trafico detenido y condiciones de riesgo. A diferencia de jams, trae coordenadas puntuales y permite "
        "asociacion espacial directa a OSM."
    )
    lines.append("")
    lines.append("Limitaciones")
    lines.append("------------")
    lines.append("- Un dia de datos permite caracterizar la muestra, no patrones estructurales definitivos.")
    lines.append("- cluster_report_count no equivale a vehiculos afectados.")
    lines.append("- nThumbsUp esta en cero para todos los registros de este archivo.")
    lines.append("- city esta ausente en una parte importante, por lo que la coordenada es mas confiable para territorio.")
    (RESULTS_DIR / "resultados_waze_alerts.txt").write_text("\n".join(lines), encoding="utf-8")


def write_methodology_md() -> None:
    text = """# Metodologia Para El Analisis De `waze_alerts_2026-06-29.json`

## 1. Proposito

El objetivo es evaluar si Waze `alerts` aporta una senal util para una futura metrica o KPI de movilidad. A diferencia de `jams`, las alertas representan eventos reportados por usuarios: accidentes, peligros, cierres, trafico pesado, trafico detenido, objetos en via, vehiculos detenidos, construccion, fallas de semaforo y riesgos climaticos.

## 2. Unidad Analitica

La unidad analitica principal es `uuid`. El archivo se trata como deduplicado por alerta unica. `cluster_id` y `cluster_report_count` se conservan como senal de corroboracion del evento, no como conteo de vehiculos ni como numero de personas afectadas.

## 3. Flujo Del Pipeline

```text
Data/Waze/waze_alerts_2026-06-29.json
  -> ingesta y diagnostico
  -> normalizacion temporal
  -> extraccion de coordenadas geoWKT
  -> clasificacion type/subtype
  -> match espacial con OSM
  -> resolucion de corridor_norm_alert
  -> variables de severidad, confiabilidad, densidad e impacto
  -> panel corredor-hora
  -> resumen por corredor
  -> conflictos y calidad
  -> figuras, capas y resultados
```

## 4. Clasificacion De Alertas

Se construye `alert_group` a partir de `type` y `subtype`:

```text
ACCIDENTE
CIERRE_VIAL
TRAFICO_DETENIDO
TRAFICO_PESADO
CONGESTION_REPORTADA
PELIGRO_EN_VIA
BACHE
OBRA_CARRIL_CERRADO
VEHICULO_DETENIDO
OBJETO_EN_VIA
FALLA_SEMAFORO
CLIMA_RIESGO
```

Esta clasificacion permite separar seguridad vial, operacion vial y congestion reportada.

## 5. Asociacion A OSM

La coordenada de la alerta es la fuente primaria. Cada punto se proyecta a UTM 16N y se compara contra subsegmentos de la red OSM nacional. Se calcula distancia punto-linea y se clasifica:

```text
SPATIAL_HIGH <= 50 m
SPATIAL_MEDIUM <= 150 m
SPATIAL_LOW_REVIEW <= 500 m
SPATIAL_FAR_REVIEW > 500 m
```

El texto vial (`street`) se usa como respaldo funcional cuando OSM local y texto Waze no comparten el mismo nivel de nombre. Se conservan ambos:

```text
nearest_osm_name / nearest_osm_ref
text_corridor_norm_waze
spatial_corridor_norm_waze
corridor_norm_alert
corridor_match_source
```

Cuando la via OSM mas cercana no tiene `name`, `ref`, `alt_name` ni `official_name`, el identificador tecnico `osm_way_id` se conserva para auditoria, pero no se convierte en `corridor_norm_alert`. Esto evita que identificadores como `Osm Way 123` entren al ranking de corredores funcionales.

## 6. Variables Construidas

```text
alert_type_norm
alert_subtype_norm
alert_group
severity_proxy
alert_reliability_proxy
alert_impact_score
event_hour
spatial_quality
osm_match_status
alert_density
impact_density
corridor_alert_pressure
```

`severity_proxy` depende del tipo/subtipo de alerta y del respaldo del cluster. `alert_reliability_proxy` combina reliability, reportRating, cluster_report_count, confidence y calidad espacial. `alert_impact_score` sintetiza severidad, confiabilidad, respaldo y calidad espacial.

## 7. Resultados Esperados

El analisis debe producir:

```text
resumen general
distribucion temporal
ranking de tipos de alerta
ranking de corredores
calidad de coordenadas
calidad de asociacion OSM
casos extremos
conflictos de asociacion
mapas de calor
capas para dashboard
```

## 8. Relacion Conceptual Con Jams

`jams` mide presion operacional de congestion: demora, longitud afectada, velocidad y recurrencia. `alerts` mide eventos viales reportados por usuarios: accidentes, peligros, cierres y condiciones de riesgo. Las dos fuentes son complementarias:

```text
jams = estado operacional de congestion
alerts = eventos o condiciones que pueden explicar o anticipar congestion
noticias = amplificacion social/noticiosa de eventos viales
OSM = infraestructura vial base
```
"""
    (INFORME_DIR / "metodologia_waze_alerts.md").write_text(text, encoding="utf-8")


def write_results_md(alerts: pd.DataFrame, summary: pd.DataFrame, quality: pd.DataFrame, conflicts: pd.DataFrame) -> None:
    type_counts = alerts["alert_group"].value_counts().head(12)
    hourly = alerts.groupby("event_hour").agg(
        alerts=("uuid", "nunique"),
        impact=("alert_impact_score", "sum"),
        critical=("is_critical_alert", "sum"),
    ).reset_index().sort_values("impact", ascending=False).head(8)
    top_corridors = summary[summary["corridor_norm_alert"].ne("UNRESOLVED")].head(15)

    lines: list[str] = []
    lines.append("# Resultados Del Analisis De Waze Alerts")
    lines.append("")
    lines.append("## 1. Resumen Ejecutivo")
    lines.append("")
    lines.append(
        "Se analizo `Data/Waze/waze_alerts_2026-06-29.json` para evaluar su utilidad como senal de eventos viales reportados por usuarios. "
        "La fuente complementa a `jams`: mientras jams mide congestion operacional, alerts identifica condiciones puntuales como accidentes, cierres, peligros y trafico detenido."
    )
    lines.append("")
    lines.append("Indicadores principales:")
    lines.append("")
    lines.append("| Indicador | Valor |")
    lines.append("|---|---:|")
    lines.append(f"| Filas crudas | {len(alerts):,} |")
    lines.append(f"| Alertas unicas por uuid | {alerts['uuid'].nunique():,} |")
    lines.append(f"| Suma cluster_report_count | {int(alerts['cluster_report_count'].sum()):,} |")
    lines.append(f"| Coordenadas validas | {int(alerts['has_valid_coordinate'].sum()):,} |")
    lines.append(f"| Corredores resueltos | {int(alerts['corridor_match_status'].eq('RESOLVED').sum()):,} |")
    lines.append(f"| Alertas criticas | {int(alerts['is_critical_alert'].sum()):,} |")
    lines.append("")
    lines.append("## 2. Distribucion Por Tipo")
    lines.append("")
    lines.append("| Grupo | Alertas |")
    lines.append("|---|---:|")
    for group, count in type_counts.items():
        lines.append(f"| {group} | {int(count):,} |")
    lines.append("")
    lines.append("## 3. Horas De Mayor Impacto")
    lines.append("")
    lines.append("| Hora | Alertas | Criticas | Impacto |")
    lines.append("|---:|---:|---:|---:|")
    for _, row in hourly.iterrows():
        lines.append(f"| {int(row['event_hour'])} | {int(row['alerts']):,} | {int(row['critical']):,} | {row['impact']:,.1f} |")
    lines.append("")
    lines.append("## 4. Ranking De Corredores")
    lines.append("")
    lines.append("| Corredor | Alertas | Reportes | Impacto | Horas activas | Score |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for _, row in top_corridors.iterrows():
        lines.append(
            f"| {row['corridor_norm_alert']} | {int(row['alerts_count_total']):,} | {int(row['reports_count_total']):,} | "
            f"{row['corridor_alert_impact']:,.1f} | {int(row['active_alert_hours'])} | {row['corridor_alert_pressure']:.2f} |"
        )
    lines.append("")
    lines.append("## 5. Calidad Del Dato")
    lines.append("")
    lines.append("| Metrica | Valor | Descripcion |")
    lines.append("|---|---:|---|")
    for _, row in quality.iterrows():
        lines.append(f"| {row['metric']} | {row['value']} | {row['description']} |")
    lines.append("")
    lines.append("## 6. Conflictos")
    lines.append("")
    if conflicts.empty:
        lines.append("No se detectaron conflictos de asociacion.")
    else:
        lines.append("| Conflicto | Casos |")
        lines.append("|---|---:|")
        for issue, count in conflicts["issue_type"].value_counts().head(12).items():
            lines.append(f"| {issue} | {int(count):,} |")
    lines.append("")
    lines.append("## 7. Figuras Generadas")
    lines.append("")
    lines.append("![Alertas por hora](../../Results/Waze/Alerts/fig_alerts_por_hora.png)")
    lines.append("")
    lines.append("![Impacto por hora](../../Results/Waze/Alerts/fig_alert_impact_por_hora.png)")
    lines.append("")
    lines.append("![Tipos de alerta](../../Results/Waze/Alerts/fig_alerts_por_tipo.png)")
    lines.append("")
    lines.append("![Top corredores](../../Results/Waze/Alerts/fig_top_corredores_alert_pressure.png)")
    lines.append("")
    lines.append("![Heatmap corredor hora](../../Results/Waze/Alerts/fig_heatmap_corredor_hora_alerts.png)")
    lines.append("")
    lines.append("![Mapa de calor alertas](../../Results/Waze/Alerts/fig_mapa_calor_alertas.png)")
    lines.append("")
    lines.append("## 8. Lectura Frente A Jams")
    lines.append("")
    lines.append(
        "`alerts` aporta una capa de eventos y riesgos. `jams` aporta una capa de estado operacional. "
        "La integracion futura deberia buscar si accidentes, cierres o peligros elevan la presion de congestion en el mismo corredor y franja horaria."
    )
    lines.append("")
    lines.append("## 9. Nota Sobre Corredores No Resueltos")
    lines.append("")
    lines.append(
        "Las alertas no resueltas no necesariamente carecen de posicion. En varios casos la coordenada cae sobre un segmento OSM cercano, "
        "pero ese segmento no tiene nombre ni referencia vial. El pipeline conserva `nearest_osm_way_id` para auditoria, pero no usa identificadores "
        "tecnicos `Osm Way` como `corridor_norm_alert`."
    )
    lines.append("")
    lines.append("## 10. Conclusion")
    lines.append("")
    lines.append(
        "Waze alerts es una fuente apta para construir una senal complementaria de eventos viales. "
        "Su mayor fortaleza frente a noticias es la coordenada; su mayor fortaleza frente a jams es la clasificacion del evento. "
        "Su limitacion principal es que representa reportes de usuarios, no una medicion oficial de todos los eventos ocurridos."
    )
    (INFORME_DIR / "resultados_waze_alerts.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_dirs()
    raw, meta = load_alerts_json()
    raw = add_temporal_and_spatial_fields(raw)
    write_field_diagnostics(raw)
    write_initial_distributions(raw)
    alerts = add_text_fields(raw)
    alerts = add_alert_classification(alerts)
    alerts = add_osm_and_corridor_resolution(alerts)
    alerts = add_alert_metrics(alerts)
    panel = build_corridor_hour_panel(alerts)
    summary = build_corridor_summary(panel, alerts)
    quality = build_quality_outputs(raw, alerts, summary)
    conflicts = build_conflicts(alerts)
    top_tables(alerts, summary)
    generate_figures(alerts, panel, summary)
    prepare_map_layers(alerts, summary)
    write_diagnostics_report(meta, raw, alerts, summary, quality, conflicts)
    write_methodology_md()
    write_results_md(alerts, summary, quality, conflicts)
    print(f"Resultados Waze alerts generados en: {RESULTS_DIR}")
    print(f"Alertas unicas: {len(alerts):,}")
    print(f"Corredores en resumen: {len(summary):,}")


if __name__ == "__main__":
    main()
