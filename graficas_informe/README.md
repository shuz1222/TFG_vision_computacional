# Análisis de resultados

Esta carpeta contiene los cálculos del Capítulo 4 y de los Apéndices A y B del informe: la **Sección 4.1** (comparación de algoritmos con la cámara de un teléfono celular, prueba del 26/10/2026) y la **Sección 4.2** (sistema completo con la Raspberry Pi, pruebas del 10/11/2026).

Los cálculos están en dos libros de Excel, con fórmulas. Los scripts de Python de esta carpeta solo miden las fotos de la prueba con el celular, para obtener los desplazamientos en píxeles.

## Libros de Excel

| Libro | Parte del informe | Datos de entrada |
| --- | --- | --- |
| `Cálculos pruebas celular.xlsx` | Sección 4.1 y Apéndice A | `datos\resultados.json`, `datos\escalas_centros.json` y `datos\rois.json` (de los scripts de esta carpeta), y `Pruebas 26-10\datos_pruebas_26_10 (con datos).xlsx` |
| `Cálculos pruebas Raspberry.xlsx` | Sección 4.2 y Apéndice B | `resultados.csv` de `Resultados Raspberry`; `rois.json` de cada montaje, `datos_pruebas_*.xlsx` y `CR1000_Table1.dat` de `Pruebas 10-11` y `Pruebas perspectiva` |

Los datos de entrada están copiados dentro de cada libro, así que se pueden abrir sin los demás archivos.

| Hoja | Contenido |
| --- | --- |
| Resultados | Los valores del informe: viga sin carga, concordancia con el LVDT, tiempos y comparaciones sin resultado |
| Escalas | Factor de escala de cada *target* y datos de la viga |
| Registro (celular) / Registrador y Muestras (Raspberry) | Carga y LVDT de cada foto |
| ROIs (celular) | Posición del *target* fijo y de las cajas en cada serie |
| Ruido | Una fila por foto de la viga sin carga |
| Mediciones | Una fila por foto con carga, en píxeles y en milímetros |
| Escalones | Promedio de cada escalón de carga (Tablas A.3, A.4 y B.5 a B.7) |
| Tiempos (Raspberry) | Tiempo de procesamiento de cada foto en la Raspberry Pi |
| Gráficas | Visión frente al LVDT |

## Cálculos

- **Factor de escala:** lado real del *target* (28.4 mm) entre su alto en píxeles, medido entre los centros de sus cuadros oscuros. En la prueba con el celular se promedia el alto de las series tomadas desde cada distancia; en la Raspberry Pi viene del `rois.json` de cada montaje (`factor_escala.py`). Cada *target* (LVDT, centro y cuerpo) tiene su propia escala.
- **Compensación con el *target* fijo:** `(dy_target − dy_fijo) × escala`. Con las luces apagadas no se reconoció el *target* fijo, así que en ese montaje no se resta (columna "Restar el fijo" de la hoja Escalas).
- **Subida del cuerpo del LVDT:** `−(dy_cuerpo − dy_fijo) × escala_cuerpo`, positiva hacia arriba.
- **Visión corregida:** viga + subida, que es lo que se compara con el LVDT.
- **Métricas:** pendiente por el origen `Σ(visión × LVDT) / Σ(LVDT²)`, RMSE, NRMSE (RMSE entre el rango del LVDT, en %), coeficiente de Pearson y error máximo.
- **Mínimo detectable:** 3 veces la desviación estándar de la serie sin carga, restando el *target* fijo.
- **Subida y LVDT por kilogramo:** pendiente por el origen frente a la carga. En la Raspberry Pi se usan solo las fotos con más de 20 kg.
- **Razón centro/LVDT:** pendiente por el origen del *target* del centro frente al de la sección del LVDT. La esperada, 1.071, sale de la deflexión de una viga simplemente apoyada con carga en el centro.
- **Cambio de tamaño de la imagen (celular):** con los desplazamientos del *target* fijo y de las cajas, `(ux·Δdx + uy·Δdy) / (ux² + uy²)`, donde `ux` y `uy` son la separación entre sus centros (hoja ROIs).
- **SIFT + FLANN:** la celda queda vacía cuando el algoritmo no entregó resultado, y las métricas se calculan solo con las fotos que sí lo tienen.

## Medición de las fotos del celular (Python)

Se usa el entorno virtual del proyecto (`.venv`) con los paquetes de `requirements.txt`. Archivos que usan los scripts:

| Archivo o carpeta | Para qué se usa |
| --- | --- |
| `Pruebas 26-10\*.jpg` | Fotos de la prueba |
| `zncc.py` y `factor_escala.py` (raíz del proyecto) | Algoritmo ZNCC, que se ejecuta tal cual, y medición del alto de los *targets* |
| `OpenCamera\ruido_0_5_1.jpg` y `Pruebas 21-10\escalon_0_5_r1_0kg_1.jpg` | Modelos del *target* y de las cajas para ubicar las regiones automáticamente |

**En el repositorio de GitHub no están las fotos**, así que estos pasos no se pueden ejecutar ahí. Sus resultados ya están en `datos\`.

| Paso | Script | Qué hace | Resultado | Tiempo |
| --- | --- | --- | --- | --- |
| 1 | `ubicar_targets.py` | Busca en la foto de referencia de cada serie las cinco regiones: *target* de la sección del LVDT, *target* del centro, *target* del cuerpo del LVDT, *target* fijo de la repisa y cajas de la repisa. | `datos\rois.json` e imágenes de control en `control\` | ≈ 1 min |
| 2 | `medir_escalas.py` | Mide el alto de cada *target* entre los centros de sus cuadros oscuros, con `medir_bordes` y `medir_centros` de `factor_escala.py` (el mismo método que en la Raspberry Pi). | `datos\escalas_centros.json` | segundos |
| 3 | `procesar.py` | Compara cada foto con la de referencia de su serie usando ZNCC y SIFT + FLANN en las cinco regiones. | `datos\resultados.json` (desplazamientos en píxeles, coeficiente de ZNCC, *inliers* de SIFT y tiempos) y una figura por comparación en `Resultados visión 26-10\figuras\` | ≈ 15 min |

Los otros dos archivos son módulos que usan esos pasos:

- **`series.py`:** define las series (ruido, escalones y enfoque automático) y la foto de referencia de cada una.
- **`algoritmos.py`:** contiene las funciones `zncc()` y `sift()`. La primera ejecuta `zncc.py` cambiando solo la configuración. La segunda repite los pasos de `sift_flann.py`: CLAHE, ecualización y suavizado; luego SIFT, FLANN y la prueba de razón 0.5; y por último RANSAC con un umbral de 5 px y un mínimo de 10 correspondencias.

## Valores de pruebas previas

Algunos valores del texto del informe vienen de las pruebas previas (19 y 21 de octubre), que se procesaron aparte y no están en esta carpeta:

- el 81–89 % del LVDT antes de la corrección;
- los 6.5 µm de la prueba anterior;
- los 2.7–3.0 µm/kg estimados con la abrazadera.
