from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
from typing import Iterable

import imageio.v2 as imageio
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import LineCollection


ROOT = Path(__file__).resolve().parents[1]
ALERTS_PATH = ROOT / "Results" / "Waze" / "Alerts" / "waze_alerts_unique_enriched.csv"
OSM_ROADS_PATH = ROOT / "Data" / "Processed" / "osm_roads_nacional" / "osm_road_segments.csv"
RESULTS_DIR = ROOT / "Results" / "Waze" / "Alerts"
OUTPUT_GIF = RESULTS_DIR / "fig_animacion_alertas_24h_x2_15min.gif"
OUTPUT_GIF_CAPITAL = RESULTS_DIR / "fig_animacion_alertas_capital_24h_x2_15min.gif"

DATE = "2026-06-29"
TIMEZONE = "America/El_Salvador"
STEP_MINUTES = 15
TRAIL_MINUTES = 60

BBOXES = {
    "national": {
        "lon_min": -90.20,
        "lon_max": -87.65,
        "lat_min": 13.05,
        "lat_max": 14.45,
        "label": "El Salvador",
        "subtitle": "El Salvador | 2026-06-29",
        "title": "Evolucion temporal de alertas Waze | ventana actual de 15 minutos",
    },
    "capital": {
        "lon_min": -89.265,
        "lon_max": -89.155,
        "lat_min": 13.660,
        "lat_max": 13.735,
        "label": "San Salvador capital",
        "subtitle": "San Salvador capital | 2026-06-29",
        "title": "Evolucion temporal de alertas Waze | San Salvador capital",
    },
}

MAIN_HIGHWAYS = {
    "motorway",
    "motorway_link",
    "trunk",
    "trunk_link",
    "primary",
    "primary_link",
    "secondary",
    "secondary_link",
}

ALERT_COLORS = {
    "ACCIDENTE": "#ff3b30",
    "CIERRE_VIAL": "#b85cff",
    "OBRA_CARRIL_CERRADO": "#ff9f0a",
    "TRAFICO_DETENIDO": "#ff2d55",
    "TRAFICO_PESADO": "#ffd60a",
    "CONGESTION_REPORTADA": "#ff7f50",
    "PELIGRO_EN_VIA": "#64d2ff",
    "VEHICULO_DETENIDO": "#0a84ff",
    "BACHE": "#30d158",
    "OBJETO_EN_VIA": "#5e5ce6",
    "CLIMA_RIESGO": "#00c7be",
    "FALLA_SEMAFORO": "#bf5af2",
}

CITY_LABELS = [
    ("Ahuachapan", -89.845, 13.921),
    ("Santa Ana", -89.5597, 13.9942),
    ("Sonsonate", -89.7242, 13.7189),
    ("San Salvador", -89.2182, 13.6929),
    ("La Libertad", -89.3222, 13.4883),
    ("San Vicente", -88.785, 13.642),
    ("Usulutan", -88.45, 13.35),
    ("San Miguel", -88.1783, 13.4833),
]

CAPITAL_LABELS = [
    ("Centro Historico", -89.191, 13.698),
    ("Escalon", -89.242, 13.708),
    ("San Benito", -89.244, 13.690),
    ("Metrocentro", -89.219, 13.706),
    ("San Jacinto", -89.197, 13.675),
    ("Col. Medica", -89.213, 13.710),
    ("Flor Blanca", -89.224, 13.700),
]


def robust_norm(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0.0).astype(float)
    if numeric.empty:
        return numeric
    lower = float(numeric.min())
    upper = float(numeric.quantile(0.95))
    if upper <= lower:
        upper = float(numeric.max())
    if upper <= lower:
        return pd.Series(0.0, index=numeric.index)
    return ((numeric.clip(lower=lower, upper=upper) - lower) / (upper - lower)).clip(0, 1)


def in_bbox(coords: np.ndarray, bbox: dict[str, float | str]) -> bool:
    if coords.size == 0:
        return False
    lon = coords[:, 0]
    lat = coords[:, 1]
    return bool(
        (lon.max() >= bbox["lon_min"])
        and (lon.min() <= bbox["lon_max"])
        and (lat.max() >= bbox["lat_min"])
        and (lat.min() <= bbox["lat_max"])
    )


