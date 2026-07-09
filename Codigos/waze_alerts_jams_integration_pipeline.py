#!/usr/bin/env python3
"""
Pipeline integrado Waze alerts + Waze jams.

Unidad metodologica principal:
- corredor-hora: permite comparar eventos reportados (alerts) con presion
  operacional de congestion (jams) sin asumir causalidad.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import pandas as pd

from waze_jams_analysis_pipeline import ROOT, compact_text, pct, robust_norm


JAMS_UNIQUE_PATH = ROOT / "Results" / "Waze" / "Jams" / "waze_jams_unique_enriched.csv"
JAMS_HOUR_PATH = ROOT / "Results" / "Waze" / "Jams" / "waze_jams_corridor_hour.csv"
JAMS_SUMMARY_PATH = ROOT / "Results" / "Waze" / "Jams" / "waze_jams_corridor_summary.csv"
ALERTS_UNIQUE_PATH = ROOT / "Results" / "Waze" / "Alerts" / "waze_alerts_unique_enriched.csv"
ALERTS_HOUR_PATH = ROOT / "Results" / "Waze" / "Alerts" / "waze_alerts_corridor_hour.csv"
ALERTS_SUMMARY_PATH = ROOT / "Results" / "Waze" / "Alerts" / "waze_alerts_corridor_summary.csv"

RESULTS_DIR = ROOT / "Results" / "Waze" / "Integrated"
INFORME_DIR = ROOT / "Informes" / "Informe_4"
TOTAL_HOURS = 24


def ensure_dirs() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    INFORME_DIR.mkdir(parents=True, exist_ok=True)


def require_inputs() -> None:
    required = [
        JAMS_UNIQUE_PATH,
        JAMS_HOUR_PATH,
        JAMS_SUMMARY_PATH,
        ALERTS_UNIQUE_PATH,
        ALERTS_HOUR_PATH,
        ALERTS_SUMMARY_PATH,
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Faltan insumos procesados:\n" + "\n".join(missing))


def corridor_key(value: Any) -> str:
    text = compact_text(value)
    return text if text else "unresolved"


def clean_corridor(value: Any, fallback: str = "UNRESOLVED") -> str:
    text = "" if value is None or pd.isna(value) else str(value).strip()
    return text if text else fallback


def normalize_01(series: pd.Series, upper_quantile: float = 0.95) -> pd.Series:
    return robust_norm(pd.to_numeric(series, errors="coerce").fillna(0), upper_quantile=upper_quantile).fillna(0)


def safe_divide(numerator: pd.Series, denominator: pd.Series, fill_value: float = 0.0) -> pd.Series:
    num = pd.to_numeric(numerator, errors="coerce").fillna(0).astype(float)
    den = pd.to_numeric(denominator, errors="coerce").fillna(0).astype(float)
    return (num / den.where(den != 0)).fillna(fill_value)


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    jams = pd.read_csv(JAMS_UNIQUE_PATH, low_memory=False)
    jams_hour = pd.read_csv(JAMS_HOUR_PATH, low_memory=False)
    jams_summary = pd.read_csv(JAMS_SUMMARY_PATH, low_memory=False)
    alerts = pd.read_csv(ALERTS_UNIQUE_PATH, low_memory=False)
    alerts_hour = pd.read_csv(ALERTS_HOUR_PATH, low_memory=False)
    alerts_summary = pd.read_csv(ALERTS_SUMMARY_PATH, low_memory=False)
    return jams, jams_hour, jams_summary, alerts, alerts_hour, alerts_summary


def build_key_crosswalk(jams_summary: pd.DataFrame, alerts_summary: pd.DataFrame) -> pd.DataFrame:
    jams = jams_summary.copy()
    alerts = alerts_summary.copy()
    jams["corridor_key"] = jams["corridor_norm_waze"].map(corridor_key)
    alerts["corridor_key"] = alerts["corridor_norm_alert"].map(corridor_key)
    j = jams.groupby("corridor_key", dropna=False).agg(
        corridor_name_jams=("corridor_norm_waze", "first"),
        jams_count_total=("jams_count_total", "sum"),
        jam_intensity_total=("jam_intensity_total", "sum"),
        corridor_jam_pressure_score=("corridor_jam_pressure_score", "max"),
    ).reset_index()
    a = alerts.groupby("corridor_key", dropna=False).agg(
        corridor_name_alerts=("corridor_norm_alert", "first"),
        alerts_count_total=("alerts_count_total", "sum"),
        corridor_alert_impact=("corridor_alert_impact", "sum"),
        corridor_alert_pressure=("corridor_alert_pressure", "max"),
    ).reset_index()
    out = j.merge(a, on="corridor_key", how="outer")
    out["corridor_name"] = out["corridor_name_alerts"].fillna(out["corridor_name_jams"]).fillna("UNRESOLVED")
    out.loc[out["corridor_key"].eq("unresolved"), "corridor_name"] = "UNRESOLVED"
    numeric_cols = [
        "jams_count_total",
        "jam_intensity_total",
        "corridor_jam_pressure_score",
        "alerts_count_total",
        "corridor_alert_impact",
        "corridor_alert_pressure",
    ]
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0)
    out["has_jams"] = out["jams_count_total"] > 0
    out["has_alerts"] = out["alerts_count_total"] > 0
    out.to_csv(RESULTS_DIR / "waze_integrated_corridor_key_crosswalk.csv", index=False)
    return out


def aggregate_jams_hour(jams: pd.DataFrame) -> pd.DataFrame:
    df = jams.copy()
    df["corridor_name"] = df["corridor_norm_waze_group"].map(clean_corridor)
    df["corridor_key"] = df["corridor_name"].map(corridor_key)
    grouped = df.groupby(["corridor_key", "event_hour"], dropna=False).agg(
        jam_count=("uuid", "nunique"),
        jam_records_count=("records_per_uuid", "sum"),
        jam_delay_total=("delay_min", "sum"),
        jam_congestion_load=("congestion_load", "sum"),
        jam_intensity_total=("jam_intensity_score", "sum"),
        jam_intensity_avg=("jam_intensity_score", "mean"),
        severe_jam_count=("severe_jam_flag", "sum"),
        extreme_jam_count=("extreme_jam_flag", "sum"),
        speed_collapse_count=("speed_collapse_flag", "sum"),
        jam_match_confidence_avg=("corridor_match_confidence_score", "mean"),
        jam_estimation_stability_avg=("jam_estimation_stability", "mean"),
        jam_avg_speed=("speed_mean", "mean"),
        jam_min_speed=("speed_min", "min"),
    ).reset_index()
    return grouped


def aggregate_alerts_hour(alerts: pd.DataFrame) -> pd.DataFrame:
    df = alerts.copy()
    df["corridor_name"] = df["corridor_norm_alert_group"].map(clean_corridor)
    df["corridor_key"] = df["corridor_name"].map(corridor_key)
    grouped = df.groupby(["corridor_key", "event_hour"], dropna=False).agg(
        alert_count=("uuid", "nunique"),
        alert_reports_count=("cluster_report_count", "sum"),
        alert_impact_total=("alert_impact_score", "sum"),
        alert_impact_avg=("alert_impact_score", "mean"),
        alert_severity_avg=("severity_proxy", "mean"),
        alert_reliability_avg=("alert_reliability_proxy", "mean"),
        critical_alert_count=("is_critical_alert", "sum"),
        safety_alert_count=("is_safety_alert", "sum"),
        operational_alert_count=("is_operational_alert", "sum"),
        accident_count=("alert_group", lambda s: int((s == "ACCIDENTE").sum())),
        closure_count=("alert_group", lambda s: int((s == "CIERRE_VIAL").sum())),
        hazard_count=("type", lambda s: int((s == "HAZARD").sum())),
        stopped_traffic_alert_count=("alert_group", lambda s: int((s == "TRAFICO_DETENIDO").sum())),
        heavy_traffic_alert_count=("alert_group", lambda s: int((s == "TRAFICO_PESADO").sum())),
        spatial_confidence_alerts=("osm_spatial_confidence_score", "mean"),
        alert_corridor_match_confidence_avg=("corridor_match_confidence_score", "mean"),
    ).reset_index()
    return grouped


def build_corridor_hour_panel(
    jams: pd.DataFrame,
    alerts: pd.DataFrame,
    crosswalk: pd.DataFrame,
) -> pd.DataFrame:
    jams_h = aggregate_jams_hour(jams)
    alerts_h = aggregate_alerts_hour(alerts)
    keys = sorted(set(crosswalk["corridor_key"].dropna().astype(str)))
    grid = pd.MultiIndex.from_product([keys, range(TOTAL_HOURS)], names=["corridor_key", "event_hour"]).to_frame(index=False)
    panel = grid.merge(jams_h, on=["corridor_key", "event_hour"], how="left")
    panel = panel.merge(alerts_h, on=["corridor_key", "event_hour"], how="left")
    panel = panel.merge(crosswalk[["corridor_key", "corridor_name"]], on="corridor_key", how="left")

    count_cols = [
        "jam_count",
        "jam_records_count",
        "jam_delay_total",
        "jam_congestion_load",
        "jam_intensity_total",
        "severe_jam_count",
        "extreme_jam_count",
        "speed_collapse_count",
        "alert_count",
        "alert_reports_count",
        "alert_impact_total",
        "critical_alert_count",
        "safety_alert_count",
        "operational_alert_count",
        "accident_count",
        "closure_count",
        "hazard_count",
        "stopped_traffic_alert_count",
        "heavy_traffic_alert_count",
    ]
    for col in count_cols:
        if col in panel.columns:
            panel[col] = pd.to_numeric(panel[col], errors="coerce").fillna(0)
    for col in [
        "jam_intensity_avg",
        "jam_match_confidence_avg",
        "jam_estimation_stability_avg",
        "jam_avg_speed",
        "jam_min_speed",
        "alert_impact_avg",
        "alert_severity_avg",
        "alert_reliability_avg",
        "spatial_confidence_alerts",
        "alert_corridor_match_confidence_avg",
    ]:
        if col in panel.columns:
            panel[col] = pd.to_numeric(panel[col], errors="coerce").fillna(0)

    panel["has_jam"] = panel["jam_count"] > 0
    panel["has_alert"] = panel["alert_count"] > 0
    panel["alert_jam_same_hour_flag"] = panel["has_jam"] & panel["has_alert"]
    panel["alert_to_jam_ratio"] = safe_divide(panel["alert_count"], panel["jam_count"]).clip(upper=10)
    panel["jam_without_alert_flag"] = panel["has_jam"] & ~panel["has_alert"]
    panel["alert_without_jam_flag"] = panel["has_alert"] & ~panel["has_jam"]

    panel = panel.sort_values(["corridor_key", "event_hour"]).reset_index(drop=True)
    panel["alert_impact_prev_1h"] = panel.groupby("corridor_key")["alert_impact_total"].shift(1).fillna(0)
    panel["alert_impact_next_1h"] = panel.groupby("corridor_key")["alert_impact_total"].shift(-1).fillna(0)
    panel["alert_count_prev_1h"] = panel.groupby("corridor_key")["alert_count"].shift(1).fillna(0)
    panel["alert_count_next_1h"] = panel.groupby("corridor_key")["alert_count"].shift(-1).fillna(0)
    panel["jam_intensity_prev_1h"] = panel.groupby("corridor_key")["jam_intensity_total"].shift(1).fillna(0)
    panel["jam_intensity_next_1h"] = panel.groupby("corridor_key")["jam_intensity_total"].shift(-1).fillna(0)
    panel["alert_leads_jam_1h_flag"] = panel["has_jam"] & (panel["alert_count_prev_1h"] > 0)
    panel["alert_lags_jam_1h_flag"] = panel["has_jam"] & (panel["alert_count_next_1h"] > 0)
    panel["alert_jam_pm1h_window_flag"] = panel["has_jam"] & (
        panel["has_alert"] | (panel["alert_count_prev_1h"] > 0) | (panel["alert_count_next_1h"] > 0)
    )
    panel["event_congestion_overlap"] = panel["alert_jam_same_hour_flag"]
    panel["alert_jam_lead_1h_flag"] = panel["alert_leads_jam_1h_flag"]
    panel["alert_jam_lag_1h_flag"] = panel["alert_lags_jam_1h_flag"]
    panel["corridor_match_confidence_jams"] = panel["jam_match_confidence_avg"]

    panel["operational_congestion_pressure"] = (
        100
        * (
            0.30 * normalize_01(panel["jam_intensity_total"])
            + 0.25 * normalize_01(panel["jam_delay_total"])
            + 0.20 * normalize_01(panel["jam_congestion_load"])
            + 0.15 * normalize_01(panel["jam_count"])
            + 0.10 * normalize_01(panel["severe_jam_count"], upper_quantile=1.0)
        )
    ).round(4)
    panel["critical_alert_pressure"] = (
        100
        * (
            0.35 * normalize_01(panel["alert_impact_total"])
            + 0.25 * normalize_01(panel["alert_count"])
            + 0.20 * normalize_01(panel["critical_alert_count"], upper_quantile=1.0)
            + 0.10 * normalize_01(panel["alert_reports_count"])
            + 0.10 * normalize_01(panel["accident_count"] + panel["closure_count"], upper_quantile=1.0)
        )
    ).round(4)
    panel["temporal_alignment_score"] = (
        100
        * (
            0.55 * panel["alert_jam_same_hour_flag"].astype(float)
            + 0.25 * panel["alert_leads_jam_1h_flag"].astype(float)
            + 0.20 * panel["alert_lags_jam_1h_flag"].astype(float)
        )
    ).round(4)
    panel["integrated_reliability_score"] = (
        100
        * (
            0.35 * panel["jam_match_confidence_avg"].fillna(0)
            + 0.25 * panel["spatial_confidence_alerts"].fillna(0)
            + 0.20 * panel["alert_corridor_match_confidence_avg"].fillna(0)
            + 0.20 * panel["jam_estimation_stability_avg"].fillna(0)
        )
    ).round(4)
    panel["integrated_corridor_hour_pressure"] = (
        0.45 * panel["operational_congestion_pressure"]
        + 0.35 * panel["critical_alert_pressure"]
        + 0.12 * panel["temporal_alignment_score"]
        + 0.08 * panel["integrated_reliability_score"]
    ).round(4)
    panel.loc[panel["corridor_key"].eq("unresolved"), "integrated_corridor_hour_pressure"] = 0.0
    panel["explanatory_alert_share"] = (
        panel["critical_alert_pressure"] / (panel["critical_alert_pressure"] + panel["operational_congestion_pressure"] + 1e-9)
    ).round(4)
    panel["data_quality_flags"] = panel.apply(data_quality_flags, axis=1)
    panel.to_csv(RESULTS_DIR / "waze_integrated_corridor_hour.csv", index=False)
    return panel


def data_quality_flags(row: pd.Series) -> str:
    flags: list[str] = []
    if row.get("corridor_key") == "unresolved":
        flags.append("UNRESOLVED_CORRIDOR")
    if bool(row.get("has_jam")) and not bool(row.get("has_alert")):
        flags.append("JAM_WITHOUT_ALERT")
    if bool(row.get("has_alert")) and not bool(row.get("has_jam")):
        flags.append("ALERT_WITHOUT_JAM")
    if row.get("integrated_reliability_score", 0) < 35 and (row.get("has_jam") or row.get("has_alert")):
        flags.append("LOW_INTEGRATED_RELIABILITY")
    return ";".join(flags)


def quadrant_label(jam_score: float, alert_score: float, jam_threshold: float, alert_threshold: float) -> str:
    high_jam = jam_score >= jam_threshold
    high_alert = alert_score >= alert_threshold
    if high_jam and high_alert:
        return "ALTA_CONGESTION_ALTAS_ALERTAS"
    if high_jam and not high_alert:
        return "ALTA_CONGESTION_BAJAS_ALERTAS"
    if not high_jam and high_alert:
        return "BAJA_CONGESTION_ALTAS_ALERTAS"
    return "BAJA_CONGESTION_BAJAS_ALERTAS"


def build_corridor_summary(panel: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    active = panel.copy()
    summary = active.groupby(["corridor_key", "corridor_name"], dropna=False).agg(
        jam_count_total=("jam_count", "sum"),
        jam_delay_total=("jam_delay_total", "sum"),
        jam_congestion_load_total=("jam_congestion_load", "sum"),
        jam_intensity_total=("jam_intensity_total", "sum"),
        severe_jam_count_total=("severe_jam_count", "sum"),
        speed_collapse_count_total=("speed_collapse_count", "sum"),
        alert_count_total=("alert_count", "sum"),
        alert_reports_total=("alert_reports_count", "sum"),
        alert_impact_total=("alert_impact_total", "sum"),
        critical_alert_count_total=("critical_alert_count", "sum"),
        accident_count_total=("accident_count", "sum"),
        closure_count_total=("closure_count", "sum"),
        hazard_count_total=("hazard_count", "sum"),
        stopped_traffic_alert_count_total=("stopped_traffic_alert_count", "sum"),
        same_hour_overlap_count=("alert_jam_same_hour_flag", "sum"),
        alert_leads_jam_1h_count=("alert_leads_jam_1h_flag", "sum"),
        alert_lags_jam_1h_count=("alert_lags_jam_1h_flag", "sum"),
        pm1h_window_overlap_count=("alert_jam_pm1h_window_flag", "sum"),
        jam_without_alert_hours=("jam_without_alert_flag", "sum"),
        alert_without_jam_hours=("alert_without_jam_flag", "sum"),
        integrated_pressure_total=("integrated_corridor_hour_pressure", "sum"),
        integrated_pressure_max=("integrated_corridor_hour_pressure", "max"),
        temporal_alignment_avg=("temporal_alignment_score", "mean"),
        reliability_avg=("integrated_reliability_score", "mean"),
    ).reset_index()
    summary["jam_active_hours"] = panel[panel["has_jam"]].groupby("corridor_key")["event_hour"].nunique().reindex(summary["corridor_key"]).fillna(0).to_numpy()
    summary["alert_active_hours"] = panel[panel["has_alert"]].groupby("corridor_key")["event_hour"].nunique().reindex(summary["corridor_key"]).fillna(0).to_numpy()
    summary["integrated_active_hours"] = (
        panel[panel["has_jam"] | panel["has_alert"]].groupby("corridor_key")["event_hour"].nunique().reindex(summary["corridor_key"]).fillna(0).to_numpy()
    )
    summary["same_hour_overlap_rate"] = safe_divide(
        summary["same_hour_overlap_count"], summary["integrated_active_hours"]
    ).round(4)
    summary["jam_hours_explained_same_hour_rate"] = safe_divide(
        summary["same_hour_overlap_count"], summary["jam_active_hours"]
    ).round(4)
    summary["jam_hours_with_alert_pm1h_rate"] = safe_divide(
        summary["pm1h_window_overlap_count"], summary["jam_active_hours"]
    ).round(4)
    summary["alert_to_jam_ratio_total"] = safe_divide(
        summary["alert_count_total"], summary["jam_count_total"]
    ).clip(upper=10).round(4)
    summary["explanatory_alert_share"] = (
        normalize_01(summary["alert_impact_total"])
        / (normalize_01(summary["alert_impact_total"]) + normalize_01(summary["jam_intensity_total"]) + 1e-9)
    ).round(4)

    summary["jam_pressure_norm"] = (
        100
        * (
            0.35 * normalize_01(summary["jam_intensity_total"])
            + 0.25 * normalize_01(summary["jam_delay_total"])
            + 0.20 * normalize_01(summary["jam_congestion_load_total"])
            + 0.20 * normalize_01(summary["jam_active_hours"], upper_quantile=1.0)
        )
    ).round(4)
    summary["alert_pressure_norm"] = (
        100
        * (
            0.35 * normalize_01(summary["alert_impact_total"])
            + 0.25 * normalize_01(summary["alert_count_total"])
            + 0.20 * normalize_01(summary["critical_alert_count_total"], upper_quantile=1.0)
            + 0.20 * normalize_01(summary["alert_active_hours"], upper_quantile=1.0)
        )
    ).round(4)
    balance = 1 - (
        abs(summary["jam_pressure_norm"] - summary["alert_pressure_norm"])
        / (summary["jam_pressure_norm"] + summary["alert_pressure_norm"] + 1e-9)
    )
    summary["corridor_event_congestion_coupling"] = (
        100
        * (
            0.30 * summary["same_hour_overlap_rate"]
            + 0.25 * summary["jam_hours_with_alert_pm1h_rate"]
            + 0.20 * balance.clip(0, 1)
            + 0.15 * normalize_01(summary["same_hour_overlap_count"], upper_quantile=1.0)
            + 0.10 * normalize_01(summary["critical_alert_count_total"], upper_quantile=1.0)
        )
    ).round(4)
    summary["integrated_corridor_pressure"] = (
        0.40 * summary["jam_pressure_norm"]
        + 0.35 * summary["alert_pressure_norm"]
        + 0.15 * summary["corridor_event_congestion_coupling"]
        + 0.10 * normalize_01(summary["integrated_pressure_total"]) * 100
    ).round(4)
    summary.loc[summary["corridor_key"].eq("unresolved"), "integrated_corridor_pressure"] = 0.0

    active_summary = summary[~summary["corridor_key"].eq("unresolved")].copy()
    jam_threshold = float(active_summary["jam_pressure_norm"].quantile(0.75)) if not active_summary.empty else 0
    alert_threshold = float(active_summary["alert_pressure_norm"].quantile(0.75)) if not active_summary.empty else 0
    summary["quadrant"] = summary.apply(
        lambda row: quadrant_label(row["jam_pressure_norm"], row["alert_pressure_norm"], jam_threshold, alert_threshold),
        axis=1,
    )
    summary["integration_priority"] = summary.apply(classify_priority, axis=1)
    summary = summary.sort_values("integrated_corridor_pressure", ascending=False)
    summary.to_csv(RESULTS_DIR / "waze_integrated_corridor_summary.csv", index=False)
    summary[summary["corridor_key"].ne("unresolved")].head(50).to_csv(
        RESULTS_DIR / "top_corredores_presion_integrada.csv", index=False
    )
    summary[summary["corridor_key"].ne("unresolved")].sort_values("jam_pressure_norm", ascending=False).head(50).to_csv(
        RESULTS_DIR / "top_corredores_por_jams.csv", index=False
    )
    summary[summary["corridor_key"].ne("unresolved")].sort_values("alert_pressure_norm", ascending=False).head(50).to_csv(
        RESULTS_DIR / "top_corredores_por_alerts.csv", index=False
    )
    summary[
        summary["corridor_key"].ne("unresolved")
        & (summary["jam_count_total"] > 0)
        & (summary["alert_count_total"] > 0)
    ].sort_values("integrated_corridor_pressure", ascending=False).to_csv(
        RESULTS_DIR / "corredores_comunes_alerts_jams.csv", index=False
    )
    summary[["quadrant", "corridor_key", "corridor_name", "jam_pressure_norm", "alert_pressure_norm", "integrated_corridor_pressure"]].to_csv(
        RESULTS_DIR / "waze_integrated_quadrants.csv", index=False
    )
    return summary


def classify_priority(row: pd.Series) -> str:
    if row["corridor_key"] == "unresolved":
        return "NO_PRIORIZAR_SIN_CORREDOR"
    if row["integrated_corridor_pressure"] >= 75 and row["corridor_event_congestion_coupling"] >= 45:
        return "CRITICO_INTEGRADO"
    if row["jam_pressure_norm"] >= 70 and row["alert_pressure_norm"] < 35:
        return "CONGESTION_NO_EXPLICADA_POR_ALERTS"
    if row["alert_pressure_norm"] >= 70 and row["jam_pressure_norm"] < 35:
        return "EVENTOS_SIN_CONGESTION_PROPORCIONAL"
    if row["integrated_corridor_pressure"] >= 55:
        return "PRIORIDAD_MEDIA_ALTA"
    if row["corridor_event_congestion_coupling"] >= 45:
        return "ACOPLAMIENTO_RELEVANTE"
    return "OBSERVACION_COMPLEMENTARIA"


def build_hourly_summary(panel: pd.DataFrame) -> pd.DataFrame:
    hourly = panel.groupby("event_hour", dropna=False).agg(
        jam_count=("jam_count", "sum"),
        jam_delay_total=("jam_delay_total", "sum"),
        jam_intensity_total=("jam_intensity_total", "sum"),
        alert_count=("alert_count", "sum"),
        alert_impact_total=("alert_impact_total", "sum"),
        critical_alert_count=("critical_alert_count", "sum"),
        same_hour_overlap_count=("alert_jam_same_hour_flag", "sum"),
        jam_without_alert_hours=("jam_without_alert_flag", "sum"),
        alert_without_jam_hours=("alert_without_jam_flag", "sum"),
        integrated_pressure_total=("integrated_corridor_hour_pressure", "sum"),
    ).reset_index()
    hourly["same_hour_overlap_share"] = safe_divide(
        hourly["same_hour_overlap_count"],
        hourly["same_hour_overlap_count"] + hourly["jam_without_alert_hours"] + hourly["alert_without_jam_hours"],
    ).round(4)
    hourly.to_csv(RESULTS_DIR / "waze_integrated_hourly_summary.csv", index=False)
    return hourly


def build_lag_analysis(panel: pd.DataFrame) -> pd.DataFrame:
    active = panel[panel["corridor_key"].ne("unresolved")].copy()
    rows = []
    for lag in [-2, -1, 0, 1, 2]:
        shifted = active.sort_values(["corridor_key", "event_hour"]).copy()
        shifted_alert = shifted.groupby("corridor_key")["alert_impact_total"].shift(lag * -1 if lag != 0 else 0)
        # Interpretation: negative lag = alert before jam; positive lag = alert after jam.
        valid = pd.DataFrame(
            {
                "jam": shifted["jam_intensity_total"],
                "alert_shifted": shifted_alert.fillna(0),
            }
        )
        valid = valid[(valid["jam"] > 0) | (valid["alert_shifted"] > 0)]
        pearson = valid["alert_shifted"].corr(valid["jam"], method="pearson") if len(valid) > 2 else 0
        spearman = valid["alert_shifted"].corr(valid["jam"], method="spearman") if len(valid) > 2 else 0
        rows.append(
            {
                "lag_hours_alert_vs_jam": lag,
                "interpretation": "alert_before_jam" if lag < 0 else "same_hour" if lag == 0 else "alert_after_jam",
                "n_active_rows": int(len(valid)),
                "pearson_alert_impact_vs_jam_intensity": round(float(pearson or 0), 4),
                "spearman_alert_impact_vs_jam_intensity": round(float(spearman or 0), 4),
            }
        )
    out = pd.DataFrame(rows)
    out.to_csv(RESULTS_DIR / "waze_integrated_lag_analysis.csv", index=False)
    return out


def build_correlation_outputs(panel: pd.DataFrame, summary: pd.DataFrame) -> pd.DataFrame:
    active_hour = panel[(panel["corridor_key"].ne("unresolved")) & ((panel["jam_count"] > 0) | (panel["alert_count"] > 0))].copy()
    pairs = [
        ("corridor_hour", active_hour, "alert_impact_total", "jam_intensity_total"),
        ("corridor_hour", active_hour, "critical_alert_count", "jam_delay_total"),
        ("corridor_hour", active_hour, "alert_count", "jam_count"),
        ("corridor_day", summary[summary["corridor_key"].ne("unresolved")], "alert_impact_total", "jam_intensity_total"),
        ("corridor_day", summary[summary["corridor_key"].ne("unresolved")], "critical_alert_count_total", "jam_delay_total"),
        ("corridor_day", summary[summary["corridor_key"].ne("unresolved")], "alert_count_total", "jam_count_total"),
    ]
    rows = []
    for level, df, x, y in pairs:
        sub = df[[x, y]].apply(pd.to_numeric, errors="coerce").fillna(0)
        sub = sub[(sub[x] > 0) | (sub[y] > 0)]
        pearson = sub[x].corr(sub[y], method="pearson") if len(sub) > 2 else 0
        spearman = sub[x].corr(sub[y], method="spearman") if len(sub) > 2 else 0
        rows.append(
            {
                "analysis_level": level,
                "x_variable": x,
                "y_variable": y,
                "n_rows": int(len(sub)),
                "pearson": round(float(pearson or 0), 4),
                "spearman": round(float(spearman or 0), 4),
            }
        )
    out = pd.DataFrame(rows)
    out.to_csv(RESULTS_DIR / "waze_integrated_correlations.csv", index=False)
    return out


def build_quality_outputs(
    jams: pd.DataFrame,
    alerts: pd.DataFrame,
    panel: pd.DataFrame,
    summary: pd.DataFrame,
    lag: pd.DataFrame,
    correlations: pd.DataFrame,
) -> pd.DataFrame:
    active_panel = panel[(panel["jam_count"] > 0) | (panel["alert_count"] > 0)]
    resolved_summary = summary[summary["corridor_key"].ne("unresolved")]
    common_corridors = int(((resolved_summary["jam_count_total"] > 0) & (resolved_summary["alert_count_total"] > 0)).sum())
    only_jams = int(((resolved_summary["jam_count_total"] > 0) & (resolved_summary["alert_count_total"] == 0)).sum())
    only_alerts = int(((resolved_summary["jam_count_total"] == 0) & (resolved_summary["alert_count_total"] > 0)).sum())
    rows = [
        ("jams_unique", int(jams["uuid"].nunique()), "Jams unicos integrados."),
        ("alerts_unique", int(alerts["uuid"].nunique()), "Alertas unicas integradas."),
        ("corridor_keys_total", int(summary["corridor_key"].nunique()), "Corredores normalizados en la union."),
        ("common_corridors_alerts_jams", common_corridors, "Corredores resueltos con alerts y jams."),
        ("only_jams_corridors", only_jams, "Corredores resueltos con jams pero sin alerts."),
        ("only_alerts_corridors", only_alerts, "Corredores resueltos con alerts pero sin jams."),
        ("corridor_hour_rows", int(len(panel)), "Filas corredor-hora en grilla completa."),
        ("active_corridor_hour_rows", int(len(active_panel)), "Filas corredor-hora con actividad en alguna fuente."),
        ("same_hour_overlap_rows", int(panel["alert_jam_same_hour_flag"].sum()), "Corredor-hora con alertas y jams simultaneos."),
        ("jam_without_alert_rows", int(panel["jam_without_alert_flag"].sum()), "Corredor-hora con jams sin alertas."),
        ("alert_without_jam_rows", int(panel["alert_without_jam_flag"].sum()), "Corredor-hora con alertas sin jams."),
        (
            "best_lag_pearson",
            float(lag.sort_values("pearson_alert_impact_vs_jam_intensity", ascending=False).iloc[0]["lag_hours_alert_vs_jam"]),
            "Lag con mayor correlacion Pearson alert_impact vs jam_intensity.",
        ),
        (
            "corridor_hour_alert_impact_jam_intensity_pearson",
            float(
                correlations[
                    (correlations["analysis_level"] == "corridor_hour")
                    & (correlations["x_variable"] == "alert_impact_total")
                ]["pearson"].iloc[0]
            ),
            "Correlacion corredor-hora entre impacto alerts e intensidad jams.",
        ),
    ]
    quality = pd.DataFrame(rows, columns=["metric", "value", "description"])
    quality.to_csv(RESULTS_DIR / "waze_integrated_quality_diagnostics.csv", index=False)

    summary[summary["integration_priority"].eq("CONGESTION_NO_EXPLICADA_POR_ALERTS")].head(50).to_csv(
        RESULTS_DIR / "corredores_congestion_no_explicada_por_alerts.csv", index=False
    )
    summary[summary["integration_priority"].eq("EVENTOS_SIN_CONGESTION_PROPORCIONAL")].head(50).to_csv(
        RESULTS_DIR / "corredores_eventos_sin_congestion_proporcional.csv", index=False
    )
    summary[summary["same_hour_overlap_count"] > 0].sort_values("corridor_event_congestion_coupling", ascending=False).head(50).to_csv(
        RESULTS_DIR / "corredores_mayor_acoplamiento_evento_congestion.csv", index=False
    )
    return quality


def save_barh(df: pd.DataFrame, x: str, y: str, title: str, path: Path, xlabel: str, color: str = "#2563eb") -> None:
    plot_df = df[[x, y]].dropna().head(15).iloc[::-1]
    fig, ax = plt.subplots(figsize=(11, 7))
    ax.barh(plot_df[y], plot_df[x], color=color)
    ax.set_title(title, loc="left", fontweight="bold")
    ax.set_xlabel(xlabel)
    ax.grid(axis="x", alpha=0.25)
    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def generate_figures(panel: pd.DataFrame, summary: pd.DataFrame, hourly: pd.DataFrame, lag: pd.DataFrame) -> pd.DataFrame:
    figures: list[dict[str, Any]] = []

    fig, ax1 = plt.subplots(figsize=(11, 4.8))
    ax1.plot(hourly["event_hour"], hourly["jam_count"], marker="o", color="#2563eb", label="Jams")
    ax1.set_ylabel("Jams", color="#2563eb")
    ax1.tick_params(axis="y", labelcolor="#2563eb")
    ax2 = ax1.twinx()
    ax2.plot(hourly["event_hour"], hourly["alert_count"], marker="o", color="#dc2626", label="Alerts")
    ax2.set_ylabel("Alerts", color="#dc2626")
    ax2.tick_params(axis="y", labelcolor="#dc2626")
    ax1.set_title("Serie horaria comparada: alerts vs jams", loc="left", fontweight="bold")
    ax1.set_xlabel("Hora local")
    ax1.set_xticks(range(24))
    ax1.grid(alpha=0.25)
    fig.tight_layout()
    path = RESULTS_DIR / "fig_integrated_hourly_counts.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    figures.append(figure_meta(path, "Serie horaria comparada alerts vs jams", "event_hour, jam_count, alert_count", "hora", "Compara volumen horario de ambas fuentes."))

    fig, ax = plt.subplots(figsize=(11, 4.8))
    ax.plot(hourly["event_hour"], normalize_01(hourly["jam_intensity_total"], upper_quantile=1.0), marker="o", color="#2563eb", label="Jam intensity normalizada")
    ax.plot(hourly["event_hour"], normalize_01(hourly["alert_impact_total"], upper_quantile=1.0), marker="o", color="#dc2626", label="Alert impact normalizado")
    ax.set_title("Presion horaria normalizada: alerts vs jams", loc="left", fontweight="bold")
    ax.set_xlabel("Hora local")
    ax.set_ylabel("Valor normalizado 0-1")
    ax.set_xticks(range(24))
    ax.grid(alpha=0.25)
    ax.legend()
    fig.tight_layout()
    path = RESULTS_DIR / "fig_integrated_hourly_pressure.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    figures.append(figure_meta(path, "Presion horaria normalizada alerts vs jams", "event_hour, jam_intensity_total, alert_impact_total", "hora", "Permite ver si los picos horarios de eventos y congestion coinciden."))

    active = panel[(panel["corridor_key"].ne("unresolved")) & ((panel["alert_impact_total"] > 0) | (panel["jam_intensity_total"] > 0))].copy()
    fig, ax = plt.subplots(figsize=(10.5, 6.5))
    colors = active["alert_jam_same_hour_flag"].map({True: "#dc2626", False: "#64748b"})
    ax.scatter(active["alert_impact_total"], active["jam_intensity_total"], s=18, alpha=0.55, c=colors)
    ax.set_xscale("symlog")
    ax.set_yscale("symlog")
    ax.set_title("Relacion corredor-hora: impacto alerts vs intensidad jams", loc="left", fontweight="bold")
    ax.set_xlabel("Alert impact total")
    ax.set_ylabel("Jam intensity total")
    ax.grid(alpha=0.25)
    ax.legend(
        handles=[
            Line2D([0], [0], marker="o", color="w", label="Alerts + jams misma hora", markerfacecolor="#dc2626", markersize=7),
            Line2D([0], [0], marker="o", color="w", label="Solo una fuente activa", markerfacecolor="#64748b", markersize=7),
        ],
        loc="best",
        frameon=False,
    )
    fig.tight_layout()
    path = RESULTS_DIR / "fig_integrated_scatter_alert_vs_jam.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    figures.append(figure_meta(path, "Scatter alert impact vs jam intensity", "alert_impact_total, jam_intensity_total", "corredor-hora", "Identifica acoplamiento y casos desacoplados entre eventos y congestion."))

    top = summary[summary["corridor_key"].ne("unresolved")].sort_values("integrated_corridor_pressure", ascending=False).head(20)
    matrix = panel[panel["corridor_key"].isin(top["corridor_key"])].pivot_table(
        index="corridor_name",
        columns="event_hour",
        values="integrated_corridor_hour_pressure",
        aggfunc="sum",
        fill_value=0,
    )
    matrix = matrix.reindex(top["corridor_name"].tolist())
    for hour in range(24):
        if hour not in matrix.columns:
            matrix[hour] = 0
    matrix = matrix[range(24)]
    fig, ax = plt.subplots(figsize=(13, 8))
    im = ax.imshow(matrix.values, aspect="auto", cmap="magma")
    ax.set_title("Heatmap integrado corredor-hora", loc="left", fontweight="bold")
    ax.set_xlabel("Hora local")
    ax.set_ylabel("Corredor")
    ax.set_xticks(range(24))
    ax.set_yticks(range(len(matrix.index)))
    ax.set_yticklabels(matrix.index)
    fig.colorbar(im, ax=ax, label="Presion integrada")
    fig.tight_layout()
    path = RESULTS_DIR / "fig_integrated_heatmap_corridor_hour.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    figures.append(figure_meta(path, "Heatmap integrado corredor-hora", "integrated_corridor_hour_pressure", "corredor-hora", "Muestra donde y cuando se concentra la presion combinada."))

    save_barh(
        summary[summary["corridor_key"].ne("unresolved")].sort_values("integrated_corridor_pressure", ascending=False),
        "integrated_corridor_pressure",
        "corridor_name",
        "Top corredores por presion integrada",
        RESULTS_DIR / "fig_integrated_top_corridors.png",
        "Score 0-100",
        "#7c3aed",
    )
    figures.append(figure_meta(RESULTS_DIR / "fig_integrated_top_corridors.png", "Top corredores por presion integrada", "integrated_corridor_pressure", "corredor-dia", "Prioriza corredores combinando congestion y eventos reportados."))

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(lag["lag_hours_alert_vs_jam"].astype(str), lag["pearson_alert_impact_vs_jam_intensity"], color="#0f766e")
    ax.axhline(0, color="#111827", linewidth=0.8)
    ax.set_title("Correlacion por rezago temporal", loc="left", fontweight="bold")
    ax.set_xlabel("Lag alerts vs jams (horas)")
    ax.set_ylabel("Pearson")
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    path = RESULTS_DIR / "fig_integrated_lag_correlation.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    figures.append(figure_meta(path, "Correlacion por rezago temporal", "lag, pearson", "corredor-hora", "Evalua si alerts se alinean mejor antes, durante o despues de jams."))

    q = summary[summary["corridor_key"].ne("unresolved")].copy()
    fig, ax = plt.subplots(figsize=(8, 6.5))
    q_colors = {
        "ALTA_CONGESTION_ALTAS_ALERTAS": "#dc2626",
        "ALTA_CONGESTION_BAJAS_ALERTAS": "#2563eb",
        "BAJA_CONGESTION_ALTAS_ALERTAS": "#f59e0b",
        "BAJA_CONGESTION_BAJAS_ALERTAS": "#64748b",
    }
    ax.scatter(
        q["alert_pressure_norm"],
        q["jam_pressure_norm"],
        s=(q["integrated_corridor_pressure"].clip(lower=5) * 1.6),
        alpha=0.6,
        c=q["quadrant"].map(q_colors).fillna("#64748b"),
    )
    ax.set_title("Cuadrantes: alertas vs congestion por corredor", loc="left", fontweight="bold")
    ax.set_xlabel("Presion por alerts")
    ax.set_ylabel("Presion por jams")
    ax.grid(alpha=0.25)
    ax.legend(
        handles=[
            Line2D([0], [0], marker="o", color="w", label="Alta congestion + altas alertas", markerfacecolor="#dc2626", markersize=8),
            Line2D([0], [0], marker="o", color="w", label="Alta congestion + bajas alertas", markerfacecolor="#2563eb", markersize=8),
            Line2D([0], [0], marker="o", color="w", label="Baja congestion + altas alertas", markerfacecolor="#f59e0b", markersize=8),
            Line2D([0], [0], marker="o", color="w", label="Baja congestion + bajas alertas", markerfacecolor="#64748b", markersize=8),
        ],
        loc="center left",
        bbox_to_anchor=(1.01, 0.5),
        frameon=False,
    )
    fig.tight_layout()
    path = RESULTS_DIR / "fig_integrated_quadrants.png"
    fig.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(fig)
    figures.append(figure_meta(path, "Cuadrantes alerts vs jams", "alert_pressure_norm, jam_pressure_norm", "corredor-dia", "Distingue corredores acoplados, congestion no explicada y eventos sin congestion proporcional."))

    fig, ax = plt.subplots(figsize=(11, 5))
    width = 0.27
    h = hourly["event_hour"]
    ax.bar(h - width, hourly["same_hour_overlap_count"], width=width, label="Alerts + jams", color="#16a34a")
    ax.bar(h, hourly["jam_without_alert_hours"], width=width, label="Jams sin alerts", color="#2563eb")
    ax.bar(h + width, hourly["alert_without_jam_hours"], width=width, label="Alerts sin jams", color="#dc2626")
    ax.set_title("Coincidencia temporal por hora", loc="left", fontweight="bold")
    ax.set_xlabel("Hora local")
    ax.set_ylabel("Corredor-hora")
    ax.set_xticks(range(24))
    ax.grid(axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    path = RESULTS_DIR / "fig_integrated_overlap_by_hour.png"
    fig.savefig(path, dpi=180)
    plt.close(fig)
    figures.append(figure_meta(path, "Coincidencia temporal por hora", "same_hour_overlap, jam_without_alert, alert_without_jam", "hora", "Mide horas donde las fuentes se superponen o se desacoplan."))

    catalog = pd.DataFrame(figures)
    return catalog


def figure_meta(path: Path, title: str, variables: str, level: str, finding_seed: str) -> dict[str, Any]:
    return {
        "figure_file": str(path.relative_to(ROOT)),
        "figure_title": title,
        "data_source": "Results/Waze/Jams + Results/Waze/Alerts",
        "variables_used": variables,
        "analysis_level": level,
        "main_finding": finding_seed,
        "decision_value": "",
        "recommended_report_section": "",
        "limitations": "",
    }


def enrich_figure_catalog(
    catalog: pd.DataFrame,
    panel: pd.DataFrame,
    summary: pd.DataFrame,
    hourly: pd.DataFrame,
    lag: pd.DataFrame,
    correlations: pd.DataFrame,
) -> pd.DataFrame:
    top_corridor = summary[summary["corridor_key"].ne("unresolved")].iloc[0]
    top_hour_alert = hourly.sort_values("alert_impact_total", ascending=False).iloc[0]
    top_hour_jam = hourly.sort_values("jam_intensity_total", ascending=False).iloc[0]
    best_lag = lag.sort_values("pearson_alert_impact_vs_jam_intensity", ascending=False).iloc[0]
    same_hour = int(panel["alert_jam_same_hour_flag"].sum())
    jam_without = int(panel["jam_without_alert_flag"].sum())
    alert_without = int(panel["alert_without_jam_flag"].sum())
    corr_hour = correlations[
        (correlations["analysis_level"] == "corridor_hour")
        & (correlations["x_variable"] == "alert_impact_total")
        & (correlations["y_variable"] == "jam_intensity_total")
    ].iloc[0]
    quadrant_counts = summary["quadrant"].value_counts().to_dict()

    details = {
        "fig_integrated_hourly_counts.png": {
            "main_finding": f"Alerts tienen su mayor volumen a las {int(top_hour_alert['event_hour']):02d}:00; jams alcanzan mayor intensidad a las {int(top_hour_jam['event_hour']):02d}:00.",
            "decision_value": "Permite ubicar ventanas horarias para monitoreo operacional integrado.",
            "recommended_report_section": "Resultados temporales",
            "limitations": "Un solo dia no permite inferir estacionalidad ni patron semanal.",
        },
        "fig_integrated_hourly_pressure.png": {
            "main_finding": "Compara las curvas normalizadas de impacto de alertas e intensidad de jams para detectar picos coincidentes o desplazados.",
            "decision_value": "Ayuda a decidir si conviene monitorear alertas como senal temprana de congestion.",
            "recommended_report_section": "Resultados temporales",
            "limitations": "La normalizacion facilita comparacion visual, pero oculta magnitudes absolutas.",
        },
        "fig_integrated_scatter_alert_vs_jam.png": {
            "main_finding": f"La correlacion corredor-hora entre impacto de alertas e intensidad jam es Pearson {corr_hour['pearson']:.2f} y Spearman {corr_hour['spearman']:.2f}.",
            "decision_value": "Identifica si la relacion es suficientemente fuerte para una metrica integrada.",
            "recommended_report_section": "Analisis estadistico",
            "limitations": "No prueba causalidad; muchas filas corredor-hora pueden tener solo una fuente activa.",
        },
        "fig_integrated_heatmap_corridor_hour.png": {
            "main_finding": f"El corredor con mayor presion integrada es {top_corridor['corridor_name']}.",
            "decision_value": "Prioriza corredores y horas para gestion o dashboard.",
            "recommended_report_section": "Ranking integrado",
            "limitations": "Se muestran top corredores; corredores menores quedan fuera de la visualizacion.",
        },
        "fig_integrated_top_corridors.png": {
            "main_finding": f"{top_corridor['corridor_name']} lidera la presion integrada con score {top_corridor['integrated_corridor_pressure']:.2f}.",
            "decision_value": "Sirve como ranking ejecutivo de priorizacion.",
            "recommended_report_section": "Ranking integrado",
            "limitations": "El score usa pesos exploratorios, no calibrados contra verdad externa.",
        },
        "fig_integrated_lag_correlation.png": {
            "main_finding": f"El mejor rezago observado es {int(best_lag['lag_hours_alert_vs_jam'])} h con Pearson {best_lag['pearson_alert_impact_vs_jam_intensity']:.2f}.",
            "decision_value": "Evalua si alerts tienden a aparecer antes, durante o despues de jams.",
            "recommended_report_section": "Analisis de rezagos",
            "limitations": "Con un dia de datos, el rezago es exploratorio y sensible a outliers.",
        },
        "fig_integrated_quadrants.png": {
            "main_finding": f"Distribucion de cuadrantes: {json.dumps(quadrant_counts, ensure_ascii=False)}.",
            "decision_value": "Separa corredores acoplados de congestion no explicada o eventos sin congestion proporcional.",
            "recommended_report_section": "Discusion de resultados",
            "limitations": "Los umbrales de alto/bajo usan percentiles internos del dia.",
        },
        "fig_integrated_overlap_by_hour.png": {
            "main_finding": f"Hay {same_hour} corredor-hora con coincidencia, {jam_without} con jams sin alerts y {alert_without} con alerts sin jams.",
            "decision_value": "Mide cobertura cruzada y brechas de explicacion.",
            "recommended_report_section": "Calidad de integracion",
            "limitations": "La coincidencia por hora no implica causalidad ni secuencia exacta.",
        },
    }
    enriched = catalog.copy()
    for idx, row in enriched.iterrows():
        name = Path(row["figure_file"]).name
        if name in details:
            for key, value in details[name].items():
                enriched.at[idx, key] = value
    enriched.to_csv(RESULTS_DIR / "catalogo_figuras_waze_integrado.csv", index=False)
    return enriched


def write_figure_analysis(catalog: pd.DataFrame) -> None:
    lines: list[str] = []
    lines.append("Analisis de figuras Waze integrado alerts + jams")
    lines.append("=" * 58)
    lines.append("")
    for _, row in catalog.iterrows():
        lines.append(row["figure_title"])
        lines.append("-" * len(row["figure_title"]))
        lines.append(f"Archivo: {row['figure_file']}")
        lines.append(f"Unidad de analisis: {row['analysis_level']}")
        lines.append(f"Variables: {row['variables_used']}")
        lines.append(f"Hallazgo principal: {row['main_finding']}")
        lines.append(f"Valor para decision: {row['decision_value']}")
        lines.append(f"Seccion recomendada: {row['recommended_report_section']}")
        lines.append(f"Limitaciones: {row['limitations']}")
        lines.append("")
    (RESULTS_DIR / "analisis_figuras_waze_integrado.txt").write_text("\n".join(lines), encoding="utf-8")

    md: list[str] = ["# Analisis De Figuras Waze Integrado", ""]
    for _, row in catalog.iterrows():
        md.append(f"## {row['figure_title']}")
        md.append("")
        md.append(f"![{row['figure_title']}](../../{row['figure_file']})")
        md.append("")
        md.append(f"**Unidad de analisis:** {row['analysis_level']}")
        md.append("")
        md.append(f"**Variables:** `{row['variables_used']}`")
        md.append("")
        md.append(f"**Hallazgo principal:** {row['main_finding']}")
        md.append("")
        md.append(f"**Valor para decision:** {row['decision_value']}")
        md.append("")
        md.append(f"**Limitacion:** {row['limitations']}")
        md.append("")
    (INFORME_DIR / "analisis_figuras_waze_integrado.md").write_text("\n".join(md), encoding="utf-8")


def write_results_report(
    jams: pd.DataFrame,
    alerts: pd.DataFrame,
    panel: pd.DataFrame,
    summary: pd.DataFrame,
    hourly: pd.DataFrame,
    lag: pd.DataFrame,
    correlations: pd.DataFrame,
    quality: pd.DataFrame,
) -> None:
    top = summary[summary["corridor_key"].ne("unresolved")].head(15)
    active_summary = summary[summary["corridor_key"].ne("unresolved")].copy()
    top_jams = active_summary.sort_values("jam_pressure_norm", ascending=False).head(5)
    top_alerts = active_summary.sort_values("alert_pressure_norm", ascending=False).head(5)
    corr_hour = correlations[
        (correlations["analysis_level"] == "corridor_hour")
        & (correlations["x_variable"] == "alert_impact_total")
        & (correlations["y_variable"] == "jam_intensity_total")
    ].iloc[0]
    lines = []
    lines.append("Resultados Waze integrado alerts + jams")
    lines.append("=" * 46)
    lines.append("")
    lines.append("Decision metodologica")
    lines.append("---------------------")
    lines.append(
        "La unidad principal es corredor-hora. Esta unidad permite observar coincidencia, ausencia y rezagos "
        "entre eventos reportados por usuarios y congestion operacional sin afirmar causalidad."
    )
    lines.append("")
    lines.append("Resumen general")
    lines.append("---------------")
    lines.append(f"- Jams unicos: {jams['uuid'].nunique():,}")
    lines.append(f"- Alerts unicas: {alerts['uuid'].nunique():,}")
    lines.append(f"- Corredores integrados: {summary['corridor_key'].nunique():,}")
    resolved_summary = summary[summary["corridor_key"].ne("unresolved")]
    lines.append(
        f"- Corredores resueltos con ambas fuentes: "
        f"{int(((resolved_summary['jam_count_total'] > 0) & (resolved_summary['alert_count_total'] > 0)).sum()):,}"
    )
    lines.append(f"- Corredor-hora con coincidencia alerts+jams: {int(panel['alert_jam_same_hour_flag'].sum()):,}")
    lines.append(f"- Corredor-hora con jams sin alerts: {int(panel['jam_without_alert_flag'].sum()):,}")
    lines.append(f"- Corredor-hora con alerts sin jams: {int(panel['alert_without_jam_flag'].sum()):,}")
    lines.append("")
    lines.append("Correlacion")
    lines.append("-----------")
    lines.append(
        f"- Corredor-hora alert_impact_total vs jam_intensity_total: Pearson {corr_hour['pearson']:.4f}, "
        f"Spearman {corr_hour['spearman']:.4f}."
    )
    best_lag = lag.sort_values("pearson_alert_impact_vs_jam_intensity", ascending=False).iloc[0]
    lines.append(
        f"- Mejor rezago exploratorio: {int(best_lag['lag_hours_alert_vs_jam'])} h "
        f"({best_lag['interpretation']}), Pearson {best_lag['pearson_alert_impact_vs_jam_intensity']:.4f}."
    )
    lines.append("")
    lines.append("Top corredores por presion integrada")
    lines.append("------------------------------------")
    for _, row in top.iterrows():
        lines.append(
            f"- {row['corridor_name']}: score {row['integrated_corridor_pressure']:.2f}, "
            f"jams {int(row['jam_count_total']):,}, alerts {int(row['alert_count_total']):,}, "
            f"overlap {int(row['same_hour_overlap_count'])} horas, cuadrante {row['quadrant']}."
        )
    lines.append("")
    lines.append("Comparacion por fuente")
    lines.append("----------------------")
    lines.append("Top 5 por presion de jams:")
    for _, row in top_jams.iterrows():
        lines.append(
            f"- {row['corridor_name']}: jam_pressure {row['jam_pressure_norm']:.2f}, "
            f"jams {int(row['jam_count_total']):,}, demora total {row['jam_delay_total']:.2f} min."
        )
    lines.append("Top 5 por presion de alerts:")
    for _, row in top_alerts.iterrows():
        lines.append(
            f"- {row['corridor_name']}: alert_pressure {row['alert_pressure_norm']:.2f}, "
            f"alerts {int(row['alert_count_total']):,}, impacto {row['alert_impact_total']:.2f}."
        )
    lines.append("")
    lines.append("Calidad de integracion")
    lines.append("----------------------")
    for _, row in quality.iterrows():
        lines.append(f"- {row['metric']}: {row['value']} ({row['description']})")
    lines.append("")
    lines.append("Interpretacion")
    lines.append("--------------")
    lines.append(
        "La integracion muestra que alerts y jams son complementarios. Los corredores con alta presion integrada "
        "combinan congestion observada, eventos reportados, recurrencia temporal y cierto grado de coincidencia. "
        "Los corredores con congestion no explicada por alerts son candidatos para revisar cobertura de reportes o "
        "causas no capturadas por alertas. Los corredores con eventos sin congestion proporcional pueden indicar "
        "eventos localizados, incidentes de seguridad sin gran efecto de flujo o baja sensibilidad de jams."
    )
    lines.append("")
    lines.append("Metrica preliminar")
    lines.append("------------------")
    lines.append(
        "Nombre propuesto: Presion Integrada Evento-Congestion Waze (PIEC-Waze). "
        "La metrica no es KPI final; es una medida exploratoria para ordenar corredores segun presion operacional "
        "de congestion, presion por eventos reportados, acoplamiento temporal y confiabilidad de asociacion."
    )
    lines.append(
        "El resultado mas fuerte de esta fase es que la metrica permite separar corredores acoplados "
        "(alta congestion y altas alertas), corredores con congestion no explicada por alerts y corredores "
        "con eventos reportados sin congestion proporcional."
    )
    lines.append("")
    lines.append("Lectura para decision")
    lines.append("---------------------")
    lines.append(
        "La evidencia sugiere que alerts y jams deben usarse como capas complementarias. Jams aporta la condicion "
        "operacional; alerts aporta contexto de eventos. Cuando ambas coinciden por corredor-hora, la senal es mas "
        "rica para priorizacion y monitoreo. Cuando no coinciden, la discrepancia tambien aporta informacion: puede "
        "mostrar baja cobertura de reportes, eventos puntuales sin efecto de flujo o congestion de origen no reportado."
    )
    lines.append("")
    lines.append("Limitaciones")
    lines.append("------------")
    lines.append("- Un solo dia no permite inferir patrones estructurales.")
    lines.append("- La coincidencia corredor-hora no prueba causalidad.")
    lines.append("- Los pesos de la presion integrada son exploratorios.")
    lines.append("- La normalizacion de corredores condiciona la calidad de la integracion.")
    lines.append("- Para madurar hacia KPI se requiere mas historico, validacion externa y analisis de sensibilidad de pesos.")
    (RESULTS_DIR / "resultados_waze_integrado.txt").write_text("\n".join(lines), encoding="utf-8")


def write_methodology_md() -> None:
    text = """# Metodologia Para El Manejo Integrado De Waze Alerts Y Jams

