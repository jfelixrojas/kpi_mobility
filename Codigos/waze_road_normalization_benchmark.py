#!/usr/bin/env python3
"""
Benchmark local de normalizacion vial Waze/OSM.

Mide cuanto aporta cada capa de normalizacion:
- texto crudo;
- texto compacto;
- normalizacion vial con abreviaturas;
- tabla de alias;
- catalogo OSM;
- resolucion final del pipeline.
"""

from __future__ import annotations

import math
import re
import unicodedata
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "Results" / "Waze" / "Jams"
JAMS_PATH = RESULTS_DIR / "waze_jams_unique_enriched.csv"
CONFLICTS_PATH = RESULTS_DIR / "waze_jams_corridor_conflicts.csv"
OSM_CATALOG_PATH = ROOT / "Data" / "Processed" / "osm_roads_nacional" / "osm_road_catalog.csv"
ALIASES_PATH = ROOT / "Data" / "Processed" / "waze_osm_aliases.csv"

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


def normalize_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    text = str(value).strip().lower()
    text = "".join(
        char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char)
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


def pct(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round(float(numerator) / float(denominator) * 100, 2)


def load_alias_keys() -> set[str]:
    if not ALIASES_PATH.exists():
        return set()
    aliases = pd.read_csv(ALIASES_PATH, low_memory=False)
    if "raw_value_norm" in aliases.columns:
        return {normalize_road_text(v) for v in aliases["raw_value_norm"].dropna() if normalize_road_text(v)}
    return {normalize_road_text(v) for v in aliases["raw_value"].dropna() if normalize_road_text(v)}


def load_osm_keys() -> tuple[set[str], set[str]]:
    if not OSM_CATALOG_PATH.exists():
        return set(), set()
    catalog = pd.read_csv(OSM_CATALOG_PATH, low_memory=False)
    keys_compact = set()
    keys_road = set()
    for col in ["road_key_norm", "representative_name", "names", "refs"]:
        if col not in catalog.columns:
            continue
        for value in catalog[col].dropna():
            for part in re.split(r";|,", str(value)):
                c = compact_text(part)
                r = normalize_road_text(part)
                if c and not c.startswith("osm way"):
                    keys_compact.add(c)
                if r and not r.startswith("osm way"):
                    keys_road.add(r)
    return keys_compact, keys_road


def contains_alias(text: str, alias_keys: set[str]) -> bool:
    if not text:
        return False
    return any(key and key in text for key in alias_keys)


def write_benchmark() -> None:
    if not JAMS_PATH.exists():
        raise FileNotFoundError(f"No existe {JAMS_PATH}. Ejecute primero make run-waze-jams-analysis.")
    jams = pd.read_csv(JAMS_PATH, low_memory=False)
    total = len(jams)
    osm_compact, osm_road = load_osm_keys()
    alias_keys = load_alias_keys()

    street_raw = jams["street_modal"].fillna("").astype(str)
    compact = street_raw.map(compact_text)
    road_norm = street_raw.map(normalize_road_text)
    combined = (
        jams["street_modal"].fillna("").astype(str)
        + " "
        + jams["startNode_modal"].fillna("").astype(str)
        + " "
        + jams["endNode_modal"].fillna("").astype(str)
    ).map(normalize_road_text)

    rows = [
        {
            "stage": "raw_street",
            "description": "Texto original en street_modal.",
            "records_with_signal": int(street_raw.str.strip().ne("").sum()),
            "coverage_pct": pct(int(street_raw.str.strip().ne("").sum()), total),
            "unique_values": int(street_raw[street_raw.str.strip().ne("")].nunique()),
            "osm_exact_matches": "",
            "alias_matches": "",
            "final_resolved": "",
            "high_confidence": "",
        },
        {
            "stage": "compact_text",
            "description": "Minusculas, sin acentos, sin signos y espacios normalizados.",
            "records_with_signal": int(compact.ne("").sum()),
            "coverage_pct": pct(int(compact.ne("").sum()), total),
            "unique_values": int(compact[compact.ne("")].nunique()),
            "osm_exact_matches": int(compact.isin(osm_compact).sum()),
            "alias_matches": int(compact.map(lambda x: contains_alias(x, alias_keys)).sum()),
            "final_resolved": "",
            "high_confidence": "",
        },
        {
            "stage": "road_normalized",
            "description": "Normalizacion vial con Av/Avenida, Blvd/Bulevar, Carr/Carretera.",
            "records_with_signal": int(road_norm.ne("").sum()),
            "coverage_pct": pct(int(road_norm.ne("").sum()), total),
            "unique_values": int(road_norm[road_norm.ne("")].nunique()),
            "osm_exact_matches": int(road_norm.isin(osm_road).sum()),
            "alias_matches": int(road_norm.map(lambda x: contains_alias(x, alias_keys)).sum()),
            "final_resolved": "",
            "high_confidence": "",
        },
        {
            "stage": "combined_text_alias",
            "description": "street + startNode + endNode contra tabla de alias.",
            "records_with_signal": int(combined.ne("").sum()),
            "coverage_pct": pct(int(combined.ne("").sum()), total),
            "unique_values": int(combined[combined.ne("")].nunique()),
            "osm_exact_matches": "",
            "alias_matches": int(combined.map(lambda x: contains_alias(x, alias_keys)).sum()),
            "final_resolved": "",
            "high_confidence": "",
        },
        {
            "stage": "final_pipeline",
            "description": "Resolucion final corridor_norm_waze.",
            "records_with_signal": int(jams["corridor_match_status"].eq("RESOLVED").sum()),
            "coverage_pct": pct(int(jams["corridor_match_status"].eq("RESOLVED").sum()), total),
            "unique_values": int(jams["corridor_norm_waze_group"].nunique()),
            "osm_exact_matches": int(jams["corridor_match_method"].isin(["OSM_NAME", "OSM_REF"]).sum()),
            "alias_matches": int(jams["corridor_match_method"].isin(["TEXT_ALIAS", "TEXT_ALIAS_TABLE"]).sum()),
            "final_resolved": int(jams["corridor_match_status"].eq("RESOLVED").sum()),
            "high_confidence": int(jams["corridor_match_confidence"].eq("HIGH").sum()),
        },
    ]
    benchmark = pd.DataFrame(rows)
    benchmark.to_csv(RESULTS_DIR / "waze_road_normalization_benchmark.csv", index=False)

    remaining_rows = []
    if CONFLICTS_PATH.exists():
        conflicts = pd.read_csv(CONFLICTS_PATH, low_memory=False)
        focus = conflicts[
            conflicts["issue_type"].isin(
                [
                    "TEXT_STREET_NOT_IN_OSM",
                    "REFERENCE_WITHOUT_FUNCTIONAL_NAME",
                    "LOW_CONFIDENCE_HIGH_IMPACT",
                    "UNRESOLVED_HIGH_IMPACT",
                ]
            )
        ].copy()
        if not focus.empty:
            focus["street_norm_candidate"] = focus["street_modal"].map(normalize_road_text)
            grouped = focus.groupby(["issue_type", "street_norm_candidate", "corridor_norm_waze"], dropna=False).agg(
                cases=("uuid", "nunique"),
                cities=("city_modal", lambda s: "; ".join(s.dropna().astype(str).value_counts().head(5).index)),
                max_intensity=("jam_intensity_score", "max"),
                avg_delay_min=("delay_min", "mean"),
                avg_length_km=("length_km", "mean"),
                examples=("street_modal", lambda s: " | ".join(s.dropna().astype(str).value_counts().head(3).index)),
            ).reset_index()
            remaining_rows = grouped.sort_values(["cases", "max_intensity"], ascending=[False, False]).to_dict("records")
    remaining = pd.DataFrame(remaining_rows)
    remaining.to_csv(RESULTS_DIR / "waze_road_normalization_remaining_terms.csv", index=False)

    lines: list[str] = []
    lines.append("Benchmark local de normalizacion vial Waze/OSM")
    lines.append("=" * 55)
    lines.append("")
    lines.append("Proposito")
    lines.append("---------")
    lines.append(
        "Medir como cambia la cobertura y unicidad de nombres viales al pasar de texto crudo a normalizacion, "
        "alias, catalogo OSM y corridor_norm_waze final."
    )
    lines.append("")
    lines.append("Resultados por etapa")
    lines.append("--------------------")
    for _, row in benchmark.iterrows():
        lines.append(
            f"- {row['stage']}: senal {row['records_with_signal']:,} ({row['coverage_pct']}%), "
            f"valores unicos {row['unique_values']}, OSM exactos {row['osm_exact_matches']}, "
            f"alias {row['alias_matches']}, resueltos finales {row['final_resolved']}, "
            f"alta confianza {row['high_confidence']}."
        )
    lines.append("")
    lines.append("Lectura")
    lines.append("-------")
    lines.append(
        "El problema principal no es solamente falta de datos, sino falta de un vocabulario vial comun. "
        "Waze, OSM y noticias pueden nombrar la misma via de formas diferentes: abreviaturas, refs, nombres locales, "
        "sentidos, nodos, colonias o nombres funcionales."
    )
    lines.append(
        "La estrategia recomendada es mantener una llave canonica del sistema: corridor_norm_waze/corridor_norm, "
        "conservando siempre el texto original y el nombre local como trazabilidad."
    )
    lines.append("")
    lines.append("Canal comun propuesto")
    lines.append("---------------------")
    lines.append("- raw_road_text: texto original de la fuente.")
    lines.append("- road_text_norm: texto limpio y sin variantes ortograficas.")
    lines.append("- route_ref_norm: referencia vial normalizada cuando exista.")
    lines.append("- local_osm_name: nombre local OSM o Waze conservado.")
    lines.append("- corridor_norm: corredor funcional canonico del sistema.")
    lines.append("- road_scope: nacional/regional, departamental, urbano, local o nodo.")
    lines.append("- match_method y confidence: trazabilidad de como se resolvio.")
    lines.append("")
    lines.append("Archivos")
    lines.append("--------")
    lines.append("- Results/Waze/Jams/waze_road_normalization_benchmark.csv")
    lines.append("- Results/Waze/Jams/waze_road_normalization_remaining_terms.csv")
    (RESULTS_DIR / "waze_road_normalization_benchmark.txt").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    write_benchmark()
    print(f"Benchmark de normalizacion generado en {RESULTS_DIR}")


if __name__ == "__main__":
    main()
