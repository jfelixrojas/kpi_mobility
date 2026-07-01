#!/usr/bin/env python3
"""
Descarga y consolida red vial OSM por departamentos de El Salvador.

La salida departamental evita cargar una red nacional completa en el dashboard.
La salida nacional consolidada sirve para analisis y fallback de map matching.
"""

from __future__ import annotations

import json
import math
import os
import re
import time
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any
from urllib import parse, request

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEPARTMENTS_DIR = ROOT / "Data" / "Processed" / "osm_roads_departments"
NATIONAL_DIR = ROOT / "Data" / "Processed" / "osm_roads_nacional"
OVERPASS_ENDPOINT = os.environ.get("OVERPASS_ENDPOINT", "https://overpass-api.de/api/interpreter")
REFRESH = os.environ.get("OSM_REFRESH", "0") == "1"

HIGHWAY_VALUES = [
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

EARTH_RADIUS_M = 6_371_000

DEPARTMENTS = [
    {"slug": "ahuachapan", "name": "AHUACHAPAN", "iso": "SV-AH", "bbox": (13.64, -90.14, 14.08, -89.65)},
    {"slug": "cabanas", "name": "CABAÑAS", "iso": "SV-CA", "bbox": (13.78, -88.98, 14.15, -88.48)},
    {"slug": "chalatenango", "name": "CHALATENANGO", "iso": "SV-CH", "bbox": (13.93, -89.45, 14.45, -88.70)},
    {"slug": "cuscatlan", "name": "CUSCATLÁN", "iso": "SV-CU", "bbox": (13.62, -89.15, 14.03, -88.78)},
    {"slug": "la_libertad", "name": "LA LIBERTAD", "iso": "SV-LI", "bbox": (13.42, -89.78, 14.06, -89.08)},
    {"slug": "la_paz", "name": "LA PAZ", "iso": "SV-PA", "bbox": (13.15, -89.14, 13.72, -88.70)},
    {"slug": "la_union", "name": "LA UNION", "iso": "SV-UN", "bbox": (13.15, -87.98, 13.80, -87.60)},
    {"slug": "morazan", "name": "MORAZÁN", "iso": "SV-MO", "bbox": (13.50, -88.35, 13.95, -87.70)},
    {"slug": "san_miguel", "name": "SAN MIGUEL", "iso": "SV-SM", "bbox": (13.12, -88.45, 13.82, -87.75)},
    {"slug": "san_salvador", "name": "SAN SALVADOR", "iso": "SV-SS", "bbox": (13.55, -89.42, 13.92, -89.00)},
    {"slug": "san_vicente", "name": "SAN VICENTE", "iso": "SV-SV", "bbox": (13.35, -88.95, 13.88, -88.45)},
    {"slug": "santa_ana", "name": "SANTA ANA", "iso": "SV-SA", "bbox": (13.75, -89.92, 14.46, -89.20)},
    {"slug": "sonsonate", "name": "SONSONATE", "iso": "SV-SO", "bbox": (13.49, -89.96, 13.93, -89.45)},
    {"slug": "usulutan", "name": "USULUTÁN", "iso": "SV-US", "bbox": (13.15, -88.75, 13.65, -88.05)},
]


def normalize_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).lower()
    text = "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )
    text = text.replace("º", "").replace("ª", "")
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def road_type_category(highway: str) -> str:
    value = normalize_text(highway)
    if value in {"motorway", "trunk", "motorway link", "trunk link"}:
        return "NACIONAL_ESTRUCTURANTE"
    if value in {"primary", "primary link"}:
        return "ARTERIAL_PRINCIPAL"
    if value in {"secondary", "secondary link"}:
        return "ARTERIAL_SECUNDARIA"
    if value in {"tertiary", "tertiary link"}:
        return "COLECTORA"
    if value in {"residential", "living street"}:
        return "LOCAL_RESIDENCIAL"
    if value == "service":
        return "SERVICIO_ACCESO"
    if value == "unclassified":
        return "NO_CLASIFICADA_OSM"
    return "OTRA"


def haversine_m(a_lon: float, a_lat: float, b_lon: float, b_lat: float) -> float:
    phi1 = math.radians(a_lat)
    phi2 = math.radians(b_lat)
    dphi = math.radians(b_lat - a_lat)
    dlambda = math.radians(b_lon - a_lon)
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def line_length_m(coords: list[tuple[float, float]]) -> float:
    return sum(haversine_m(a_lon, a_lat, b_lon, b_lat) for (a_lon, a_lat), (b_lon, b_lat) in zip(coords, coords[1:]))


