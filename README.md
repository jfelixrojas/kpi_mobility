# Prueba de Concepto PVN - Incidentes Viales Noticiosos

Este repositorio contiene una prueba de concepto para analizar eventos viales reportados en noticias y redes, asociarlos espacialmente con una red vial de OpenStreetMap (OSM) y evaluar si esta fuente puede aportar una metrica complementaria al sistema de movilidad.

El objetivo no es construir todavia el KPI final de movilidad. El objetivo de esta etapa es demostrar, con evidencia de datos, si las noticias georreferenciadas permiten construir una señal util de Presion Vial Noticiosa (PVN): volumen de eventos, severidad preliminar, recurrencia por corredor, asociacion evento-via, engagement social y calidad del dato.

## Que contiene el proyecto

```text
Codigos/
  streamlit_incidentes_dashboard.py      Dashboard principal de incidentes
  incidentes_analysis_pipeline.py        Pipeline de analisis de incidentes
  osm_overpass_departments.py            Descarga/procesamiento OSM por departamentos
  corridor_weight_experiments.py         Experimentos de pesos para corredores
  generate_incidentes_executive_figures.py
  generate_incidentes_detailed_report.py

Data/
  News/
    incidentes.csv                       Base principal original, si se incluye
  Processed/
    osm_roads_san_salvador/              Red vial OSM AMSS/San Salvador
    osm_roads_departments/               Red vial OSM por departamento
    osm_roads_nacional/                  Red vial OSM nacional consolidada

Results/
  News/
    Incidentes/                          Resultados principales del analisis
    Ultimas100/                          Resultados preliminares de una etapa anterior

Informes/
  informe_ejecutivo_pvn_incidentes.pdf   Informe ejecutivo generado

Makefile                                 Comandos principales de ejecucion
```

## Dashboard principal

El dashboard principal esta en:

```text
Codigos/streamlit_incidentes_dashboard.py
```

Se ejecuta con:

```bash
make run-incidentes-dashboard
```

El `Makefile` busca automaticamente un puerto disponible empezando en `8501`. Al ejecutarlo, imprimira una URL similar a:

```text
Streamlit incidentes: http://127.0.0.1:8501
```

Abre esa URL en el navegador.

Si quieres fijar manualmente el puerto:

```bash
make run-incidentes-dashboard STREAMLIT_PORT=8601
```

Si quieres cambiar el host:

```bash
make run-incidentes-dashboard STREAMLIT_HOST=0.0.0.0 STREAMLIT_PORT=8601
```

## Dependencias

Para ejecutar el dashboard se requiere Python 3 y estas librerias:

```bash
python3 -m pip install streamlit pandas pydeck
```

Para ejecutar tambien los pipelines, figuras e informes, se recomienda instalar:

```bash
python3 -m pip install streamlit pandas pydeck matplotlib lxml
```

## Archivos minimos para que abra el dashboard

El dashboard no lee directamente `Data/News/incidentes.csv`. Lee la base ya procesada y enriquecida desde `Results/News/Incidentes/`.

El archivo minimo indispensable es:

```text
Results/News/Incidentes/eventos_incidentes_osm_nacional_enriched.csv
```

Si ese archivo no existe, el dashboard intenta usar:

```text
Results/News/Incidentes/eventos_incidentes_osm_enriched.csv
```

Sin uno de esos dos archivos, Streamlit mostrara un mensaje indicando que primero debe ejecutarse:

```bash
make run-incidentes-analysis
```

## Archivos necesarios para el mapa vial

Para que la capa vial OSM se visualice correctamente en el mapa, se requieren archivos de segmentos viales:

```text
Data/Processed/osm_roads_san_salvador/osm_road_segments.csv
Data/Processed/osm_roads_departments/*/osm_road_segments.csv
Data/Processed/osm_roads_nacional/osm_road_segments.csv
```

La ruta departamental es importante porque el dashboard carga la red vial segun el departamento filtrado. Si no existe red departamental, intenta usar la red nacional. Si tampoco existe, el dashboard puede abrir, pero el mapa no tendra capa vial OSM.

## Resultados recomendados para una experiencia completa

Para que todas las pestañas del dashboard tengan contenido completo, conserva estos archivos:

```text
Results/News/Incidentes/eventos_incidentes_osm_nacional_enriched.csv
Results/News/Incidentes/analisis_corredores_criticos.csv
Results/News/Incidentes/sensibilidad_pesos_corredores.csv
Results/News/Incidentes/resumen_engagement_por_fuente_incidentes.csv
Results/News/Incidentes/base_engagement_snapshots.csv
Results/News/Incidentes/diagnostico_coordenadas_incidentes.csv
Results/News/Incidentes/diagnostico_integridad_incidentes.csv
Results/News/Incidentes/resumen_unresolved_corridor_norm.csv
Results/News/Incidentes/analisis_unresolved_corridor_norm_detalle.csv
Results/News/Incidentes/investigacion_osm_sin_nombre_ref_detalle.csv
Results/News/Incidentes/investigacion_osm_sin_nombre_ref_candidatos.csv
Results/News/Incidentes/diagnostico_cobertura_osm_departamental.csv
Results/News/Incidentes/ranking_tipo_via_osm_nacional.csv
Results/News/Incidentes/fig_resumen_ejecutivo_incidentes.png
Results/News/Incidentes/fig_corredores_sensibilidad_incidentes.png
Results/News/Incidentes/fig_mapa_ejecutivo_incidentes.png
```

Si alguno falta, el dashboard no necesariamente falla, pero algunas secciones apareceran vacias o con menor nivel de detalle.

## Pestañas del dashboard

El dashboard esta organizado en ocho pestañas:

- `Resumen`: indicadores principales de eventos, menciones, impacto social, severidad y viabilidad metodologica.
- `Mapa PVN`: red vial OSM, puntos de incidentes y mapas de calor por eventos, menciones e impacto social.
- `Corredores`: ranking de corredores normalizados, recurrencia, severidad, impacto y robustez por escenarios de pesos.
- `Temporal`: comportamiento de eventos, menciones e impacto por fecha y hora.
- `Engagement`: amplificacion social/noticiosa: menciones, views, likes, shares e impacto social.
- `OSM / Vias`: asociacion evento-via, distancia al segmento OSM, tipo de via y cobertura de red.
- `Calidad`: diagnostico de coordenadas, casos sin coordenada, coordenadas repetidas, no resueltos y brechas de asociacion.
- `Detalle`: tabla operativa de eventos filtrados con opcion de descarga CSV.

## Flujo de trabajo recomendado

Si ya existen los resultados procesados:

```bash
make run-incidentes-dashboard
```

Si se quiere regenerar el analisis de incidentes:

```bash
make run-incidentes-analysis
```

Si se quiere descargar o actualizar la red OSM por departamentos:

```bash
make download-osm-departments
```

Si se quiere regenerar las figuras ejecutivas:

```bash
make run-incidentes-figures
```

## Notas metodologicas

- La coordenada del evento es la fuente principal para asociar noticia y via.
- OSM se usa como red vial base para encontrar el segmento vial mas cercano y caracterizar la via.
- `corridor_norm` consolida nombres funcionales de corredores cuando OSM usa nombres locales o referencias distintas.
- La PVN no mide siniestralidad oficial. Mide una señal experimental basada en noticias, georreferenciacion, severidad preliminar y engagement.
- Los scores de corredores son exploratorios. Sirven para evaluar robustez, recurrencia y potencial utilidad de la fuente noticiosa, no para reemplazar estadisticas oficiales.

## Comando principal

Para ejecutar la visualizacion:

```bash
make run-incidentes-dashboard
```
