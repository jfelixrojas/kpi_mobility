#!/usr/bin/env python3
"""
Evaluacion de aptitud de noticias como fuente auxiliar para metricas de movilidad.

Objetivo:
- No construye el KPI final de movilidad.
- Evalua si la fuente de noticias merece entrar al sistema de metricas.
- Produce evidencia sobre clasificabilidad, severidad, geocodificacion,
  asociacion vial OSM, confiabilidad, sesgos y brechas.

Salidas principales:
    Results/News/Evaluation/
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any
from urllib import parse, request

import matplotlib.pyplot as plt
import pandas as pd

from social_road_index_poc import markdown_table, normalize_text, pct


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "Results" / "News"
EVAL_DIR = RESULTS_DIR / "Evaluation"
PROCESSED_DIR = ROOT / "Data" / "Processed" / "news_source_evaluation"

BASE_CONTEXT_PATH = RESULTS_DIR / "road_context_extracted.csv"
BASE_EVENTS_PATH = RESULTS_DIR / "base_eventos_normalizada.csv"
MENTIONS_PATH = RESULTS_DIR / "base_menciones_expandida.csv"
ROAD_MATCHES_PATH = RESULTS_DIR / "road_text_matches.csv"
OSM_SEGMENTS_PATH = ROOT / "Data" / "Processed" / "osm_roads_san_salvador" / "osm_road_segments.csv"

NOMINATIM_ENDPOINT = "https://nominatim.openstreetmap.org/search"
NOMINATIM_CACHE_PATH = PROCESSED_DIR / "nominatim_cache.json"
GEOCODE_DELAY_SECONDS = float(os.environ.get("NOMINATIM_DELAY_SECONDS", "1.1"))
SKIP_REMOTE_GEOCODING = os.environ.get("SKIP_REMOTE_GEOCODING", "0") == "1"

# BBox AMSS usada para la red OSM descargada: sur, oeste, norte, este.
AMSS_BBOX = (13.55, -89.42, 13.92, -89.00)
EL_SALVADOR_BBOX = (13.0, -90.2, 14.6, -87.6)


def safe_float(value: Any) -> float | None:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return None
        return float(value)
    except Exception:
        return None


def nonempty(value: Any) -> bool:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    return bool(str(value).strip())


def bool_col(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series([False] * len(frame), index=frame.index)
    return frame[column].map(lambda value: bool(value) if not pd.isna(value) else False)


def in_bbox(lat: float | None, lon: float | None, bbox: tuple[float, float, float, float]) -> bool:
    if lat is None or lon is None:
        return False
    south, west, north, east = bbox
    return south <= lat <= north and west <= lon <= east


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_base_events() -> pd.DataFrame:
    if BASE_CONTEXT_PATH.exists():
        events = pd.read_csv(BASE_CONTEXT_PATH)
    else:
        events = pd.read_csv(BASE_EVENTS_PATH)

    for col in [
        "corridor_candidate",
        "road_context_level",
        "capital_analysis_eligible",
        "capital_scope",
        "capital_subarea",
    ]:
        if col not in events.columns:
            events[col] = ""

    events["event_id"] = events["uuid"]
    events["address_available"] = events["address"].map(nonempty)
    events["municipality_available"] = events["municipality"].map(nonempty)
    events["department_available"] = events["department"].map(nonempty)
    events["road_context_available"] = events["corridor_candidate"].map(nonempty)
    events["has_original_coordinates"] = events.apply(
        lambda row: in_bbox(safe_float(row.get("latitude")), safe_float(row.get("longitude")), EL_SALVADOR_BBOX),
        axis=1,
    )
    events["capital_analysis_eligible"] = events["capital_analysis_eligible"].fillna(False).astype(bool)
    return events


def build_geocode_queries(row: pd.Series) -> list[str]:
    address = str(row.get("address", "") or "").strip()
    municipality = str(row.get("municipality", "") or "").strip()
    department = str(row.get("department", "") or "").strip()
    corridor = str(row.get("corridor_candidate", "") or "").strip()

    queries: list[str] = []
    if address:
        parts = [address]
        if municipality and normalize_text(municipality) not in normalize_text(address):
            parts.append(municipality)
        if department and normalize_text(department) not in normalize_text(" ".join(parts)):
            parts.append(department)
        parts.append("El Salvador")
        queries.append(", ".join(parts))

    if corridor:
        parts = [corridor]
        if municipality:
            parts.append(municipality)
        if department:
            parts.append(department)
        parts.append("El Salvador")
        queries.append(", ".join(parts))

    if municipality and department:
        queries.append(f"{municipality}, {department}, El Salvador")
    elif municipality:
        queries.append(f"{municipality}, El Salvador")

    deduped = []
    seen = set()
    for query in queries:
        norm = normalize_text(query)
        if norm and norm not in seen:
            seen.add(norm)
            deduped.append(query)
    return deduped[:3]


def nominatim_search(query: str, cache: dict[str, Any]) -> list[dict[str, Any]]:
    key = normalize_text(query)
    if key in cache:
        return cache[key]
    if SKIP_REMOTE_GEOCODING:
        cache[key] = []
        return []

    params = {
        "q": query,
        "format": "jsonv2",
        "limit": 3,
        "addressdetails": 1,
        "extratags": 1,
        "countrycodes": "sv",
        "accept-language": "es",
    }
    url = NOMINATIM_ENDPOINT + "?" + parse.urlencode(params)
    req = request.Request(
        url,
        headers={
            "User-Agent": "devcodes-mobility-news-source-evaluation/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with request.urlopen(req, timeout=45) as response:
            payload = response.read().decode("utf-8")
        results = json.loads(payload)
        if not isinstance(results, list):
            results = []
    except Exception as exc:
        results = [{"_error": str(exc)}]

    cache[key] = results
    write_json(NOMINATIM_CACHE_PATH, cache)
    time.sleep(GEOCODE_DELAY_SECONDS)
    return results


def classify_geocode_result(result: dict[str, Any], row: pd.Series, query: str) -> dict[str, Any]:
    if not result or result.get("_error"):
        return {
            "geocode_status": "ERROR" if result and result.get("_error") else "NO_RESULT",
            "geocode_error": result.get("_error", "") if result else "",
        }

    lat = safe_float(result.get("lat"))
    lon = safe_float(result.get("lon"))
    if not in_bbox(lat, lon, EL_SALVADOR_BBOX):
        return {
            "geocode_status": "OUTSIDE_EL_SALVADOR_BBOX",
            "geocode_lat": lat,
            "geocode_lon": lon,
        }

    result_class = str(result.get("category") or result.get("class") or "")
    result_type = str(result.get("type") or "")
    addresstype = str(result.get("addresstype") or "")
    display = normalize_text(result.get("display_name", ""))
    corridor = normalize_text(row.get("corridor_candidate", ""))
    municipality = normalize_text(row.get("municipality", ""))
    department = normalize_text(row.get("department", ""))
    query_head = normalize_text(str(query).split(",")[0])

    road_like = {
        "road",
        "residential",
        "primary",
        "secondary",
        "tertiary",
        "trunk",
        "motorway",
        "unclassified",
        "route",
    }
    poi_like = {"school", "hospital", "fuel", "bus_station", "station", "marketplace", "commercial"}
    municipal_like = {"city", "town", "village", "municipality", "county", "state", "administrative"}

    if result_class == "highway" or result_type in road_like or addresstype in road_like:
        level = "ROAD_OR_CORRIDOR"
        confidence = 0.62
    elif result_type in poi_like or result_class in {"amenity", "shop", "building", "tourism"}:
        level = "POI_OR_LANDMARK"
        confidence = 0.58
    elif result_type in municipal_like or addresstype in municipal_like or result_class == "boundary":
        level = "MUNICIPALITY_OR_ADMIN"
        confidence = 0.35
    else:
        level = "PLACE_OR_AMBIGUOUS"
        confidence = 0.45

    corridor_match = bool(corridor and corridor in display)
    municipality_match = bool(municipality and municipality in display)
    department_match = bool(department and department in display)
    query_head_match = bool(query_head and len(query_head) >= 8 and query_head in display)

    if corridor_match:
        confidence += 0.18
    if municipality_match:
        confidence += 0.08
    if department_match:
        confidence += 0.05
    if query_head_match:
        confidence += 0.05

    importance = safe_float(result.get("importance")) or 0
    confidence += min(max(importance, 0), 1) * 0.08

    # Nominatim can return plausible but unrelated landmarks for vague road
    # strings. If the result does not agree with the road text or an
    # administrative hint from the event, keep it as geocoded but not usable
    # for road-level analysis.
    has_context_match = corridor_match or municipality_match or department_match or query_head_match
    if level in {"ROAD_OR_CORRIDOR", "POI_OR_LANDMARK", "PLACE_OR_AMBIGUOUS"} and not has_context_match:
        level = "AMBIGUOUS_LOW_CONTEXT_MATCH"
        confidence = min(confidence, 0.35)

    confidence = round(min(confidence, 0.95), 4)

    return {
        "geocode_status": "GEOCODED",
        "geocode_error": "",
        "geocode_query": query,
        "geocode_lat": lat,
        "geocode_lon": lon,
        "geocode_display_name": result.get("display_name", ""),
        "geocode_osm_type": result.get("osm_type", ""),
        "geocode_osm_id": result.get("osm_id", ""),
        "geocode_category": result_class,
        "geocode_type": result_type,
        "geocode_addresstype": addresstype,
        "geocode_level": level,
        "geocode_confidence": confidence,
        "geocode_usable_for_road_analysis": level in {"ROAD_OR_CORRIDOR", "POI_OR_LANDMARK"} and confidence >= 0.55,
    }


def geocode_events(events: pd.DataFrame) -> pd.DataFrame:
    cache = load_json(NOMINATIM_CACHE_PATH, {})
    rows = []

    for _, row in events.iterrows():
        lat = safe_float(row.get("latitude"))
        lon = safe_float(row.get("longitude"))
        if in_bbox(lat, lon, EL_SALVADOR_BBOX):
            confidence = safe_float(row.get("geo_confidence")) or 0.65
            rows.append(
                {
                    "event_id": row["event_id"],
                    "geocode_status": "ORIGINAL_COORDINATES",
                    "geocode_error": "",
                    "geocode_query": "",
                    "geocode_lat": lat,
                    "geocode_lon": lon,
                    "geocode_display_name": "Coordenadas originales del evento",
                    "geocode_osm_type": "",
                    "geocode_osm_id": "",
                    "geocode_category": "original",
                    "geocode_type": "original_coordinates",
                    "geocode_addresstype": "",
                    "geocode_level": "ORIGINAL_POINT",
                    "geocode_confidence": round(confidence, 4),
                    "geocode_usable_for_road_analysis": confidence >= 0.55,
                }
            )
            continue

        best: dict[str, Any] | None = None
        queries = build_geocode_queries(row)
        for query in queries:
            results = nominatim_search(query, cache)
            valid_results = [result for result in results if not result.get("_error")]
            if not valid_results:
                candidate = classify_geocode_result(results[0], row, query) if results else {"geocode_status": "NO_RESULT"}
            else:
                classified = [classify_geocode_result(result, row, query) for result in valid_results]
                classified = [item for item in classified if item.get("geocode_status") == "GEOCODED"]
                candidate = max(classified, key=lambda item: item.get("geocode_confidence", 0), default={"geocode_status": "NO_RESULT"})

            if best is None or candidate.get("geocode_confidence", 0) > best.get("geocode_confidence", 0):
                best = candidate
            if best and best.get("geocode_usable_for_road_analysis"):
                break

        if best is None:
            best = {
                "geocode_status": "NOT_ATTEMPTED_NO_LOCATION_TEXT",
                "geocode_error": "",
                "geocode_query": "",
                "geocode_lat": None,
                "geocode_lon": None,
                "geocode_display_name": "",
                "geocode_osm_type": "",
                "geocode_osm_id": "",
                "geocode_category": "",
                "geocode_type": "",
                "geocode_addresstype": "",
                "geocode_level": "NO_LOCATION_TEXT",
                "geocode_confidence": 0.0,
                "geocode_usable_for_road_analysis": False,
            }

        best["event_id"] = row["event_id"]
        rows.append(best)

    geocoded = pd.DataFrame(rows)
    merged = events.merge(geocoded, how="left", on="event_id")
    return merged


def project_point(lon: float, lat: float, lat0: float) -> tuple[float, float]:
    meters_per_degree_lat = 111_320.0
    meters_per_degree_lon = 111_320.0 * math.cos(math.radians(lat0))
    return lon * meters_per_degree_lon, lat * meters_per_degree_lat


def point_to_segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    qx = ax + t * dx
    qy = ay + t * dy
    return math.hypot(px - qx, py - qy)


def parse_segment_records(segments: pd.DataFrame) -> list[dict[str, Any]]:
    records = []
    for _, row in segments.iterrows():
        coords = json.loads(row["geometry_json"])
        if len(coords) < 2:
            continue
        lons = [float(point[0]) for point in coords]
        lats = [float(point[1]) for point in coords]
        records.append(
            {
                "osm_way_id": row["osm_way_id"],
                "name": row.get("name", ""),
                "ref": row.get("ref", ""),
                "highway": row.get("highway", ""),
                "oneway": row.get("oneway", ""),
                "lanes": row.get("lanes", ""),
                "maxspeed": row.get("maxspeed", ""),
                "surface": row.get("surface", ""),
                "road_key_norm": row.get("road_key_norm", ""),
                "road_type_category": row.get("road_type_category", ""),
                "length_m": row.get("length_m", 0),
                "coords": [(float(lon), float(lat)) for lon, lat in coords],
                "min_lon": min(lons),
                "max_lon": max(lons),
                "min_lat": min(lats),
                "max_lat": max(lats),
            }
        )
    return records


def nearest_segment(
    lon: float,
    lat: float,
    records: list[dict[str, Any]],
    road_key: str | None = None,
    search_degrees: float = 0.035,
) -> dict[str, Any] | None:
    if road_key:
        candidates = [record for record in records if normalize_text(record["road_key_norm"]) == normalize_text(road_key)]
    else:
        candidates = [
            record
            for record in records
            if record["min_lon"] - search_degrees <= lon <= record["max_lon"] + search_degrees
            and record["min_lat"] - search_degrees <= lat <= record["max_lat"] + search_degrees
        ]
    if not candidates:
        return None

    px, py = project_point(lon, lat, lat)
    best_record = None
    best_distance = float("inf")
    for record in candidates:
        projected = [project_point(coord_lon, coord_lat, lat) for coord_lon, coord_lat in record["coords"]]
        for (ax, ay), (bx, by) in zip(projected, projected[1:]):
            distance = point_to_segment_distance(px, py, ax, ay, bx, by)
            if distance < best_distance:
                best_distance = distance
                best_record = record

    if best_record is None:
        return None
    return {**best_record, "distance_m": round(best_distance, 2)}


def classify_spatial_match(row: pd.Series) -> str:
    text_status = str(row.get("text_match_status", ""))
    text_distance = safe_float(row.get("distance_to_text_corridor_m"))
    nearest_distance = safe_float(row.get("nearest_osm_distance_m"))
    usable_point = bool(row.get("geocode_usable_for_road_analysis", False))

    if not usable_point:
        if text_status == "TEXT_MATCH_ACCEPTED":
            return "TEXTUAL_CORRIDOR_ONLY"
        if "REVIEW" in text_status:
            return "TEXTUAL_CORRIDOR_REVIEW_ONLY"
        return "NO_SPATIAL_INPUT"

    if text_distance is not None and text_status == "TEXT_MATCH_ACCEPTED":
        if text_distance <= 75:
            return "SPATIAL_TEXT_HIGH"
        if text_distance <= 200:
            return "SPATIAL_TEXT_MEDIUM"
        if text_distance <= 500:
            return "SPATIAL_TEXT_LOW_REVIEW"
        return "TEXT_MATCH_DISTANCE_CONFLICT"

    if text_distance is not None and "REVIEW" in text_status:
        if text_distance <= 150:
            return "SPATIAL_TEXT_REVIEW_MEDIUM"
        if text_distance <= 500:
            return "SPATIAL_TEXT_REVIEW_LOW"
        return "TEXT_REVIEW_DISTANCE_CONFLICT"

    if nearest_distance is not None:
        if nearest_distance <= 50:
            return "SPATIAL_NEAREST_ONLY_REVIEW"
        if nearest_distance <= 200:
            return "SPATIAL_NEAREST_LOW_REVIEW"
    return "NO_ACCEPTABLE_ROAD_MATCH"


def match_events_to_osm(events: pd.DataFrame) -> pd.DataFrame:
    matches = pd.read_csv(ROAD_MATCHES_PATH) if ROAD_MATCHES_PATH.exists() else pd.DataFrame()
    if matches.empty:
        events["text_match_status"] = "NO_TEXT_MATCH_TABLE"
        return events

    text_match_cols = [
        "road_name_candidate",
        "matched_road_key_norm",
        "matched_osm_name",
        "matched_refs",
        "predominant_highway",
        "predominant_road_type",
        "segment_count",
        "length_km",
        "text_match_score",
        "text_match_method",
        "alternative_matches_ge_078",
        "match_status",
    ]
    event_matches = events.merge(
        matches[text_match_cols],
        how="left",
        left_on="corridor_candidate",
        right_on="road_name_candidate",
    )
    event_matches["text_match_status"] = event_matches["match_status"].fillna(
        event_matches["corridor_candidate"].map(lambda value: "NO_ROAD_CANDIDATE" if not nonempty(value) else "NO_CATALOG_MATCH")
    )

    if not OSM_SEGMENTS_PATH.exists():
        event_matches["spatial_match_status"] = "OSM_SEGMENTS_MISSING"
        return event_matches

    segments = pd.read_csv(OSM_SEGMENTS_PATH)
    records = parse_segment_records(segments)
    rows = []
    for _, row in event_matches.iterrows():
        lat = safe_float(row.get("geocode_lat"))
        lon = safe_float(row.get("geocode_lon"))
        output = {}
        if in_bbox(lat, lon, AMSS_BBOX):
            nearest = nearest_segment(lon, lat, records)
            if nearest:
                output.update(
                    {
                        "nearest_osm_way_id": nearest["osm_way_id"],
                        "nearest_osm_name": nearest["name"],
                        "nearest_osm_ref": nearest["ref"],
                        "nearest_osm_highway": nearest["highway"],
                        "nearest_osm_road_key_norm": nearest["road_key_norm"],
                        "nearest_osm_road_type": nearest["road_type_category"],
                        "nearest_osm_oneway": nearest["oneway"],
                        "nearest_osm_lanes": nearest["lanes"],
                        "nearest_osm_maxspeed": nearest["maxspeed"],
                        "nearest_osm_surface": nearest["surface"],
                        "nearest_osm_distance_m": nearest["distance_m"],
                    }
                )
            road_key = str(row.get("matched_road_key_norm", "") or "").strip()
            if road_key:
                text_nearest = nearest_segment(lon, lat, records, road_key=road_key)
                if text_nearest:
                    output.update(
                        {
                            "text_corridor_osm_way_id": text_nearest["osm_way_id"],
                            "text_corridor_osm_name": text_nearest["name"],
                            "text_corridor_osm_ref": text_nearest["ref"],
                            "text_corridor_highway": text_nearest["highway"],
                            "distance_to_text_corridor_m": text_nearest["distance_m"],
                        }
                    )
        else:
            output["road_network_scope_status"] = "OUTSIDE_AMSS_OSM_BBOX_OR_NO_POINT"
        rows.append(output)

    spatial = pd.DataFrame(rows)
    combined = pd.concat([event_matches.reset_index(drop=True), spatial.reset_index(drop=True)], axis=1)
    combined["spatial_match_status"] = combined.apply(classify_spatial_match, axis=1)
    return combined


def build_manual_validation_sample(events: pd.DataFrame, sample_size: int = 25) -> pd.DataFrame:
    events = events.copy()
    status_rank = {
        "SPATIAL_TEXT_HIGH": 1,
        "SPATIAL_TEXT_MEDIUM": 2,
        "TEXTUAL_CORRIDOR_ONLY": 3,
        "SPATIAL_TEXT_LOW_REVIEW": 4,
        "TEXT_MATCH_DISTANCE_CONFLICT": 5,
        "TEXTUAL_CORRIDOR_REVIEW_ONLY": 6,
        "NO_SPATIAL_INPUT": 7,
        "NO_ACCEPTABLE_ROAD_MATCH": 8,
    }
    events["validation_priority"] = events["spatial_match_status"].map(lambda s: status_rank.get(s, 9))
    events["severity_sort"] = events["severity_score"].fillna(0)
    events["mentions_sort"] = events["mentions"].fillna(0)

    buckets = []
    for status in [
        "SPATIAL_TEXT_HIGH",
        "SPATIAL_TEXT_MEDIUM",
        "TEXTUAL_CORRIDOR_ONLY",
        "TEXT_MATCH_DISTANCE_CONFLICT",
        "TEXTUAL_CORRIDOR_REVIEW_ONLY",
        "NO_SPATIAL_INPUT",
    ]:
        subset = events[events["spatial_match_status"] == status].sort_values(["severity_sort", "mentions_sort"], ascending=False)
        if not subset.empty:
            buckets.append(subset.head(4))
    sampled = pd.concat(buckets, ignore_index=True) if buckets else events.head(0)
    remaining = events[~events["event_id"].isin(sampled["event_id"])].sort_values(
        ["severity_sort", "mentions_sort"], ascending=False
    )
    sampled = pd.concat([sampled, remaining], ignore_index=True).drop_duplicates("event_id").head(sample_size)

    manual = sampled[
        [
            "event_id",
            "datetime",
            "incident",
            "severity_class",
            "severity_score",
            "injury_flag",
            "fatality_flag",
            "mentions",
            "address",
            "municipality",
            "department",
            "observation",
            "corridor_candidate",
            "geocode_status",
            "geocode_level",
            "geocode_confidence",
            "geocode_display_name",
            "text_match_status",
            "matched_osm_name",
            "nearest_osm_name",
            "nearest_osm_distance_m",
            "distance_to_text_corridor_m",
            "spatial_match_status",
        ]
    ].copy()
    for col in [
        "manual_event_is_vial",
        "manual_severity_correct",
        "manual_geocode_correct",
        "manual_road_match_correct",
        "manual_accept_for_metric",
        "manual_notes",
    ]:
        manual[col] = ""
    return manual


def diagnostic_row(metric: str, value: Any, interpretation: str, decision_use: str) -> dict[str, Any]:
    return {
        "metric": metric,
        "value": value,
        "interpretation": interpretation,
        "decision_use": decision_use,
    }


def build_bias_diagnostics(events: pd.DataFrame, mentions: pd.DataFrame | None) -> pd.DataFrame:
    total = len(events)
    rows = []
    rows.append(diagnostic_row("eventos_unicos", total, "Eventos deduplicados disponibles.", "Base de evaluacion"))
    rows.append(diagnostic_row("menciones_totales", int(events["mentions"].sum()), "Volumen de menciones asociadas a eventos.", "Robustez informativa"))
    rows.append(
        diagnostic_row(
            "eventos_con_multiples_menciones",
            int((events["mentions"].fillna(0) > 1).sum()),
            "Eventos reportados mas de una vez.",
            "Corroboracion preliminar",
        )
    )
    rows.append(
        diagnostic_row(
            "eventos_con_direccion_textual",
            int(events["address_available"].sum()),
            "Eventos con texto ubicable.",
            "Potencial de geocodificacion",
        )
    )
    rows.append(
        diagnostic_row(
            "eventos_con_coordenadas_originales",
            int(events["has_original_coordinates"].sum()),
            "Eventos con lat/lon desde la fuente.",
            "Analisis espacial directo",
        )
    )
    rows.append(
        diagnostic_row(
            "eventos_geocodificados_utiles_para_via",
            int(bool_col(events, "geocode_usable_for_road_analysis").sum()),
            "Eventos con punto suficientemente util para asociacion vial.",
            "Aptitud espacial",
        )
    )

    if "department_norm" in events.columns:
        known = events[events["department_norm"].fillna("SIN_DEPTO") != "SIN_DEPTO"]
        rows.append(
            diagnostic_row(
                "departamentos_con_eventos",
                int(known["department_norm"].nunique()),
                "Cobertura territorial departamental observable.",
                "Sesgo territorial",
            )
        )
        if not known.empty:
            top_dept = known["department_norm"].value_counts(normalize=True).iloc[0]
            rows.append(
                diagnostic_row(
                    "concentracion_departamento_principal_pct",
                    round(top_dept * 100, 2),
                    "Porcentaje de eventos concentrado en el departamento con mas registros.",
                    "Riesgo de sesgo territorial",
                )
            )

    if mentions is not None and "source" in mentions.columns and not mentions.empty:
        source_counts = mentions["source"].fillna("SIN_FUENTE").value_counts(normalize=True)
        rows.append(
            diagnostic_row(
                "fuentes_distintas_menciones",
                int(mentions["source"].fillna("SIN_FUENTE").nunique()),
                "Fuentes distintas observadas en las menciones.",
                "Diversidad informativa",
            )
        )
        rows.append(
            diagnostic_row(
                "concentracion_fuente_principal_pct",
                round(float(source_counts.iloc[0]) * 100, 2),
                "Peso de la fuente dominante sobre las menciones.",
                "Riesgo de sesgo por fuente",
            )
        )

    return pd.DataFrame(rows)


def source_diversity_score(events: pd.DataFrame, mentions: pd.DataFrame | None) -> float:
    if mentions is None or mentions.empty or "source" not in mentions.columns:
        source_penalty = 0.5
    else:
        top_share = mentions["source"].fillna("SIN_FUENTE").value_counts(normalize=True).iloc[0]
        source_penalty = max(0.0, 1 - float(top_share))

    if "department_norm" in events.columns:
        known = events[events["department_norm"].fillna("SIN_DEPTO") != "SIN_DEPTO"]
        dept_coverage = min(known["department_norm"].nunique() / 14, 1.0) if not known.empty else 0.0
        top_dept_share = known["department_norm"].value_counts(normalize=True).iloc[0] if not known.empty else 1.0
        dept_balance = max(0.0, 1 - float(top_dept_share))
    else:
        dept_coverage = 0.0
        dept_balance = 0.0
    return round(100 * (0.4 * dept_coverage + 0.3 * dept_balance + 0.3 * source_penalty), 2)


def compute_fitness_index(events: pd.DataFrame, mentions: pd.DataFrame | None) -> pd.DataFrame:
    total = len(events)
    capital_scope = events[bool_col(events, "capital_analysis_eligible")].copy()
    if capital_scope.empty:
        capital_scope = events.copy()

    classifiability = 100 * events["incident"].map(nonempty).mean()
    severity_identifiable = 100 * (events["severity_class"].fillna("") != "OTHER_LOW_INFORMATION").mean()
    address_rate = events["address_available"].mean()
    point_rate = bool_col(events, "geocode_usable_for_road_analysis").mean()
    road_context_rate = events["road_context_available"].mean()
    spatial_readiness = 100 * (0.35 * address_rate + 0.40 * point_rate + 0.25 * road_context_rate)

    text_accepted_or_review = capital_scope["text_match_status"].fillna("").isin(
        ["TEXT_MATCH_ACCEPTED", "TEXT_MATCH_REVIEW", "WEAK_TEXT_MATCH_REVIEW"]
    ).mean()
    spatial_accepted_or_review = capital_scope["spatial_match_status"].fillna("").isin(
        [
            "SPATIAL_TEXT_HIGH",
            "SPATIAL_TEXT_MEDIUM",
            "SPATIAL_TEXT_LOW_REVIEW",
            "SPATIAL_TEXT_REVIEW_MEDIUM",
            "SPATIAL_TEXT_REVIEW_LOW",
            "SPATIAL_NEAREST_ONLY_REVIEW",
            "TEXTUAL_CORRIDOR_ONLY",
            "TEXTUAL_CORRIDOR_REVIEW_ONLY",
        ]
    ).mean()
    road_association = 100 * (0.45 * text_accepted_or_review + 0.55 * spatial_accepted_or_review)

    reliability = 100 * (
        0.45 * events["evidence_score"].fillna(0).mean()
        + 0.30 * (events["mentions"].fillna(0) > 1).mean()
        + 0.25 * (events["source_diversity"].fillna(0) > 1).mean()
    )
    bias_control = source_diversity_score(events, mentions)
    validation_component = 0.0

    components = [
        ("clasificabilidad_evento", classifiability, 0.18, "Capacidad de identificar tipo de evento."),
        ("severidad_identificable", severity_identifiable, 0.18, "Capacidad de extraer gravedad preliminar."),
        ("preparacion_espacial", spatial_readiness, 0.20, "Disponibilidad de direccion, punto o contexto vial."),
        ("asociacion_vial_osm", road_association, 0.20, "Capacidad de conectar eventos con vias/corredores OSM."),
        ("confiabilidad_informativa", reliability, 0.14, "Menciones, fuentes y evidencia de corroboracion."),
        ("control_sesgo_cobertura", bias_control, 0.10, "Diversidad territorial y de fuentes."),
    ]

    observable = sum(score * weight for _, score, weight, _ in components)
    decision = observable * 0.85 + validation_component * 0.15

    rows = [
        {
            "component": name,
            "score_0_100": round(score, 2),
            "weight": weight,
            "weighted_score": round(score * weight, 2),
            "interpretation": interpretation,
        }
        for name, score, weight, interpretation in components
    ]
    rows.append(
        {
            "component": "indice_aptitud_observable_0_100",
            "score_0_100": round(observable, 2),
            "weight": 1.0,
            "weighted_score": round(observable, 2),
            "interpretation": "Puntaje observable sin validacion manual externa.",
        }
    )
    rows.append(
        {
            "component": "indice_decision_condicionada_0_100",
            "score_0_100": round(decision, 2),
            "weight": 1.0,
            "weighted_score": round(decision, 2),
            "interpretation": "Puntaje con penalizacion por validacion manual pendiente.",
        }
    )
    rows.append(
        {
            "component": "validacion_manual_completada",
            "score_0_100": validation_component,
            "weight": 0.15,
            "weighted_score": 0,
            "interpretation": "La muestra queda preparada, pero no puede autocompletarse sin revision humana.",
        }
    )
    return pd.DataFrame(rows)


def decision_from_index(index: pd.DataFrame) -> tuple[str, str]:
    observable = float(index.loc[index["component"] == "indice_aptitud_observable_0_100", "score_0_100"].iloc[0])
    conditioned = float(index.loc[index["component"] == "indice_decision_condicionada_0_100", "score_0_100"].iloc[0])
    road = float(index.loc[index["component"] == "asociacion_vial_osm", "score_0_100"].iloc[0])
    spatial = float(index.loc[index["component"] == "preparacion_espacial", "score_0_100"].iloc[0])

    if observable >= 70 and road >= 55 and spatial >= 45:
        return (
            "ADOPTAR_CON_RESTRICCIONES",
            "La fuente tiene valor suficiente como senal auxiliar, pero requiere validacion manual y reglas de confianza antes de integrarse operacionalmente.",
        )
    if conditioned >= 61:
        return (
            "ADOPTAR_CON_RESTRICCIONES",
            "La fuente es util como metrica auxiliar exploratoria, no como indicador oficial ni KPI final.",
        )
    if observable >= 45:
        return (
            "USAR_SOLO_EXPLORATORIAMENTE",
            "La fuente aporta senal, pero la aptitud espacial/vial todavia es limitada para decisiones operativas.",
        )
    return (
        "NO_ADOPTAR_TODAVIA",
        "La fuente no alcanza suficiente aptitud observable para entrar al sistema de metricas.",
    )


def plot_fitness_components(index: pd.DataFrame) -> None:
    components = index[~index["component"].str.startswith("indice_") & (index["component"] != "validacion_manual_completada")]
    fig, ax = plt.subplots(figsize=(10, 5), dpi=180)
    colors = ["#3fb8ff", "#76d275", "#ffcf5a", "#ff7b72", "#a78bfa", "#9ca3af"]
    ax.barh(components["component"], components["score_0_100"], color=colors[: len(components)])
    ax.set_xlim(0, 100)
    ax.set_xlabel("Puntaje 0-100")
    ax.set_title("Componentes del indice de aptitud de la fuente")
    ax.grid(axis="x", alpha=0.2)
    for idx, value in enumerate(components["score_0_100"]):
        ax.text(value + 1, idx, f"{value:.1f}", va="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(EVAL_DIR / "indice_aptitud_componentes.png", bbox_inches="tight")
    plt.close(fig)


def plot_evaluation_funnel(events: pd.DataFrame) -> None:
    values = {
        "Eventos": len(events),
        "Direccion": int(events["address_available"].sum()),
        "Contexto vial": int(events["road_context_available"].sum()),
        "Geocod. util": int(bool_col(events, "geocode_usable_for_road_analysis").sum()),
        "Match OSM": int(
            events["spatial_match_status"].fillna("").isin(
                [
                    "SPATIAL_TEXT_HIGH",
                    "SPATIAL_TEXT_MEDIUM",
                    "SPATIAL_TEXT_LOW_REVIEW",
                    "SPATIAL_TEXT_REVIEW_MEDIUM",
                    "SPATIAL_TEXT_REVIEW_LOW",
                    "SPATIAL_NEAREST_ONLY_REVIEW",
                    "TEXTUAL_CORRIDOR_ONLY",
                    "TEXTUAL_CORRIDOR_REVIEW_ONLY",
                ]
            ).sum()
        ),
    }
    fig, ax = plt.subplots(figsize=(9, 4.8), dpi=180)
    ax.plot(list(values.keys()), list(values.values()), marker="o", color="#3fb8ff", linewidth=2.5)
    ax.fill_between(list(values.keys()), list(values.values()), color="#3fb8ff", alpha=0.12)
    ax.set_ylim(0, max(values.values()) * 1.15)
    ax.set_title("Embudo de aprovechabilidad de noticias")
    ax.set_ylabel("Eventos")
    ax.grid(axis="y", alpha=0.2)
    for idx, value in enumerate(values.values()):
        ax.text(idx, value + 2, str(value), ha="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(EVAL_DIR / "embudo_aprovechabilidad_noticias.png", bbox_inches="tight")
    plt.close(fig)


def write_text_summary(events: pd.DataFrame, index: pd.DataFrame, diagnostics: pd.DataFrame, decision: tuple[str, str]) -> None:
    decision_code, decision_text = decision
    total = len(events)
    capital = int(bool_col(events, "capital_analysis_eligible").sum())
    usable_geo = int(bool_col(events, "geocode_usable_for_road_analysis").sum())
    text_matches = int(events["text_match_status"].fillna("").isin(["TEXT_MATCH_ACCEPTED", "TEXT_MATCH_REVIEW", "WEAK_TEXT_MATCH_REVIEW"]).sum())
    spatial_or_text = int(
        events["spatial_match_status"].fillna("").isin(
            [
                "SPATIAL_TEXT_HIGH",
                "SPATIAL_TEXT_MEDIUM",
                "SPATIAL_TEXT_LOW_REVIEW",
                "SPATIAL_TEXT_REVIEW_MEDIUM",
                "SPATIAL_TEXT_REVIEW_LOW",
                "SPATIAL_NEAREST_ONLY_REVIEW",
                "TEXTUAL_CORRIDOR_ONLY",
                "TEXTUAL_CORRIDOR_REVIEW_ONLY",
            ]
        ).sum()
    )
    observable = index.loc[index["component"] == "indice_aptitud_observable_0_100", "score_0_100"].iloc[0]
    conditioned = index.loc[index["component"] == "indice_decision_condicionada_0_100", "score_0_100"].iloc[0]

    status_counts = events["spatial_match_status"].value_counts().reset_index()
    status_counts.columns = ["spatial_match_status", "events"]
    geo_counts = events["geocode_level"].fillna("SIN_GEOCODIFICAR").value_counts().reset_index()
    geo_counts.columns = ["geocode_level", "events"]

    lines = [
        "EVALUACION DE APTITUD DE NOTICIAS VIALES",
        "=" * 44,
        "",
        "1. Decision ejecutiva",
        "-" * 21,
        f"Decision: {decision_code}",
        decision_text,
        "",
        f"Indice observable de aptitud: {observable}/100",
        f"Indice condicionado por validacion pendiente: {conditioned}/100",
        "",
        "2. Resultados principales",
        "-" * 25,
        f"Eventos evaluados: {total}",
        f"Eventos en alcance capital/AMSS: {capital}",
        f"Eventos con direccion textual: {int(events['address_available'].sum())} ({pct(events['address_available'].sum(), total)}%)",
        f"Eventos con contexto vial textual: {int(events['road_context_available'].sum())} ({pct(events['road_context_available'].sum(), total)}%)",
        f"Eventos geocodificados utiles para analisis vial: {usable_geo} ({pct(usable_geo, total)}%)",
        f"Eventos con match textual OSM aceptado/revision: {text_matches} ({pct(text_matches, total)}%)",
        f"Eventos con asociacion vial aprovechable o revisable: {spatial_or_text} ({pct(spatial_or_text, total)}%)",
        "",
        "3. Distribucion de geocodificacion",
        "-" * 33,
        markdown_table(geo_counts, max_col_width=120),
        "",
        "4. Distribucion de asociacion vial",
        "-" * 34,
        markdown_table(status_counts, max_col_width=120),
        "",
        "5. Componentes de aptitud",
        "-" * 25,
        markdown_table(index, max_col_width=130),
        "",
        "6. Diagnostico de sesgos y cobertura",
        "-" * 37,
        markdown_table(diagnostics, max_col_width=140),
        "",
        "7. Conclusion",
        "-" * 13,
        "La fuente de noticias aporta senal util para clasificacion, severidad preliminar, recurrencia territorial y menciones de corredores.",
        "Sin embargo, la decision de integrarla debe hacerse con restricciones porque la validacion manual aun no esta completada y la geocodificacion no convierte todos los casos en puntos viales confiables.",
        "La recomendacion es incorporarla como fuente auxiliar exploratoria/alerta temprana, no como KPI final ni como sustituto de estadistica oficial.",
        "",
    ]
    (EVAL_DIR / "resumen_aptitud_fuente_noticias.txt").write_text("\n".join(lines), encoding="utf-8")


def write_executive_report(events: pd.DataFrame, index: pd.DataFrame, decision: tuple[str, str]) -> None:
    decision_code, decision_text = decision
    observable = index.loc[index["component"] == "indice_aptitud_observable_0_100", "score_0_100"].iloc[0]
    conditioned = index.loc[index["component"] == "indice_decision_condicionada_0_100", "score_0_100"].iloc[0]

    report = f"""# Resumen ejecutivo - Aptitud de noticias para metricas de movilidad

