"""Étiquettes QR de scan rapide AtelierBorne — outil de bureau, PAS installé sur le Pi.

Une étiquette 102 × 152 mm par produit : QR « + » (BCELL-ENTREE:<réf>) et QR « − » (BCELL-SORTIE:<réf>).
La borne n'a besoin que du texte de ces codes ; le scanner les décode lui-même.

Utilisation sur un Mac/PC avec Python 3 :
    python3 -m pip install reportlab
    python3 generer_etiquettes.py produits.csv etiquettes.pdf
produits.csv : une ligne par produit « référence;libellé » (export Dolibarr possible), en-tête facultatif.
"""
import datetime as dt
from pathlib import Path
import re
import csv
import sys

PREFIXES = {'in': 'BCELL-ENTREE:', 'out': 'BCELL-SORTIE:'}


def code_for(direction, ref):
    return PREFIXES[direction] + str(ref)

WIDTH_MM, HEIGHT_MM = 102, 152
GREEN = (0x1F / 255, 0x7A / 255, 0x3D / 255)
RED = (0xC6 / 255, 0x28 / 255, 0x28 / 255)
BRAND = (0x5C / 255, 0x9C / 255, 0xD3 / 255)
INK = (0x14 / 255, 0x20 / 255, 0x2E / 255)


def _fit(c, text, font, size, max_width, min_size=9):
    """Réduit la taille de police jusqu'à ce que le texte tienne sur la largeur."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    while size > min_size and stringWidth(text, font, size) > max_width:
        size -= 0.5
    return size


def _qr(c, value, x, y, size):
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics import renderPDF
    widget = QrCodeWidget(value, barLevel='M', barBorder=0)
    x0, y0, x1, y1 = widget.getBounds()
    w, h = x1 - x0, y1 - y0
    d = Drawing(size, size, transform=[size / w, 0, 0, size / h, 0, 0])
    d.add(widget)
    renderPDF.draw(d, c, x, y)


def _panel(c, mm, top, label, colour, value, title):
    """Demi-étiquette : bandeau coloré, grand signe, QR, texte de contrôle."""
    left, width, height = 6 * mm, (WIDTH_MM - 12) * mm, 58 * mm
    bottom = top - height
    c.setStrokeColorRGB(*colour)
    c.setLineWidth(2.2)
    c.roundRect(left, bottom, width, height, 3 * mm, stroke=1, fill=0)
    c.setFillColorRGB(*colour)
    c.roundRect(left, top - 11 * mm, width, 11 * mm, 3 * mm, stroke=0, fill=1)
    c.rect(left, top - 11 * mm, width, 4 * mm, stroke=0, fill=1)
    c.setFillColorRGB(1, 1, 1)
    c.setFont('Helvetica-Bold', 16)
    c.drawCentredString(WIDTH_MM * mm / 2, top - 7.7 * mm, label)
    qr = 38 * mm
    _qr(c, value, (WIDTH_MM * mm - qr) / 2, bottom + 5.5 * mm, qr)
    c.setFillColorRGB(*INK)
    c.setFont('Helvetica', 6.5)
    c.drawCentredString(WIDTH_MM * mm / 2, bottom + 2.2 * mm, value)
    c.setFillColorRGB(*colour)
    c.setFont('Helvetica-Bold', 30)
    c.drawString(left + 5 * mm, bottom + 21 * mm, title)
    c.drawRightString(left + width - 5 * mm, bottom + 21 * mm, title)


def build(products, path):
    """products : liste de dicts {ref, label}. Une page 102 × 152 mm par produit."""
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=(WIDTH_MM * mm, HEIGHT_MM * mm))
    c.setTitle('Étiquettes scan rapide AtelierBorne')
    c.setAuthor('AtelierBorne — Bcell')
    for p in products:
        ref, name = str(p['ref']), str(p.get('label') or p['ref'])
        # En-tête : marque, nom du produit, référence.
        c.setFillColorRGB(*BRAND)
        for i, (dx, dy) in enumerate(((0, 0), (4.2, 0), (0, -4.2), (4.2, -4.2))):
            c.roundRect((6 + dx) * mm, (HEIGHT_MM - 9 + dy) * mm, 3.6 * mm, 3.6 * mm, 0.5 * mm, stroke=0, fill=1)
        c.setFillColorRGB(*INK)
        c.setFont('Helvetica-Bold', 8)
        c.drawString(15.5 * mm, (HEIGHT_MM - 6.6) * mm, 'BCELL ENERGY')
        c.setFont('Helvetica', 7)
        c.drawString(15.5 * mm, (HEIGHT_MM - 10) * mm, 'Scan rapide — stock atelier')
        size = _fit(c, name, 'Helvetica-Bold', 17, (WIDTH_MM - 12) * mm)
        c.setFont('Helvetica-Bold', size)
        c.drawString(6 * mm, (HEIGHT_MM - 18.5) * mm, name)
        c.setFont('Helvetica', 10)
        c.setFillColorRGB(0.35, 0.40, 0.47)
        c.drawString(6 * mm, (HEIGHT_MM - 23.5) * mm, 'Réf. ' + ref)
        _panel(c, mm, (HEIGHT_MM - 27) * mm, 'AJOUTER 1 AU STOCK', GREEN, code_for('in', ref), '+')
        _panel(c, mm, (HEIGHT_MM - 27 - 61) * mm, 'RETIRER 1 DU STOCK', RED, code_for('out', ref), '–')
        c.showPage()
    c.save()
    return path


def read_csv(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        sample = f.read(2048)
        f.seek(0)
        dialect = csv.Sniffer().sniff(sample, delimiters=';,\t') if sample else csv.excel
        rows = [r for r in csv.reader(f, dialect) if r and r[0].strip()]
    if rows and rows[0][0].strip().lower() in ('ref', 'réf', 'référence', 'reference', 'réf.'):
        rows = rows[1:]
    return [{'ref': r[0].strip(), 'label': (r[1].strip() if len(r) > 1 and r[1].strip() else r[0].strip())} for r in rows]


def main(argv):
    if len(argv) != 3:
        print(__doc__)
        return 1
    products = read_csv(argv[1])
    if not products:
        print('Aucun produit dans le fichier.')
        return 1
    print(f'{len(products)} étiquette(s) → {build(products, argv[2])}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
