# Informe ejecutivo - Prueba de concepto de Presion Vial Noticiosa

**Fecha:** 2026-06-30  
**Base principal:** `Data/News/incidentes.csv`  
**Carpeta de resultados:** `Results/News/Incidentes/`  
**Variable candidata:** Presion Vial Noticiosa (PVN)

## 1. Resumen ejecutivo

Esta prueba de concepto evalua si los incidentes viales recopilados desde noticias, redes sociales y fuentes digitales pueden aportar una variable complementaria al futuro sistema de KPI de movilidad. El objetivo no es construir todavia el KPI final, sino demostrar con evidencia si la informacion noticiosa tiene suficiente estructura, calidad geografica, trazabilidad temporal, severidad preliminar y senal social para convertirse en una metrica util.

La variable candidata se denomina **Presion Vial Noticiosa (PVN)**. La PVN no debe interpretarse como siniestralidad oficial ni como conteo real total de accidentes. Mide la intensidad observada en fuentes noticiosas y digitales, combinando eventos deduplicados, menciones asociadas, severidad preliminar, ubicacion espacial, asociacion con red vial OSM y amplificacion social.

El resultado principal es favorable: la base permite construir una capa analitica de incidentes sobre una red vial OSM, identificar territorios y corredores con recurrencia, diferenciar eventos por severidad y observar donde se concentra la conversacion social. La fuente debe entrar al sistema como **variable complementaria de monitoreo temprano**, no como fuente unica ni definitiva.

![Resumen ejecutivo](fig_resumen_ejecutivo_incidentes.png)

## 2. Decision recomendada

La informacion de `incidentes.csv` **si merece entrar al sistema de metricas de movilidad como variable complementaria**, bajo tres condiciones:

1. La PVN debe presentarse como una metrica experimental basada en noticias, no como estadistica oficial de accidentes.
2. La coordenada debe ser la fuente principal para asociar evento-via; el texto debe usarse como soporte, normalizacion o recuperacion de casos sin coordenada.
3. El resultado debe usarse para priorizacion, monitoreo, alertas territoriales y seleccion de corredores candidatos, no para concluir causalidad ni tasas reales de riesgo.

En terminos ejecutivos, la fuente sirve para responder: **donde se esta concentrando la presion vial reportada, que tan graves son los eventos, que corredores se repiten y donde la conversacion social amplifica el problema.**

## 3. Datos analizados

La base principal contiene eventos deduplicados y menciones asociadas. Esto es importante porque no se mezclan dos unidades distintas: un evento vial puede aparecer en varias publicaciones, pero sigue siendo un solo incidente.

| Indicador | Resultado |
| --- | ---: |
| Eventos deduplicados | 113 |
| Menciones asociadas | 312 |
| Snapshots de engagement | 2,197 |
| Periodo observado | 2026-06-27 18:23:51 a 2026-06-30 12:07:28 |
| Accidentes de transito | 103 |
| Otros eventos viales | 10 |
| Likes ultimo snapshot | 2,185 |
| Comentarios ultimo snapshot | 62 |
| Shares/retweets ultimo snapshot | 170 |
| Quotes ultimo snapshot | 2 |
| Visualizaciones ultimo snapshot | 91,246 |
| Impacto social ponderado total | 3,258.54 |

La lectura temporal debe hacerse con cautela porque el periodo observado es corto. Aun asi, el conjunto permite probar la metodologia completa: limpieza, deduplicacion, georreferenciacion, asociacion vial, severidad, engagement, mapas de calor, ranking territorial y ranking por corredor.

## 4. Que mide la PVN

La **Presion Vial Noticiosa** mide la intensidad con la que los incidentes viales aparecen y se amplifican en fuentes digitales. Esta variable puede construirse desde tres niveles:

| Nivel | Que mide | Uso esperado |
| --- | --- | --- |
| Evento | Severidad, menciones, engagement, calidad geografica y asociacion OSM | Priorizar eventos relevantes |
| Territorio | Concentracion por departamento, municipio o zona | Detectar areas con presion noticiosa |
| Corredor | Recurrencia, severidad y amplificacion social por via/corredor | Identificar corredores candidatos para analisis vial |

La PVN funciona como una **senal complementaria** para un KPI de movilidad mas amplio. No reemplaza variables duras como velocidad, flujo, tiempos de viaje, TPDA, siniestros oficiales o capacidad vial. Su valor esta en capturar una dimension que las fuentes operativas tradicionales pueden no reflejar: **percepcion publica, reportabilidad, recurrencia noticiosa y amplificacion social del incidente vial.**

## 5. Calidad geografica

