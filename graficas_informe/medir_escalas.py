# Mide el alto de cada target en la foto de referencia de cada serie del 26/10 con el mismo método que
# factor_escala.py usa en la Raspberry: medir_bordes ubica el tablero a partir de la ROI de datos/rois.json, y
# medir_centros mide la distancia entre los centros de los cuadros oscuros de arriba y de abajo. Resultado: datos/escalas_centros.json, con los altos que usa la hoja Escalas de "Cálculos pruebas celular.xlsx".
import os, sys, json
import cv2
aqui = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, aqui)
sys.path.insert(0, os.path.dirname(aqui))
from series import SERIES, CARP
from factor_escala import medir_bordes, medir_centros

TARGETS = ("LVDT", "Centro", "Cuerpo", "Repisa")
rois = json.load(open(os.path.join(aqui, "datos", "rois.json")))
salida = {}
for nombre, s in SERIES.items():
    gris = cv2.imread(os.path.join(CARP, s["ref"]), cv2.IMREAD_GRAYSCALE)
    salida[nombre] = {}
    for t in TARGETS:
        x, y, w, h = rois[nombre][t]["roi"]
        # la ROI de ubicar_targets.py tiene 4 px de margen por lado alrededor del tablero
        b = medir_bordes(gris, x + w / 2, y + h / 2, (w + h) / 2 - 8)
        c = medir_centros(gris, b) if b else None
        if c is None:
            raise SystemExit(f"{nombre}, {t}: no se encontraron los centros de los cuadros oscuros")
        salida[nombre][t] = dict(alto_px=c["alto"], ancho_px=c["ancho"], alto_bordes_px=b["alto"])
        print(f"{nombre:34s} {t:7s} alto {c['alto']:7.2f} px  ancho {c['ancho']:7.2f} px  (borde a borde: {b['alto']:7.2f} px)")
json.dump(salida, open(os.path.join(aqui, "datos", "escalas_centros.json"), "w", encoding="utf-8"), indent=1)
print("Guardado:", os.path.join(aqui, "datos", "escalas_centros.json"))
