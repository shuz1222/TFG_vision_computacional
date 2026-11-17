# Funciones que aplican ZNCC y SIFT + FLANN
# a un par de imágenes y una región, y guardan la figura que genera cada algoritmo.
# Las usa procesar.py; este archivo no se ejecuta solo.
import os, sys, re, io, json, time, contextlib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np, cv2
aqui = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, aqui)
from series import SERIES, CARP, RAIZ

SALIDA = os.path.join(RAIZ, "Resultados visión 26-10", "figuras")
MARGEN_SIFT = {0.5: 45, 1.0: 25}       # extension hacia abajo del ROI de SIFT
DPI = 70

fuente = open(os.path.join(RAIZ, "zncc.py"), encoding="utf-8").read()
fuente = fuente.replace("exit()", "raise SystemExit")
fuente = fuente.replace("# 6. VISUALIZACIÓN", "_t_fin = __import__('time').perf_counter()\n# 6. VISUALIZACIÓN")


def zncc(ref, new, roi, figura, margen=60):
    src = fuente.replace("plt.show()", f"plt.savefig(r'{figura}', dpi={DPI})\nplt.close('all')")
    cfg = dict(ruta_imagen_ref=repr(ref), ruta_imagen_nueva=repr(new),
               x=roi[0], y=roi[1], w=roi[2], h=roi[3], margen_busqueda=margen)
    for k, v in cfg.items():
        src, n = re.subn(rf"(?m)^{k} = [^#\n]*", lambda m: f"{k} = {v} ", src, count=1)
        assert n == 1, k
    buf = io.StringIO(); g = {"__name__": "__main__", "__file__": os.path.join(RAIZ, "zncc.py")}
    t0 = time.perf_counter()
    with contextlib.redirect_stdout(buf):
        try:
            exec(compile(src, "zncc.py", "exec"), g)
        except SystemExit:
            pass
    plt.close("all")
    out = buf.getvalue()
    leer = lambda p: (float(m.group(1)) if (m := re.search(p, out)) else None)
    return dict(dx=leer(r"Desplazamiento en X: ([-\d.]+) píxeles"), dy=leer(r"Desplazamiento en Y: ([-\d.]+) píxeles"),
                coef=leer(r"ZNCC máximo: ([-\d.]+)"), t=(g.get("_t_fin", time.perf_counter()) - t0))


def sift(ref, new, roi, figura):
    t0 = time.perf_counter()
    x, y, w, h = roi
    img_ref = cv2.imread(ref, cv2.IMREAD_GRAYSCALE); img_new = cv2.imread(new, cv2.IMREAD_GRAYSCALE)
    a = img_ref[y:y + h, x:x + w]; b = img_new[y:y + h, x:x + w]
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    a = cv2.GaussianBlur(cv2.equalizeHist(clahe.apply(a)), (5, 5), 0)
    b = cv2.GaussianBlur(cv2.equalizeHist(clahe.apply(b)), (5, 5), 0)
    s = cv2.SIFT_create()
    ka, da = s.detectAndCompute(a, None); kb, db = s.detectAndCompute(b, None)
    res = dict(dx=None, dy=None, inliers=0, buenos=0, puntos_ref=len(ka), puntos_new=len(kb))
    inl = []
    if da is not None and db is not None and len(ka) >= 2 and len(kb) >= 2:
        fl = cv2.FlannBasedMatcher(dict(algorithm=1, trees=5), dict(checks=50))
        good = [m for m, n in (p for p in fl.knnMatch(da, db, k=2) if len(p) == 2) if m.distance < 0.5 * n.distance]
        res["buenos"] = len(good)
        if len(good) >= 10:
            src = np.float32([ka[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
            dst = np.float32([kb[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
            M, mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0)
            if M is not None:
                sel = mask.ravel() == 1
                d = (dst - src)[sel]
                inl = [g for g, v in zip(good, sel) if v]
                if len(d):
                    res.update(dx=float(d[:, 0, 0].mean()), dy=float(d[:, 0, 1].mean()), inliers=len(d))
    res["t"] = time.perf_counter() - t0
    # figura igual a la de sift_flann.py
    plt.figure(figsize=(12, 6))
    if inl:
        im = cv2.drawMatches(a, ka, b, kb, inl, None, flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
        plt.imshow(im); plt.title(f"Inliers: {len(inl)} de {res['buenos']} matches")
    else:
        plt.imshow(np.hstack([a, b]), cmap="gray"); plt.title(f"Sin medición ({res['buenos']} matches)")
    plt.axis("off"); plt.savefig(figura, dpi=DPI); plt.close("all")
    return res


