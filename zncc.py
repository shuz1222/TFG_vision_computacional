import os
import cv2
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches

# CONFIGURACIÓN
# Por defecto, el par de ejemplo: cámara a 1 m, sin carga (referencia) y con 250 kg.

carpeta_ejemplo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Pruebas 10-11", "D100", "R1")
ruta_imagen_ref = os.path.join(carpeta_ejemplo, "D100_R1_P1_000kg_a.png")
ruta_imagen_nueva = os.path.join(carpeta_ejemplo, "D100_R1_P6_250kg_a.png")

# ROI de la plantilla (de roi.py), ajustado al contorno del target
x = 2341
y = 1548
w = 104
h = 104

margen_busqueda = 60       # Desplazamiento máximo esperado del target, en píxeles
umbral_zncc = 0.80         # Por debajo de este coeficiente no se reporta medición
factor_interpolacion = 20  # Ampliación para el refinamiento subpíxel (20 = pasos de 1/20 de píxel)
factor_escala = 0.2808     # mm/píxel (de factor_escala.py); None = reportar solo en píxeles


# Recorta una ventana y, si se sale de la imagen, completa el faltante repitiendo el borde.
def recortar_con_borde(img, x0, y0, ancho, alto):
    alto_img, ancho_img = img.shape[:2]
    izq, arr = max(0, -x0), max(0, -y0)
    der, aba = max(0, x0 + ancho - ancho_img), max(0, y0 + alto - alto_img)
    recorte = img[max(0, y0):y0 + alto, max(0, x0):x0 + ancho]
    if izq or arr or der or aba:
        recorte = cv2.copyMakeBorder(recorte, arr, aba, izq, der, cv2.BORDER_REPLICATE)
    return recorte


# Posición del máximo, respecto a i, de la parábola que pasa por valores[i-1], [i] e [i+1].
def vertice_parabola(valores, i):
    if i <= 0 or i >= len(valores) - 1:
        return 0.0
    curvatura = valores[i - 1] - 2 * valores[i] + valores[i + 1]
    if curvatura == 0:
        return 0.0
    return 0.5 * (valores[i - 1] - valores[i + 1]) / curvatura


