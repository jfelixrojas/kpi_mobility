#!/usr/bin/env python3
"""
Prueba de concepto para aterrizar la metodologia MIVI-KPI en eventos viales
sociales y una red vial KML/KMZ.

El script:
- Lee noticias/eventos deduplicados.
- Calcula puntajes iniciales por evento: severidad, amplificacion social,
  confianza espacial y calidad minima de datos.
- Agrega el indice por dia, departamento y municipio.
- Caracteriza la red vial del KMZ.
- Asocia eventos con coordenadas al segmento vial mas cercano.

No modifica los datos crudos.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zipfile import ZipFile

import pandas as pd
from lxml import etree


ROOT = Path(__file__).resolve().parents[1]
NEWS_CSV = ROOT / "Data" / "News" / "ultimas_100_noticias.csv"
ROADS_KMZ = ROOT / "Data" / "Maps" / "RED VIAL NACIONAL DIC22.kmz"
OUTPUT_DIR = ROOT / "Data" / "Processed" / "social_road_index_poc"
RESULTS_DIR = ROOT / "Results" / "News"

KML_NS = "{http://www.opengis.net/kml/2.2}"
EARTH_RADIUS_M = 6_371_000


SPANISH_NUMBERS = {
    "un": 1,
    "una": 1,
    "uno": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
}

DEPARTMENT_NAMES = [
    "AHUACHAPAN",
    "CABAÑAS",
    "CHALATENANGO",
    "CUSCATLAN",
    "LA LIBERTAD",
    "LA PAZ",
    "LA UNION",
    "MORAZAN",
    "SAN MIGUEL",
    "SAN SALVADOR",
    "SAN VICENTE",
    "SANTA ANA",
    "SONSONATE",
    "USULUTAN",
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
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def safe_json_loads(value: Any, default: Any) -> Any:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def number_from_token(token: str) -> int | None:
    token = normalize_text(token)
    if token.isdigit():
        return int(token)
    return SPANISH_NUMBERS.get(token)


def max_count_near_keywords(text: str, keyword_regex: str) -> int:
    number_regex = r"(\d+|un|una|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez)"
    patterns = [
        rf"{number_regex}\s+(?:personas?\s+)?{keyword_regex}",
        rf"{keyword_regex}\s+(?:a\s+)?{number_regex}\s+(?:personas?)?",
    ]
    counts = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            counts.append(number_from_token(match.group(1)))
    valid_counts = [count for count in counts if count is not None]
    return max(valid_counts, default=0)


def contains_any(text: str, terms: Iterable[str]) -> bool:
    return any(term in text for term in terms)


def severity_features(observation: str, incident: str) -> dict[str, Any]:
    text = normalize_text(observation)
    incident_norm = normalize_text(incident)

    fatality = contains_any(
        text,
        [
            "fallecid",
            "muert",
            "fatal",
            "perdio la vida",
            "sin vida",
            "murio",
        ],
    )
    injured = contains_any(text, ["lesion", "herid", "atendid"])
    material_only = contains_any(text, ["solo danos materiales", "solo daños materiales"])
    vulnerable = contains_any(text, ["motocic", "moto", "peaton", "atropell", "ciclist"])
    motorcycle = contains_any(text, ["motocic", "moto"])
    pedestrian = contains_any(text, ["peaton", "atropell"])
    heavy_vehicle = contains_any(text, ["camion", "rastra", "furgon", "pipa", "bus", "microbus"])
    obstruction = contains_any(
        text,
        [
            "carril",
            "paso",
            "carga vehicular",
            "cierre",
            "bloque",
            "derrame",
            "arbol",
            "desperfecto",
            "trafico",
        ],
    )
    multiple = contains_any(
        text,
        [
            "multiple",
            "triple",
            "varios vehiculos",
            "tres vehiculos",
            "dos vehiculos",
            "vehiculos involucrados",
        ],
    )

    injury_count = max_count_near_keywords(text, r"(?:lesionad\w*|herid\w*)")
    fatality_count = max_count_near_keywords(text, r"(?:fallecid\w*|muert\w*)")

    if fatality:
        severity_class = "FATALITY_REPORTED"
        severity = 0.9
        if fatality_count:
            severity += min(fatality_count, 3) * 0.03
    elif injured:
        severity_class = "INJURY_REPORTED"
        severity = 0.5
        if injury_count:
            severity += min(injury_count, 6) * 0.05
    elif incident_norm == "traffic_accident":
        severity_class = "TRAFFIC_ACCIDENT_UNSPECIFIED"
        severity = 0.32
    elif obstruction:
        severity_class = "ROAD_AFFECTATION"
        severity = 0.22
    else:
        severity_class = "OTHER_LOW_INFORMATION"
        severity = 0.12

    if vulnerable:
        severity += 0.08
    if pedestrian:
        severity += 0.04
    if motorcycle:
        severity += 0.03
    if heavy_vehicle:
        severity += 0.05
    if multiple:
        severity += 0.06
    if obstruction:
        severity += 0.03
    if material_only:
        severity_class = "MATERIAL_DAMAGE_ONLY"
        severity = min(severity, 0.25)

    severity = max(0.0, min(1.0, severity))
    return {
        "severity_class": severity_class,
        "severity_score": round(severity, 4),
        "fatality_flag": fatality,
        "fatality_count_text": fatality_count,
        "injury_flag": injured,
        "injury_count_text": injury_count,
        "vulnerable_user_flag": vulnerable,
        "motorcycle_flag": motorcycle,
        "pedestrian_flag": pedestrian,
        "heavy_vehicle_flag": heavy_vehicle,
        "multi_vehicle_flag": multiple,
        "obstruction_flag": obstruction,
        "material_damage_only_flag": material_only,
    }


def aggregate_news_flag(observation: str) -> bool:
    text = normalize_text(observation)
    return contains_any(
        text,
        [
            "diferentes percances",
            "varios accidentes",
            "varios percances",
            "al menos cinco lesionados en accidentes",
            "jornada de accidentes",
            "resumen",
        ],
    )


def location_conflict_flag(observation: str, department: Any) -> bool:
    text = normalize_text(observation)
    dept_norm = normalize_text(department)
    mentioned = [
        dept
        for dept in DEPARTMENT_NAMES
        if normalize_text(dept) in text
    ]
    if not mentioned:
        return False
    if not dept_norm:
        return False
    return all(normalize_text(dept) != dept_norm for dept in mentioned)


def spatial_level(row: pd.Series, is_aggregate: bool) -> str:
    has_point = pd.notna(row.get("latitude")) and pd.notna(row.get("longitude"))
    has_address = bool(str(row.get("address") or "").strip()) and not pd.isna(row.get("address"))
    has_municipality = bool(str(row.get("municipality") or "").strip()) and not pd.isna(row.get("municipality"))
    has_department = bool(str(row.get("department") or "").strip()) and not pd.isna(row.get("department"))
    if is_aggregate:
        return "MULTI_LOCATION_NEWS"
    if has_point:
        return "POINT"
    if has_address and has_municipality:
        return "ADDRESS_TEXT"
    if has_municipality:
        return "MUNICIPALITY"
    if has_department:
        return "DEPARTMENT"
    if has_address:
        return "TEXT_ONLY"
    return "UNKNOWN"


def source_diversity(evidence: list[dict[str, Any]]) -> int:
    return len({str(item.get("source")) for item in evidence if item.get("source")})


def metric_readiness(row: dict[str, Any]) -> tuple[str, str, float]:
    spatial = row["spatial_level"]
    aggregate = bool(row["aggregate_news_flag"])
    conflict = bool(row["location_conflict_flag"])
    quality = float(row["data_quality_score"])
    geo = float(row["geo_confidence"])
    evidence = float(row["evidence_score"])

    penalty = 0.0
    if aggregate:
        penalty += 0.20
    if conflict:
        penalty += 0.25

    if spatial == "POINT" and not aggregate and not conflict:
        status = "USABLE_PARA_METRICA_ESPACIAL"
        reason = "Tiene coordenadas puntuales y no presenta alerta textual fuerte."
        spatial_weight = 1.0
    elif spatial == "ADDRESS_TEXT":
        status = "USABLE_CON_GEOCODIFICACION"
        reason = "Tiene direccion textual y municipio; puede mejorar con geocodificacion."
        spatial_weight = 0.75
    elif spatial in {"MUNICIPALITY", "DEPARTMENT"}:
        status = "USABLE_PARA_METRICA_TERRITORIAL"
        reason = "Sirve para agregados territoriales, no para segmento vial."
        spatial_weight = 0.45
    elif spatial == "MULTI_LOCATION_NEWS":
        status = "USABLE_SOLO_COMO_CONTEXTO"
        reason = "La noticia parece resumir varios eventos o ubicaciones."
        spatial_weight = 0.20
    elif spatial == "TEXT_ONLY":
        status = "REQUIERE_EXTRACCION_GEOESPACIAL"
        reason = "Tiene texto ubicable, pero falta municipio/departamento estructurado."
        spatial_weight = 0.25
    else:
        status = "NO_USABLE_TODAVIA"
        reason = "No tiene ubicacion suficiente para metricas defendibles."
        spatial_weight = 0.10

    readiness = 100 * (
        0.30 * quality
        + 0.25 * spatial_weight
        + 0.20 * geo
        + 0.15 * evidence
        + 0.10 * (0 if penalty else 1)
    )
    readiness = max(0.0, min(100.0, readiness - penalty * 100))
    return status, reason, round(readiness, 2)


def build_enriched_events(news_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(news_csv)
    enriched_rows = []

    max_mentions = 10
    for _, row in df.iterrows():
        reliability = safe_json_loads(row.get("reliability"), {})
        evidence = safe_json_loads(row.get("evidence"), [])
        if not isinstance(evidence, list):
            evidence = []

        mentions = int(reliability.get("mentions") or len(evidence) or 1)
        links_count = int(reliability.get("links_count") or len(evidence) or 0)
        geo_confidence = float(reliability.get("geo_confidence") or 0)
        src_diversity = source_diversity(evidence)

        severity = severity_features(row.get("observation", ""), row.get("incident", ""))
        is_aggregate = aggregate_news_flag(row.get("observation", ""))
        loc_conflict = location_conflict_flag(row.get("observation", ""), row.get("department"))
        level = spatial_level(row, is_aggregate)

        has_point = pd.notna(row.get("latitude")) and pd.notna(row.get("longitude"))
        has_address = pd.notna(row.get("address")) and bool(str(row.get("address")).strip())
        has_municipality = pd.notna(row.get("municipality")) and bool(str(row.get("municipality")).strip())
        has_department = pd.notna(row.get("department")) and bool(str(row.get("department")).strip())

        evidence_score = min(math.log1p(mentions) / math.log1p(max_mentions), 1.0)
        spatial_score = min(geo_confidence + (0.1 if has_point else 0), 1.0)
        data_quality = (
            (0.20 if has_address else 0)
            + (0.15 if has_municipality else 0)
            + (0.15 if has_department else 0)
            + min(src_diversity, 3) / 3 * 0.15
            + min(links_count, 3) / 3 * 0.10
            + (0.15 if has_point else 0)
            + (0.10 if not is_aggregate else 0)
        )
        if loc_conflict:
            data_quality = max(0.0, data_quality - 0.15)
        data_quality = min(data_quality, 1.0)

        event_index = 100 * (
            0.35 * severity["severity_score"]
            + 0.25 * evidence_score
            + 0.20 * spatial_score
            + 0.20 * data_quality
        )

        enriched = row.to_dict()
        enriched.update(severity)
        enriched.update(
            {
                "event_date": pd.to_datetime(row["datetime"]).date().isoformat(),
                "event_hour": pd.to_datetime(row["datetime"]).hour,
                "mentions": mentions,
                "links_count": links_count,
                "source_diversity": src_diversity,
                "geo_confidence": geo_confidence,
                "evidence_score": round(evidence_score, 4),
                "spatial_score": round(spatial_score, 4),
                "data_quality_score": round(data_quality, 4),
                "social_road_event_index_0_100": round(event_index, 2),
                "spatial_level": level,
                "aggregate_news_flag": is_aggregate,
                "location_conflict_flag": loc_conflict,
            }
        )
        readiness_status, readiness_reason, readiness_score = metric_readiness(enriched)
        enriched.update(
            {
                "metric_readiness_status": readiness_status,
                "metric_readiness_reason": readiness_reason,
                "metric_readiness_score_0_100": readiness_score,
            }
        )
        enriched_rows.append(enriched)

    enriched_df = pd.DataFrame(enriched_rows)
    enriched_df["department_norm"] = enriched_df["department"].map(lambda x: normalize_text(x).upper() if pd.notna(x) else "SIN_DEPTO")
    enriched_df["municipality_norm"] = enriched_df["municipality"].map(lambda x: normalize_text(x).title() if pd.notna(x) else "SIN_MUNICIPIO")
    return enriched_df


def build_mentions_expanded(news_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(news_csv)
    rows = []
    for _, event in df.iterrows():
        evidence = safe_json_loads(event.get("evidence"), [])
        reliability = safe_json_loads(event.get("reliability"), {})
        if not isinstance(evidence, list):
            evidence = []
        for index, mention in enumerate(evidence, start=1):
            rows.append(
                {
                    "event_uuid": event.get("uuid"),
                    "ticketNumber": event.get("ticketNumber"),
                    "event_datetime_row": event.get("datetime"),
                    "event_incident": event.get("incident"),
                    "event_department": event.get("department"),
                    "event_municipality": event.get("municipality"),
                    "event_address": event.get("address"),
                    "event_geo_confidence": reliability.get("geo_confidence"),
                    "event_mentions_total": reliability.get("mentions"),
                    "mention_order": index,
                    "mention_id": mention.get("mention_id"),
                    "source": mention.get("source"),
                    "source_item_id": mention.get("source_item_id"),
                    "canonical_url": mention.get("canonical_url"),
                    "url": mention.get("url"),
                    "published_at": mention.get("published_at"),
                    "event_datetime_mention": mention.get("event_datetime"),
                    "is_relevant": mention.get("is_relevant"),
                    "relevance_confidence": mention.get("relevance_confidence"),
                    "relevance_reason_code": mention.get("relevance_reason_code"),
                    "is_followup_update": mention.get("is_followup_update"),
                    "needs_maps": mention.get("needs_maps"),
                    "maps_reason": mention.get("maps_reason"),
                    "title": mention.get("title"),
                    "raw_text": mention.get("raw_text"),
                    "context_summary": mention.get("context_summary"),
                    "content_hash": mention.get("content_hash"),
                    "content_fingerprint": mention.get("content_fingerprint"),
                    "mention_department": mention.get("department"),
                    "mention_municipality": mention.get("municipality"),
                    "mention_latitude": mention.get("latitude"),
                    "mention_longitude": mention.get("longitude"),
                    "mention_geo_confidence": mention.get("geo_confidence"),
                    "geo_validation_status": mention.get("geo_validation_status"),
                }
            )
    return pd.DataFrame(rows)


def aggregate_indices(events: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    daily = (
        events.groupby("event_date", dropna=False)
        .agg(
            events=("uuid", "count"),
            traffic_accidents=("incident", lambda s: int((s == "TRAFFIC_ACCIDENT").sum())),
            other_events=("incident", lambda s: int((s == "OTHER").sum())),
            score_sum=("social_road_event_index_0_100", "sum"),
            avg_event_index=("social_road_event_index_0_100", "mean"),
            severity_sum=("severity_score", "sum"),
            mentions_sum=("mentions", "sum"),
            avg_geo_confidence=("geo_confidence", "mean"),
            point_events=("spatial_level", lambda s: int((s == "POINT").sum())),
            address_text_events=("spatial_level", lambda s: int((s == "ADDRESS_TEXT").sum())),
            multi_location_news=("aggregate_news_flag", "sum"),
        )
        .reset_index()
        .sort_values("event_date")
    )
    daily["cumulative_events"] = daily["events"].cumsum()
    daily["cumulative_score"] = daily["score_sum"].cumsum().round(2)
    max_daily = daily["score_sum"].max() or 1
    daily["daily_social_road_index_0_100"] = (daily["score_sum"] / max_daily * 100).round(2)
    final_cumulative = daily["cumulative_score"].iloc[-1] or 1
    daily["cumulative_social_signal_0_100"] = (daily["cumulative_score"] / final_cumulative * 100).round(2)

    department = (
        events.groupby("department_norm", dropna=False)
        .agg(
            events=("uuid", "count"),
            traffic_accidents=("incident", lambda s: int((s == "TRAFFIC_ACCIDENT").sum())),
            score_sum=("social_road_event_index_0_100", "sum"),
            avg_event_index=("social_road_event_index_0_100", "mean"),
            severity_sum=("severity_score", "sum"),
            mentions_sum=("mentions", "sum"),
            avg_geo_confidence=("geo_confidence", "mean"),
            point_events=("spatial_level", lambda s: int((s == "POINT").sum())),
            address_text_events=("spatial_level", lambda s: int((s == "ADDRESS_TEXT").sum())),
        )
        .reset_index()
        .sort_values(["score_sum", "events"], ascending=False)
    )
    max_department = department["score_sum"].max() or 1
    department["department_index_0_100"] = (department["score_sum"] / max_department * 100).round(2)

    municipality = (
        events.groupby(["department_norm", "municipality_norm"], dropna=False)
        .agg(
            events=("uuid", "count"),
            score_sum=("social_road_event_index_0_100", "sum"),
            avg_event_index=("social_road_event_index_0_100", "mean"),
            severity_sum=("severity_score", "sum"),
            mentions_sum=("mentions", "sum"),
            avg_geo_confidence=("geo_confidence", "mean"),
            point_events=("spatial_level", lambda s: int((s == "POINT").sum())),
            address_text_events=("spatial_level", lambda s: int((s == "ADDRESS_TEXT").sum())),
        )
        .reset_index()
        .sort_values(["score_sum", "events"], ascending=False)
    )
    max_municipality = municipality["score_sum"].max() or 1
    municipality["municipality_index_0_100"] = (municipality["score_sum"] / max_municipality * 100).round(2)
    return daily, department, municipality


def pct(count: float, total: float) -> float:
    if not total:
        return 0.0
    return round(count / total * 100, 2)


def build_quality_diagnostics(
    events: pd.DataFrame,
    mentions: pd.DataFrame,
    road_matches: pd.DataFrame,
) -> pd.DataFrame:
    total = len(events)
    diagnostics = []

    def add(metric: str, value: Any, percent: float | None, reading: str) -> None:
        diagnostics.append(
            {
                "metric": metric,
                "value": value,
                "percent": percent,
                "reading": reading,
            }
        )

    add("eventos_totales", total, 100.0, "Unidad principal: evento vial deduplicado.")
    add("menciones_expandidas", len(mentions), None, "Unidad secundaria: publicaciones o notas asociadas al evento.")
    add("promedio_menciones_por_evento", round(float(events["mentions"].mean()), 2), None, "Mide respaldo o amplificacion informativa.")
    add("eventos_traffic_accident", int((events["incident"] == "TRAFFIC_ACCIDENT").sum()), pct((events["incident"] == "TRAFFIC_ACCIDENT").sum(), total), "La fuente esta altamente concentrada en accidentes.")
    add("eventos_other", int((events["incident"] == "OTHER").sum()), pct((events["incident"] == "OTHER").sum(), total), "Eventos viales no clasificados como accidente.")
    add("eventos_con_multiples_menciones", int((events["mentions"] > 1).sum()), pct((events["mentions"] > 1).sum(), total), "Mayor respaldo informativo y mejor deduplicacion potencial.")
    add("eventos_con_mas_de_una_fuente", int((events["source_diversity"] > 1).sum()), pct((events["source_diversity"] > 1).sum(), total), "Corroboracion por fuentes distintas.")
    add("eventos_con_lesionados_texto", int(events["injury_flag"].sum()), pct(events["injury_flag"].sum(), total), "Severidad preliminar inferible desde texto.")
    add("eventos_con_fallecidos_texto", int(events["fatality_flag"].sum()), pct(events["fatality_flag"].sum(), total), "Eventos de severidad alta para validacion prioritaria.")
    add("eventos_con_usuarios_vulnerables", int(events["vulnerable_user_flag"].sum()), pct(events["vulnerable_user_flag"].sum(), total), "Aporta informacion relevante para KPIs de seguridad vial.")
    add("eventos_motocicleta", int(events["motorcycle_flag"].sum()), pct(events["motorcycle_flag"].sum(), total), "Variable recurrente en la muestra.")
    add("eventos_peaton_atropello", int(events["pedestrian_flag"].sum()), pct(events["pedestrian_flag"].sum(), total), "Variable relevante para usuarios vulnerables.")
    add("eventos_vehiculo_pesado_o_tp", int(events["heavy_vehicle_flag"].sum()), pct(events["heavy_vehicle_flag"].sum(), total), "Aporta lectura de carga/transporte publico cuando el texto lo permite.")
    add("eventos_con_afectacion_vial", int(events["obstruction_flag"].sum()), pct(events["obstruction_flag"].sum(), total), "Indica cierres, paso afectado, carga vehicular u obstruccion.")
    add("registros_con_lat_lon", int(pd.notna(events["latitude"]).sum()), pct(pd.notna(events["latitude"]).sum(), total), "Cobertura de coordenadas crudas.")
    add("eventos_puntuales_validables", int((events["spatial_level"] == "POINT").sum()), pct((events["spatial_level"] == "POINT").sum(), total), "Base real para correlacion directa evento-via.")
    add("eventos_direccion_municipio", int((events["spatial_level"] == "ADDRESS_TEXT").sum()), pct((events["spatial_level"] == "ADDRESS_TEXT").sum(), total), "Potencial principal para geocodificacion.")
    add("eventos_solo_texto", int((events["spatial_level"] == "TEXT_ONLY").sum()), pct((events["spatial_level"] == "TEXT_ONLY").sum(), total), "Requieren extraccion geopolitica o geocodificacion semantica.")
    add("eventos_multiubicacion", int(events["aggregate_news_flag"].sum()), pct(events["aggregate_news_flag"].sum(), total), "No deben forzarse a una unica via.")
    add("eventos_con_conflicto_ubicacion", int(events["location_conflict_flag"].sum()), pct(events["location_conflict_flag"].sum(), total), "Requieren revision antes de usarse espacialmente.")
    add("eventos_usables_ahora_espacialmente", int((events["metric_readiness_status"] == "USABLE_PARA_METRICA_ESPACIAL").sum()), pct((events["metric_readiness_status"] == "USABLE_PARA_METRICA_ESPACIAL").sum(), total), "Aptos para metricas con coordenada puntual.")
    add("eventos_usables_con_geocodificacion", int((events["metric_readiness_status"] == "USABLE_CON_GEOCODIFICACION").sum()), pct((events["metric_readiness_status"] == "USABLE_CON_GEOCODIFICACION").sum(), total), "Principal bolsa de mejora para llegar a correlacion vial.")
    add("eventos_usables_territoriales", int((events["metric_readiness_status"] == "USABLE_PARA_METRICA_TERRITORIAL").sum()), pct((events["metric_readiness_status"] == "USABLE_PARA_METRICA_TERRITORIAL").sum(), total), "Sirven por municipio/departamento, no por segmento vial.")
    if road_matches.empty:
        add("eventos_con_match_vial_aceptado", 0, 0.0, "No hay puntos suficientes o confiables para asociacion vial aceptada.")
    else:
        accepted = int(road_matches["road_match_quality"].isin(["HIGH", "MEDIUM", "LOW"]).sum())
        add("eventos_con_match_vial_aceptado", accepted, pct(accepted, total), "Eventos con distancia a red vial dentro de umbral inicial.")
    return pd.DataFrame(diagnostics)


def build_variable_maturity(events: pd.DataFrame) -> pd.DataFrame:
    total = len(events)
    variables = [
        ("fecha_hora_evento", "datetime", events["datetime"].notna().sum(), "USABLE_AHORA", "Permite series temporales diarias y horarias."),
        ("tipo_incidente", "incident", events["incident"].notna().sum(), "USABLE_AHORA", "Clasificacion base: accidente u otro evento vial."),
        ("texto_observacion", "observation", events["observation"].notna().sum(), "USABLE_AHORA_CON_NLP_SIMPLE", "Permite extraer severidad, actores y condiciones viales."),
        ("menciones", "reliability.mentions/evidence", events["mentions"].notna().sum(), "USABLE_AHORA", "Aporta respaldo informativo y deduplicacion."),
        ("fuentes_distintas", "evidence.source", events["source_diversity"].notna().sum(), "USABLE_AHORA", "Mide corroboracion entre fuentes."),
        ("severidad_preliminar", "derivada_texto", events["severity_score"].notna().sum(), "USABLE_CON_VALIDACION", "Buena para exploracion; requiere reglas auditables o modelo validado."),
        ("lesionados", "derivada_texto", events["injury_flag"].sum(), "USABLE_CON_VALIDACION", "Variable importante para seguridad vial; debe validarse con fuente oficial si se convierte en KPI."),
        ("fallecidos", "derivada_texto", events["fatality_flag"].sum(), "USABLE_CON_VALIDACION_PRIORITARIA", "Alta relevancia; requiere validacion oficial."),
        ("usuarios_vulnerables", "derivada_texto", events["vulnerable_user_flag"].sum(), "USABLE_CON_VALIDACION", "Aporta a metricas de seguridad de motociclistas/peatones/ciclistas."),
        ("departamento", "department", events["department"].notna().sum(), "USABLE_AHORA_TERRITORIAL", "Permite agregacion gruesa."),
        ("municipio", "municipality", events["municipality"].notna().sum(), "USABLE_AHORA_TERRITORIAL", "Permite primera POC territorial."),
        ("direccion_textual", "address", events["address"].notna().sum(), "USABLE_CON_GEOCODIFICACION", "Principal entrada para mejorar capa espacial."),
        ("latitud_longitud", "latitude/longitude", (events[["latitude", "longitude"]].notna().all(axis=1)).sum(), "INSUFICIENTE_PARA_ANALISIS_VIAL_MASIVO", "Solo sirve en eventos puntuales confiables."),
        ("match_segmento_vial", "derivada_red_vial", 0, "REQUIERE_GEOCODIFICACION_Y_RED_ATRIBUTADA", "No debe forzarse hasta mejorar coordenadas y red vial."),
        ("confianza_geografica", "reliability.geo_confidence", events["geo_confidence"].notna().sum(), "USABLE_AHORA_COMO_CONTROL", "No reemplaza validacion espacial, pero ayuda a filtrar."),
        ("calidad_del_dato", "derivada", events["data_quality_score"].notna().sum(), "USABLE_AHORA_COMO_INDICADOR_INTERNO", "Mide completitud y robustez minima."),
    ]
    return pd.DataFrame(
        [
            {
                "variable": name,
                "source_field": source,
                "usable_records": int(count),
                "usable_percent": pct(count, total),
                "maturity": maturity,
                "interpretation": interpretation,
            }
            for name, source, count, maturity, interpretation in variables
        ]
    )


def build_exploratory_indicators(
    events: pd.DataFrame,
    mentions: pd.DataFrame,
    daily: pd.DataFrame,
    department: pd.DataFrame,
    municipality: pd.DataFrame,
    road_matches: pd.DataFrame,
) -> pd.DataFrame:
    total = len(events)
    top_day = daily.sort_values("score_sum", ascending=False).iloc[0]
    top_department = department.sort_values("score_sum", ascending=False).iloc[0]
    top_municipality = municipality.sort_values("score_sum", ascending=False).iloc[0]
    indicators = [
        ("eventos_deduplicados", total, "Volumen de eventos viales consolidados."),
        ("menciones_expandidas", len(mentions), "Volumen de publicaciones/notas que respaldan eventos."),
        ("menciones_promedio_por_evento", round(float(events["mentions"].mean()), 2), "Amplificacion social promedio."),
        ("porcentaje_accidentes", pct((events["incident"] == "TRAFFIC_ACCIDENT").sum(), total), "Concentracion de la fuente en accidentes."),
        ("porcentaje_eventos_con_lesionados", pct(events["injury_flag"].sum(), total), "Capacidad de detectar severidad no fatal."),
        ("porcentaje_eventos_con_fallecidos", pct(events["fatality_flag"].sum(), total), "Capacidad de detectar severidad critica."),
        ("porcentaje_usuarios_vulnerables", pct(events["vulnerable_user_flag"].sum(), total), "Aporte potencial a seguridad vial."),
        ("porcentaje_con_direccion_util", pct((events["spatial_level"] == "ADDRESS_TEXT").sum(), total), "Potencial de geocodificacion."),
        ("porcentaje_con_coordenada_puntual", pct((events["spatial_level"] == "POINT").sum(), total), "Capacidad actual de analisis vial fino."),
        ("porcentaje_usables_con_geocodificacion", pct((events["metric_readiness_status"] == "USABLE_CON_GEOCODIFICACION").sum(), total), "Bolsa de registros que puede madurar con geocoder."),
        ("dia_mayor_senal", top_day["event_date"], f"{int(top_day['events'])} eventos; score {round(float(top_day['score_sum']), 2)}."),
        ("departamento_mayor_senal", top_department["department_norm"], f"{int(top_department['events'])} eventos; indice {top_department['department_index_0_100']}."),
        ("municipio_mayor_senal", f"{top_municipality['department_norm']} / {top_municipality['municipality_norm']}", f"{int(top_municipality['events'])} eventos; indice {top_municipality['municipality_index_0_100']}."),
    ]
    if road_matches.empty:
        indicators.append(("eventos_asociados_a_red_vial", 0, "Sin eventos puntuales para asociacion vial defendible."))
    else:
        accepted = int(road_matches["road_match_quality"].isin(["HIGH", "MEDIUM", "LOW"]).sum())
        indicators.append(("eventos_asociados_a_red_vial", accepted, "Eventos con distancia a red vial dentro de umbral."))
    return pd.DataFrame(
        [{"indicator": name, "value": value, "interpretation": interpretation} for name, value, interpretation in indicators]
    )


def parse_coordinate_text(text: str) -> list[tuple[float, float]]:
    coords = []
    for token in text.split():
        parts = token.split(",")
        if len(parts) < 2:
            continue
        try:
            lon = float(parts[0])
            lat = float(parts[1])
        except ValueError:
            continue
        coords.append((lon, lat))
    return coords


def lonlat_to_xy(lon: float, lat: float, lat0: float) -> tuple[float, float]:
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    lat0_rad = math.radians(lat0)
    return (
        EARTH_RADIUS_M * lon_rad * math.cos(lat0_rad),
        EARTH_RADIUS_M * lat_rad,
    )


def xy_to_lonlat(x: float, y: float, lat0: float) -> tuple[float, float]:
    lat0_rad = math.radians(lat0)
    lat = math.degrees(y / EARTH_RADIUS_M)
    lon = math.degrees(x / (EARTH_RADIUS_M * math.cos(lat0_rad)))
    return lon, lat


def segment_distance_m(
    point_lon: float,
    point_lat: float,
    a_lon: float,
    a_lat: float,
    b_lon: float,
    b_lat: float,
) -> tuple[float, float, float]:
    px, py = lonlat_to_xy(point_lon, point_lat, point_lat)
    ax, ay = lonlat_to_xy(a_lon, a_lat, point_lat)
    bx, by = lonlat_to_xy(b_lon, b_lat, point_lat)
    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        proj_x, proj_y = ax, ay
    else:
        t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))
        proj_x = ax + t * dx
        proj_y = ay + t * dy
    distance = math.hypot(px - proj_x, py - proj_y)
    proj_lon, proj_lat = xy_to_lonlat(proj_x, proj_y, point_lat)
    return distance, proj_lon, proj_lat


def haversine_m(a_lon: float, a_lat: float, b_lon: float, b_lat: float) -> float:
    phi1 = math.radians(a_lat)
    phi2 = math.radians(b_lat)
    dphi = math.radians(b_lat - a_lat)
    dlambda = math.radians(b_lon - a_lon)
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(h))


@dataclass
class RoadStats:
    placemarks: int = 0
    line_strings: int = 0
    vertices: int = 0
    total_length_km: float = 0.0
    min_lon: float = 999.0
    min_lat: float = 999.0
    max_lon: float = -999.0
    max_lat: float = -999.0
    style_counts: Counter[str] | None = None


def match_quality(distance_m: float | None) -> str:
    if distance_m is None or math.isnan(distance_m):
        return "NO_MATCH"
    if distance_m <= 30:
        return "HIGH"
    if distance_m <= 50:
        return "MEDIUM"
    if distance_m <= 100:
        return "LOW"
    return "REVIEW"


def road_stats_and_matches(kmz_path: Path, point_events: pd.DataFrame) -> tuple[RoadStats, pd.DataFrame]:
    stats = RoadStats(style_counts=Counter())
    candidates = []
    for _, row in point_events.iterrows():
        candidates.append(
            {
                "uuid": row["uuid"],
                "ticketNumber": row["ticketNumber"],
                "latitude": float(row["latitude"]),
                "longitude": float(row["longitude"]),
                "observation": row["observation"],
                "spatial_level": row["spatial_level"],
                "aggregate_news_flag": bool(row["aggregate_news_flag"]),
                "location_conflict_flag": bool(row["location_conflict_flag"]),
                "best_distance_m": float("inf"),
                "matched_road_name": None,
                "matched_style": None,
                "matched_lon": None,
                "matched_lat": None,
            }
        )

    with ZipFile(kmz_path) as zf:
        with zf.open("doc.kml") as f:
            context = etree.iterparse(
                f,
                events=("end",),
                tag=KML_NS + "Placemark",
                recover=True,
                huge_tree=True,
            )
            for _, placemark in context:
                stats.placemarks += 1
                name = placemark.findtext(KML_NS + "name") or ""
                style = placemark.findtext(KML_NS + "styleUrl") or ""
                if style:
                    stats.style_counts[style] += 1

                coordinate_elements = placemark.findall(".//" + KML_NS + "coordinates")
                for coordinate_element in coordinate_elements:
                    raw = (coordinate_element.text or "").strip()
                    if not raw:
                        continue
                    coords = parse_coordinate_text(raw)
                    if len(coords) < 2:
                        continue

                    stats.line_strings += 1
                    stats.vertices += len(coords)
                    for lon, lat in coords:
                        stats.min_lon = min(stats.min_lon, lon)
                        stats.min_lat = min(stats.min_lat, lat)
                        stats.max_lon = max(stats.max_lon, lon)
                        stats.max_lat = max(stats.max_lat, lat)

                    for (a_lon, a_lat), (b_lon, b_lat) in zip(coords, coords[1:]):
                        stats.total_length_km += haversine_m(a_lon, a_lat, b_lon, b_lat) / 1000
                        for candidate in candidates:
                            distance, proj_lon, proj_lat = segment_distance_m(
                                candidate["longitude"],
                                candidate["latitude"],
                                a_lon,
                                a_lat,
                                b_lon,
                                b_lat,
                            )
                            if distance < candidate["best_distance_m"]:
                                candidate["best_distance_m"] = distance
                                candidate["matched_road_name"] = name
                                candidate["matched_style"] = style
                                candidate["matched_lon"] = proj_lon
                                candidate["matched_lat"] = proj_lat

                placemark.clear()
                while placemark.getprevious() is not None:
                    del placemark.getparent()[0]

    match_rows = []
    for candidate in candidates:
        distance = candidate["best_distance_m"]
        if math.isinf(distance):
            distance = None
        warning = []
        if candidate["aggregate_news_flag"]:
            warning.append("aggregate_news_not_point_event")
        if candidate["location_conflict_flag"]:
            warning.append("possible_location_conflict")
        match_rows.append(
            {
                **candidate,
                "best_distance_m": round(distance, 2) if distance is not None else None,
                "matched_lon": round(candidate["matched_lon"], 7) if candidate["matched_lon"] is not None else None,
                "matched_lat": round(candidate["matched_lat"], 7) if candidate["matched_lat"] is not None else None,
                "road_match_quality": match_quality(distance),
                "match_warning": ";".join(warning),
            }
        )
    return stats, pd.DataFrame(match_rows)


def write_geojson(events: pd.DataFrame, path: Path) -> None:
    features = []
    for _, row in events[pd.notna(events["latitude"]) & pd.notna(events["longitude"])].iterrows():
        props = {
            "uuid": row["uuid"],
            "ticketNumber": row["ticketNumber"],
            "datetime": row["datetime"],
            "incident": row["incident"],
            "department": row.get("department"),
            "municipality": row.get("municipality"),
            "address": row.get("address"),
            "observation": row.get("observation"),
            "index_0_100": row["social_road_event_index_0_100"],
            "severity_score": row["severity_score"],
            "mentions": int(row["mentions"]),
            "geo_confidence": row["geo_confidence"],
            "spatial_level": row["spatial_level"],
            "aggregate_news_flag": bool(row["aggregate_news_flag"]),
            "location_conflict_flag": bool(row["location_conflict_flag"]),
        }
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row["longitude"]), float(row["latitude"])],
                },
                "properties": props,
            }
        )
    geojson = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(geojson, ensure_ascii=False, indent=2), encoding="utf-8")


def markdown_table(df: pd.DataFrame, max_col_width: int = 120) -> str:
    if df.empty:
        return "_Sin registros._"

    def clean(value: Any) -> str:
        if pd.isna(value):
            return ""
        text = str(value).replace("\n", " ").replace("|", "\\|")
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > max_col_width:
            return text[: max_col_width - 3] + "..."
        return text

    columns = list(df.columns)
    rows = [[clean(value) for value in row] for row in df.itertuples(index=False, name=None)]
    widths = [
        max(len(str(column)), *(len(row[index]) for row in rows))
        for index, column in enumerate(columns)
    ]
    header = "| " + " | ".join(str(column).ljust(widths[index]) for index, column in enumerate(columns)) + " |"
    separator = "| " + " | ".join("-" * widths[index] for index in range(len(columns))) + " |"
    body = [
        "| " + " | ".join(row[index].ljust(widths[index]) for index in range(len(columns))) + " |"
        for row in rows
    ]
    return "\n".join([header, separator, *body])


def counts_table(series: pd.Series, label: str) -> pd.DataFrame:
    table = series.fillna("SIN_DATO").value_counts(dropna=False).reset_index()
    table.columns = [label, "count"]
    total = table["count"].sum()
    table["percent"] = table["count"].map(lambda count: pct(count, total))
    return table


def write_summary(
    events: pd.DataFrame,
    daily: pd.DataFrame,
    department: pd.DataFrame,
    municipality: pd.DataFrame,
    road_stats: RoadStats,
    road_matches: pd.DataFrame,
    path: Path,
) -> None:
    spatial_counts = events["spatial_level"].value_counts(dropna=False)
    top_events = events.sort_values("social_road_event_index_0_100", ascending=False).head(10)

    lines = [
        "# POC - Indice social de eventos viales",
        "",
        f"Generado: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Insumos",
        "",
        f"- Noticias/eventos: `{NEWS_CSV}`",
        f"- Red vial KMZ: `{ROADS_KMZ}`",
        "",
        "## Lectura metodologica",
        "",
        "Esta prueba toma los eventos viales sociales como una familia de variables dentro de MIVI-KPI.",
        "El indice no debe interpretarse todavia como KPI oficial: es una senal exploratoria que combina severidad textual, amplificacion social, confianza espacial y calidad minima de datos.",
        "",
        "## Calidad y cobertura",
        "",
        f"- Eventos: {len(events)}",
        f"- Accidentes de transito: {int((events['incident'] == 'TRAFFIC_ACCIDENT').sum())}",
        f"- Otros eventos viales/sociales: {int((events['incident'] == 'OTHER').sum())}",
        f"- Registros con lat/lon: {int(pd.notna(events['latitude']).sum())}",
        f"- Eventos puntuales con coordenadas: {int((events['spatial_level'] == 'POINT').sum())}",
        f"- Eventos con direccion textual y municipio: {int((events['spatial_level'] == 'ADDRESS_TEXT').sum())}",
        f"- Noticias multiubicacion/agregadas: {int(events['aggregate_news_flag'].sum())}",
        f"- Posibles conflictos de ubicacion textual: {int(events['location_conflict_flag'].sum())}",
        "",
        "### Niveles espaciales",
        "",
    ]
    for level, count in spatial_counts.items():
        lines.append(f"- {level}: {count}")

    lines.extend(
        [
            "",
            "## Red vial",
            "",
            f"- Placemarks: {road_stats.placemarks}",
            f"- LineStrings: {road_stats.line_strings}",
            f"- Vertices: {road_stats.vertices}",
            f"- Longitud aproximada: {road_stats.total_length_km:,.1f} km",
            f"- BBox lon/lat: [{road_stats.min_lon:.6f}, {road_stats.min_lat:.6f}, {road_stats.max_lon:.6f}, {road_stats.max_lat:.6f}]",
            "",
            "## Indice temporal",
            "",
            markdown_table(daily),
            "",
            "## Departamentos con mayor senal",
            "",
            markdown_table(department.head(10)),
            "",
            "## Municipios con mayor senal",
            "",
            markdown_table(municipality.head(10)),
            "",
            "## Eventos con mayor indice",
            "",
            markdown_table(
                top_events[
                    [
                        "datetime",
                        "department",
                        "municipality",
                        "mentions",
                        "severity_score",
                        "geo_confidence",
                        "social_road_event_index_0_100",
                        "spatial_level",
                        "observation",
                    ]
                ]
            ),
            "",
            "## Asociacion punto-segmento",
            "",
        ]
    )

    if road_matches.empty:
        lines.append("No hay eventos con coordenadas para asociar a segmentos.")
    else:
        lines.append(markdown_table(road_matches))

    lines.extend(
        [
            "",
            "## Advertencias",
            "",
            "- Con 100 registros y cuatro dias de observacion, el indice solo mide senal exploratoria; no mide riesgo real ni tasa de siniestralidad.",
            "- La mayoria de eventos no tiene coordenadas. La asociacion espacial fina requiere geocodificacion o coordenadas desde el origen.",
            "- El KMZ tiene geometria vial, pero no trae atributos operativos suficientes como tipo de via, sentido, jerarquia, municipio o fuente por segmento.",
            "- Las noticias agregadas o multiubicacion no deben forzarse a un unico punto vial.",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_results_txt(
    events: pd.DataFrame,
    mentions: pd.DataFrame,
    daily: pd.DataFrame,
    department: pd.DataFrame,
    municipality: pd.DataFrame,
    diagnostics: pd.DataFrame,
    variable_maturity: pd.DataFrame,
    exploratory_indicators: pd.DataFrame,
    road_stats: RoadStats,
    road_matches: pd.DataFrame,
    path: Path,
) -> None:
    top_events = events.sort_values("social_road_event_index_0_100", ascending=False).head(15)
    source_counts = counts_table(mentions["source"], "source") if not mentions.empty else pd.DataFrame()
    event_source_counts = counts_table(events["source"], "event_source")
    severity_counts = counts_table(events["severity_class"], "severity_class")
    spatial_counts = counts_table(events["spatial_level"], "spatial_level")
    readiness_counts = counts_table(events["metric_readiness_status"], "metric_readiness_status")
    hourly = (
        events.groupby("event_hour")
        .agg(events=("uuid", "count"), score_sum=("social_road_event_index_0_100", "sum"), severity_sum=("severity_score", "sum"))
        .reset_index()
        .sort_values("event_hour")
    )

    lines = [
        "RESULTADOS - ANALISIS DE NOTICIAS VIALES",
        "=" * 45,
        "",
        f"Generado: {datetime.now().isoformat(timespec='seconds')}",
        f"Datos de noticias: {NEWS_CSV}",
        f"Datos de red vial: {ROADS_KMZ}",
        "",
        "1. Enfoque metodologico cerrado",
        "-" * 35,
        "La prueba de concepto NO construye todavia el KPI de movilidad.",
        "Evalua si las noticias y reportes digitales pueden convertirse en fuente valida para variables, metricas exploratorias e insumos de un futuro sistema de KPIs de movilidad.",
        "La unidad principal es el evento vial deduplicado. La unidad secundaria es la mencion/noticia/post contenida en evidence.",
        "",
        "Cadena metodologica aplicada:",
        "noticia/post/RSS -> mencion -> evento deduplicado -> variable extraida -> metrica exploratoria -> evaluacion de madurez para KPI futuro.",
        "",
        "2. Que enfoque ya esta presente en el codigo actual",
        "-" * 48,
        "- Severidad preliminar inferida desde texto.",
        "- Amplificacion/respaldo informativo mediante numero de menciones y diversidad de fuentes.",
        "- Calidad espacial: coordenadas, direccion, municipio, departamento, texto o multiubicacion.",
        "- Diagnostico de eventos que requieren geocodificacion.",
        "- Agregacion temporal, departamental y municipal.",
        "- Caracterizacion de red vial KMZ.",
        "- Intento de asociacion evento-via solo cuando hay coordenadas.",
        "- Clasificacion de madurez para metricas futuras.",
        "",
        "3. Que falta para llegar a una POC de alto nivel",
        "-" * 45,
        "- Geocodificar direcciones textuales para convertir ADDRESS_TEXT en puntos defendibles.",
        "- Enriquecer la red vial con atributos OSM: highway, name, ref, oneway, lanes, maxspeed, surface, bridge, tunnel, access.",
        "- Crear identificadores persistentes de segmento vial.",
        "- Separar noticias multiubicacion en eventos individuales o excluirlas del analisis puntual.",
        "- Validar severidad contra fuente oficial si se pretende madurar a KPI formal.",
        "- Construir capa territorial oficial de municipios/departamentos para mapas coropleticos.",
        "- Definir umbrales institucionales antes de llamar KPI a cualquier indicador.",
        "",
        "4. Resumen ejecutivo de datos",
        "-" * 30,
        f"Eventos deduplicados: {len(events)}",
        f"Menciones expandidas: {len(mentions)}",
        f"Periodo observado: {events['datetime'].min()} a {events['datetime'].max()}",
        f"Accidentes de transito: {int((events['incident'] == 'TRAFFIC_ACCIDENT').sum())}",
        f"Otros eventos viales/sociales: {int((events['incident'] == 'OTHER').sum())}",
        f"Eventos con lesionados inferidos: {int(events['injury_flag'].sum())}",
        f"Eventos con fallecidos inferidos: {int(events['fatality_flag'].sum())}",
        f"Eventos con usuarios vulnerables inferidos: {int(events['vulnerable_user_flag'].sum())}",
        f"Registros con lat/lon: {int(events[['latitude', 'longitude']].notna().all(axis=1).sum())}",
        f"Eventos puntuales validables: {int((events['spatial_level'] == 'POINT').sum())}",
        f"Eventos con direccion + municipio: {int((events['spatial_level'] == 'ADDRESS_TEXT').sum())}",
        "",
        "5. Diagnostico de calidad y aprovechamiento",
        "-" * 44,
        markdown_table(diagnostics, max_col_width=150),
        "",
        "6. Indicadores exploratorios obtenidos",
        "-" * 40,
        markdown_table(exploratory_indicators, max_col_width=150),
        "",
        "7. Madurez de variables para metricas/KPIs futuros",
        "-" * 52,
        markdown_table(variable_maturity, max_col_width=150),
        "",
        "8. Distribucion por fuente de menciones",
        "-" * 38,
        markdown_table(source_counts, max_col_width=120),
        "",
        "9. Fuente principal registrada por evento",
        "-" * 42,
        markdown_table(event_source_counts, max_col_width=120),
        "",
        "10. Clasificacion de severidad preliminar",
        "-" * 44,
        markdown_table(severity_counts, max_col_width=120),
        "",
        "11. Calidad espacial de eventos",
        "-" * 35,
        markdown_table(spatial_counts, max_col_width=120),
        "",
        "12. Madurez por evento para metrica futura",
        "-" * 45,
        markdown_table(readiness_counts, max_col_width=120),
        "",
        "13. Serie diaria de senal noticiosa vial",
        "-" * 43,
        markdown_table(daily, max_col_width=120),
        "",
        "14. Serie horaria",
        "-" * 18,
        markdown_table(hourly, max_col_width=120),
        "",
        "15. Resultados por departamento",
        "-" * 33,
        markdown_table(department, max_col_width=120),
        "",
        "16. Resultados por municipio",
        "-" * 30,
        markdown_table(municipality, max_col_width=120),
        "",
        "17. Eventos con mayor senal exploratoria",
        "-" * 43,
        markdown_table(
            top_events[
                [
                    "uuid",
                    "datetime",
                    "incident",
                    "department",
                    "municipality",
                    "mentions",
                    "severity_class",
                    "severity_score",
                    "geo_confidence",
                    "data_quality_score",
                    "metric_readiness_status",
                    "social_road_event_index_0_100",
                    "observation",
                ]
            ],
            max_col_width=150,
        ),
        "",
        "18. Red vial base disponible",
        "-" * 30,
        f"Placemarks: {road_stats.placemarks}",
        f"LineStrings: {road_stats.line_strings}",
        f"Vertices: {road_stats.vertices}",
        f"Longitud aproximada: {road_stats.total_length_km:,.1f} km",
        f"BBox lon/lat: [{road_stats.min_lon:.6f}, {road_stats.min_lat:.6f}, {road_stats.max_lon:.6f}, {road_stats.max_lat:.6f}]",
        "Lectura: la red sirve como geometria base, pero requiere enriquecimiento de atributos para analisis vial de alto nivel.",
        "",
        "19. Asociacion evento-via obtenida",
        "-" * 36,
        markdown_table(road_matches, max_col_width=150) if not road_matches.empty else "No hay eventos puntuales suficientes para asociacion vial.",
        "",
        "20. Resultado esperado desde estos datos",
        "-" * 40,
        "Resultado fuerte de la etapa actual:",
        "- Demostrar que las noticias aportan variables temporales, semanticas, territoriales y de confiabilidad.",
        "- Demostrar que la mayor brecha esta en georreferenciacion puntual.",
        "- Identificar que la fuente sirve mejor hoy para metricas territoriales y de calidad de monitoreo que para KPI vial por segmento.",
        "- Construir una lista priorizada de eventos geocodificables.",
        "",
        "Resultado que NO debe afirmarse todavia:",
        "- No se debe decir que se mide accidentalidad real total.",
        "- No se debe decir que ya existe un KPI oficial de movilidad.",
        "- No se debe forzar una noticia sin coordenadas a un segmento vial.",
        "",
        "21. Conclusion tecnica",
        "-" * 24,
        "La fuente noticiosa si permite construir una metrica exploratoria importante: una metrica de senal vial noticiosa o presion vial reportada.",
        "Esa metrica puede alimentar el futuro sistema de KPIs de movilidad como fuente complementaria, especialmente para monitoreo temprano, severidad preliminar, usuarios vulnerables, priorizacion territorial y control de brechas de datos.",
        "Sin embargo, para convertirla en insumo robusto de KPI por via o corredor, primero hay que geocodificar direcciones, validar ubicaciones, enriquecer la red vial y mantener el estado de confianza de cada asociacion evento-via.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    events = build_enriched_events(NEWS_CSV)
    mentions = build_mentions_expanded(NEWS_CSV)
    daily, department, municipality = aggregate_indices(events)

    point_events = events[pd.notna(events["latitude"]) & pd.notna(events["longitude"])].copy()
    road_stats, road_matches = road_stats_and_matches(ROADS_KMZ, point_events)
    diagnostics = build_quality_diagnostics(events, mentions, road_matches)
    variable_maturity = build_variable_maturity(events)
    exploratory_indicators = build_exploratory_indicators(
        events,
        mentions,
        daily,
        department,
        municipality,
        road_matches,
    )

    events.to_csv(OUTPUT_DIR / "events_enriched.csv", index=False)
    mentions.to_csv(OUTPUT_DIR / "mentions_expanded.csv", index=False)
    daily.to_csv(OUTPUT_DIR / "daily_social_road_index.csv", index=False)
    department.to_csv(OUTPUT_DIR / "department_social_road_index.csv", index=False)
    municipality.to_csv(OUTPUT_DIR / "municipality_social_road_index.csv", index=False)
    diagnostics.to_csv(OUTPUT_DIR / "quality_diagnostics.csv", index=False)
    variable_maturity.to_csv(OUTPUT_DIR / "variable_maturity.csv", index=False)
    exploratory_indicators.to_csv(OUTPUT_DIR / "exploratory_indicators.csv", index=False)
    road_matches.to_csv(OUTPUT_DIR / "road_matches.csv", index=False)
    write_geojson(events, OUTPUT_DIR / "event_points.geojson")
    write_summary(
        events,
        daily,
        department,
        municipality,
        road_stats,
        road_matches,
        OUTPUT_DIR / "poc_summary.md",
    )

    events.to_csv(RESULTS_DIR / "base_eventos_normalizada.csv", index=False)
    mentions.to_csv(RESULTS_DIR / "base_menciones_expandida.csv", index=False)
    diagnostics.to_csv(RESULTS_DIR / "diagnostico_calidad_datos.csv", index=False)
    variable_maturity.to_csv(RESULTS_DIR / "madurez_variables.csv", index=False)
    exploratory_indicators.to_csv(RESULTS_DIR / "indicadores_exploratorios.csv", index=False)
    road_matches.to_csv(RESULTS_DIR / "eventos_asociados_red_vial.csv", index=False)
    daily.to_csv(RESULTS_DIR / "serie_diaria_senal_vial.csv", index=False)
    department.to_csv(RESULTS_DIR / "resultados_departamento.csv", index=False)
    municipality.to_csv(RESULTS_DIR / "resultados_municipio.csv", index=False)
    write_geojson(events, RESULTS_DIR / "eventos_georreferenciables.geojson")
    write_results_txt(
        events,
        mentions,
        daily,
        department,
        municipality,
        diagnostics,
        variable_maturity,
        exploratory_indicators,
        road_stats,
        road_matches,
        RESULTS_DIR / "resultados_noticias.txt",
    )

    print(f"Eventos procesados: {len(events)}")
    print(f"Menciones expandidas: {len(mentions)}")
    print(f"Eventos con coordenadas: {len(point_events)}")
    print(f"Salidas: {OUTPUT_DIR}")
    print(f"Resultados: {RESULTS_DIR}")


if __name__ == "__main__":
    main()
