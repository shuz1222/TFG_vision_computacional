import os
import sys
import json
import cv2
import numpy as np

# Uso:  python factor_escala.py                 (una imagen y un ROI de la configuración: se marcan las 4 esquinas)
#       python factor_escala.py ruta/rois.json  (mide los targets de regiones_escala en la foto de referencia que
#                                                guardó roi.py, y escribe sus escalas en ese rois.json)
#
# La escala de cada target es L_real dividido entre su alto en píxeles. Se usa el alto porque se miden
# desplazamientos verticales: el alto aparente del target en su posición de la imagen ya incluye su distancia
# a la cámara, la inclinación de la cámara y la distorsión del lente, y no cambia si la cámara o el target
# están girados sobre el eje vertical.
#
# El alto se mide entre los centros de los cuadros oscuros de arriba y de abajo del tablero,
# que están a 2/3 del lado, el alto es 1.5 veces esa distancia. El centro de cada cuadro es el punto medio entre
# sus dos bordes, así que no cambia si el desenfoque o el umbral hacen que el cuadro se vea más grande. Con el
# umbral, cada cuadro oscuro se veía hasta ~10 % más grande, y el tablero medido de borde a borde
# resultó entre 0.3 y 3.5 % más grande, la escala quedaba corta frente al LVDT.
# Los bordes solo se usan para ubicar el tablero, a partir del ROI de rois.json. Si en un target no se
# encuentran, o las marcas no coinciden, se marcan sus 4 esquinas con clics. El target fijo no necesita
# escala, su movimiento se resta en píxeles.

# CONFIGURACIÓN

ruta_imagen = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Pruebas 10-11", "D100", "R1",
                           "D100_R1_P1_000kg_a.png")   # Por defecto, la foto de ejemplo a 1 m

# ROI que contiene al target (de roi.py), solo para el uso sin rois.json
x_roi = 2341
y_roi = 1548
w_roi = 104
h_roi = 104

regiones_escala = ("LVDT", "Centro", "Cuerpo")  # Targets de rois.json cuya escala se mide
region_principal = "LVDT"  # Su escala se guarda también como factor_escala
margen_recorte = 10        # Píxeles que se agregan alrededor del ROI en las vistas ampliadas
factor_zoom = 4.0          # Ampliación del ROI en las vistas
L_real = 28.4              # mm, lado medido del tablero del target impreso


# Posición subpíxel del borde exterior del tablero a la izquierda y a la derecha del centro c de un
# perfil: el primer paso de oscuro a claro entre 0.25 y 0.8 lados del centro, interpolado en el umbral.
def _borde_exterior(perfil, c, lado, umbral):
    oscuro = perfil < umbral
    bordes = []
    for paso in (-1, 1):
        borde = None
        for d in range(int(0.25 * lado), int(0.8 * lado)):
            i = c + paso * d
            j = i + paso
            if not (0 <= i < len(perfil) and 0 <= j < len(perfil)):
                break
            if oscuro[i] and not oscuro[j]:
                borde = i + paso * (umbral - perfil[i]) / (perfil[j] - perfil[i])
                break
        bordes.append(borde)
    return bordes


# Ubica los bordes exteriores del tablero 3 x 3 de un target con precisión subpíxel, a partir de su
# centro (cx, cy) y su lado aproximados, en píxeles de la imagen completa.
#
# Una franja horizontal que cruza el centro pasa por los cuadros oscuros de la izquierda y la derecha, y
# una vertical por los de arriba y abajo. Cada borde es el punto donde el perfil promedio de la franja
# cruza el nivel medio entre el negro y el blanco del target, que es la mitad de la rampa de grises del
# borde desenfocado. Devuelve un dict con x0, x1, y0, y1, ancho, alto y nota, o None si no se encontraron los bordes.
def medir_bordes(gris, cx, cy, lado):
    lado0 = lado
    for _ in range(2):  # la segunda pasada recentra la franja con el resultado de la primera
        m = int(round(0.9 * lado))
        cxi, cyi = int(round(cx)), int(round(cy))
        if cxi - m < 0 or cyi - m < 0 or cxi + m > gris.shape[1] or cyi + m > gris.shape[0]:
            return None
        rec = gris[cyi - m:cyi + m, cxi - m:cxi + m].astype(float)
        umbral = (np.percentile(rec, 95) + np.percentile(rec, 5)) / 2
        banda = max(2, int(lado / 10))
        perfil_x = rec[m - banda:m + banda, :].mean(axis=0)
        perfil_y = rec[:, m - banda:m + banda].mean(axis=1)
        izq, der = _borde_exterior(perfil_x, m, lado, umbral)
        arr, aba = _borde_exterior(perfil_y, m, lado, umbral)
        # Si un borde no aparece, se estima con el lado perpendicular
        nota = None
        if None in (izq, der) and None not in (arr, aba):
            izq, der = (der - (aba - arr), der) if izq is None else (izq, izq + (aba - arr))
            nota = "un borde lateral se estimó con el alto"
        elif None in (arr, aba) and None not in (izq, der):
            arr, aba = (aba - (der - izq), aba) if arr is None else (arr, arr + (der - izq))
            nota = "un borde superior o inferior se estimó con el ancho"
        if None in (izq, der, arr, aba):
            return None
        x0, x1, y0, y1 = cxi - m + izq, cxi - m + der, cyi - m + arr, cyi - m + aba
        cx, cy, lado = (x0 + x1) / 2, (y0 + y1) / 2, ((x1 - x0) + (y1 - y0)) / 2
    ancho, alto = x1 - x0, y1 - y0
    # Control: un resultado muy distinto del lado aproximado indica que se tomó otro borde
    if not (0.6 < ancho / lado0 < 1.4 and 0.6 < alto / lado0 < 1.4):
        return None
    return dict(x0=x0, x1=x1, y0=y0, y1=y1, ancho=ancho, alto=alto, nota=nota)