def iter_road_lines(bbox: dict[str, float | str], max_lines: int | None = None) -> Iterable[np.ndarray]:
    if not OSM_ROADS_PATH.exists():
        return

    columns = ["highway", "geometry_json", "length_m"]
    roads = pd.read_csv(OSM_ROADS_PATH, usecols=columns)
    roads = roads[roads["highway"].isin(MAIN_HIGHWAYS)].copy()
    roads["length_m"] = pd.to_numeric(roads["length_m"], errors="coerce").fillna(0.0)
    roads = roads.sort_values("length_m", ascending=False)
    if max_lines is not None:
        roads = roads.head(max_lines)

    for geometry in roads["geometry_json"].dropna():
        try:
            coords = np.array(json.loads(geometry), dtype=float)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if coords.ndim != 2 or coords.shape[0] < 2 or coords.shape[1] < 2:
            continue
        coords = coords[:, :2]
        if in_bbox(coords, bbox):
            yield coords


def load_alerts(bbox: dict[str, float | str]) -> pd.DataFrame:
    if not ALERTS_PATH.exists():
        raise FileNotFoundError(f"No existe {ALERTS_PATH}")

    usecols = [
        "uuid",
        "datetime_local",
        "event_date_local",
        "lat",
        "lon",
        "alert_group",
        "alert_type_norm",
        "alert_impact_score",
        "severity_proxy",
        "corridor_norm_alert",
    ]
    alerts = pd.read_csv(ALERTS_PATH, usecols=usecols)
    alerts = alerts[alerts["event_date_local"].astype(str).eq(DATE)].copy()
    alerts["datetime_local"] = pd.to_datetime(alerts["datetime_local"], errors="coerce", utc=True).dt.tz_convert(TIMEZONE)
    alerts["lat"] = pd.to_numeric(alerts["lat"], errors="coerce")
    alerts["lon"] = pd.to_numeric(alerts["lon"], errors="coerce")
    alerts["alert_impact_score"] = pd.to_numeric(alerts["alert_impact_score"], errors="coerce").fillna(0.0)
    alerts["severity_proxy"] = pd.to_numeric(alerts["severity_proxy"], errors="coerce").fillna(0.0)
    alerts["alert_group"] = alerts["alert_group"].fillna("SIN_CLASIFICAR").astype(str)
    alerts = alerts.dropna(subset=["datetime_local", "lat", "lon"])
    alerts = alerts[
        alerts["lon"].between(float(bbox["lon_min"]), float(bbox["lon_max"]))
        & alerts["lat"].between(float(bbox["lat_min"]), float(bbox["lat_max"]))
    ].copy()
    alerts["impact_norm"] = robust_norm(alerts["alert_impact_score"])
    alerts["point_size"] = 22 + 70 * alerts["impact_norm"]
    return alerts.sort_values("datetime_local").reset_index(drop=True)


def draw_base_map(ax: plt.Axes, road_lines: list[np.ndarray], bbox: dict[str, float | str], labels: list[tuple[str, float, float]]) -> None:
    ax.set_facecolor("#061014")
    if road_lines:
        collection = LineCollection(road_lines, colors="#4c6873", linewidths=0.35, alpha=0.42, zorder=1)
        ax.add_collection(collection)

    for name, lon, lat in labels:
        ax.scatter([lon], [lat], s=8, color="#e8f1f2", alpha=0.70, zorder=3)
        offset_lon = 0.018 if bbox["label"] == "El Salvador" else 0.002
        offset_lat = 0.012 if bbox["label"] == "El Salvador" else 0.0014
        ax.text(lon + offset_lon, lat + offset_lat, name, color="#d9e5e8", fontsize=7, alpha=0.86, zorder=3)

    ax.set_xlim(float(bbox["lon_min"]), float(bbox["lon_max"]))
    ax.set_ylim(float(bbox["lat_min"]), float(bbox["lat_max"]))
    ax.set_aspect("equal", adjustable="box")
    ax.grid(color="#20343b", linewidth=0.35, alpha=0.35)
    ax.tick_params(colors="#9fb2ba", labelsize=7)
    for spine in ax.spines.values():
        spine.set_color("#29454e")