La calidad geografica es suficiente para una prueba de concepto. De 113 eventos, 89 tienen par latitud/longitud y 88 se encuentran dentro del control preliminar de El Salvador.

| Estado de coordenada | Eventos | Menciones | Impacto social | Porcentaje |
| --- | ---: | ---: | ---: | ---: |
| Punto valido | 55 | 130 | 1,988.58 | 48.67% |
| Punto valido con coordenada repetida | 33 | 116 | 1,022.57 | 29.20% |
| Sin coordenada | 24 | 39 | 247.39 | 21.24% |
| Fuera del bbox de El Salvador | 1 | 27 | 0.00 | 0.88% |

La existencia de coordenadas repetidas no se trato como error automatico. Se conservo porque puede significar recurrencia real, uso de punto generico por geocodificacion o concentracion sobre una misma interseccion/corredor. La recomendacion es mantener estas coordenadas, pero etiquetarlas para control de calidad.

![Diagnostico de coordenadas](diagnostico_coordenadas_incidentes.png)

## 6. Asociacion evento-via con OSM

La asociacion evento-via se implemento usando la coordenada como fuente principal. El flujo conceptual es:

```text
evento deduplicado -> coordenada -> segmento OSM mas cercano -> nombre/ref OSM -> corridor_norm
```

El texto de la noticia se usa para complementar la asociacion, especialmente cuando OSM devuelve nombres locales o cuando la noticia menciona corredores funcionales mas amplios. Por ejemplo, una noticia puede decir "Carretera Panamericana", mientras OSM puede devolver un segmento local con `ref=CA-1`. Para resolver esto se creo `corridor_norm`, que consolida nombres funcionales equivalentes.

| Estado de match OSM | Eventos |
| --- | ---: |
| SPATIAL_OSM_HIGH | 77 |
| SPATIAL_OSM_MEDIUM | 6 |
| SPATIAL_OSM_LOW_REVIEW | 2 |
| SPATIAL_OSM_DISTANCE_CONFLICT | 2 |
| NO_NEAR_OSM_SEGMENT | 1 |
| INVALID_POINT_FOR_OSM | 1 |
| NO_COORDINATE_FOR_OSM | 24 |

El 73.45% de los eventos tiene asociacion OSM alta o media. Esto es un resultado fuerte para una prueba de concepto, porque permite pasar de puntos aislados a lectura por red vial.

## 7. Cobertura OSM nacional

Se amplio OSM desde AMSS hacia una red departamental/nacional. El resultado generado incluye 14 departamentos con cobertura `OK`.

| Indicador OSM | Resultado |
| --- | ---: |
| Departamentos con cobertura generada | 14 |
| Segmentos OSM consolidados | 109,221 |
| Vias catalogadas | 85,962 |
| Longitud vial acumulada | 38,320.40 km |

Los departamentos con mayor cantidad de segmentos descargados fueron San Salvador, La Libertad, Santa Ana, Cuscatlan y San Miguel. Esto permite que los eventos fuera del AMSS tambien tengan intento de asociacion vial.

![Mapa vial e incidentes](fig_mapa_ejecutivo_incidentes.png)

## 8. Resultados territoriales

La concentracion territorial muestra que los principales departamentos por volumen de eventos son San Salvador, La Libertad y Sonsonate.

| Departamento | Eventos | Accidentes | Menciones | Impacto social | Puntos validos |
| --- | ---: | ---: | ---: | ---: | ---: |
| San Salvador | 30 | 26 | 63 | 804.71 | 27 |
| La Libertad | 26 | 25 | 105 | 939.57 | 21 |
| Sonsonate | 14 | 14 | 52 | 853.34 | 13 |
| Sin departamento | 13 | 12 | 19 | 162.53 | 2 |
| Santa Ana | 10 | 10 | 21 | 191.97 | 10 |

A nivel municipal, San Salvador concentra 15 eventos, seguido por Sonsonate, Santa Tecla, Santa Ana y Antiguo Cuscatlan. Esto confirma que el enfoque territorial sirve para una lectura ejecutiva, pero la lectura por corredor es mas accionable para movilidad.

| Municipio | Departamento | Eventos | Menciones | Impacto social |
| --- | --- | ---: | ---: | ---: |
| San Salvador | San Salvador | 15 | 31 | 547.42 |
| Sonsonate | Sonsonate | 9 | 42 | 66.44 |
| Santa Tecla | La Libertad | 9 | 26 | 63.58 |
| Santa Ana | Santa Ana | 7 | 12 | 63.74 |
| Antiguo Cuscatlan | La Libertad | 5 | 17 | 480.98 |
| Armenia | Sonsonate | 2 | 5 | 713.35 |
| San Juan Opico | La Libertad | 2 | 7 | 281.26 |