# Desde 'inicio' avanza en la dirección 'paso' hasta el primer paso de oscuro
# a claro, y devuelve la posición subpíxel donde el perfil cruza el umbral (o None).
def _cruce(perfil, inicio, paso, umbral, maximo):
    i = int(round(inicio))
    for _ in range(int(maximo)):
        j = i + paso
        if not (0 <= i < len(perfil) and 0 <= j < len(perfil)):
            return None
        if perfil[i] < umbral <= perfil[j]:
            return i + paso * (umbral - perfil[i]) / (perfil[j] - perfil[i])
        i = j
    return None


# Centros de los dos cuadros oscuros de un perfil que cruza el tablero (bordes exteriores e0 y e1): cada
# centro es el punto medio entre el borde exterior y el borde interior del cuadro, ambos con el mismo umbral.
def _centros_eje(perfil, e0, e1, lado, umbral):
    c1, c2 = e0 + lado / 6, e1 - lado / 6             # un punto dentro de cada cuadro oscuro
    tope = 0.4 * lado + 3
    bordes = (_cruce(perfil, c1, -1, umbral, tope), _cruce(perfil, c1, 1, umbral, tope),
              _cruce(perfil, c2, 1, umbral, tope), _cruce(perfil, c2, -1, umbral, tope))
    if None in bordes:
        return None
    return (bordes[0] + bordes[1]) / 2, (bordes[2] + bordes[3]) / 2


# Centros de los cuadros oscuros del tablero ubicado por medir_bordes (b). Una franja vertical por la columna
# del medio cruza los cuadros de arriba y de abajo, y una horizontal por la fila del medio los de la izquierda y
# la derecha. El centro de cada cuadro es el punto medio entre sus dos bordes: si el desenfoque, el umbral o la
# impresión hacen que el cuadro se vea más grande o más pequeño, sus dos bordes se corren por igual y el punto
# medio no cambia. Como los centros de dos cuadros opuestos están a 2/3 del lado, el alto y el ancho del
# tablero son 1.5 veces la distancia entre ellos. Si los centros de la izquierda y la derecha no se encuentran
# (fondo oscuro pegado al target), el ancho queda el de los bordes, que solo se usa como control.
# Devuelve un dict con las posiciones (arriba, abajo, izq, der, xc, yc), ancho y alto, o None.
def medir_centros(gris, b):
    xc, yc = (b["x0"] + b["x1"]) / 2, (b["y0"] + b["y1"]) / 2
    rec = gris[int(b["y0"]):int(np.ceil(b["y1"])), int(b["x0"]):int(np.ceil(b["x1"]))].astype(float)
    umbral = (np.percentile(rec, 95) + np.percentile(rec, 5)) / 2
    bx, by = max(1, int(0.08 * b["ancho"])), max(1, int(0.08 * b["alto"]))
    perfil_y = gris[:, int(round(xc)) - bx:int(round(xc)) + bx + 1].astype(float).mean(axis=1)
    perfil_x = gris[int(round(yc)) - by:int(round(yc)) + by + 1, :].astype(float).mean(axis=0)
    v = _centros_eje(perfil_y, b["y0"], b["y1"], b["alto"], umbral)
    if v is None:
        return None
    h = _centros_eje(perfil_x, b["x0"], b["x1"], b["ancho"], umbral)
    izq, der = h if h is not None else (b["x0"] + b["ancho"] / 6, b["x1"] - b["ancho"] / 6)
    return dict(arriba=v[0], abajo=v[1], izq=izq, der=der, xc=xc, yc=yc, alto=1.5 * (v[1] - v[0]),
                ancho=1.5 * (der - izq) if h is not None else b["ancho"])


