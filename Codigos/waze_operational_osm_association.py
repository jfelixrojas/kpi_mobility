#!/usr/bin/env python3
"""
Asociacion probabilistica Waze jams -> OSM sin usar texto vial.

Objetivo metodologico:
- Usar la huella operacional del jam: longitud, demora, velocidad, nivel y hora.
- Usar atributos estructurales OSM: tipo de via, longitud, ref, carriles, velocidad y cobertura territorial.
- Comparar contra la asociacion textual existente solo como referencia de evaluacion.

Esta asociacion no sustituye el match textual ni un match espacial; produce candidatos OSM
por compatibilidad operacional cuando el jam no trae geometria directa.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
JAMS_PATH = ROOT / "Results" / "Waze" / "Jams" / "waze_jams_unique_enriched.csv"
OSM_CATALOG_PATH = ROOT / "Data" / "Processed" / "osm_roads_nacional" / "osm_road_catalog.csv"
RESULTS_DIR = ROOT / "Results" / "Waze" / "Jams"

TOP_K = 5
EPS = 1e-9


ROAD_TYPE_HIERARCHY = {
    "NACIONAL_ESTRUCTURANTE": 1.00,
    "ARTERIAL_PRINCIPAL": 0.86,
    "ARTERIAL_SECUNDARIA": 0.72,
    "COLECTORA": 0.56,
    "NO_CLASIFICADA_OSM": 0.45,
    "LOCAL_RESIDENCIAL": 0.28,
    "SERVICIO_ACCESO": 0.18,
}

GENERIC_ROAD_KEYS = {
    "",
    "calle",
    "avenida",
    "boulevard",
    "bulevar",
    "pasaje",
    "calle principal",
    "avenida principal",
    "pasaje s n",
    "senda",
    "senda s n",
    "carretera",
    "camino",
    "calle antigua",
}

DEPARTMENT_ALIASES = {
    "AHUACHAPAN": ["ahuachapan", "atiquizaya", "apaneca", "tacuba", "turin", "san francisco menendez", "cara sucia", "la hachadura"],
    "CABAÑAS": ["cabanas", "sensuntepeque", "ilobasco", "victoria", "dolores", "jutiapa", "tejutla"],
    "CHALATENANGO": ["chalatenango", "nueva concepcion", "la palma", "la reina", "tejutla", "agua caliente"],
    "CUSCATLÁN": ["cuscatlan", "cojutepeque", "san rafael cedros", "suchitoto", "el carmen", "san pedro perulapan"],
    "LA LIBERTAD": [
        "la libertad",
        "santa tecla",
        "antiguo cuscatlan",
        "colon",
        "lourdes",
        "quezaltepeque",
        "san juan opico",
        "sitio del nino",
        "ciudad arce",
        "nuevo cuscatlan",
        "san jose villanueva",
        "zaragoza",
        "merliot",
        "talnique",
        "comasagua",
        "tamanique",
    ],
    "LA PAZ": ["la paz", "zacatecoluca", "olocuilta", "santiago nonualco", "san pedro masahuat", "cuyultitan", "el rosario"],
    "LA UNION": ["la union", "santa rosa de lima", "conchagua", "pasaquina", "anamoros", "el sauce", "intipuca"],
    "MORAZÁN": ["morazan", "san francisco gotera", "jocoro", "el divisadero", "sociedad", "corinto", "osicala"],
    "SAN MIGUEL": [
        "san miguel",
        "moncagua",
        "chapeltique",
        "lolotique",
        "ciudad barrios",
        "chinameca",
        "quela",
        "quelepa",
        "san jorge",
        "el transito",
        "sesori",
    ],
    "SAN SALVADOR": [
        "san salvador",
        "soyapango",
        "apopa",
        "mejicanos",
        "ciudad delgado",
        "san marcos",
        "san martin",
        "ilopango",
        "cuscatancingo",
        "planes de renderos",
        "san bartolo",
        "ayutuxtepeque",
        "nejapa",
        "santo tomas",
        "aguilares",
        "tonacatepeque",
        "guazapa",
        "panchimalco",
        "rosario de mora",
        "santiago texacuangos",
        "el paisnal",
        "colonia escalon",
        "san benito",
        "flor blanca",
        "san jacinto",
        "zacamil",
    ],
    "SAN VICENTE": ["san vicente", "apastepeque", "san ildefonso", "san lorenzo", "tecoluca", "verapaz", "guadalupe"],
    "SANTA ANA": ["santa ana", "chalchuapa", "el congo", "metapan", "coatepeque", "candelaria de la frontera"],
    "SONSONATE": ["sonsonate", "sonzacate", "acajutla", "izalco", "juayua", "nahuizalco", "san antonio del monte", "armenía", "armenia"],
    "USULUTÁN": [
        "usulutan",
        "jiquilisco",
        "santiago de maria",
        "santa maria",
        "concepcion batres",
        "mercedes umana",
        "el triunfo",
        "ereguayquin",
        "santa elena",
        "ozatlan",
        "jucuapa",
    ],
}


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


def title_case(value: Any) -> str:
    text = compact_text(value)
    if not text:
        return ""
    lower_words = {"a", "al", "de", "del", "la", "las", "los", "y", "el"}
    words = []
    for idx, token in enumerate(text.split()):
        if idx > 0 and token in lower_words:
            words.append(token)
        elif token in {"ca", "rn", "lib", "sam"}:
            words.append(token.upper())
        else:
            words.append(token.capitalize())
    return " ".join(words)


def pct(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round(float(numerator) / float(denominator) * 100, 2)


def robust_norm(values: pd.Series, upper_quantile: float = 0.95) -> pd.Series:
    x = pd.to_numeric(values, errors="coerce").fillna(0.0).astype(float)
    if x.empty:
        return x
    lower = float(x.min())
    upper = float(x.quantile(upper_quantile))
    if upper <= lower:
        upper = float(x.max())
    if upper <= lower:
        return pd.Series(0.0, index=x.index)
    return ((x.clip(lower=lower, upper=upper) - lower) / (upper - lower)).clip(0, 1)


def parse_numeric_max(value: Any) -> float:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return 0.0
    nums = re.findall(r"\d+(?:\.\d+)?", str(value))
    if not nums:
        return 0.0
    return max(float(num) for num in nums)


def first_nonempty(values: pd.Series) -> str:
    for value in values:
        if value is not None and not pd.isna(value) and str(value).strip():
            text = str(value).strip()
            if compact_text(text) != "nan":
                return text
    return ""


def infer_department(city: Any) -> str:
    text = compact_text(city)
    if not text:
        return ""
    matches: list[tuple[int, str]] = []
    for department, aliases in DEPARTMENT_ALIASES.items():
        for alias in aliases:
            alias_norm = compact_text(alias)
            if alias_norm and alias_norm in text:
                matches.append((len(alias_norm), department))
    if not matches:
        return ""
    return sorted(matches, reverse=True)[0][1]


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    if not JAMS_PATH.exists():
        raise FileNotFoundError(f"No existe {JAMS_PATH}. Ejecute primero make run-waze-jams-analysis.")
    if not OSM_CATALOG_PATH.exists():
        raise FileNotFoundError(f"No existe {OSM_CATALOG_PATH}. Ejecute primero la descarga OSM nacional.")
    return (
        pd.read_csv(JAMS_PATH, low_memory=False),
        pd.read_csv(OSM_CATALOG_PATH, low_memory=False),
    )


def representative_name(row: pd.Series) -> str:
    for col in ["representative_name", "road_key_norm"]:
        value = row.get(col, "")
        if value is not None and not pd.isna(value) and str(value).strip():
            text = str(value).strip()
            if compact_text(text) != "nan":
                return text
    return title_case(row.get("road_key_norm", ""))


def build_osm_candidates(catalog: pd.DataFrame) -> pd.DataFrame:
    out = catalog.copy()
    for col in [
        "road_key_norm",
        "representative_name",
        "refs",
        "predominant_road_type",
        "source_department",
        "length_km",
        "segment_count",
        "lanes_values",
        "maxspeed_values",
    ]:
        if col not in out.columns:
            out[col] = ""

    out["candidate_key"] = out["road_key_norm"].map(compact_text)
    out = out[out["candidate_key"].ne("")]
    out = out[~out["candidate_key"].str.startswith("osm way")]
    out = out[~out["candidate_key"].isin(GENERIC_ROAD_KEYS)]
    out["length_km"] = pd.to_numeric(out["length_km"], errors="coerce").fillna(0.0)
    out = out[out["length_km"] > 0.03]
    out["representative_clean"] = out.apply(representative_name, axis=1)
    out["hierarchy_score_raw"] = out["predominant_road_type"].map(ROAD_TYPE_HIERARCHY).fillna(0.45)
    out["has_ref"] = out["refs"].fillna("").astype(str).str.strip().ne("").astype(float)
    out["lanes_max_row"] = out["lanes_values"].map(parse_numeric_max)
    out["maxspeed_max_row"] = out["maxspeed_values"].map(parse_numeric_max)

    rows = []
    for key, group in out.groupby("candidate_key", dropna=False):
        group = group.sort_values(["length_km", "hierarchy_score_raw"], ascending=False)
        departments = sorted(set(group["source_department"].dropna().astype(str)))
        road_types = group["predominant_road_type"].dropna().astype(str)
        road_type = road_types.mode().iloc[0] if not road_types.empty else ""
        rows.append(
            {
                "osm_candidate_key": key,
                "osm_candidate_name": first_nonempty(group["representative_clean"]) or title_case(key),
                "osm_departments": ";".join(departments),
                "osm_department_count": len(departments),
                "osm_length_km": float(group["length_km"].sum()),
                "osm_segment_count": int(pd.to_numeric(group["segment_count"], errors="coerce").fillna(0).sum()),
                "osm_hierarchy_score": float(group["hierarchy_score_raw"].max()),
                "osm_has_ref": float(group["has_ref"].max()),
                "osm_lanes_max": float(group["lanes_max_row"].max()),
                "osm_maxspeed_max": float(group["maxspeed_max_row"].max()),
                "osm_predominant_road_type": road_type,
            }
        )
    candidates = pd.DataFrame(rows)
    candidates["osm_length_norm"] = robust_norm(candidates["osm_length_km"])
    candidates["osm_lanes_norm"] = robust_norm(candidates["osm_lanes_max"], upper_quantile=0.99)
    candidates["osm_maxspeed_norm"] = robust_norm(candidates["osm_maxspeed_max"], upper_quantile=0.99)
    candidates["osm_national_presence_norm"] = (candidates["osm_department_count"] / 14.0).clip(0, 1)
    candidates["osm_structural_prior"] = (
        0.35 * candidates["osm_hierarchy_score"]
        + 0.20 * candidates["osm_length_norm"]
        + 0.15 * candidates["osm_has_ref"]
        + 0.15 * candidates["osm_lanes_norm"]
        + 0.10 * candidates["osm_maxspeed_norm"]
        + 0.05 * candidates["osm_national_presence_norm"]
    ).round(6)
    candidates = candidates.sort_values("osm_structural_prior", ascending=False).reset_index(drop=True)
    candidates.to_csv(RESULTS_DIR / "waze_operational_osm_candidates_catalog.csv", index=False)
    return candidates


def expected_hierarchy_from_jam(jams: pd.DataFrame) -> pd.Series:
    length_norm = robust_norm(jams["length_km"])
    delay_norm = robust_norm(jams["delay_min"])
    level_norm = ((pd.to_numeric(jams["level_max"], errors="coerce").fillna(1) - 1) / 4.0).clip(0, 1)
    speed = pd.to_numeric(jams["speed_min"], errors="coerce").fillna(50)
    low_speed_norm = (1 - (speed / 45.0).clip(0, 1)).clip(0, 1)
    return (0.35 * length_norm + 0.25 * delay_norm + 0.25 * level_norm + 0.15 * low_speed_norm).clip(0, 1)


def expected_speed_context(jams: pd.DataFrame) -> pd.Series:
    level_norm = ((pd.to_numeric(jams["level_max"], errors="coerce").fillna(1) - 1) / 4.0).clip(0, 1)
    length_norm = robust_norm(jams["length_km"])
    delay_norm = robust_norm(jams["delay_min"])
    return (0.45 * length_norm + 0.35 * level_norm + 0.20 * delay_norm).clip(0, 1)


def classify_confidence(score: float, margin: float, territory_known: bool = False) -> str:
    threshold_bonus = 0.03 if territory_known else 0.0
    if score >= 0.78 + threshold_bonus and margin >= 0.045:
        return "HIGH"
    if score >= 0.66 and margin >= 0.020:
        return "MEDIUM"
    return "LOW"


def score_candidates_for_jam(
    jam: pd.Series,
    candidates: pd.DataFrame,
    arrays: dict[str, np.ndarray],
    model: str,
) -> pd.DataFrame:
    jam_length = max(float(jam.get("length_km", 0) or 0), 0.03)
    expected_hierarchy = float(jam.get("expected_osm_hierarchy", 0) or 0)
    expected_speed = float(jam.get("expected_osm_speed_context", 0) or 0)
    inferred_department = str(jam.get("inferred_department", "") or "")

    osm_length = arrays["length"]
    osm_hierarchy = arrays["hierarchy"]
    osm_speed = arrays["speed"]
    osm_prior = arrays["prior"]

    length_capacity = np.minimum(1.0, (osm_length + 0.05) / (jam_length * 0.75 + 0.05))
    length_shape = np.exp(-np.abs(np.log1p(osm_length) - np.log1p(jam_length)) / 2.2)
    length_fit = 0.72 * length_capacity + 0.28 * length_shape
    hierarchy_fit = 1.0 - np.abs(osm_hierarchy - expected_hierarchy)
    speed_fit = 1.0 - np.abs(osm_speed - expected_speed)

    if model == "contextual":
        if inferred_department:
            dept_token = f"|{inferred_department}|"
            territory_fit = np.array(
                [
                    1.0 if dept_token in dept else 0.45 if count >= 4 else 0.15
                    for dept, count in zip(arrays["department_tokens"], arrays["department_count"])
                ],
                dtype=float,
            )
        else:
            territory_fit = np.full(len(candidates), 0.45, dtype=float)
        score = (
            0.30 * hierarchy_fit
            + 0.25 * length_fit
            + 0.20 * osm_prior
            + 0.15 * territory_fit
            + 0.10 * speed_fit
        )
    else:
        territory_fit = np.full(len(candidates), np.nan, dtype=float)
        score = 0.35 * hierarchy_fit + 0.30 * length_fit + 0.25 * osm_prior + 0.10 * speed_fit

    # Avoid candidates that are structurally irrelevant when the jam is operationally intense.
    if expected_hierarchy >= 0.70:
        score = np.where(osm_hierarchy < 0.28, score - 0.10, score)

    top_idx = np.argpartition(score, -TOP_K)[-TOP_K:]
    top_idx = top_idx[np.argsort(score[top_idx])[::-1]]
    top_scores = score[top_idx]
    top2 = float(top_scores[1]) if len(top_scores) > 1 else 0.0

    rows = []
    for rank, idx in enumerate(top_idx, start=1):
        rows.append(
            {
                "uuid": jam["uuid"],
                "model": model,
                "candidate_rank": rank,
                "operational_candidate": candidates.iloc[idx]["osm_candidate_name"],
                "operational_candidate_key": candidates.iloc[idx]["osm_candidate_key"],
                "operational_candidate_departments": candidates.iloc[idx]["osm_departments"],
                "operational_candidate_road_type": candidates.iloc[idx]["osm_predominant_road_type"],
                "operational_candidate_length_km": round(float(candidates.iloc[idx]["osm_length_km"]), 4),
                "operational_candidate_structural_prior": round(float(candidates.iloc[idx]["osm_structural_prior"]), 4),
                "operational_match_score": round(float(score[idx]), 6),
                "operational_score_margin_top2": round(float(top_scores[0] - top2), 6),
                "operational_match_confidence": classify_confidence(
                    float(top_scores[0]),
                    float(top_scores[0] - top2),
                    territory_known=bool(inferred_department and model == "contextual"),
                )
                if rank == 1
                else "",
                "jam_expected_osm_hierarchy": round(expected_hierarchy, 4),
                "jam_length_km": round(jam_length, 4),
                "jam_delay_min": round(float(jam.get("delay_min", 0) or 0), 4),
                "jam_speed_min": round(float(jam.get("speed_min", 0) or 0), 4),
                "jam_level_max": float(jam.get("level_max", 0) or 0),
                "jam_city": jam.get("city_modal", ""),
                "jam_inferred_department": inferred_department,
            }
        )
    return pd.DataFrame(rows)


def build_operational_association(jams: pd.DataFrame, candidates: pd.DataFrame) -> pd.DataFrame:
    out = jams.copy()
    out["inferred_department"] = out["city_modal"].map(infer_department)
    out["expected_osm_hierarchy"] = expected_hierarchy_from_jam(out)
    out["expected_osm_speed_context"] = expected_speed_context(out)

    candidates = candidates.reset_index(drop=True)
    arrays = {
        "length": candidates["osm_length_km"].to_numpy(dtype=float),
        "hierarchy": candidates["osm_hierarchy_score"].to_numpy(dtype=float),
        "speed": candidates["osm_maxspeed_norm"].to_numpy(dtype=float),
        "prior": candidates["osm_structural_prior"].to_numpy(dtype=float),
        "department_tokens": ("|" + candidates["osm_departments"].fillna("").astype(str) + "|").to_numpy(dtype=object),
        "department_count": candidates["osm_department_count"].to_numpy(dtype=float),
    }

    records = []
    compare_cols = [
        "uuid",
        "corridor_norm_waze",
        "corridor_norm_waze_group",
        "corridor_match_method",
        "corridor_match_confidence",
        "corridor_match_status",
        "event_hour",
        "time_period",
        "city_modal",
        "street_modal",
        "delay_min",
        "length_km",
        "speed_min",
        "level_max",
        "jam_intensity_score",
        "inferred_department",
        "expected_osm_hierarchy",
    ]
    base = out[[col for col in compare_cols if col in out.columns]].copy()
    base["text_corridor_key"] = base["corridor_norm_waze"].map(compact_text)

    for _, jam in out.iterrows():
        for model in ["global", "contextual"]:
            records.append(score_candidates_for_jam(jam, candidates, arrays, model))

    topk = pd.concat(records, ignore_index=True)
    topk.to_csv(RESULTS_DIR / "waze_operational_osm_top5_candidates.csv", index=False)

    top1 = topk[topk["candidate_rank"].eq(1)].copy()
    top1 = top1.merge(base, on="uuid", how="left")
    top1["text_corridor_key"] = top1["text_corridor_key"].fillna("")
    top1["top1_matches_text"] = (
        top1["operational_candidate_key"].eq(top1["text_corridor_key"])
        & top1["text_corridor_key"].ne("")
        & top1["corridor_norm_waze_group"].ne("UNRESOLVED")
    )

    contains = []
    for (uuid, model), group in topk.groupby(["uuid", "model"]):
        text_key = base.loc[base["uuid"].eq(uuid), "text_corridor_key"]
        text_value = text_key.iloc[0] if not text_key.empty else ""
        keys = set(group["operational_candidate_key"].tolist())
        contains.append(
            {
                "uuid": uuid,
                "model": model,
                "top3_contains_text": bool(text_value and text_value in set(group[group["candidate_rank"] <= 3]["operational_candidate_key"])),
                "top5_contains_text": bool(text_value and text_value in keys),
            }
        )
    contains_df = pd.DataFrame(contains)
    comparison = top1.merge(contains_df, on=["uuid", "model"], how="left")
    comparison.to_csv(RESULTS_DIR / "waze_operational_vs_text_comparison.csv", index=False)
    return comparison


def summarize_comparison(comparison: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    eval_df = comparison[
        comparison["corridor_norm_waze_group"].fillna("UNRESOLVED").ne("UNRESOLVED")
        & comparison["text_corridor_key"].fillna("").ne("")
    ].copy()
    by_model = eval_df.groupby("model").agg(
        evaluated_jams=("uuid", "nunique"),
        top1_exact_matches=("top1_matches_text", "sum"),
        top3_contains_text=("top3_contains_text", "sum"),
        top5_contains_text=("top5_contains_text", "sum"),
        avg_operational_score=("operational_match_score", "mean"),
        avg_expected_hierarchy=("expected_osm_hierarchy", "mean"),
        inferred_department_coverage=("inferred_department", lambda s: int(s.fillna("").ne("").sum())),
    ).reset_index()
    by_model["top1_exact_match_pct"] = by_model.apply(lambda r: pct(r["top1_exact_matches"], r["evaluated_jams"]), axis=1)
    by_model["top3_contains_text_pct"] = by_model.apply(lambda r: pct(r["top3_contains_text"], r["evaluated_jams"]), axis=1)
    by_model["top5_contains_text_pct"] = by_model.apply(lambda r: pct(r["top5_contains_text"], r["evaluated_jams"]), axis=1)
    by_model["inferred_department_coverage_pct"] = by_model.apply(
        lambda r: pct(r["inferred_department_coverage"], r["evaluated_jams"]), axis=1
    )
    by_model.to_csv(RESULTS_DIR / "waze_operational_vs_text_summary.csv", index=False)

    by_method = eval_df.groupby(["model", "corridor_match_method", "corridor_match_confidence"]).agg(
        evaluated_jams=("uuid", "nunique"),
        top1_exact_matches=("top1_matches_text", "sum"),
        top5_contains_text=("top5_contains_text", "sum"),
        avg_operational_score=("operational_match_score", "mean"),
    ).reset_index()
    by_method["top1_exact_match_pct"] = by_method.apply(lambda r: pct(r["top1_exact_matches"], r["evaluated_jams"]), axis=1)
    by_method["top5_contains_text_pct"] = by_method.apply(lambda r: pct(r["top5_contains_text"], r["evaluated_jams"]), axis=1)
    by_method.to_csv(RESULTS_DIR / "waze_operational_vs_text_by_method.csv", index=False)

    predicted = comparison.groupby(["model", "operational_candidate", "operational_candidate_key"]).agg(
        predicted_jams=("uuid", "nunique"),
        predicted_delay_min=("delay_min", "sum"),
        predicted_intensity=("jam_intensity_score", "sum"),
        avg_operational_score=("operational_match_score", "mean"),
        avg_expected_hierarchy=("expected_osm_hierarchy", "mean"),
        high_operational_confidence=("operational_match_confidence", lambda s: int((s == "HIGH").sum())),
        medium_operational_confidence=("operational_match_confidence", lambda s: int((s == "MEDIUM").sum())),
        low_operational_confidence=("operational_match_confidence", lambda s: int((s == "LOW").sum())),
    ).reset_index()
    predicted = predicted.sort_values(["model", "predicted_intensity"], ascending=[True, False])
    predicted.to_csv(RESULTS_DIR / "waze_operational_osm_predicted_corridors.csv", index=False)

    text_rank = comparison[
        comparison["corridor_norm_waze_group"].fillna("UNRESOLVED").ne("UNRESOLVED")
    ].drop_duplicates(["uuid", "model"])
    text_rank = text_rank.groupby(["model", "corridor_norm_waze_group"]).agg(
        text_jams=("uuid", "nunique"),
        text_delay_min=("delay_min", "sum"),
        text_intensity=("jam_intensity_score", "sum"),
    ).reset_index()
    overlap_rows = []
    for model in sorted(comparison["model"].unique()):
        text_top = set(text_rank[text_rank["model"].eq(model)].sort_values("text_intensity", ascending=False).head(20)["corridor_norm_waze_group"].map(compact_text))
        pred_top = set(predicted[predicted["model"].eq(model)].sort_values("predicted_intensity", ascending=False).head(20)["operational_candidate_key"])
        overlap_rows.append(
            {
                "model": model,
                "top20_text_operational_overlap_count": len(text_top.intersection(pred_top)),
                "top20_text_operational_overlap_pct": pct(len(text_top.intersection(pred_top)), 20),
            }
        )
    overlap = pd.DataFrame(overlap_rows)
    overlap.to_csv(RESULTS_DIR / "waze_operational_text_top20_overlap.csv", index=False)
    return by_model, by_method, predicted


def write_report(
    jams: pd.DataFrame,
    candidates: pd.DataFrame,
    comparison: pd.DataFrame,
    by_model: pd.DataFrame,
    by_method: pd.DataFrame,
    predicted: pd.DataFrame,
) -> None:
    lines: list[str] = []
    lines.append("Experimento: asociacion operacional probabilistica Waze jams -> OSM")
    lines.append("=" * 72)
    lines.append("")
    lines.append("Proposito")
    lines.append("---------")
    lines.append(
        "Se construyo una ruta alternativa a la asociacion textual. La prediccion no usa street, "
        "startNode, endNode, ref ni nombre vial del jam. Usa longitud, demora, velocidad, level, "
        "hora y atributos estructurales OSM. La asociacion textual existente se usa solo para comparacion."
    )
    lines.append("")
    lines.append("Insumos")
    lines.append("-------")
    lines.append(f"- Jams unicos evaluados: {len(jams):,}")
    lines.append(f"- Candidatos OSM estructurales: {len(candidates):,}")
    lines.append(
        f"- Cobertura de departamento inferido desde city_modal: "
        f"{int(jams['city_modal'].map(infer_department).ne('').sum()):,} "
        f"({pct(int(jams['city_modal'].map(infer_department).ne('').sum()), len(jams))}%)"
    )
    lines.append("")
    lines.append("Modelos evaluados")
    lines.append("-----------------")
    lines.append("- global: no usa territorio; compara cada jam contra todos los corredores OSM candidatos.")
    lines.append("- contextual: usa solo departamento inferido desde city_modal para ponderar candidatos territoriales.")
    lines.append("")
    lines.append("Comparacion contra asociacion textual")
    lines.append("-------------------------------------")
    for _, row in by_model.iterrows():
        lines.append(
            f"- {row['model']}: evaluados {int(row['evaluated_jams']):,}; "
            f"top1 exacto {row['top1_exact_match_pct']:.2f}%; "
            f"textual dentro del top3 {row['top3_contains_text_pct']:.2f}%; "
            f"textual dentro del top5 {row['top5_contains_text_pct']:.2f}%; "
            f"score operacional promedio {row['avg_operational_score']:.3f}."
        )
    lines.append("")
    lines.append("Lectura por tipo de match textual")
    lines.append("---------------------------------")
    method_view = by_method.sort_values(["model", "evaluated_jams"], ascending=[True, False]).head(18)
    for _, row in method_view.iterrows():
        lines.append(
            f"- {row['model']} / {row['corridor_match_method']} / {row['corridor_match_confidence']}: "
            f"{int(row['evaluated_jams']):,} jams, top1 {row['top1_exact_match_pct']:.2f}%, "
            f"top5 {row['top5_contains_text_pct']:.2f}%."
        )
    lines.append("")
    lines.append("Confianza operacional")
    lines.append("---------------------")
    confidence = comparison.groupby(["model", "operational_match_confidence"]).size().reset_index(name="jams")
    for _, row in confidence.iterrows():
        total_model = int(comparison["model"].eq(row["model"]).sum())
        lines.append(
            f"- {row['model']} / {row['operational_match_confidence']}: "
            f"{int(row['jams']):,} jams ({pct(row['jams'], total_model)}%)."
        )
    lines.append("")
    lines.append("Solapamiento de rankings")
    lines.append("------------------------")
    text_rank = comparison[
        comparison["corridor_norm_waze_group"].fillna("UNRESOLVED").ne("UNRESOLVED")
    ].drop_duplicates(["uuid", "model"])
    text_rank = text_rank.groupby(["model", "corridor_norm_waze_group"]).agg(
        text_intensity=("jam_intensity_score", "sum"),
    ).reset_index()
    for model in sorted(comparison["model"].unique()):
        text_top = set(
            text_rank[text_rank["model"].eq(model)]
            .sort_values("text_intensity", ascending=False)
            .head(20)["corridor_norm_waze_group"]
            .map(compact_text)
        )
        pred_top = set(
            predicted[predicted["model"].eq(model)]
            .sort_values("predicted_intensity", ascending=False)
            .head(20)["operational_candidate_key"]
        )
        overlap_count = len(text_top.intersection(pred_top))
        lines.append(
            f"- {model}: {overlap_count}/20 corredores compartidos entre top textual y top operacional "
            f"({pct(overlap_count, 20)}%)."
        )
    lines.append("")
    lines.append("Top corredores inferidos operacionalmente")
    lines.append("-----------------------------------------")
    for model in ["contextual", "global"]:
        lines.append(f"{model}:")
        top_pred = predicted[predicted["model"].eq(model)].head(10)
        for _, row in top_pred.iterrows():
            lines.append(
                f"- {row['operational_candidate']}: {int(row['predicted_jams']):,} jams, "
                f"demora {row['predicted_delay_min']:,.1f} min, intensidad {row['predicted_intensity']:,.1f}, "
                f"score {row['avg_operational_score']:.3f}."
            )
    lines.append("")
    lines.append("Analisis objetivo")
    lines.append("-----------------")
    lines.append(
        "El experimento demuestra que la huella operacional por si sola no alcanza para asignar una via exacta "
        "con alta precision evento a evento. Esto es esperado: Waze jams no trae geometria directa y muchos "
        "corredores OSM pueden ser operacionalmente compatibles con una misma combinacion de longitud, demora y velocidad."
    )
    lines.append(
        "La ruta si aporta valor como mecanismo de priorizacion probabilistica: reduce el universo OSM a candidatos "
        "funcionalmente plausibles, permite medir incertidumbre y puede servir cuando no existe texto vial util."
    )
    lines.append(
        "El modelo contextual debe interpretarse como mejor candidato para implementacion, porque agrega territorio "
        "sin depender del nombre de la via. Aun asi, no debe reemplazar el match textual cuando este existe con ref/name "
        "alto ni un match espacial si aparece geometria."
    )
    lines.append("")
    lines.append("Decision recomendada")
    lines.append("--------------------")
    lines.append(
        "Usar la asociacion operacional como capa secundaria de respaldo: 1) para jams sin texto vial resoluble; "
        "2) para asignar tipo funcional probable de via; 3) para comparar si los corredores textuales tienen sentido "
        "operacional; y 4) para construir capas de presion agregada donde la unidad no sea el punto exacto sino la "
        "compatibilidad corredor-congestion."
    )
    lines.append("")
    lines.append("Archivos generados")
    lines.append("------------------")
    for name in [
        "waze_operational_osm_candidates_catalog.csv",
        "waze_operational_osm_top5_candidates.csv",
        "waze_operational_vs_text_comparison.csv",
        "waze_operational_vs_text_summary.csv",
        "waze_operational_vs_text_by_method.csv",
        "waze_operational_osm_predicted_corridors.csv",
        "waze_operational_text_top20_overlap.csv",
    ]:
        lines.append(f"- Results/Waze/Jams/{name}")
    (RESULTS_DIR / "waze_operational_osm_report.txt").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    jams, catalog = load_inputs()
    candidates = build_osm_candidates(catalog)
    comparison = build_operational_association(jams, candidates)
    by_model, by_method, predicted = summarize_comparison(comparison)
    write_report(jams, candidates, comparison, by_model, by_method, predicted)
    print(f"Experimento operacional Waze->OSM generado en: {RESULTS_DIR}")
    print(f"Jams evaluados: {len(jams):,}")
    print(f"Candidatos OSM: {len(candidates):,}")
    print(by_model.to_string(index=False))


if __name__ == "__main__":
    main()