## 9. Severidad preliminar

La base permite extraer severidad preliminar desde campos estructurados y texto. Esto es clave porque una metrica de movilidad no deberia ponderar igual un accidente sin detalle, un incidente con lesionados y un evento con fallecidos.

| Clase de severidad | Eventos |
| --- | ---: |
| Accidente no especificado | 56 |
| Lesionados reportados | 29 |
| Fallecidos reportados | 15 |
| Baja informacion / otro | 8 |
| Solo danos materiales | 3 |
| Afectacion vial | 2 |

Adicionalmente, se identificaron 33 eventos con lesionados, 15 con fallecidos, 29 con usuarios vulnerables y 31 con vehiculos pesados. Estas variables son relevantes para una PVN porque permiten separar volumen simple de criticidad del evento.

## 10. Corredores normalizados

El paso mas importante de la prueba fue pasar de evento puntual a corredor funcional. Se obtuvo `corridor_norm` en 81 de 113 eventos, equivalentes al 71.68% de la base. En total se identificaron 46 corredores funcionales distintos.

| Corredor normalizado | Eventos | Menciones | Impacto social | Fallecidos | Lesionados | OSM alto/medio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Carretera Panamericana | 18 | 46 | 442.71 | 0 | 4 | 13 |
| Carretera al Puerto de La Libertad | 5 | 21 | 43.89 | 0 | 0 | 5 |
| Carretera A Sonsonate | 4 | 10 | 39.48 | 3 | 1 | 3 |
| Autopista a Comalapa | 3 | 6 | 45.52 | 0 | 1 | 2 |
| Boulevard Constitucion | 3 | 29 | 25.54 | 0 | 1 | 2 |
| Avenida Oidor Pedro Ramirez de Quinonez | 3 | 29 | 14.00 | 1 | 2 | 3 |
| Carretera Quezaltepeque - San Juan Opico | 2 | 7 | 281.26 | 1 | 0 | 2 |
| Paseo General Escalon | 2 | 11 | 278.93 | 0 | 1 | 2 |
| Calle A Mariona | 2 | 4 | 117.52 | 0 | 1 | 2 |
| Avenida Bernal | 2 | 8 | 71.08 | 0 | 2 | 1 |

La Carretera Panamericana aparece como el corredor mas consistente por volumen, menciones, cobertura territorial y estabilidad metodologica. Otros corredores tienen menor volumen, pero alta severidad o alta amplificacion social.

## 11. Score exploratorio de corredores criticos

Se calculo un score exploratorio de criticidad de corredores. Este score no es el KPI final. Su funcion es ordenar corredores por una combinacion de volumen, severidad, usuarios vulnerables, menciones, impacto social y calidad de asociacion OSM.

| Ranking | Corredor | Score criticidad | Eventos | Menciones | Impacto social | Lectura ejecutiva |
| ---: | --- | ---: | ---: | ---: | ---: | --- |
| 1 | Carretera Panamericana | 79.88 | 18 | 46 | 442.71 | Corredor dominante y mas robusto |
| 2 | Carretera A Sonsonate | 36.05 | 4 | 10 | 39.48 | Alta severidad relativa |
| 3 | Avenida Oidor Pedro Ramirez de Quinonez | 28.61 | 3 | 29 | 14.00 | Recurrencia con lesionados/fallecido |
| 4 | Carretera A Armenia | 28.35 | 1 | 4 | 710.35 | Bajo volumen, muy alto impacto social |
| 5 | Carretera Quezaltepeque - San Juan Opico | 20.94 | 2 | 7 | 281.26 | Severidad e impacto social relevantes |
| 6 | Carretera al Puerto de La Libertad | 20.31 | 5 | 21 | 43.89 | Recurrencia estable, menor severidad |

La interpretacion clave es que la PVN no solo detecta donde hay mas eventos; tambien permite distinguir corredores con pocos eventos pero alta severidad o alta amplificacion social.

![Corredores y sensibilidad](fig_corredores_sensibilidad_incidentes.png)

## 12. Robustez de corredores

Se probaron escenarios de pesos para evaluar si los corredores criticos dependen de una unica formula. No se buscaron pesos optimos porque no existe una verdad externa supervisada. Se evaluo sensibilidad bajo tres enfoques: recurrencia/volumen, severidad y social/noticioso.

