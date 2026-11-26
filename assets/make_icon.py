"""Genera assets/telegram-icon.png: un radar con los colores de Google (512x512)."""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

S = 2048                      # se dibuja a 4x y se reduce para suavizar bordes
OUT = 512
C = S // 2
BLUE, RED, YELLOW, GREEN = (66, 133, 244), (234, 67, 53), (251, 188, 5), (52, 168, 83)
BG = (255, 255, 255)
GRID = (218, 224, 233)

img = Image.new("RGBA", (S, S), BG + (255,))
d = ImageDraw.Draw(img)

R = int(S * 0.43)             # radio del radar (cabe en el recorte circular de Telegram)

# Anillo exterior en cuatro arcos de color, con pequeñas separaciones
ring_w = int(S * 0.045)
box = [C - R, C - R, C + R, C + R]
gap = 6
for i, col in enumerate([BLUE, RED, YELLOW, GREEN]):
    start = -135 + i * 90 + gap / 2
    d.arc(box, start, start + 90 - gap, fill=col, width=ring_w)

# Anillos interiores y cruz de la retícula
inner = R - ring_w - int(S * 0.02)
for f in (1.0, 0.68, 0.36):
    r = int(inner * f)
    d.ellipse([C - r, C - r, C + r, C + r], outline=GRID, width=int(S * 0.008))
lw = int(S * 0.007)
d.line([C - inner, C, C + inner, C], fill=GRID, width=lw)
d.line([C, C - inner, C, C + inner], fill=GRID, width=lw)

# Barrido: abanico azul que se desvanece hacia atrás
sweep = Image.new("RGBA", (S, S), (0, 0, 0, 0))
sd = ImageDraw.Draw(sweep)
head = -50                    # ángulo del borde delantero (grados, PIL: 0 = derecha, sentido horario)
span = 75
steps = 150
for k in range(steps):
    a0 = head - span + span * k / steps
    alpha = int(150 * (k / steps) ** 1.6)
    sd.pieslice([C - inner, C - inner, C + inner, C + inner], a0, a0 + span / steps + 0.4,
                fill=BLUE + (alpha,))
img.alpha_composite(sweep)
d = ImageDraw.Draw(img)

# Línea del barrido
rad = math.radians(head)
d.line([C, C, C + inner * math.cos(rad), C + inner * math.sin(rad)], fill=BLUE, width=int(S * 0.016))


def blip(angle_deg: float, dist: float, col, r: int) -> None:
    """Un punto detectado con un halo suave."""
    a = math.radians(angle_deg)
    x, y = C + inner * dist * math.cos(a), C + inner * dist * math.sin(a)
    halo = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse([x - r * 2.4, y - r * 2.4, x + r * 2.4, y + r * 2.4], fill=col + (90,))
    img.alpha_composite(halo.filter(ImageFilter.GaussianBlur(r * 0.8)))
    ImageDraw.Draw(img).ellipse([x - r, y - r, x + r, y + r], fill=col + (255,))


blip(-62, 0.62, RED, int(S * 0.034))       # el más reciente, junto al barrido
blip(-150, 0.48, YELLOW, int(S * 0.028))
blip(130, 0.70, GREEN, int(S * 0.028))
blip(35, 0.30, BLUE, int(S * 0.022))

# Centro
d = ImageDraw.Draw(img)
cr = int(S * 0.03)
d.ellipse([C - cr, C - cr, C + cr, C + cr], fill=BLUE)
cr2 = int(S * 0.012)
d.ellipse([C - cr2, C - cr2, C + cr2, C + cr2], fill=BG)

out = Path(__file__).with_name("telegram-icon.png")
img.convert("RGB").resize((OUT, OUT), Image.LANCZOS).save(out, optimize=True)
print(out)
