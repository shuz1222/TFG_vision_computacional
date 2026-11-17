# Ubica en la foto de referencia de cada serie del 26/10: los dos targets de la viga, el target del cuerpo
# del LVDT, el target de la repisa y una zona de textura natural de la repisa (cajas), para comparar.
import os, sys, json
import numpy as np, cv2
aqui = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, aqui)
from series import SERIES, CARP, RAIZ

LADO_VIGA, LADO_REPISA = 28.4, 66.3
# tablero del target (mismo diseño impreso) tomado de una foto del 19/10
tpl = cv2.imread(os.path.join(RAIZ, "OpenCamera", "ruido_0_5_1.jpg"), 0)[1751:1924, 2028:2203]
# cajas de la repisa a la izquierda del target de la repisa (textura natural, como la "repisa" del 19/10)
tpl_cajas = cv2.imread(os.path.join(RAIZ, "Pruebas 21-10", "escalon_0_5_r1_0kg_1.jpg"), 0)[925:1025, 1190:1500]


def buscar(img, t0, escalas, n=1, zona=None):
    x0, y0 = (0, 0)
    if zona:
        x0, y0, x1, y1 = zona; img = img[y0:y1, x0:x1]
    mejores = []
    for f in escalas:
        t = cv2.resize(t0, None, fx=f, fy=f, interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_CUBIC)
        res = cv2.matchTemplate(img, t, cv2.TM_CCOEFF_NORMED)
        for _ in range(n + 2):
            _, v, _, (x, y) = cv2.minMaxLoc(res)
            mejores.append((v, x + x0, y + y0, t.shape[1], t.shape[0], f))
            res[max(0, y - t.shape[0]):y + t.shape[0], max(0, x - t.shape[1]):x + t.shape[1]] = -1
    mejores.sort(reverse=True)
    elegidos = []
    for m in mejores:
        if all(abs(m[1] - e[1]) > e[3] or abs(m[2] - e[2]) > e[4] for e in elegidos):
            elegidos.append(m)
        if len(elegidos) == n:
            break
    return elegidos


# Bordes del tablero (cuadros oscuros) dentro de una zona, con umbral de Otsu.
def tablero(img, x, y, w, h):
    pad = int(0.08 * w)
    x0, y0 = max(0, x - pad), max(0, y - pad)
    c = img[y0:y + h + pad, x0:x + w + pad]
    t, _ = cv2.threshold(c, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    osc = c < t
    cols = np.where(osc.mean(0) > 0.25)[0]; fils = np.where(osc.mean(1) > 0.25)[0]
    return x0 + cols[0], y0 + fils[0], cols[-1] - cols[0] + 1, fils[-1] - fils[0] + 1


def roi_tablero(img, m, lado, mg=4):
    bx, by, bw, bh = tablero(img, m[1], m[2], m[3], m[4])
    return dict(roi=[int(bx - mg), int(by - mg), int(bw + 2 * mg), int(bh + 2 * mg)], lado_px=[int(bw), int(bh)],
                escala=lado / np.mean([bw, bh]), coincidencia=round(float(m[0]), 3))


COLORES = {"LVDT": (0, 200, 0), "Centro": (0, 0, 255), "Cuerpo": (255, 0, 255), "Repisa": (255, 128, 0), "Cajas": (0, 200, 255)}
salida, vistas = {}, []
for nombre, s in SERIES.items():
    img = cv2.imread(os.path.join(CARP, s["ref"]), 0)
    f0 = 1.0 if s["dist"] == 0.5 else 0.5
    tres = buscar(img, tpl, np.linspace(0.8, 1.15, 15) * f0, n=3)
    tres.sort(key=lambda m: m[2])                     # el de más arriba es el del cuerpo del LVDT
    viga = sorted(tres[1:], key=lambda m: m[1])       # izquierda = plano del LVDT, derecha = centro
    info = {"LVDT": roi_tablero(img, viga[0], LADO_VIGA), "Centro": roi_tablero(img, viga[1], LADO_VIGA),
            "Cuerpo": roi_tablero(img, tres[0], LADO_VIGA)}
    rep = buscar(img, tpl, np.linspace(0.25, 0.6, 15), n=1, zona=(1300, 750, 1950, 1300))[0]
    info["Repisa"] = roi_tablero(img, rep, LADO_REPISA)
    caj = buscar(img, tpl_cajas, np.linspace(0.75, 1.1, 15), n=1)[0]
    info["Cajas"] = dict(roi=[int(caj[1]), int(caj[2]), int(caj[3]), int(caj[4])], escala=None, coincidencia=round(float(caj[0]), 3))
    salida[nombre] = info
    print(f"{nombre:20s} " + " | ".join(f"{k}: {v['roi']} ({v['coincidencia']})" + (f" lado {np.mean(v['lado_px']):.1f}" if 'lado_px' in v else "") for k, v in info.items()))
    col = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    for k, c in COLORES.items():
        x, y, w, h = info[k]["roi"]
        cv2.rectangle(col, (x, y), (x + w, y + h), c, 6)
        cv2.putText(col, k, (x, y - 15), cv2.FONT_HERSHEY_SIMPLEX, 2.0, c, 5)
    cv2.putText(col, nombre, (60, 150), cv2.FONT_HERSHEY_SIMPLEX, 4, (0, 255, 255), 8)
    vistas.append(cv2.resize(col, (832, 624), interpolation=cv2.INTER_AREA))
    # recorte de control de cada ROI
    tiras = []
    for k in COLORES:
        x, y, w, h = info[k]["roi"]
        c = cv2.cvtColor(img[y:y + h, x:x + w], cv2.COLOR_GRAY2BGR)
        c = cv2.resize(c, (int(w * 200 / h), 200), interpolation=cv2.INTER_CUBIC)
        tiras += [c, np.full((200, 8, 3), 255, np.uint8)]
    archivo = "recortes_" + nombre.replace(" ", "_").replace(",", "").replace("á", "a") + ".jpg"
    cv2.imwrite(os.path.join(aqui, "control", archivo), np.hstack(tiras))

json.dump(salida, open(os.path.join(aqui, "datos", "rois.json"), "w"), indent=1, default=float)
filas = [np.hstack(vistas[i:i + 3] + [np.zeros_like(vistas[0])] * (3 - len(vistas[i:i + 3]))) for i in range(0, len(vistas), 3)]
cv2.imwrite(os.path.join(aqui, "control", "rois_todas.jpg"), np.vstack(filas), [cv2.IMWRITE_JPEG_QUALITY, 80])