## 1. Proposito

Esta fase integra los resultados ya procesados de `waze_jams_2026-06-29.json` y `waze_alerts_2026-06-29.json`. El objetivo es estudiar la relacion entre congestion operacional y eventos viales reportados por usuarios.

La integracion no busca reemplazar los analisis separados. Su valor esta en construir una capa comun que permita responder si una condicion operacional de congestion esta acompanada por reportes ciudadanos, si los reportes aparecen antes o despues de la congestion, y que corredores concentran ambas senales.

## 2. Unidad De Analisis

La unidad principal es:

```text
corredor-hora
```

Esta unidad permite comparar ambas fuentes sin afirmar causalidad. Un jam y una alerta se consideran coincidentes cuando comparten `corridor_norm` y `event_hour`.

La eleccion de corredor-hora es metodologica: evita comparar registros individuales que no tienen la misma naturaleza. Un `jam` representa una condicion operacional estimada por Waze; una `alert` representa un reporte puntual o cluster de reportes de usuarios. Por eso se agregan ambas fuentes a una unidad comun antes de compararlas.

## 3. Fuentes

```text
Results/Waze/Jams/waze_jams_unique_enriched.csv
Results/Waze/Jams/waze_jams_corridor_hour.csv
Results/Waze/Jams/waze_jams_corridor_summary.csv
Results/Waze/Alerts/waze_alerts_unique_enriched.csv
Results/Waze/Alerts/waze_alerts_corridor_hour.csv
Results/Waze/Alerts/waze_alerts_corridor_summary.csv
```

