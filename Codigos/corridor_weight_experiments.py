#!/usr/bin/env python3
"""
Experimentos de pesos para corredores criticos de incidentes.

Este modulo no busca pesos optimos. Sin una verdad externa observada
(siniestralidad oficial, aforos, tiempos de viaje u otra referencia), los
pesos son escenarios metodologicos para evaluar sensibilidad y robustez.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "Results" / "News" / "Incidentes"
BASE_CANDIDATES = [
    RESULTS_DIR / "analisis_corredores_criticos.csv",
    RESULTS_DIR / "ranking_corredores_norm.csv",
]
EXPERIMENTS_CSV = RESULTS_DIR / "experimentos_pesos_corredores.csv"
SENSITIVITY_CSV = RESULTS_DIR / "sensibilidad_pesos_corredores.csv"
REPORT_TXT = RESULTS_DIR / "experimentos_pesos_corredores.txt"


INPUT_COLUMNS = [
    "events",
    "severity_sum",
    "fatality_events",
    "injury_events",
    "vulnerable_events",
    "mentions",
    "impact_social",
    "osm_high_medium",
]


WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "ACTUAL_PIPELINE": {
        "events": 0.24,
        "mentions": 0.14,
        "impact_social": 0.18,
        "severity_sum": 0.16,
        "fatality_events": 0.10,
        "injury_events": 0.07,
        "vulnerable_events": 0.05,
        "osm_high_medium": 0.06,
    },
    "A_RECURRENCIA_VOLUMEN": {
        "events": 0.40,
        "severity_sum": 0.18,
        "fatality_events": 0.10,
        "injury_events": 0.07,
        "vulnerable_events": 0.05,
        "mentions": 0.08,
        "impact_social": 0.07,
        "osm_high_medium": 0.05,
    },
    "B_SEVERIDAD": {
        "events": 0.16,
        "mentions": 0.06,
        "impact_social": 0.08,
        "severity_sum": 0.25,
        "fatality_events": 0.20,
        "injury_events": 0.12,
        "vulnerable_events": 0.08,
        "osm_high_medium": 0.05,
    },
    "C_SOCIAL_NOTICIOSO": {
        "events": 0.14,
        "mentions": 0.25,
        "impact_social": 0.35,
        "severity_sum": 0.08,
        "fatality_events": 0.05,
        "injury_events": 0.04,
        "vulnerable_events": 0.03,
        "osm_high_medium": 0.06,
    },
}


PROFILE_LABELS = {
    "ACTUAL_PIPELINE": "Score actual del pipeline exploratorio",
    "A_RECURRENCIA_VOLUMEN": "Escenario A: recurrencia y volumen",
    "B_SEVERIDAD": "Escenario B: severidad vial",
    "C_SOCIAL_NOTICIOSO": "Escenario C: amplificacion social/noticiosa",
}


def validate_weights() -> None:
    for profile, weights in WEIGHT_PROFILES.items():
        total = sum(weights.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"Los pesos de {profile} suman {total:.6f}, no 1.0")


def load_base_corridors() -> pd.DataFrame:
    for path in BASE_CANDIDATES:
        if path.exists():
            df = pd.read_csv(path)
            if not df.empty:
                return df
    candidates = ", ".join(str(path) for path in BASE_CANDIDATES)
    raise FileNotFoundError(f"No existe una tabla base de corredores. Ejecuta primero el pipeline. Rutas buscadas: {candidates}")


def choose_corridor_col(df: pd.DataFrame) -> str:
    for col in ["corridor_norm", "corridor_candidate"]:
        if col in df.columns:
            nonempty = df[col].fillna("").astype(str).str.strip()
            if (nonempty != "").any():
                return col
    raise ValueError("La tabla base no contiene corridor_norm ni corridor_candidate con informacion util.")


def prepare_base(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    corridor_col = choose_corridor_col(df)
    base = df.copy()
    base[corridor_col] = base[corridor_col].fillna("").astype(str).str.strip()
    base = base[base[corridor_col] != ""].copy()

    for col in INPUT_COLUMNS:
        if col not in base.columns:
            base[col] = 0.0
        base[col] = pd.to_numeric(base[col], errors="coerce").fillna(0.0)

    if "corridor_criticality_score" in base.columns:
        base["corridor_criticality_score"] = pd.to_numeric(base["corridor_criticality_score"], errors="coerce").fillna(0.0)

    for col in INPUT_COLUMNS:
        denom = max(float(base[col].max()), 1.0)
        base[f"{col}_norm_for_weights"] = base[col].astype(float) / denom

    return base, corridor_col


def score_profile(base: pd.DataFrame, profile: str, weights: dict[str, float], corridor_col: str) -> pd.DataFrame:
    scored = base[[corridor_col, *INPUT_COLUMNS]].copy()
    scored["profile"] = profile
    scored["profile_label"] = PROFILE_LABELS[profile]
    score = 0.0
    for col, weight in weights.items():
        component = base[f"{col}_norm_for_weights"].astype(float) * weight
        scored[f"component_{col}"] = (100 * component).round(4)
        score = score + component
    scored["score_0_100"] = (100 * score).round(4)
    scored["rank"] = scored["score_0_100"].rank(method="min", ascending=False).astype(int)
    scored = scored.rename(columns={corridor_col: "corridor"})
    return scored.sort_values(["rank", "corridor"])


def classify_robustness(top5_frequency: int) -> str:
    if top5_frequency >= 3:
        return "ROBUSTO"
    if top5_frequency == 1:
        return "DEPENDIENTE_DEL_ENFOQUE"
    if top5_frequency == 0:
        return "NO_PRIORITARIO"
    return "INTERMEDIO"


def build_sensitivity(experiments: pd.DataFrame) -> pd.DataFrame:
    rank_pivot = experiments.pivot_table(index="corridor", columns="profile", values="rank", aggfunc="min")
    score_pivot = experiments.pivot_table(index="corridor", columns="profile", values="score_0_100", aggfunc="max")

    rank_cols = {profile: f"rank_{profile}" for profile in WEIGHT_PROFILES}
    score_cols = {profile: f"score_{profile}" for profile in WEIGHT_PROFILES}
    sensitivity = pd.concat(
        [
            rank_pivot.rename(columns=rank_cols),
            score_pivot.rename(columns=score_cols),
        ],
        axis=1,
    ).reset_index()

    profile_rank_cols = [f"rank_{profile}" for profile in WEIGHT_PROFILES]
    profile_score_cols = [f"score_{profile}" for profile in WEIGHT_PROFILES]
    sensitivity["ranking_promedio"] = sensitivity[profile_rank_cols].mean(axis=1).round(2)
    sensitivity["desviacion_estandar_ranking"] = sensitivity[profile_rank_cols].std(axis=1, ddof=0).round(2)
    sensitivity["score_promedio_normalizado"] = sensitivity[profile_score_cols].mean(axis=1).round(2)
    sensitivity["frecuencia_top_3"] = (sensitivity[profile_rank_cols] <= 3).sum(axis=1).astype(int)
    sensitivity["frecuencia_top_5"] = (sensitivity[profile_rank_cols] <= 5).sum(axis=1).astype(int)
    sensitivity["frecuencia_top_10"] = (sensitivity[profile_rank_cols] <= 10).sum(axis=1).astype(int)
    sensitivity["clasificacion_robustez"] = sensitivity["frecuencia_top_5"].map(classify_robustness)
    return sensitivity.sort_values(
        ["frecuencia_top_5", "frecuencia_top_10", "ranking_promedio", "score_promedio_normalizado"],
        ascending=[False, False, True, False],
    )


def format_weights(weights: dict[str, float]) -> str:
    parts = [f"{col}={weight:.2f}" for col, weight in weights.items()]
    return "; ".join(parts)


def top_list(experiments: pd.DataFrame, profile: str, n: int = 10) -> list[str]:
    subset = experiments[experiments["profile"] == profile].sort_values("rank").head(n)
    rows = []
    for _, row in subset.iterrows():
        rows.append(f"{int(row['rank'])}. {row['corridor']} - score {row['score_0_100']:.2f}")
    return rows


def write_report(base: pd.DataFrame, corridor_col: str, experiments: pd.DataFrame, sensitivity: pd.DataFrame) -> None:
    lines: list[str] = []
    lines.append("Experimentos de pesos para corredores criticos")
    lines.append("=" * 52)
    lines.append("")
    lines.append("Alcance metodologico")
    lines.append("--------------------")
    lines.append(
        "Estos experimentos no aprenden pesos optimos porque no existe una verdad observada externa contra la cual entrenar o calibrar "
        "el score, por ejemplo siniestralidad oficial, aforos, velocidades reales o tiempos de viaje. Lo que se evalua es sensibilidad: "
        "si un corredor permanece critico cuando cambia el enfoque analitico."
    )
    lines.append("")
    lines.append(f"Tabla base utilizada: {corridor_col}. Corredores evaluados: {len(base)}.")
    lines.append("")
    lines.append("Pesos evaluados")
    lines.append("----------------")
    for profile, weights in WEIGHT_PROFILES.items():
        lines.append(f"{profile} ({PROFILE_LABELS[profile]}): {format_weights(weights)}. Suma={sum(weights.values()):.2f}")
    lines.append("")
    lines.append("Lectura de variables")
    lines.append("--------------------")
    lines.append("events: volumen de eventos asociados al corredor.")
    lines.append("severity_sum: severidad acumulada de los eventos reportados.")
    lines.append("fatality_events, injury_events y vulnerable_events: senales de gravedad y usuarios vulnerables.")
    lines.append("mentions e impact_social: amplificacion noticiosa/social, no equivalen a accidentalidad real.")
    lines.append("osm_high_medium: eventos con asociacion espacial OSM alta o media.")
    lines.append("")
    for profile in WEIGHT_PROFILES:
        lines.append(f"Top 10 - {profile}")
        lines.append("-" * (8 + len(profile)))
        lines.extend(top_list(experiments, profile))
        lines.append("")
    lines.append("Corredores robustos")
    lines.append("-------------------")
    robust = sensitivity[sensitivity["clasificacion_robustez"] == "ROBUSTO"].head(15)
    if robust.empty:
        lines.append("No hay corredores que aparezcan en top 5 en al menos tres escenarios.")
    else:
        for _, row in robust.iterrows():
            lines.append(
                f"{row['corridor']} - top5={int(row['frecuencia_top_5'])}/4, "
                f"ranking_promedio={row['ranking_promedio']:.2f}, "
                f"score_promedio={row['score_promedio_normalizado']:.2f}"
            )
    lines.append("")
    lines.append("Interpretacion")
    lines.append("---------------")
    lines.append(
        "Un corredor ROBUSTO merece analisis prioritario porque no depende de un unico supuesto de ponderacion. "
        "Un corredor DEPENDIENTE_DEL_ENFOQUE puede ser relevante, pero solo bajo una lectura especifica, por ejemplo social o severidad. "
        "Un corredor NO_PRIORITARIO no aparece recurrentemente en los escenarios evaluados."
    )
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run() -> dict[str, Any]:
    validate_weights()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    raw = load_base_corridors()
    base, corridor_col = prepare_base(raw)
    experiments = pd.concat(
        [score_profile(base, profile, weights, corridor_col) for profile, weights in WEIGHT_PROFILES.items()],
        ignore_index=True,
    )
    sensitivity = build_sensitivity(experiments)

    experiments.to_csv(EXPERIMENTS_CSV, index=False)
    sensitivity.to_csv(SENSITIVITY_CSV, index=False)
    write_report(base, corridor_col, experiments, sensitivity)
    return {
        "corridors": len(base),
        "experiments": len(experiments),
        "robust": int((sensitivity["clasificacion_robustez"] == "ROBUSTO").sum()),
        "outputs": [EXPERIMENTS_CSV, SENSITIVITY_CSV, REPORT_TXT],
    }


def main() -> None:
    result = run()
    print(
        "Experimentos de pesos generados: "
        f"{result['corridors']} corredores, {result['experiments']} filas, "
        f"{result['robust']} corredores robustos."
    )
    for path in result["outputs"]:
        print(path)


if __name__ == "__main__":
    main()
