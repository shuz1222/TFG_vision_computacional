# Medición de un ensayo completo: compara cada foto de una carpeta con la foto de referencia, en todas
# las regiones de rois.json, con ZNCC (función de zncc.py) y SIFT + FLANN (función de sift_flann.py), y
# guarda los desplazamientos en resultados.csv dentro de esa carpeta.
#
# - La foto de referencia es la primera de la carpeta (la más antigua, o la primera por nombre).
# - rois.json (de roi.py y factor_escala.py) se busca en la carpeta y, si no está, en la carpeta superior,
#   de modo que un mismo montaje puede tener una subcarpeta por serie o repetición.
# - Las fotos que ya están en resultados.csv no se vuelven a medir, así que se puede ejecutar después de
#   cada foto. Con seguir = True queda esperando fotos nuevas y las mide al llegar (Ctrl+C para salir).
#
# Uso:  python3 medir.py                     (usa la carpeta de la configuración)
#       python3 medir.py ~/tfg/fotos/r1      (usa esa carpeta)
import os
import sys
import csv
import json
import time
import datetime
import cv2
from zncc import medir_zncc
from sift_flann import medir_sift

# CONFIGURACIÓN

carpeta = os.path.expanduser("~/tfg/fotos")
algoritmos = ("zncc", "sift")         # Algoritmos que se aplican
ordenar_por = "fecha"                 # "fecha" (orden de captura) o "nombre"
seguir = False                        # True = esperar fotos nuevas y medirlas al llegar

# ZNCC (mismos valores que zncc.py y la Tabla de parámetros del informe)
margen_busqueda = 60
umbral_zncc = 0.80
factor_interpolacion = 20

# SIFT + FLANN (mismos valores que sift_flann.py)
umbral_ratio_lowe = 0.5
umbral_ransac = 5.0
minimo_correspondencias = 10
# El ROI de SIFT es una ventana fija: se extiende (arriba, abajo), en mm, para que el target no salga de
# ella al desplazarse. Los targets de la viga bajan con la carga y el del cuerpo del LVDT sube.
extension_sift_mm = {"LVDT": (0.0, 8.0), "Centro": (0.0, 8.0), "Cuerpo": (2.5, 0.0)}

# Cada target se convierte a mm con su propia escala ("escalas_regiones" de rois.json, de factor_escala.py).
# Con un rois.json antiguo sin ellas, se usa la del LVDT y, para el target del cuerpo del LVDT (más lejos de
# la cámara), esa misma corregida suponiendo esta profundidad
profundidad_cuerpo_m = 0.04

EXTENSIONES = (".png", ".jpg", ".jpeg")
ARCHIVO_CSV = "resultados.csv"

if len(sys.argv) > 1:
    carpeta = os.path.expanduser(sys.argv[1])
carpeta = os.path.abspath(carpeta)


# Número para la consola ('--' si no hay medición).
def fmt(v, dec=3):
    return "--" if v is None else f"{v:.{dec}f}"


# Número para resultados.csv (celda vacía si no hay medición).
def celda(v, dec=4):
    return "" if v is None else f"{v:.{dec}f}"


def listar_fotos():
    fotos = [f for f in os.listdir(carpeta)
             if f.lower().endswith(EXTENSIONES) and not f.startswith("control_")]
    if ordenar_por == "fecha":
        fotos.sort(key=lambda f: (os.path.getmtime(os.path.join(carpeta, f)), f))
    else:
        fotos.sort()
    return fotos


def resta(a, b):
    return None if a is None or b is None else a - b


# 1. CARGAR rois.json
ruta_json = next((p for p in (os.path.join(carpeta, "rois.json"), os.path.join(os.path.dirname(carpeta), "rois.json"))
                  if os.path.exists(p)), None)
if ruta_json is None:
    print(f"Error: no hay rois.json en {carpeta} ni en la carpeta superior. Ejecuta primero roi.py.")
    exit()
with open(ruta_json, encoding="utf-8") as f:
    config_rois = json.load(f)