def build_area_query(iso_code: str) -> str:
    highway_regex = "^(" + "|".join(HIGHWAY_VALUES) + ")$"
    return f"""
[out:json][timeout:180];
area["ISO3166-2"="{iso_code}"]->.searchArea;
(
  way(area.searchArea)["highway"~"{highway_regex}"];
);
out tags geom;
"""


def build_bbox_query(bbox: tuple[float, float, float, float]) -> str:
    south, west, north, east = bbox
    highway_regex = "^(" + "|".join(HIGHWAY_VALUES) + ")$"
    return f"""
[out:json][timeout:180];
(
  way["highway"~"{highway_regex}"]({south},{west},{north},{east});
);
out tags geom;
"""


def post_overpass(query: str) -> dict[str, Any]:
    data = parse.urlencode({"data": query}).encode("utf-8")
    req = request.Request(
        OVERPASS_ENDPOINT,
        data=data,
        headers={
            "User-Agent": "devcodes-mobility-poc/1.0",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        },
        method="POST",
    )
    last_error = None
    for attempt in range(3):
        try:
            with request.urlopen(req, timeout=240) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            time.sleep(4 + attempt * 4)
    raise RuntimeError(str(last_error))


def fetch_department(department: dict[str, Any], output_dir: Path) -> tuple[dict[str, Any], str]:
    cache_path = output_dir / "osm_overpass_raw.json"
    meta_path = output_dir / "osm_overpass_meta.json"
    if cache_path.exists() and not REFRESH:
        return json.loads(cache_path.read_text(encoding="utf-8")), "CACHE"

    try:
        payload = post_overpass(build_area_query(department["iso"]))
        if payload.get("elements"):
            cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            meta_path.write_text(json.dumps({"query_mode": "AREA", **department}, ensure_ascii=False, indent=2), encoding="utf-8")
            return payload, "AREA"
    except Exception:
        pass

    payload = post_overpass(build_bbox_query(department["bbox"]))
    cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    meta_path.write_text(json.dumps({"query_mode": "BBOX", **department}, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload, "BBOX"


def parse_osm_segments(overpass: dict[str, Any], department: dict[str, Any], query_mode: str) -> pd.DataFrame:
    rows = []
    for element in overpass.get("elements", []):
        if element.get("type") != "way":
            continue
        tags = element.get("tags", {})
        geometry = element.get("geometry", [])
        coords = [(float(point["lon"]), float(point["lat"])) for point in geometry if "lon" in point and "lat" in point]
        if len(coords) < 2:
            continue
        name = tags.get("name", "")
        ref = tags.get("ref", "")
        alt_name = tags.get("alt_name", "")
        official_name = tags.get("official_name", "")
        name_norm = normalize_text(name)
        ref_norm = normalize_text(ref)
        alt_name_norm = normalize_text(alt_name)
        official_name_norm = normalize_text(official_name)
        road_key_norm = name_norm or ref_norm or alt_name_norm or official_name_norm or f"osm_way_{element.get('id')}"
        rows.append(
            {
                "source_department": department["name"],
                "source_department_slug": department["slug"],
                "source_query_mode": query_mode,
                "osm_way_id": element.get("id"),
                "name": name,
                "ref": ref,
                "alt_name": alt_name,
                "official_name": official_name,
                "highway": tags.get("highway", ""),
                "oneway": tags.get("oneway", ""),
                "lanes": tags.get("lanes", ""),
                "maxspeed": tags.get("maxspeed", ""),
                "surface": tags.get("surface", ""),
                "bridge": tags.get("bridge", ""),
                "tunnel": tags.get("tunnel", ""),
                "junction": tags.get("junction", ""),
                "access": tags.get("access", ""),
                "length_m": round(line_length_m(coords), 2),
                "vertices": len(coords),
                "name_norm": name_norm,
                "ref_norm": ref_norm,
                "alt_name_norm": alt_name_norm,
                "official_name_norm": official_name_norm,
                "road_key_norm": road_key_norm,
                "road_type_category": road_type_category(tags.get("highway", "")),
                "geometry_json": json.dumps(coords, ensure_ascii=False),
            }
        )
    return pd.DataFrame(rows)


def mode_value(values: pd.Series) -> str:
    clean = [str(value) for value in values if pd.notna(value) and str(value).strip()]
    return Counter(clean).most_common(1)[0][0] if clean else ""


def unique_join(values: pd.Series, limit: int = 8) -> str:
    clean = sorted({str(value).strip() for value in values if pd.notna(value) and str(value).strip()})
    if len(clean) > limit:
        return "; ".join(clean[:limit]) + f"; +{len(clean) - limit} mas"
    return "; ".join(clean)


def build_road_catalog(segments: pd.DataFrame) -> pd.DataFrame:
    if segments.empty:
        return pd.DataFrame()
    return (
        segments.groupby(["source_department", "road_key_norm"], dropna=False)
        .agg(
            segment_count=("osm_way_id", "count"),
            osm_way_ids=("osm_way_id", lambda s: ";".join(str(int(v)) for v in s if pd.notna(v))),
            length_km=("length_m", lambda s: round(float(s.sum()) / 1000, 3)),
            representative_name=("name", mode_value),
            names=("name", unique_join),
            refs=("ref", unique_join),
            alt_names=("alt_name", unique_join),
            official_names=("official_name", unique_join),
            predominant_highway=("highway", mode_value),
            highway_values=("highway", unique_join),
            predominant_road_type=("road_type_category", mode_value),
            oneway_values=("oneway", unique_join),
            lanes_values=("lanes", unique_join),
            maxspeed_values=("maxspeed", unique_join),
            surface_values=("surface", unique_join),
        )
        .reset_index()
        .sort_values(["source_department", "segment_count", "length_km"], ascending=[True, False, False])
    )


def write_segments_geojson(segments: pd.DataFrame, path: Path) -> None:
    features = []
    for _, row in segments.iterrows():
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": json.loads(row["geometry_json"])},
                "properties": {key: row.get(key) for key in ["source_department", "osm_way_id", "name", "ref", "highway", "oneway", "lanes", "maxspeed", "surface", "length_m", "road_key_norm", "road_type_category"]},
            }
        )
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False), encoding="utf-8")


