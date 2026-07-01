#!/usr/bin/env python3
"""
Pipeline principal para Data/News/incidentes.csv.

Este script reemplaza el foco previo en ultimas_100_noticias.csv y genera
resultados independientes en Results/News/Incidentes.

Objetivo metodologico:
- Mantener evento, mencion y snapshot de engagement como unidades separadas.
- Analizar integridad espacial sin excluir registros problematicos.
- Construir capas geoespaciales y pesos de heatmap.
- Enriquecer puntos con red OSM disponible para AMSS.
- Calcular una metrica exploratoria, no un KPI final.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
INPUT_CSV = ROOT / "Data" / "News" / "incidentes.csv"
RESULTS_DIR = ROOT / "Results" / "News" / "Incidentes"
OSM_SEGMENTS_PATH = ROOT / "Data" / "Processed" / "osm_roads_san_salvador" / "osm_road_segments.csv"
OSM_DEPARTMENTS_DIR = ROOT / "Data" / "Processed" / "osm_roads_departments"
OSM_NATIONAL_DIR = ROOT / "Data" / "Processed" / "osm_roads_nacional"
OSM_NATIONAL_SEGMENTS_PATH = OSM_NATIONAL_DIR / "osm_road_segments.csv"
OSM_NATIONAL_COVERAGE_PATH = OSM_NATIONAL_DIR / "diagnostico_cobertura_osm.csv"

# Control preliminar de integridad. No excluye puntos; solo etiqueta.
EL_SALVADOR_BBOX = (13.0, -90.2, 14.6, -87.6)  # south, west, north, east
AMSS_BBOX = (13.55, -89.42, 13.92, -89.00)


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


KNOWN_CORRIDORS = {
    "carretera troncal del norte": ["carretera troncal del norte", "troncal del norte"],
    "carretera panamericana": ["carretera panamericana", "panamericana"],
    "tramo los chorros": ["tramo los chorros", "los chorros"],
    "bulevar del ejercito": ["bulevar del ejercito", "boulevard del ejercito"],
    "carretera de oro": ["carretera de oro"],
    "boulevard constitucion": ["boulevard constitucion", "bulevar constitucion", "el constitucion"],
    "autopista a comalapa": ["autopista a comalapa", "autopista comalapa", "carretera a comalapa"],
    "bulevar venezuela": ["bulevar venezuela", "boulevard venezuela", "entrada al venezuela"],
    "avenida bernal": ["avenida bernal", "av bernal"],
    "autopista norte": ["autopista norte"],
    "carretera a sonsonate": ["carretera a sonsonate", "carretera hacia sonsonate"],
    "carretera a santa ana": ["carretera a santa ana", "carretera hacia santa ana"],
    "carretera al puerto de la libertad": [
        "carretera al puerto de la libertad",
        "carretera al puerto",
        "carretera del puerto de la libertad",
    ],
    "paseo general escalon": ["paseo general escalon"],
    "calle a mariona": ["calle a mariona", "calle de mariona"],
    "avenida jerusalen": ["avenida jerusalen"],
    "ruta de paz": ["ruta de paz"],
    "periferico gerardo barrios": ["periferico gerardo barrios"],
}


DEPARTMENT_SLUGS = {
    "CABAÑAS": "cabanas",
    "CHALATENANGO": "chalatenango",
    "CUSCATLÁN": "cuscatlan",
    "LA LIBERTAD": "la_libertad",
    "LA PAZ": "la_paz",
    "MORAZÁN": "morazan",
    "SAN MIGUEL": "san_miguel",
    "SAN SALVADOR": "san_salvador",
    "SAN VICENTE": "san_vicente",
    "SANTA ANA": "santa_ana",
    "SONSONATE": "sonsonate",
    "USULUTÁN": "usulutan",
    "AHUACHAPÁN": "ahuachapan",
    "LA UNIÓN": "la_union",
}


CORRIDOR_NORM_RULES = [
    {
        "norm": "Carretera Panamericana",
        "refs": ["ca 1", "ca 1w", "ca1", "ca1w"],
        "aliases": [
            "carretera panamericana",
            "panamericana",
            "boulevard del ejercito",
            "bulevar del ejercito",
            "tramo los chorros",
            "los chorros",
            "ca 1",
            "ca 1w",
        ],
    },
    {
        "norm": "Autopista a Comalapa",
        "refs": ["rn 5", "rn5"],
        "aliases": [
            "autopista a comalapa",
            "autopista comalapa",
            "carretera a comalapa",
            "carretera comalapa",
            "rn 5",
        ],
    },
    {
        "norm": "Carretera al Puerto de La Libertad",
        "refs": [],
        "aliases": [
            "carretera al puerto de la libertad",
            "carretera al puerto",
            "carretera del puerto de la libertad",
            "carretera que conduce del puerto de la libertad",
            "carretera que conecta el puerto de la libertad",
            "puerto de la libertad hacia santa tecla",
            "puerto de la libertad con santa tecla",
        ],
    },
    {
        "norm": "Paseo General Escalón",
        "refs": [],
        "aliases": ["paseo general escalon", "paseo escalon", "general escalon"],
    },
    {
        "norm": "Carretera Quezaltepeque - San Juan Opico",
        "refs": ["lib 25", "lib25"],
        "aliases": [
            "calle de tacachico a san juan opico",
            "calle tacachico a san juan opico",
            "carretera de quezaltepeque a san juan opico",
            "quezaltepeque con san juan opico",
            "quezaltepeque a san juan opico",
            "lib 25",
        ],
    },
]


DEPARTMENT_ALIASES = {
    "": "SIN_DEPTO",
    "cabanas": "CABAÑAS",
    "chalatenango": "CHALATENANGO",
    "cuscatlan": "CUSCATLÁN",
    "la libertad": "LA LIBERTAD",
    "la paz": "LA PAZ",
    "morazan": "MORAZÁN",
    "san miguel": "SAN MIGUEL",
    "san salvador": "SAN SALVADOR",
    "san vicente": "SAN VICENTE",
    "santa ana": "SANTA ANA",
    "sonsonate": "SONSONATE",
    "usulutan": "USULUTÁN",
}


MUNICIPALITY_ALIASES = {
    "": "SIN_MUNICIPIO",
    "antiguo cuscatlan": "Antiguo Cuscatlán",
    "armenia": "Armenia",
    "candelaria de la frontera": "Candelaria de la Frontera",
    "chalatenango": "Chalatenango",
    "ciudad arce": "Ciudad Arce",
    "ciudad delgado": "Ciudad Delgado",
    "colon": "Colón",
    "cuscatancingo": "Cuscatancingo",
    "cuscatlan norte": "Cuscatlán Norte",
    "el barillo": "El Barillo",
    "el transito": "El Tránsito",
    "ilobasco": "Ilobasco",
    "ilopango": "Ilopango",
    "izalco": "Izalco",
    "la libertad": "La Libertad",
    "la libertad centro": "La Libertad Centro",
    "la libertad sur": "La Libertad Sur",
    "la paz centro": "La Paz Centro",
    "los naranjos": "Los Naranjos",
    "los planes de renderos": "Los Planes de Renderos",
    "mejicanos": "Mejicanos",
    "nejapa": "Nejapa",
    "quezaltepeque": "Quezaltepeque",
    "san carlos": "San Carlos",
    "san francisco gotera": "San Francisco Gotera",
    "san juan opico": "San Juan Opico",
    "san luis talpa": "San Luis Talpa",
    "san miguel": "San Miguel",
    "san pablo tacachico": "San Pablo Tacachico",
    "san pedro perulapan": "San Pedro Perulapán",
    "san rafael cedros": "San Rafael Cedros",
    "san salvador": "San Salvador",
    "san salvador centro": "San Salvador Centro",
    "san salvador este": "San Salvador Este",
    "san salvador sur": "San Salvador Sur",
    "san vicente norte": "San Vicente Norte",
    "santa ana": "Santa Ana",
    "santa ana centro": "Santa Ana Centro",
    "santa maria": "Santa María",
    "santa tecla": "Santa Tecla",
    "santiago de maria": "Santiago de María",
    "santiago nonualco": "Santiago Nonualco",
    "sonsonate": "Sonsonate",
    "soyapango": "Soyapango",
}


ROAD_PHRASE_PATTERN = re.compile(
    r"\b(?:carretera|autopista|bulevar|boulevard|avenida|av\.?|calle|ruta|periferico|bypass|troncal|alameda|paseo)"
    r"\s+(?:[a-z0-9ªº\.\-/]+\s*){0,9}",
    flags=re.IGNORECASE,
)

ROAD_KIND_TOKENS = {
    "carretera",
    "autopista",
    "bulevar",
    "boulevard",
    "avenida",
    "av",
    "calle",
    "ruta",
    "periferico",
    "bypass",
    "troncal",
    "alameda",
    "paseo",
}

ROAD_FILLER_TOKENS = {"que", "conduce", "de", "del", "la", "las", "los", "el", "a", "al", "hacia", "y", "en"}

KM_PATTERN = re.compile(
    r"\b(?:kilometro|km)\s*([0-9]+(?:\s*(?:1/2|1/4|3/4|½|¼|¾))?)",
    flags=re.IGNORECASE,
)


def ensure_dirs() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)


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
    text = text.replace("º", "").replace("ª", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def compact_text(value: Any) -> str:
    text = normalize_text(value)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def title_case_spanish(value: str) -> str:
    lowercase_words = {"de", "del", "la", "las", "los", "y", "el"}
    parts = []
    for idx, token in enumerate(compact_text(value).split()):
        if idx > 0 and token in lowercase_words:
            parts.append(token)
        else:
            parts.append(token.capitalize())
    return " ".join(parts)


def title_case_corridor(value: Any) -> str:
    text = compact_text(value)
    return title_case_spanish(text) if text else ""


def slugify(value: Any) -> str:
    return compact_text(value).replace(" ", "_")


def normalize_department_name(value: Any) -> str:
    key = compact_text(value)
    return DEPARTMENT_ALIASES.get(key, title_case_spanish(key).upper() if key else "SIN_DEPTO")


def normalize_municipality_name(value: Any) -> str:
    key = compact_text(value)
    return MUNICIPALITY_ALIASES.get(key, title_case_spanish(key) if key else "SIN_MUNICIPIO")


def territory_normalization_status(department: Any, municipality: Any) -> str:
    has_department = nonempty(department)
    has_municipality = nonempty(municipality)
    if has_department and has_municipality:
        return "DEPARTMENT_AND_MUNICIPALITY"
    if has_department:
        return "DEPARTMENT_ONLY"
    if has_municipality:
        return "MUNICIPALITY_ONLY"
    return "NO_TERRITORY_FIELDS"


def corridor_rule_match(text: str, field: str) -> tuple[str, str] | tuple[str, None]:
    text_norm = compact_text(text)
    if not text_norm:
        return "", None
    for rule in CORRIDOR_NORM_RULES:
        for value in rule.get(field, []):
            candidate = compact_text(value)
            if candidate and re.search(rf"(^|\s){re.escape(candidate)}(\s|$)", text_norm):
                return rule["norm"], field.upper()
    return "", None


def infer_corridor_norm_from_osm(row: pd.Series) -> tuple[str, str]:
    osm_ref = compact_text(row.get("nearest_osm_ref", ""))
    osm_name = compact_text(row.get("nearest_osm_name", ""))
    ref_norm, ref_source = corridor_rule_match(osm_ref, "refs")
    if ref_norm:
        return ref_norm, "OSM_REF"
    name_norm, _ = corridor_rule_match(osm_name, "aliases")
    if name_norm:
        return name_norm, "OSM_NAME"
    return title_case_corridor(osm_name), "OSM_NAME" if osm_name else "UNRESOLVED"


def infer_corridor_norm_from_text(row: pd.Series) -> tuple[str, str]:
    text = " ".join(
        [
            str(row.get("corridor_candidate") or ""),
            str(row.get("road_name_candidates") or ""),
            str(row.get("address") or ""),
            str(row.get("observation") or ""),
        ]
    )
    ref_norm, _ = corridor_rule_match(text, "refs")
    if ref_norm:
        return ref_norm, "TEXT_ALIAS"
    alias_norm, _ = corridor_rule_match(text, "aliases")
    if alias_norm:
        return alias_norm, "TEXT_ALIAS"
    candidate = row.get("corridor_candidate")
    candidate_key = compact_text(candidate)
    if candidate_key in KNOWN_CORRIDORS:
        return title_case_corridor(candidate), "MANUAL_RULE"
    return title_case_corridor(candidate), "TEXT_ALIAS" if nonempty(candidate) else "UNRESOLVED"


def is_strong_text_corridor(text_norm: str, text_source: str) -> bool:
    if text_source == "MANUAL_RULE":
        return True
    text_key = compact_text(text_norm)
    if text_key in KNOWN_CORRIDORS:
        return True
    return any(compact_text(rule["norm"]) == text_key for rule in CORRIDOR_NORM_RULES)


def is_intersection_like(row: pd.Series) -> bool:
    text = compact_text(" ".join([str(row.get("address") or ""), str(row.get("observation") or ""), str(row.get("corridor_candidate") or "")]))
    return bool(row.get("intersection_candidate")) or " interseccion " in f" {text} " or " y " in f" {text} "


def resolve_corridor_norm(row: pd.Series) -> dict[str, Any]:
    text_norm, text_source = infer_corridor_norm_from_text(row)
    osm_norm, osm_source = infer_corridor_norm_from_osm(row)
    distance = safe_float(row.get("nearest_osm_distance_m"))
    osm_status = str(row.get("osm_match_status") or "")
    has_osm = nonempty(row.get("nearest_osm_name")) or nonempty(row.get("nearest_osm_ref"))
    spatial_reasonable = osm_status in {"SPATIAL_OSM_HIGH", "SPATIAL_OSM_MEDIUM"}

    if text_norm and osm_norm and text_norm == osm_norm:
        return {
            "corridor_norm": text_norm,
            "corridor_norm_source": osm_source if osm_source in {"OSM_REF", "OSM_NAME"} else text_source,
            "text_osm_resolution": "COMPATIBLE",
            "corridor_resolution_confidence": "HIGH" if osm_status == "SPATIAL_OSM_HIGH" else "MEDIUM",
            "nearest_osm_corridor_norm": osm_norm,
            "text_corridor_norm": text_norm,
        }

    if text_norm and has_osm and spatial_reasonable and is_intersection_like(row):
        return {
            "corridor_norm": text_norm,
            "corridor_norm_source": text_source,
            "text_osm_resolution": "INTERSECTION_ACCEPTED",
            "corridor_resolution_confidence": "MEDIUM",
            "nearest_osm_corridor_norm": osm_norm,
            "text_corridor_norm": text_norm,
        }

    if text_norm and has_osm and spatial_reasonable and distance is not None and distance <= 50 and is_strong_text_corridor(text_norm, text_source):
        return {
            "corridor_norm": text_norm,
            "corridor_norm_source": text_source,
            "text_osm_resolution": "LOCAL_NAME_WITHIN_CORRIDOR",
            "corridor_resolution_confidence": "MEDIUM",
            "nearest_osm_corridor_norm": osm_norm,
            "text_corridor_norm": text_norm,
        }

    if text_norm and has_osm and spatial_reasonable:
        return {
            "corridor_norm": text_norm,
            "corridor_norm_source": text_source,
            "text_osm_resolution": "REVIEW_COORDINATE_OR_NAME",
            "corridor_resolution_confidence": "LOW",
            "nearest_osm_corridor_norm": osm_norm,
            "text_corridor_norm": text_norm,
        }

    if osm_norm and osm_source != "UNRESOLVED":
        return {
            "corridor_norm": osm_norm,
            "corridor_norm_source": osm_source,
            "text_osm_resolution": "COMPATIBLE" if not text_norm else "REVIEW_COORDINATE_OR_NAME",
            "corridor_resolution_confidence": "MEDIUM",
            "nearest_osm_corridor_norm": osm_norm,
            "text_corridor_norm": text_norm,
        }

    if text_norm:
        return {
            "corridor_norm": text_norm,
            "corridor_norm_source": text_source,
            "text_osm_resolution": "UNRESOLVED",
            "corridor_resolution_confidence": "LOW",
            "nearest_osm_corridor_norm": osm_norm if osm_source != "UNRESOLVED" else "",
            "text_corridor_norm": text_norm,
        }

    return {
        "corridor_norm": "",
        "corridor_norm_source": "UNRESOLVED",
        "text_osm_resolution": "UNRESOLVED",
        "corridor_resolution_confidence": "LOW",
        "nearest_osm_corridor_norm": osm_norm if osm_source != "UNRESOLVED" else "",
        "text_corridor_norm": "",
    }


def nonempty(value: Any) -> bool:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    return str(value).strip().lower() not in {"", "nan", "none", "null", "na", "n/a"}


def safe_float(value: Any) -> float | None:
    try:
        if value is None or not nonempty(value):
            return None
        parsed = float(value)
        if math.isnan(parsed):
            return None
        return parsed
    except Exception:
        return None


def parse_json(value: Any, default: Any) -> Any:
    if not nonempty(value):
        return default
    try:
        return json.loads(str(value))
    except Exception:
        return default


def pct(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return round(float(numerator) / float(denominator) * 100, 2)


def number_from_token(token: str) -> int | None:
    token = compact_text(token)
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
    return max([count for count in counts if count is not None], default=0)


def contains_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)


def severity_features(observation: str, incident: str) -> dict[str, Any]:
    text = compact_text(observation)
    incident_norm = compact_text(incident)

    fatality = contains_any(text, ["fallecid", "muert", "fatal", "perdio la vida", "sin vida", "murio"])
    injured = contains_any(text, ["lesion", "herid", "atendid", "trasladad"])
    material_only = contains_any(text, ["solo danos materiales", "sin heridos", "no dejo heridos"])
    vulnerable = contains_any(text, ["motocic", "moto", "peaton", "atropell", "ciclist"])
    motorcycle = contains_any(text, ["motocic", "moto"])
    pedestrian = contains_any(text, ["peaton", "atropell"])
    heavy_vehicle = contains_any(text, ["camion", "rastra", "furgon", "pipa", "bus", "microbus", "volqueta"])
    obstruction = contains_any(text, ["carril", "paso", "carga vehicular", "cierre", "bloque", "derrame", "trafico"])
    multiple = contains_any(text, ["multiple", "triple", "varios vehiculos", "tres vehiculos", "dos vehiculos"])

    injury_count = max_count_near_keywords(text, r"(?:lesionad\w*|herid\w*)")
    fatality_count = max_count_near_keywords(text, r"(?:fallecid\w*|muert\w*)")

    if fatality:
        severity_class = "FATALITY_REPORTED"
        severity = 0.90 + min(fatality_count, 3) * 0.03
    elif injured:
        severity_class = "INJURY_REPORTED"
        severity = 0.50 + min(injury_count, 6) * 0.05
    elif material_only:
        severity_class = "MATERIAL_DAMAGE_ONLY"
        severity = 0.20
    elif incident_norm == "traffic accident":
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

    severity = round(max(0.0, min(1.0, severity)), 4)
    return {
        "severity_class": severity_class,
        "severity_score": severity,
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


def clean_road_phrase(phrase: str) -> str:
    phrase = normalize_text(phrase)
    phrase = re.split(
        r"(?:,|;|\.|\n|\(|\)|<|>|/| - )|"
        r"\b(?:accidente|percance|colision|choque|atropello|retiro|genera|genero|provoca|provoco|impacta|impacto|"
        r"involucra|involucrados|deja|dejando|fallece|fallecio|fallecido|lesionado|lesionada|herido|herida|"
        r"volqueta|vehiculo|vehiculos|camion|motocicleta|motociclista|bus|microbus|sedan|pick|rastra|conductor|conductora|"
        r"reportado|registrado|tras|en|a la altura|frente|cerca|cercanias|inmediaciones|sentido|sector|"
        r"antes|despues|rumbo|hacia|sobre|por|con|contra)\b",
        phrase,
    )[0]
    phrase = re.sub(r"\b(?:del|de la|de los|de las)$", "", phrase)
    phrase = re.sub(r"[^a-z0-9 ]+", " ", phrase)
    return re.sub(r"\s+", " ", phrase).strip(" ,.;:-")


def is_valid_road_phrase(phrase: str) -> bool:
    tokens = compact_text(phrase).split()
    if len(tokens) < 2:
        return False
    if tokens[0] in ROAD_KIND_TOKENS and all(token in ROAD_FILLER_TOKENS for token in tokens[1:]):
        return False
    if len(tokens) <= 3 and set(tokens) <= (ROAD_KIND_TOKENS | ROAD_FILLER_TOKENS):
        return False
    return True


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
        if is_valid_road_phrase(phrase):
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


def classify_road_type_candidate(road_name: str, text: str) -> str:
    value = compact_text(road_name or text)
    if any(term in value for term in ["autopista", "carretera", "troncal", "panamericana", "ruta", "periferico", "bypass"]):
        return "NACIONAL_ESTRUCTURANTE"
    if any(term in value for term in ["bulevar", "boulevard", "alameda", "paseo"]):
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


def latest_engagement_from_mentions(mentions: list[dict[str, Any]]) -> tuple[dict[str, float], int, int]:
    totals = {"likes": 0.0, "comments": 0.0, "shares": 0.0, "quotes": 0.0, "views": 0.0}
    mentions_with_engagement = 0
    snapshots = 0
    for item in mentions:
        engagement = item.get("engagement")
        if not isinstance(engagement, list) or not engagement:
            continue
        mentions_with_engagement += 1
        snapshots += len(engagement)

        def sort_key(snapshot: dict[str, Any]) -> pd.Timestamp:
            ts = pd.to_datetime(snapshot.get("captured_at"), errors="coerce")
            if pd.isna(ts):
                return pd.Timestamp.min.tz_localize("UTC")
            return ts

        latest = sorted([snap for snap in engagement if isinstance(snap, dict)], key=sort_key)[-1]
        for key in totals:
            totals[key] += safe_float(latest.get(key)) or 0.0
    return totals, mentions_with_engagement, snapshots


def impact_social_score(likes: float, comments: float, shares: float, quotes: float, views: float) -> float:
    # Views are important but can dominate; log dampens their effect.
    return round(likes + comments * 2 + shares * 3 + quotes * 3 + math.log1p(max(views, 0)), 4)


def load_raw() -> pd.DataFrame:
    return pd.read_csv(INPUT_CSV, dtype=str, keep_default_na=False)


def build_event_tables(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    event_rows = []
    mention_rows = []
    snapshot_rows = []

    for _, row in raw.iterrows():
        reliability = parse_json(row.get("reliability"), {})
        evidence = parse_json(row.get("evidence"), [])
        if not isinstance(evidence, list):
            evidence = []
        links = reliability.get("links", []) if isinstance(reliability, dict) else []
        if not isinstance(links, list):
            links = []

        link_decisions = Counter()
        dedupe_scores = []
        for link in links:
            if not isinstance(link, dict):
                continue
            link_decisions[str(link.get("decision") or "")] += 1
            score = safe_float(link.get("dedupe_score"))
            if score is not None:
                dedupe_scores.append(score)

        latest_engagement, engagement_mentions, engagement_snapshots = latest_engagement_from_mentions(evidence)
        impact = impact_social_score(
            latest_engagement["likes"],
            latest_engagement["comments"],
            latest_engagement["shares"],
            latest_engagement["quotes"],
            latest_engagement["views"],
        )

        source_set = sorted({str(item.get("source") or "") for item in evidence if isinstance(item, dict) and nonempty(item.get("source"))})
        mentions_count = int(reliability.get("mentions") or len(evidence) or 0) if isinstance(reliability, dict) else len(evidence)
        links_count = int(reliability.get("links_count") or len(evidence) or 0) if isinstance(reliability, dict) else len(evidence)
        lat = safe_float(row.get("latitude"))
        lon = safe_float(row.get("longitude"))
        event_dt = pd.to_datetime(row.get("datetime"), errors="coerce")
        department_norm = normalize_department_name(row.get("department"))
        municipality_norm = normalize_municipality_name(row.get("municipality"))
        territory_status = territory_normalization_status(row.get("department"), row.get("municipality"))

        combined = " ".join([compact_text(row.get("address")), compact_text(row.get("observation"))])
        known = extract_known_corridors(combined)
        generic = extract_generic_road_phrases(combined)
        road_names = dedupe_road_names(known + generic)
        km_refs = extract_km_references(combined)
        intersection = extract_intersection(combined, road_names)
        primary_road = road_names[0] if road_names else ""
        corridor_candidate = known[0] if known else primary_road
        context_level = road_context_level(road_names, intersection, km_refs)
        road_type = classify_road_type_candidate(primary_road, combined)

        severity = severity_features(row.get("observation", ""), row.get("incident", ""))
        geo_confidence = safe_float(reliability.get("geo_confidence")) if isinstance(reliability, dict) else None
        if geo_confidence is None:
            geo_confidence = 0.0

        event_rows.append(
            {
                **row.to_dict(),
                **severity,
                "event_date": event_dt.date().isoformat() if not pd.isna(event_dt) else "",
                "event_hour": int(event_dt.hour) if not pd.isna(event_dt) else None,
                "event_weekday": event_dt.day_name() if not pd.isna(event_dt) else "",
                "department_norm": department_norm,
                "municipality_norm": municipality_norm,
                "territory_normalization_status": territory_status,
                "mentions": mentions_count,
                "links_count": links_count,
                "source_diversity": len(source_set),
                "source_list": "; ".join(source_set),
                "merge_links": int(link_decisions.get("MERGE", 0)),
                "new_links": int(link_decisions.get("NEW", 0)),
                "max_dedupe_score": round(max(dedupe_scores), 4) if dedupe_scores else None,
                "geo_confidence": round(geo_confidence, 4),
                "latitude_num": lat,
                "longitude_num": lon,
                "has_address": nonempty(row.get("address")),
                "has_municipality": nonempty(row.get("municipality")),
                "has_department": nonempty(row.get("department")),
                "road_name_candidates": "; ".join(road_names),
                "primary_road_candidate": primary_road,
                "corridor_candidate": corridor_candidate,
                "intersection_candidate": intersection,
                "km_references": "; ".join(km_refs),
                "road_context_level": context_level,
                "road_context_available": context_level != "NO_ROAD_CONTEXT",
                "road_type_candidate": road_type,
                "engagement_mentions": engagement_mentions,
                "engagement_snapshots": engagement_snapshots,
                "latest_likes": latest_engagement["likes"],
                "latest_comments": latest_engagement["comments"],
                "latest_shares": latest_engagement["shares"],
                "latest_quotes": latest_engagement["quotes"],
                "latest_views": latest_engagement["views"],
                "impact_social_score": impact,
                "impact_raw_sum": round(sum(latest_engagement.values()), 4),
            }
        )

        for item in evidence:
            if not isinstance(item, dict):
                continue
            engagement = item.get("engagement") if isinstance(item.get("engagement"), list) else []
            latest_snapshot = {}
            if engagement:
                latest_snapshot = engagement[-1] if isinstance(engagement[-1], dict) else {}
            mention_rows.append(
                {
                    "event_uuid": row.get("uuid"),
                    "ticketNumber": row.get("ticketNumber"),
                    "event_datetime_row": row.get("datetime"),
                    "mention_id": item.get("mention_id"),
                    "source": item.get("source"),
                    "source_item_id": item.get("source_item_id"),
                    "tweet_status_id_ref": item.get("tweet_status_id_ref"),
                    "canonical_url": item.get("canonical_url"),
                    "url": item.get("url"),
                    "published_at": item.get("published_at"),
                    "event_datetime_mention": item.get("event_datetime"),
                    "is_relevant": item.get("is_relevant"),
                    "relevance_confidence": item.get("relevance_confidence"),
                    "relevance_reason_code": item.get("relevance_reason_code"),
                    "is_followup_update": item.get("is_followup_update"),
                    "needs_maps": item.get("needs_maps"),
                    "maps_reason": item.get("maps_reason"),
                    "title": item.get("title"),
                    "context_summary": item.get("context_summary"),
                    "raw_text": item.get("raw_text"),
                    "municipality": item.get("municipality"),
                    "department": item.get("department"),
                    "latitude": item.get("latitude"),
                    "longitude": item.get("longitude"),
                    "geo_confidence": item.get("geo_confidence"),
                    "geo_validation_status": item.get("geo_validation_status"),
                    "maps_country_code": item.get("maps_country_code"),
                    "maps_country_name": item.get("maps_country_name"),
                    "engagement_snapshots": len(engagement),
                    "latest_likes": latest_snapshot.get("likes"),
                    "latest_comments": latest_snapshot.get("comments"),
                    "latest_shares": latest_snapshot.get("shares"),
                    "latest_quotes": latest_snapshot.get("quotes"),
                    "latest_views": latest_snapshot.get("views"),
                    "latest_captured_at": latest_snapshot.get("captured_at"),
                }
            )
            for idx, snapshot in enumerate(engagement):
                if not isinstance(snapshot, dict):
                    continue
                snapshot_rows.append(
                    {
                        "event_uuid": row.get("uuid"),
                        "ticketNumber": row.get("ticketNumber"),
                        "mention_id": item.get("mention_id"),
                        "source": item.get("source"),
                        "published_at": item.get("published_at"),
                        "snapshot_index": idx,
                        "captured_at": snapshot.get("captured_at"),
                        "likes": snapshot.get("likes"),
                        "comments": snapshot.get("comments"),
                        "shares": snapshot.get("shares"),
                        "quotes": snapshot.get("quotes"),
                        "views": snapshot.get("views"),
                    }
                )

    events = pd.DataFrame(event_rows)
    mentions = pd.DataFrame(mention_rows)
    snapshots = pd.DataFrame(snapshot_rows)
    return enrich_coordinates(events), mentions, snapshots


def in_bbox(lat: float | None, lon: float | None, bbox: tuple[float, float, float, float]) -> bool:
    if lat is None or lon is None:
        return False
    south, west, north, east = bbox
    return south <= lat <= north and west <= lon <= east


def enrich_coordinates(events: pd.DataFrame) -> pd.DataFrame:
    events = events.copy()
    events["coordinate_pair_present"] = events["latitude_num"].notna() & events["longitude_num"].notna()
    events["coordinate_inside_sv_bbox"] = events.apply(
        lambda row: in_bbox(row["latitude_num"], row["longitude_num"], EL_SALVADOR_BBOX),
        axis=1,
    )
    events["coordinate_inside_amss_bbox"] = events.apply(
        lambda row: in_bbox(row["latitude_num"], row["longitude_num"], AMSS_BBOX),
        axis=1,
    )

    rounded = []
    for _, row in events.iterrows():
        if pd.notna(row["latitude_num"]) and pd.notna(row["longitude_num"]):
            rounded.append(f"{float(row['latitude_num']):.6f},{float(row['longitude_num']):.6f}")
        else:
            rounded.append("")
    events["coordinate_key_6dec"] = rounded
    reuse = events[events["coordinate_key_6dec"] != ""]["coordinate_key_6dec"].value_counts()
    events["coordinate_reuse_count"] = events["coordinate_key_6dec"].map(lambda key: int(reuse.get(key, 0)) if key else 0)
    events["repeated_coordinate_flag"] = events["coordinate_reuse_count"] > 1

    def status(row: pd.Series) -> str:
        if not bool(row["coordinate_pair_present"]):
            return "MISSING_POINT"
        if not bool(row["coordinate_inside_sv_bbox"]):
            return "OUTSIDE_EL_SALVADOR_BBOX"
        if float(row.get("geo_confidence") or 0) < 0.5:
            return "LOW_GEO_CONFIDENCE_POINT"
        if bool(row["repeated_coordinate_flag"]):
            return "VALID_POINT_REPEATED_COORDINATE"
        return "VALID_POINT"

    events["coordinate_quality_status"] = events.apply(status, axis=1)
    return events


def project_point(lon: float, lat: float, lat0: float) -> tuple[float, float]:
    meters_per_degree_lat = 111_320.0
    meters_per_degree_lon = 111_320.0 * math.cos(math.radians(lat0))
    return lon * meters_per_degree_lon, lat * meters_per_degree_lat


def point_to_segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx = bx - ax
    dy = by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    qx = ax + t * dx
    qy = ay + t * dy
    return math.hypot(px - qx, py - qy)


def parse_segment_records(segments: pd.DataFrame) -> list[dict[str, Any]]:
    records = []
    for _, row in segments.iterrows():
        coords = parse_json(row.get("geometry_json"), [])
        if len(coords) < 2:
            continue
        lons = [float(point[0]) for point in coords]
        lats = [float(point[1]) for point in coords]
        records.append(
            {
                "osm_way_id": row.get("osm_way_id"),
                "name": row.get("name", ""),
                "ref": row.get("ref", ""),
                "highway": row.get("highway", ""),
                "oneway": row.get("oneway", ""),
                "lanes": row.get("lanes", ""),
                "maxspeed": row.get("maxspeed", ""),
                "surface": row.get("surface", ""),
                "road_key_norm": row.get("road_key_norm", ""),
                "road_type_category": row.get("road_type_category", ""),
                "length_m": row.get("length_m", 0),
                "coords": [(float(lon), float(lat)) for lon, lat in coords],
                "min_lon": min(lons),
                "max_lon": max(lons),
                "min_lat": min(lats),
                "max_lat": max(lats),
            }
        )
    return records


def nearest_segment(
    lon: float,
    lat: float,
    records: list[dict[str, Any]],
    search_degrees: float = 0.035,
) -> dict[str, Any] | None:
    candidates = [
        record
        for record in records
        if record["min_lon"] - search_degrees <= lon <= record["max_lon"] + search_degrees
        and record["min_lat"] - search_degrees <= lat <= record["max_lat"] + search_degrees
    ]
    if not candidates:
        return None

    px, py = project_point(lon, lat, lat)
    best_record = None
    best_distance = float("inf")
    for record in candidates:
        projected = [project_point(coord_lon, coord_lat, lat) for coord_lon, coord_lat in record["coords"]]
        for (ax, ay), (bx, by) in zip(projected, projected[1:]):
            distance = point_to_segment_distance(px, py, ax, ay, bx, by)
            if distance < best_distance:
                best_distance = distance
                best_record = record

    if best_record is None:
        return None
    return {**best_record, "distance_m": round(best_distance, 2)}


def text_consistency_status(row: pd.Series) -> str:
    candidate = compact_text(row.get("corridor_candidate", ""))
    if not candidate:
        return "NO_TEXT_TO_VALIDATE"
    osm_text = compact_text(
        " ".join(
            [
                str(row.get("nearest_osm_name") or ""),
                str(row.get("nearest_osm_ref") or ""),
                str(row.get("nearest_osm_road_key_norm") or ""),
            ]
        )
    )
    if not osm_text:
        return "NO_OSM_TO_VALIDATE"
    if candidate in osm_text or osm_text in candidate:
        return "TEXT_SPATIAL_CONSISTENT"

    candidate_tokens = set(candidate.split())
    osm_tokens = set(osm_text.split())
    overlap = len(candidate_tokens & osm_tokens) / len(candidate_tokens | osm_tokens) if candidate_tokens and osm_tokens else 0
    if overlap >= 0.45:
        return "TEXT_SPATIAL_REVIEW"
    return "TEXT_SPATIAL_CONFLICT"


def osm_match_status(distance: float | None, point_status: str, source_scope: str, in_amss: bool) -> str:
    if point_status == "MISSING_POINT":
        return "NO_COORDINATE_FOR_OSM"
    if point_status == "OUTSIDE_EL_SALVADOR_BBOX":
        return "INVALID_POINT_FOR_OSM"
    if source_scope == "NO_OSM_NETWORK":
        return "NO_OSM_NETWORK_FOR_POINT"
    if source_scope == "AMSS" and not in_amss:
        return "OUTSIDE_AMSS_OSM_SCOPE"
    if distance is None:
        return "NO_NEAR_OSM_SEGMENT"
    if distance <= 50:
        return "SPATIAL_OSM_HIGH"
    if distance <= 150:
        return "SPATIAL_OSM_MEDIUM"
    if distance <= 500:
        return "SPATIAL_OSM_LOW_REVIEW"
    return "SPATIAL_OSM_DISTANCE_CONFLICT"


def department_osm_segments_path(department_norm: Any) -> Path:
    slug = DEPARTMENT_SLUGS.get(str(department_norm), slugify(department_norm))
    return OSM_DEPARTMENTS_DIR / slug / "osm_road_segments.csv"


def load_segment_records(path: Path, cache: dict[Path, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    if path not in cache:
        cache[path] = parse_segment_records(pd.read_csv(path, low_memory=False)) if path.exists() else []
    return cache[path]


def select_osm_source(row: pd.Series, cache: dict[Path, list[dict[str, Any]]]) -> tuple[str, str, Path | None, list[dict[str, Any]]]:
    department = str(row.get("department_norm") or "")
    department_path = department_osm_segments_path(department)
    if department_path.exists():
        return "DEPARTMENT", department, department_path, load_segment_records(department_path, cache)
    if OSM_NATIONAL_SEGMENTS_PATH.exists():
        return "NATIONAL", "NACIONAL", OSM_NATIONAL_SEGMENTS_PATH, load_segment_records(OSM_NATIONAL_SEGMENTS_PATH, cache)
    if OSM_SEGMENTS_PATH.exists() and bool(row.get("coordinate_inside_amss_bbox")):
        return "AMSS", "SAN SALVADOR", OSM_SEGMENTS_PATH, load_segment_records(OSM_SEGMENTS_PATH, cache)
    return "NO_OSM_NETWORK", "", None, []


def enrich_with_osm(events: pd.DataFrame) -> pd.DataFrame:
    events = events.copy()
    if not any([OSM_SEGMENTS_PATH.exists(), OSM_NATIONAL_SEGMENTS_PATH.exists(), OSM_DEPARTMENTS_DIR.exists()]):
        events["osm_match_status"] = "OSM_SEGMENTS_MISSING"
        events["text_spatial_consistency"] = "NO_OSM_TO_VALIDATE"
        events["nearest_osm_source_scope"] = "NO_OSM_NETWORK"
        events["nearest_osm_source_department"] = ""
        events["nearest_osm_source_path"] = ""
        resolution = events.apply(resolve_corridor_norm, axis=1, result_type="expand")
        return pd.concat([events.reset_index(drop=True), resolution.reset_index(drop=True)], axis=1)

    cache: dict[Path, list[dict[str, Any]]] = {}
    rows = []
    for _, row in events.iterrows():
        lat = safe_float(row.get("latitude_num"))
        lon = safe_float(row.get("longitude_num"))
        output: dict[str, Any] = {}
        nearest = None
        source_scope, source_department, source_path, records = select_osm_source(row, cache)
        if row.get("coordinate_quality_status") != "OUTSIDE_EL_SALVADOR_BBOX" and source_scope != "NO_OSM_NETWORK":
            nearest = nearest_segment(lon, lat, records) if lat is not None and lon is not None and records else None
        if nearest:
            output.update(
                {
                    "nearest_osm_way_id": nearest["osm_way_id"],
                    "nearest_osm_name": nearest["name"],
                    "nearest_osm_ref": nearest["ref"],
                    "nearest_osm_highway": nearest["highway"],
                    "nearest_osm_road_key_norm": nearest["road_key_norm"],
                    "nearest_osm_road_type": nearest["road_type_category"],
                    "nearest_osm_oneway": nearest["oneway"],
                    "nearest_osm_lanes": nearest["lanes"],
                    "nearest_osm_maxspeed": nearest["maxspeed"],
                    "nearest_osm_surface": nearest["surface"],
                    "nearest_osm_distance_m": nearest["distance_m"],
                    "nearest_osm_source_scope": source_scope,
                    "nearest_osm_source_department": source_department,
                    "nearest_osm_source_path": str(source_path or ""),
                }
            )
        else:
            output.update(
                {
                    "nearest_osm_way_id": "",
                    "nearest_osm_name": "",
                    "nearest_osm_ref": "",
                    "nearest_osm_highway": "",
                    "nearest_osm_road_key_norm": "",
                    "nearest_osm_road_type": "",
                    "nearest_osm_oneway": "",
                    "nearest_osm_lanes": "",
                    "nearest_osm_maxspeed": "",
                    "nearest_osm_surface": "",
                    "nearest_osm_distance_m": None,
                    "nearest_osm_source_scope": source_scope,
                    "nearest_osm_source_department": source_department,
                    "nearest_osm_source_path": str(source_path or ""),
                }
            )
        rows.append(output)

    osm = pd.DataFrame(rows)
    combined = pd.concat([events.reset_index(drop=True), osm.reset_index(drop=True)], axis=1)
    combined["osm_match_status"] = combined.apply(
        lambda row: osm_match_status(
            safe_float(row.get("nearest_osm_distance_m")),
            str(row.get("coordinate_quality_status")),
            str(row.get("nearest_osm_source_scope") or "NO_OSM_NETWORK"),
            bool(row.get("coordinate_inside_amss_bbox")),
        ),
        axis=1,
    )
    combined["text_spatial_consistency"] = combined.apply(text_consistency_status, axis=1)
    resolution = combined.apply(resolve_corridor_norm, axis=1, result_type="expand")
    combined = pd.concat([combined.reset_index(drop=True), resolution.reset_index(drop=True)], axis=1)
    return combined


def add_exploratory_metric(events: pd.DataFrame) -> pd.DataFrame:
    events = events.copy()
    max_mentions = max(float(events["mentions"].max()), 1.0)
    max_impact = max(float(events["impact_social_score"].max()), 1.0)
    dates = pd.to_datetime(events["datetime"], errors="coerce")
    min_date = dates.min()
    max_date = dates.max()
    span_seconds = max((max_date - min_date).total_seconds(), 1.0) if not pd.isna(min_date) and not pd.isna(max_date) else 1.0

    osm_score_map = {
        "SPATIAL_OSM_HIGH": 100,
        "SPATIAL_OSM_MEDIUM": 75,
        "SPATIAL_OSM_LOW_REVIEW": 50,
        "OUTSIDE_AMSS_OSM_SCOPE": 35,
        "NO_COORDINATE_FOR_OSM": 20,
        "INVALID_POINT_FOR_OSM": 10,
        "NO_NEAR_OSM_SEGMENT": 15,
        "SPATIAL_OSM_DISTANCE_CONFLICT": 20,
        "NO_OSM_NETWORK_FOR_POINT": 15,
        "OSM_SEGMENTS_MISSING": 10,
    }
    coordinate_score_map = {
        "VALID_POINT": 100,
        "VALID_POINT_REPEATED_COORDINATE": 85,
        "LOW_GEO_CONFIDENCE_POINT": 55,
        "MISSING_POINT": 25,
        "OUTSIDE_EL_SALVADOR_BBOX": 5,
    }

    metric_rows = []
    for idx, row in events.iterrows():
        recency = 0.0
        dt = dates.iloc[idx]
        if not pd.isna(dt):
            recency = ((dt - min_date).total_seconds() / span_seconds) * 100
        components = {
            "severity_component": float(row["severity_score"]) * 100,
            "mentions_component": min(math.log1p(float(row["mentions"])) / math.log1p(max_mentions), 1.0) * 100,
            "source_diversity_component": min(float(row["source_diversity"]) / 3.0, 1.0) * 100,
            "impact_social_component": min(math.log1p(float(row["impact_social_score"])) / math.log1p(max_impact), 1.0) * 100,
            "geo_quality_component": coordinate_score_map.get(str(row["coordinate_quality_status"]), 0),
            "osm_association_component": osm_score_map.get(str(row.get("osm_match_status")), 0),
            "temporal_recency_component": recency,
        }
        score = (
            0.20 * components["severity_component"]
            + 0.16 * components["mentions_component"]
            + 0.12 * components["source_diversity_component"]
            + 0.22 * components["impact_social_component"]
            + 0.14 * components["geo_quality_component"]
            + 0.10 * components["osm_association_component"]
            + 0.06 * components["temporal_recency_component"]
        )
        metric_rows.append({**components, "metric_score_0_100": round(score, 2)})

    metric_df = pd.DataFrame(metric_rows)
    events = pd.concat([events.reset_index(drop=True), metric_df], axis=1)
    events["metric_category"] = pd.cut(
        events["metric_score_0_100"],
        bins=[-0.01, 20, 40, 60, 80, 100],
        labels=["BAJA", "MODERADA", "RELEVANTE", "ALTA", "CRITICA"],
    ).astype(str)
    return events


def build_integrity_tables(events: pd.DataFrame, mentions: pd.DataFrame, snapshots: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    total = len(events)
    rows = []

    def add(metric: str, value: float, denominator: float | None, reading: str) -> None:
        rows.append(
            {
                "metric": metric,
                "value": round(float(value), 4) if isinstance(value, (int, float)) else value,
                "percent": pct(value, denominator) if denominator else None,
                "reading": reading,
            }
        )

    add("eventos_totales", total, total, "Unidad principal: evento vial deduplicado.")
    add("menciones_expandidas", len(mentions), None, "Unidad secundaria: publicaciones asociadas al evento.")
    add("snapshots_engagement", len(snapshots), None, "Capturas temporales de interaccion social.")
    add("eventos_con_lat_lon", int(events["coordinate_pair_present"].sum()), total, "Eventos con coordenada cruda en columnas principales.")
    add("eventos_con_lat_lon_dentro_sv_bbox", int(events["coordinate_inside_sv_bbox"].sum()), total, "Puntos dentro del control preliminar de El Salvador.")
    add("eventos_fuera_sv_bbox", int((events["coordinate_quality_status"] == "OUTSIDE_EL_SALVADOR_BBOX").sum()), total, "Posibles errores de geocodificacion.")
    add("eventos_sin_lat_lon", int((events["coordinate_quality_status"] == "MISSING_POINT").sum()), total, "Eventos que requieren geocodificacion si se desea punto.")
    add("eventos_con_coordenada_repetida", int(events["repeated_coordinate_flag"].sum()), total, "No se eliminan; se analizan como recurrencia o posible punto generico.")
    add("eventos_con_address", int(events["has_address"].sum()), total, "Direccion textual disponible.")
    add("eventos_con_municipio", int(events["has_municipality"].sum()), total, "Municipio estructurado disponible.")
    add("eventos_con_departamento", int(events["has_department"].sum()), total, "Departamento estructurado disponible.")
    add("eventos_con_contexto_vial_textual", int(events["road_context_available"].sum()), total, "Texto permite extraer via, corredor, km o interseccion.")
    add("eventos_con_engagement", int((events["engagement_mentions"] > 0).sum()), total, "Eventos con likes, shares, views u otra interaccion.")
    add("eventos_con_multiples_menciones", int((events["mentions"] > 1).sum()), total, "Senal de amplificacion y/o corroboracion.")
    add("eventos_con_mas_de_una_fuente", int((events["source_diversity"] > 1).sum()), total, "Corroboracion multifuente.")
    add("eventos_con_osm_alto_medio", int(events["osm_match_status"].isin(["SPATIAL_OSM_HIGH", "SPATIAL_OSM_MEDIUM"]).sum()), total, "Puntos asociados con red OSM departamental, nacional o fallback AMSS a distancia razonable.")
    add("likes_ultimo_snapshot", float(events["latest_likes"].sum()), None, "Likes acumulados usando el ultimo snapshot por mencion.")
    add("comments_ultimo_snapshot", float(events["latest_comments"].sum()), None, "Comentarios acumulados usando el ultimo snapshot por mencion.")
    add("shares_ultimo_snapshot", float(events["latest_shares"].sum()), None, "Compartidos/retweets acumulados usando el ultimo snapshot por mencion.")
    add("quotes_ultimo_snapshot", float(events["latest_quotes"].sum()), None, "Citas acumuladas usando el ultimo snapshot por mencion.")
    add("views_ultimo_snapshot", float(events["latest_views"].sum()), None, "Visualizaciones acumuladas usando el ultimo snapshot por mencion.")
    add("impacto_social_ponderado_total", float(events["impact_social_score"].sum()), None, "Suma del impacto social ponderado para heatmap principal.")
    add("impacto_raw_total", float(events["impact_raw_sum"].sum()), None, "Suma cruda de likes, comentarios, shares, quotes y views.")

    coord = (
        events.groupby("coordinate_quality_status", dropna=False)
        .agg(
            events=("uuid", "count"),
            mentions=("mentions", "sum"),
            impact_social=("impact_social_score", "sum"),
            avg_geo_confidence=("geo_confidence", "mean"),
        )
        .reset_index()
        .sort_values("events", ascending=False)
    )
    coord["percent"] = coord["events"].map(lambda n: pct(n, total))
    return pd.DataFrame(rows), coord


def build_aggregates(events: pd.DataFrame) -> dict[str, pd.DataFrame]:
    outputs: dict[str, pd.DataFrame] = {}

    outputs["departments"] = (
        events.groupby("department_norm", dropna=False)
        .agg(
            events=("uuid", "count"),
            traffic_accidents=("incident", lambda s: int((s == "TRAFFIC_ACCIDENT").sum())),
            mentions=("mentions", "sum"),
            impact_social=("impact_social_score", "sum"),
            severity_sum=("severity_score", "sum"),
            valid_points=("coordinate_inside_sv_bbox", "sum"),
            address_events=("has_address", "sum"),
            avg_metric_score=("metric_score_0_100", "mean"),
        )
        .reset_index()
        .sort_values(["events", "impact_social"], ascending=False)
    )

    outputs["municipalities"] = (
        events.groupby(["department_norm", "municipality_norm"], dropna=False)
        .agg(
            events=("uuid", "count"),
            mentions=("mentions", "sum"),
            impact_social=("impact_social_score", "sum"),
            severity_sum=("severity_score", "sum"),
            valid_points=("coordinate_inside_sv_bbox", "sum"),
            address_events=("has_address", "sum"),
            avg_metric_score=("metric_score_0_100", "mean"),
        )
        .reset_index()
        .sort_values(["events", "impact_social"], ascending=False)
    )

    outputs["territory_normalization"] = (
        events.assign(
            department_raw=events["department"].map(lambda x: str(x).strip() if nonempty(x) else "SIN_DEPTO"),
            municipality_raw=events["municipality"].map(lambda x: str(x).strip() if nonempty(x) else "SIN_MUNICIPIO"),
        )
        .groupby(
            [
                "department_raw",
                "department_norm",
                "municipality_raw",
                "municipality_norm",
                "territory_normalization_status",
            ],
            dropna=False,
        )
        .agg(events=("uuid", "count"), mentions=("mentions", "sum"), impact_social=("impact_social_score", "sum"))
        .reset_index()
        .sort_values(["events", "impact_social"], ascending=False)
    )

    road_events = events[events["corridor_candidate"].map(nonempty)].copy()
    norm_events = events[events["corridor_norm"].map(nonempty)].copy() if "corridor_norm" in events.columns else pd.DataFrame()
    outputs["corridors"] = (
        road_events.groupby("corridor_candidate", dropna=False)
        .agg(
            events=("uuid", "count"),
            mentions=("mentions", "sum"),
            impact_social=("impact_social_score", "sum"),
            severity_sum=("severity_score", "sum"),
            valid_points=("coordinate_inside_sv_bbox", "sum"),
            fatality_events=("fatality_flag", "sum"),
            injury_events=("injury_flag", "sum"),
            vulnerable_events=("vulnerable_user_flag", "sum"),
            avg_metric_score=("metric_score_0_100", "mean"),
        )
        .reset_index()
        .sort_values(["events", "impact_social"], ascending=False)
    )

    outputs["corridors_norm"] = (
        norm_events.groupby("corridor_norm", dropna=False)
        .agg(
            events=("uuid", "count"),
            mentions=("mentions", "sum"),
            impact_social=("impact_social_score", "sum"),
            severity_sum=("severity_score", "sum"),
            valid_points=("coordinate_inside_sv_bbox", "sum"),
            fatality_events=("fatality_flag", "sum"),
            injury_events=("injury_flag", "sum"),
            vulnerable_events=("vulnerable_user_flag", "sum"),
            osm_high_medium=("osm_match_status", lambda s: int(s.isin(["SPATIAL_OSM_HIGH", "SPATIAL_OSM_MEDIUM"]).sum())),
            compatible_events=("text_osm_resolution", lambda s: int(s.isin(["COMPATIBLE", "LOCAL_NAME_WITHIN_CORRIDOR", "INTERSECTION_ACCEPTED"]).sum())),
            review_events=("text_osm_resolution", lambda s: int((s == "REVIEW_COORDINATE_OR_NAME").sum())),
            corridor_candidates=("corridor_candidate", lambda s: "; ".join(sorted({str(v) for v in s if nonempty(v)}))),
            avg_metric_score=("metric_score_0_100", "mean"),
        )
        .reset_index()
        .sort_values(["events", "impact_social"], ascending=False)
        if not norm_events.empty
        else pd.DataFrame()
    )

    if not norm_events.empty:
        corridor_stats = (
            norm_events.groupby("corridor_norm", dropna=False)
            .agg(
                events=("uuid", "count"),
                mentions=("mentions", "sum"),
                source_diversity_max=("source_diversity", "max"),
                impact_social=("impact_social_score", "sum"),
                avg_impact_social=("impact_social_score", "mean"),
                severity_sum=("severity_score", "sum"),
                avg_severity=("severity_score", "mean"),
                fatality_events=("fatality_flag", "sum"),
                injury_events=("injury_flag", "sum"),
                vulnerable_events=("vulnerable_user_flag", "sum"),
                heavy_vehicle_events=("heavy_vehicle_flag", "sum"),
                valid_points=("coordinate_inside_sv_bbox", "sum"),
                repeated_coordinate_events=("repeated_coordinate_flag", "sum"),
                amss_points=("coordinate_inside_amss_bbox", "sum"),
                osm_high_medium=("osm_match_status", lambda s: int(s.isin(["SPATIAL_OSM_HIGH", "SPATIAL_OSM_MEDIUM"]).sum())),
                avg_osm_distance_m=("nearest_osm_distance_m", "mean"),
                avg_metric_score=("metric_score_0_100", "mean"),
                first_event=("datetime", "min"),
                last_event=("datetime", "max"),
                departments=("department_norm", lambda s: "; ".join(sorted(set(s.dropna().astype(str))))),
                municipalities=("municipality_norm", lambda s: "; ".join(sorted(set(s.dropna().astype(str))))),
                road_type_candidate=("road_type_candidate", lambda s: "; ".join(sorted(set(s.dropna().astype(str))))),
                corridor_candidates=("corridor_candidate", lambda s: "; ".join(sorted({str(v) for v in s if nonempty(v)}))),
                compatible_events=("text_osm_resolution", lambda s: int(s.isin(["COMPATIBLE", "LOCAL_NAME_WITHIN_CORRIDOR", "INTERSECTION_ACCEPTED"]).sum())),
                review_events=("text_osm_resolution", lambda s: int((s == "REVIEW_COORDINATE_OR_NAME").sum())),
            )
            .reset_index()
        )
        for col in ["events", "mentions", "impact_social", "severity_sum", "fatality_events", "injury_events", "vulnerable_events", "valid_points", "osm_high_medium"]:
            max_value = max(float(corridor_stats[col].max()), 1.0)
            corridor_stats[f"{col}_norm"] = corridor_stats[col].astype(float) / max_value
        corridor_stats["corridor_criticality_score"] = (
            100
            * (
                0.24 * corridor_stats["events_norm"]
                + 0.14 * corridor_stats["mentions_norm"]
                + 0.18 * corridor_stats["impact_social_norm"]
                + 0.16 * corridor_stats["severity_sum_norm"]
                + 0.10 * corridor_stats["fatality_events_norm"]
                + 0.07 * corridor_stats["injury_events_norm"]
                + 0.05 * corridor_stats["vulnerable_events_norm"]
                + 0.06 * corridor_stats["osm_high_medium_norm"]
            )
        ).round(2)
        outputs["critical_corridors"] = corridor_stats.drop(
            columns=[
                "events_norm",
                "mentions_norm",
                "impact_social_norm",
                "severity_sum_norm",
                "fatality_events_norm",
                "injury_events_norm",
                "vulnerable_events_norm",
                "valid_points_norm",
                "osm_high_medium_norm",
            ],
            errors="ignore",
        ).sort_values("corridor_criticality_score", ascending=False)
    else:
        outputs["critical_corridors"] = pd.DataFrame()

    outputs["corridor_diagnostics"] = pd.DataFrame(
        [
            {
                "metric": "eventos_con_corredor_textual",
                "value": int(len(road_events)),
                "percent": pct(len(road_events), len(events)),
                "reading": "Eventos donde address/observation permitieron extraer un corredor o via textual.",
            },
            {
                "metric": "corredores_distintos_extraidos",
                "value": int(road_events["corridor_candidate"].nunique()) if not road_events.empty else 0,
                "percent": None,
                "reading": "Cantidad de nombres de corredores/vias candidatos despues de limpieza textual.",
            },
            {
                "metric": "eventos_con_corredor_norm",
                "value": int(len(norm_events)),
                "percent": pct(len(norm_events), len(events)),
                "reading": "Eventos con corredor funcional normalizado despues de resolver texto y OSM.",
            },
            {
                "metric": "corredores_norm_distintos",
                "value": int(norm_events["corridor_norm"].nunique()) if not norm_events.empty else 0,
                "percent": None,
                "reading": "Cantidad de corredores funcionales consolidados.",
            },
            {
                "metric": "eventos_con_corredor_y_coordenada_valida",
                "value": int(road_events["coordinate_inside_sv_bbox"].sum()) if not road_events.empty else 0,
                "percent": pct(int(road_events["coordinate_inside_sv_bbox"].sum()), len(road_events)) if not road_events.empty else 0,
                "reading": "Eventos con corredor textual y punto util dentro de El Salvador.",
            },
            {
                "metric": "eventos_con_corredor_en_bbox_amss",
                "value": int(road_events["coordinate_inside_amss_bbox"].sum()) if not road_events.empty else 0,
                "percent": pct(int(road_events["coordinate_inside_amss_bbox"].sum()), len(road_events)) if not road_events.empty else 0,
                "reading": "Eventos con corredor textual dentro del bbox AMSS; se conserva como zoom capitalino, no como unico alcance OSM.",
            },
            {
                "metric": "eventos_con_corredor_y_osm_alto_medio",
                "value": int(road_events["osm_match_status"].isin(["SPATIAL_OSM_HIGH", "SPATIAL_OSM_MEDIUM"]).sum()) if not road_events.empty else 0,
                "percent": pct(int(road_events["osm_match_status"].isin(["SPATIAL_OSM_HIGH", "SPATIAL_OSM_MEDIUM"]).sum()), len(road_events)) if not road_events.empty else 0,
                "reading": "Eventos de corredor que tambien tienen asociacion espacial razonable con OSM.",
            },
            {
                "metric": "impacto_social_en_corredores",
                "value": round(float(road_events["impact_social_score"].sum()), 4) if not road_events.empty else 0,
                "percent": pct(float(road_events["impact_social_score"].sum()), float(events["impact_social_score"].sum())) if float(events["impact_social_score"].sum()) else 0,
                "reading": "Porcentaje del impacto social total concentrado en eventos con corredor textual.",
            },
        ]
    )

    outputs["osm_road_type"] = (
        events.groupby("nearest_osm_road_type", dropna=False)
        .agg(
            events=("uuid", "count"),
            mentions=("mentions", "sum"),
            impact_social=("impact_social_score", "sum"),
            avg_distance_m=("nearest_osm_distance_m", "mean"),
        )
        .reset_index()
        .sort_values(["events", "impact_social"], ascending=False)
    )

    outputs["daily"] = (
        events.groupby("event_date", dropna=False)
        .agg(
            events=("uuid", "count"),
            traffic_accidents=("incident", lambda s: int((s == "TRAFFIC_ACCIDENT").sum())),
            mentions=("mentions", "sum"),
            impact_social=("impact_social_score", "sum"),
            views=("latest_views", "sum"),
            shares=("latest_shares", "sum"),
            valid_points=("coordinate_inside_sv_bbox", "sum"),
            avg_metric_score=("metric_score_0_100", "mean"),
        )
        .reset_index()
        .sort_values("event_date")
    )

    outputs["hourly"] = (
        events.groupby("event_hour", dropna=False)
        .agg(
            events=("uuid", "count"),
            mentions=("mentions", "sum"),
            impact_social=("impact_social_score", "sum"),
            views=("latest_views", "sum"),
            shares=("latest_shares", "sum"),
            avg_metric_score=("metric_score_0_100", "mean"),
        )
        .reset_index()
        .sort_values("event_hour")
    )

    outputs["heatmap_weights"] = events[
        events["coordinate_pair_present"]
    ][
        [
            "uuid",
            "ticketNumber",
            "datetime",
            "event_date",
            "event_hour",
            "incident",
            "department",
            "department_norm",
            "municipality",
            "municipality_norm",
            "address",
            "latitude_num",
            "longitude_num",
            "coordinate_quality_status",
            "coordinate_inside_sv_bbox",
            "coordinate_reuse_count",
            "mentions",
            "source_diversity",
            "latest_likes",
            "latest_comments",
            "latest_shares",
            "latest_quotes",
            "latest_views",
            "impact_social_score",
            "metric_score_0_100",
            "metric_category",
        ]
    ].rename(
        columns={
            "latitude_num": "latitude",
            "longitude_num": "longitude",
            "mentions": "heat_weight_menciones",
            "impact_social_score": "heat_weight_impacto_social",
        }
    )
    outputs["heatmap_weights"]["heat_weight_eventos"] = 1

    return outputs


def build_osm_network_summary() -> pd.DataFrame:
    if not OSM_SEGMENTS_PATH.exists():
        return pd.DataFrame()
    segments = pd.read_csv(OSM_SEGMENTS_PATH)
    segments["length_km"] = pd.to_numeric(segments["length_m"], errors="coerce").fillna(0) / 1000
    segments["has_name"] = segments["name"].map(nonempty)
    segments["is_oneway"] = segments["oneway"].fillna("").astype(str).str.lower().eq("yes")
    segments["lanes_num"] = pd.to_numeric(segments["lanes"], errors="coerce")
    segments["maxspeed_num"] = pd.to_numeric(segments["maxspeed"], errors="coerce")
    return (
        segments.groupby("highway", dropna=False)
        .agg(
            segmentos=("osm_way_id", "count"),
            km=("length_km", "sum"),
            vias_con_nombre=("has_name", "sum"),
            vias_oneway=("is_oneway", "sum"),
            carriles_promedio=("lanes_num", "mean"),
            velocidad_promedio=("maxspeed_num", "mean"),
        )
        .reset_index()
        .sort_values("km", ascending=False)
    )


def build_corridor_resolution_tables(events: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    cols = [
        "ticketNumber",
        "datetime",
        "department_norm",
        "municipality_norm",
        "address",
        "corridor_candidate",
        "corridor_norm",
        "corridor_norm_source",
        "text_corridor_norm",
        "nearest_osm_corridor_norm",
        "nearest_osm_name",
        "nearest_osm_ref",
        "nearest_osm_highway",
        "nearest_osm_distance_m",
        "nearest_osm_source_scope",
        "osm_match_status",
        "text_spatial_consistency",
        "text_osm_resolution",
        "corridor_resolution_confidence",
        "mentions",
        "impact_social_score",
    ]
    available = [col for col in cols if col in events.columns]
    resolution = events[available].copy()
    conflicts = resolution[resolution["text_spatial_consistency"] == "TEXT_SPATIAL_CONFLICT"].copy()
    return resolution, conflicts


def write_geojson(events: pd.DataFrame, path: Path) -> None:
    features = []
    for _, row in events[events["coordinate_pair_present"]].iterrows():
        props = {
            key: row.get(key)
            for key in [
                "uuid",
                "ticketNumber",
                "datetime",
                "incident",
                "department",
                "municipality",
                "address",
                "mentions",
                "source_diversity",
                "coordinate_quality_status",
                "coordinate_reuse_count",
                "latest_likes",
                "latest_comments",
                "latest_shares",
                "latest_quotes",
                "latest_views",
                "impact_social_score",
                "metric_score_0_100",
                "metric_category",
                "osm_match_status",
                "nearest_osm_name",
                "nearest_osm_highway",
                "nearest_osm_distance_m",
            ]
        }
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row["longitude_num"]), float(row["latitude_num"])],
                },
                "properties": props,
            }
        )
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, indent=2), encoding="utf-8")


def save_plots(events: pd.DataFrame, aggregates: dict[str, pd.DataFrame]) -> None:
    plt.style.use("seaborn-v0_8-whitegrid")

    fig, ax = plt.subplots(figsize=(9, 4.8))
    status_counts = events["coordinate_quality_status"].value_counts()
    status_counts.plot(kind="bar", ax=ax, color="#2A7F62")
    ax.set_title("Diagnostico de coordenadas - incidentes.csv")
    ax.set_xlabel("Estado")
    ax.set_ylabel("Eventos")
    ax.tick_params(axis="x", rotation=30)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "diagnostico_coordenadas_incidentes.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4.5))
    daily = aggregates["daily"]
    ax.plot(daily["event_date"], daily["events"], marker="o", label="Eventos")
    ax.plot(daily["event_date"], daily["mentions"], marker="o", label="Menciones")
    ax.set_title("Serie diaria de eventos y menciones")
    ax.set_xlabel("Fecha")
    ax.set_ylabel("Conteo")
    ax.legend()
    ax.tick_params(axis="x", rotation=20)
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "serie_diaria_eventos_incidentes.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 4.5))
    hourly = aggregates["hourly"]
    ax.bar(hourly["event_hour"].astype(str), hourly["events"], color="#4D7EA8")
    ax.set_title("Eventos por hora")
    ax.set_xlabel("Hora")
    ax.set_ylabel("Eventos")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "serie_horaria_eventos_incidentes.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5))
    top = events.sort_values("impact_social_score", ascending=False).head(10).copy()
    labels = top["ticketNumber"] + " - " + top["municipality"].fillna("").astype(str)
    ax.barh(labels[::-1], top["impact_social_score"][::-1], color="#B85C38")
    ax.set_title("Top 10 eventos por impacto social")
    ax.set_xlabel("Impacto social ponderado")
    fig.tight_layout()
    fig.savefig(RESULTS_DIR / "ranking_impacto_social_incidentes.png", dpi=180)
    plt.close(fig)


def format_table(df: pd.DataFrame, max_rows: int = 15) -> str:
    if df.empty:
        return "(sin datos)"
    frame = df.head(max_rows).copy().fillna("")
    try:
        return frame.to_markdown(index=False)
    except Exception:
        cols = list(frame.columns)
        rows = [" | ".join(cols), " | ".join(["---"] * len(cols))]
        for _, row in frame.iterrows():
            rows.append(" | ".join(str(row.get(col, "")) for col in cols))
        return "\n".join(rows)


def write_summary(
    events: pd.DataFrame,
    mentions: pd.DataFrame,
    snapshots: pd.DataFrame,
    diagnostics: pd.DataFrame,
    coord_diag: pd.DataFrame,
    aggregates: dict[str, pd.DataFrame],
    osm_network_summary: pd.DataFrame,
) -> None:
    total = len(events)
    valid_points = int(events["coordinate_inside_sv_bbox"].sum())
    outside = int((events["coordinate_quality_status"] == "OUTSIDE_EL_SALVADOR_BBOX").sum())
    missing = int((events["coordinate_quality_status"] == "MISSING_POINT").sum())
    repeated = int(events["repeated_coordinate_flag"].sum())
    engagement_events = int((events["engagement_mentions"] > 0).sum())
    osm_high_medium = int(events["osm_match_status"].isin(["SPATIAL_OSM_HIGH", "SPATIAL_OSM_MEDIUM"]).sum())
    total_likes = int(events["latest_likes"].sum())
    total_comments = int(events["latest_comments"].sum())
    total_shares = int(events["latest_shares"].sum())
    total_quotes = int(events["latest_quotes"].sum())
    total_views = int(events["latest_views"].sum())
    total_raw_impact = int(events["impact_raw_sum"].sum())
    resolution_counts = (
        events["text_osm_resolution"].value_counts().reset_index().rename(columns={"index": "text_osm_resolution", "count": "events"})
        if "text_osm_resolution" in events.columns
        else pd.DataFrame()
    )
    conflict_resolution = (
        events[events["text_spatial_consistency"] == "TEXT_SPATIAL_CONFLICT"]["text_osm_resolution"]
        .value_counts()
        .reset_index()
        .rename(columns={"index": "text_osm_resolution", "count": "events"})
        if "text_spatial_consistency" in events.columns and "text_osm_resolution" in events.columns
        else pd.DataFrame()
    )
    osm_coverage_summary = pd.read_csv(OSM_NATIONAL_COVERAGE_PATH) if OSM_NATIONAL_COVERAGE_PATH.exists() else pd.DataFrame()
    top_impact = events.sort_values("impact_social_score", ascending=False).head(10)[
        [
            "ticketNumber",
            "datetime",
            "incident",
            "department",
            "municipality",
            "mentions",
            "latest_views",
            "latest_shares",
            "impact_social_score",
            "coordinate_quality_status",
            "osm_match_status",
        ]
    ]

    text = [
        "RESULTADOS - ANALISIS DE INCIDENTES VIALES",
        "===========================================",
        "",
        f"Generado: {datetime.now().isoformat(timespec='seconds')}",
        f"Datos fuente: {INPUT_CSV}",
        "",
        "1. Enfoque metodologico",
        "-----------------------",
        "La base principal es incidentes.csv. La unidad principal es el evento vial deduplicado.",
        "La unidad secundaria es la mencion asociada en evidence y la unidad terciaria es el snapshot de engagement.",
        "No se excluyen coordenadas fuera de El Salvador ni coordenadas repetidas; se etiquetan como calidad/posible error.",
        "La salida no es un KPI final. Es una metrica exploratoria de presion socio-vial noticiosa.",
        "",
        "2. Resumen general",
        "------------------",
        f"Eventos deduplicados: {total}",
        f"Menciones expandidas: {len(mentions)}",
        f"Snapshots de engagement: {len(snapshots)}",
        f"Periodo observado: {events['datetime'].min()} a {events['datetime'].max()}",
        f"Eventos con coordenada dentro de El Salvador: {valid_points} ({pct(valid_points, total)}%)",
        f"Eventos fuera del bbox de El Salvador: {outside} ({pct(outside, total)}%)",
        f"Eventos sin coordenada: {missing} ({pct(missing, total)}%)",
        f"Eventos con coordenada repetida: {repeated} ({pct(repeated, total)}%)",
        f"Eventos con engagement: {engagement_events} ({pct(engagement_events, total)}%)",
        f"Eventos OSM con match alto/medio: {osm_high_medium} ({pct(osm_high_medium, total)}%)",
        f"Likes ultimo snapshot: {total_likes}",
        f"Comentarios ultimo snapshot: {total_comments}",
        f"Shares/retweets ultimo snapshot: {total_shares}",
        f"Quotes ultimo snapshot: {total_quotes}",
        f"Views ultimo snapshot: {total_views}",
        f"Impacto crudo ultimo snapshot: {total_raw_impact}",
        f"Impacto social ponderado: {round(float(events['impact_social_score'].sum()), 2)}",
        "",
        "3. Diagnostico de integridad",
        "----------------------------",
        format_table(diagnostics, max_rows=30),
        "",
        "4. Diagnostico de coordenadas",
        "-----------------------------",
        format_table(coord_diag, max_rows=20),
        "",
        "5. Ranking territorial por departamento",
        "---------------------------------------",
        format_table(aggregates["departments"], max_rows=15),
        "",
        "6. Ranking territorial por municipio",
        "-----------------------------------",
        format_table(aggregates["municipalities"], max_rows=20),
        "",
        "7. Diagnostico de normalizacion territorial",
        "-------------------------------------------",
        "Los valores originales de departamento y municipio se conservan, pero los rankings se calculan con campos normalizados.",
        "Esto evita separar artificialmente valores como SAN SALVADOR y San Salvador, o CUSCATLAN y CUSCATLÁN.",
        format_table(aggregates["territory_normalization"], max_rows=20),
        "",
        "8. Diagnostico de corredores",
        "----------------------------",
        "La variable corridor_candidate se extrae de address y observation. Representa la via, carretera, bulevar, avenida, calle o tramo mencionado en el texto.",
        "No reemplaza el match espacial OSM: sirve como lectura semantica del evento y como puente para rankings por corredor.",
        format_table(aggregates["corridor_diagnostics"], max_rows=20),
        "",
        "9. Ranking de corredores extraidos del texto",
        "--------------------------------------------",
        format_table(aggregates["corridors"], max_rows=20),
        "",
        "10. Analisis de corredores criticos",
        "----------------------------------",
        "El puntaje de criticidad de corredor combina volumen de eventos, menciones, impacto social, severidad, fallecidos, lesionados, usuarios vulnerables y asociacion OSM alta/media.",
        "Este puntaje no es KPI final; es una metrica de priorizacion exploratoria para decidir que corredores merecen revision detallada.",
        format_table(aggregates["critical_corridors"], max_rows=20),
        "",
        "11. Ranking por corredor normalizado",
        "-----------------------------------",
        "corridor_norm representa el corredor funcional consolidado. nearest_osm_name conserva el segmento local OSM y corridor_candidate conserva el texto extraido de la noticia.",
        format_table(aggregates["corridors_norm"], max_rows=20),
        "",
        "12. Resolucion texto-OSM y corridor_norm",
        "----------------------------------------",
        "Los conflictos texto-OSM no se eliminan: se clasifican como compatibles, nombre local dentro de corredor, interseccion aceptada o revision.",
        format_table(resolution_counts, max_rows=20),
        "",
        "Conflictos texto-OSM reclasificados",
        "-----------------------------------",
        format_table(conflict_resolution, max_rows=20),
        "",
        "13. Serie diaria",
        "----------------",
        format_table(aggregates["daily"], max_rows=20),
        "",
        "14. Serie horaria",
        "-----------------",
        format_table(aggregates["hourly"], max_rows=24),
        "",
        "15. Top eventos por impacto social",
        "----------------------------------",
        format_table(top_impact, max_rows=10),
        "",
        "16. Capa vial base OSM San Salvador/AMSS",
        "----------------------------------------",
        "La capa vial AMSS se conserva como capa visual capitalina y respaldo local. Esta almacenada en:",
        str(OSM_SEGMENTS_PATH),
        "La asociacion analitica evento-via ya no depende solo de esta capa: si existe red departamental, el evento usa primero su departamento; si no, usa red nacional; y como ultimo respaldo puede usar AMSS.",
        "Las capas OSM contienen atributos como highway, name, ref, oneway, lanes, maxspeed, surface y longitud.",
        format_table(osm_network_summary, max_rows=20),
        "",
        "17. Cobertura OSM departamental/nacional",
        "----------------------------------------",
        "La red OSM se descargo y particiono por departamento para evitar cargar innecesariamente una red nacional completa en cada analisis interactivo.",
        "El consolidado nacional queda como producto analitico y fallback para eventos sin red departamental disponible.",
        format_table(osm_coverage_summary, max_rows=20),
        "",
        "18. Lectura OSM evento-via",
        "--------------------------",
        "La coordenada es la fuente principal de asociacion evento-via. Con coordenada valida, se busca el segmento OSM mas cercano usando primero la red del departamento normalizado, luego la red nacional y finalmente AMSS si aplica.",
        "Si no hay coordenada, no se fuerza un match espacial: queda NO_COORDINATE_FOR_OSM y la noticia solo aporta texto, territorio y engagement.",
        format_table(events["osm_match_status"].value_counts().reset_index().rename(columns={"index": "osm_match_status", "count": "events"}), max_rows=20),
        "",
        "19. Heatmaps propuestos",
        "-----------------------",
        "Se generaron pesos para tres capas: eventos, menciones e impacto social.",
        "heat_weight_eventos = 1",
        "heat_weight_menciones = mentions",
        "heat_weight_impacto_social = likes + comments*2 + shares*3 + quotes*3 + log(1 + views)",
        "Estas capas se pueden superponer en dashboard con controles de opacidad.",
        "",
        "20. Conclusion",
        "--------------",
        "incidentes.csv tiene mayor madurez que ultimas_100_noticias.csv para visualizacion geoespacial e interaccion social.",
        "La cobertura de coordenadas permite construir una capa de puntos y heatmaps. El engagement permite medir afectacion/amplificacion social.",
        "Las coordenadas problematicas y repetidas deben permanecer como indicadores de integridad, no eliminarse.",
        "OSM debe usarse en modo spatial-first: punto -> via cercana -> atributos viales -> validacion textual.",
    ]
    (RESULTS_DIR / "resultados_incidentes.txt").write_text("\n".join(text), encoding="utf-8")


def save_outputs(events: pd.DataFrame, mentions: pd.DataFrame, snapshots: pd.DataFrame) -> None:
    events = enrich_with_osm(events)
    events = add_exploratory_metric(events)
    diagnostics, coord_diag = build_integrity_tables(events, mentions, snapshots)
    aggregates = build_aggregates(events)
    osm_network_summary = build_osm_network_summary()
    corridor_resolution, conflict_review = build_corridor_resolution_tables(events)

    events.to_csv(RESULTS_DIR / "base_eventos_incidentes_normalizada.csv", index=False)
    mentions.to_csv(RESULTS_DIR / "base_menciones_incidentes_expandida.csv", index=False)
    snapshots.to_csv(RESULTS_DIR / "base_engagement_snapshots.csv", index=False)
    diagnostics.to_csv(RESULTS_DIR / "diagnostico_integridad_incidentes.csv", index=False)
    coord_diag.to_csv(RESULTS_DIR / "diagnostico_coordenadas_incidentes.csv", index=False)
    events.to_csv(RESULTS_DIR / "eventos_incidentes_osm_enriched.csv", index=False)
    events.to_csv(RESULTS_DIR / "eventos_incidentes_osm_nacional_enriched.csv", index=False)
    events[
        events["coordinate_pair_present"]
    ].to_csv(RESULTS_DIR / "eventos_incidentes_puntos.csv", index=False)
    write_geojson(events, RESULTS_DIR / "eventos_incidentes_georreferenciados.geojson")

    aggregates["departments"].to_csv(RESULTS_DIR / "ranking_departamentos_incidentes.csv", index=False)
    aggregates["municipalities"].to_csv(RESULTS_DIR / "ranking_municipios_incidentes.csv", index=False)
    aggregates["territory_normalization"].to_csv(RESULTS_DIR / "diagnostico_normalizacion_territorial.csv", index=False)
    aggregates["corridors"].to_csv(RESULTS_DIR / "ranking_corredores_incidentes.csv", index=False)
    aggregates["corridors_norm"].to_csv(RESULTS_DIR / "ranking_corredores_norm.csv", index=False)
    aggregates["critical_corridors"].to_csv(RESULTS_DIR / "analisis_corredores_criticos.csv", index=False)
    aggregates["corridor_diagnostics"].to_csv(RESULTS_DIR / "diagnostico_corredores_incidentes.csv", index=False)
    aggregates["osm_road_type"].to_csv(RESULTS_DIR / "ranking_tipo_via_osm.csv", index=False)
    aggregates["osm_road_type"].to_csv(RESULTS_DIR / "ranking_tipo_via_osm_nacional.csv", index=False)
    corridor_resolution.to_csv(RESULTS_DIR / "corridor_norm_resolution.csv", index=False)
    conflict_review.to_csv(RESULTS_DIR / "revision_conflictos_texto_osm.csv", index=False)
    conflict_review.to_csv(RESULTS_DIR / "revision_conflictos_texto_osm_nacional.csv", index=False)
    if OSM_NATIONAL_COVERAGE_PATH.exists():
        pd.read_csv(OSM_NATIONAL_COVERAGE_PATH).to_csv(RESULTS_DIR / "diagnostico_cobertura_osm_departamental.csv", index=False)
    else:
        pd.DataFrame(
            [
                {
                    "scope": "AMSS_FALLBACK",
                    "status": "OSM_DEPARTMENTS_NOT_GENERATED",
                    "segments": int(len(pd.read_csv(OSM_SEGMENTS_PATH))) if OSM_SEGMENTS_PATH.exists() else 0,
                    "message": "Ejecuta make download-osm-departments para generar cobertura departamental/nacional.",
                }
            ]
        ).to_csv(RESULTS_DIR / "diagnostico_cobertura_osm_departamental.csv", index=False)
    osm_network_summary.to_csv(RESULTS_DIR / "resumen_red_vial_osm_amss.csv", index=False)
    aggregates["daily"].to_csv(RESULTS_DIR / "serie_temporal_eventos_incidentes.csv", index=False)
    aggregates["hourly"].to_csv(RESULTS_DIR / "serie_horaria_eventos_incidentes.csv", index=False)
    aggregates["heatmap_weights"].to_csv(RESULTS_DIR / "heatmap_weights_incidentes.csv", index=False)
    mentions.groupby("source", dropna=False).agg(
        menciones=("mention_id", "count"),
        eventos=("event_uuid", "nunique"),
        latest_likes=("latest_likes", lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum()),
        latest_comments=("latest_comments", lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum()),
        latest_shares=("latest_shares", lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum()),
        latest_quotes=("latest_quotes", lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum()),
        latest_views=("latest_views", lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum()),
    ).reset_index().sort_values("menciones", ascending=False).to_csv(
        RESULTS_DIR / "resumen_engagement_por_fuente_incidentes.csv",
        index=False,
    )
    snapshots.assign(
        captured_date=lambda df: pd.to_datetime(df["captured_at"], errors="coerce").dt.date.astype(str),
        captured_hour=lambda df: pd.to_datetime(df["captured_at"], errors="coerce").dt.hour,
    ).groupby(["captured_date", "captured_hour"], dropna=False).agg(
        snapshots=("mention_id", "count"),
        likes=("likes", lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum()),
        comments=("comments", lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum()),
        shares=("shares", lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum()),
        quotes=("quotes", lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum()),
        views=("views", lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum()),
    ).reset_index().to_csv(RESULTS_DIR / "serie_temporal_engagement_incidentes.csv", index=False)

    metric_cols = [
        "uuid",
        "ticketNumber",
        "datetime",
        "incident",
        "department",
        "municipality",
        "department_norm",
        "municipality_norm",
        "corridor_candidate",
        "corridor_norm",
        "corridor_norm_source",
        "text_osm_resolution",
        "corridor_resolution_confidence",
        "mentions",
        "impact_social_score",
        "severity_component",
        "mentions_component",
        "source_diversity_component",
        "impact_social_component",
        "geo_quality_component",
        "osm_association_component",
        "temporal_recency_component",
        "metric_score_0_100",
        "metric_category",
    ]
    events[metric_cols].to_csv(RESULTS_DIR / "metricas_exploratorias_incidentes.csv", index=False)
    save_plots(events, aggregates)
    write_summary(events, mentions, snapshots, diagnostics, coord_diag, aggregates, osm_network_summary)


def main() -> None:
    ensure_dirs()
    raw = load_raw()
    events, mentions, snapshots = build_event_tables(raw)
    save_outputs(events, mentions, snapshots)
    print(f"Resultados generados en {RESULTS_DIR}")
    print(f"Eventos: {len(events)} | Menciones: {len(mentions)} | Snapshots engagement: {len(snapshots)}")


if __name__ == "__main__":
    main()