# Recorte del ROI con margen, ampliado. Devuelve la imagen y la esquina del recorte en la imagen.
def ampliar(img, roi):
    x, y, w, h = roi
    x0, y0 = max(0, x - margen_recorte), max(0, y - margen_recorte)
    rec = img[y0:y + h + margen_recorte, x0:x + w + margen_recorte]
    return cv2.resize(rec, None, fx=factor_zoom, fy=factor_zoom, interpolation=cv2.INTER_CUBIC), x0, y0


# Dibuja sobre una vista ampliada (recorte que empieza en (x0, y0)) lo que se midió: la línea vertical
# (verde, da el alto y la escala) une los centros de los cuadros oscuros de arriba y de abajo, y la
# horizontal (celeste, da el ancho) los de la izquierda y la derecha, cada centro con una marca.
def dibujar_centros(vista, c, x0, y0):
    a = lambda v, o: (v - o + 0.5) * factor_zoom          # píxel de la imagen - píxel de la vista
    xc, yc = a(c["xc"], x0), a(c["yc"], y0)
    t = max(6.0, 0.1 * c["alto"] * factor_zoom)           # media longitud de las marcas
    p = lambda x, y: (int(round(x)), int(round(y)))
    verde, celeste = (0, 220, 0), (255, 200, 0)
    # Líneas de 2 px: con 1 px desaparecen si la ventana se muestra achicada
    cv2.line(vista, p(a(c["izq"], x0), yc), p(a(c["der"], x0), yc), celeste, 2)
    for xb in (a(c["izq"], x0), a(c["der"], x0)):
        cv2.line(vista, p(xb, yc - t), p(xb, yc + t), celeste, 2)
    cv2.line(vista, p(xc, a(c["arriba"], y0)), p(xc, a(c["abajo"], y0)), verde, 2)
    for yb in (a(c["arriba"], y0), a(c["abajo"], y0)):
        cv2.line(vista, p(xc - t, yb), p(xc + t, yb), verde, 2)


def esperar_tecla(ventana, vista):
    cv2.namedWindow(ventana, cv2.WINDOW_NORMAL)
    cv2.imshow(ventana, vista)
    tecla = cv2.waitKey(0) & 0xFF
    cv2.destroyAllWindows()
    return chr(tecla).lower() if tecla < 128 else ""