## 4. Llave Comun De Integracion

La llave comun es `corridor_key`, construida a partir de los corredores normalizados de cada pipeline:

```text
jams:   corridor_norm_waze -> compact_text -> corridor_key
alerts: corridor_norm_alert -> compact_text -> corridor_key
```

Esto permite unir nombres funcionales equivalentes aunque provengan de procesos separados. Los casos no resueltos se mantienen como `UNRESOLVED` y no se eliminan, porque tambien son evidencia de calidad de datos y de normalizacion vial pendiente.

## 5. Variables Integradas

Se construyen variables por corredor-hora:

```text
jam_count
jam_delay_total
jam_congestion_load
jam_intensity_total
severe_jam_count
speed_collapse_count
alert_count
alert_impact_total
critical_alert_count
accident_count
closure_count
hazard_count
stopped_traffic_alert_count
alert_jam_same_hour_flag
event_congestion_overlap
alert_jam_lead_1h_flag
alert_jam_lag_1h_flag
alert_leads_jam_1h_flag
alert_lags_jam_1h_flag
jam_without_alert_flag
alert_without_jam_flag
alert_to_jam_ratio
spatial_confidence_alerts
corridor_match_confidence_jams
operational_congestion_pressure
critical_alert_pressure
temporal_alignment_score
integrated_reliability_score
integrated_corridor_hour_pressure
```