## Decision

**{decision_code}.** {decision_text}

La prueba no construye el KPI final de movilidad. Evalua si las noticias merecen entrar como fuente auxiliar al sistema de metricas.

## Puntajes

- Indice observable de aptitud: **{observable}/100**
- Indice condicionado por validacion manual pendiente: **{conditioned}/100**

## Evidencia principal

- Eventos evaluados: **{len(events)}**
- Eventos con direccion textual: **{int(events['address_available'].sum())}**
- Eventos con contexto vial textual: **{int(events['road_context_available'].sum())}**
- Eventos geocodificados utiles para analisis vial: **{int(bool_col(events, 'geocode_usable_for_road_analysis').sum())}**
- Eventos con alcance capital/AMSS: **{int(bool_col(events, 'capital_analysis_eligible').sum())}**
- Eventos con asociacion vial aprovechable o revisable: **{int(events['spatial_match_status'].fillna('').isin(['SPATIAL_TEXT_HIGH','SPATIAL_TEXT_MEDIUM','SPATIAL_TEXT_LOW_REVIEW','SPATIAL_TEXT_REVIEW_MEDIUM','SPATIAL_TEXT_REVIEW_LOW','SPATIAL_NEAREST_ONLY_REVIEW','TEXTUAL_CORRIDOR_ONLY','TEXTUAL_CORRIDOR_REVIEW_ONLY']).sum())}**

