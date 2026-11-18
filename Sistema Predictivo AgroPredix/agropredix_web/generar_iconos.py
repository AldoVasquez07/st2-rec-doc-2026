"""Genera los íconos de la PWA de AgroPredix. Se ejecuta una sola vez:

    pip install pillow
    python generar_iconos.py

Crea los PNG en pwa/static/pwa/. Si más adelante tiene un logo propio, basta con
reemplazar esos archivos por los suyos (mismos nombres y tamaños).
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw

VERDE = (25, 135, 84)        # #198754, el verde de la barra de AgroPredix
BLANCO = (255, 255, 255)
SALIDA = Path(__file__).resolve().parent / 'pwa' / 'static' / 'pwa'


def hoja(cx, cy, largo, ancho, grados, n=40):
    """Polígono en forma de hoja: base en (cx, cy), apuntando hacia 'grados'."""
    a = math.radians(grados)
    arriba, abajo = [], []
    for i in range(n + 1):
        t = i / n
        x = t * largo
        w = ancho / 2 * math.sin(math.pi * t) ** 0.9
        arriba.append((x, -w))
        abajo.append((x, w))
    return [(cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a))
            for x, y in arriba + abajo[::-1]]


def dibujar(tam, glifo, esquinas=0.0):
    """Brote blanco sobre fondo verde. 'glifo' = tamaño del dibujo respecto al lienzo."""
    s = 4                                   # se dibuja 4 veces más grande y se reduce (bordes suaves)
    n = tam * s
    img = Image.new('RGBA', (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if esquinas:
        d.rounded_rectangle([0, 0, n - 1, n - 1], radius=int(n * esquinas), fill=VERDE)
    else:
        d.rectangle([0, 0, n, n], fill=VERDE)
    g = n * glifo
    cx, base = n / 2, n / 2 + g * 0.40
    tallo = max(2, int(g * 0.07))
    d.line([(cx, base), (cx, base - g * 0.62)], fill=BLANCO, width=tallo)
    d.polygon(hoja(cx, base - g * 0.28, g * 0.55, g * 0.27, -38), fill=BLANCO)     # hoja derecha
    d.polygon(hoja(cx, base - g * 0.44, g * 0.55, g * 0.27, -142), fill=BLANCO)    # hoja izquierda
    d.rounded_rectangle([cx - g * 0.40, base - g * 0.01, cx + g * 0.40, base + g * 0.07],
                        radius=g * 0.04, fill=BLANCO)                               # suelo
    return img.resize((tam, tam), Image.LANCZOS)


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    iconos = {
        'icon-192.png': dibujar(192, 0.62, esquinas=0.18),
        'icon-512.png': dibujar(512, 0.62, esquinas=0.18),
        # "maskable": el sistema la recorta en círculo/cuadrado redondeado, por eso el dibujo va más pequeño
        'icon-maskable-512.png': dibujar(512, 0.46),
        # iOS exige fondo sin transparencia
        'apple-touch-icon.png': dibujar(180, 0.58).convert('RGB'),
        'favicon.png': dibujar(48, 0.66, esquinas=0.2),
    }
    for nombre, img in iconos.items():
        img.save(SALIDA / nombre, optimize=True)
        print('creado', SALIDA / nombre, img.size)


if __name__ == '__main__':
    main()