# Ventana para hacer clic en las 4 esquinas del tablero. Devuelve las esquinas en píxeles de la imagen
# completa (ancho, alto y centro), o None si no se marcaron 4.
def marcar_esquinas(img, roi, nombre):
    vista, x0, y0 = ampliar(img, roi)
    puntos = []
    ventana = f"Esquinas del target {nombre}"

    def click(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            puntos.append((x, y))
            cv2.circle(vista, (x, y), 5, (0, 0, 255), -1)
            cv2.putText(vista, str(len(puntos)), (x + 10, y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            cv2.imshow(ventana, vista)

    cv2.namedWindow(ventana, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(ventana, click)
    print(f"Haz clic en las 4 esquinas del tablero del target {nombre}, en cualquier orden. Luego ENTER o ESPACIO.")
    cv2.imshow(ventana, vista)
    cv2.waitKey(0)
    cv2.destroyAllWindows()
    if len(puntos) != 4:
        print(f"Error: debes seleccionar 4 puntos; seleccionaste {len(puntos)}.")
        return None
    # Centro del píxel ampliado - coordenadas de la imagen completa
    pts = (np.array(puntos, dtype=float) + 0.5) / factor_zoom - 0.5 + np.array([x0, y0])
    # Separar los dos puntos de arriba y los dos de abajo, y ordenar cada par de izquierda a derecha
    pts = pts[np.argsort(pts[:, 1])]
    sup_izq, sup_der = sorted(pts[:2], key=lambda p: p[0])
    inf_izq, inf_der = sorted(pts[2:], key=lambda p: p[0])
    # Cada medida es el promedio de los dos lados opuestos
    ancho = (np.linalg.norm(sup_der - sup_izq) + np.linalg.norm(inf_der - inf_izq)) / 2
    alto = (np.linalg.norm(inf_izq - sup_izq) + np.linalg.norm(inf_der - sup_der)) / 2
    cx, cy = pts.mean(axis=0)
    return dict(ancho=ancho, alto=alto, cx=cx, cy=cy)


# Lado del tablero de un target (ancho y alto en px) y el método con que se obtuvo, o None.
def medir_target(img, gris, roi, nombre):
    x, y, w, h = roi
    b = medir_bordes(gris, x + w / 2, y + h / 2, (w + h) / 2)
    c = medir_centros(gris, b) if b is not None else None
    if c is not None:
        vista, x0, y0 = ampliar(img, roi)
        dibujar_centros(vista, c, x0, y0)
        print(f"\n{nombre}: las marcas verdes deben quedar en el centro de los cuadros oscuros de arriba y de abajo; "
              "de su distancia sale la escala. Las celestes, en el centro de los de la izquierda y la derecha (ancho)."
              + (f" ({b['nota']})" if b["nota"] else ""))
        print("ENTER = aceptar   M = marcar las esquinas a mano")
        if esperar_tecla(f"Centros del target {nombre}", vista) != "m":
            return c["ancho"], c["alto"], "centros"
    else:
        print(f"\n{nombre}: no se encontró el tablero automáticamente; marca las esquinas.")
    # Respaldo: los clics dan la posición, y se vuelve a buscar el tablero desde ahí
    k = marcar_esquinas(img, roi, nombre)
    if k is None:
        return None
    b = medir_bordes(gris, k["cx"], k["cy"], (k["ancho"] + k["alto"]) / 2)
    c = medir_centros(gris, b) if b is not None else None
    if c is not None:
        vista, x0, y0 = ampliar(img, roi)
        dibujar_centros(vista, c, x0, y0)
        print(f"{nombre}: centros buscados desde los clics. ENTER = aceptar   M = usar los clics tal cual")
        if esperar_tecla(f"Centros del target {nombre}", vista) != "m":
            return c["ancho"], c["alto"], "centros desde clics"
    return k["ancho"], k["alto"], "clics"


if __name__ == "__main__":

    ruta_json = sys.argv[1] if len(sys.argv) > 1 else None
    if len(sys.argv) > 2:
        print(f'Nota: el argumento "{sys.argv[2]}" ya no se usa; la escala sale siempre del alto del target.')
    datos = None
    if ruta_json:
        with open(ruta_json, encoding="utf-8") as f:
            datos = json.load(f)
        ruta_imagen = os.path.join(os.path.dirname(os.path.abspath(ruta_json)), datos["referencia"])
        targets = {n: datos["regiones"][n] for n in regiones_escala if n in datos["regiones"]}
        if region_principal not in targets:
            print(f"Error: {ruta_json} no tiene la región {region_principal}.")
            exit()
    else:
        targets = {region_principal: [x_roi, y_roi, w_roi, h_roi]}


    # 1. CARGAR IMAGEN
    img = cv2.imread(ruta_imagen)
    if img is None:
        print("Error: No se pudo cargar la imagen. Verifica la ruta.")
        exit()
    gris = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


    # 2. MEDIR CADA TARGET
    lados, metodos = {}, {}
    for nombre, roi in targets.items():
        r = medir_target(img, gris, roi, nombre)
        if r is None:
            if nombre == region_principal:
                print(f"Error: sin la medida del target {region_principal} no hay factor de escala.")
                exit()
            print(f"Se omite el target {nombre}; medir.py usará la escala del {region_principal} para él.")
            continue
        lados[nombre] = r[:2]
        metodos[nombre] = r[2]


    # 3. FACTORES DE ESCALA (alto de cada target)
    escalas = {n: L_real / alto for n, (ancho, alto) in lados.items()}
    s = escalas[region_principal]
    D = datos.get("distancia_camara_m") if datos else None
    print(f"\n{'Target':8s} {'ancho px':>9s} {'alto px':>8s} {'ancho/alto':>10s} {'escala mm/px':>13s}  método")
    for n, (ancho, alto) in lados.items():
        print(f"{n:8s} {ancho:9.2f} {alto:8.2f} {ancho / alto:10.3f} {escalas[n]:13.4f}  {metodos[n]}")
    print("(ancho/alto = 1.000 con la cámara de frente; ≈ cos θ si la cámara está girada en horizontal)")
    for n in escalas:
        if n != region_principal:
            dif = escalas[n] / s - 1
            texto = f"; con D = {D} m equivale a estar ~{100 * dif * D:.1f} cm más lejos" if D else ""
            print(f"{n}: se ve {100 * dif:+.1f} % más pequeño que el target {region_principal} en alto{texto}")


    # 4. GUARDAR EN rois.json (solo si se usó un rois.json)
    if ruta_json:
        datos["factor_escala"] = float(s)
        datos["escala_usada"] = "alto"
        datos["lado_target_mm"] = L_real
        datos["lado_target_px"] = [round(float(v), 2) for v in lados[region_principal]]
        datos["escalas_regiones"] = {n: float(v) for n, v in escalas.items()}
        datos["lados_px"] = {n: [round(float(a), 2), round(float(b), 2)] for n, (a, b) in lados.items()}
        datos["metodo_escala"] = metodos
        datos.pop("lado_target_px_clics", None)
        with open(ruta_json, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=1, ensure_ascii=False)
        print(f"\nEscalas guardadas en {ruta_json}: "
              + ", ".join(f"{n} {v:.4f}" for n, v in escalas.items()) + " mm/px")
    else:
        print(f"\nFactor de escala: {s:.4f} mm/px")
