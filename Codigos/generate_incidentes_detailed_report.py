#!/usr/bin/env python3
"""
Genera un informe detallado en Markdown para el analisis de incidentes.csv.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "Results" / "News" / "Incidentes"
OUTPUT = RESULTS_DIR / "informe_detallado_incidentes.md"


PATHS = {
    "events": RESULTS_DIR / "eventos_incidentes_osm_nacional_enriched.csv",
    "mentions": RESULTS_DIR / "base_menciones_incidentes_expandida.csv",
    "snapshots": RESULTS_DIR / "base_engagement_snapshots.csv",
    "integrity": RESULTS_DIR / "diagnostico_integridad_incidentes.csv",
    "coordinates": RESULTS_DIR / "diagnostico_coordenadas_incidentes.csv",
    "departments": RESULTS_DIR / "ranking_departamentos_incidentes.csv",
    "municipalities": RESULTS_DIR / "ranking_municipios_incidentes.csv",
    "corridors_norm": RESULTS_DIR / "ranking_corredores_norm.csv",
    "critical_corridors": RESULTS_DIR / "analisis_corredores_criticos.csv",
    "daily": RESULTS_DIR / "serie_temporal_eventos_incidentes.csv",
    "hourly": RESULTS_DIR / "serie_horaria_eventos_incidentes.csv",
    "engagement_source": RESULTS_DIR / "resumen_engagement_por_fuente_incidentes.csv",
    "osm_type": RESULTS_DIR / "ranking_tipo_via_osm_nacional.csv",
    "osm_coverage": RESULTS_DIR / "diagnostico_cobertura_osm_departamental.csv",
    "resolution": RESULTS_DIR / "corridor_norm_resolution.csv",
    "conflicts": RESULTS_DIR / "revision_conflictos_texto_osm_nacional.csv",
    "sensitivity": RESULTS_DIR / "sensibilidad_pesos_corredores.csv",
    "experiments": RESULTS_DIR / "experimentos_pesos_corredores.csv",
}


def read_csv(key: str) -> pd.DataFrame:
    path = PATHS[key]
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def number(value: float | int, decimals: int = 2) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float) and not value.is_integer():
        return f"{value:,.{decimals}f}"
    return f"{int(value):,}"


def pct(num: float, den: float) -> str:
    if not den:
        return "0.00%"
    return f"{100 * num / den:.2f}%"


def table(df: pd.DataFrame, cols: list[str] | None = None, max_rows: int = 12) -> str:
    if df.empty:
        return "_Sin datos disponibles._"
    frame = df.copy()
    if cols:
        frame = frame[[col for col in cols if col in frame.columns]]
    frame = frame.head(max_rows).fillna("")
    try:
        return frame.to_markdown(index=False)
    except Exception:
        headers = list(frame.columns)
        rows = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
        for _, row in frame.iterrows():
            rows.append("| " + " | ".join(str(row[col]) for col in headers) + " |")
        return "\n".join(rows)


def value_counts_table(series: pd.Series, name: str, max_rows: int = 20) -> pd.DataFrame:
    if series.empty:
        return pd.DataFrame(columns=[name, "events"])
    return series.value_counts(dropna=False).reset_index().rename(columns={"index": name, series.name or "count": "events"}).head(max_rows)


def bool_sum(series: pd.Series) -> int:
    return int(series.astype(str).str.lower().isin(["true", "1", "yes"]).sum())


def build_report() -> str:
    events = read_csv("events")
    mentions = read_csv("mentions")
    snapshots = read_csv("snapshots")
    integrity = read_csv("integrity")
    coordinates = read_csv("coordinates")
    departments = read_csv("departments")
    municipalities = read_csv("municipalities")
    corridors_norm = read_csv("corridors_norm")
    critical_corridors = read_csv("critical_corridors")
    daily = read_csv("daily")
    hourly = read_csv("hourly")
    engagement_source = read_csv("engagement_source")
    osm_type = read_csv("osm_type")
    osm_coverage = read_csv("osm_coverage")
    resolution = read_csv("resolution")
    conflicts = read_csv("conflicts")
    sensitivity = read_csv("sensitivity")

    if events.empty:
        raise FileNotFoundError("No existe eventos_incidentes_osm_nacional_enriched.csv. Ejecuta make run-incidentes-analysis.")

    total_events = len(events)
    total_mentions = len(mentions)
    total_snapshots = len(snapshots)
    period_min = events["datetime"].min()
    period_max = events["datetime"].max()
    valid_points = bool_sum(events["coordinate_inside_sv_bbox"])
    coordinate_pairs = bool_sum(events["coordinate_pair_present"])
    repeated = bool_sum(events["repeated_coordinate_flag"])
    missing = int((events["coordinate_quality_status"] == "MISSING_POINT").sum())
    outside = int((events["coordinate_quality_status"] == "OUTSIDE_EL_SALVADOR_BBOX").sum())
    osm_high_medium = int(events["osm_match_status"].isin(["SPATIAL_OSM_HIGH", "SPATIAL_OSM_MEDIUM"]).sum())
    corridor_events = int(events["corridor_norm"].fillna("").astype(str).str.strip().ne("").sum())
    corridors_distinct = int(events["corridor_norm"].fillna("").astype(str).str.strip().replace("", pd.NA).dropna().nunique())
    impact_total = float(pd.to_numeric(events["impact_social_score"], errors="coerce").fillna(0).sum())
    views_total = float(pd.to_numeric(events["latest_views"], errors="coerce").fillna(0).sum())
    likes_total = float(pd.to_numeric(events["latest_likes"], errors="coerce").fillna(0).sum())
    shares_total = float(pd.to_numeric(events["latest_shares"], errors="coerce").fillna(0).sum())
    comments_total = float(pd.to_numeric(events["latest_comments"], errors="coerce").fillna(0).sum())
    fatality = int(pd.to_numeric(events.get("fatality_flag", 0), errors="coerce").fillna(0).sum())
    injury = int(pd.to_numeric(events.get("injury_flag", 0), errors="coerce").fillna(0).sum())
    vulnerable = int(pd.to_numeric(events.get("vulnerable_user_flag", 0), errors="coerce").fillna(0).sum())
    heavy = int(pd.to_numeric(events.get("heavy_vehicle_flag", 0), errors="coerce").fillna(0).sum())

    robust = sensitivity[sensitivity["clasificacion_robustez"] == "ROBUSTO"].copy() if not sensitivity.empty else pd.DataFrame()
    source_scope = value_counts_table(events["nearest_osm_source_scope"], "nearest_osm_source_scope")
    osm_status = value_counts_table(events["osm_match_status"], "osm_match_status")
    text_resolution = value_counts_table(events["text_osm_resolution"], "text_osm_resolution")
    severity = value_counts_table(events["severity_class"], "severity_class")
    corridor_source = value_counts_table(events["corridor_norm_source"], "corridor_norm_source")

    lines: list[str] = []
    lines.extend(
        [
            "# Informe detallado - Analisis de incidentes.csv",
            "",
            f"**Fecha de generacion:** {datetime.now().isoformat(timespec='seconds')}",
            "",
            "## 1. Proposito del analisis",
            "",
            "Este informe documenta el trabajo realizado sobre `Data/News/incidentes.csv`. El objetivo no fue construir todavia el KPI final de movilidad, sino evaluar si los incidentes recopilados desde noticias y redes sociales pueden aportar una metrica complementaria util para el sistema de movilidad.",
            "",
            "La pregunta de fondo es: **la informacion noticiosa georreferenciada permite detectar presion vial, recurrencia por corredor, severidad preliminar y amplificacion social de manera suficientemente estructurada para entrar al sistema de metricas?**",
            "",
            "La respuesta, con los datos actuales, es positiva para una prueba de concepto: la base contiene eventos deduplicados, menciones, engagement, coordenadas, informacion territorial y posibilidad de asociacion con red vial OSM. La advertencia metodologica es que esta fuente no debe interpretarse como siniestralidad oficial.",
            "",
            "## 2. Alcance y unidad de analisis",
            "",
            "Se trabajaron tres unidades separadas:",
            "",
            "- **Evento:** registro deduplicado de un incidente vial. Es la unidad principal.",
            "- **Mencion:** publicacion, nota, tweet, RSS o entrada asociada al evento. Un evento puede tener multiples menciones.",
            "- **Snapshot de engagement:** captura temporal de interacciones sociales asociadas a una mencion.",
            "",
            "Esta separacion evita confundir cantidad de noticias con cantidad de eventos. Tambien permite medir amplificacion social sin duplicar incidentes.",
            "",
            "### Resumen cuantitativo",
            "",
            f"- Eventos deduplicados: **{number(total_events)}**.",
            f"- Menciones asociadas: **{number(total_mentions)}**.",
            f"- Snapshots de engagement: **{number(total_snapshots)}**.",
            f"- Periodo observado: **{period_min}** a **{period_max}**.",
            f"- Eventos con coordenada dentro de El Salvador: **{number(valid_points)}** ({pct(valid_points, total_events)}).",
            f"- Eventos con asociacion OSM alta/media: **{number(osm_high_medium)}** ({pct(osm_high_medium, total_events)}).",
            f"- Eventos con corredor normalizado: **{number(corridor_events)}** ({pct(corridor_events, total_events)}).",
            f"- Corredores funcionales distintos: **{number(corridors_distinct)}**.",
            "",
            "![Resumen ejecutivo](fig_resumen_ejecutivo_incidentes.png)",
            "",
            "## 3. Flujo implementado",
            "",
            "El flujo implementado se estructura asi:",
            "",
            "1. Lectura de `incidentes.csv`.",
            "2. Normalizacion de campos temporales, territoriales, coordenadas y engagement.",
            "3. Expansion de menciones y snapshots.",
            "4. Diagnostico de integridad y calidad geografica.",
            "5. Extraccion de severidad preliminar, usuarios vulnerables y contexto vial textual.",
            "6. Descarga y construccion de red OSM departamental/nacional.",
            "7. Asociacion espacial evento-via usando coordenada como fuente principal.",
            "8. Resolucion semantica texto-OSM mediante `corridor_norm`.",
            "9. Calculo de rankings territoriales, temporales, por tipo de via y por corredor.",
            "10. Calculo de score exploratorio de corredores criticos.",
            "11. Experimentos de pesos A/B/C y sensibilidad metodologica.",
            "12. Generacion de dashboard y figuras ejecutivas.",
            "",
            "## 4. Calidad e integridad del dato",
            "",
            "El diagnostico de integridad muestra que la base tiene estructura suficiente para analisis exploratorio avanzado. Hay campos utiles de evento, fuente, ubicacion, evidencia, engagement, coordenadas y reglas de deduplicacion.",
            "",
            "### Indicadores de integridad",
            "",
            table(integrity, max_rows=25),
            "",
            "### Calidad geografica",
            "",
            f"- Eventos con par latitud/longitud: **{number(coordinate_pairs)}**.",
            f"- Eventos dentro del bbox de El Salvador: **{number(valid_points)}**.",
            f"- Eventos sin coordenada: **{number(missing)}**.",
            f"- Eventos fuera del bbox de El Salvador: **{number(outside)}**.",
            f"- Eventos con coordenada repetida: **{number(repeated)}**.",
            "",
            table(coordinates, max_rows=10),
            "",
            "La interpretacion es favorable: la mayoria de eventos cuenta con coordenadas utiles. Sin embargo, las coordenadas repetidas no se eliminan porque pueden significar recurrencia real, ubicacion generica o geocodificacion aproximada. Se conservan como una senal de calidad y se etiquetan para analisis.",
            "",
            "![Diagnostico de coordenadas](diagnostico_coordenadas_incidentes.png)",
            "",
            "## 5. Normalizacion territorial",
            "",
            "Se conservaron los campos originales de departamento y municipio, pero se generaron campos normalizados para evitar fragmentacion por diferencias de escritura. Esto permite rankings consistentes por departamento y municipio.",
            "",
            "### Ranking por departamento",
            "",
            table(departments, ["department_norm", "events", "traffic_accidents", "mentions", "impact_social", "severity_sum", "valid_points", "avg_metric_score"], 13),
            "",
            "Los departamentos con mayor volumen son San Salvador, La Libertad, Sonsonate y Santa Ana. Esto sugiere concentracion en zonas urbanas y corredores interurbanos de alta exposicion noticiosa.",
            "",
            "### Ranking por municipio",
            "",
            table(municipalities, ["department_norm", "municipality_norm", "events", "mentions", "impact_social", "severity_sum", "valid_points", "avg_metric_score"], 15),
            "",
            "La lectura municipal muestra concentracion en San Salvador, Sonsonate, Santa Tecla, Santa Ana y Antiguo Cuscatlan. A nivel de movilidad, el municipio ayuda a priorizar territorio, pero la lectura por corredor resulta mas accionable.",
            "",
            "## 6. Severidad preliminar y variables extraidas",
            "",
            "A partir del texto y campos estructurados se construyeron variables de severidad preliminar. Estas variables no sustituyen partes oficiales, pero permiten diferenciar eventos de bajo contenido informativo frente a incidentes con lesionados, fallecidos o usuarios vulnerables.",
            "",
            "### Distribucion de severidad",
            "",
            table(severity, max_rows=10),
            "",
            f"- Eventos con fallecidos: **{number(fatality)}**.",
            f"- Eventos con lesionados: **{number(injury)}**.",
            f"- Eventos con usuarios vulnerables: **{number(vulnerable)}**.",
            f"- Eventos con vehiculos pesados: **{number(heavy)}**.",
            "",
            "Estas variables son relevantes porque una metrica de movilidad no deberia ponderar igual un reporte de congestion, un accidente con lesionados y un evento con fallecidos.",
            "",
            "## 7. Red OSM departamental y nacional",
            "",
            "Se construyo una red OSM enriquecida por departamentos usando Overpass API. La logica fue particionar la red para evitar cargar todo el pais en cada operacion interactiva. El consolidado nacional queda como producto analitico y respaldo.",
            "",
            "### Cobertura OSM generada",
            "",
            table(osm_coverage, ["department", "slug", "status", "query_mode", "segments", "catalog_roads", "length_km"], 20),
            "",
            "El resultado permite que el match evento-via funcione fuera del AMSS. La prioridad de busqueda implementada es:",
            "",
            "1. Si el evento tiene coordenada y departamento normalizado, se usa la red OSM de ese departamento.",
            "2. Si no hay red departamental o falla, se usa la red nacional consolidada.",
            "3. Si aplica y existe, AMSS queda como respaldo local.",
            "4. Si no hay coordenada, no se fuerza match espacial y el evento queda como `NO_COORDINATE_FOR_OSM`.",
            "",
            "## 8. Asociacion evento-via con OSM",
            "",
            "La asociacion evento-via se hizo con la coordenada como fuente principal. Esto es metodologicamente importante porque el texto de una noticia puede mencionar una carretera general, una interseccion, una colonia o una referencia local. La coordenada permite buscar el segmento vial mas cercano en OSM y medir distancia.",
            "",
            "La clasificacion espacial usada fue:",
            "",
            "- `SPATIAL_OSM_HIGH`: distancia menor o igual a 50 m.",
            "- `SPATIAL_OSM_MEDIUM`: distancia mayor a 50 m y menor o igual a 150 m.",
            "- `SPATIAL_OSM_LOW_REVIEW`: distancia mayor a 150 m y menor o igual a 500 m.",
            "- `SPATIAL_OSM_DISTANCE_CONFLICT`: distancia mayor a 500 m.",
            "- `NO_COORDINATE_FOR_OSM`: evento sin coordenada.",
            "- `INVALID_POINT_FOR_OSM`: coordenada invalida para asociacion.",
            "",
            "### Resultado del match OSM",
            "",
            table(osm_status, max_rows=15),
            "",
            "### Fuente OSM usada",
            "",
            table(source_scope, max_rows=10),
            "",
            "El resultado principal es que **83 eventos** tienen asociacion OSM alta o media. Esto demuestra que la capa de noticias puede conectarse operativamente con la red vial, no solo con unidades administrativas.",
            "",
            "### Tipo de via OSM asociado",
            "",
            table(osm_type, max_rows=12),
            "",
            "La presencia de tipos como `LOCAL_RESIDENCIAL`, `ARTERIAL_PRINCIPAL`, `ARTERIAL_SECUNDARIA`, `COLECTORA` y `NACIONAL_ESTRUCTURANTE` permite comenzar a diferenciar la naturaleza vial de los incidentes.",
            "",
            "![Mapa ejecutivo](fig_mapa_ejecutivo_incidentes.png)",
            "",
            "## 9. Resolucion texto-OSM y corridor_norm",
            "",
            "OSM puede dividir una misma via en muchos segmentos y nombrarlos con etiquetas locales. Por ejemplo, una noticia puede decir `Carretera Panamericana`, mientras OSM devuelve un segmento local como `2a Calle Poniente` con referencia `CA-1`. Para evitar fragmentacion, se creo `corridor_norm`, que representa el corredor funcional consolidado.",
            "",
            "Columnas creadas:",
            "",
            "- `corridor_norm`: corredor funcional consolidado.",
            "- `corridor_norm_source`: fuente usada para resolverlo: `OSM_REF`, `OSM_NAME`, `TEXT_ALIAS`, `MANUAL_RULE` o `UNRESOLVED`.",
            "- `text_corridor_norm`: corredor inferido desde el texto de la noticia.",
            "- `nearest_osm_corridor_norm`: corredor inferido desde OSM.",
            "- `text_osm_resolution`: clasificacion de compatibilidad texto-OSM.",
            "- `corridor_resolution_confidence`: confianza de la resolucion.",
            "",
            "### Fuentes de corridor_norm",
            "",
            table(corridor_source, max_rows=10),
            "",
            "### Resolucion texto-OSM",
            "",
            table(text_resolution, max_rows=10),
            "",
            "Los conflictos no se eliminaron. Se reclasificaron como compatibles, intersecciones aceptadas, nombre local dentro de corredor, revision o no resuelto. Esto mantiene trazabilidad metodologica.",
            "",
            f"Casos en revision/conflicto documentados: **{number(len(conflicts))}**.",
            "",
            table(conflicts, ["ticketNumber", "department_norm", "municipality_norm", "corridor_candidate", "nearest_osm_name", "nearest_osm_ref", "corridor_norm", "text_osm_resolution", "corridor_resolution_confidence", "nearest_osm_distance_m"], 15),
            "",
            "## 10. Corredores normalizados y criticidad",
            "",
            "El resultado mas accionable del analisis es el ranking por corredor normalizado. Este nivel es mas util para movilidad que solo mirar puntos o municipios, porque permite priorizar tramos, carreteras y ejes viales.",
            "",
            "### Ranking por corredor normalizado",
            "",
            table(corridors_norm, ["corridor_norm", "events", "mentions", "impact_social", "severity_sum", "valid_points", "fatality_events", "injury_events", "vulnerable_events", "osm_high_medium", "compatible_events", "review_events"], 15),
            "",
            "La `Carretera Panamericana` aparece como el corredor dominante: concentra volumen, menciones, asociaciones OSM y recurrencia territorial. Otros corredores relevantes son `Carretera A Sonsonate`, `Carretera al Puerto de La Libertad`, `Autopista a Comalapa`, `Boulevard Constitucion` y `Paseo General Escalon`.",
            "",
            "### Score exploratorio de corredores criticos",
            "",
            "Se calculo un score exploratorio que combina volumen, menciones, impacto social, severidad, fallecidos, lesionados, usuarios vulnerables y asociacion OSM alta/media. Este score no es el KPI final; sirve para priorizar corredores que merecen analisis detallado.",
            "",
            table(critical_corridors, ["corridor_norm", "events", "mentions", "impact_social", "severity_sum", "fatality_events", "injury_events", "vulnerable_events", "osm_high_medium", "avg_osm_distance_m", "corridor_criticality_score"], 15),
            "",
            "![Corredores y sensibilidad](fig_corredores_sensibilidad_incidentes.png)",
            "",
            "## 11. Experimentos de pesos y sensibilidad",
            "",
            "Se implementaron experimentos para evaluar si los corredores criticos dependen de un solo supuesto de ponderacion.",
            "",
            "Escenarios:",
            "",
            "- **Actual:** balance exploratorio entre volumen, severidad, engagement y match OSM.",
            "- **A - Recurrencia/volumen:** mayor peso a cantidad de eventos.",
            "- **B - Severidad:** mayor peso a severidad, fallecidos, lesionados y usuarios vulnerables.",
            "- **C - Social/noticioso:** mayor peso a menciones e impacto social.",
            "",
            "No se buscaron pesos optimos porque no existe una verdad externa observada contra la cual calibrar. La finalidad fue evaluar robustez.",
            "",
            "### Corredores robustos",
            "",
            table(robust, ["corridor", "rank_ACTUAL_PIPELINE", "rank_A_RECURRENCIA_VOLUMEN", "rank_B_SEVERIDAD", "rank_C_SOCIAL_NOTICIOSO", "ranking_promedio", "score_promedio_normalizado", "frecuencia_top_5", "clasificacion_robustez"], 10),
            "",
            "Los corredores robustos son importantes porque se mantienen en posiciones altas aunque cambie el enfoque metodologico. La `Carretera Panamericana` es el caso mas claro: aparece en primer lugar en todos los escenarios.",
            "",
            "## 12. Temporalidad",
            "",
            "El periodo cubierto es corto, por lo que no permite afirmar tendencia estructural. Aun asi, la serie diaria permite observar picos de actividad noticiosa y de engagement.",
            "",
            table(daily, max_rows=10),
            "",
            "La mayor actividad aparece el 29 de junio de 2026, con mayor volumen de eventos, menciones, visualizaciones y shares. Esto muestra que la fuente puede usarse para monitoreo temprano, siempre que se amplie la ventana temporal.",
            "",
            "![Serie diaria](serie_diaria_eventos_incidentes.png)",
            "",
            "### Serie horaria",
            "",
            table(hourly, max_rows=24),
            "",
            "## 13. Engagement e impacto social",
            "",
            "El engagement permite medir amplificacion social y visibilidad publica. No mide accidentalidad real, pero si ayuda a identificar donde un evento genero mayor conversacion o exposicion digital.",
            "",
            f"- Likes ultimo snapshot: **{number(likes_total)}**.",
            f"- Comentarios ultimo snapshot: **{number(comments_total)}**.",
            f"- Shares/retweets ultimo snapshot: **{number(shares_total)}**.",
            f"- Views ultimo snapshot: **{number(views_total)}**.",
            f"- Impacto social ponderado total: **{number(impact_total)}**.",
            "",
            "### Engagement por fuente",
            "",
            table(engagement_source, max_rows=10),
            "",
            "La fuente con mayor cantidad de menciones es `X`, seguida por RSS, Facebook e Instagram. Esto sugiere que las fuentes sociales y noticiosas no aportan el mismo tipo de senal: X concentra volumen y visualizaciones; Facebook e Instagram aportan interacciones distintas.",
            "",
            "![Ranking de impacto social](ranking_impacto_social_incidentes.png)",
            "",
            "## 14. Figuras generadas",
            "",
            "Se generaron figuras tecnicas y ejecutivas:",
            "",
            "- `fig_resumen_ejecutivo_incidentes.png`: indicadores principales, territorio, calidad geografica y evolucion diaria.",
            "- `fig_corredores_sensibilidad_incidentes.png`: corredores criticos y robustez por escenarios.",
            "- `fig_mapa_ejecutivo_incidentes.png`: incidentes georreferenciados sobre red vial principal OSM.",
            "- `diagnostico_coordenadas_incidentes.png`: calidad geografica.",
            "- `ranking_impacto_social_incidentes.png`: eventos con mayor impacto social.",
            "- `serie_diaria_eventos_incidentes.png`: serie diaria.",
            "- `serie_horaria_eventos_incidentes.png`: serie horaria.",
            "",
            "## 15. Productos generados",
            "",
            "Archivos principales en `Results/News/Incidentes`:",
            "",
            "- `eventos_incidentes_osm_nacional_enriched.csv`: base final enriquecida evento-via.",
            "- `base_menciones_incidentes_expandida.csv`: menciones asociadas a eventos.",
            "- `base_engagement_snapshots.csv`: snapshots de engagement.",
            "- `ranking_departamentos_incidentes.csv`: ranking territorial departamental.",
            "- `ranking_municipios_incidentes.csv`: ranking territorial municipal.",
            "- `ranking_corredores_norm.csv`: ranking por corredor funcional normalizado.",
            "- `analisis_corredores_criticos.csv`: score exploratorio de corredores.",
            "- `corridor_norm_resolution.csv`: trazabilidad de resolucion texto-OSM.",
            "- `revision_conflictos_texto_osm_nacional.csv`: casos a revisar.",
            "- `diagnostico_cobertura_osm_departamental.csv`: cobertura OSM por departamento.",
            "- `ranking_tipo_via_osm_nacional.csv`: tipo de via OSM asociado.",
            "- `experimentos_pesos_corredores.csv`: scores bajo escenarios de pesos.",
            "- `sensibilidad_pesos_corredores.csv`: robustez de corredores.",
            "- `experimentos_pesos_corredores.txt`: explicacion de sensibilidad.",
            "- `resultados_incidentes.txt`: resumen completo de resultados tabulados.",
            "",
            "## 16. Limitaciones",
            "",
            "Las principales limitaciones son:",
            "",
            "- El periodo observado es corto: cuatro dias. No permite concluir tendencias de largo plazo.",
            "- Las noticias tienen sesgo de cobertura: no todos los incidentes se reportan y no todos los territorios tienen igual visibilidad.",
            "- El engagement mide amplificacion social, no gravedad vial real.",
            "- Hay eventos sin coordenada y eventos con coordenadas repetidas.",
            "- Algunas asociaciones texto-OSM requieren revision porque OSM puede nombrar segmentos con nombres locales o porque la noticia menciona un corredor amplio.",
            "- No hay calibracion contra fuentes oficiales de siniestralidad, aforos o tiempos de viaje.",
            "",
            "## 17. Conclusiones",
            "",
            "El analisis demuestra que `incidentes.csv` tiene valor para el sistema de metricas de movilidad como fuente complementaria. La base permite construir una metrica exploratoria de presion socio-vial que combina evento, territorio, via, severidad preliminar y amplificacion social.",
            "",
            "La evidencia mas fuerte es la asociacion evento-via: 83 eventos tienen match OSM alto o medio, y se obtuvieron 46 corredores normalizados. Esto permite pasar de una lectura noticiosa a una lectura operacional por corredor.",
            "",
            "La `Carretera Panamericana` aparece como el corredor mas consistente y critico. Tambien destacan `Carretera A Sonsonate`, `Avenida Oidor Pedro Ramirez de Quinonez`, `Carretera A Armenia` y `Carretera Quezaltepeque - San Juan Opico` como corredores robustos bajo experimentos de sensibilidad.",
            "",
            "La recomendacion es incorporar esta fuente como **metrica complementaria exploratoria**, no como KPI final. Su rol seria detectar presion vial noticiosa, priorizar corredores para revision, observar amplificacion social y alimentar capas de monitoreo geoespacial.",
            "",
            "## 18. Recomendaciones de continuidad",
            "",
            "Para evolucionar esta prueba de concepto hacia una metrica madura se recomienda:",
            "",
            "1. Ampliar la ventana temporal a varias semanas o meses.",
            "2. Mantener la coordenada como fuente principal de asociacion evento-via.",
            "3. Usar `corridor_norm` como unidad principal para analisis vial.",
            "4. Separar siempre evento, mencion y engagement.",
            "5. Incorporar exposicion vial por corredor: longitud, jerarquia vial, volumen vehicular si existe, TPDA o velocidades.",
            "6. Cruzar posteriormente con fuentes oficiales para calibrar el valor explicativo de la metrica.",
            "7. Mantener dashboard con capas: red vial base, puntos, heat eventos, heat menciones y heat impacto social.",
            "",
            "## 19. Lectura ejecutiva final",
            "",
            "Las noticias no reemplazan los datos oficiales, pero si aportan una senal temprana y espacialmente util. Con `incidentes.csv` ya es posible identificar corredores recurrentes, eventos severos, zonas con alta amplificacion social y calidad de asociacion con red vial. Por tanto, la fuente merece entrar al sistema de metricas como una capa complementaria de monitoreo socio-vial.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(build_report(), encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
