# Series de imágenes de la prueba con el teléfono celular (26/10/2026): foto de referencia y fotos a comparar.
# Las fotos están en la carpeta "Pruebas 26-10" del proyecto.
import os
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # carpeta del proyecto
CARP = os.path.join(RAIZ, "Pruebas 26-10")
KG = (50, 100, 150, 200, 250)


def _escalones(d, r):
    fotos = [f"escalon_{d}_r{r}_0kg_2.jpg"]
    for kg in KG:
        fotos += [f"escalon_{d}_r{r}_{kg}kg_1.jpg", f"escalon_{d}_r{r}_{kg}kg_2.jpg"]
    if r < 3:   # la descarga de una repeticion es el inicio de la siguiente
        fotos += [f"escalon_{d}_r{r + 1}_0kg_1.jpg", f"escalon_{d}_r{r + 1}_0kg_2.jpg"]
    else:
        fotos += [f"escalon_{d}_r3_0kg_3.jpg", f"escalon_{d}_r3_0kg_4.jpg"]
    return dict(ref=f"escalon_{d}_r{r}_0kg_1.jpg", fotos=fotos)


SERIES = {}
SERIES["Ruido 0,5 m"] = dict(tipo="ruido", dist=0.5, ref="ruido_0_5_1.jpg", fotos=[f"ruido_0_5_{k}.jpg" for k in range(2, 11)])
for r in (1, 2, 3):
    SERIES[f"Escalones 0,5 m R{r}"] = dict(tipo="escalones", dist=0.5, rep=r, **_escalones("0_5", r))
for r in (1, 2, 3):
    SERIES[f"Escalones 1 m R{r}"] = dict(tipo="escalones", dist=1.0, rep=r, **_escalones("1", r))
SERIES["Ruido 1 m"] = dict(tipo="ruido", dist=1.0, ref="ruido_1_1.jpg", fotos=[f"ruido_1_{k}.jpg" for k in range(2, 11)])
# ruido con el enfoque automático activado
SERIES["Ruido 0,5 m, enfoque automático"] = dict(tipo="ruido_auto", dist=0.5, ref="ruido_0_5_auto_1.jpg",
                                                 fotos=[f"ruido_0_5_auto_{k}.jpg" for k in range(2, 11)])
SERIES["Ruido 1 m, enfoque automático"] = dict(tipo="ruido_auto", dist=1.0, ref="ruido_1_auto_1.jpg",
                                               fotos=[f"ruido_1_auto_{k}.jpg" for k in range(2, 11)])
