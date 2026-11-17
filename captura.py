# Captura de las fotos de un ensayo con la cámara IMX477 en la Raspberry Pi: exposición, ganancia y balance
# de blancos fijos, y nombres y carpetas del plan de pruebas. Se usa por SSH y
# no abre ventanas. Las fotos se procesan después con roi.py, factor_escala.py y medir.py.
#
# Uso:
#   python3 captura.py exposicion [factor]  - foto en automático; calcula y guarda los ajustes fijos
#   python3 captura.py D100                 - foto del montaje, serie de ruido y escalones R1 a R3
#   python3 captura.py A30 2                - lo mismo, pero solo con 2 repeticiones (R1 y R2)
#   python3 captura.py D100 estabilidad     - 5 fotos quieto y 5 caminando cerca, para revisar el montaje
#
# El código del montaje es libre: D100, D300, ... (distancias) o A00, A30, ... (perspectiva).
# Las fotos que ya existen no se vuelven a tomar: si se corta la conexión, solo se tiene que ejecutar de nuevo.
import os
import sys
import csv
import json
import time
import datetime
import subprocess

# CONFIGURACIÓN

carpeta_base = os.path.expanduser("~/tfg/fotos")
archivo_ajustes = os.path.expanduser("~/tfg/ajustes.json")
factor_exposicion = 0.7   # Fracción de la exposición automática (llevada a ganancia 1). Menor que 1 para no
                          # saturar el blanco de los targets: en automático ya salía saturado.
fotos_ruido = 10
pausa_ruido_s = 3
fotos_estabilidad = 5
repeticiones = (1, 2, 3)
PASOS = [(1, 0, "sin carga"), (2, 50, "50 kg"), (3, 100, "100 kg"), (4, 150, "150 kg"), (5, 200, "200 kg"),
         (6, 250, "250 kg"), (7, 0, "descarga: retira toda la carga")]
COMANDO_CAMARA = ["rpicam-still"]


def ahora():
    return datetime.datetime.now().strftime("%H:%M:%S")


def leer_ajustes():
    if not os.path.exists(archivo_ajustes):
        print("Error: no hay ajustes de exposición. Ejecuta primero: python3 captura.py exposicion")
        sys.exit(1)
    with open(archivo_ajustes, encoding="utf-8") as f:
        return json.load(f)


