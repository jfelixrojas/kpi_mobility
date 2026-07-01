#!/usr/bin/env python3
"""
Descarga red vial OSM con Overpass y hace match textual con corredores
candidatos extraidos desde noticias.

Objetivo:
- Construir una red OSM enriquecida para el area capitalina de San Salvador.
- Manejar que una misma via en OSM esta dividida en muchos ways/segmentos.
- Agregar esos segmentos en un catalogo de corredores.
- Comparar los nombres extraidos de noticias contra name/ref/alt_name de OSM.

No geocodifica eventos ni hace map matching espacial punto-segmento.
"""

from __future__ import annotations

import json
import math
import re
import time
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib import parse, request

import pandas as pd

from social_road_index_poc import RESULTS_DIR, markdown_table, normalize_text, pct


ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT / "Data" / "Processed" / "osm_roads_san_salvador"
OVERPASS_ENDPOINT = "https://overpass-api.de/api/interpreter"

# BBox amplio para AMSS y entorno inmediato:
# sur, oeste, norte, este
AMSS_BBOX = (13.55, -89.42, 13.92, -89.00)
REFRESH_OVERPASS_CACHE = False

CAPITAL_CORRIDORS = RESULTS_DIR / "capital_corridor_candidates.csv"

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


def osm_text(value: Any) -> str:
    text = normalize_text(value)
    replacements = {
        r"\bboulevard\b": "bulevar",
        r"\bblvd\b": "bulevar",
        r"\bblvr\b": "bulevar",
        r"\bblv\b": "bulevar",
        r"\bav\.\b": "avenida",
        r"\bav\b": "avenida",
        r"\bave\b": "avenida",
        r"\bavenida\.\b": "avenida",
        r"\bcarret\.\b": "carretera",
        r"\bctra\b": "carretera",
        r"\bcalz\.\b": "calle",
        r"\bcalle\.\b": "calle",
        r"\bautop\.\b": "autopista",
        r"\bpanamerican highway\b": "carretera panamericana",
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)
    text = text.replace("º", "").replace("ª", "")
    text = re.sub(r"\bnorte\b", "norte", text)
    text = re.sub(r"\bsur\b", "sur", text)
    text = re.sub(r"\boriente\b", "oriente", text)
    text = re.sub(r"\bponiente\b", "poniente", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def road_type_category(highway: str) -> str:
    highway = osm_text(highway)
    if highway in {"motorway", "trunk", "motorway link", "trunk link"}:
        return "NACIONAL_ESTRUCTURANTE"
    if highway in {"primary", "primary link"}:
        return "ARTERIAL_PRINCIPAL"
    if highway in {"secondary", "secondary link"}:
        return "ARTERIAL_SECUNDARIA"
    if highway in {"tertiary", "tertiary link"}:
        return "COLECTORA"
    if highway in {"residential", "living street"}:
        return "LOCAL_RESIDENCIAL"
    if highway == "service":
        return "SERVICIO_ACCESO"
    if highway == "unclassified":
        return "NO_CLASIFICADA_OSM"
    return "OTRA"


def build_overpass_query() -> str:
    south, west, north, east = AMSS_BBOX
    highway_regex = "^(" + "|".join(HIGHWAY_VALUES) + ")$"
    return f"""
[out:json][timeout:180];
(
  way["highway"~"{highway_regex}"]["name"]({south},{west},{north},{east});
  way["highway"~"{highway_regex}"]["ref"]({south},{west},{north},{east});
);
out tags geom;
"""


def fetch_overpass_json(cache_path: Path) -> dict[str, Any]:
    if cache_path.exists() and not REFRESH_OVERPASS_CACHE:
        return json.loads(cache_path.read_text(encoding="utf-8"))

    query = build_overpass_query()
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
                payload = response.read().decode("utf-8")
            cache_path.write_text(payload, encoding="utf-8")
            return json.loads(payload)
        except Exception as exc:
            last_error = exc
            time.sleep(3 + attempt * 3)
    raise RuntimeError(f"No fue posible consultar Overpass: {last_error}")


def haversine_m(a_lon: float, a_lat: float, b_lon: float, b_lat: float) -> float:
    phi1 = math.radians(a_lat)
    phi2 = math.radians(b_lat)
    dphi = math.radians(b_lat - a_lat)
    dlambda = math.radians(b_lon - a_lon)
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


def line_length_m(coords: list[tuple[float, float]]) -> float:
    total = 0.0
    for (a_lon, a_lat), (b_lon, b_lat) in zip(coords, coords[1:]):
        total += haversine_m(a_lon, a_lat, b_lon, b_lat)
    return total


def parse_osm_segments(overpass: dict[str, Any]) -> pd.DataFrame:
    rows = []
    for element in overpass.get("elements", []):
        if element.get("type") != "way":
            continue
        tags = element.get("tags", {})
        geometry = element.get("geometry", [])
        coords = [
            (float(point["lon"]), float(point["lat"]))
            for point in geometry
            if "lon" in point and "lat" in point
        ]
        if len(coords) < 2:
            continue

        name = tags.get("name", "")
        ref = tags.get("ref", "")
        alt_name = tags.get("alt_name", "")
        official_name = tags.get("official_name", "")
        highway = tags.get("highway", "")
        length_m = line_length_m(coords)

        name_norm = osm_text(name)
        ref_norm = osm_text(ref)
        alt_name_norm = osm_text(alt_name)
        official_name_norm = osm_text(official_name)
        road_key_norm = name_norm or ref_norm or alt_name_norm or official_name_norm or f"osm_way_{element.get('id')}"

        rows.append(
            {
                "osm_way_id": element.get("id"),
                "name": name,
                "ref": ref,
                "alt_name": alt_name,
                "official_name": official_name,
                "highway": highway,
                "oneway": tags.get("oneway", ""),
                "lanes": tags.get("lanes", ""),
                "maxspeed": tags.get("maxspeed", ""),
                "surface": tags.get("surface", ""),
                "bridge": tags.get("bridge", ""),
                "tunnel": tags.get("tunnel", ""),
                "junction": tags.get("junction", ""),
                "access": tags.get("access", ""),
                "length_m": round(length_m, 2),
                "vertices": len(coords),
                "name_norm": name_norm,
                "ref_norm": ref_norm,
                "alt_name_norm": alt_name_norm,
                "official_name_norm": official_name_norm,
                "road_key_norm": road_key_norm,
                "road_type_category": road_type_category(highway),
                "geometry_json": json.dumps(coords, ensure_ascii=False),
            }
        )
    return pd.DataFrame(rows)


def mode_value(values: pd.Series) -> str:
    clean = [str(value) for value in values if pd.notna(value) and str(value).strip()]
    if not clean:
        return ""
    return Counter(clean).most_common(1)[0][0]


def unique_join(values: pd.Series, limit: int = 8) -> str:
    clean = sorted({str(value).strip() for value in values if pd.notna(value) and str(value).strip()})
    if len(clean) > limit:
        return "; ".join(clean[:limit]) + f"; +{len(clean) - limit} mas"
    return "; ".join(clean)


def build_road_catalog(segments: pd.DataFrame) -> pd.DataFrame:
    if segments.empty:
        return pd.DataFrame()

    catalog = (
        segments.groupby("road_key_norm", dropna=False)
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
            bridge_values=("bridge", unique_join),
            tunnel_values=("tunnel", unique_join),
            junction_values=("junction", unique_join),
        )
        .reset_index()
    )
    catalog["search_text"] = catalog.apply(
        lambda row: osm_text(
            " ".join(
                [
                    str(row["road_key_norm"]),
                    str(row["representative_name"]),
                    str(row["names"]),
                    str(row["refs"]),
                    str(row["alt_names"]),
                    str(row["official_names"]),
                ]
            )
        ),
        axis=1,
    )
    return catalog.sort_values(["segment_count", "length_km"], ascending=False)