rois = config_rois["regiones"]
s = config_rois.get("factor_escala")
D = config_rois.get("distancia_camara_m", 1.0)
escalas_medidas = config_rois.get("escalas_regiones", {})
escalas = {}
if s is not None:
    escalas = {"LVDT": escalas_medidas.get("LVDT", s), "Centro": escalas_medidas.get("Centro", s),
               "Cuerpo": escalas_medidas.get("Cuerpo", s * (D + profundidad_cuerpo_m) / D)}

print(f"Regiones ({ruta_json}): {', '.join(rois)}")
if s is None:
    print("Advertencia: rois.json no tiene factor de escala (factor_escala.py); se reporta solo en píxeles.")
else:
    print("Escalas (mm/px): " + ", ".join(
        f"{n} {v:.4f}" + ("" if n in escalas_medidas or n == "LVDT" else
                          f" (supuesta a {100 * profundidad_cuerpo_m:.0f} cm detrás)" if n == "Cuerpo" else " (la del LVDT)")
        for n, v in escalas.items() if n in rois))
if "Fijo" not in rois:
    print("Advertencia: no hay región 'Fijo'; los desplazamientos en mm no se compensan con el target fijo.")

# Escala solo para dimensionar el ROI de SIFT: la medida o, si falta, la estimada del lente de 6 mm
s_ext = s if s is not None else 0.258 * D
rois_sift = {}
for nombre, (x, y, w, h) in rois.items():
    arriba, abajo = (round(mm / s_ext) for mm in extension_sift_mm.get(nombre, (0.0, 0.0)))
    rois_sift[nombre] = [x, max(0, y - arriba), w, h + min(y, arriba) + abajo]


# 2. COLUMNAS DE resultados.csv
columnas = ["foto", "hora_archivo", "referencia"]
for alg in algoritmos:
    calidad = "coef" if alg == "zncc" else "inliers"
    for nombre in rois:
        columnas += [f"{alg}_{nombre}_dx_px", f"{alg}_{nombre}_dy_px", f"{alg}_{nombre}_{calidad}", f"{alg}_{nombre}_t_s"]
for alg in algoritmos:
    columnas += [f"{alg}_viga_mm", f"{alg}_centro_mm", f"{alg}_subida_mm", f"{alg}_viga_mas_subida_mm"]
columnas += ["t_lectura_s", "t_total_s"]

ruta_csv = os.path.join(carpeta, ARCHIVO_CSV)
medidas = set()
if os.path.exists(ruta_csv):
    with open(ruta_csv, newline="", encoding="utf-8") as f:
        lector = csv.DictReader(f)
        if lector.fieldnames != columnas:
            print(f"Error: {ruta_csv} tiene otras columnas (¿cambiaron las regiones o los algoritmos?). "
                  "Renómbralo o bórralo y vuelve a ejecutar.")
            exit()
        medidas = {fila["foto"] for fila in lector}


