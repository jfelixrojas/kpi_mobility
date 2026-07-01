#!/usr/bin/env python3
"""
Genera figuras ejecutivas para el analisis de incidentes.csv.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "Results" / "News" / "Incidentes"
OSM_NATIONAL_SEGMENTS = ROOT / "Data" / "Processed" / "osm_roads_nacional" / "osm_road_segments.csv"

EVENTS = RESULTS_DIR / "eventos_incidentes_osm_nacional_enriched.csv"
DEPARTMENTS = RESULTS_DIR / "ranking_departamentos_incidentes.csv"
DAILY = RESULTS_DIR / "serie_temporal_eventos_incidentes.csv"
COORDS = RESULTS_DIR / "diagnostico_coordenadas_incidentes.csv"
CORRIDORS = RESULTS_DIR / "analisis_corredores_criticos.csv"
SENSITIVITY = RESULTS_DIR / "sensibilidad_pesos_corredores.csv"

SAN_SALVADOR_VIEW = {
    "west": -89.36,
    "east": -89.05,
    "south": 13.58,
    "north": 13.83,
}


COLORS = {
    "blue": "#2563eb",
    "sky": "#38bdf8",
    "green": "#16a34a",
    "amber": "#f59e0b",
    "red": "#dc2626",
    "slate": "#334155",
    "muted": "#94a3b8",
    "light": "#e2e8f0",
    "bg": "#f8fafc",
    "text": "#0f172a",
}


def save(fig: plt.Figure, name: str) -> Path:
    path = RESULTS_DIR / name
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def short_label(value: str, limit: int = 26) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "."


def in_view(lon: float, lat: float, view: dict[str, float], margin: float = 0.0) -> bool:
    return (
        view["west"] - margin <= lon <= view["east"] + margin
        and view["south"] - margin <= lat <= view["north"] + margin
    )


def coords_intersect_view(coords: list[list[float]], view: dict[str, float], margin: float = 0.01) -> bool:
    return any(in_view(float(lon), float(lat), view, margin) for lon, lat in coords)


def executive_dashboard() -> Path:
    events = pd.read_csv(EVENTS)
    departments = pd.read_csv(DEPARTMENTS)
    daily = pd.read_csv(DAILY)
    coords = pd.read_csv(COORDS)

    total_events = len(events)
    total_mentions = int(events["mentions"].sum())
    valid_points = int(events["coordinate_inside_sv_bbox"].astype(bool).sum())
    osm_high_medium = int(events["osm_match_status"].isin(["SPATIAL_OSM_HIGH", "SPATIAL_OSM_MEDIUM"]).sum())
    corridors = int(events["corridor_norm"].fillna("").astype(str).str.strip().ne("").sum())
    impact = float(events["impact_social_score"].sum())

    fig = plt.figure(figsize=(15, 9))
    fig.suptitle("Resumen ejecutivo - incidentes viales desde noticias", fontsize=18, fontweight="bold", color=COLORS["text"], y=0.98)
    grid = fig.add_gridspec(3, 4, height_ratios=[0.85, 1.35, 1.35], hspace=0.55, wspace=0.35)

    cards = [
        ("Eventos", f"{total_events}", "eventos deduplicados"),
        ("Menciones", f"{total_mentions}", "publicaciones asociadas"),
        ("Puntos validos", f"{valid_points}", f"{valid_points / total_events:.0%} dentro de SV"),
        ("Match OSM", f"{osm_high_medium}", f"{osm_high_medium / total_events:.0%} alto/medio"),
        ("Con corredor", f"{corridors}", "eventos con corredor norm."),
        ("Impacto social", f"{impact:,.0f}", "score ponderado"),
    ]
    for idx, (title, value, note) in enumerate(cards):
        ax = fig.add_subplot(grid[0, idx % 4] if idx < 4 else grid[1, idx - 4])
        ax.set_axis_off()
        ax.add_patch(plt.Rectangle((0, 0), 1, 1, transform=ax.transAxes, color=COLORS["bg"], ec=COLORS["light"], lw=1.2))
        ax.text(0.06, 0.70, title, fontsize=11, color=COLORS["slate"], transform=ax.transAxes)
        ax.text(0.06, 0.35, value, fontsize=24, fontweight="bold", color=COLORS["text"], transform=ax.transAxes)
        ax.text(0.06, 0.12, note, fontsize=9, color=COLORS["muted"], transform=ax.transAxes)

    ax_dep = fig.add_subplot(grid[1, 2:])
    dep_top = departments.head(8).iloc[::-1]
    ax_dep.barh(dep_top["department_norm"], dep_top["events"], color=COLORS["blue"])
    ax_dep.set_title("Eventos por departamento", loc="left", fontsize=12, fontweight="bold")
    ax_dep.set_xlabel("eventos")
    ax_dep.grid(axis="x", alpha=0.25)

    ax_coord = fig.add_subplot(grid[2, :2])
    coord_order = coords.sort_values("events", ascending=True)
    ax_coord.barh(coord_order["coordinate_quality_status"], coord_order["events"], color=[COLORS["green"], COLORS["amber"], COLORS["red"], COLORS["muted"]][: len(coord_order)])
    ax_coord.set_title("Calidad geografica", loc="left", fontsize=12, fontweight="bold")
    ax_coord.set_xlabel("eventos")
    ax_coord.grid(axis="x", alpha=0.25)

    ax_daily = fig.add_subplot(grid[2, 2:])
    daily["event_date"] = pd.to_datetime(daily["event_date"])
    ax_daily.plot(daily["event_date"], daily["events"], marker="o", color=COLORS["blue"], lw=2.2, label="eventos")
    ax_daily.plot(daily["event_date"], daily["mentions"], marker="o", color=COLORS["amber"], lw=2.2, label="menciones")
    ax_daily.set_title("Evolucion diaria observada", loc="left", fontsize=12, fontweight="bold")
    ax_daily.grid(alpha=0.25)
    ax_daily.legend(frameon=False)
    ax_daily.tick_params(axis="x", rotation=25)

    return save(fig, "fig_resumen_ejecutivo_incidentes.png")


def corridor_sensitivity() -> Path:
    corridors = pd.read_csv(CORRIDORS).head(12)
    sensitivity = pd.read_csv(SENSITIVITY).head(12)

    fig, axes = plt.subplots(1, 2, figsize=(15, 7), gridspec_kw={"width_ratios": [1.15, 1]})
    fig.suptitle("Corredores criticos y robustez metodologica", fontsize=17, fontweight="bold", color=COLORS["text"])

    left = corridors.iloc[::-1]
    colors = [COLORS["blue"] if v >= 20 else COLORS["sky"] for v in left["corridor_criticality_score"]]
    axes[0].barh([short_label(v, 34) for v in left["corridor_norm"]], left["corridor_criticality_score"], color=colors)
    axes[0].set_title("Score exploratorio de criticidad", loc="left", fontsize=12, fontweight="bold")
    axes[0].set_xlabel("score 0-100")
    axes[0].grid(axis="x", alpha=0.25)

    right = sensitivity.iloc[::-1]
    class_colors = {
        "ROBUSTO": COLORS["green"],
        "DEPENDIENTE_DEL_ENFOQUE": COLORS["amber"],
        "INTERMEDIO": COLORS["sky"],
        "NO_PRIORITARIO": COLORS["muted"],
    }
    axes[1].barh(
        [short_label(v, 34) for v in right["corridor"]],
        right["frecuencia_top_5"],
        color=[class_colors.get(v, COLORS["muted"]) for v in right["clasificacion_robustez"]],
    )
    axes[1].set_title("Frecuencia en top 5 bajo 4 escenarios", loc="left", fontsize=12, fontweight="bold")
    axes[1].set_xlabel("escenarios en top 5")
    axes[1].set_xlim(0, 4.2)
    axes[1].grid(axis="x", alpha=0.25)

    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)

    return save(fig, "fig_corredores_sensibilidad_incidentes.png")


def incident_map() -> Path:
    events = pd.read_csv(EVENTS)
    points = events[events["coordinate_inside_sv_bbox"].astype(str).str.lower().isin(["true", "1"])].copy()
    points["longitude_num"] = pd.to_numeric(points["longitude_num"], errors="coerce")
    points["latitude_num"] = pd.to_numeric(points["latitude_num"], errors="coerce")
    points = points.dropna(subset=["longitude_num", "latitude_num"])
    view_points = points[
        points.apply(lambda row: in_view(float(row["longitude_num"]), float(row["latitude_num"]), SAN_SALVADOR_VIEW), axis=1)
    ].copy()

    fig, ax = plt.subplots(figsize=(11, 9))
    ax.set_title("Zoom vial San Salvador / AMSS con incidentes georreferenciados", fontsize=15, fontweight="bold", color=COLORS["text"])
    ax.set_facecolor("#020617")

    if OSM_NATIONAL_SEGMENTS.exists():
        major = {"motorway", "trunk", "primary", "secondary", "motorway_link", "trunk_link", "primary_link", "secondary_link"}
        roads = pd.read_csv(OSM_NATIONAL_SEGMENTS, usecols=["highway", "geometry_json"], low_memory=False)
        roads = roads[roads["highway"].isin(major)]
        for _, row in roads.iterrows():
            try:
                coords = json.loads(row["geometry_json"])
            except Exception:
                continue
            if not coords or not coords_intersect_view(coords, SAN_SALVADOR_VIEW):
                continue
            xs = [pt[0] for pt in coords]
            ys = [pt[1] for pt in coords]
            color = "#67e8f9" if row["highway"] in {"motorway", "trunk", "primary"} else "#64748b"
            lw = 0.85 if row["highway"] in {"motorway", "trunk", "primary"} else 0.45
            ax.plot(xs, ys, color=color, alpha=0.36, linewidth=lw, zorder=1)

    sev_colors = {
        "FATALITY_REPORTED": COLORS["red"],
        "INJURY_REPORTED": COLORS["amber"],
        "MATERIAL_DAMAGE_ONLY": COLORS["sky"],
        "TRAFFIC_ACCIDENT_UNSPECIFIED": COLORS["blue"],
        "ROAD_AFFECTATION": COLORS["green"],
        "OTHER_LOW_INFORMATION": COLORS["muted"],
    }
    sizes = (pd.to_numeric(view_points["impact_social_score"], errors="coerce").fillna(0).clip(lower=0).pow(0.5) * 18 + 22).clip(22, 210)
    ax.scatter(
        view_points["longitude_num"],
        view_points["latitude_num"],
        s=sizes,
        c=view_points["severity_class"].map(lambda v: sev_colors.get(str(v), COLORS["muted"])),
        alpha=0.78,
        edgecolor="white",
        linewidth=0.35,
        zorder=3,
    )

    place_labels = [
        ("San Salvador", -89.191, 13.692),
        ("Santa Tecla", -89.289, 13.674),
        ("Antiguo Cuscatlan", -89.240, 13.676),
        ("Mejicanos", -89.214, 13.724),
        ("Cuscatancingo", -89.181, 13.728),
        ("Soyapango", -89.151, 13.710),
        ("Ilopango", -89.109, 13.695),
        ("San Marcos", -89.183, 13.659),
        ("Apopa", -89.179, 13.807),
        ("Nejapa", -89.272, 13.815),
    ]
    for label, lon, lat in place_labels:
        if not in_view(lon, lat, SAN_SALVADOR_VIEW):
            continue
        ax.text(
            lon,
            lat,
            label,
            color="#e2e8f0",
            fontsize=8.5,
            ha="center",
            va="center",
            zorder=4,
            bbox={
                "facecolor": "#0f172a",
                "edgecolor": "none",
                "alpha": 0.62,
                "boxstyle": "round,pad=0.18",
            },
        )

    ax.text(
        0.02,
        0.97,
        f"Eventos visibles: {len(view_points)} de {len(points)} con coordenada valida",
        transform=ax.transAxes,
        color="#cbd5e1",
        fontsize=10,
        va="top",
        ha="left",
        bbox={"facecolor": "#0f172a", "edgecolor": "#334155", "alpha": 0.75, "boxstyle": "round,pad=0.35"},
    )

    ax.set_xlim(SAN_SALVADOR_VIEW["west"], SAN_SALVADOR_VIEW["east"])
    ax.set_ylim(SAN_SALVADOR_VIEW["south"], SAN_SALVADOR_VIEW["north"])
    ax.set_xlabel("longitud")
    ax.set_ylabel("latitud")
    ax.grid(color="white", alpha=0.08)
    ax.tick_params(colors="#cbd5e1")
    ax.xaxis.label.set_color("#cbd5e1")
    ax.yaxis.label.set_color("#cbd5e1")

    handles = [
        plt.Line2D([0], [0], marker="o", color="w", label="fallecido", markerfacecolor=COLORS["red"], markersize=8),
        plt.Line2D([0], [0], marker="o", color="w", label="lesionado", markerfacecolor=COLORS["amber"], markersize=8),
        plt.Line2D([0], [0], marker="o", color="w", label="accidente/otro", markerfacecolor=COLORS["blue"], markersize=8),
    ]
    leg = ax.legend(handles=handles, loc="lower left", frameon=True, facecolor="#0f172a", edgecolor="#334155")
    for text in leg.get_texts():
        text.set_color("white")

    return save(fig, "fig_mapa_ejecutivo_incidentes.png")


def main() -> None:
    paths = [executive_dashboard(), corridor_sensitivity(), incident_map()]
    for path in paths:
        print(path)


if __name__ == "__main__":
    main()