def token_jaccard(a: str, b: str) -> float:
    a_tokens = set(a.split())
    b_tokens = set(b.split())
    if not a_tokens or not b_tokens:
        return 0.0
    return len(a_tokens & b_tokens) / len(a_tokens | b_tokens)


def text_match_score(candidate: str, osm_text_value: str) -> tuple[float, str]:
    candidate_norm = osm_text(candidate)
    osm_norm = osm_text(osm_text_value)
    if not candidate_norm or not osm_norm:
        return 0.0, "EMPTY"
    if candidate_norm == osm_norm:
        return 1.0, "EXACT"
    if candidate_norm in osm_norm:
        smaller = min(len(candidate_norm), len(osm_norm))
        larger = max(len(candidate_norm), len(osm_norm))
        length_ratio = smaller / larger if larger else 0
        return round(0.86 + 0.10 * length_ratio, 4), "CONTAINS"
    if osm_norm in candidate_norm:
        smaller = min(len(candidate_norm), len(osm_norm))
        larger = max(len(candidate_norm), len(osm_norm))
        length_ratio = smaller / larger if larger else 0
        if length_ratio >= 0.70:
            return round(0.82 + 0.10 * length_ratio, 4), "CONTAINS_PARTIAL"
        if length_ratio >= 0.50:
            return round(0.64 + 0.12 * length_ratio, 4), "PARTIAL_REVIEW"
        return round(0.45 + 0.10 * length_ratio, 4), "PARTIAL_WEAK"
    ratio = SequenceMatcher(None, candidate_norm, osm_norm).ratio()
    jaccard = token_jaccard(candidate_norm, osm_norm)
    score = 0.70 * ratio + 0.30 * jaccard
    return round(score, 4), "FUZZY"