def selected_departments() -> list[dict[str, Any]]:
    raw = os.environ.get("OSM_DEPARTMENTS", "").strip()
    if not raw:
        return DEPARTMENTS
    wanted = {normalize_text(item).replace(" ", "_") for item in raw.split(",") if item.strip()}
    return [dept for dept in DEPARTMENTS if dept["slug"] in wanted or normalize_text(dept["name"]).replace(" ", "_") in wanted]


def main() -> None:
    DEPARTMENTS_DIR.mkdir(parents=True, exist_ok=True)
    NATIONAL_DIR.mkdir(parents=True, exist_ok=True)

    all_segments = []
    diagnostics = []
    for dept in selected_departments():
        out_dir = DEPARTMENTS_DIR / dept["slug"]
        out_dir.mkdir(parents=True, exist_ok=True)
        try:
            overpass, mode = fetch_department(dept, out_dir)
            segments = parse_osm_segments(overpass, dept, mode)
            catalog = build_road_catalog(segments)
            segments.to_csv(out_dir / "osm_road_segments.csv", index=False)
            catalog.to_csv(out_dir / "osm_road_catalog.csv", index=False)
            write_segments_geojson(segments, out_dir / "osm_road_segments.geojson")
            if not segments.empty:
                all_segments.append(segments)
            diagnostics.append(
                {
                    "department": dept["name"],
                    "slug": dept["slug"],
                    "status": "OK" if not segments.empty else "EMPTY",
                    "query_mode": mode,
                    "segments": len(segments),
                    "catalog_roads": len(catalog),
                    "length_km": round(float(segments["length_m"].sum()) / 1000, 3) if not segments.empty else 0,
                    "message": "",
                }
            )
            print(f"{dept['name']}: {len(segments)} segmentos ({mode})")
        except Exception as exc:
            diagnostics.append(
                {
                    "department": dept["name"],
                    "slug": dept["slug"],
                    "status": "ERROR",
                    "query_mode": "",
                    "segments": 0,
                    "catalog_roads": 0,
                    "length_km": 0,
                    "message": str(exc),
                }
            )
            print(f"{dept['name']}: ERROR {exc}")

    national = pd.concat(all_segments, ignore_index=True) if all_segments else pd.DataFrame()
    if not national.empty:
        national = national.drop_duplicates(subset=["osm_way_id", "geometry_json"]).reset_index(drop=True)
    national_catalog = build_road_catalog(national) if not national.empty else pd.DataFrame()
    national.to_csv(NATIONAL_DIR / "osm_road_segments.csv", index=False)
    national_catalog.to_csv(NATIONAL_DIR / "osm_road_catalog.csv", index=False)
    if not national.empty:
        write_segments_geojson(national, NATIONAL_DIR / "osm_road_segments.geojson")
    pd.DataFrame(diagnostics).to_csv(NATIONAL_DIR / "diagnostico_cobertura_osm.csv", index=False)
    print(f"Nacional consolidado: {len(national)} segmentos")
    print(f"Diagnostico: {NATIONAL_DIR / 'diagnostico_cobertura_osm.csv'}")


if __name__ == "__main__":
    main()
