#!/usr/bin/env python3
"""
Pipeline de analisis para Data/Waze/waze_jams_2026-06-29.json.

Unidad metodologica:
- La fila cruda no se interpreta como vehiculo ni como evento independiente.
- El uuid se usa como unidad base de congestion.
- Las variaciones internas por uuid se conservan como senal de estabilidad/incertidumbre.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
INPUT_JSON = ROOT / "Data" / "Waze" / "waze_jams_2026-06-29.json"
RESULTS_DIR = ROOT / "Results" / "Waze" / "Jams"
OSM_NATIONAL_CATALOG_PATH = ROOT / "Data" / "Processed" / "osm_roads_nacional" / "osm_road_catalog.csv"
OSM_NATIONAL_SEGMENTS_PATH = ROOT / "Data" / "Processed" / "osm_roads_nacional" / "osm_road_segments.csv"
WAZE_OSM_ALIASES_PATH = ROOT / "Data" / "Processed" / "waze_osm_aliases.csv"

LOCAL_TZ = "America/El_Salvador"
TOTAL_HOURS = 24
EPS = 1e-9
ROUTE_REF_PREFIXES = {
    "ca",
    "rn",
    "lib",
    "sam",
    "sal",
    "ahu",
    "cab",
    "cha",
    "cus",
    "lap",
    "mor",
    "paz",
    "san",
    "son",
    "usu",
}

ROAD_ABBREVIATIONS = [
    (re.compile(r"\bav\b"), "avenida"),
    (re.compile(r"\bavda\b"), "avenida"),
    (re.compile(r"\bblvd\b"), "bulevar"),
    (re.compile(r"\bboulevard\b"), "bulevar"),
    (re.compile(r"\bblvr\b"), "bulevar"),
    (re.compile(r"\bcarr\b"), "carretera"),
    (re.compile(r"\bctra\b"), "carretera"),
    (re.compile(r"\bautop\b"), "autopista"),
    (re.compile(r"\bprol\b"), "prolongacion"),
]


CORRIDOR_RULES: list[dict[str, Any]] = [
    {
        "norm": "Carretera Panamericana",
        "refs": ["ca 1", "ca 1a", "ca 1w", "ca1", "ca1a", "ca1w"],
        "aliases": ["carretera panamericana", "panamericana", "ca 1", "ca 1a", "ca 1w", "ca1", "ca1a", "ca1w"],
    },
    {
        "norm": "Carretera del Litoral",
        "refs": ["ca 2", "ca 2e", "ca 2w", "ca2", "ca2e", "ca2w"],
        "aliases": ["carretera del litoral", "litoral", "ca 2", "ca 2e", "ca 2w", "ca2", "ca2e", "ca2w"],
    },
    {
        "norm": "Carretera Troncal del Norte",
        "refs": ["ca 4", "ca4"],
        "aliases": ["carretera troncal del norte", "troncal del norte"],
    },
    {
        "norm": "Autopista a Comalapa",
        "refs": ["rn 5", "rn5"],
        "aliases": ["autopista a comalapa", "autopista comalapa", "carretera a comalapa", "rn 5", "rn5"],
    },
    {
        "norm": "Ruta Militar",
        "refs": ["rn 18", "rn18", "ca 7", "ca7"],
        "aliases": ["ruta militar", "rn 18", "rn18", "ca 7", "ca7"],
    },
    {
        "norm": "Bulevar Venezuela",
        "refs": [],
        "aliases": ["bulevar venezuela", "boulevard venezuela"],
    },
    {
        "norm": "Bulevar del Ejercito",
        "refs": [],
        "aliases": ["bulevar del ejercito", "boulevard del ejercito"],
    },
    {
        "norm": "Bulevar Constitucion",
        "refs": [],
        "aliases": ["bulevar constitucion", "boulevard constitucion"],
    },
    {
        "norm": "Bulevar de Los Proceres",
        "refs": [],
        "aliases": ["bulevar de los proceres", "boulevard de los proceres"],
    },
    {
        "norm": "Bulevar Monseñor Romero",
        "refs": ["rn 21", "rn21"],
        "aliases": ["bulevar monsenor romero", "bulevar monseñor romero", "rn 21", "rn21"],
    },
    {
        "norm": "Carretera al Puerto de La Libertad",
        "refs": [],
        "aliases": [
            "carretera al puerto de la libertad",
            "carretera del puerto de la libertad",
            "carretera al puerto",
            "carretera a la libertad",
        ],
    },
    {
        "norm": "Calle al Volcan",
        "refs": [],
        "aliases": ["calle al volcan", "calle a el volcan"],
    },
    {
        "norm": "Carril del Sitramss",
        "refs": [],
        "aliases": ["carril del sitramss", "sitramss"],
    },
]


GENERIC_STREET_TERMS = {
    "",
    "sin calle",
    "calle principal",
    "salida",
    "entrada",
}


def load_alias_lookup() -> dict[str, dict[str, Any]]:
    if not WAZE_OSM_ALIASES_PATH.exists():
        return {}
    aliases = pd.read_csv(WAZE_OSM_ALIASES_PATH, low_memory=False)
    required = ["raw_value", "corridor_norm"]
    if any(col not in aliases.columns for col in required):
        return {}
    if "raw_value_norm" not in aliases.columns:
        aliases["raw_value_norm"] = aliases["raw_value"].map(normalize_road_text)
    aliases["priority"] = pd.to_numeric(aliases.get("priority", 50), errors="coerce").fillna(50)
    lookup: dict[str, dict[str, Any]] = {}
    for _, row in aliases.sort_values(["priority", "raw_value_norm"], ascending=[False, True]).iterrows():
        key = normalize_road_text(row.get("raw_value_norm") or row.get("raw_value"))
        if not key or key in lookup:
            continue
        lookup[key] = {
            "corridor_norm": str(row.get("corridor_norm", "")).strip(),
            "corridor_group": str(row.get("corridor_group", "")).strip(),
            "road_scope": str(row.get("road_scope", "")).strip(),
            "source_type": str(row.get("source_type", "")).strip(),
            "notes": str(row.get("notes", "")).strip(),
            "priority": float(row.get("priority", 50) or 50),
        }
    return lookup


def alias_match(text: str, alias_lookup: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any]] | None:
    if not text:
        return None
    candidates = []
    for key, meta in alias_lookup.items():
        if key and key in text:
            candidates.append((meta.get("priority", 50), len(key), key, meta))
    if not candidates:
        return None
    _, _, key, meta = sorted(candidates, reverse=True)[0]
    corridor = str(meta.get("corridor_norm", "")).strip()
    if not corridor:
        return None
    return corridor, meta | {"matched_alias": key}


def is_route_ref_like(value: Any) -> bool:
    text = normalize_route_ref(value)
    return bool(re.match(r"^(" + "|".join(sorted(ROUTE_REF_PREFIXES)) + r")\s+[0-9]{1,3}[a-z]?$", text))


def infer_corridor_group(corridor: str, method: str, refs: list[str], alias_meta: dict[str, Any] | None = None) -> str:
    if alias_meta and alias_meta.get("corridor_group"):
        return str(alias_meta["corridor_group"])
    corridor_norm = compact_text(corridor)
    if not corridor_norm:
        return "UNRESOLVED"
    if any(ref.startswith(("ca ", "rn ")) for ref in refs):
        return "NACIONAL_REGIONAL"
    if any(ref.startswith(("sal ", "lib ", "sam ", "ahu ", "cab ", "cha ", "cus ", "lap ", "mor ", "san ", "son ", "usu ")) for ref in refs):
        return "DEPARTAMENTAL_LOCAL"
    if any(token in corridor_norm for token in ["panamericana", "litoral", "comalapa", "troncal del norte", "ruta militar"]):
        return "NACIONAL_REGIONAL"
    if method in {"OSM_NAME", "TEXT_ALIAS", "TEXT_ALIAS_TABLE"} and any(
        token in corridor_norm for token in ["bulevar", "alameda", "avenida", "calle", "paseo"]
    ):
        return "URBANO_LOCAL"
    if method == "NODE_CONTEXT":
        return "CONTEXTO_NODO"
    if is_route_ref_like(corridor):
        return "REFERENCIA_OSM_SIN_NOMBRE"
    return "LOCAL_NO_CLASIFICADO"


def infer_road_scope(corridor: str, method: str, refs: list[str], alias_meta: dict[str, Any] | None = None) -> str:
    if alias_meta and alias_meta.get("road_scope"):
        return str(alias_meta["road_scope"])
    group = infer_corridor_group(corridor, method, refs, alias_meta)
    if group == "NACIONAL_REGIONAL":
        return "CORREDOR_ESTRUCTURANTE"
    if group == "DEPARTAMENTAL_LOCAL":
        return "REFERENCIA_DEPARTAMENTAL"
    if group == "URBANO_LOCAL":
        return "VIA_URBANA"
    if group == "CONTEXTO_NODO":
        return "CONTEXTO_NO_VIA"
    if group == "REFERENCIA_OSM_SIN_NOMBRE":
        return "REFERENCIA_OSM_SIN_NOMBRE"
    return "NO_CLASIFICADO"


def resolved_payload(
    *,
    candidate: str,
    corridor: str,
    method: str,
    confidence: str,
    refs: list[str],
    local_name: str = "",
    alias_meta: dict[str, Any] | None = None,
    osm_meta: dict[str, Any] | None = None,
    detail: str = "",
) -> dict[str, Any]:
    meta = osm_meta or {}
    return {
        "corridor_candidate_waze": candidate,
        "corridor_norm_waze": corridor,
        "corridor_local_name_waze": local_name,
        "corridor_group_waze": infer_corridor_group(corridor, method, refs, alias_meta),
        "road_scope_waze": infer_road_scope(corridor, method, refs, alias_meta),
        "corridor_match_method": method,
        "corridor_match_confidence": confidence,
        "corridor_match_status": "RESOLVED",
        "unresolved_reason": "",
        "corridor_resolution_detail": detail,
        "osm_catalog_road_type": meta.get("road_type", ""),
        "osm_catalog_length_km": meta.get("length_km", ""),
        "osm_catalog_departments": meta.get("departments", ""),
    }


def unresolved_payload(reason: str) -> dict[str, Any]:
    return {
        "corridor_candidate_waze": "",
        "corridor_norm_waze": "",
        "corridor_local_name_waze": "",
        "corridor_group_waze": "UNRESOLVED",
        "road_scope_waze": "UNRESOLVED",
        "corridor_match_method": "UNRESOLVED",
        "corridor_match_confidence": "UNRESOLVED",
        "corridor_match_status": "UNRESOLVED",
        "unresolved_reason": reason,
        "corridor_resolution_detail": reason,
        "osm_catalog_road_type": "",
        "osm_catalog_length_km": "",
        "osm_catalog_departments": "",
    }


def ensure_dirs() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)


def normalize_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip().lower()
    text = "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )
    text = text.replace("ª", "a").replace("º", "o")
    text = re.sub(r"[\u2010-\u2015]", "-", text)
    text = re.sub(r"[^a-z0-9/ ._-]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def compact_text(value: Any) -> str:
    text = normalize_text(value)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_road_text(value: Any) -> str:
    text = compact_text(value)
    for pattern, replacement in ROAD_ABBREVIATIONS:
        text = pattern.sub(replacement, text)
    return re.sub(r"\s+", " ", text).strip()


def format_route_ref(value: Any) -> str:
    ref = normalize_route_ref(value)
    match = re.match(r"^([a-z]+)\s+([0-9]{1,3}[a-z]?)$", ref)
    if not match:
        return title_case(ref)
    return f"{match.group(1).upper()} {match.group(2).upper()}"


def title_case(value: Any) -> str:
    text = compact_text(value)
    if not text:
        return ""
    lower_words = {"a", "al", "de", "del", "la", "las", "los", "y", "el"}
    out = []
    for idx, token in enumerate(text.split()):
        if idx > 0 and token in lower_words:
            out.append(token)
        elif token in ROUTE_REF_PREFIXES:
            out.append(token.upper())
        elif idx > 0 and out[-1].lower() in ROUTE_REF_PREFIXES and re.match(r"^[0-9]{1,3}[a-z]?$", token):
            out.append(token.upper())
        else:
            out.append(token.capitalize())
    return " ".join(out)


def pct(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round(float(numerator) / float(denominator) * 100, 2)


def mode_value(series: pd.Series) -> Any:
    nonempty = series.dropna().astype(str)
    nonempty = nonempty[nonempty.str.strip() != ""]
    if nonempty.empty:
        return ""
    counts = Counter(nonempty.tolist())
    return counts.most_common(1)[0][0]


def normalize_route_ref(value: Any) -> str:
    text = compact_text(value)
    if not text:
        return ""
    match = re.match(r"^(ca|rn|lib|sam|sal|ahu|cab|cha|cus|lap|mor|paz|san|son|usu)\s*0*([0-9]{1,3}[a-z]?)$", text)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return text


def extract_route_refs(*values: Any) -> list[str]:
    text = " ".join(normalize_text(value) for value in values if value is not None)
    # Match CA-1, CA1, CA 1A, RN-5, LIB 15, SAM 01, SAL 37N.
    pattern = re.compile(r"\b(ca|rn|lib|sam|sal|ahu|cab|cha|cus|lap|mor|paz|san|son|usu)\s*-?\s*0*([0-9]{1,3}[a-z]?)\b", re.I)
    refs = []
    for prefix, number in pattern.findall(text):
        refs.append(normalize_route_ref(f"{prefix} {number}"))
    return sorted(set(refs))


def road_name_after_ref(street: Any) -> str:
    text = normalize_text(street)
    if "/" not in text:
        return ""
    parts = [normalize_road_text(part) for part in text.split("/") if normalize_road_text(part)]
    if len(parts) < 2:
        return ""
    first = parts[0]
    if first and not extract_route_refs(first):
        return title_case(first)
    # Prefer the first non-ref descriptive part.
    for part in parts[1:]:
        if not extract_route_refs(part):
            return title_case(part)
    return title_case(parts[-1])


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


def robust_norm(series: pd.Series, upper_quantile: float = 0.95) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").fillna(0.0).astype(float)
    if values.empty:
        return values
    lower = float(values.min())
    upper = float(values.quantile(upper_quantile))
    if upper <= lower:
        upper = float(values.max())
    if upper <= lower:
        return pd.Series(0.0, index=values.index)
    clipped = values.clip(lower=lower, upper=upper)
    return ((clipped - lower) / (upper - lower)).clip(0, 1)


def build_osm_lookup() -> tuple[dict[str, str], dict[str, str], set[str], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    if not OSM_NATIONAL_CATALOG_PATH.exists():
        return {}, {}, set(), {}, {}
    catalog = pd.read_csv(OSM_NATIONAL_CATALOG_PATH, low_memory=False)
    for col in ["road_key_norm", "representative_name", "refs", "length_km", "predominant_road_type", "source_department"]:
        if col not in catalog.columns:
            catalog[col] = ""
    catalog["length_km"] = pd.to_numeric(catalog["length_km"], errors="coerce").fillna(0)
    catalog["road_key_compact"] = catalog["road_key_norm"].map(normalize_road_text)
    catalog = catalog.sort_values("length_km", ascending=False)

    def representative(row: pd.Series, fallback: str = "") -> str:
        for col in ["representative_name", "road_key_norm"]:
            value = row.get(col, "")
            if value is not None and not pd.isna(value) and str(value).strip():
                text = str(value).strip()
                if compact_text(text) != "nan":
                    return text
        return title_case(fallback)

    def metadata(row: pd.Series) -> dict[str, Any]:
        return {
            "road_type": row.get("predominant_road_type", ""),
            "length_km": round(float(row.get("length_km", 0) or 0), 4),
            "departments": row.get("source_department", ""),
        }

    name_map: dict[str, str] = {}
    name_meta: dict[str, dict[str, Any]] = {}
    for _, row in catalog.iterrows():
        key = row["road_key_compact"]
        if key and key not in name_map and not key.startswith("osm way"):
            name_map[key] = representative(row, key)
            name_meta[key] = metadata(row)

    ref_map: dict[str, str] = {}
    ref_meta: dict[str, dict[str, Any]] = {}
    for _, row in catalog.iterrows():
        refs = str(row.get("refs", "") or "")
        for raw_ref in re.split(r";|,", refs):
            ref = normalize_route_ref(raw_ref)
            if ref and ref not in ref_map:
                value = representative(row, ref)
                if compact_text(value) == compact_text(ref):
                    value = format_route_ref(ref)
                ref_map[ref] = value
                ref_meta[ref] = metadata(row)

    return name_map, ref_map, set(name_map.keys()), name_meta, ref_meta


def rule_match(text: str, refs: list[str]) -> tuple[str, str] | None:
    refs_set = {normalize_route_ref(ref) for ref in refs}
    for rule in CORRIDOR_RULES:
        if refs_set.intersection(set(rule["refs"])):
            # CA-4 is ambiguous; require text support for Troncal del Norte unless no better name exists.
            if "ca 4" in refs_set and rule["norm"] == "Carretera Troncal del Norte" and "troncal del norte" not in text:
                continue
            return rule["norm"], "OSM_REF"
        for alias in rule["aliases"]:
            if compact_text(alias) in text:
                return rule["norm"], "TEXT_ALIAS"
    return None


def resolve_corridor(
    row: pd.Series,
    osm_name_map: dict[str, str],
    osm_ref_map: dict[str, str],
    osm_names: set[str],
    osm_name_meta: dict[str, dict[str, Any]],
    osm_ref_meta: dict[str, dict[str, Any]],
    alias_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    street_norm = row.get("street_norm", "")
    start_norm = row.get("start_node_norm", "")
    end_norm = row.get("end_node_norm", "")
    city_norm = row.get("city_norm", "")
    refs = [ref for ref in str(row.get("route_ref", "")).split(";") if ref]
    text = compact_text(" ".join([street_norm, start_norm, end_norm]))
    local_name = title_case(street_norm)

    if not street_norm and not start_norm and not end_norm:
        return unresolved_payload("NO_STREET_OR_NODE_TEXT")

    matched = rule_match(text, refs)
    if matched:
        norm, method = matched
        return resolved_payload(
            candidate=norm,
            corridor=norm,
            method=method,
            confidence="HIGH",
            refs=refs,
            local_name=local_name,
            detail="CORRIDOR_RULE_OR_REF_ALIAS",
        )

    alias = alias_match(text, alias_lookup)
    if alias:
        norm, alias_meta = alias
        return resolved_payload(
            candidate=norm,
            corridor=norm,
            method="TEXT_ALIAS_TABLE",
            confidence="HIGH",
            refs=refs,
            local_name=local_name,
            alias_meta=alias_meta,
            detail=f"ALIAS_TABLE:{alias_meta.get('matched_alias', '')}",
        )

    after_ref = road_name_after_ref(row.get("street_modal", ""))
    after_ref_norm = normalize_road_text(after_ref)

    for ref in refs:
        if ref in osm_ref_map:
            norm = osm_ref_map[ref]
            if is_route_ref_like(norm) and after_ref_norm and not is_route_ref_like(after_ref_norm):
                if after_ref_norm in osm_name_map:
                    corridor = osm_name_map[after_ref_norm]
                    method = "OSM_NAME"
                    confidence = "HIGH"
                    detail = f"REF_WITH_OSM_NAME:{format_route_ref(ref)}"
                    osm_meta = osm_name_meta.get(after_ref_norm, osm_ref_meta.get(ref, {}))
                else:
                    corridor = title_case(after_ref_norm)
                    method = "REF_TEXT_NAME"
                    confidence = "HIGH"
                    detail = f"REF_WITH_TEXT_NAME:{format_route_ref(ref)}"
                    osm_meta = osm_ref_meta.get(ref, {})
                return resolved_payload(
                    candidate=format_route_ref(ref),
                    corridor=corridor,
                    method=method,
                    confidence=confidence,
                    refs=refs,
                    local_name=local_name,
                    osm_meta=osm_meta,
                    detail=detail,
                )
            return resolved_payload(
                candidate=format_route_ref(ref),
                corridor=norm,
                method="OSM_REF",
                confidence="HIGH",
                refs=refs,
                local_name=local_name,
                osm_meta=osm_ref_meta.get(ref, {}),
                detail="OSM_REF_LOOKUP",
            )

    if after_ref_norm:
        if after_ref_norm in osm_name_map:
            norm = osm_name_map[after_ref_norm]
            confidence = "HIGH"
            method = "OSM_NAME"
            osm_meta = osm_name_meta.get(after_ref_norm, {})
            detail = "ROAD_NAME_AFTER_REF_OSM_NAME"
        else:
            norm = title_case(after_ref_norm)
            confidence = "MEDIUM"
            method = "TEXT_STREET"
            osm_meta = {}
            detail = "ROAD_NAME_AFTER_REF_TEXT"
        return resolved_payload(
            candidate=norm,
            corridor=norm,
            method=method,
            confidence=confidence,
            refs=refs,
            local_name=local_name,
            osm_meta=osm_meta,
            detail=detail,
        )

    if street_norm and street_norm not in GENERIC_STREET_TERMS:
        if street_norm in osm_names:
            norm = osm_name_map.get(street_norm, title_case(street_norm))
            method = "OSM_NAME"
            confidence = "HIGH"
            osm_meta = osm_name_meta.get(street_norm, {})
            detail = "OSM_NAME_EXACT"
        else:
            norm = title_case(street_norm)
            method = "TEXT_STREET"
            confidence = "MEDIUM" if city_norm else "LOW"
            osm_meta = {}
            detail = "TEXT_STREET_NO_OSM_EXACT"
        return resolved_payload(
            candidate=norm,
            corridor=norm,
            method=method,
            confidence=confidence,
            refs=refs,
            local_name=local_name,
            osm_meta=osm_meta,
            detail=detail,
        )

    node_candidate = end_norm or start_norm
    if node_candidate and node_candidate not in GENERIC_STREET_TERMS:
        norm = title_case(node_candidate)
        return resolved_payload(
            candidate=norm,
            corridor=norm,
            method="NODE_CONTEXT",
            confidence="LOW",
            refs=refs,
            local_name=title_case(node_candidate),
            detail="NODE_CONTEXT_AS_LAST_RESORT",
        )

    return unresolved_payload("GENERIC_OR_EMPTY_ROAD_TEXT")


def load_jams_json() -> tuple[pd.DataFrame, dict[str, Any]]:
    if not INPUT_JSON.exists():
        raise FileNotFoundError(f"No existe {INPUT_JSON}")
    with INPUT_JSON.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    records = payload.get("records", [])
    meta = {key: value for key, value in payload.items() if key != "records"}
    return pd.DataFrame(records), meta


def add_temporal_fields(df: pd.DataFrame) -> pd.DataFrame:
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
    diagnostics.to_csv(RESULTS_DIR / "diagnostico_campos_jams.csv", index=False)
    return diagnostics


def write_initial_distributions(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    hourly = df.groupby("event_hour", dropna=False).agg(
        raw_records=("uuid", "size"),
        unique_jams=("uuid", "nunique"),
        avg_level=("level", "mean"),
        delay_sum=("delay", "sum"),
        length_sum=("length", "sum"),
        avg_speed_kmh=("speedKMH", "mean"),
    ).reset_index()
    hourly.to_csv(RESULTS_DIR / "distribucion_horaria_jams.csv", index=False)

    rows = []
    for col in ["level", "delay", "length", "speedKMH"]:
        values = pd.to_numeric(df[col], errors="coerce").dropna()
        rows.append(
            {
                "variable": col,
                "count": int(values.count()),
                "min": values.min(),
                "p25": values.quantile(0.25),
                "p50": values.quantile(0.50),
                "p75": values.quantile(0.75),
                "p90": values.quantile(0.90),
                "p95": values.quantile(0.95),
                "p99": values.quantile(0.99),
                "max": values.max(),
                "mean": values.mean(),
                "std": values.std(ddof=0),
            }
        )
    variables = pd.DataFrame(rows)
    variables.to_csv(RESULTS_DIR / "distribucion_variables_jams.csv", index=False)
    return hourly, variables


def aggregate_unique_jams(df: pd.DataFrame) -> pd.DataFrame:
    grouped = df.groupby("uuid", dropna=False).agg(
        id=("id", "first"),
        ts_first=("ts", "first"),
        datetime_utc=("datetime_utc", "first"),
        datetime_local=("datetime_local", "first"),
        event_date_local=("event_date_local", "first"),
        event_hour=("event_hour", "first"),
        event_minute=("event_minute", "first"),
        time_period=("time_period", "first"),
        is_peak_morning=("is_peak_morning", "first"),
        is_peak_evening=("is_peak_evening", "first"),
        is_night=("is_night", "first"),
        city_modal=("city", mode_value),
        street_modal=("street", mode_value),
        startNode_modal=("startNode", mode_value),
        endNode_modal=("endNode", mode_value),
        country_modal=("country", mode_value),
        level_max=("level", "max"),
        level_median=("level", "median"),
        level_mean=("level", "mean"),
        level_range=("level", lambda s: float(pd.to_numeric(s, errors="coerce").max() - pd.to_numeric(s, errors="coerce").min())),
        delay_max=("delay", "max"),
        delay_median=("delay", "median"),
        delay_mean=("delay", "mean"),
        delay_std=("delay", lambda s: float(pd.to_numeric(s, errors="coerce").std(ddof=0) or 0)),
        delay_range=("delay", lambda s: float(pd.to_numeric(s, errors="coerce").max() - pd.to_numeric(s, errors="coerce").min())),
        length_max=("length", "max"),
        length_median=("length", "median"),
        length_mean=("length", "mean"),
        length_std=("length", lambda s: float(pd.to_numeric(s, errors="coerce").std(ddof=0) or 0)),
        length_range=("length", lambda s: float(pd.to_numeric(s, errors="coerce").max() - pd.to_numeric(s, errors="coerce").min())),
        speed_min=("speedKMH", "min"),
        speed_median=("speedKMH", "median"),
        speed_mean=("speedKMH", "mean"),
        speed_std=("speedKMH", lambda s: float(pd.to_numeric(s, errors="coerce").std(ddof=0) or 0)),
        speed_range=("speedKMH", lambda s: float(pd.to_numeric(s, errors="coerce").max() - pd.to_numeric(s, errors="coerce").min())),
        records_per_uuid=("uuid", "size"),
    ).reset_index()
    for col in ["datetime_utc", "datetime_local"]:
        grouped[col] = grouped[col].astype(str)
    grouped.to_csv(RESULTS_DIR / "waze_jams_unique_base.csv", index=False)
    return grouped


def add_text_fields(jams: pd.DataFrame) -> pd.DataFrame:
    out = jams.copy()
    out["street_norm"] = out["street_modal"].map(normalize_road_text)
    out["city_norm"] = out["city_modal"].map(compact_text)
    out["start_node_norm"] = out["startNode_modal"].map(normalize_road_text)
    out["end_node_norm"] = out["endNode_modal"].map(normalize_road_text)
    out["road_text_combined"] = (
        out["street_norm"].fillna("")
        + " "
        + out["start_node_norm"].fillna("")
        + " "
        + out["end_node_norm"].fillna("")
    ).map(compact_text)
    out["route_ref"] = out.apply(
        lambda row: ";".join(extract_route_refs(row["street_modal"], row["startNode_modal"], row["endNode_modal"])),
        axis=1,
    )
    out["road_name_candidate"] = out["street_modal"].map(road_name_after_ref)
    out["has_street"] = out["street_norm"].fillna("").ne("")
    out["has_nodes"] = out["start_node_norm"].fillna("").ne("") | out["end_node_norm"].fillna("").ne("")
    out["has_route_ref"] = out["route_ref"].fillna("").ne("")
    out[
        [
            "uuid",
            "street_modal",
            "city_modal",
            "startNode_modal",
            "endNode_modal",
            "street_norm",
            "city_norm",
            "start_node_norm",
            "end_node_norm",
            "road_text_combined",
            "route_ref",
            "road_name_candidate",
            "has_street",
            "has_nodes",
            "has_route_ref",
        ]
    ].to_csv(RESULTS_DIR / "waze_jams_text_normalization.csv", index=False)
    return out


def add_corridor_resolution(jams: pd.DataFrame) -> pd.DataFrame:
    osm_name_map, osm_ref_map, osm_names, osm_name_meta, osm_ref_meta = build_osm_lookup()
    alias_lookup = load_alias_lookup()
    resolved = jams.apply(
        lambda row: resolve_corridor(row, osm_name_map, osm_ref_map, osm_names, osm_name_meta, osm_ref_meta, alias_lookup),
        axis=1,
    )
    resolved_df = pd.DataFrame(resolved.tolist(), index=jams.index)
    out = pd.concat([jams, resolved_df], axis=1)
    confidence_score = {"HIGH": 1.0, "MEDIUM": 0.66, "LOW": 0.33, "UNRESOLVED": 0.0}
    out["corridor_match_confidence_score"] = out["corridor_match_confidence"].map(confidence_score).fillna(0.0)
    out["corridor_norm_waze_group"] = out["corridor_norm_waze"].replace("", "UNRESOLVED").fillna("UNRESOLVED")
    out[
        [
            "uuid",
            "street_modal",
            "city_modal",
            "route_ref",
            "road_name_candidate",
            "corridor_candidate_waze",
            "corridor_norm_waze",
            "corridor_local_name_waze",
            "corridor_group_waze",
            "road_scope_waze",
            "corridor_match_method",
            "corridor_match_confidence",
            "corridor_match_status",
            "corridor_resolution_detail",
            "osm_catalog_road_type",
            "osm_catalog_length_km",
            "osm_catalog_departments",
            "unresolved_reason",
        ]
    ].to_csv(RESULTS_DIR / "waze_jams_corridor_resolution.csv", index=False)
    return out


def categorize_speed(speed: float) -> str:
    if pd.isna(speed):
        return "SIN_DATO"
    if speed <= 2:
        return "DETENIDO"
    if speed <= 5:
        return "CASI_DETENIDO"
    if speed <= 10:
        return "MUY_LENTO"
    if speed <= 20:
        return "LENTO"
    return "MODERADO"


def stability_class(value: float) -> str:
    if value >= 0.80:
        return "HIGH"
    if value >= 0.55:
        return "MEDIUM"
    return "LOW"


def add_jam_metrics(jams: pd.DataFrame) -> pd.DataFrame:
    out = jams.copy()
    out["delay_min"] = pd.to_numeric(out["delay_max"], errors="coerce").fillna(0) / 60
    out["length_km"] = pd.to_numeric(out["length_max"], errors="coerce").fillna(0) / 1000
    out["congestion_load"] = out["delay_min"] * out["length_km"]
    out["delay_density"] = out["delay_min"] / out["length_km"].clip(lower=0.001)
    out["speed_category"] = out["speed_min"].map(categorize_speed)
    out["speed_collapse_flag"] = out["speed_min"] <= 5
    out["severe_jam_flag"] = out["level_max"] >= 4
    out["extreme_jam_flag"] = out["level_max"] == 5
    out["low_speed_component"] = 1 / out["speed_min"].clip(lower=1)

    level_norm = robust_norm(out["level_max"], upper_quantile=1.0)
    delay_norm = robust_norm(out["delay_max"])
    length_norm = robust_norm(out["length_max"])
    low_speed_norm = robust_norm(out["low_speed_component"])
    out["jam_intensity_score"] = (
        100 * (0.30 * level_norm + 0.30 * delay_norm + 0.25 * length_norm + 0.15 * low_speed_norm)
    ).round(4)

    range_components = pd.concat(
        [
            robust_norm(out["speed_range"]),
            robust_norm(out["delay_range"]),
            robust_norm(out["length_range"]),
            robust_norm(out["level_range"], upper_quantile=1.0),
        ],
        axis=1,
    )
    out["jam_estimation_stability"] = (1 - range_components.mean(axis=1)).clip(0, 1).round(4)
    out["jam_estimation_stability_class"] = out["jam_estimation_stability"].map(stability_class)
    records_norm = robust_norm(out["records_per_uuid"])
    out["congestion_reliability_proxy"] = (
        100
        * (
            0.35 * records_norm
            + 0.40 * out["jam_estimation_stability"]
            + 0.25 * out["corridor_match_confidence_score"]
        )
    ).round(4)
    out.to_csv(RESULTS_DIR / "waze_jams_unique_enriched.csv", index=False)
    return out


def build_corridor_hour_panel(jams: pd.DataFrame) -> pd.DataFrame:
    group_cols = ["corridor_norm_waze_group", "event_hour"]
    panel = jams.groupby(group_cols, dropna=False).agg(
        jams_count=("uuid", "nunique"),
        records_count=("records_per_uuid", "sum"),
        delay_total_min=("delay_min", "sum"),
        delay_avg_min=("delay_min", "mean"),
        length_total_km=("length_km", "sum"),
        length_avg_km=("length_km", "mean"),
        avg_speed_kmh=("speed_mean", "mean"),
        min_speed_kmh=("speed_min", "min"),
        level_avg=("level_mean", "mean"),
        level_max=("level_max", "max"),
        severe_jam_count=("severe_jam_flag", "sum"),
        extreme_jam_count=("extreme_jam_flag", "sum"),
        speed_collapse_count=("speed_collapse_flag", "sum"),
        congestion_load_total=("congestion_load", "sum"),
        delay_density_avg=("delay_density", "mean"),
        jam_intensity_total=("jam_intensity_score", "sum"),
        jam_intensity_avg=("jam_intensity_score", "mean"),
        estimation_stability_avg=("jam_estimation_stability", "mean"),
        high_confidence_jams=("corridor_match_confidence", lambda s: int((s == "HIGH").sum())),
        medium_confidence_jams=("corridor_match_confidence", lambda s: int((s == "MEDIUM").sum())),
        low_confidence_jams=("corridor_match_confidence", lambda s: int((s == "LOW").sum())),
        unresolved_jams=("corridor_match_status", lambda s: int((s == "UNRESOLVED").sum())),
    ).reset_index()
    panel = panel.rename(columns={"corridor_norm_waze_group": "corridor_norm_waze"})
    panel["severe_jam_rate"] = (panel["severe_jam_count"] / panel["jams_count"].clip(lower=1)).round(4)
    panel["speed_collapse_rate"] = (panel["speed_collapse_count"] / panel["jams_count"].clip(lower=1)).round(4)
    panel.to_csv(RESULTS_DIR / "waze_jams_corridor_hour.csv", index=False)
    return panel


def classify_corridor(row: pd.Series, pressure_p75: float) -> str:
    active_hours = row["active_congestion_hours"]
    pressure = row["corridor_jam_pressure_score"]
    severe_rate = row["corridor_severe_rate"]
    collapse_rate = row["corridor_speed_collapse_rate"]
    anomaly = row["jam_anomaly_score"]
    if row["corridor_norm_waze"] == "UNRESOLVED":
        return "SIN_OBSERVACION_SUFFICIENTE"
    if active_hours >= 8 and pressure >= pressure_p75 * 0.65:
        return "CONGESTION_RECURRENTE"
    if active_hours >= 4 and collapse_rate >= 0.35:
        return "BAJA_VELOCIDAD_PERSISTENTE"
    if active_hours <= 3 and (pressure >= pressure_p75 or anomaly >= 2):
        return "PICO_PUNTUAL"
    if active_hours <= 3 and severe_rate >= 0.50:
        return "CONGESTION_SEVERA_AISLADA"
    if pressure < pressure_p75 * 0.25:
        return "BAJA_PRESION_OBSERVADA"
    return "PRESION_INTERMEDIA"


def build_corridor_summary(panel: pd.DataFrame, jams: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary = panel.groupby("corridor_norm_waze", dropna=False).agg(
        jams_count_total=("jams_count", "sum"),
        records_count_total=("records_count", "sum"),
        active_congestion_hours=("event_hour", "nunique"),
        corridor_delay_burden=("delay_total_min", "sum"),
        corridor_length_burden=("length_total_km", "sum"),
        corridor_congestion_load=("congestion_load_total", "sum"),
        corridor_avg_speed=("avg_speed_kmh", "mean"),
        corridor_min_speed=("min_speed_kmh", "min"),
        severe_jam_count_total=("severe_jam_count", "sum"),
        speed_collapse_count_total=("speed_collapse_count", "sum"),
        jam_intensity_total=("jam_intensity_total", "sum"),
        estimation_stability_avg=("estimation_stability_avg", "mean"),
        high_confidence_jams=("high_confidence_jams", "sum"),
        medium_confidence_jams=("medium_confidence_jams", "sum"),
        low_confidence_jams=("low_confidence_jams", "sum"),
        unresolved_jams=("unresolved_jams", "sum"),
    ).reset_index()
    summary["corridor_congestion_recurrence"] = (summary["active_congestion_hours"] / TOTAL_HOURS).round(4)
    summary["corridor_severe_rate"] = (summary["severe_jam_count_total"] / summary["jams_count_total"].clip(lower=1)).round(4)
    summary["corridor_speed_collapse_rate"] = (
        summary["speed_collapse_count_total"] / summary["jams_count_total"].clip(lower=1)
    ).round(4)
    summary["corridor_low_speed_exposure"] = summary["corridor_speed_collapse_rate"]
    summary["unresolved_share"] = (summary["unresolved_jams"] / summary["jams_count_total"].clip(lower=1)).round(4)
    summary["corridor_match_confidence_avg"] = (
        (summary["high_confidence_jams"] * 1.0 + summary["medium_confidence_jams"] * 0.66 + summary["low_confidence_jams"] * 0.33)
        / summary["jams_count_total"].clip(lower=1)
    ).round(4)

    peak = panel.sort_values(["corridor_norm_waze", "jam_intensity_total"], ascending=[True, False]).drop_duplicates(
        "corridor_norm_waze"
    )[["corridor_norm_waze", "event_hour", "jam_intensity_total"]]
    peak = peak.rename(columns={"event_hour": "peak_congestion_hour", "jam_intensity_total": "peak_hour_intensity"})
    summary = summary.merge(peak, on="corridor_norm_waze", how="left")

    vol = panel.groupby("corridor_norm_waze")["jam_intensity_total"].std(ddof=0).reset_index(name="congestion_volatility")
    summary = summary.merge(vol, on="corridor_norm_waze", how="left")
    summary["congestion_volatility"] = summary["congestion_volatility"].fillna(0)

    pressure = (
        0.25 * robust_norm(summary["corridor_delay_burden"])
        + 0.20 * robust_norm(summary["corridor_congestion_load"])
        + 0.20 * robust_norm(summary["active_congestion_hours"], upper_quantile=1.0)
        + 0.15 * robust_norm(summary["corridor_severe_rate"], upper_quantile=1.0)
        + 0.10 * robust_norm(summary["corridor_speed_collapse_rate"], upper_quantile=1.0)
        + 0.10 * robust_norm(summary["jams_count_total"])
    )
    summary["corridor_jam_pressure_score"] = (100 * pressure).round(4)
    summary.loc[summary["corridor_norm_waze"].eq("UNRESOLVED"), "corridor_jam_pressure_score"] = 0.0

    hourly_pivot = panel.pivot_table(
        index="corridor_norm_waze", columns="event_hour", values="jam_intensity_total", aggfunc="sum", fill_value=0
    )
    for hour in range(24):
        if hour not in hourly_pivot.columns:
            hourly_pivot[hour] = 0
    hourly_pivot = hourly_pivot[sorted(hourly_pivot.columns)]
    profile = hourly_pivot.apply(lambda row: json.dumps([round(float(row[h]), 4) for h in range(24)]), axis=1)
    behavior = summary[["corridor_norm_waze", "jams_count_total", "active_congestion_hours"]].copy()
    behavior["corridor_hour_profile"] = behavior["corridor_norm_waze"].map(profile)
    behavior["jam_anomaly_score"] = behavior["corridor_norm_waze"].map(
        hourly_pivot.apply(lambda row: 0.0 if row.std(ddof=0) == 0 else float((row.max() - row.mean()) / row.std(ddof=0)), axis=1)
    ).fillna(0).round(4)
    behavior = behavior.merge(
        summary[
            [
                "corridor_norm_waze",
                "corridor_jam_pressure_score",
                "corridor_severe_rate",
                "corridor_speed_collapse_rate",
                "corridor_congestion_recurrence",
                "corridor_match_confidence_avg",
            ]
        ],
        on="corridor_norm_waze",
        how="left",
    )
    pressure_p75 = float(summary["corridor_jam_pressure_score"].quantile(0.75)) if not summary.empty else 0.0
    behavior["corridor_congestion_type"] = behavior.apply(lambda row: classify_corridor(row, pressure_p75), axis=1)
    behavior["observed_corridor_flag"] = behavior["corridor_norm_waze"].ne("UNRESOLVED")
    behavior["silent_corridor_flag"] = False
    behavior["waze_observation_coverage_jams"] = (
        100
        * (
            0.70 * (behavior["active_congestion_hours"] / TOTAL_HOURS)
            + 0.30 * behavior["corridor_match_confidence_avg"].fillna(0)
        )
    ).round(4)

    summary = summary.sort_values("corridor_jam_pressure_score", ascending=False)
    behavior = behavior.sort_values("corridor_jam_pressure_score", ascending=False)
    summary.to_csv(RESULTS_DIR / "waze_jams_corridor_summary.csv", index=False)
    behavior.to_csv(RESULTS_DIR / "waze_jams_corridor_behavior.csv", index=False)
    return summary, behavior


def build_quality_outputs(raw: pd.DataFrame, jams: pd.DataFrame, summary: pd.DataFrame) -> pd.DataFrame:
    total_raw = len(raw)
    total_unique = len(jams)
    assigned = int(jams["corridor_match_status"].eq("RESOLVED").sum())
    quality_rows = [
        ("raw_rows", total_raw, "Filas crudas del JSON."),
        ("unique_jams_uuid", total_unique, "Congestiones unicas por uuid."),
        ("exact_duplicate_rows", int(raw.duplicated().sum()), "Duplicados exactos en filas crudas."),
        ("uuid_duplicate_rows", int(total_raw - raw["uuid"].nunique()), "Filas que exceden el conteo de uuid unico."),
        ("street_empty_count", int(jams["street_norm"].eq("").sum()), "Jams sin street despues de normalizacion."),
        ("street_empty_pct", pct(int(jams["street_norm"].eq("").sum()), total_unique), "Porcentaje de jams sin street."),
        ("corridor_assigned_count", assigned, "Jams con corredor resuelto."),
        ("corridor_assigned_pct", pct(assigned, total_unique), "Porcentaje de jams con corredor resuelto."),
        ("high_confidence_count", int(jams["corridor_match_confidence"].eq("HIGH").sum()), "Jams con match HIGH."),
        ("medium_confidence_count", int(jams["corridor_match_confidence"].eq("MEDIUM").sum()), "Jams con match MEDIUM."),
        ("low_confidence_count", int(jams["corridor_match_confidence"].eq("LOW").sum()), "Jams con match LOW."),
        ("unresolved_count", int(jams["corridor_match_status"].eq("UNRESOLVED").sum()), "Jams no resueltos."),
        ("negative_delay_count", int((jams["delay_max"] < 0).sum()), "Jams con delay maximo negativo."),
        ("zero_speed_count", int((jams["speed_min"] == 0).sum()), "Jams con velocidad minima cero."),
        ("country_not_es_count", int((jams["country_modal"] != "ES").sum()), "Jams fuera del codigo ES."),
        ("low_stability_count", int(jams["jam_estimation_stability_class"].eq("LOW").sum()), "Jams con baja estabilidad interna."),
    ]
    quality = pd.DataFrame(quality_rows, columns=["metric", "value", "description"])
    quality.to_csv(RESULTS_DIR / "waze_jams_quality_diagnostics.csv", index=False)

    unresolved = jams[jams["corridor_match_status"].eq("UNRESOLVED")].copy()
    unresolved = unresolved[
        [
            "uuid",
            "event_hour",
            "city_modal",
            "street_modal",
            "startNode_modal",
            "endNode_modal",
            "route_ref",
            "unresolved_reason",
            "delay_min",
            "length_km",
            "jam_intensity_score",
        ]
    ].sort_values("jam_intensity_score", ascending=False)
    unresolved.to_csv(RESULTS_DIR / "waze_jams_unresolved_corridors.csv", index=False)

    delay_p99 = jams["delay_max"].quantile(0.99)
    length_p99 = jams["length_max"].quantile(0.99)
    intensity_p99 = jams["jam_intensity_score"].quantile(0.99)
    extreme = jams[
        (jams["delay_max"] >= delay_p99)
        | (jams["length_max"] >= length_p99)
        | (jams["jam_intensity_score"] >= intensity_p99)
        | (jams["delay_max"] < 0)
        | (jams["speed_min"] == 0)
        | (jams["jam_estimation_stability_class"] == "LOW")
    ].copy()
    extreme[
        [
            "uuid",
            "event_hour",
            "city_modal",
            "street_modal",
            "corridor_norm_waze",
            "corridor_match_confidence",
            "delay_max",
            "length_max",
            "speed_min",
            "level_max",
            "jam_intensity_score",
            "jam_estimation_stability",
            "records_per_uuid",
        ]
    ].sort_values("jam_intensity_score", ascending=False).to_csv(RESULTS_DIR / "waze_jams_extreme_cases.csv", index=False)

    return quality


def build_corridor_conflicts(jams: pd.DataFrame) -> pd.DataFrame:
    if jams.empty:
        conflicts = pd.DataFrame()
        conflicts.to_csv(RESULTS_DIR / "waze_jams_corridor_conflicts.csv", index=False)
        return conflicts

    intensity_p90 = float(jams["jam_intensity_score"].quantile(0.90))
    street_multi = (
        jams[jams["street_norm"].fillna("").ne("")]
        .groupby("street_norm")["corridor_norm_waze_group"]
        .nunique()
    )
    ambiguous_streets = set(street_multi[street_multi > 1].index)
    ref_multi = (
        jams[jams["route_ref"].fillna("").ne("")]
        .groupby("route_ref")["corridor_norm_waze_group"]
        .nunique()
    )
    ambiguous_refs = set(ref_multi[ref_multi > 1].index)

    rows: list[dict[str, Any]] = []

    def add_issue(row: pd.Series, issue_type: str, reason: str) -> None:
        rows.append(
            {
                "uuid": row.get("uuid", ""),
                "event_hour": row.get("event_hour", ""),
                "city_modal": row.get("city_modal", ""),
                "street_modal": row.get("street_modal", ""),
                "startNode_modal": row.get("startNode_modal", ""),
                "endNode_modal": row.get("endNode_modal", ""),
                "route_ref": row.get("route_ref", ""),
                "corridor_norm_waze": row.get("corridor_norm_waze_group", ""),
                "corridor_local_name_waze": row.get("corridor_local_name_waze", ""),
                "corridor_group_waze": row.get("corridor_group_waze", ""),
                "road_scope_waze": row.get("road_scope_waze", ""),
                "corridor_match_method": row.get("corridor_match_method", ""),
                "corridor_match_confidence": row.get("corridor_match_confidence", ""),
                "corridor_resolution_detail": row.get("corridor_resolution_detail", ""),
                "issue_type": issue_type,
                "issue_reason": reason,
                "jam_intensity_score": row.get("jam_intensity_score", ""),
                "delay_min": row.get("delay_min", ""),
                "length_km": row.get("length_km", ""),
                "speed_min": row.get("speed_min", ""),
                "level_max": row.get("level_max", ""),
            }
        )

    for _, row in jams.iterrows():
        corridor = row.get("corridor_norm_waze_group", "")
        method = row.get("corridor_match_method", "")
        confidence = row.get("corridor_match_confidence", "")
        intensity = float(row.get("jam_intensity_score", 0) or 0)
        street_norm = row.get("street_norm", "")
        route_ref = row.get("route_ref", "")

        if corridor == "UNRESOLVED":
            add_issue(row, "UNRESOLVED", "No se pudo asociar el jam a corredor.")
            if intensity >= intensity_p90:
                add_issue(row, "UNRESOLVED_HIGH_IMPACT", "Jam no resuelto con intensidad en percentil 90 o superior.")
            continue

        if method == "TEXT_STREET":
            add_issue(row, "TEXT_STREET_NOT_IN_OSM", "El corredor se deriva del texto de calle sin coincidencia exacta OSM.")
        if method == "NODE_CONTEXT":
            add_issue(row, "NODE_CONTEXT_USED_AS_CORRIDOR", "El corredor se infiere de startNode/endNode como ultimo recurso.")
        if confidence == "LOW" and intensity >= intensity_p90:
            add_issue(row, "LOW_CONFIDENCE_HIGH_IMPACT", "Jam de alto impacto con asociacion de baja confianza.")
        if is_route_ref_like(corridor):
            add_issue(row, "REFERENCE_WITHOUT_FUNCTIONAL_NAME", "La asociacion queda como referencia OSM sin nombre funcional.")
        if street_norm in ambiguous_streets:
            add_issue(row, "SAME_STREET_MULTIPLE_CORRIDORS", "El mismo texto normalizado aparece asociado a multiples corredores.")
        if route_ref and route_ref in ambiguous_refs:
            add_issue(row, "SAME_REF_MULTIPLE_CORRIDORS", "La misma referencia vial aparece asociada a multiples corredores.")

    conflicts = pd.DataFrame(rows)
    if not conflicts.empty:
        conflicts = conflicts.sort_values(["issue_type", "jam_intensity_score"], ascending=[True, False])
    conflicts.to_csv(RESULTS_DIR / "waze_jams_corridor_conflicts.csv", index=False)
    return conflicts


def top_tables(jams: pd.DataFrame, summary: pd.DataFrame) -> None:
    summary.sort_values("corridor_delay_burden", ascending=False).head(30).to_csv(
        RESULTS_DIR / "top_corredores_por_delay.csv", index=False
    )
    summary.sort_values("corridor_congestion_load", ascending=False).head(30).to_csv(
        RESULTS_DIR / "top_corredores_por_congestion_load.csv", index=False
    )
    summary.sort_values("corridor_jam_pressure_score", ascending=False).head(30).to_csv(
        RESULTS_DIR / "top_corredores_por_pressure_score.csv", index=False
    )
    jams.sort_values("jam_intensity_score", ascending=False).head(50).to_csv(
        RESULTS_DIR / "top_jams_por_intensidad.csv", index=False
    )
    jams.sort_values("delay_density", ascending=False).head(50).to_csv(
        RESULTS_DIR / "top_jams_por_delay_density.csv", index=False
    )


def save_barh(df: pd.DataFrame, x: str, y: str, title: str, path: Path, xlabel: str) -> None:
    plot_df = df[[x, y]].dropna().head(15).iloc[::-1]
    fig, ax = plt.subplots(figsize=(11, 7))
    ax.barh(plot_df[y], plot_df[x], color="#2f80ed")
    ax.set_title(title, loc="left", fontweight="bold")
    ax.set_xlabel(xlabel)
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def generate_figures(jams: pd.DataFrame, panel: pd.DataFrame, summary: pd.DataFrame) -> None:
    hourly = jams.groupby("event_hour").agg(
        jams=("uuid", "nunique"),
        delay_total=("delay_min", "sum"),
        congestion_load=("congestion_load", "sum"),
        avg_speed=("speed_mean", "mean"),
    ).reindex(range(24), fill_value=0)

    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.plot(hourly.index, hourly["jams"], marker="o", color="#2563eb")
    ax.set_title("Jams unicos por hora", loc="left", fontweight="bold")
    ax.set_xlabel("Hora local")
    ax.set_ylabel("Jams unicos")
    ax.set_xticks(range(24))
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig_serie_horaria_jams.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.plot(hourly.index, hourly["delay_total"], marker="o", color="#dc2626")
    ax.set_title("Demora acumulada por hora", loc="left", fontweight="bold")
    ax.set_xlabel("Hora local")
    ax.set_ylabel("Minutos de demora")
    ax.set_xticks(range(24))
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig_serie_horaria_delay.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.plot(hourly.index, hourly["congestion_load"], marker="o", color="#7c3aed")
    ax.set_title("Carga de congestion por hora", loc="left", fontweight="bold")
    ax.set_xlabel("Hora local")
    ax.set_ylabel("delay_min * length_km")
    ax.set_xticks(range(24))
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig_serie_horaria_congestion_load.png", dpi=180)
    plt.close(fig)

    save_barh(
        summary.sort_values("corridor_delay_burden", ascending=False),
        "corridor_delay_burden",
        "corridor_norm_waze",
        "Top corredores por demora acumulada",
        RESULTS_DIR / "fig_top_corredores_delay.png",
        "Minutos de demora",
    )
    save_barh(
        summary.sort_values("corridor_jam_pressure_score", ascending=False),
        "corridor_jam_pressure_score",
        "corridor_norm_waze",
        "Top corredores por score de presion jam",
        RESULTS_DIR / "fig_top_corredores_pressure.png",
        "Score 0-100",
    )

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    jams["level_max"].value_counts().sort_index().plot(kind="bar", ax=axes[0], color="#f59e0b")
    axes[0].set_title("Distribucion de level max")
    axes[0].set_xlabel("Level")
    axes[0].set_ylabel("Jams")
    jams["speed_category"].value_counts().reindex(["DETENIDO", "CASI_DETENIDO", "MUY_LENTO", "LENTO", "MODERADO", "SIN_DATO"]).dropna().plot(
        kind="bar", ax=axes[1], color="#10b981"
    )
    axes[1].set_title("Categoria de velocidad minima")
    axes[1].set_xlabel("Categoria")
    axes[1].tick_params(axis="x", rotation=35)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig_distribucion_level_speed.png", dpi=180)
    plt.close(fig)

    top_corridors = summary.head(20)["corridor_norm_waze"].tolist()
    matrix = panel[panel["corridor_norm_waze"].isin(top_corridors)].pivot_table(
        index="corridor_norm_waze", columns="event_hour", values="jam_intensity_total", aggfunc="sum", fill_value=0
    )
    for hour in range(24):
        if hour not in matrix.columns:
            matrix[hour] = 0
    matrix = matrix[range(24)]
    fig, ax = plt.subplots(figsize=(13, 8))
    im = ax.imshow(matrix.values, aspect="auto", cmap="magma")
    ax.set_title("Matriz corredor-hora por intensidad jam", loc="left", fontweight="bold")
    ax.set_xlabel("Hora local")
    ax.set_ylabel("Corredor")
    ax.set_xticks(range(24))
    ax.set_yticks(range(len(matrix.index)))
    ax.set_yticklabels(matrix.index)
    fig.colorbar(im, ax=ax, label="Intensidad total")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "fig_heatmap_corredor_hora.png", dpi=180)
    plt.close(fig)


def prepare_map_layers(summary: pd.DataFrame) -> None:
    layer = summary[summary["corridor_norm_waze"].ne("UNRESOLVED")].copy()
    layer["corridor_norm_key"] = layer["corridor_norm_waze"].map(compact_text)
    layer[
        [
            "corridor_norm_waze",
            "corridor_norm_key",
            "jams_count_total",
            "corridor_delay_burden",
            "corridor_congestion_load",
            "corridor_speed_collapse_rate",
            "active_congestion_hours",
            "corridor_jam_pressure_score",
            "corridor_match_confidence_avg",
        ]
    ].to_csv(RESULTS_DIR / "waze_jams_corridor_layers.csv", index=False)

    if not OSM_NATIONAL_SEGMENTS_PATH.exists() or layer.empty:
        return
    metric_cols = [
        "corridor_norm_key",
        "jams_count_total",
        "corridor_delay_burden",
        "corridor_congestion_load",
        "corridor_speed_collapse_rate",
        "active_congestion_hours",
        "corridor_jam_pressure_score",
    ]
    metrics = layer[metric_cols].drop_duplicates("corridor_norm_key")
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
    segments["corridor_norm_key"] = segments["road_key_norm"].map(compact_text)
    enriched = segments.merge(metrics, on="corridor_norm_key", how="inner")
    enriched.to_csv(RESULTS_DIR / "waze_jams_osm_segments_enriched.csv", index=False)


def write_diagnostics_report(
    meta: dict[str, Any],
    raw: pd.DataFrame,
    jams: pd.DataFrame,
    summary: pd.DataFrame,
    quality: pd.DataFrame,
    conflicts: pd.DataFrame,
) -> None:
    lines: list[str] = []
    lines.append("Resultados del analisis Waze Jams")
    lines.append("=" * 40)
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
        "La fila cruda no se interpreta como vehiculo ni como evento independiente. "
        "El uuid se usa como unidad base de congestion; las variaciones internas se usan para medir estabilidad."
    )
    lines.append("")
    lines.append("Resumen general")
    lines.append("---------------")
    lines.append(f"- Filas crudas: {len(raw):,}")
    lines.append(f"- Jams unicos por uuid: {len(jams):,}")
    lines.append(f"- Filas excedentes respecto a uuid: {len(raw) - raw['uuid'].nunique():,}")
    datetime_local = pd.to_datetime(jams["datetime_local"], errors="coerce")
    lines.append(f"- Rango local: {datetime_local.min()} a {datetime_local.max()}")
    lines.append(f"- Corredores resueltos: {int(jams['corridor_match_status'].eq('RESOLVED').sum()):,} ({pct(int(jams['corridor_match_status'].eq('RESOLVED').sum()), len(jams))}%)")
    lines.append(f"- No resueltos: {int(jams['corridor_match_status'].eq('UNRESOLVED').sum()):,} ({pct(int(jams['corridor_match_status'].eq('UNRESOLVED').sum()), len(jams))}%)")
    lines.append("")
    lines.append("Horas criticas")
    lines.append("--------------")
    hourly = jams.groupby("event_hour").agg(
        jams=("uuid", "nunique"),
        delay_total=("delay_min", "sum"),
        pressure=("jam_intensity_score", "sum"),
    ).reset_index()
    for _, row in hourly.sort_values("pressure", ascending=False).head(8).iterrows():
        lines.append(
            f"- Hora {int(row['event_hour']):02d}: {int(row['jams']):,} jams, "
            f"{row['delay_total']:,.1f} min demora, intensidad {row['pressure']:,.1f}"
        )
    lines.append("")
    lines.append("Top corredores por score")
    lines.append("------------------------")
    ranked_corridors = summary[summary["corridor_norm_waze"].ne("UNRESOLVED")].copy()
    for _, row in ranked_corridors.head(15).iterrows():
        lines.append(
            f"- {row['corridor_norm_waze']}: score {row['corridor_jam_pressure_score']:.2f}, "
            f"jams {int(row['jams_count_total']):,}, demora {row['corridor_delay_burden']:,.1f} min, "
            f"horas activas {int(row['active_congestion_hours'])}"
        )
    lines.append("")
    lines.append("Calidad")
    lines.append("-------")
    for _, row in quality.iterrows():
        lines.append(f"- {row['metric']}: {row['value']} ({row['description']})")
    if not conflicts.empty:
        lines.append("")
        lines.append("Conflictos de asociacion vial")
        lines.append("------------------------------")
        for issue, count in conflicts["issue_type"].value_counts().head(12).items():
            lines.append(f"- {issue}: {count:,}")
    lines.append("")
    lines.append("Limitaciones")
    lines.append("------------")
    lines.append("- Jams no trae geometria directa; no se crean puntos falsos.")
    lines.append("- records_per_uuid no mide vehiculos ni duracion.")
    lines.append("- La asociacion a corredor depende de texto, alias y catalogo OSM cuando esta disponible.")
    lines.append("- Un dia de datos permite exploracion operacional, no patrones estructurales definitivos.")
    lines.append("")
    lines.append("Potencial analitico")
    lines.append("-------------------")
    lines.append(
        "El archivo permite construir una senal operacional de congestion por corredor-hora: "
        "demora acumulada, carga de congestion, baja velocidad, recurrencia y score de presion jam. "
        "Esta senal queda lista para compararse posteriormente con Waze alerts y noticias."
    )
    (RESULTS_DIR / "resultados_waze_jams.txt").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_dirs()
    raw, meta = load_jams_json()
    raw = add_temporal_fields(raw)
    field_diag = write_field_diagnostics(raw)
    write_initial_distributions(raw)
    unique = aggregate_unique_jams(raw)
    unique = add_text_fields(unique)
    unique = add_corridor_resolution(unique)
    unique = add_jam_metrics(unique)
    panel = build_corridor_hour_panel(unique)
    summary, behavior = build_corridor_summary(panel, unique)
    quality = build_quality_outputs(raw, unique, summary)
    conflicts = build_corridor_conflicts(unique)
    top_tables(unique, summary)
    generate_figures(unique, panel, summary)
    prepare_map_layers(summary)
    write_diagnostics_report(meta, raw, unique, summary, quality, conflicts)
    print(f"Resultados Waze jams generados en: {RESULTS_DIR}")
    print(f"Jams unicos: {len(unique):,}")
    print(f"Corredores en resumen: {len(summary):,}")


if __name__ == "__main__":
    main()