## Figuras sugeridas

**Figura 1. Embudo de aprovechabilidad de noticias**  
Insertar: `Results/News/Evaluation/embudo_aprovechabilidad_noticias.png`

**Figura 2. Componentes del indice de aptitud**  
Insertar: `Results/News/Evaluation/indice_aptitud_componentes.png`

**Figura 3. Base vial OSM AMSS**  
Insertar: `Results/News/osm_base_vial_amss_dark.png`

**Figura 4. Base vial OSM + corredores mencionados en noticias**  
Insertar: `Results/News/osm_base_vial_amss_dark_highlight_news.png`

## Lectura ejecutiva

Las noticias son utiles como senal complementaria porque permiten extraer tipo de evento, severidad preliminar, menciones, fuentes, territorialidad y vias mencionadas. La fuente no debe interpretarse como siniestralidad real total, sino como presion vial reportada/noticiosa.

El mayor valor aparece en tres usos:

1. Monitoreo exploratorio de eventos viales reportados.
2. Identificacion de corredores y zonas recurrentemente mencionadas.
3. Priorizacion preliminar para revision o cruce con fuentes oficiales.

## Condiciones para integrarla al sistema

- Mantener separada esta fuente de estadisticas oficiales.
- Usarla como metrica auxiliar, no como KPI final.
- Exigir geocodificacion y match vial con nivel de confianza.
- Completar validacion manual de la muestra preparada.
- Documentar sesgos por fuente, municipio y cobertura mediatica.

