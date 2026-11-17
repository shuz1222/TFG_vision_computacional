# Marca con el ratón, sobre la foto de referencia de un montaje, las regiones de interés (ROI) de cada
# target, imprime sus coordenadas en la imagen de resolución completa y las guarda en rois.json, en la
# misma carpeta de la foto. Ese archivo lo usan factor_escala.py y medir.py.
#
# Cada región se marca en dos pasos: primero de forma aproximada sobre la imagen reducida y luego, con
# precisión, sobre una ampliación de esa zona. Para ZNCC el recuadro debe ajustarse al contorno del target.
#
# Uso:  python roi.py                          (usa ruta_imagen_ref y distancia_camara_m de la configuración)
#       python roi.py ruta/de/la/foto.png
#       python roi.py ruta/de/la/foto.png 2.0    (además, la distancia de la cámara a la viga en m)
import os
import sys
import json
import cv2

# CONFIGURACIÓN

ruta_imagen_ref = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Pruebas 10-11", "D100", "R1",
                               "D100_R1_P1_000kg_a.png")   # Por defecto, la foto de ejemplo a 1 m
regiones = ["LVDT", "Centro", "Cuerpo", "Fijo", "Cajas"]  # Orden en que se piden (se puede omitir cualquiera)
distancia_camara_m = 1.0   # Distancia de la cámara a la viga; la usa medir.py para la escala del cuerpo del LVDT
ancho_max_pantalla = 1280  # Ancho máximo para mostrar la imagen al seleccionar ROI
lado_ampliacion = 700      # Tamaño en pantalla de la zona ampliada del segundo paso

if len(sys.argv) > 1:
    ruta_imagen_ref = sys.argv[1]
if len(sys.argv) > 2:
    distancia_camara_m = float(sys.argv[2])


# Recuadro marcado con el ratón (x, y, w, h); (0, 0, 0, 0) si se cancela con la tecla C.
def seleccionar(ventana, imagen):
    cv2.namedWindow(ventana, cv2.WINDOW_NORMAL)
    roi = cv2.selectROI(ventana, imagen, fromCenter=False, showCrosshair=True)
    cv2.destroyWindow(ventana)
    return roi


# 1. CARGAR IMAGEN DE REFERENCIA
img_ref = cv2.imread(ruta_imagen_ref, cv2.IMREAD_GRAYSCALE)

if img_ref is None:
    print("Error: No se pudo cargar la imagen. Verifica la ruta.")
    exit()

alto_original, ancho_original = img_ref.shape[:2]
escala = min(1.0, ancho_max_pantalla / ancho_original)
img_ref_red = cv2.cvtColor(cv2.resize(img_ref, (int(ancho_original * escala), int(alto_original * escala))),
                           cv2.COLOR_GRAY2BGR)


# 2. SELECCIONAR CADA REGIÓN
print("Para cada región: encierra el target y presiona ENTER o ESPACIO.")
print("Para omitir una región (o el paso de precisión), presiona C.")
rois = {}
for nombre in regiones:
    # Paso 1: selección aproximada sobre la imagen reducida
    print(f"\n{nombre}: selección aproximada")
    x_red, y_red, w_red, h_red = seleccionar(f"{nombre} - seleccion aproximada (C = omitir)", img_ref_red)
    if w_red == 0 or h_red == 0:
        print(f"{nombre}: omitida")
        continue
    x0, y0 = int(x_red / escala), int(y_red / escala)
    w0, h0 = int(w_red / escala), int(h_red / escala)

    # Paso 2: selección precisa sobre una ampliación de la zona marcada
    borde = max(w0, h0) // 2 + 10
    zx0, zy0 = max(0, x0 - borde), max(0, y0 - borde)
    zx1, zy1 = min(ancho_original, x0 + w0 + borde), min(alto_original, y0 + h0 + borde)
    zona = img_ref[zy0:zy1, zx0:zx1]
    amp = lado_ampliacion / max(zona.shape[:2])
    zona_amp = cv2.resize(zona, None, fx=amp, fy=amp, interpolation=cv2.INTER_NEAREST)
    print(f"{nombre}: selección precisa (ajusta el recuadro al contorno del target)")
    xa, ya, wa, ha = seleccionar(f"{nombre} - seleccion precisa (C = usar la aproximada)", zona_amp)
    if wa > 0 and ha > 0:
        x, y = zx0 + round(xa / amp), zy0 + round(ya / amp)
        w, h = round(wa / amp), round(ha / amp)
    else:
        x, y, w, h = x0, y0, w0, h0

    rois[nombre] = [int(x), int(y), int(w), int(h)]
    print(f"ROI {nombre} (imagen original): x={x}, y={y}, w={w}, h={h}")
    cv2.rectangle(img_ref_red, (int(x * escala), int(y * escala)), (int((x + w) * escala), int((y + h) * escala)),
                  (0, 200, 0), 2)
    cv2.putText(img_ref_red, nombre, (int(x * escala), int(y * escala) - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 0), 2)

if not rois:
    print("Error: No se seleccionó ningún ROI.")
    exit()


# 3. GUARDAR rois.json E IMAGEN DE CONTROL
carpeta = os.path.dirname(os.path.abspath(ruta_imagen_ref))
datos = dict(referencia=os.path.basename(ruta_imagen_ref), distancia_camara_m=distancia_camara_m,
             regiones=rois, factor_escala=None)
ruta_json = os.path.join(carpeta, "rois.json")
with open(ruta_json, "w", encoding="utf-8") as f:
    json.dump(datos, f, indent=1, ensure_ascii=False)
ruta_control = os.path.join(carpeta, "control_rois.jpg")
cv2.imwrite(ruta_control, img_ref_red)

print(f"\nDistancia de la cámara a la viga: {distancia_camara_m} m")
print(f"Regiones guardadas en {ruta_json}")
print(f"Imagen de control: {ruta_control}")
print("Siguiente paso: factor_escala.py con este rois.json, para obtener el factor de escala.")

cv2.imshow("Regiones marcadas (cualquier tecla para cerrar)", img_ref_red)
cv2.waitKey(0)
cv2.destroyAllWindows()
