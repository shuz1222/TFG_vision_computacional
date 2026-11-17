# Corre ZNCC y SIFT + FLANN en todas las series del 26/10/2026
# sobre las cinco regiones, guardando las figuras de cada algoritmo y los resultados numéricos.
import os, sys, json, time
aqui = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, aqui)
import algoritmos as A
from series import SERIES, CARP

rois = json.load(open(os.path.join(aqui, "datos", "rois.json")))
EXTRA_VIGA = {0.5: 45, 1.0: 25}    # SIFT: el ROI de los targets de la viga se extiende hacia abajo (su ventana es fija)
EXTRA_CUERPO = 10                  # SIFT: el ROI del cuerpo del LVDT se extiende hacia arriba
resultados = {}; t0 = time.time()
for nombre, s in SERIES.items():
    carpeta = os.path.join(A.SALIDA, nombre); os.makedirs(carpeta, exist_ok=True)
    ref = os.path.join(CARP, s["ref"]); filas = []
    for foto in s["fotos"]:
        new = os.path.join(CARP, foto); fila = dict(foto=foto)
        for z, info in rois[nombre].items():
            x, y, w, h = info["roi"]
            if z in ("LVDT", "Centro"):
                roi_s = [x, y, w, h + EXTRA_VIGA[s["dist"]]]
            elif z == "Cuerpo":
                roi_s = [x, y - EXTRA_CUERPO, w, h + EXTRA_CUERPO]
            else:
                roi_s = [x, y, w, h]
            base = os.path.join(carpeta, foto[:-4] + "_" + z)
            fila[z] = dict(zncc=A.zncc(ref, new, info["roi"], base + "_ZNCC.png"), sift=A.sift(ref, new, roi_s, base + "_SIFT.png"),
                           roi_sift=roi_s)
        filas.append(fila)
        g = lambda z, a: fila[z][a]["dy"]
        print(f"{nombre:20s} {foto:28s} LVDT Z {g('LVDT', 'zncc')} S {g('LVDT', 'sift')} | Cuerpo Z {g('Cuerpo', 'zncc')} | "
              f"Repisa Z {g('Repisa', 'zncc')} S {g('Repisa', 'sift')} | Cajas Z {g('Cajas', 'zncc')} | {time.time() - t0:5.0f} s", flush=True)
    resultados[nombre] = dict(ref=s["ref"], filas=filas)
    json.dump(resultados, open(os.path.join(aqui, "datos", "resultados.json"), "w"), indent=1, default=float)
print("LISTO", round(time.time() - t0), "s")
