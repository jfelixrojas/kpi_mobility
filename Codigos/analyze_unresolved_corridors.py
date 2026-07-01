#!/usr/bin/env python3
"""
Analiza casos no resueltos de corridor_norm y resolucion texto-OSM.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "Results" / "News" / "Incidentes"
EVENTS_PATH = RESULTS_DIR / "eventos_incidentes_osm_nacional_enriched.csv"

DETAIL_UNRESOLVED = RESULTS_DIR / "analisis_unresolved_corridor_norm_detalle.csv"
DETAIL_EMPTY = RESULTS_DIR / "analisis_corridor_norm_vacio_detalle.csv"
SUMMARY_CSV = RESULTS_DIR / "resumen_unresolved_corridor_norm.csv"
REPORT_TXT = RESULTS_DIR / "analisis_unresolved_corridor_norm.txt"


ROAD_TERMS = re.compile(
    r"\b(carretera|autopista|calle|avenida|alameda|boulevard|bulevar|bypass|by ?pass|redondel|"
    r"desvio|desvío|km|kilometro|kilómetro|pasarela|puente|sentido|via|vía|tramo|periferico|periférico)\b",
    re.IGNORECASE,
)


def nonempty(value: object) -> bool:
    return bool(str(value if value is not None else "").strip()) and str(value).strip().lower() != "nan"


def bool_value(value: object) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def road_term_present(row: pd.Series) -> bool:
    text = " ".join(
        str(row.get(col) or "")
        for col in ["address", "observation", "corridor_candidate", "text_corridor_norm", "nearest_osm_name", "nearest_osm_ref"]
    )
    return bool(ROAD_TERMS.search(text))


def classify_unresolved(row: pd.Series) -> str:
    has_coord = bool_value(row.get("coordinate_pair_present"))
    inside_sv = bool_value(row.get("coordinate_inside_sv_bbox"))
    has_corridor = nonempty(row.get("corridor_norm"))
    has_osm_name_ref = nonempty(row.get("nearest_osm_name")) or nonempty(row.get("nearest_osm_ref"))
    coord_status = str(row.get("coordinate_quality_status") or "")
    osm_status = str(row.get("osm_match_status") or "")

    if not has_coord and not has_corridor:
        return "A_SIN_COORDENADA_SIN_CORREDOR_TEXTUAL"
    if not has_coord and has_corridor:
        return "B_SIN_COORDENADA_CON_CORREDOR_TEXTUAL"
    if coord_status == "OUTSIDE_EL_SALVADOR_BBOX":
        return "C_COORDENADA_FUERA_SV"
    if osm_status == "NO_NEAR_OSM_SEGMENT":
        return "D_COORDENADA_SIN_SEGMENTO_OSM_CERCANO"
    if has_coord and inside_sv and not has_osm_name_ref and has_corridor:
        return "E_CORREDOR_TEXTUAL_PERO_OSM_SIN_NOMBRE_REF"
    if has_coord and inside_sv and not has_osm_name_ref and not has_corridor:
        return "F_COORDENADA_VALIDA_PERO_OSM_SIN_NOMBRE_REF_Y_SIN_TEXTO_VIAL"
    if osm_status == "SPATIAL_OSM_DISTANCE_CONFLICT":
        return "G_DISTANCIA_OSM_CONFLICTIVA"
    if has_coord and inside_sv and has_osm_name_ref and not has_corridor:
        return "H_OSM_CON_REF_NO_NORMALIZADA_O_SIN_REGLA"
    return "Z_OTRO"


def recommended_action(row: pd.Series) -> str:
    cause = str(row.get("unresolved_cause") or "")
    has_road_text = bool(row.get("road_term_present"))
    if cause == "A_SIN_COORDENADA_SIN_CORREDOR_TEXTUAL":
        return "REVISAR_TEXTO_O_GEOCODIFICAR" if has_road_text else "NO_USAR_PARA_CORREDOR_HASTA_TENER_UBICACION"
    if cause == "B_SIN_COORDENADA_CON_CORREDOR_TEXTUAL":
        return "GEOCODIFICAR_DIRECCION_O_ASOCIAR_SOLO_COMO_CORREDOR_TEXTUAL"
    if cause == "C_COORDENADA_FUERA_SV":
        return "REVISAR_GEOCODIFICACION"
    if cause == "D_COORDENADA_SIN_SEGMENTO_OSM_CERCANO":
        return "REVISAR_COORDENADA_O_COBERTURA_OSM"
    if cause == "E_CORREDOR_TEXTUAL_PERO_OSM_SIN_NOMBRE_REF":
        return "BUSCAR_SEGMENTO_OSM_NOMBRADO_EN_RADIO_O_ACEPTAR_TEXTO_CON_BAJA_CONFIANZA"
    if cause == "F_COORDENADA_VALIDA_PERO_OSM_SIN_NOMBRE_REF_Y_SIN_TEXTO_VIAL":
        return "NO_ASIGNAR_CORREDOR_SIN_REVISION;_PROBAR_NEAREST_NAMED_OSM"
    if cause == "G_DISTANCIA_OSM_CONFLICTIVA":
        return "REVISAR_COORDENADA_VS_TERRITORIO"
    if cause == "H_OSM_CON_REF_NO_NORMALIZADA_O_SIN_REGLA":
        return "AGREGAR_REGLA_REF_OSM_TRAS_VALIDACION"
    return "REVISION"


def top_table(df: pd.DataFrame, cols: list[str], n: int = 12) -> str:
    if df.empty:
        return "(sin datos)"
    frame = df[[col for col in cols if col in df.columns]].head(n).fillna("")
    return markdown_table(frame)


def markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "(sin datos)"
    frame = df.fillna("").copy()
    cols = list(frame.columns)
    rows = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in frame.iterrows():
        values = [str(row[col]).replace("\n", " ").replace("|", "/") for col in cols]
        rows.append("| " + " | ".join(values) + " |")
    return "\n".join(rows)


def write_report(events: pd.DataFrame, unresolved: pd.DataFrame, empty: pd.DataFrame, summary: pd.DataFrame) -> None:
    total = len(events)
    lines: list[str] = []
    lines.extend(
        [
            "Analisis de corridor_norm no resueltos",
            "=====================================",
            "",
            "1. Lectura correcta del problema",
            "--------------------------------",
            "Hay dos niveles distintos de no resolucion:",
            "",
            f"- Eventos con text_osm_resolution = UNRESOLVED: {len(unresolved)} de {total}.",
            f"- Eventos con corridor_norm vacio: {len(empty)} de {total}.",
            "",
            "Esto significa que no todos los UNRESOLVED estan perdidos. Algunos tienen corredor textual, pero no tienen una corroboracion OSM con nombre/ref util.",
            "",
            "2. Causas principales",
            "---------------------",
            markdown_table(summary),
            "",
            "3. Interpretacion",
            "-----------------",
            "Los casos no resueltos se explican principalmente por tres fenomenos:",
            "",
            "- Falta de coordenada y falta de corredor textual suficientemente claro.",
            "- Coordenada valida, pero el segmento OSM mas cercano no tiene nombre ni ref, por lo que no se debe inventar un corredor funcional.",
            "- Texto con corredor presente, pero sin coordenada o sin corroboracion OSM nombrada.",
            "",
            "4. Casos con corridor_norm vacio",
            "-------------------------------",
            top_table(
                empty.sort_values(["impact_social_score", "mentions"], ascending=False),
                [
                    "ticketNumber",
                    "datetime",
                    "department_norm",
                    "municipality_norm",
                    "address",
                    "unresolved_cause",
                    "recommended_action",
                    "coordinate_quality_status",
                    "osm_match_status",
                    "mentions",
                    "impact_social_score",
                    "severity_class",
                ],
                20,
            ),
            "",
            "5. Casos UNRESOLVED pero con corredor textual",
            "---------------------------------------------",
            "Estos casos no deben tratarse igual que los vacios. Ya existe una senal textual de via/corredor, pero falta soporte espacial OSM fuerte.",
            "",
            top_table(
                unresolved[unresolved["corridor_norm"].fillna("").astype(str).str.strip().ne("")]
                .sort_values(["impact_social_score", "mentions"], ascending=False),
                [
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
                ],
                20,
            ),
            "",
            "6. Acciones recomendadas",
            "------------------------",
            "Para mejorar la resolucion se recomienda:",
            "",
            "1. Agregar una busqueda secundaria de `nearest named OSM segment`: si el segmento mas cercano no tiene `name` ni `ref`, buscar dentro de 150-300 m el segmento nombrado mas cercano.",
            "2. Mejorar la extraccion textual para patrones como `carretera que conduce hacia`, `via que conecta A con B`, `sentido A a B`, `desvio X` y referencias tipo `bypass`.",
            "3. Geocodificar los casos con corredor textual pero sin coordenada, manteniendo confianza baja/media segun precision.",
            "4. Crear reglas manuales solo para referencias OSM validadas, por ejemplo `SAL50S` o `PAZ32S`, antes de convertirlas en corredores funcionales.",
            "5. No asignar corredor a eventos que solo tienen municipio/zona o coordenada generica sin texto vial. Deben permanecer como territoriales, no viales.",
            "",
            "7. Conclusion",
            "-------------",
            "Los no resueltos no invalidan la metodologia. Mas bien muestran donde falta informacion para elevar confianza. El problema principal no es la imposibilidad de asociar noticias a vias, sino la necesidad de separar: corredor confirmado, corredor textual sin soporte OSM, evento territorial sin corredor y caso que requiere geocodificacion o revision.",
            "",
        ]
    )
    REPORT_TXT.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    events = pd.read_csv(EVENTS_PATH)
    for col in [
        "corridor_norm",
        "corridor_candidate",
        "text_corridor_norm",
        "nearest_osm_name",
        "nearest_osm_ref",
        "address",
        "observation",
    ]:
        if col in events.columns:
            events[col] = events[col].fillna("").astype(str)

    events["road_term_present"] = events.apply(road_term_present, axis=1)
    events["unresolved_cause"] = events.apply(classify_unresolved, axis=1)
    events["recommended_action"] = events.apply(recommended_action, axis=1)

    unresolved = events[events["text_osm_resolution"].eq("UNRESOLVED")].copy()
    empty = events[events["corridor_norm"].fillna("").astype(str).str.strip().eq("")].copy()

    summary = (
        unresolved.groupby(["unresolved_cause", "recommended_action"], dropna=False)
        .agg(
            events=("uuid", "count"),
            mentions=("mentions", "sum"),
            impact_social=("impact_social_score", "sum"),
            fatality_events=("fatality_flag", "sum"),
            injury_events=("injury_flag", "sum"),
            road_text_events=("road_term_present", "sum"),
        )
        .reset_index()
        .sort_values(["events", "impact_social"], ascending=False)
    )

    detail_cols = [
        "ticketNumber",
        "datetime",
        "incident",
        "department_norm",
        "municipality_norm",
        "address",
        "observation",
        "corridor_candidate",
        "corridor_norm",
        "corridor_norm_source",
        "text_corridor_norm",
        "nearest_osm_name",
        "nearest_osm_ref",
        "nearest_osm_corridor_norm",
        "text_osm_resolution",
        "corridor_resolution_confidence",
        "unresolved_cause",
        "recommended_action",
        "road_term_present",
        "coordinate_quality_status",
        "osm_match_status",
        "nearest_osm_distance_m",
        "mentions",
        "impact_social_score",
        "severity_class",
        "fatality_flag",
        "injury_flag",
        "vulnerable_user_flag",
    ]
    unresolved[[col for col in detail_cols if col in unresolved.columns]].to_csv(DETAIL_UNRESOLVED, index=False)
    empty[[col for col in detail_cols if col in empty.columns]].to_csv(DETAIL_EMPTY, index=False)
    summary.to_csv(SUMMARY_CSV, index=False)
    write_report(events, unresolved, empty, summary)

    print(REPORT_TXT)
    print(DETAIL_UNRESOLVED)
    print(DETAIL_EMPTY)
    print(SUMMARY_CSV)


if __name__ == "__main__":
    main()