def split_aliases(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return []
    aliases = []
    for raw in str(value).split(";"):
        alias = osm_text(raw)
        if len(alias) >= 4 and not re.fullmatch(r"[a-z]|\d+", alias):
            aliases.append(alias)
    return aliases


def road_aliases(row: pd.Series) -> list[str]:
    aliases = []
    for field in [
        "road_key_norm",
        "representative_name",
        "names",
        "refs",
        "alt_names",
        "official_names",
    ]:
        aliases.extend(split_aliases(row.get(field)))
    return sorted(set(aliases))


def best_road_text_match(candidate: str, road: pd.Series) -> tuple[float, str, str]:
    best_score = 0.0
    best_method = "NO_ALIAS"
    best_alias = ""
    for alias in road_aliases(road):
        score, method = text_match_score(candidate, alias)
        if score > best_score:
            best_score = score
            best_method = method
            best_alias = alias
    return best_score, best_method, best_alias


def match_status(score: float, alternatives: int, method: str) -> str:
    if method in {"EXACT", "CONTAINS"} and score >= 0.88 and alternatives <= 5:
        return "TEXT_MATCH_ACCEPTED"
    if score >= 0.78:
        return "TEXT_MATCH_REVIEW"
    if score >= 0.65:
        return "WEAK_TEXT_MATCH_REVIEW"
    return "NO_TEXT_MATCH"


def build_text_matches(candidates: pd.DataFrame, catalog: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, candidate in candidates.iterrows():
        candidate_name = candidate["corridor"]
        scored = []
        for _, road in catalog.iterrows():
            score, method, alias = best_road_text_match(candidate_name, road)
            if score >= 0.55:
                scored.append((score, method, alias, road))
        scored.sort(key=lambda item: (item[0], float(item[3]["length_km"]), int(item[3]["segment_count"])), reverse=True)
        alternatives = len([item for item in scored if item[0] >= 0.78])

        if scored:
            best_score, best_method, best_alias, best = scored[0]
            top_alternatives = [
                {
                    "road_key_norm": item[3]["road_key_norm"],
                    "name": item[3]["representative_name"],
                    "alias": item[2],
                    "score": item[0],
                    "highway": item[3]["predominant_highway"],
                    "length_km": item[3]["length_km"],
                }
                for item in scored[:5]
            ]
            rows.append(
                {
                    "road_name_candidate": candidate_name,
                    "news_events": candidate.get("events"),
                    "news_severity_sum": candidate.get("severity_sum"),
                    "news_mentions_sum": candidate.get("mentions_sum"),
                    "matched_road_key_norm": best["road_key_norm"],
                    "matched_osm_name": best["representative_name"],
                    "matched_names": best["names"],
                    "matched_refs": best["refs"],
                    "predominant_highway": best["predominant_highway"],
                    "highway_values": best["highway_values"],
                    "predominant_road_type": best["predominant_road_type"],
                    "segment_count": best["segment_count"],
                    "length_km": best["length_km"],
                    "oneway_values": best["oneway_values"],
                    "lanes_values": best["lanes_values"],
                    "maxspeed_values": best["maxspeed_values"],
                    "surface_values": best["surface_values"],
                    "text_match_score": best_score,
                    "text_match_method": best_method,
                    "matched_alias": best_alias,
                    "alternative_matches_ge_078": alternatives,
                    "match_status": match_status(best_score, alternatives, best_method),
                    "top_alternatives_json": json.dumps(top_alternatives, ensure_ascii=False),
                }
            )
        else:
            rows.append(
                {
                    "road_name_candidate": candidate_name,
                    "news_events": candidate.get("events"),
                    "news_severity_sum": candidate.get("severity_sum"),
                    "news_mentions_sum": candidate.get("mentions_sum"),
                    "matched_road_key_norm": "",
                    "matched_osm_name": "",
                    "matched_names": "",
                    "matched_refs": "",
                    "predominant_highway": "",
                    "highway_values": "",
                    "predominant_road_type": "",
                    "segment_count": 0,
                    "length_km": 0,
                    "oneway_values": "",
                    "lanes_values": "",
                    "maxspeed_values": "",
                    "surface_values": "",
                    "text_match_score": 0.0,
                    "text_match_method": "NO_CANDIDATE",
                    "matched_alias": "",
                    "alternative_matches_ge_078": 0,
                    "match_status": "NO_TEXT_MATCH",
                    "top_alternatives_json": "[]",
                }
            )
    return pd.DataFrame(rows).sort_values(["match_status", "text_match_score", "news_events"], ascending=[True, False, False])


def write_segments_geojson(segments: pd.DataFrame, path: Path) -> None:
    features = []
    for _, row in segments.iterrows():
        coords = json.loads(row["geometry_json"])
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {
                    "osm_way_id": int(row["osm_way_id"]),
                    "name": row["name"],
                    "ref": row["ref"],
                    "highway": row["highway"],
                    "oneway": row["oneway"],
                    "lanes": row["lanes"],
                    "maxspeed": row["maxspeed"],
                    "surface": row["surface"],
                    "length_m": row["length_m"],
                    "road_key_norm": row["road_key_norm"],
                    "road_type_category": row["road_type_category"],
                },
            }
        )
    geojson = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(geojson, ensure_ascii=False), encoding="utf-8")


