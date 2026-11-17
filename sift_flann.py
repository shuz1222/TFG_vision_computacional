import os
import cv2
import numpy as np
import matplotlib.pyplot as plt

# CONFIGURACIÓN
# Por defecto, el par de ejemplo: cámara a 1 m, sin carga (referencia) y con 250 kg.

carpeta_ejemplo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Pruebas 10-11", "D100", "R1")
ruta_imagen_ref = os.path.join(carpeta_ejemplo, "D100_R1_P1_000kg_a.png")
ruta_imagen_nueva = os.path.join(carpeta_ejemplo, "D100_R1_P6_250kg_a.png")

# ROI fijo (de roi.py), con margen para que el target no salga de él al desplazarse
# (el del ejemplo es el del target, extendido 8 mm hacia abajo, como en medir.py)
x = 2341
y = 1548
w = 104
h = 133

umbral_ratio_lowe = 0.5        # Prueba de razón de Lowe
umbral_ransac = 5.0            # Error de reproyección máximo de un inlier, en píxeles
minimo_correspondencias = 10   # Con menos correspondencias no se reporta medición
factor_escala = 0.2808         # mm/píxel (de factor_escala.py); None = reportar solo en píxeles


# Desplazamiento del contenido del ROI (x, y, w, h) entre dos imágenes en escala de grises.
#
# Aplica los pasos 2 a 7 de este programa y devuelve un diccionario. Si la medición no es válida,
# 'dx' y 'dy' son None y 'motivo' explica por qué. La usan este programa y medir.py.
def medir_sift(img_ref, img_new, roi, umbral_ratio_lowe=0.5, umbral_ransac=5.0, minimo_correspondencias=10):
    x, y, w, h = roi

    # 2. RECORTAR AMBAS IMÁGENES AL ROI
    img_ref_roi = img_ref[y:y+h, x:x+w]
    img_new_roi = img_new[y:y+h, x:x+w]

    # 3. PREPROCESAMIENTO: CLAHE, ecualización del histograma y filtro gaussiano
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    img_ref_roi = cv2.GaussianBlur(cv2.equalizeHist(clahe.apply(img_ref_roi)), (5, 5), 0)
    img_new_roi = cv2.GaussianBlur(cv2.equalizeHist(clahe.apply(img_new_roi)), (5, 5), 0)

    # 4. SIFT
    sift = cv2.SIFT_create()
    kp_ref, des_ref = sift.detectAndCompute(img_ref_roi, None)
    kp_new, des_new = sift.detectAndCompute(img_new_roi, None)

    r = dict(dx=None, dy=None, inliers=0, buenos=0, matches_totales=None, motivo=None,
             puntos_ref=len(kp_ref), puntos_new=len(kp_new), img_ref_roi=img_ref_roi, img_new_roi=img_new_roi,
             kp_ref=kp_ref, kp_new=kp_new, inlier_matches=[])

    if len(kp_ref) < 2 or len(kp_new) < 2:
        r["motivo"] = "No se reporta medición: no hay suficientes puntos SIFT en el ROI."
        return r

    # 5. FLANN MATCHER
    FLANN_INDEX_KDTREE = 1
    flann = cv2.FlannBasedMatcher(dict(algorithm=FLANN_INDEX_KDTREE, trees=5), dict(checks=50))
    matches = flann.knnMatch(des_ref, des_new, k=2)

    # 6. PRUEBA DE RAZÓN DE LOWE
    good_matches = [m for m, n in (par for par in matches if len(par) == 2)
                    if m.distance < umbral_ratio_lowe * n.distance]
    r.update(matches_totales=len(matches), buenos=len(good_matches))

    # 7. RANSAC Y CÁLCULO DE DESPLAZAMIENTO
    # La homografía solo separa inliers de outliers; el desplazamiento es el promedio de los inliers.
    if len(good_matches) < minimo_correspondencias:
        r["motivo"] = f"No se reporta medición: hay menos de {minimo_correspondencias} correspondencias."
        return r

    src_pts = np.float32([kp_ref[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp_new[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

    M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, umbral_ransac)

    if M is None:
        r["motivo"] = "No se reporta medición: no se pudo estimar la homografía."
        return r

    es_inlier = mask.ravel() == 1
    desplazamientos = (dst_pts - src_pts)[es_inlier]
    r.update(dx=float(desplazamientos[:, 0, 0].mean()), dy=float(desplazamientos[:, 0, 1].mean()),
             inliers=len(desplazamientos), inlier_matches=[m for m, v in zip(good_matches, es_inlier) if v])
    return r


if __name__ == "__main__":
    # 1. CARGAR IMÁGENES
    img_ref = cv2.imread(ruta_imagen_ref, cv2.IMREAD_GRAYSCALE)
    img_new = cv2.imread(ruta_imagen_nueva, cv2.IMREAD_GRAYSCALE)

    if img_ref is None or img_new is None:
        print("Error: No se pudieron cargar las imágenes. Verifica las rutas.")
        exit()

    print(f"ROI: x={x}, y={y}, w={w}, h={h}")

    # 2 a 7. ROI, PREPROCESAMIENTO, SIFT, FLANN, PRUEBA DE RAZÓN Y RANSAC (función medir_sift)
    res = medir_sift(img_ref, img_new, (x, y, w, h), umbral_ratio_lowe, umbral_ransac, minimo_correspondencias)

    print(f"Puntos SIFT en referencia: {res['puntos_ref']}")
    print(f"Puntos SIFT en nueva: {res['puntos_new']}")

    if res["matches_totales"] is None:
        print(res["motivo"])
        exit()

    print(f"Matches totales: {res['matches_totales']}")
    print(f"Buenos matches (filtrados): {res['buenos']}")

    if res["dx"] is None:
        print(res["motivo"])
    else:
        dx, dy = res["dx"], res["dy"]
        print(f"\nDesplazamiento en X: {dx:.3f} píxeles")
        print(f"Desplazamiento en Y: {dy:.3f} píxeles")
        print(f"Puntos usados (inliers): {res['inliers']} de {res['buenos']}")

        if factor_escala is not None:
            print(f"Desplazamiento en X: {dx * factor_escala:.3f} mm")
            print(f"Desplazamiento en Y: {dy * factor_escala:.3f} mm")

    # 8. VISUALIZACIÓN DE INLIERS
    if res["inlier_matches"]:
        img_inliers = cv2.drawMatches(res["img_ref_roi"], res["kp_ref"], res["img_new_roi"], res["kp_new"],
                                      res["inlier_matches"], None, flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)

        plt.figure(figsize=(12, 6))
        plt.imshow(img_inliers)
        plt.title(f"Inliers: {len(res['inlier_matches'])} de {res['buenos']} matches")
        plt.axis('off')
        plt.show()