# Mide una foto en todas las regiones. Devuelve la fila de resultados.csv y un resumen para la
# consola, o (None, None) si la foto no se pudo leer.
def medir_foto(foto, img_ref):
    t0 = time.perf_counter()
    img_new = cv2.imread(os.path.join(carpeta, foto), cv2.IMREAD_GRAYSCALE)
    t_lectura = time.perf_counter() - t0
    if img_new is None or img_new.shape != img_ref.shape:
        return None, None
    hora = datetime.datetime.fromtimestamp(os.path.getmtime(os.path.join(carpeta, foto)))
    fila = dict(foto=foto, hora_archivo=hora.strftime("%Y-%m-%d %H:%M:%S"), referencia=referencia)
    resumen = {}
    for alg in algoritmos:
        dy = {}
        for nombre in rois:
            t1 = time.perf_counter()
            if alg == "zncc":
                r = medir_zncc(img_ref, img_new, rois[nombre], margen_busqueda, umbral_zncc, factor_interpolacion)
                fila[f"zncc_{nombre}_coef"] = celda(r["coef"])
            else:
                r = medir_sift(img_ref, img_new, rois_sift[nombre], umbral_ratio_lowe, umbral_ransac,
                               minimo_correspondencias)
                fila[f"sift_{nombre}_inliers"] = r["inliers"]
            dy[nombre] = r["dy"]
            fila[f"{alg}_{nombre}_dx_px"] = celda(r["dx"])
            fila[f"{alg}_{nombre}_dy_px"] = celda(r["dy"])
            fila[f"{alg}_{nombre}_t_s"] = celda(time.perf_counter() - t1, 3)

        # Desplazamientos en mm: compensación con el target fijo y corrección de la subida del soporte del LVDT
        viga = centro = subida = corr = None
        if s is not None:
            fijo = dy["Fijo"] if "Fijo" in rois else 0.0
            d_viga, d_centro, d_cuerpo = (resta(dy.get(n), fijo) for n in ("LVDT", "Centro", "Cuerpo"))
            # Cada target con su escala; el cuerpo del LVDT sube con la carga (signo contrario)
            viga = None if d_viga is None else d_viga * escalas["LVDT"]
            centro = None if d_centro is None else d_centro * escalas["Centro"]
            subida = None if d_cuerpo is None else -d_cuerpo * escalas["Cuerpo"]
            corr = None if viga is None or subida is None else viga + subida
        fila[f"{alg}_viga_mm"] = celda(viga)
        fila[f"{alg}_centro_mm"] = celda(centro)
        fila[f"{alg}_subida_mm"] = celda(subida)
        fila[f"{alg}_viga_mas_subida_mm"] = celda(corr)
        resumen[alg] = (viga, subida, corr, dy.get("LVDT"))
    fila["t_lectura_s"] = celda(t_lectura, 3)
    fila["t_total_s"] = celda(time.perf_counter() - t0, 3)
    return fila, resumen


def mostrar(fila, resumen):
    partes = []
    for alg, (viga, subida, corr, dy_px) in resumen.items():
        if s is None:
            partes.append(f"{alg.upper()}: viga {fmt(dy_px)} px")
        else:
            partes.append(f"{alg.upper()}: viga {fmt(viga)} mm, subida {fmt(subida)} mm, viga + subida {fmt(corr)} mm")
    print(f"{fila['foto']}: " + " | ".join(partes) + f" | {fila['t_total_s']} s", flush=True)


# 3. MEDIR LAS FOTOS (y, con seguir = True, las que vayan llegando)
referencia, img_ref = None, None
try:
    while True:
        fotos = listar_fotos()
        if seguir:
            # Solo fotos terminadas de guardar: sin cambios en los últimos 3 s
            fotos = [f for f in fotos if time.time() - os.path.getmtime(os.path.join(carpeta, f)) > 3]
        if referencia is None and fotos:
            referencia = fotos[0]
            img_ref = cv2.imread(os.path.join(carpeta, referencia), cv2.IMREAD_GRAYSCALE)
            if img_ref is None:
                print(f"Error: no se pudo leer la foto de referencia {referencia}.")
                exit()
            if referencia != config_rois.get("referencia"):
                print(f"Nota: las regiones se marcaron en {config_rois.get('referencia')}; "
                      f"la referencia de esta carpeta es {referencia}.")
            print(f"Referencia: {referencia}\n")
        pendientes = [f for f in fotos if f != referencia and f not in medidas]
        for foto in pendientes:
            fila, resumen = medir_foto(foto, img_ref)
            if fila is None:
                print(f"{foto}: no se pudo leer o no tiene la resolución de la referencia; se omite.")
                medidas.add(foto)
                continue
            mostrar(fila, resumen)
            nuevo = not os.path.exists(ruta_csv)
            with open(ruta_csv, "a", newline="", encoding="utf-8") as f:
                escritor = csv.DictWriter(f, fieldnames=columnas)
                if nuevo:
                    escritor.writeheader()
                escritor.writerow(fila)
            medidas.add(foto)
        if not seguir:
            break
        time.sleep(2)
except KeyboardInterrupt:
    pass

if referencia is None:
    print("No hay fotos en la carpeta.")
else:
    print(f"\nResultados en {ruta_csv}")