## 6. Relacion Temporal

Se evalua:

```text
misma hora: alerts y jams en corredor-hora
alerta previa: alerta en h-1 y jam en h
alerta posterior: alerta en h+1 y jam en h
ventana +-1h: alerta en h-1, h o h+1 con jam en h
```

Estas reglas separan tres conceptos:

- coincidencia: ambas fuentes aparecen en el mismo corredor-hora;
- rezago: una fuente aparece antes o despues de la otra;
- posible explicacion operacional: una alerta critica coincide o antecede una condicion de congestion.

La ultima categoria no se interpreta como causalidad. Solo indica una relacion temporal y territorial que merece seguimiento.

## 7. Metrica Integrada Preliminar

Nombre propuesto:

```text
Presion Integrada Evento-Congestion Waze (PIEC-Waze)
```

La metrica se calcula en dos niveles:

```text
integrated_corridor_hour_pressure
integrated_corridor_pressure
```

El score integrado es exploratorio:

```text
integrated_corridor_hour_pressure =
  0.45 * operational_congestion_pressure
  + 0.35 * critical_alert_pressure
  + 0.12 * temporal_alignment_score
  + 0.08 * integrated_reliability_score
```

El resumen por corredor usa:

```text
integrated_corridor_pressure =
  0.40 * jam_pressure_norm
  + 0.35 * alert_pressure_norm
  + 0.15 * corridor_event_congestion_coupling
  + 0.10 * integrated_pressure_total_norm
```

