#!/usr/bin/env python3
"""
Grafica la red vial OSM procesada para el area capitalina.

Salidas:
- Mapa base vial oscuro.
- Mapa base vial con corredores extraidos de noticias resaltados.

No usa mapa base externo: solo la geometria OSM descargada con Overpass.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Iterable

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D


ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = ROOT / "Data" / "Processed" / "osm_roads_san_salvador"
RESULTS_DIR = ROOT / "Results" / "News"

SEGMENTS_PATH = PROCESSED_DIR / "osm_road_segments.csv"
MATCHES_PATH = RESULTS_DIR / "road_text_matches.csv"

BASE_OUTPUT = RESULTS_DIR / "osm_base_vial_amss_dark.png"
HIGHLIGHT_OUTPUT = RESULTS_DIR / "osm_base_vial_amss_dark_highlight_news.png"
SUMMARY_OUTPUT = RESULTS_DIR / "osm_base_vial_map_summary.txt"

BACKGROUND = "#05080d"

ROAD_STYLE = {
    "motorway": {"color": "#5ad7ff", "lw": 1.15, "alpha": 0.92, "z": 8},
    "trunk": {"color": "#58d2ff", "lw": 1.05, "alpha": 0.9, "z": 8},
    "primary": {"color": "#80e0ff", "lw": 0.9, "alpha": 0.85, "z": 7},
    "secondary": {"color": "#b6e68a", "lw": 0.65, "alpha": 0.7, "z": 6},
    "tertiary": {"color": "#6dd0b6", "lw": 0.42, "alpha": 0.52, "z": 5},
    "unclassified": {"color": "#70879a", "lw": 0.28, "alpha": 0.35, "z": 4},
    "residential": {"color": "#4a6f91", "lw": 0.22, "alpha": 0.26, "z": 3},
    "living_street": {"color": "#405f7b", "lw": 0.18, "alpha": 0.22, "z": 2},
    "service": {"color": "#33475e", "lw": 0.14, "alpha": 0.18, "z": 1},
    "motorway_link": {"color": "#5ad7ff", "lw": 0.75, "alpha": 0.8, "z": 7},
    "trunk_link": {"color": "#58d2ff", "lw": 0.75, "alpha": 0.8, "z": 7},
    "primary_link": {"color": "#80e0ff", "lw": 0.6, "alpha": 0.72, "z": 6},
    "secondary_link": {"color": "#b6e68a", "lw": 0.45, "alpha": 0.6, "z": 5},
    "tertiary_link": {"color": "#6dd0b6", "lw": 0.35, "alpha": 0.5, "z": 4},
}

HIGHLIGHT_COLOR = "#ffcf5a"
REVIEW_COLOR = "#ff7b72"


def web_mercator(lon: float, lat: float) -> tuple[float, float]:
    radius = 6_378_137.0
    x = radius * math.radians(lon)
    y = radius * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x, y


def parse_geometry(value: str) -> list[tuple[float, float]]:
    coords = json.loads(value)
    return [web_mercator(float(lon), float(lat)) for lon, lat in coords]


def load_segments() -> pd.DataFrame:
    if not SEGMENTS_PATH.exists():
        raise FileNotFoundError(f"No existe {SEGMENTS_PATH}. Ejecuta primero osm_overpass_road_match.py")

    segments = pd.read_csv(SEGMENTS_PATH)
    segments["projected_geometry"] = segments["geometry_json"].map(parse_geometry)
    return segments


def setup_axis(width: float = 14, height: float = 14) -> tuple[plt.Figure, plt.Axes]:
    fig, ax = plt.subplots(figsize=(width, height), dpi=260)
    fig.patch.set_facecolor(BACKGROUND)
    ax.set_facecolor(BACKGROUND)
    ax.set_aspect("equal")
    ax.axis("off")
    return fig, ax


def apply_bounds(ax: plt.Axes, segments: pd.DataFrame) -> None:
    xs: list[float] = []
    ys: list[float] = []
    for coords in segments["projected_geometry"]:
        for x, y in coords:
            xs.append(x)
            ys.append(y)

    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)
    pad_x = (x_max - x_min) * 0.035
    pad_y = (y_max - y_min) * 0.035
    ax.set_xlim(x_min - pad_x, x_max + pad_x)
    ax.set_ylim(y_min - pad_y, y_max + pad_y)


def draw_segments(ax: plt.Axes, segments: pd.DataFrame) -> None:
    # De menor a mayor jerarquia para que las vias principales queden encima.
    ordered = segments.sort_values("length_m")
    for _, row in ordered.iterrows():
        style = ROAD_STYLE.get(
            row["highway"],
            {"color": "#607184", "lw": 0.2, "alpha": 0.25, "z": 2},
        )
        coords = row["projected_geometry"]
        if len(coords) < 2:
            continue
        xs, ys = zip(*coords)
        ax.plot(
            xs,
            ys,
            color=style["color"],
            linewidth=style["lw"],
            alpha=style["alpha"],
            solid_capstyle="round",
            zorder=style["z"],
        )


def draw_highlighted_roads(ax: plt.Axes, segments: pd.DataFrame, matches: pd.DataFrame) -> None:
    accepted = set(
        matches.loc[matches["match_status"] == "TEXT_MATCH_ACCEPTED", "matched_road_key_norm"]
        .dropna()
        .astype(str)
    )
    review = set(
        matches.loc[matches["match_status"].str.contains("REVIEW", na=False), "matched_road_key_norm"]
        .dropna()
        .astype(str)
    )

    highlight_keys = accepted | review
    selected = segments[segments["road_key_norm"].isin(highlight_keys)].copy()
    if selected.empty:
        return

    # Halo oscuro para separar los corredores de la red base.
    for _, row in selected.iterrows():
        coords = row["projected_geometry"]
        xs, ys = zip(*coords)
        ax.plot(xs, ys, color="#000000", linewidth=2.5, alpha=0.45, solid_capstyle="round", zorder=20)

    for _, row in selected.iterrows():
        coords = row["projected_geometry"]
        xs, ys = zip(*coords)
        color = HIGHLIGHT_COLOR if row["road_key_norm"] in accepted else REVIEW_COLOR
        width = 1.35 if row["road_key_norm"] in accepted else 1.05
        ax.plot(xs, ys, color=color, linewidth=width, alpha=0.9, solid_capstyle="round", zorder=21)

    label_matches = matches[matches["match_status"].isin(["TEXT_MATCH_ACCEPTED", "TEXT_MATCH_REVIEW"])].copy()
    label_matches = label_matches.sort_values(["news_events", "text_match_score"], ascending=False).head(12)
    add_corridor_labels(ax, segments, label_matches)


def midpoint(coords: Iterable[tuple[float, float]]) -> tuple[float, float]:
    points = list(coords)
    return points[len(points) // 2]


def add_corridor_labels(ax: plt.Axes, segments: pd.DataFrame, matches: pd.DataFrame) -> None:
    for _, match in matches.iterrows():
        road_key = str(match.get("matched_road_key_norm", ""))
        road_segments = segments[segments["road_key_norm"] == road_key]
        if road_segments.empty:
            continue
        longest = road_segments.sort_values("length_m", ascending=False).iloc[0]
        x, y = midpoint(longest["projected_geometry"])
        label = str(match.get("road_name_candidate", "")).title()
        ax.text(
            x,
            y,
            label,
            color="#e8f6ff",
            fontsize=5.5,
            ha="center",
            va="center",
            zorder=30,
            bbox={
                "boxstyle": "round,pad=0.18",
                "facecolor": "#07111c",
                "edgecolor": "#24425b",
                "linewidth": 0.25,
                "alpha": 0.82,
            },
        )


def add_small_caption(ax: plt.Axes, title: str, subtitle: str) -> None:
    ax.text(
        0.012,
        0.985,
        title,
        transform=ax.transAxes,
        color="#eaf8ff",
        fontsize=10,
        fontweight="bold",
        ha="left",
        va="top",
    )
    ax.text(
        0.012,
        0.965,
        subtitle,
        transform=ax.transAxes,
        color="#9db5c9",
        fontsize=6.5,
        ha="left",
        va="top",
    )


def add_legend(ax: plt.Axes) -> None:
    legend_items = [
        Line2D([0], [0], color="#58d2ff", lw=1.6, label="Trunk / estructurante"),
        Line2D([0], [0], color="#80e0ff", lw=1.3, label="Primary"),
        Line2D([0], [0], color="#b6e68a", lw=1.0, label="Secondary"),
        Line2D([0], [0], color="#6dd0b6", lw=0.8, label="Tertiary"),
        Line2D([0], [0], color="#4a6f91", lw=0.7, label="Residential / local"),
    ]
    legend = ax.legend(
        handles=legend_items,
        loc="lower left",
        frameon=True,
        facecolor="#07111c",
        edgecolor="#24425b",
        fontsize=6,
        labelcolor="#d8e8f5",
    )
    legend.get_frame().set_alpha(0.82)


def save_base_map(segments: pd.DataFrame) -> None:
    fig, ax = setup_axis()
    draw_segments(ax, segments)
    apply_bounds(ax, segments)
    add_small_caption(
        ax,
        "Base vial OSM - AMSS / San Salvador",
        "Geometria OSM descargada via Overpass. Color y grosor segun highway.",
    )
    add_legend(ax)
    fig.savefig(BASE_OUTPUT, facecolor=BACKGROUND, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)


def save_highlight_map(segments: pd.DataFrame, matches: pd.DataFrame) -> None:
    fig, ax = setup_axis()
    draw_segments(ax, segments)
    draw_highlighted_roads(ax, segments, matches)
    apply_bounds(ax, segments)
    add_small_caption(
        ax,
        "Base vial OSM + corredores mencionados en noticias",
        "Amarillo: match textual aceptado. Rojo: requiere revision.",
    )
    fig.savefig(HIGHLIGHT_OUTPUT, facecolor=BACKGROUND, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)


def write_summary(segments: pd.DataFrame, matches: pd.DataFrame) -> None:
    highway_counts = segments["highway"].value_counts()
    accepted = int((matches["match_status"] == "TEXT_MATCH_ACCEPTED").sum())
    review = int(matches["match_status"].str.contains("REVIEW", na=False).sum())
    lines = [
        "MAPA BASE VIAL OSM",
        "=" * 19,
        "",
        f"Segmentos graficados: {len(segments)}",
        f"Corredores noticia-OSM aceptados resaltables: {accepted}",
        f"Corredores noticia-OSM en revision resaltables: {review}",
        "",
        "Distribucion por highway:",
    ]
    for highway, count in highway_counts.items():
        lines.append(f"- {highway}: {count}")
    lines.extend(
        [
            "",
            f"Mapa base: {BASE_OUTPUT}",
            f"Mapa con corredores de noticias: {HIGHLIGHT_OUTPUT}",
            "",
            "Nota: esta visualizacion no valida por si sola la ubicacion exacta de cada evento.",
            "Sirve para inspeccionar la red OSM, la jerarquia vial y los corredores candidatos para una siguiente fase de geocodificacion/map matching.",
        ]
    )
    SUMMARY_OUTPUT.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    segments = load_segments()
    matches = pd.read_csv(MATCHES_PATH) if MATCHES_PATH.exists() else pd.DataFrame()

    save_base_map(segments)
    if not matches.empty:
        save_highlight_map(segments, matches)
    write_summary(segments, matches)

    print(f"Mapa base: {BASE_OUTPUT}")
    if HIGHLIGHT_OUTPUT.exists():
        print(f"Mapa con corredores: {HIGHLIGHT_OUTPUT}")
    print(f"Resumen: {SUMMARY_OUTPUT}")


if __name__ == "__main__":
    main()