# Desplazamiento del target del ROI (x, y, w, h) entre dos imágenes en escala de grises.
#
# Aplica los pasos 3 a 5 de este programa y devuelve un diccionario. Si la medición no es válida,
# 'dx' y 'dy' son None y 'motivo' explica por qué. La usan este programa y medir.py.
def medir_zncc(img_ref, img_new, roi, margen_busqueda=60, umbral_zncc=0.80, factor_interpolacion=20):
    x, y, w, h = roi

    # 3. VENTANAS DE TRABAJO
    # No se ecualiza: ZNCC resta la media y divide entre la desviación estándar de cada ventana, por lo
    # que ya compensa los cambios de brillo y contraste, y ecualizar alteraría la textura del target.
    radio_refinamiento = 2     # Vecindad (píxeles) alrededor del pico entero que se explora al refinar
    borde_interp = 4           # Píxeles extra que necesita el núcleo de Lanczos en los bordes
    margen_total = margen_busqueda + radio_refinamiento + borde_interp

    # Misma ventana en ambas imágenes: el ROI ampliado. La plantilla queda en (margen_total, margen_total).
    ven_ref = recortar_con_borde(img_ref, x - margen_total, y - margen_total, w + 2 * margen_total, h + 2 * margen_total)
    ven_new = recortar_con_borde(img_new, x - margen_total, y - margen_total, w + 2 * margen_total, h + 2 * margen_total)
    ven_ref = ven_ref.astype(np.float32)
    ven_new = ven_new.astype(np.float32)

    plantilla = ven_ref[margen_total:margen_total + h, margen_total:margen_total + w]

    r = dict(dx=None, dy=None, coef=None, coef_refinado=None, k=None, motivo=None,
             poco_contraste=bool(plantilla.std() < 5),
             ven_ref=ven_ref, ven_new=ven_new, margen_total=margen_total)

    # 4. BÚSQUEDA CON ZNCC (píxel entero)
    # TM_CCOEFF_NORMED es la correlación cruzada normalizada de media cero (ZNCC).
    extra = radio_refinamiento + borde_interp
    zona_busqueda = ven_new[extra:-extra, extra:-extra]
    mapa_zncc = cv2.matchTemplate(zona_busqueda, plantilla, cv2.TM_CCOEFF_NORMED)
    _, zncc_max, _, (col_max, fil_max) = cv2.minMaxLoc(mapa_zncc)

    dx_entero = col_max - margen_busqueda
    dy_entero = fil_max - margen_busqueda
    r.update(coef=zncc_max, mapa_zncc=mapa_zncc, dx_entero=dx_entero, dy_entero=dy_entero)

    if zncc_max < umbral_zncc:
        r["motivo"] = f"No se reporta medición: el coeficiente ZNCC es menor que {umbral_zncc}."
        return r
    if abs(dx_entero) == margen_busqueda or abs(dy_entero) == margen_busqueda:
        r["motivo"] = ("No se reporta medición: el máximo quedó en el borde de la zona de búsqueda. "
                       "Aumenta margen_busqueda.")
        return r

    # 5. REFINAMIENTO SUBPÍXEL
    # Se amplían con interpolación de Lanczos la plantilla y la vecindad del pico entero, y se
    # repite la búsqueda con ZNCC sobre las imágenes ampliadas.
    # Limitar la ampliación para que la plantilla ampliada no supere 3000 píxeles de lado
    k = int(max(1, min(factor_interpolacion, 3000 // max(w, h))))

    col = margen_total + dx_entero   # Posición de la coincidencia entera dentro de ven_new
    fil = margen_total + dy_entero

    rec_ref = ven_ref[margen_total - borde_interp:margen_total + h + borde_interp,
                      margen_total - borde_interp:margen_total + w + borde_interp]
    rec_new = ven_new[fil - extra:fil + h + extra, col - extra:col + w + extra]

    plantilla_amp = cv2.resize(rec_ref, None, fx=k, fy=k, interpolation=cv2.INTER_LANCZOS4)
    zona_amp = cv2.resize(rec_new, None, fx=k, fy=k, interpolation=cv2.INTER_LANCZOS4)

    # Descartar la franja ampliada que depende del borde del recorte
    b = borde_interp * k
    plantilla_amp = plantilla_amp[b:-b, b:-b]
    zona_amp = zona_amp[b:-b, b:-b]

    mapa_amp = cv2.matchTemplate(zona_amp, plantilla_amp, cv2.TM_CCOEFF_NORMED)
    _, zncc_refinado, _, (col_amp, fil_amp) = cv2.minMaxLoc(mapa_amp)

    # Ajuste parabólico final sobre el mapa ampliado
    col_fino = col_amp + vertice_parabola(mapa_amp[fil_amp, :], col_amp)
    fil_fino = fil_amp + vertice_parabola(mapa_amp[:, col_amp], fil_amp)

    r.update(dx=float(dx_entero + (col_fino - radio_refinamiento * k) / k),
             dy=float(dy_entero + (fil_fino - radio_refinamiento * k) / k),
             coef_refinado=zncc_refinado, k=k)
    return r


if __name__ == "__main__":
    # 1. CARGAR IMÁGENES
    img_ref = cv2.imread(ruta_imagen_ref, cv2.IMREAD_GRAYSCALE)
    img_new = cv2.imread(ruta_imagen_nueva, cv2.IMREAD_GRAYSCALE)

    if img_ref is None or img_new is None:
        print("Error: No se pudieron cargar las imágenes. Verifica las rutas.")
        exit()

    if img_ref.shape != img_new.shape:
        print("Error: Las dos imágenes deben tener la misma resolución.")
        exit()

    # 2. VERIFICAR ROI
    if w < 8 or h < 8:
        print("Error: El ROI es demasiado pequeño.")
        exit()

    print(f"ROI de la plantilla: x={x}, y={y}, w={w}, h={h}")

    # 3 a 5. VENTANAS, BÚSQUEDA CON ZNCC Y REFINAMIENTO SUBPÍXEL
    res = medir_zncc(img_ref, img_new, (x, y, w, h), margen_busqueda, umbral_zncc, factor_interpolacion)
    margen_total = res["margen_total"]
    dx_entero, dy_entero = res["dx_entero"], res["dy_entero"]
    dx, dy = res["dx"], res["dy"]
    medicion_valida = dx is not None

    if res["poco_contraste"]:
        print("Advertencia: la plantilla tiene muy poco contraste; el resultado puede no ser confiable.")

    print(f"Coeficiente ZNCC máximo: {res['coef']:.4f}")
    print(f"Desplazamiento entero: X={dx_entero}, Y={dy_entero} píxeles")

    if not medicion_valida:
        print(res["motivo"])
    else:
        print(f"\nDesplazamiento en X: {dx:.3f} píxeles")
        print(f"Desplazamiento en Y: {dy:.3f} píxeles")
        print(f"Coeficiente ZNCC tras el refinamiento: {res['coef_refinado']:.4f} (ampliación x{res['k']})")

        if factor_escala is not None:
            print(f"Desplazamiento en X: {dx * factor_escala:.3f} mm")
            print(f"Desplazamiento en Y: {dy * factor_escala:.3f} mm")

    # 6. VISUALIZACIÓN
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    axes[0].imshow(res["ven_ref"], cmap='gray', vmin=0, vmax=255)
    axes[0].add_patch(patches.Rectangle((margen_total, margen_total), w, h, linewidth=2, edgecolor='lime', facecolor='none'))
    axes[0].set_title("Referencia: plantilla")
    axes[0].axis('off')

    axes[1].imshow(res["ven_new"], cmap='gray', vmin=0, vmax=255)
    axes[1].add_patch(patches.Rectangle((margen_total, margen_total), w, h, linewidth=1, edgecolor='lime',
                                        facecolor='none', linestyle='--'))
    if medicion_valida:
        axes[1].add_patch(patches.Rectangle((margen_total + dx, margen_total + dy), w, h, linewidth=2,
                                            edgecolor='red', facecolor='none'))
        axes[1].set_title(f"Nueva: dX={dx:.2f} px, dY={dy:.2f} px")
    else:
        axes[1].set_title("Nueva: sin medición")
    axes[1].axis('off')

    mapa = axes[2].imshow(res["mapa_zncc"], cmap='viridis', vmin=-1, vmax=1,
                          extent=[-margen_busqueda - 0.5, margen_busqueda + 0.5, margen_busqueda + 0.5, -margen_busqueda - 0.5])
    axes[2].plot(dx_entero, dy_entero, 'r+', markersize=12)
    axes[2].set_title(f"Mapa ZNCC (máximo = {res['coef']:.3f})")
    axes[2].set_xlabel("Desplazamiento en X (píxeles)")
    axes[2].set_ylabel("Desplazamiento en Y (píxeles)")
    fig.colorbar(mapa, ax=axes[2], fraction=0.046)

    plt.tight_layout()
    plt.show()