No es KPI final. Es una metrica de prueba para evaluar si la combinacion de fuentes aporta valor. Su objetivo es ordenar corredores segun presion operacional, presion por eventos reportados, coincidencia temporal y confiabilidad de asociacion.

## 8. Componentes

`operational_congestion_pressure` resume la senal de `jams`: intensidad de congestion, demora, carga de congestion, volumen de jams y jams severos.

`critical_alert_pressure` resume la senal de `alerts`: impacto de alertas, cantidad de alertas, alertas criticas, reportes agrupados, accidentes y cierres.

`temporal_alignment_score` mide coincidencia o vecindad temporal entre alertas y jams.

`integrated_reliability_score` pondera la confianza de asociacion a corredor y estabilidad de los datos procesados.

`corridor_event_congestion_coupling` resume que tan acopladas estan las fuentes en un corredor a lo largo del dia.

## 9. Analisis Estadistico

Se calculan correlaciones Pearson y Spearman entre:

```text
alert_impact_total vs jam_intensity_total
critical_alert_count vs jam_delay_total
alert_count vs jam_count
```

Tambien se calcula correlacion con rezagos de -2, -1, 0, +1 y +2 horas.

## 10. Cuadrantes De Interpretacion

La integracion permite identificar:

```text
corredores con alta congestion y altas alertas
corredores con alta congestion y bajas alertas
corredores con altas alertas y baja congestion
corredores con baja presion en ambas fuentes
```

