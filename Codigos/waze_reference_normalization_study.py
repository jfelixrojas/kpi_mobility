#!/usr/bin/env python3
"""
Estudio focalizado de referencias Waze/OSM sin nombre funcional.

El objetivo no es resolver forzadamente las referencias, sino clasificar si
pueden normalizarse como corredor funcional, si deben conservarse como
referencia tecnica o si requieren validacion externa.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from waze_jams_analysis_pipeline import (
    RESULTS_DIR,
    ROOT,
    compact_text,
    extract_route_refs,
    format_route_ref,
    normalize_route_ref,
)


JAMS_PATH = RESULTS_DIR / "waze_jams_unique_enriched.csv"
OSM_CATALOG_PATH = ROOT / "Data" / "Processed" / "osm_roads_nacional" / "osm_road_catalog.csv"
OSM_SEGMENTS_PATH = ROOT / "Data" / "Processed" / "osm_roads_nacional" / "osm_road_segments.csv"

TARGET_REFS = {
    "rn 10": {
        "display_ref": "RN 10",
        "reference_context": "Waze la ubica principalmente en El Congo, Santa Ana e Izalco.",
        "candidate_corridor_norm": "RN 10 - El Congo / Izalco",
        "candidate_group": "NACIONAL_REGIONAL",
        "candidate_scope": "CORREDOR_ESTRUCTURANTE",
        "preliminary_decision": "SEMI_CURADA_MEDIA",
        "decision_reason": "No aparece en el catalogo OSM nacional disponible, pero Waze muestra una referencia consistente y concentrada territorialmente.",
    },
    "rn 17": {
        "display_ref": "RN 17",
        "reference_context": "Waze y OSM la ubican en San Miguel / El Delirio.",
        "candidate_corridor_norm": "RN 17 - Carretera El Delirio",
        "candidate_group": "NACIONAL_REGIONAL",
        "candidate_scope": "CORREDOR_ESTRUCTURANTE",
        "preliminary_decision": "SEMI_CURADA_ALTA",
        "decision_reason": "OSM contiene la referencia RN 17, pero sin nombre funcional. El contexto territorial permite proponer una etiqueta funcional trazable.",
    },
    "san 16": {
        "display_ref": "SAN 16",
        "reference_context": "Waze la ubica en Chalchuapa, El Coco y Jerez.",
        "candidate_corridor_norm": "SAN 16 - Chalchuapa / La Magdalena / El Coco",
        "candidate_group": "DEPARTAMENTAL_LOCAL",
        "candidate_scope": "REFERENCIA_DEPARTAMENTAL",
        "preliminary_decision": "SEMI_CURADA_ALTA",
        "decision_reason": "No aparece en el catalogo OSM nacional disponible, pero Waze muestra concentracion clara y existe contexto institucional sobre SAN 16N en Chalchuapa.",
    },
    "rn 12": {
        "display_ref": "RN 12",
        "reference_context": "Waze la ubica en Juayua, Nahuizalco, Salcoatitan y San Jose La Majada.",
        "candidate_corridor_norm": "Ruta a Los Naranjos",
        "candidate_group": "NACIONAL_REGIONAL",
        "candidate_scope": "CORREDOR_ESTRUCTURANTE",
        "preliminary_decision": "SEMI_CURADA_ALTA",
        "decision_reason": "OSM contiene tramos RN 12/RN 12W asociados a Ruta a Los Naranjos y Carretera a Ahuachapan; requiere decidir si RN 12 y RN 12W se consolidan.",
    },
    "san 24": {
        "display_ref": "SAN 24",
        "reference_context": "Waze la ubica en El Congo, Santa Ana y Coatepeque.",
        "candidate_corridor_norm": "SAN 24 - El Congo / Santa Ana",
        "candidate_group": "DEPARTAMENTAL_LOCAL",
        "candidate_scope": "REFERENCIA_DEPARTAMENTAL",
        "preliminary_decision": "SEMI_CURADA_MEDIA",
        "decision_reason": "No aparece en el catalogo OSM nacional disponible. La concentracion Waze permite una etiqueta operativa, pero requiere validacion antes de consolidar nombre funcional.",
    },
}


JAMS_COLUMNS = [
    "uuid",
    "event_hour",
    "time_period",
    "city_modal",
    "street_modal",
    "startNode_modal",
    "endNode_modal",
    "route_ref",
    "road_text_combined",
    "corridor_norm_waze",
    "corridor_local_name_waze",
    "corridor_group_waze",
    "road_scope_waze",
    "corridor_match_method",
    "corridor_match_confidence",
    "corridor_resolution_detail",
    "delay_min",
    "length_km",
    "congestion_load",
    "delay_density",
    "jam_intensity_score",
    "level_max",
    "speed_min",
    "severe_jam_flag",
    "speed_collapse_flag",
]


def join_top(series: pd.Series, limit: int = 8) -> str:
    cleaned = series.fillna("").astype(str).str.strip()
    cleaned = cleaned[cleaned.ne("")]
    if cleaned.empty:
        return ""
    counts = cleaned.value_counts().head(limit)
    return "; ".join(f"{idx} ({int(val)})" for idx, val in counts.items())


def contains_ref(series: pd.Series, ref_norm: str) -> pd.Series:
    escaped = re.escape(ref_norm)
    compact_ref = ref_norm.replace(" ", "")
    normalized = series.fillna("").astype(str).map(normalize_route_ref)
    compacted = normalized.str.replace(" ", "", regex=False)
    return (
        normalized.str.contains(rf"(?:^|;|\b){escaped}(?:;|\b|$)", regex=True)
        | compacted.str.contains(compact_ref, regex=False)
    )


def waze_ref_mask(jams: pd.DataFrame, ref_norm: str) -> pd.Series:
    return (
        contains_ref(jams["route_ref"], ref_norm)
        | contains_ref(jams["street_modal"], ref_norm)
        | contains_ref(jams["road_text_combined"], ref_norm)
    )


def ref_family(value: str) -> tuple[str, str, str]:
    ref = normalize_route_ref(value)
    match = re.match(r"^([a-z]+)\s+([0-9]{1,3})([a-z]?)$", ref)
    if not match:
        return "", "", ""
    return match.group(1), match.group(2), match.group(3)


def refs_from_row(row: pd.Series, cols: list[str]) -> set[str]:
    refs: set[str] = set()
    for col in cols:
        if col not in row.index:
            continue
        value = row.get(col)
        refs.update(extract_route_refs(value))
    return refs


def ref_relation(refs: set[str], ref_norm: str) -> str:
    target_prefix, target_number, target_suffix = ref_family(ref_norm)
    if not target_prefix:
        return "NO_REF"
    if ref_norm in refs:
        return "EXACT"
    for candidate in refs:
        prefix, number, suffix = ref_family(candidate)
        if prefix == target_prefix and number == target_number and suffix != target_suffix:
            return "VARIANT"
    return "NO_REF"


def osm_ref_masks(df: pd.DataFrame, ref_norm: str) -> tuple[pd.Series, pd.Series, pd.Series]:
    candidate_cols = [
        col
        for col in ["road_key_norm", "refs", "ref", "ref_norm", "names", "alt_names", "official_names"]
        if col in df.columns
    ]
    if not candidate_cols:
        empty = pd.Series(False, index=df.index)
        return empty, empty, empty
    relations = df.apply(lambda row: ref_relation(refs_from_row(row, candidate_cols), ref_norm), axis=1)
    exact = relations.eq("EXACT")
    variant = relations.eq("VARIANT")
    return exact | variant, exact, variant


def summarize_osm_catalog(catalog: pd.DataFrame, segments: pd.DataFrame, ref_norm: str) -> dict[str, Any]:
    cat_mask, cat_exact, cat_variant = osm_ref_masks(catalog, ref_norm)
    seg_mask, seg_exact, seg_variant = osm_ref_masks(segments, ref_norm)
    cat = catalog[cat_mask].copy()
    seg = segments[seg_mask].copy()
    names = []
    refs = []
    alt_names = []
    official_names = []
    for col, target in [
        ("representative_name", names),
        ("names", names),
        ("name", names),
        ("refs", refs),
        ("ref", refs),
        ("alt_names", alt_names),
        ("alt_name", alt_names),
        ("official_names", official_names),
        ("official_name", official_names),
    ]:
        source = cat if col in cat.columns else seg if col in seg.columns else None
        if source is None:
            continue
        for value in source[col].dropna().astype(str):
            for part in re.split(r";|\|", value):
                part = part.strip()
                if part:
                    target.append(part)

    def uniq(values: list[str], limit: int = 10) -> str:
        seen: list[str] = []
        for value in values:
            if value and value not in seen:
                seen.append(value)
        return "; ".join(seen[:limit])

    return {
        "osm_catalog_rows": int(len(cat)),
        "osm_segment_rows": int(len(seg)),
        "osm_exact_catalog_rows": int(cat_exact.sum()),
        "osm_variant_catalog_rows": int(cat_variant.sum()),
        "osm_exact_segment_rows": int(seg_exact.sum()),
        "osm_variant_segment_rows": int(seg_variant.sum()),
        "osm_ref_relation": "EXACT"
        if int(cat_exact.sum() + seg_exact.sum()) > 0
        else "VARIANT"
        if int(cat_variant.sum() + seg_variant.sum()) > 0
        else "NO_REF",
        "osm_departments": join_top(
            pd.concat(
                [
                    cat.get("source_department", pd.Series(dtype=str)),
                    seg.get("source_department", pd.Series(dtype=str)),
                ],
                ignore_index=True,
            ),
            limit=8,
        ),
        "osm_length_km": round(float(seg.get("length_m", pd.Series(dtype=float)).fillna(0).sum()) / 1000, 3)
        if "length_m" in seg
        else round(float(cat.get("length_km", pd.Series(dtype=float)).fillna(0).sum()), 3),
        "osm_names": uniq(names),
        "osm_refs": uniq(refs),
        "osm_alt_names": uniq(alt_names),
        "osm_official_names": uniq(official_names),
        "osm_highways": join_top(
            pd.concat(
                [
                    cat.get("predominant_highway", pd.Series(dtype=str)),
                    seg.get("highway", pd.Series(dtype=str)),
                ],
                ignore_index=True,
            ),
            limit=8,
        ),
        "osm_road_types": join_top(cat.get("predominant_road_type", pd.Series(dtype=str)), limit=8)
        if "predominant_road_type" in cat
        else "",
    }


def summarize_waze(jams: pd.DataFrame, ref_norm: str) -> tuple[dict[str, Any], pd.DataFrame]:
    target = jams[waze_ref_mask(jams, ref_norm)].copy()
    if target.empty:
        return {
            "waze_jams": 0,
            "active_hours": 0,
            "waze_top_hour": "",
            "waze_delay_min": 0.0,
            "waze_length_km": 0.0,
            "waze_congestion_load": 0.0,
            "waze_intensity": 0.0,
            "waze_severe_rate": 0.0,
            "waze_speed_collapse_rate": 0.0,
            "waze_avg_speed_min": 0.0,
            "waze_top_cities": "",
            "waze_top_streets": "",
            "waze_top_start_nodes": "",
            "waze_top_end_nodes": "",
            "waze_existing_corridors": "",
            "waze_match_methods": "",
            "waze_confidence": "",
        }, target

    hour_counts = target["event_hour"].dropna().astype(int).value_counts()
    top_hour = str(int(hour_counts.index[0])) if not hour_counts.empty else ""
    return {
        "waze_jams": int(len(target)),
        "active_hours": int(target["event_hour"].nunique(dropna=True)),
        "waze_top_hour": top_hour,
        "waze_delay_min": round(float(target["delay_min"].fillna(0).sum()), 3),
        "waze_length_km": round(float(target["length_km"].fillna(0).sum()), 3),
        "waze_congestion_load": round(float(target["congestion_load"].fillna(0).sum()), 3),
        "waze_intensity": round(float(target["jam_intensity_score"].fillna(0).sum()), 3),
        "waze_severe_rate": round(float(target["severe_jam_flag"].fillna(False).mean() * 100), 2),
        "waze_speed_collapse_rate": round(float(target["speed_collapse_flag"].fillna(False).mean() * 100), 2),
        "waze_avg_speed_min": round(float(target["speed_min"].fillna(0).mean()), 3),
        "waze_top_cities": join_top(target["city_modal"], limit=8),
        "waze_top_streets": join_top(target["street_modal"], limit=8),
        "waze_top_start_nodes": join_top(target["startNode_modal"], limit=8),
        "waze_top_end_nodes": join_top(target["endNode_modal"], limit=8),
        "waze_existing_corridors": join_top(target["corridor_norm_waze"], limit=8),
        "waze_match_methods": join_top(target["corridor_match_method"], limit=8),
        "waze_confidence": join_top(target["corridor_match_confidence"], limit=8),
    }, target


def decision_from_evidence(row: dict[str, Any]) -> tuple[str, str]:
    has_osm = row["osm_catalog_rows"] > 0 or row["osm_segment_rows"] > 0
    has_osm_name = bool(str(row["osm_names"]).strip() or str(row["osm_alt_names"]).strip() or str(row["osm_official_names"]).strip())
    osm_name_text = compact_text(" ".join(str(row.get(col, "")) for col in ["osm_names", "osm_alt_names", "osm_official_names"]))
    local_node_terms = ["redonel", "redondel", "rotonda", "roundabout"]
    has_only_node_name = bool(osm_name_text) and any(term in osm_name_text for term in local_node_terms)
    has_functional_osm_name = has_osm_name and not has_only_node_name
    has_waze = row["waze_jams"] > 0
    relation = row.get("osm_ref_relation", "NO_REF")

    if relation == "EXACT" and has_functional_osm_name and has_waze:
        return "NORMALIZABLE_SEMI_AUTOMATICO", "OSM aporta nombre o alias; Waze aporta ocurrencia y territorio."
    if relation == "EXACT" and has_osm and has_waze:
        return "NORMALIZABLE_CON_ALIAS_CURADO", "OSM aporta referencia exacta, pero no nombre funcional suficiente; se requiere alias canonico trazable."
    if relation == "VARIANT" and has_functional_osm_name and has_waze:
        return (
            "NORMALIZABLE_POR_FAMILIA_REF_CON_VALIDACION",
            "OSM aporta una variante de la referencia, no la referencia exacta; se puede proponer alias, pero requiere validacion.",
        )
    if relation == "VARIANT" and has_osm and has_waze:
        return (
            "FAMILIA_REF_SIN_NOMBRE_FUNCIONAL",
            "OSM confirma una familia de referencia, pero no aporta nombre funcional suficiente.",
        )
    if has_waze and row["waze_jams"] >= 20:
        return "NORMALIZABLE_SOLO_CON_VALIDACION", "Waze aporta senal consistente, pero el catalogo OSM disponible no confirma nombre/ref."
    if has_waze:
        return "CONSERVAR_REF_TECNICA", "La senal Waze existe, pero es insuficiente para crear nombre funcional sin validacion."
    return "SIN_EVIDENCIA_LOCAL", "No hay evidencia suficiente en Waze/OSM local."


def alias_candidates(study: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in study.iterrows():
        ref_norm = row["ref_norm"]
        meta = TARGET_REFS[ref_norm]
        decision = row["normalization_decision"]
        if decision in {"SIN_EVIDENCIA_LOCAL", "CONSERVAR_REF_TECNICA"}:
            continue
        rows.append(
            {
                "raw_value": meta["display_ref"],
                "raw_value_norm": ref_norm,
                "source_type": "REFERENCE_CURATED_STUDY",
                "corridor_norm": meta["candidate_corridor_norm"],
                "corridor_group": meta["candidate_group"],
                "road_scope": meta["candidate_scope"],
                "priority": 88 if "ALTA" in meta["preliminary_decision"] else 75,
                "notes": f"Candidate from reference normalization study; decision={decision}",
                "apply_now": "NO",
            }
        )
        rows.append(
            {
                "raw_value": meta["display_ref"].replace(" ", "-"),
                "raw_value_norm": ref_norm,
                "source_type": "REFERENCE_CURATED_STUDY",
                "corridor_norm": meta["candidate_corridor_norm"],
                "corridor_group": meta["candidate_group"],
                "road_scope": meta["candidate_scope"],
                "priority": 88 if "ALTA" in meta["preliminary_decision"] else 75,
                "notes": f"Hyphen variant from reference normalization study; decision={decision}",
                "apply_now": "NO",
            }
        )
    return pd.DataFrame(rows)


def write_report(study: pd.DataFrame, alias_df: pd.DataFrame) -> None:
    lines: list[str] = []
    lines.append("Estudio de normalizacion de referencias Waze/OSM")
    lines.append("=" * 56)
    lines.append("")
    lines.append("Proposito")
    lines.append("---------")
    lines.append(
        "Analizar referencias que aparecen como corredor tecnico o sin nombre funcional en Waze Jams: "
        "RN 10, RN 17, SAN 16, RN 12 y SAN 24."
    )
    lines.append(
        "El objetivo es decidir si pueden transformarse en corridor_norm_waze canonico, si deben conservarse "
        "como referencia tecnica o si requieren validacion externa."
    )
    lines.append("")
    lines.append("Criterio metodologico")
    lines.append("---------------------")
    lines.append("- No toda referencia debe convertirse automaticamente en nombre funcional.")
    lines.append("- La normalizacion requiere evidencia: Waze consistente, OSM con ref/name/alt_name u otra fuente institucional.")
    lines.append("- Si hay homonimia posible, se prioriza el contexto territorial observado en el dataset.")
    lines.append("- El resultado propuesto debe conservar trazabilidad: ref original, texto Waze, nombre OSM, decision y confianza.")
    lines.append("")
    lines.append("Resumen por referencia")
    lines.append("----------------------")
    for _, row in study.iterrows():
        lines.append(f"- {row['display_ref']}: {int(row['waze_jams'])} jams, {row['waze_delay_min']:.1f} min demora, "
                     f"{row['waze_intensity']:.1f} intensidad, OSM catalogo {int(row['osm_catalog_rows'])}, "
                     f"OSM segmentos {int(row['osm_segment_rows'])}.")
        lines.append(f"  Decision: {row['normalization_decision']}.")
        lines.append(
            f"  Relacion OSM-ref: {row['osm_ref_relation']} "
            f"(exact catalog/seg={int(row['osm_exact_catalog_rows'])}/{int(row['osm_exact_segment_rows'])}, "
            f"variant catalog/seg={int(row['osm_variant_catalog_rows'])}/{int(row['osm_variant_segment_rows'])})."
        )
        lines.append(f"  Candidato: {row['candidate_corridor_norm']}.")
        lines.append(f"  Ciudades Waze: {row['waze_top_cities'] or 'sin informacion'}.")
        lines.append(f"  Nombres OSM: {row['osm_names'] or 'sin nombre OSM'}. Refs OSM: {row['osm_refs'] or 'sin ref OSM'}")
        lines.append(f"  Lectura: {row['normalization_reason']}")
    lines.append("")
    lines.append("Hallazgos principales")
    lines.append("---------------------")
    lines.append(
        "1. RN 17 no debe interpretarse como ruta de bus San Salvador-Panchimalco en este dataset: "
        "la evidencia Waze/OSM la ubica en San Miguel/El Delirio."
    )
    lines.append(
        "2. RN 12 presenta una diferencia importante entre el texto Waze RN-12 y OSM RN 12/RN 12W; "
        "el nombre funcional mas defendible con la evidencia OSM es Ruta a Los Naranjos, pero debe conservarse "
        "la referencia original para trazabilidad."
    )
    lines.append(
        "3. SAN 16 es normalizable de forma semi-curada: Waze la concentra en Chalchuapa/El Coco/Jerez y existe "
        "contexto institucional para el tramo La Magdalena-El Coco-frontera."
    )
    lines.append(
        "4. RN 10, SAN 16 y SAN 24 no aparecen como referencia exacta en OSM, pero si aparecen variantes de familia "
        "como RN10S, SAN16N y SAN24E. Esto permite proponer normalizacion, pero no aprobarla sin validacion."
    )
    lines.append(
        "5. RN 17 si aparece como referencia exacta en OSM, pero el nombre detectado es local/nodal; por eso requiere "
        "alias curado para convertirse en corredor funcional."
    )
    lines.append(
        "6. La normalizacion debe manejar homonimias: una 'ruta' puede significar referencia vial, corredor turistico, "
        "ruta de transporte publico o nombre local. El contexto territorial evita mezclar entidades distintas."
    )
    lines.append("")
    lines.append("Candidatos de alias")
    lines.append("-------------------")
    if alias_df.empty:
        lines.append("No se generaron candidatos de alias.")
    else:
        for _, row in alias_df.iterrows():
            lines.append(
                f"- {row['raw_value']} -> {row['corridor_norm']} "
                f"({row['corridor_group']}, {row['road_scope']}, apply_now={row['apply_now']})"
            )
    lines.append("")
    lines.append("Recomendacion")
    lines.append("-------------")
    lines.append(
        "Crear una tabla de normalizacion vial curada con tres estados: APROBADO, CANDIDATO y RECHAZADO. "
        "Los candidatos de este estudio deben entrar inicialmente como CANDIDATO, no como regla definitiva."
    )
    lines.append(
        "Para el dashboard, se puede mostrar el candidato funcional cuando la decision empiece por NORMALIZABLE, "
        "pero siempre dejando visible la referencia tecnica y si la evidencia OSM fue exacta o por variante."
    )
    lines.append("")
    lines.append("Archivos generados")
    lines.append("------------------")
    lines.append("- Results/Waze/Jams/waze_reference_normalization_study.csv")
    lines.append("- Results/Waze/Jams/waze_reference_normalization_waze_examples.csv")
    lines.append("- Results/Waze/Jams/waze_reference_normalization_osm_evidence.csv")
    lines.append("- Results/Waze/Jams/waze_reference_normalization_alias_candidates.csv")

    (RESULTS_DIR / "waze_reference_normalization_study.txt").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    jams = pd.read_csv(JAMS_PATH, usecols=JAMS_COLUMNS, low_memory=False)
    catalog = pd.read_csv(OSM_CATALOG_PATH, low_memory=False)
    segments = pd.read_csv(OSM_SEGMENTS_PATH, low_memory=False)

    study_rows: list[dict[str, Any]] = []
    examples: list[pd.DataFrame] = []
    osm_rows: list[pd.DataFrame] = []

    for ref_norm, meta in TARGET_REFS.items():
        waze_summary, target_jams = summarize_waze(jams, ref_norm)
        osm_summary = summarize_osm_catalog(catalog, segments, ref_norm)
        row = {
            "ref_norm": ref_norm,
            "display_ref": meta["display_ref"],
            **waze_summary,
            **osm_summary,
            "reference_context": meta["reference_context"],
            "candidate_corridor_norm": meta["candidate_corridor_norm"],
            "candidate_group": meta["candidate_group"],
            "candidate_scope": meta["candidate_scope"],
            "preliminary_decision": meta["preliminary_decision"],
            "decision_reason_predefined": meta["decision_reason"],
        }
        decision, reason = decision_from_evidence(row)
        row["normalization_decision"] = decision
        row["normalization_reason"] = reason
        row["display_ref_formatted"] = format_route_ref(ref_norm)
        study_rows.append(row)

        if not target_jams.empty:
            example = target_jams.sort_values("jam_intensity_score", ascending=False).head(25).copy()
            example.insert(0, "target_ref", meta["display_ref"])
            examples.append(example)

        cat_mask, _, _ = osm_ref_masks(catalog, ref_norm)
        cat = catalog[cat_mask].copy()
        if not cat.empty:
            cat.insert(0, "target_ref", meta["display_ref"])
            osm_rows.append(cat)

    study = pd.DataFrame(study_rows).sort_values(["waze_jams", "waze_intensity"], ascending=False)
    alias_df = alias_candidates(study)

    study.to_csv(RESULTS_DIR / "waze_reference_normalization_study.csv", index=False)
    alias_df.to_csv(RESULTS_DIR / "waze_reference_normalization_alias_candidates.csv", index=False)
    if examples:
        pd.concat(examples, ignore_index=True).to_csv(
            RESULTS_DIR / "waze_reference_normalization_waze_examples.csv", index=False
        )
    else:
        pd.DataFrame().to_csv(RESULTS_DIR / "waze_reference_normalization_waze_examples.csv", index=False)
    if osm_rows:
        pd.concat(osm_rows, ignore_index=True).to_csv(
            RESULTS_DIR / "waze_reference_normalization_osm_evidence.csv", index=False
        )
    else:
        pd.DataFrame().to_csv(RESULTS_DIR / "waze_reference_normalization_osm_evidence.csv", index=False)

    write_report(study, alias_df)
    print(f"Estudio generado en {RESULTS_DIR}")


if __name__ == "__main__":
    main()