| Corredor | Ranking promedio | Frecuencia top 5 | Clasificacion |
| --- | ---: | ---: | --- |
| Carretera Panamericana | 1.00 | 4/4 | Robusto |
| Carretera A Sonsonate | 2.50 | 4/4 | Robusto |
| Avenida Oidor Pedro Ramirez de Quinonez | 3.00 | 4/4 | Robusto |
| Carretera A Armenia | 3.75 | 4/4 | Robusto |
| Carretera Quezaltepeque - San Juan Opico | 5.50 | 3/4 | Robusto |
| Carretera al Puerto de La Libertad | 7.00 | 1/4 | Dependiente del enfoque |

La senal mas estable es Carretera Panamericana: aparece primera bajo todos los escenarios. Esto es una evidencia fuerte de que la metodologia no depende exclusivamente de un conjunto arbitrario de pesos.

## 13. Tipo de via asociado

La asociacion con OSM permite clasificar los eventos por tipo de via. Esto abre la puerta a cruzar PVN con jerarquia vial, infraestructura y exposicion futura.

| Tipo de via OSM | Eventos | Menciones | Impacto social | Distancia media |
| --- | ---: | ---: | ---: | ---: |
| Local residencial | 23 | 71 | 1,113.46 | 21.04 m |
| Arterial principal | 19 | 72 | 478.23 | 6.24 m |
| Servicio/acceso | 13 | 22 | 335.25 | 17.11 m |
| Arterial secundaria | 9 | 26 | 510.44 | 5.14 m |
| Colectora | 9 | 23 | 324.45 | 139.37 m |
| Nacional estructurante | 7 | 16 | 127.79 | 80.34 m |
| No clasificada OSM | 7 | 10 | 103.23 | 92.03 m |

Esta salida debe interpretarse como clasificacion OSM preliminar. En una etapa posterior conviene armonizar los tipos OSM con una jerarquia vial oficial o institucional.

## 14. Engagement e impacto social

La base permite analizar no solo eventos, sino tambien amplificacion social. Esto es precisamente lo que diferencia la PVN de una metrica puramente vial.

| Fuente | Menciones | Eventos | Likes | Comentarios | Shares | Views |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| X | 174 | 73 | 465 | 18 | 126 | 90,836 |
| RSS | 64 | 11 | 0 | 0 | 0 | 0 |
| Facebook | 46 | 40 | 866 | 38 | 44 | 0 |
| Instagram | 21 | 21 | 854 | 6 | 0 | 410 |
| Google News | 7 | 5 | 0 | 0 | 0 | 0 |

La plataforma X domina en menciones y visualizaciones; Facebook e Instagram aportan senal fuerte de interaccion por likes y comentarios. La PVN permite separar "evento vial" de "evento socialmente amplificado".

## 15. Evolucion temporal observada

El periodo observado es corto, por lo que no permite afirmar tendencia estructural. Aun asi, es suficiente para probar filtros temporales y monitoreo diario/hora.

| Fecha | Eventos | Accidentes | Menciones | Impacto social | Views | Shares |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 2026-06-27 | 14 | 11 | 30 | 23.14 | 3,425 | 0 |
| 2026-06-28 | 36 | 32 | 66 | 410.62 | 13,149 | 21 |
| 2026-06-29 | 50 | 49 | 182 | 2,414.13 | 62,034 | 130 |
| 2026-06-30 | 13 | 11 | 34 | 410.65 | 12,638 | 19 |

El 2026-06-29 concentra el mayor volumen de eventos, menciones, impacto social, visualizaciones y compartidos. Como prueba de concepto, esto valida que la PVN puede operar con filtros por fecha, hora y capa de mapa.

## 16. Mapas de calor y visualizacion

Se implemento un dashboard en Streamlit con mapa interactivo, red vial OSM, puntos de incidentes, capas de calor y filtros temporales/territoriales. Las tres capas de calor son:

| Capa | Peso usado | Que permite ver |
| --- | --- | --- |
| Heat eventos | 1 por evento | Concentracion espacial de incidentes |
| Heat menciones | Numero de menciones por evento | Donde se reporta o replica mas informacion |
| Heat impacto | Impacto social ponderado | Donde la conversacion social se amplifica mas |

El dashboard tambien incluye referencia visual de colores y valores por mapa de calor. Esto permite explicar que el color no representa una categoria fija universal, sino intensidad relativa sobre los datos filtrados y el radio de visualizacion.

## 17. Casos no resueltos y brechas

La principal brecha metodologica no es la falta de datos, sino la resolucion fina de algunos eventos contra OSM y texto vial.