def draw_side_panel(
    ax: plt.Axes,
    frame_start: pd.Timestamp,
    frame_end: pd.Timestamp,
    current: pd.DataFrame,
    accumulated: pd.DataFrame,
    alerts: pd.DataFrame,
    bbox: dict[str, float | str],
) -> None:
    ax.set_facecolor("#0b151a")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    total = len(alerts)
    accumulated_count = len(accumulated)
    current_count = len(current)
    progress = accumulated_count / total if total else 0
    critical_count = int(current["alert_group"].isin(["ACCIDENTE", "CIERRE_VIAL", "TRAFICO_DETENIDO"]).sum()) if current_count else 0

    top_type = "Sin alertas"
    if current_count:
        top_type = str(current["alert_group"].value_counts().idxmax()).replace("_", " ").title()

    ax.text(0.04, 0.96, "Waze Alerts", color="#f2f7f8", fontsize=16, weight="bold", transform=ax.transAxes)
    ax.text(0.04, 0.91, str(bbox["subtitle"]), color="#9fb2ba", fontsize=9, transform=ax.transAxes)
    ax.text(0.04, 0.84, frame_start.strftime("%H:%M") + " - " + frame_end.strftime("%H:%M"), color="#ffffff", fontsize=24, weight="bold", transform=ax.transAxes)
    ax.text(0.04, 0.79, "Paso: 15 min | Reproduccion: x2", color="#9fb2ba", fontsize=8.5, transform=ax.transAxes)

    stats = [
        ("Alertas intervalo", f"{current_count:,}"),
        ("Alertas acumuladas", f"{accumulated_count:,} / {total:,}"),
        ("Criticas intervalo", f"{critical_count:,}"),
        ("Tipo dominante", top_type),
    ]
    y = 0.70
    for label, value in stats:
        ax.text(0.04, y, label, color="#9fb2ba", fontsize=8, transform=ax.transAxes)
        ax.text(0.04, y - 0.045, value, color="#f2f7f8", fontsize=13, weight="bold", transform=ax.transAxes)
        y -= 0.105

    ax.text(0.04, 0.30, "Progreso del dia", color="#9fb2ba", fontsize=8, transform=ax.transAxes)
    ax.add_patch(plt.Rectangle((0.04, 0.265), 0.82, 0.025, color="#26383f", transform=ax.transAxes, clip_on=False))
    ax.add_patch(plt.Rectangle((0.04, 0.265), 0.82 * progress, 0.025, color="#64d2ff", transform=ax.transAxes, clip_on=False))

    legend_items = [
        ("Accidente", ALERT_COLORS["ACCIDENTE"]),
        ("Obra/carril", ALERT_COLORS["OBRA_CARRIL_CERRADO"]),
        ("Trafico pesado", ALERT_COLORS["TRAFICO_PESADO"]),
        ("Trafico detenido", ALERT_COLORS["TRAFICO_DETENIDO"]),
        ("Peligro/vehiculo", ALERT_COLORS["PELIGRO_EN_VIA"]),
    ]
    ax.text(0.04, 0.235, "Colores principales", color="#9fb2ba", fontsize=8, transform=ax.transAxes)
    y = 0.200
    for label, color in legend_items:
        ax.scatter([0.06], [y], s=45, color=color, transform=ax.transAxes)
        ax.text(0.12, y - 0.012, label, color="#d9e5e8", fontsize=8, transform=ax.transAxes)
        y -= 0.037

    ax.text(
        0.04,
        0.008,
        "Puntos tenues: acumulado del dia\nPuntos destacados: intervalo actual",
        color="#718992",
        fontsize=6.4,
        transform=ax.transAxes,
    )


