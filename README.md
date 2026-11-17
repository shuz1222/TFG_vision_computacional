# Medición de desplazamientos estructurales con visión por computadora

Código del Trabajo Final de Graduación *"Prueba de concepto de un sistema de monitoreo de desplazamientos estructurales por medio de visión por computadora"* (Escuela de Ingeniería Electrónica, Tecnológico de Costa Rica, 2026), desarrollado con el apoyo del CIVCO.

Una cámara fotografía *targets* visuales (tableros impresos de 3 × 3 cuadros) adheridos a una viga bajo carga. El programa compara cada foto con una foto de referencia, mide cuánto se movió cada *target* en píxeles y lo convierte a milímetros con un factor de escala obtenido del propio *target*. El sistema final usa una cámara IMX477 con un lente de 6 mm y una Raspberry Pi 4.

Se compararon dos algoritmos:

- **ZNCC** (correlación cruzada normalizada de media cero) con refinamiento subpíxel. Es el algoritmo seleccionado.
- **SIFT + FLANN**, con prueba de razón de Lowe y RANSAC.

En las pruebas de laboratorio, con la cámara a entre 1 y 4 m de la viga, ZNCC tuvo un desplazamiento mínimo detectable de 13 a 78 µm y un error (RMSE) frente a un LVDT de 0.023 a 0.051 mm. Los detalles están en el informe del TFG.

## Contenido

```
├── roi.py                      Marca las regiones de los targets en la foto de referencia
├── factor_escala.py            Mide el factor de escala (mm/píxel) de cada target
├── zncc.py                     Algoritmo ZNCC (función medir_zncc y ejemplo con un par de fotos)
├── sift_flann.py               Algoritmo SIFT + FLANN (función medir_sift y ejemplo con un par de fotos)
├── captura.py                  Toma las fotos de un ensayo en la Raspberry Pi
├── medir.py                    Mide todas las fotos de un ensayo y guarda los resultados en un CSV
├── graficas_informe/           Análisis de resultados: cálculos del informe en Excel y medición de las fotos del celular
├── Pruebas 26-10/              Registro de la prueba con el teléfono celular (Excel)
├── Pruebas 10-11/              Pruebas de distancia: rois.json, registros y el par de fotos de ejemplo
├── Pruebas perspectiva/        Pruebas de ángulo e iluminación: rois.json y registros
└── Resultados Raspberry/       Resultados que midió la Raspberry Pi (resultados.csv de cada serie)
```

Las fotos de los ensayos no se incluyen por su tamaño (unos 15 MB cada una), salvo un par de ejemplo con la cámara a 1 m: `Pruebas 10-11/D100/R1/D100_R1_P1_000kg_a.png` (sin carga) y `D100_R1_P6_250kg_a.png` (250 kg).

## Instalación

**En una computadora** (probado con Python 3.13 en Windows):

```
pip install -r requirements.txt
```

**En la Raspberry Pi** (Raspberry Pi OS), con los paquetes del sistema:

```
sudo apt install python3-opencv python3-matplotlib
```

Las fotos se toman con `rpicam-still`, que viene con Raspberry Pi OS.

## Prueba rápida

Con el par de ejemplo, sin configurar nada:

```
python zncc.py
```

Muestra la plantilla, la zona de búsqueda y el mapa de correlación, e imprime:

```
Coeficiente ZNCC máximo: 0.9799
Desplazamiento entero: X=-1, Y=17 píxeles
Desplazamiento en X: -0.545 píxeles
Desplazamiento en Y: 17.358 píxeles
Coeficiente ZNCC tras el refinamiento: 0.9933 (ampliación x20)
Desplazamiento en X: -0.153 mm
Desplazamiento en Y: 4.874 mm
```

`python sift_flann.py` hace lo mismo con SIFT + FLANN (17.524 píxeles con 13 correspondencias consistentes). Un desplazamiento en Y positivo es hacia abajo.

## Programas del sistema

### `roi.py`: regiones de interés

Sobre la foto de referencia de un montaje se marca, con el ratón, la región de cada *target*: `LVDT` (*target* de la viga junto al sensor de referencia), `Centro`, `Cuerpo` (cuerpo del LVDT), `Fijo` (*target* fijo para compensar movimientos de la cámara) y `Cajas`. Cada región se marca en dos pasos: primero de forma aproximada sobre la imagen reducida y luego con precisión sobre una ampliación. Se confirma con Enter o Espacio, y con C se omite una región. Para ZNCC, el recuadro debe ajustarse al contorno del *target*.

```
python roi.py ruta/D100_montaje.png 1.0
```

El segundo argumento es la distancia aproximada de la cámara a la viga, en metros. Guarda `rois.json` y una imagen de control `control_rois.jpg` junto a la foto.

### `factor_escala.py`: factor de escala

Mide el alto en píxeles de cada *target* (`LVDT`, `Centro` y `Cuerpo`) y calcula su factor de escala como `L_real / alto`, con `L_real` = 28.4 mm, el lado medido del *target* impreso. El alto se mide entre los centros de los cuadros oscuros de arriba y de abajo: el centro de un cuadro no cambia aunque el cuadro se vea más grande por la impresión o el desenfoque.

```
python factor_escala.py ruta/rois.json
```

No hace falta dar clics. En cada *target* muestra las líneas medidas; Enter acepta y M permite marcar las cuatro esquinas a mano. Escribe las escalas en el mismo `rois.json` (`escalas_regiones`). El *target* fijo no necesita escala, porque su movimiento se resta en píxeles.