## Recomendacion

Incorporar la fuente en modo **exploratorio/controlado**. La fuente merece seguir en el sistema de metricas como insumo auxiliar, pero todavia no debe alimentar automaticamente un KPI de movilidad hasta completar validacion manual y reglas de aceptacion espacial.
"""
    (EVAL_DIR / "resumen_ejecutivo_aptitud_noticias.md").write_text(report, encoding="utf-8")


def write_manual_validation_instructions() -> None:
    instructions = """VALIDACION MANUAL DE MUESTRA
============================

Archivo a revisar:
Results/News/Evaluation/validacion_manual_muestra.csv

Objetivo:
Medir si la fuente de noticias y el pipeline automatico clasifican correctamente eventos, severidad, geocodificacion y asociacion vial.

Campos a completar:
- manual_event_is_vial: SI / NO / DUDOSO
- manual_severity_correct: SI / NO / DUDOSO
- manual_geocode_correct: SI / NO / DUDOSO
- manual_road_match_correct: SI / NO / DUDOSO
- manual_accept_for_metric: SI / NO / CON_RESTRICCIONES
- manual_notes: explicacion breve

Criterio:
- SI: el resultado automatico es aceptable para analisis.
- DUDOSO: requiere fuente adicional o revision en mapa.
- NO: no debe usarse sin correccion.