Esto ayuda a separar senales acopladas, brechas de reporte y eventos que no generan congestion proporcional.

## 11. Que Mide Cada Fuente

`jams` mide condiciones operacionales estimadas por Waze: demora, velocidad, longitud afectada, nivel de congestion e intensidad.

`alerts` mide eventos reportados por usuarios: accidentes, peligros, cierres, vehiculos detenidos, trafico detenido, obras, objetos en via y otros reportes.

La integracion mide una relacion espaciotemporal entre ambas: donde y cuando congestion y eventos reportados aparecen juntos, separados o desacoplados.

## 12. Que No Se Puede Inferir Todavia

No se puede afirmar causalidad entre alertas y jams con un solo dia de datos.

No se puede afirmar que todos los jams tengan una alerta explicativa, porque Waze puede detectar congestion sin que un usuario reporte un evento.

No se puede afirmar que todas las alertas produzcan congestion, porque hay eventos puntuales de seguridad que no afectan de forma fuerte el flujo.

No se puede considerar este score como KPI final sin validacion temporal, calibracion de pesos y contraste con fuentes externas.

## 13. Maduracion Hacia KPI

Para madurar esta metrica hacia un KPI de movilidad se requiere:

- ampliar el periodo a varios dias, semanas y tipos de dia;
- validar estabilidad de rankings por corredor;
- calibrar pesos por sensibilidad y, si existe, contra una fuente externa;
- mejorar normalizacion de corredores entre Waze, OSM y fuentes institucionales;
- separar dias atipicos de patrones recurrentes;
- medir capacidad explicativa de alerts sobre jams por corredor, franja horaria y tipo de evento.
"""
    (INFORME_DIR / "metodologia_waze_integrado.md").write_text(text, encoding="utf-8")


def write_results_md(
    jams: pd.DataFrame,
    alerts: pd.DataFrame,
    panel: pd.DataFrame,
    summary: pd.DataFrame,
    hourly: pd.DataFrame,
    lag: pd.DataFrame,
    correlations: pd.DataFrame,
    quality: pd.DataFrame,
    catalog: pd.DataFrame,
) -> None:
    top = summary[summary["corridor_key"].ne("unresolved")].head(15)
    active_summary = summary[summary["corridor_key"].ne("unresolved")].copy()
    top_jams = active_summary.sort_values("jam_pressure_norm", ascending=False).head(8)
    top_alerts = active_summary.sort_values("alert_pressure_norm", ascending=False).head(8)
    corr_hour = correlations[
        (correlations["analysis_level"] == "corridor_hour")
        & (correlations["x_variable"] == "alert_impact_total")
        & (correlations["y_variable"] == "jam_intensity_total")
    ].iloc[0]
    lines: list[str] = []
    lines.append("# Resultados Waze Integrado Alerts + Jams")
    lines.append("")
    lines.append("## 1. Resumen Ejecutivo")
    lines.append("")
    lines.append(
        "Se integro la senal operacional de `jams` con la senal de eventos reportados de `alerts` usando `corredor-hora` como unidad comun. "
        "El objetivo fue evaluar si los eventos reportados coinciden, anteceden o acompanian los picos de congestion."
    )
    lines.append("")
    lines.append("| Indicador | Valor |")
    lines.append("|---|---:|")
    lines.append(f"| Jams unicos | {jams['uuid'].nunique():,} |")
    lines.append(f"| Alerts unicas | {alerts['uuid'].nunique():,} |")
    lines.append(f"| Corredores integrados | {summary['corridor_key'].nunique():,} |")
    resolved_summary = summary[summary["corridor_key"].ne("unresolved")]
    lines.append(
        f"| Corredores resueltos con ambas fuentes | "
        f"{int(((resolved_summary['jam_count_total'] > 0) & (resolved_summary['alert_count_total'] > 0)).sum()):,} |"
    )
    lines.append(f"| Corredor-hora con coincidencia | {int(panel['alert_jam_same_hour_flag'].sum()):,} |")
    lines.append(f"| Jams sin alerts en la misma hora | {int(panel['jam_without_alert_flag'].sum()):,} |")
    lines.append(f"| Alerts sin jams en la misma hora | {int(panel['alert_without_jam_flag'].sum()):,} |")
    lines.append("")
    lines.append("## 2. Correlacion")
    lines.append("")
    lines.append(
        f"La correlacion corredor-hora entre `alert_impact_total` y `jam_intensity_total` fue Pearson `{corr_hour['pearson']:.4f}` "
        f"y Spearman `{corr_hour['spearman']:.4f}`. Esto debe interpretarse como asociacion exploratoria, no causalidad."
    )
    best_lag = lag.sort_values("pearson_alert_impact_vs_jam_intensity", ascending=False).iloc[0]
    lines.append("")
    lines.append(
        f"El mejor rezago exploratorio fue `{int(best_lag['lag_hours_alert_vs_jam'])}` horas "
        f"(`{best_lag['interpretation']}`), con Pearson `{best_lag['pearson_alert_impact_vs_jam_intensity']:.4f}`. "
        "En este dia, la relacion mas fuerte aparece en la misma hora, no como senal claramente anticipatoria."
    )
    lines.append("")
    lines.append("## 3. Top Corredores Integrados")
    lines.append("")
    lines.append("| Corredor | Score integrado | Jams | Alerts | Overlap horas | Cuadrante |")
    lines.append("|---|---:|---:|---:|---:|---|")
    for _, row in top.iterrows():
        lines.append(
            f"| {row['corridor_name']} | {row['integrated_corridor_pressure']:.2f} | "
            f"{int(row['jam_count_total']):,} | {int(row['alert_count_total']):,} | "
            f"{int(row['same_hour_overlap_count'])} | {row['quadrant']} |"
        )
    lines.append("")
    lines.append("## 4. Comparacion Por Fuente")
    lines.append("")
    lines.append("### Top por presion de jams")
    lines.append("")
    lines.append("| Corredor | Jam pressure | Jams | Demora total min |")
    lines.append("|---|---:|---:|---:|")
    for _, row in top_jams.iterrows():
        lines.append(
            f"| {row['corridor_name']} | {row['jam_pressure_norm']:.2f} | "
            f"{int(row['jam_count_total']):,} | {row['jam_delay_total']:.2f} |"
        )
    lines.append("")
    lines.append("### Top por presion de alerts")
    lines.append("")
    lines.append("| Corredor | Alert pressure | Alerts | Impacto alerts |")
    lines.append("|---|---:|---:|---:|")
    for _, row in top_alerts.iterrows():
        lines.append(
            f"| {row['corridor_name']} | {row['alert_pressure_norm']:.2f} | "
            f"{int(row['alert_count_total']):,} | {row['alert_impact_total']:.2f} |"
        )
    lines.append("")
    lines.append(
        "Esta comparacion es importante porque muestra si un corredor aparece critico por congestion operacional, "
        "por eventos reportados o por ambas fuentes. Esa diferencia evita confundir volumen de trafico lento con eventos viales reportados."
    )
    lines.append("")
    lines.append("## 5. Calidad De Integracion")
    lines.append("")
    lines.append("| Metrica | Valor | Descripcion |")
    lines.append("|---|---:|---|")
    for _, row in quality.iterrows():
        lines.append(f"| {row['metric']} | {row['value']} | {row['description']} |")
    lines.append("")
    lines.append("## 6. Metrica Preliminar Integrada")
    lines.append("")
    lines.append(
        "Se propone denominar la metrica exploratoria como **Presion Integrada Evento-Congestion Waze (PIEC-Waze)**. "
        "No es un KPI final; es una metrica de prueba para evaluar si la combinacion de `alerts` y `jams` aporta una senal accionable."
    )
    lines.append("")
    lines.append("La formula por corredor-hora es:")
    lines.append("")
    lines.append("```text")
    lines.append("integrated_corridor_hour_pressure =")
    lines.append("  0.45 * operational_congestion_pressure")
    lines.append("  + 0.35 * critical_alert_pressure")
    lines.append("  + 0.12 * temporal_alignment_score")
    lines.append("  + 0.08 * integrated_reliability_score")
    lines.append("```")
    lines.append("")
    lines.append(
        "La lectura es directa: a mayor score, mayor combinacion de congestion, eventos reportados, coincidencia temporal y confianza de asociacion. "
        "La metrica permite priorizar corredores, pero todavia no debe usarse como indicador institucional definitivo."
    )
    lines.append("")
    lines.append("## 7. Que Aporta La Integracion")
    lines.append("")
    lines.append(
        "`jams` aporta la dimension operacional: demora, intensidad, carga de congestion y velocidad. "
        "`alerts` aporta la dimension de eventos: accidentes, cierres, peligros, trafico detenido, vehiculos detenidos y otros reportes. "
        "La integracion permite observar si ambas dimensiones se concentran en los mismos corredores y horas."
    )
    lines.append("")
    lines.append(
        "Los corredores en el cuadrante `ALTA_CONGESTION_ALTAS_ALERTAS` son los candidatos mas fuertes para monitoreo integrado. "
        "Los corredores `ALTA_CONGESTION_BAJAS_ALERTAS` indican congestion que no esta siendo explicada por reportes de eventos. "
        "Los corredores `BAJA_CONGESTION_ALTAS_ALERTAS` pueden reflejar eventos localizados, seguridad vial o reportes sin impacto fuerte en flujo."
    )
    lines.append("")
    lines.append("## 8. Figuras Analizadas")
    lines.append("")
    for _, row in catalog.iterrows():
        lines.append(f"### {row['figure_title']}")
        lines.append("")
        lines.append(f"![{row['figure_title']}](../../{row['figure_file']})")
        lines.append("")
        lines.append(f"**Hallazgo:** {row['main_finding']}")
        lines.append("")
        lines.append(f"**Valor de decision:** {row['decision_value']}")
        lines.append("")
    lines.append("## 9. Conclusion")
    lines.append("")
    lines.append(
        "La integracion muestra que `alerts` y `jams` no son sustitutos: son senales complementarias. "
        "`jams` mide intensidad de congestion; `alerts` ayuda a explicar eventos o condiciones que pueden acompanar esa congestion. "
        "La siguiente fase deberia ampliar el periodo temporal, validar estabilidad de rankings y calibrar pesos con mas dias o con una fuente externa."
    )
    lines.append("")
    lines.append("## 10. Proximos Pasos")
    lines.append("")
    lines.append("- Ampliar el analisis a mas dias para distinguir patrones recurrentes de condiciones atipicas.")
    lines.append("- Medir sensibilidad de pesos de `PIEC-Waze` y estabilidad de top corredores.")
    lines.append("- Mejorar la normalizacion de corredores entre Waze, OSM y nomenclatura institucional.")
    lines.append("- Contrastar corredores criticos con datos externos si estan disponibles: aforos, tiempos de viaje, siniestralidad o reportes oficiales.")
    (INFORME_DIR / "resultados_waze_integrado.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    ensure_dirs()
    require_inputs()
    jams, jams_hour, jams_summary, alerts, alerts_hour, alerts_summary = load_inputs()
    crosswalk = build_key_crosswalk(jams_summary, alerts_summary)
    panel = build_corridor_hour_panel(jams, alerts, crosswalk)
    summary = build_corridor_summary(panel, crosswalk)
    hourly = build_hourly_summary(panel)
    lag = build_lag_analysis(panel)
    correlations = build_correlation_outputs(panel, summary)
    quality = build_quality_outputs(jams, alerts, panel, summary, lag, correlations)
    catalog = generate_figures(panel, summary, hourly, lag)
    catalog = enrich_figure_catalog(catalog, panel, summary, hourly, lag, correlations)
    write_figure_analysis(catalog)
    write_results_report(jams, alerts, panel, summary, hourly, lag, correlations, quality)
    write_methodology_md()
    write_results_md(jams, alerts, panel, summary, hourly, lag, correlations, quality, catalog)
    print(f"Resultados Waze integrados generados en: {RESULTS_DIR}")
    print(f"Corredores integrados: {summary['corridor_key'].nunique():,}")
    print(f"Corredor-hora con actividad: {int(((panel['jam_count'] > 0) | (panel['alert_count'] > 0)).sum()):,}")


if __name__ == "__main__":
    main()