### `zncc.py` y `sift_flann.py`: algoritmos de medición

Cada uno contiene la función de medición (`medir_zncc` y `medir_sift`), que usa `medir.py`, y un ejemplo que se ejecuta con un par de fotos y una región definidos en el bloque `CONFIGURACIÓN` del inicio del archivo.

```python
import cv2
from zncc import medir_zncc

ref = cv2.imread("referencia.png", cv2.IMREAD_GRAYSCALE)
nueva = cv2.imread("nueva.png", cv2.IMREAD_GRAYSCALE)
r = medir_zncc(ref, nueva, [2341, 1548, 104, 104])   # región [x, y, ancho, alto]
print(r["dy"], r["coef"])                            # desplazamiento vertical (px) y coeficiente ZNCC
```

Parámetros principales:

| Algoritmo | Parámetro | Valor |
| --- | --- | --- |
| ZNCC | Zona de búsqueda | ±60 píxeles |
| ZNCC | Coeficiente mínimo | 0.80 |
| ZNCC | Ampliación para el refinamiento subpíxel | 20 |
| SIFT + FLANN | Prueba de razón de Lowe | 0.5 |
| SIFT + FLANN | Umbral de RANSAC | 5 píxeles |
| SIFT + FLANN | Correspondencias mínimas | 10 |

SIFT + FLANN no es determinista: FLANN y RANSAC usan números aleatorios, así que repetir la misma medición puede cambiar el resultado en algunas centésimas de píxel.

### `captura.py`: captura en la Raspberry Pi

Toma las fotos de un ensayo con exposición, ganancia y balance de blancos fijos, en PNG y a resolución completa. Se usa por SSH y no abre ventanas.

```
python3 captura.py exposicion        # 1. Mide la exposición automática y guarda los ajustes fijos
python3 captura.py D100              # 2. Foto del montaje, 10 fotos sin carga y escalones de carga
python3 captura.py D100 estabilidad  #    (opcional) 5 fotos quieto y 5 caminando cerca, para revisar el montaje
```

En el modo de montaje, el programa pide Enter antes de cada paso (sin carga, 50, 100, 150, 200 y 250 kg y descarga), toma dos fotos por paso y repite todo tres veces (R1 a R3). Con `r` repite el paso anterior. Las fotos que ya existen no se vuelven a tomar, así que si se corta la conexión basta con ejecutar de nuevo el mismo comando. Las fotos quedan así:

```
~/tfg/fotos/D100/
├── D100_montaje.png             Foto de referencia para roi.py y factor_escala.py
├── registro_fotos.csv           Hora y ajustes de cada foto
├── ruido/D100_ruido_01.png ...  Viga sin carga
└── R1/D100_R1_P2_050kg_a.png    Repetición 1, paso 2 (50 kg), primera foto
```

### `medir.py`: medición de un ensayo

Compara cada foto de una carpeta con la primera (la referencia) en todas las regiones de `rois.json`, con ZNCC y SIFT + FLANN, y agrega una fila por foto a `resultados.csv` en esa carpeta. Busca `rois.json` en la carpeta o en la superior, así que sirve para cada serie de un montaje. Las fotos que ya están en el CSV no se vuelven a medir; con `seguir = True` en la configuración, queda esperando fotos nuevas.

```
python3 medir.py ~/tfg/fotos/D100/R1
```

Columnas principales del CSV:

- `zncc_<región>_dy_px` y `sift_<región>_dy_px`: desplazamiento vertical de cada *target*, en píxeles.
- `zncc_viga_mm`: desplazamiento de la viga en mm, restando el *target* fijo.
- `zncc_subida_mm`: subida del cuerpo del LVDT.
- `zncc_viga_mas_subida_mm`: desplazamiento comparable con el LVDT, cuyo soporte se mueve con la carga.

### Flujo de un ensayo completo

1. Montar la cámara frente a la viga, enfocar y bloquear el enfoque.
2. `captura.py exposicion` y luego `captura.py <montaje>`.
3. `roi.py` sobre `<montaje>_montaje.png`, para marcar las regiones.
4. `factor_escala.py <montaje>/rois.json`, para calcular las escalas.
5. `medir.py` sobre cada carpeta de fotos (`ruido`, `R1`, `R2`, `R3`).

## Análisis de resultados (`graficas_informe/`)

Los cálculos del Capítulo 4 y de los apéndices del informe están en dos libros de Excel, con fórmulas:

- `Cálculos pruebas celular.xlsx`: pruebas con el teléfono celular (Sección 4.1 y Apéndice A).
- `Cálculos pruebas Raspberry.xlsx`: pruebas con el sistema completo (Sección 4.2 y Apéndice B).

A partir de los desplazamientos en píxeles, cada libro los convierte a milímetros, resta el *target* fijo, corrige la subida del soporte del LVDT, los compara con las lecturas del LVDT y calcula las métricas del informe. La hoja Resultados reúne esos valores.

Los desplazamientos en píxeles de las pruebas con el celular se midieron con los scripts de Python de la misma carpeta (`ubicar_targets.py`, `medir_escalas.py` y `procesar.py`), que necesitan las fotos originales. Los de la Raspberry Pi son los `resultados.csv` de `Resultados Raspberry/`. `graficas_informe/README.md` describe cada paso.

## Autor

Jesús Jafet Soto Benavides, Escuela de Ingeniería Electrónica, Tecnológico de Costa Rica.