La decision final de adopcion operacional no debe cerrarse como ADOPTAR plenamente hasta completar esta validacion.
"""
    (EVAL_DIR / "validacion_manual_instrucciones.txt").write_text(instructions, encoding="utf-8")


def main() -> None:
    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    events = load_base_events()
    mentions = pd.read_csv(MENTIONS_PATH) if MENTIONS_PATH.exists() else None

    evaluation_base = events.copy()
    evaluation_base.to_csv(EVAL_DIR / "base_fuente_noticias_evaluacion.csv", index=False)

    geocoded = geocode_events(events)
    geocoded.to_csv(EVAL_DIR / "eventos_geocodificados.csv", index=False)

    matched = match_events_to_osm(geocoded)
    matched.to_csv(EVAL_DIR / "eventos_matched_osm.csv", index=False)

    manual = build_manual_validation_sample(matched)
    manual.to_csv(EVAL_DIR / "validacion_manual_muestra.csv", index=False)
    write_manual_validation_instructions()

    diagnostics = build_bias_diagnostics(matched, mentions)
    diagnostics.to_csv(EVAL_DIR / "diagnostico_sesgos_fuente.csv", index=False)

    index = compute_fitness_index(matched, mentions)
    index.to_csv(EVAL_DIR / "indice_aptitud_fuente_noticias.csv", index=False)

    decision = decision_from_index(index)
    plot_fitness_components(index)
    plot_evaluation_funnel(matched)
    write_text_summary(matched, index, diagnostics, decision)
    write_executive_report(matched, index, decision)

    print(f"Decision: {decision[0]}")
    print(decision[1])
    print(f"Resultados: {EVAL_DIR}")


if __name__ == "__main__":
    main()