def draw_frame(
    alerts: pd.DataFrame,
    road_lines: list[np.ndarray],
    frame_start: pd.Timestamp,
    frame_end: pd.Timestamp,
    bbox: dict[str, float | str],
    labels: list[tuple[str, float, float]],
) -> np.ndarray:
    current = alerts[(alerts["datetime_local"] >= frame_start) & (alerts["datetime_local"] < frame_end)]
    accumulated = alerts[alerts["datetime_local"] < frame_end]
    trail_start = frame_end - pd.Timedelta(minutes=TRAIL_MINUTES)
    trail = alerts[(alerts["datetime_local"] >= trail_start) & (alerts["datetime_local"] < frame_end)]

    fig = plt.figure(figsize=(12, 7), dpi=110, facecolor="#061014")
    grid = fig.add_gridspec(1, 2, width_ratios=[4.8, 1.35], wspace=0.035)
    ax_map = fig.add_subplot(grid[0, 0])
    ax_side = fig.add_subplot(grid[0, 1])

    draw_base_map(ax_map, road_lines, bbox, labels)

    if not accumulated.empty:
        ax_map.scatter(
            accumulated["lon"],
            accumulated["lat"],
            s=7,
            color="#b8c7cc",
            alpha=0.16,
            linewidths=0,
            zorder=4,
        )

    if not trail.empty:
        ax_map.scatter(
            trail["lon"],
            trail["lat"],
            s=18,
            facecolors="none",
            edgecolors="#64d2ff",
            alpha=0.18,
            linewidths=0.8,
            zorder=5,
        )

    if not current.empty:
        for group, group_df in current.groupby("alert_group"):
            color = ALERT_COLORS.get(group, "#ffffff")
            ax_map.scatter(
                group_df["lon"],
                group_df["lat"],
                s=group_df["point_size"],
                color=color,
                edgecolors="#061014",
                linewidths=0.35,
                alpha=0.92,
                zorder=6,
            )

    ax_map.set_title(
        str(bbox["title"]),
        color="#f2f7f8",
        fontsize=13,
        weight="bold",
        pad=10,
    )
    ax_map.set_xlabel("Longitud", color="#9fb2ba", fontsize=8)
    ax_map.set_ylabel("Latitud", color="#9fb2ba", fontsize=8)

    draw_side_panel(ax_side, frame_start, frame_end, current, accumulated, alerts, bbox)

    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight", pad_inches=0.08)
    plt.close(fig)
    buffer.seek(0)
    return imageio.imread(buffer)


def build_animation(output_path: Path, fps_multiplier: float, max_road_lines: int | None, scope: str) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bbox = BBOXES[scope]
    labels = CAPITAL_LABELS if scope == "capital" else CITY_LABELS
    alerts = load_alerts(bbox)
    if alerts.empty:
        raise ValueError("No hay alertas validas para construir la animacion.")

    road_lines = list(iter_road_lines(bbox, max_lines=max_road_lines))
    base_time = pd.Timestamp(DATE + " 00:00:00", tz=TIMEZONE)
    frame_starts = [base_time + pd.Timedelta(minutes=STEP_MINUTES * i) for i in range(int(24 * 60 / STEP_MINUTES))]
    frame_duration_ms = int(round(max(40.0, 160.0 / fps_multiplier)))

    with imageio.get_writer(output_path, mode="I", duration=frame_duration_ms, loop=0) as writer:
        for frame_start in frame_starts:
            frame_end = frame_start + pd.Timedelta(minutes=STEP_MINUTES)
            writer.append_data(draw_frame(alerts, road_lines, frame_start, frame_end, bbox, labels))

    metadata_path = output_path.with_suffix(".txt")
    metadata_path.write_text(
        "\n".join(
            [
                "Animacion Waze Alerts",
                f"scope={scope}",
                f"scope_label={bbox['label']}",
                f"fecha={DATE}",
                f"zona_horaria={TIMEZONE}",
                f"paso_minutos={STEP_MINUTES}",
                f"frames={len(frame_starts)}",
                f"alertas_usadas={len(alerts)}",
                f"bbox_lon_min={bbox['lon_min']}",
                f"bbox_lon_max={bbox['lon_max']}",
                f"bbox_lat_min={bbox['lat_min']}",
                f"bbox_lat_max={bbox['lat_max']}",
                f"reproduccion_x={fps_multiplier}",
                f"duracion_frame_ms={frame_duration_ms}",
                f"red_vial_contexto_segmentos={len(road_lines)}",
                f"salida={output_path}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Genera GIF temporal de alertas Waze para El Salvador.")
    parser.add_argument("--scope", choices=sorted(BBOXES), default="national", help="Alcance espacial de la animacion.")
    parser.add_argument("--output", type=Path, default=None, help="Ruta del GIF de salida.")
    parser.add_argument("--speed", type=float, default=2.0, help="Multiplicador de velocidad visual.")
    parser.add_argument("--max-road-lines", type=int, default=6500, help="Maximo de segmentos OSM usados como base.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = args.output
    if output is None:
        output = OUTPUT_GIF_CAPITAL if args.scope == "capital" else OUTPUT_GIF
    build_animation(output, fps_multiplier=args.speed, max_road_lines=args.max_road_lines, scope=args.scope)
    print(f"GIF generado: {output}")


if __name__ == "__main__":
    main()