| Causa no resuelta | Eventos | Accion recomendada |
| --- | ---: | --- |
| Coordenada valida, OSM sin nombre/ref y sin texto vial suficiente | 17 | No asignar corredor sin revision; probar via nombrada cercana |
| Sin coordenada, con corredor textual | 12 | Geocodificar direccion o asociar solo como corredor textual |
| Corredor textual, OSM sin nombre/ref | 11 | Buscar segmento nombrado cercano o aceptar baja confianza |
| Sin coordenada ni corredor textual | 12 | No usar para corredor hasta recuperar ubicacion |
| Ref OSM no normalizada o sin regla | 2 | Agregar regla OSM tras validacion |
| Distancia OSM conflictiva o fuera de El Salvador | 3 | Revisar coordenada, cobertura o territorio |

Estas brechas son manejables. No invalidan la prueba, pero si delimitan que la PVN debe incluir indicadores de calidad: coordenada valida, distancia a OSM, fuente de `corridor_norm`, resolucion texto-OSM y confianza de asociacion.

## 18. Producto obtenido

La prueba dejo implementados los siguientes productos:

| Producto | Archivo / ubicacion |
| --- | --- |
| Base normalizada de eventos | `base_eventos_incidentes_normalizada.csv` |
| Eventos enriquecidos con OSM nacional | `eventos_incidentes_osm_nacional_enriched.csv` |
| Capa GeoJSON de incidentes | `eventos_incidentes_georreferenciados.geojson` |
| Ranking territorial | `ranking_departamentos_incidentes.csv`, `ranking_municipios_incidentes.csv` |
| Ranking de corredores | `ranking_corredores_norm.csv` |
| Score exploratorio de corredores criticos | `analisis_corredores_criticos.csv` |
| Experimentos de pesos | `experimentos_pesos_corredores.csv`, `sensibilidad_pesos_corredores.csv` |
| Diagnosticos de calidad | `diagnostico_coordenadas_incidentes.csv`, `diagnostico_integridad_incidentes.csv` |
| Red OSM departamental/nacional | `Data/Processed/osm_roads_departments/`, `Data/Processed/osm_roads_nacional/` |
| Dashboard interactivo | `make run-incidentes-dashboard` |

## 19. Conclusiones ejecutivas

1. **La fuente noticiosa es util como variable complementaria.** La base contiene eventos deduplicados, menciones, engagement, coordenadas, texto vial, severidad preliminar y suficiente estructura para asociacion espacial.

2. **La PVN no debe ser el KPI final de movilidad.** Debe ser una entrada o componente dentro de un sistema mas amplio. Su aporte es detectar presion observada en fuentes digitales, no medir siniestralidad real total.

3. **La coordenada es la clave metodologica.** Con coordenadas, el sistema puede asociar eventos a red OSM, clasificar tipo de via y construir corredores funcionales. Sin coordenada, el texto puede ayudar, pero con menor confianza.

4. **La lectura por corredor es mas accionable que la lectura por municipio.** El territorio permite priorizacion general; el corredor permite pasar a gestion vial concreta.

5. **Carretera Panamericana es el hallazgo mas robusto.** Aparece como corredor dominante por volumen y mantiene el primer lugar bajo todos los escenarios de pesos.

6. **La amplificacion social aporta una dimension nueva.** Eventos con bajo volumen pueden volverse relevantes por impacto social, como ocurre con corredores que tienen pocos eventos pero alta interaccion.

7. **La calidad es suficiente para POC, no para operacion definitiva sin controles.** Hay 24 eventos sin coordenada, 33 con coordenada repetida y 57 eventos con resolucion texto-OSM no resuelta. Estos casos deben alimentar un modulo de calidad y recuperacion, no eliminarse automaticamente.

## 20. Recomendacion final

Se recomienda avanzar con la **Presion Vial Noticiosa (PVN)** como variable candidata dentro del sistema de metricas de movilidad, con caracter experimental y complementario. La PVN debe madurar hacia un componente operacional que integre:

- eventos deduplicados;
- severidad preliminar;
- menciones y fuentes;
- engagement o impacto social;
- coordenadas y calidad geografica;
- asociacion OSM evento-via;
- corredor normalizado;
- filtros temporales y territoriales;
- indicadores de confianza.

El siguiente paso no deberia ser cambiar los pesos de forma arbitraria, sino ampliar la ventana temporal, estabilizar la ingesta diaria, mejorar geocodificacion de casos sin coordenada, documentar reglas de `corridor_norm` y, posteriormente, cruzar PVN con variables duras de movilidad como velocidad, demora, flujo, TPDA o tiempos de viaje.

La conclusion ejecutiva es clara: **las noticias si aportan informacion relevante para el sistema, siempre que se usen como senal complementaria de presion vial observada y no como reemplazo de datos oficiales u operativos.**
