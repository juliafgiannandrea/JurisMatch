"""Gera os ícones PNG do PWA em app/web/icons a partir do mesmo desenho do icon.svg.

Uso, a partir da raiz do projeto:
    python scripts/gerar_icones_pwa.py

Desenho num grid de 64 unidades (igual ao SVG), renderizado em 8x e reduzido com LANCZOS para ter borda suave.
"""
from pathlib import Path

from PIL import Image, ImageDraw

DESTINO = Path(__file__).resolve().parents[1] / "app" / "web" / "icons"
VINHO = (122, 33, 49, 255)
PAPEL = (244, 239, 228, 255)
SUPER = 8


def desenhar(lado: int, *, cantos: bool, escala_marca: float = 1.0) -> Image.Image:
    """lado: tamanho final em px. cantos: fundo arredondado (rx 14/64) ou quadrado cheio.
    escala_marca: encolhe o J em volta do centro (ícone maskable precisa caber na zona segura de 80%)."""
    grande = lado * SUPER
    u = grande / 64  # px por unidade do grid

    img = Image.new("RGBA", (grande, grande), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if cantos:
        d.rounded_rectangle((0, 0, grande - 1, grande - 1), radius=14 * u, fill=VINHO)
    else:
        d.rectangle((0, 0, grande, grande), fill=VINHO)

    def p(x: float, y: float) -> tuple[float, float]:
        """Ponto do grid 64 para px, com a escala da marca aplicada em volta do centro."""
        return ((32 + (x - 32) * escala_marca) * u, (32 + (y - 32) * escala_marca) * u)

    s = escala_marca * u
    # barra de cima (serifa): x 25..45, y 16..21
    d.rectangle((*p(25, 16), *p(45, 21)), fill=PAPEL)
    # haste: x 35..41, y 16..37
    d.rectangle((*p(35, 16), *p(41, 37)), fill=PAPEL)
    # gancho: arco de raio 9 (traço 6) com centro em (29, 37), de 0 a 157 graus
    cx, cy = p(29, 37)
    r_ext = 12 * s
    d.arc((cx - r_ext, cy - r_ext, cx + r_ext, cy + r_ext), start=0, end=157, fill=PAPEL, width=round(6 * s))

    return img.resize((lado, lado), Image.Resampling.LANCZOS)


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    saidas = {
        "icon-192.png": desenhar(192, cantos=True),
        "icon-512.png": desenhar(512, cantos=True),
        "icon-maskable-512.png": desenhar(512, cantos=False, escala_marca=0.72),
        # iOS arredonda sozinho e não aceita transparência: fundo cheio
        "apple-touch-icon.png": desenhar(180, cantos=False, escala_marca=0.86).convert("RGB"),
    }
    for nome, img in saidas.items():
        img.save(DESTINO / nome, optimize=True)
        print(f"{DESTINO / nome}  {img.size[0]}x{img.size[1]}")


if __name__ == "__main__":
    main()
