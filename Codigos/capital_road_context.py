#!/usr/bin/env python3
"""
Zoom capitalino y extraccion preliminar de contexto vial desde noticias.

Este script implementa el primer paso antes de OSM/geocodificacion:
- Identifica eventos del area capitalina / San Salvador metropolitano.
- Extrae candidatos de via, corredor, interseccion y kilometraje desde texto.
- Clasifica el tipo de contexto vial disponible.
- Produce resultados en Results/News.

No asigna eventos a segmentos viales todavia. Esa etapa requiere coordenadas
geocodificadas y una red vial OSM enriquecida.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from social_road_index_poc import (
    NEWS_CSV,
    RESULTS_DIR,
    build_enriched_events,
    markdown_table,
    normalize_text,
    pct,
)


ROOT = Path(__file__).resolve().parents[1]
BASE_EVENTS = RESULTS_DIR / "base_eventos_normalizada.csv"

CAPITAL_CORE_MUNICIPALITIES = {
    "san salvador",
    "san salvador centro",
    "san salvador este",
    "san salvador oeste",
    "san salvador norte",
    "soyapango",
    "ciudad delgado",
    "mejicanos",
    "apopa",
    "nejapa",
    "guazapa",
    "cuscatancingo",
    "ayutuxtepeque",
    "ilopango",
    "san martin",
    "tonacatepeque",
    "san marcos",
    "panchimalco",
    "santo tomas",
    "santiago texacuangos",
}

CAPITAL_EXTENDED_MUNICIPALITIES = {
    "santa tecla",
    "antiguo cuscatlan",
    "la libertad sur",
    "merliot",
}

CAPITAL_TEXT_HINTS = {
    "san salvador",
    "soyapango",
    "ciudad delgado",
    "mejicanos",
    "apopa",
    "nejapa",
    "guazapa",
    "zacamil",
    "metrocentro",
    "fenadesal",
    "terminal de oriente",
    "terminal del sur",
    "salvador del mundo",
    "san jacinto",
    "escalon",
    "zacamil",
    "universidad de el salvador",
    "bulevar del ejercito",
    "boulevard del ejercito",
    "carretera de oro",
    "boulevard constitucion",
    "bulevar constitucion",
    "avenida bernal",
    "autopista norte",
    "troncal del norte",
}

KNOWN_CORRIDORS = {
    "carretera troncal del norte": [
        "carretera troncal del norte",
        "troncal del norte",
    ],
    "carretera panamericana": [
        "carretera panamericana",
        "panamericana",
    ],
    "tramo los chorros": [
        "tramo los chorros",
        "los chorros",
    ],
    "bulevar del ejercito": [
        "bulevar del ejercito",
        "boulevard del ejercito",
    ],
    "carretera de oro": [
        "carretera de oro",
    ],
    "boulevard constitucion": [
        "boulevard constitucion",
        "bulevar constitucion",
        "el constitucion",
    ],
    "autopista a comalapa": [
        "autopista a comalapa",
        "autopista comalapa",
    ],
    "bulevar venezuela": [
        "bulevar venezuela",
        "boulevard venezuela",
        "entrada al venezuela",
    ],
    "avenida bernal": [
        "avenida bernal",
        "av bernal",
    ],
    "calle agua caliente": [
        "calle agua caliente",
        "calle de agua caliente",
    ],
    "calle antigua a tonacatepeque": [
        "calle antigua a tonacatepeque",
        "calle tonacatepeque",
    ],
    "calle antigua a nejapa": [
        "calle antigua a nejapa",
    ],
    "carretera a quezaltepeque": [
        "carretera a quezaltepeque",
    ],
    "carretera a los planes de renderos": [
        "carretera a los planes de renderos",
        "planes de renderos",
    ],
    "calle los sisimiles": [
        "calle los sisimiles",
        "los sisimiles",
    ],
    "autopista norte": [
        "autopista norte",
    ],
    "49 avenida sur": [
        "49 av sur",
        "49 avenida sur",
    ],
    "59 avenida sur": [
        "59 avenida sur",
    ],
    "75 avenida norte": [
        "75 avenida norte",
        "calle 75 avenida norte",
    ],
    "29 avenida norte": [
        "29 avenida norte",
        "29 av nte",
        "29 av. nte",
    ],
    "10 avenida norte": [
        "10 avenida norte",
        "10a avenida norte",
        "10ª avenida norte",
        "10. avenida norte",
    ],
    "calle buenos aires": [
        "calle buenos aires",
    ],
    "calle ramon belloso": [
        "calle ramon belloso",
    ],
    "avenida barberena": [
        "avenida barberena",
    ],
    "calle cuba": [
        "calle cuba",
    ],
    "bulevar merliot": [
        "bulevar merliot",
        "boulevard merliot",
    ],
    "bulevar sur": [
        "bulevar sur",
        "boulevard sur",
    ],
    "periferico claudia lars": [
        "periferico claudia lars",
        "bulevar claudia lars",
        "boulevard claudia lars",
    ],
    "carretera al puerto de la libertad": [
        "carretera al puerto de la libertad",
        "carretera al puerto",
    ],
}


ROAD_PHRASE_PATTERN = re.compile(
    r"\b(?:carretera|autopista|bulevar|boulevard|avenida|av\.?|calle|ruta|periferico|bypass|troncal)"
    r"\s+(?:[a-z0-9ªº\.\-/]+\s*){0,7}",
    flags=re.IGNORECASE,
)

KM_PATTERN = re.compile(
    r"\b(?:kilometro|km)\s*([0-9]+(?:\s*(?:1/2|1/4|3/4|½|¼|¾))?)",
    flags=re.IGNORECASE,
)


def normalized_value(value: Any) -> str:
    return normalize_text(value)


def load_events() -> pd.DataFrame:
    if BASE_EVENTS.exists():
        return pd.read_csv(BASE_EVENTS)
    return build_enriched_events(NEWS_CSV)


def combined_text(row: pd.Series) -> str:
    parts = [
        row.get("address"),
        row.get("observation"),
        row.get("municipality"),
        row.get("department"),
    ]
    return " ".join(normalized_value(part) for part in parts if pd.notna(part))


def capital_scope(row: pd.Series, text: str) -> tuple[bool, str, str]:
    municipality = normalized_value(row.get("municipality"))
    department = normalized_value(row.get("department"))

    if municipality in CAPITAL_CORE_MUNICIPALITIES:
        return True, "AMSS_CORE", "municipality_core"
    if municipality in CAPITAL_EXTENDED_MUNICIPALITIES:
        return True, "AMSS_EXTENDED", "municipality_extended"
    if department == "san salvador":
        return True, "SAN_SALVADOR_DEPARTMENT", "department_san_salvador"
    if any(hint in text for hint in CAPITAL_TEXT_HINTS):
        return True, "CAPITAL_TEXT_HINT", "text_hint"
    return False, "OUTSIDE_CAPITAL_SCOPE", "outside"


def capital_subarea(row: pd.Series, text: str) -> str:
    municipality = normalized_value(row.get("municipality"))
    if municipality in {"soyapango", "ilopango", "san martin", "san salvador este"}:
        return "ESTE"
    if municipality in {"apopa", "nejapa", "guazapa", "ciudad delgado", "cuscatancingo", "ayutuxtepeque"}:
        return "NORTE"
    if municipality in {"mejicanos"} or "zacamil" in text:
        return "NORTE-OESTE"
    if municipality in {"santa tecla", "antiguo cuscatlan", "la libertad sur"} or any(term in text for term in ["merliot", "escalon", "salvador del mundo", "constitucion"]):
        return "OESTE"
    if any(term in text for term in ["san jacinto", "planes de renderos", "panchimalco", "terminal del sur", "comalapa"]):
        return "SUR"
    if municipality in {"san salvador", "san salvador centro"} or any(term in text for term in ["centro de san salvador", "metrocentro", "avenida bernal"]):
        return "CENTRO"
    if "carretera de oro" in text or "bulevar del ejercito" in text or "boulevard del ejercito" in text:
        return "ESTE"
    if "troncal del norte" in text or "autopista norte" in text:
        return "NORTE"
    return "CAPITAL_SIN_SUBAREA"


def clean_road_phrase(phrase: str) -> str:
    phrase = normalized_value(phrase)
    phrase = re.split(
        r"\b(?:accidente|percance|colision|choque|atropello|retiro|genera|involucra|deja|en|a la altura|frente|cerca|cercanias|inmediaciones|sentido|sector|antes|despues|rumbo|hacia|sobre|por)\b",
        phrase,
    )[0]
    phrase = re.sub(r"\s+", " ", phrase).strip(" ,.;:-")
    return phrase


def extract_known_corridors(text: str) -> list[str]:
    matches = []
    for canonical, aliases in KNOWN_CORRIDORS.items():
        if any(alias in text for alias in aliases):
            matches.append(canonical)
    return sorted(set(matches))


def extract_generic_road_phrases(text: str) -> list[str]:
    phrases = []
    for match in ROAD_PHRASE_PATTERN.finditer(text):
        phrase = clean_road_phrase(match.group(0))
        if len(phrase.split()) >= 2:
            phrases.append(phrase)
    return sorted(set(phrases))


def dedupe_road_names(road_names: list[str]) -> list[str]:
    clean_names = [name for name in road_names if name]
    result = []
    for name in sorted(set(clean_names), key=lambda value: (len(value), value)):
        if any(name == existing or name in existing or existing in name for existing in result):
            if not any(name == existing or name in existing for existing in result):
                result.append(name)
            continue
        result.append(name)
    return sorted(result)


def extract_km_references(text: str) -> list[str]:
    refs = []
    for match in KM_PATTERN.finditer(text):
        refs.append(f"km {match.group(1).replace(' ', '')}")
    return sorted(set(refs))


def extract_intersection(text: str, road_candidates: list[str]) -> str:
    patterns = [
        r"interseccion de la? (.+?) y la? (.+?)(?:,|;| en |$)",
        r"interseccion de (.+?) y (.+?)(?:,|;| en |$)",
        r"(.+? avenida .+?) y (.+? calle .+?)(?:,|;| en |$)",
        r"(.+? calle .+?) y (.+? avenida .+?)(?:,|;| en |$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            a = clean_road_phrase(match.group(1))
            b = clean_road_phrase(match.group(2))
            if a and b and a != b:
                return f"{a} / {b}"

    if len(road_candidates) >= 2 and any(marker in text for marker in [" interseccion ", " esquina "]):
        return f"{road_candidates[0]} / {road_candidates[1]}"
    return ""


def classify_road_type(road_name: str, text: str) -> str:
    value = normalized_value(road_name or text)
    if any(term in value for term in ["autopista", "carretera", "troncal", "panamericana", "ruta", "periferico", "bypass"]):
        return "NACIONAL_ESTRUCTURANTE"
    if any(term in value for term in ["bulevar", "boulevard"]):
        return "ARTERIAL_URBANA"
    if "avenida" in value or re.search(r"\bav\b", value):
        return "ARTERIAL_O_COLECTORA_URBANA"
    if "calle" in value:
        return "LOCAL_O_COLECTORA_URBANA"
    if any(term in value for term in ["desvio", "retorno", "redondel", "semaforo"]):
        return "NODO_INTERSECCION"
    return "NO_CLASIFICADA"


def road_context_level(road_names: list[str], intersection: str, km_refs: list[str]) -> str:
    if intersection:
        return "INTERSECTION_TEXT"
    if km_refs and road_names:
        return "KM_REFERENCE_ON_ROAD"
    if road_names:
        return "ROAD_NAME_EXTRACTED"
    if km_refs:
        return "KM_REFERENCE_ONLY"
    return "NO_ROAD_CONTEXT"


def enrich_context(events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in events.iterrows():
        text = combined_text(row)
        is_capital, scope, scope_reason = capital_scope(row, text)
        subarea = capital_subarea(row, text) if is_capital else "OUTSIDE"

        known = extract_known_corridors(text)
        generic = extract_generic_road_phrases(text)
        road_names = dedupe_road_names(known + generic)
        km_refs = extract_km_references(text)
        intersection = extract_intersection(text, road_names)
        context_level = road_context_level(road_names, intersection, km_refs)
        primary_road = road_names[0] if road_names else ""
        road_type = classify_road_type(primary_road, text)
        analysis_status = "OUTSIDE_CAPITAL_SCOPE"
        if is_capital:
            analysis_status = "ELIGIBLE"
            if bool(row.get("aggregate_news_flag")):
                analysis_status = "CONTEXT_ONLY_MULTI_LOCATION"
            elif bool(row.get("location_conflict_flag")):
                analysis_status = "REVIEW_LOCATION_CONFLICT"

        enriched = row.to_dict()
        enriched.update(
            {
                "capital_area_flag": is_capital,
                "capital_scope": scope,
                "capital_scope_reason": scope_reason,
                "capital_subarea": subarea,
                "capital_analysis_status": analysis_status,
                "capital_analysis_eligible": analysis_status == "ELIGIBLE",
                "road_name_candidates": "; ".join(road_names),
                "primary_road_candidate": primary_road,
                "corridor_candidate": known[0] if known else primary_road,
                "intersection_candidate": intersection,
                "km_references": "; ".join(km_refs),
                "road_context_level": context_level,
                "road_type_candidate": road_type,
                "road_context_text": text[:1000],
            }
        )
        rows.append(enriched)
    return pd.DataFrame(rows)


def aggregate_capital_outputs(context: pd.DataFrame) -> dict[str, pd.DataFrame]:
    capital_related = context[context["capital_area_flag"]].copy()
    capital = context[context["capital_analysis_eligible"]].copy()
    with_road = capital[capital["road_context_level"] != "NO_ROAD_CONTEXT"].copy()

    outputs = {}
    outputs["capital_by_scope"] = counts(capital_related["capital_scope"], "capital_scope")
    outputs["capital_analysis_status"] = counts(capital_related["capital_analysis_status"], "capital_analysis_status")
    outputs["capital_by_subarea"] = counts(capital["capital_subarea"], "capital_subarea")
    outputs["capital_by_municipality"] = (
        capital.groupby(["department_norm", "municipality_norm"], dropna=False)
        .agg(
            events=("uuid", "count"),
            severity_sum=("severity_score", "sum"),
            mentions_sum=("mentions", "sum"),
            avg_metric_readiness=("metric_readiness_score_0_100", "mean"),
            address_text_events=("spatial_level", lambda s: int((s == "ADDRESS_TEXT").sum())),
            road_context_events=("road_context_level", lambda s: int((s != "NO_ROAD_CONTEXT").sum())),
        )
        .reset_index()
        .sort_values(["events", "severity_sum"], ascending=False)
    )
    outputs["capital_road_context_level"] = counts(capital["road_context_level"], "road_context_level")
    outputs["capital_road_type"] = counts(capital["road_type_candidate"], "road_type_candidate")
    outputs["capital_corridors"] = (
        with_road.assign(corridor=with_road["corridor_candidate"].replace("", pd.NA))
        .dropna(subset=["corridor"])
        .groupby("corridor", dropna=False)
        .agg(
            events=("uuid", "count"),
            severity_sum=("severity_score", "sum"),
            mentions_sum=("mentions", "sum"),
            injury_events=("injury_flag", "sum"),
            fatality_events=("fatality_flag", "sum"),
            vulnerable_events=("vulnerable_user_flag", "sum"),
            address_text_events=("spatial_level", lambda s: int((s == "ADDRESS_TEXT").sum())),
        )
        .reset_index()
        .sort_values(["events", "severity_sum"], ascending=False)
    )
    outputs["all_road_context_level"] = counts(context["road_context_level"], "road_context_level")
    return outputs


def counts(series: pd.Series, label: str) -> pd.DataFrame:
    table = series.fillna("SIN_DATO").value_counts(dropna=False).reset_index()
    table.columns = [label, "events"]
    total = table["events"].sum()
    table["percent"] = table["events"].map(lambda n: pct(n, total))
    return table


def write_summary(context: pd.DataFrame, outputs: dict[str, pd.DataFrame], path: Path) -> None:
    capital_related = context[context["capital_area_flag"]].copy()
    capital = context[context["capital_analysis_eligible"]].copy()
    with_road = capital[capital["road_context_level"] != "NO_ROAD_CONTEXT"].copy()
    top_capital = capital.sort_values("social_road_event_index_0_100", ascending=False).head(15)

    lines = [
        "ZOOM CAPITALINO - CONTEXTO VIAL EXTRAIDO DESDE NOTICIAS",
        "=" * 62,
        "",
        "1. Alcance",
        "-" * 10,
        "Este resultado implementa el primer paso concreto: extraer territorialidad capitalina y contexto vial textual desde las noticias.",
        "No hace geocodificacion, no descarga OSM y no asigna segmentos viales. Prepara los datos para esas etapas.",
        "",
        "2. Resumen",
        "-" * 10,
        f"Eventos totales analizados: {len(context)}",
        f"Eventos relacionados con alcance capitalino/ampliado: {len(capital_related)} ({pct(len(capital_related), len(context))}%)",
        f"Eventos elegibles para zoom operativo capitalino: {len(capital)} ({pct(len(capital), len(context))}%)",
        f"Eventos capitalinos con algun contexto vial textual: {len(with_road)} ({pct(len(with_road), len(capital))}%)",
        f"Eventos capitalinos con direccion + municipio: {int((capital['spatial_level'] == 'ADDRESS_TEXT').sum())}",
        f"Eventos capitalinos con coordenada puntual validable: {int((capital['spatial_level'] == 'POINT').sum())}",
        "",
        "3. Lectura tecnica",
        "-" * 18,
        "El valor principal esta en que muchos eventos no tienen coordenadas, pero si contienen nombres de vias, corredores, intersecciones o referencias kilometricas.",
        "Esto permite crear una capa preliminar de contexto vial y priorizar geocodificacion por corredores.",
        "La clasificacion de tipo de via es candidata textual, no atributo OSM confirmado.",
        "",
        "4. Eventos por alcance capitalino",
        "-" * 34,
        markdown_table(outputs["capital_by_scope"], max_col_width=120),
        "",
        "4.1 Estado de elegibilidad capitalina",
        "-" * 39,
        markdown_table(outputs["capital_analysis_status"], max_col_width=120),
        "",
        "5. Eventos por subarea capitalina",
        "-" * 35,
        markdown_table(outputs["capital_by_subarea"], max_col_width=120),
        "",
        "6. Eventos por municipio capitalino",
        "-" * 38,
        markdown_table(outputs["capital_by_municipality"], max_col_width=120),
        "",
        "7. Nivel de contexto vial en capital",
        "-" * 40,
        markdown_table(outputs["capital_road_context_level"], max_col_width=120),
        "",
        "8. Tipo de via candidato en capital",
        "-" * 39,
        markdown_table(outputs["capital_road_type"], max_col_width=120),
        "",
        "9. Corredores/vias candidatas con mayor aparicion",
        "-" * 52,
        markdown_table(outputs["capital_corridors"].head(25), max_col_width=140),
        "",
        "10. Eventos capitalinos con mayor senal",
        "-" * 41,
        markdown_table(
            top_capital[
                [
                    "uuid",
                    "datetime",
                    "department",
                    "municipality",
                    "capital_subarea",
                    "severity_class",
                    "mentions",
                    "social_road_event_index_0_100",
                    "road_context_level",
                    "road_type_candidate",
                    "corridor_candidate",
                    "intersection_candidate",
                    "km_references",
                    "observation",
                ]
            ],
            max_col_width=150,
        ),
        "",
        "11. Que se puede hacer con esto",
        "-" * 32,
        "- Priorizar geocodificacion de eventos capitalinos por corredor.",
        "- Construir un ranking preliminar de vias/corredores mencionados.",
        "- Separar analisis por tipo de via candidato: estructurante, arterial, local/colectora.",
        "- Preparar el cruce posterior con OSM para confirmar highway/name/ref/oneway/lanes/maxspeed.",
        "",
        "12. Siguiente paso recomendado",
        "-" * 32,
        "Traer red OSM enriquecida del area capitalina y hacer dos cruces: match textual por name/ref y geocodificacion de direcciones para match espacial punto-segmento.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    events = load_events()
    context = enrich_context(events)
    outputs = aggregate_capital_outputs(context)

    capital = context[context["capital_analysis_eligible"]].copy()

    context.to_csv(RESULTS_DIR / "road_context_extracted.csv", index=False)
    capital.to_csv(RESULTS_DIR / "capital_events.csv", index=False)
    outputs["capital_by_municipality"].to_csv(RESULTS_DIR / "capital_municipality_summary.csv", index=False)
    outputs["capital_corridors"].to_csv(RESULTS_DIR / "capital_corridor_candidates.csv", index=False)
    outputs["capital_road_type"].to_csv(RESULTS_DIR / "capital_road_type_summary.csv", index=False)
    outputs["capital_road_context_level"].to_csv(RESULTS_DIR / "capital_road_context_level_summary.csv", index=False)
    write_summary(context, outputs, RESULTS_DIR / "capital_road_context_summary.txt")

    print(f"Eventos analizados: {len(context)}")
    print(f"Eventos capitalinos elegibles: {len(capital)}")
    print(f"Eventos capitalinos con contexto vial: {int((capital['road_context_level'] != 'NO_ROAD_CONTEXT').sum())}")
    print(f"Resultados: {RESULTS_DIR}")


if __name__ == "__main__":
    main()