# Toma una foto PNG con los ajustes fijos y la anota en el registro. Devuelve True si se guardó.
def tomar(ruta, ajustes, registro, nota=""):
    r, b = ajustes["awb"]
    args = COMANDO_CAMARA + ["-n", "--immediate", "--encoding", "png",
                             "--shutter", str(int(ajustes["shutter"])), "--gain", f"{ajustes['gain']:.2f}",
                             "--awbgains", f"{r:.3f},{b:.3f}", "--denoise", "cdn_off", "-o", ruta]
    hora = ahora()
    t0 = time.time()
    res = subprocess.run(args, capture_output=True, text=True)
    if res.returncode != 0 or not os.path.exists(ruta):
        print(f"  ERROR al tomar {os.path.basename(ruta)}:")
        print("  " + "\n  ".join((res.stderr or "").strip().splitlines()[-5:]))
        print("  Revisa el cable de la cámara (con la Raspberry apagada) y vuelve a ejecutar.")
        return False
    nuevo = not os.path.exists(registro)
    with open(registro, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if nuevo:
            w.writerow(["archivo", "carpeta", "hora", "shutter_us", "ganancia", "awb_rojo", "awb_azul", "nota"])
        w.writerow([os.path.basename(ruta), os.path.basename(os.path.dirname(ruta)), hora,
                    int(ajustes["shutter"]), ajustes["gain"], r, b, nota])
    print(f"  {os.path.basename(ruta)} guardada a las {hora} ({time.time() - t0:.1f} s){' - ' + nota if nota else ''}")
    return True


# Espera Enter. Devuelve '' para seguir, 'r' para repetir el paso anterior; con 'q' termina.
def pedir(texto):
    resp = input(texto).strip().lower()
    if resp == "q":
        print("Captura detenida. Para seguir donde quedaste, vuelve a ejecutar el mismo comando.")
        sys.exit(0)
    return resp


# Foto en automático, lectura de sus metadatos y cálculo de los ajustes fijos con ganancia 1.
def modo_exposicion(factor):
    os.makedirs(carpeta_base, exist_ok=True)
    ruta = os.path.join(carpeta_base, "exposicion_auto.png")
    ruta_meta = os.path.join(carpeta_base, "exposicion_auto.json")
    print("Tomando una foto en automático (unos 5 s)...")
    res = subprocess.run(COMANDO_CAMARA + ["-n", "--encoding", "png", "-o", ruta, "--metadata", ruta_meta],
                         capture_output=True, text=True)
    if res.returncode != 0 or not os.path.exists(ruta_meta):
        print("Error al tomar la foto en automático:\n" + (res.stderr or "")[-500:])
        sys.exit(1)
    with open(ruta_meta, encoding="utf-8") as f:
        meta = json.load(f)
    et, ag = meta["ExposureTime"], meta["AnalogueGain"]
    dg = meta.get("DigitalGain", 1.0)
    awb = [float(meta["ColourGains"][0]), float(meta["ColourGains"][1])]
    # Misma cantidad de luz con ganancia 1: tiempo x ganancia constante; luego el factor de seguridad
    shutter = et * ag * dg * factor
    ajustes = dict(shutter=round(shutter), gain=1.0, awb=awb, factor=factor,
                   automatico=dict(ExposureTime=et, AnalogueGain=ag, DigitalGain=dg),
                   fecha=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    with open(archivo_ajustes, "w", encoding="utf-8") as f:
        json.dump(ajustes, f, indent=1)
    print(f"Automático: exposición {et} µs, ganancia analógica {ag:.2f}, ganancia digital {dg:.2f}, "
          f"balance de blancos {awb[0]:.3f}, {awb[1]:.3f}")
    print(f"Ajustes fijos guardados en {archivo_ajustes}: --shutter {round(shutter)} --gain 1.0 "
          f"--awbgains {awb[0]:.3f},{awb[1]:.3f}  (factor {factor})")

    ruta_fija = os.path.join(carpeta_base, "exposicion_fija.png")
    if tomar(ruta_fija, ajustes, os.path.join(carpeta_base, "registro_exposicion.csv"), "prueba de exposición"):
        try:
            import cv2
            for nombre, r in (("automática", ruta), ("fija", ruta_fija)):
                g = cv2.imread(r, cv2.IMREAD_GRAYSCALE)
                print(f"  Foto {nombre}: brillo medio {g.mean():.0f}, píxeles saturados {(g >= 250).mean() * 100:.2f} %")
        except Exception:
            pass
    print("Abre exposicion_fija.png (por VNC o WinSCP) y revisa que el blanco de los targets no se vea quemado.")
    print("Si se ve quemado, repite con un factor menor, por ejemplo: python3 captura.py exposicion 0.5")


def modo_montaje(codigo, ajustes, repeticiones=repeticiones):
    carpeta = os.path.join(carpeta_base, codigo)
    for sub in ("ruido",) + tuple(f"R{r}" for r in repeticiones):
        os.makedirs(os.path.join(carpeta, sub), exist_ok=True)
    registro = os.path.join(carpeta, "registro_fotos.csv")

    # 1. Foto del montaje (para roi.py y factor_escala.py, en la casa)
    ruta = os.path.join(carpeta, f"{codigo}_montaje.png")
    if not os.path.exists(ruta):
        pedir(f"\n[Montaje] Enter para tomar la foto del montaje (q = salir): ")
        if not tomar(ruta, ajustes, registro, "montaje"):
            sys.exit(1)

    # 2. Serie de ruido
    rutas = [os.path.join(carpeta, "ruido", f"{codigo}_ruido_{k:02d}.png") for k in range(1, fotos_ruido + 1)]
    if not all(os.path.exists(r) for r in rutas):
        pedir(f"\n[Ruido] Viga sin carga. Anota la muestra del registrador, aléjate de la mesa y presiona Enter: ")
        for r in rutas:
            if not os.path.exists(r):
                if not tomar(r, ajustes, registro, "ruido"):
                    sys.exit(1)
                time.sleep(pausa_ruido_s)
        print("  Serie de ruido lista. Anota la muestra del registrador del final.")

    # 3. Escalones de carga
    for rep in repeticiones:
        anterior = None
        for p, kg, desc in PASOS:
            par = [os.path.join(carpeta, f"R{rep}", f"{codigo}_R{rep}_P{p}_{kg:03d}kg_{x}.png") for x in ("a", "b")]
            if all(os.path.exists(r) for r in par):
                anterior = (par, p, desc)
                continue
            while True:
                resp = pedir(f"\n[R{rep} P{p}] {desc}. Espera a que se estabilice, aléjate y presiona Enter "
                             f"(r = repetir el paso anterior, q = salir): ")
                if resp == "r" and anterior:
                    par_ant, p_ant, desc_ant = anterior
                    print(f"  Repitiendo R{rep} P{p_ant} ({desc_ant}). Deja la carga de ese paso.")
                    for r in par_ant:
                        tomar(r, ajustes, registro, "repetida")
                    continue
                break
            for r in par:
                if not os.path.exists(r) and not tomar(r, ajustes, registro, f"R{rep} P{p}"):
                    sys.exit(1)
            print("  Anota en el Excel la muestra del registrador de las dos fotos.")
            anterior = (par, p, desc)
        print(f"\nRepetición R{rep} lista.")
    print(f"\nMontaje {codigo} completo. Copia la carpeta {carpeta} a la portátil con WinSCP.")


def modo_estabilidad(codigo, ajustes):
    carpeta = os.path.join(carpeta_base, codigo, "estabilidad")
    os.makedirs(carpeta, exist_ok=True)
    registro = os.path.join(carpeta_base, codigo, "registro_fotos.csv")
    for parte, texto in (("quieto", "No toques nada ni te muevas"),
                         ("movimiento", "Camina alrededor y manipula la prensa SIN aplicar carga")):
        pedir(f"\n[Estabilidad] {texto}. Presiona Enter para empezar ({fotos_estabilidad} fotos): ")
        for k in range(1, fotos_estabilidad + 1):
            if not tomar(os.path.join(carpeta, f"{codigo}_est_{parte}_{k:02d}.png"), ajustes, registro, parte):
                sys.exit(1)
            time.sleep(pausa_ruido_s)
    print(f"\nListo. En casa: python3 medir.py {carpeta} y revisa la columna zncc_Fijo_dy_px.")


def main(argv):
    if len(argv) < 2:
        print("Uso: python3 captura.py exposicion [factor] | python3 captura.py D100 [estabilidad | n.º de repeticiones]")
        return
    print(f"Hora de la Raspberry: {ahora()}  (debe coincidir con la del registrador; si no: sudo date -s ...)")
    if argv[1] == "exposicion":
        modo_exposicion(float(argv[2]) if len(argv) > 2 else factor_exposicion)
        return
    ajustes = leer_ajustes()
    print(f"Ajustes fijos: --shutter {ajustes['shutter']} --gain {ajustes['gain']} "
          f"--awbgains {ajustes['awb'][0]:.3f},{ajustes['awb'][1]:.3f}  (del {ajustes['fecha']})")
    if len(argv) > 2 and argv[2] == "estabilidad":
        modo_estabilidad(argv[1], ajustes)
    elif len(argv) > 2 and argv[2].isdigit() and int(argv[2]) >= 1:
        modo_montaje(argv[1], ajustes, tuple(range(1, int(argv[2]) + 1)))
    else:
        modo_montaje(argv[1], ajustes)


if __name__ == "__main__":
    try:
        main(sys.argv)
    except KeyboardInterrupt:
        print("\nCaptura interrumpida. Para seguir donde quedaste, vuelve a ejecutar el mismo comando.")