def write_summary(
    segments: pd.DataFrame,
    catalog: pd.DataFrame,
    candidates: pd.DataFrame,
    matches: pd.DataFrame,
    path: Path,
) -> None:
    status_counts = matches["match_status"].value_counts().reset_index()
    status_counts.columns = ["match_status", "count"]
    status_counts["percent"] = status_counts["count"].map(lambda n: pct(n, len(matches)))

    highway_counts = segments["highway"].value_counts().reset_index()
    highway_counts.columns = ["highway", "segments"]
    highway_counts["percent"] = highway_counts["segments"].map(lambda n: pct(n, len(segments)))

    type_counts = catalog["predominant_road_type"].value_counts().reset_index()
    type_counts.columns = ["road_type", "corridors"]
    type_counts["percent"] = type_counts["corridors"].map(lambda n: pct(n, len(catalog)))

    accepted = matches[matches["match_status"] == "TEXT_MATCH_ACCEPTED"].copy()
    review = matches[matches["match_status"].isin(["TEXT_MATCH_REVIEW", "WEAK_TEXT_MATCH_REVIEW"])].copy()
    no_match = matches[matches["match_status"] == "NO_TEXT_MATCH"].copy()

    lines = [
        "OSM ENRIQUECIDO Y MATCH TEXTUAL DE VIAS",
        "=" * 44,
        "",
        "1. Objetivo",
        "-" * 11,
        "Construir una red vial OSM enriquecida para el area capitalina y comparar los corredores/vias extraidos de noticias contra name/ref/alt_name de OSM.",
        "Esto permite pasar de una mencion textual de via a un corredor OSM con atributos como highway, oneway, lanes, maxspeed, surface y longitud aproximada.",
        "",
        "2. Manejo de vias divididas en muchos segmentos",
        "-" * 49,
        "OSM representa una misma via como multiples ways. Por eso se generan dos niveles:",
        "- Segmentos OSM: cada way individual con geometria y tags.",
        "- Catalogo de corredores: agrupacion por nombre/ref normalizado.",
        "El match textual se hace contra el catalogo de corredores, no contra cada segmento individual.",
        "",
        "3. Cobertura descargada",
        "-" * 22,
        f"BBox AMSS usada (sur, oeste, norte, este): {AMSS_BBOX}",
        f"Segmentos OSM descargados con name/ref: {len(segments)}",
        f"Corredores agrupados: {len(catalog)}",
        f"Longitud total aproximada de segmentos: {round(float(segments['length_m'].sum()) / 1000, 2)} km",
        "",
        "4. Distribucion de segmentos por highway",
        "-" * 41,
        markdown_table(highway_counts.head(20), max_col_width=120),
        "",
        "5. Distribucion de corredores por tipo predominante",
        "-" * 52,
        markdown_table(type_counts, max_col_width=120),
        "",
        "6. Match textual contra corredores de noticias",
        "-" * 46,
        f"Corredores candidatos desde noticias: {len(candidates)}",
        f"Matches aceptados: {len(accepted)}",
        f"Matches en revision: {len(review)}",
        f"Sin match suficiente: {len(no_match)}",
        "",
        markdown_table(status_counts, max_col_width=120),
        "",
        "7. Matches aceptados",
        "-" * 20,
        markdown_table(
            accepted[
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
            max_col_width=140,
        ),
        "",
        "8. Matches en revision",
        "-" * 22,
        markdown_table(
            review[
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
            max_col_width=140,
        ),
        "",
        "9. Sin match suficiente",
        "-" * 24,
        markdown_table(no_match[["road_name_candidate", "news_events", "text_match_score", "match_status"]], max_col_width=120),
        "",
        "10. Uso metodologico",
        "-" * 19,
        "Estos resultados no sustituyen la geocodificacion. Sirven para confirmar que las vias mencionadas en noticias existen en OSM y para asignar atributos viales candidatos.",
        "El siguiente paso es geocodificar direcciones y realizar match espacial punto-segmento sobre los corredores OSM aceptados/revisados.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    raw_path = PROCESSED_DIR / "osm_overpass_amss_raw.json"
    overpass = fetch_overpass_json(raw_path)
    segments = parse_osm_segments(overpass)
    catalog = build_road_catalog(segments)
    candidates = pd.read_csv(CAPITAL_CORRIDORS)
    matches = build_text_matches(candidates, catalog)

    segments.to_csv(PROCESSED_DIR / "osm_road_segments.csv", index=False)
    catalog.to_csv(PROCESSED_DIR / "osm_road_catalog.csv", index=False)
    write_segments_geojson(segments, PROCESSED_DIR / "osm_road_segments.geojson")

    catalog.to_csv(RESULTS_DIR / "osm_road_catalog.csv", index=False)
    matches.to_csv(RESULTS_DIR / "road_text_matches.csv", index=False)
    write_summary(
        segments,
        catalog,
        candidates,
        matches,
        RESULTS_DIR / "capital_osm_match_summary.txt",
    )

    print(f"Segmentos OSM: {len(segments)}")
    print(f"Corredores OSM agrupados: {len(catalog)}")
    print(f"Corredores de noticias: {len(candidates)}")
    print(f"Matches aceptados: {int((matches['match_status'] == 'TEXT_MATCH_ACCEPTED').sum())}")
    print(f"Resultados: {RESULTS_DIR}")


if __name__ == "__main__":
    main()
