#!/usr/bin/env python3
"""
Investiga eventos con coordenada valida, sin name/ref OSM cercano y sin texto vial suficiente.

La hipotesis es que algunos casos se pueden recuperar buscando el segmento OSM
nombrado mas cercano dentro de un radio prudente, porque el segmento mas
cercano puede ser una via sin name/ref.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "Results" / "News" / "Incidentes"
EVENTS_PATH = RESULTS_DIR / "eventos_incidentes_osm_nacional_enriched.csv"
OSM_DEPARTMENTS_DIR = ROOT / "Data" / "Processed" / "osm_roads_departments"
OSM_NATIONAL_SEGMENTS = ROOT / "Data" / "Processed" / "osm_roads_nacional" / "osm_road_segments.csv"

DETAIL_PATH = RESULTS_DIR / "investigacion_osm_sin_nombre_ref_detalle.csv"
CANDIDATES_PATH = RESULTS_DIR / "investigacion_osm_sin_nombre_ref_candidatos.csv"
REPORT_PATH = RESULTS_DIR / "investigacion_osm_sin_nombre_ref.txt"


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


ROAD_CONTEXT_PATTERNS = {
    "direccion_general": re.compile(r"\b(sentido|subiendo|bajando|conduce|conecta|hacia)\b", re.I),
    "referencia_lugar": re.compile(r"\b(frente|altura|cerca|zona|centro|caserio|caserío|desvio|desvío|restaurante|colegio|vidri|walmart|motel)\b", re.I),
    "infraestructura": re.compile(r"\b(carretera|calle|avenida|bypass|by ?pass|via|vía|puente|km|kil[oó]metro)\b", re.I),
}


def nonempty(value: Any) -> bool:
    text = str(value if value is not None else "").strip()
    return bool(text) and text.lower() != "nan"


def slugify_department(value: Any) -> str:
    return DEPARTMENT_SLUGS.get(str(value).strip().upper(), "")


def department_segments_path(department: Any) -> Path | None:
    slug = slugify_department(department)
    if not slug:
        return None
    path = OSM_DEPARTMENTS_DIR / slug / "osm_road_segments.csv"
    return path if path.exists() else None


def point_segment_distance_m(lon: float, lat: float, lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    lat0 = math.radians(lat)
    mx = 111_320.0 * math.cos(lat0)
    my = 110_574.0
    px, py = lon * mx, lat * my
    ax, ay = lon1 * mx, lat1 * my
    bx, by = lon2 * mx, lat2 * my
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def point_polyline_distance_m(lon: float, lat: float, coords: list[list[float]]) -> float:
    if len(coords) == 1:
        return point_segment_distance_m(lon, lat, coords[0][0], coords[0][1], coords[0][0], coords[0][1])
    best = float("inf")
    for a, b in zip(coords, coords[1:]):
        try:
            dist = point_segment_distance_m(lon, lat, float(a[0]), float(a[1]), float(b[0]), float(b[1]))
        except Exception:
            continue
        if dist < best:
            best = dist
    return best


def load_named_segments(path: Path) -> pd.DataFrame:
    cols = [
        "source_department",
        "source_department_slug",
        "osm_way_id",
        "name",
        "ref",
        "alt_name",
        "official_name",
        "highway",
        "road_type_category",
        "length_m",
        "geometry_json",
    ]
    df = pd.read_csv(path, usecols=lambda col: col in cols, low_memory=False)
    for col in ["name", "ref", "alt_name", "official_name"]:
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("").astype(str)
    mask = df[["name", "ref", "alt_name", "official_name"]].apply(lambda s: s.str.strip().ne("") & s.str.lower().ne("nan")).any(axis=1)
    return df[mask].copy()


def bbox_prefilter(df: pd.DataFrame, lon: float, lat: float, radius_m: float = 700.0) -> pd.DataFrame:
    # Conservative degree buffer around El Salvador latitudes.
    lat_buffer = radius_m / 110_574.0
    lon_buffer = radius_m / (111_320.0 * max(math.cos(math.radians(lat)), 0.2))
    # Cheap text filter over geometry JSON avoids parsing the whole department in most cases.
    # If geometry strings are unavailable or unusual, fall back to full df.
    return df


def nearest_named_candidates(df: pd.DataFrame, lon: float, lat: float, limit: int = 5) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for _, row in bbox_prefilter(df, lon, lat).iterrows():
        try:
            coords = json.loads(row["geometry_json"])
        except Exception:
            continue
        if not coords:
            continue
        dist = point_polyline_distance_m(lon, lat, coords)
        if dist <= 750:
            candidates.append(
                {
                    "candidate_osm_way_id": row.get("osm_way_id"),
                    "candidate_name": row.get("name", ""),
                    "candidate_ref": row.get("ref", ""),
                    "candidate_alt_name": row.get("alt_name", ""),
                    "candidate_official_name": row.get("official_name", ""),
                    "candidate_highway": row.get("highway", ""),
                    "candidate_road_type": row.get("road_type_category", ""),
                    "candidate_length_m": row.get("length_m", ""),
                    "candidate_distance_m": round(float(dist), 2),
                    "candidate_source_department": row.get("source_department", ""),
                    "candidate_source_department_slug": row.get("source_department_slug", ""),
                }
            )
    return sorted(candidates, key=lambda item: item["candidate_distance_m"])[:limit]


def classify_distance(distance: float | None) -> str:
    if distance is None or math.isnan(distance):
        return "NO_NAMED_SEGMENT_WITHIN_750M"
    if distance <= 50:
        return "RECUPERABLE_NAMED_SEGMENT_<=50M"
    if distance <= 150:
        return "RECUPERABLE_NAMED_SEGMENT_<=150M"
    if distance <= 300:
        return "POTENCIAL_NAMED_SEGMENT_<=300M"
    if distance <= 500:
        return "BAJA_CONFIANZA_NAMED_SEGMENT_<=500M"
    if distance <= 750:
        return "MUY_BAJA_CONFIANZA_NAMED_SEGMENT_<=750M"
    return "NO_NAMED_SEGMENT_WITHIN_750M"


def text_clues(row: pd.Series) -> str:
    text = " ".join(str(row.get(col) or "") for col in ["address", "observation"])
    labels = [label for label, pattern in ROAD_CONTEXT_PATTERNS.items() if pattern.search(text)]
    return ";".join(labels) if labels else "SIN_PISTA_VIAL_TEXTUAL"


def investigation_note(row: pd.Series, candidate: dict[str, Any] | None) -> str:
    if not candidate:
        return "No se encontro via OSM nombrada dentro de 750 m. Mantener como territorial o revisar geocodificacion."
    distance = float(candidate["candidate_distance_m"])
    if distance <= 50:
        return "Existe via OSM nombrada muy cercana. Candidato fuerte para nearest_named_osm."
    if distance <= 150:
        return "Existe via OSM nombrada cercana. Candidato razonable, revisar texto/territorio."
    if distance <= 300:
        return "Existe via OSM nombrada en radio medio. Usar solo con baja confianza o validacion."
    return "Via OSM nombrada lejana. No asignar automaticamente sin revision."


def main() -> None:
    events = pd.read_csv(EVENTS_PATH)
    for col in [
        "corridor_norm",
        "nearest_osm_name",
        "nearest_osm_ref",
        "address",
        "observation",
        "department_norm",
        "municipality_norm",
    ]:
        events[col] = events[col].fillna("").astype(str)

    target = events[
        (events["text_osm_resolution"] == "UNRESOLVED")
        & events["corridor_norm"].str.strip().eq("")
        & events["coordinate_quality_status"].isin(["VALID_POINT", "VALID_POINT_REPEATED_COORDINATE"])
        & events["nearest_osm_name"].str.strip().eq("")
        & events["nearest_osm_ref"].str.strip().eq("")
    ].copy()

    cache: dict[Path, pd.DataFrame] = {}
    detail_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []

    for _, row in target.iterrows():
        lon = pd.to_numeric(row.get("longitude_num"), errors="coerce")
        lat = pd.to_numeric(row.get("latitude_num"), errors="coerce")
        source_path = department_segments_path(row.get("department_norm")) or OSM_NATIONAL_SEGMENTS
        if source_path not in cache:
            cache[source_path] = load_named_segments(source_path)

        candidates = nearest_named_candidates(cache[source_path], float(lon), float(lat), limit=5)
        best = candidates[0] if candidates else None
        best_distance = float(best["candidate_distance_m"]) if best else None
        status = classify_distance(best_distance)
        clues = text_clues(row)

        base = {
            "ticketNumber": row.get("ticketNumber"),
            "datetime": row.get("datetime"),
            "department_norm": row.get("department_norm"),
            "municipality_norm": row.get("municipality_norm"),
            "latitude_num": row.get("latitude_num"),
            "longitude_num": row.get("longitude_num"),
            "address": row.get("address"),
            "observation": row.get("observation"),
            "mentions": row.get("mentions"),
            "impact_social_score": row.get("impact_social_score"),
            "severity_class": row.get("severity_class"),
            "fatality_flag": row.get("fatality_flag"),
            "injury_flag": row.get("injury_flag"),
            "coordinate_quality_status": row.get("coordinate_quality_status"),
            "osm_match_status": row.get("osm_match_status"),
            "nearest_unnamed_osm_distance_m": row.get("nearest_osm_distance_m"),
            "osm_source_path_used": str(source_path),
            "text_clues": clues,
            "nearest_named_status": status,
            "investigation_note": investigation_note(row, best),
        }
        if best:
            base.update(best)
        detail_rows.append(base)

        for rank, candidate in enumerate(candidates, start=1):
            candidate_rows.append(
                {
                    "ticketNumber": row.get("ticketNumber"),
                    "candidate_rank": rank,
                    **candidate,
                }
            )

    detail = pd.DataFrame(detail_rows)
    candidates_df = pd.DataFrame(candidate_rows)
    detail.to_csv(DETAIL_PATH, index=False)
    candidates_df.to_csv(CANDIDATES_PATH, index=False)

    status_counts = detail["nearest_named_status"].value_counts().reset_index() if not detail.empty else pd.DataFrame()
    text_counts = detail["text_clues"].value_counts().reset_index() if not detail.empty else pd.DataFrame()

    lines = [
        "Investigacion de casos con OSM sin name/ref y sin corridor_norm",
        "===============================================================",
        "",
        f"Casos investigados: {len(detail)}",
        "",
        "Estos casos son eventos con coordenada valida, `corridor_norm` vacio, `text_osm_resolution = UNRESOLVED`, y segmento OSM inmediato sin `name` ni `ref`.",
        "",
        "1. Resultado de busqueda nearest named OSM",
        "-----------------------------------------",
        status_counts.to_string(index=False) if not status_counts.empty else "(sin datos)",
        "",
        "2. Pistas textuales detectadas",
        "------------------------------",
        text_counts.to_string(index=False) if not text_counts.empty else "(sin datos)",
        "",
        "3. Casos con candidato OSM nombrado mas cercano",
        "-----------------------------------------------",
        detail[
            [
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
                "severity_class",
                "impact_social_score",
            ]
        ].sort_values(["candidate_distance_m", "impact_social_score"], ascending=[True, False]).head(25).fillna("").to_string(index=False)
        if not detail.empty
        else "(sin datos)",
        "",
        "4. Lectura metodologica",
        "-----------------------",
        "Si existe una via nombrada dentro de 50 m, se puede considerar recuperable automaticamente con confianza media/alta.",
        "Entre 50 y 150 m puede ser recuperable, pero conviene revisar coherencia territorial y texto.",
        "Entre 150 y 300 m debe quedar como baja confianza o revision.",
        "Mas alla de 300 m no deberia asignarse corredor automaticamente.",
        "",
        "5. Recomendacion",
        "----------------",
        "Implementar una segunda busqueda `nearest_named_osm_segment` en el pipeline. Esta busqueda no reemplaza al segmento OSM mas cercano; lo complementa cuando el segmento inmediato no tiene `name` ni `ref`.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")

    print(REPORT_PATH)
    print(DETAIL_PATH)
    print(CANDIDATES_PATH)


if __name__ == "__main__":
    main()
