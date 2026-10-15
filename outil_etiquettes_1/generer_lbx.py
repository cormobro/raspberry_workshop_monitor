"""Étiquettes P-touch (.lbx) de scan rapide — outil de bureau, PAS installé sur le Pi.

Une étiquette par produit, à partir d'un modèle vide créé dans P-touch Editor
(fourni : modele_vide_QL1110_DK11241.lbx — Brother QL-1110NWB, DK-11241 102 × 152 mm, paysage).
Colonne gauche encadrée : « + AJOUTER 1 AU STOCK » (QR BCELL-ENTREE:<réf>) ;
colonne droite encadrée : « – RETIRER 1 DU STOCK » (QR BCELL-SORTIE:<réf>).

Utilisation :
    python3 -m pip install qrcode
    python3 generer_lbx.py modele_vide_QL1110_DK11241.lbx produits.csv dossier_sortie
produits.csv : « référence;libellé » avec une ligne d'en-tête.
Taille de module QR validée sur P-touch Editor 5.4 : 2.4 pt (3.2, 4.0, 4.8 et 5 pt refusés).
"""
import csv, re, sys, zipfile
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr
import qrcode

if len(sys.argv) != 4:
    print(__doc__); sys.exit(1)
with zipfile.ZipFile(sys.argv[1]) as _modele:
    LABEL = _modele.read('label.xml').decode('utf-8')
    PROP = _modele.read('prop.xml').decode('utf-8')
if '<pt:objects/>' not in LABEL:
    sys.exit('Le modèle doit être une étiquette vide (aucun objet).')
X0, Y0, W, H = 17.3, 4.3, 398.4, 279.4   # zone imprimable (<style:backGround>) du modèle
import os
CELL = float(os.environ.get('CELL', '2.4'))  # 2.4 pt : seule grande taille acceptée par P-touch 5.4 lors des essais  # taille d'un module QR en points
oid = [0]

def style(x, y, w, h, name):
    oid[0] += 1
    return (f'<pt:objectStyle x="{x:.1f}pt" y="{y:.1f}pt" width="{w:.1f}pt" height="{h:.1f}pt" backColor="#FFFFFF" '
            f'backPrintColorNumber="0" ropMode="COPYPEN" angle="0" anchor="TOPLEFT" flip="NONE">'
            f'<pt:pen style="NULL" widthX="0.5pt" widthY="0.5pt" color="#000000" printColorNumber="1"/>'
            f'<pt:brush style="NULL" color="#000000" printColorNumber="1" id="0"/>'
            f'<pt:expanded objectName={quoteattr(name)} ID="0" lock="0" templateMergeTarget="LABELLIST" '
            f'templateMergeType="NONE" templateMergeID="0" linkStatus="NONE" linkID="0"/></pt:objectStyle>')

def font(size, bold):
    return (f'<text:ptFontInfo><text:logFont name="Arial" width="0" italic="false" weight="{700 if bold else 400}" '
            f'charSet="0" pitchAndFamily="34"/><text:fontExt effect="NOEFFECT" underline="0" strikeout="0" '
            f'size="{size}pt" orgSize="{size}pt" textColor="#000000" textPrintColorNumber="1"/></text:ptFontInfo>')

def text(x, y, w, h, value, size, bold=False, align='LEFT', name='Texte'):
    n = len(value.encode('utf-16-le')) // 2
    return (f'<text:text>{style(x, y, w, h, name)}{font(size, bold)}'
            f'<text:textControl control="FIXEDFRAME" clipFrame="false" aspectNormal="true" shrink="true" autoLF="false" avoidImage="false"/>'
            f'<text:textAlign horizontalAlignment="{align}" verticalAlignment="CENTER" inLineAlignment="BASELINE"/>'
            f'<text:textStyle vertical="false" nullBlock="false" charSpace="0" lineSpace="0" orgPoint="{size}pt" combinedChars="false"/>'
            f'<pt:data>{escape(value)}</pt:data><text:stringItem charLen="{n}">{font(size, bold)}</text:stringItem></text:text>')

def frame(x, y, w, h, name, pen=2.0):
    """Cadre rectangulaire noir, fond transparent (placé avant les textes : il passe dessous)."""
    st = style(x, y, w, h, name).replace('<pt:pen style="NULL" widthX="0.5pt" widthY="0.5pt"',
                                         f'<pt:pen style="INSIDEFRAME" widthX="{pen}pt" widthY="{pen}pt"')
    return f'<draw:rect>{st}<draw:rectStyle shape="RECTANGLE" roundnessX="0pt" roundnessY="0pt"/></draw:rect>'

def qr(x, y, value, name):
    q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0)
    q.add_data(value); q.make(fit=True)
    side = q.modules_count * CELL
    return side, (f'<barcode:barcode>{style(x - side / 2, y, side, side, name)}'
                  f'<barcode:barcodeStyle protocol="QRCODE" lengths="48" zeroFill="false" barWidth="{CELL}pt" barRatio="1:3" '
                  f'humanReadable="false" humanReadableAlignment="LEFT" checkDigit="false" autoLengths="true" margin="false" '
                  f'sameLengthBar="false" bearerBar="false"/>'
                  f'<barcode:qrcodeStyle model="2" eccLevel="15%" cellSize="{CELL}pt" mbcs="auto" joint="1" version="auto"/>'
                  f'<pt:data>{escape(value)}</pt:data></barcode:barcode>')

def label_xml(ref, name):
    oid[0] = 0
    half = W / 2
    objs = [text(X0 + 6, Y0 + 4, W - 12, 24, name, 16, True, name='Libelle'),
            text(X0 + 6, Y0 + 28, W - 12, 14, 'Réf. ' + ref + '  ·  BCELL ENERGY — scan rapide stock', 9, name='Reference')]
    # Bloc « titre + QR + code » centré verticalement sous l'en-tête (identique pour les deux colonnes).
    sides = []
    for direction in ('ENTREE', 'SORTIE'):
        q = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0)
        q.add_data(f'BCELL-{direction}:{ref}'); q.make(fit=True)
        sides.append(q.modules_count * CELL)
    side_max = max(sides)
    top, bottom = Y0 + 60, Y0 + H - 12
    block = 24 + 10 + side_max + 6 + 12
    if block > bottom - top or side_max > half - 12:
        raise SystemExit(f'QR trop grand pour {ref} avec {CELL} pt')
    start = top + (bottom - top - block) / 2
    for i, direction in enumerate(('ENTREE', 'SORTIE')):
        objs.append(frame(X0 + half * i + 4, Y0 + 52, half - 8, H - 58, 'Cadre' + direction))
    for i, (direction, title) in enumerate((('ENTREE', '+  AJOUTER 1 AU STOCK'), ('SORTIE', '–  RETIRER 1 DU STOCK'))):
        cx = X0 + half * i + half / 2
        code = f'BCELL-{direction}:{ref}'
        objs.append(text(X0 + half * i + 16, start, half - 32, 24, title, 14, True, 'CENTER', 'Titre' + direction))
        qy = start + 34 + (side_max - sides[i]) / 2
        side, obj = qr(cx, qy, code, 'QR' + direction)
        objs.append(obj)
        objs.append(text(X0 + half * i + 10, start + 34 + side_max + 6, half - 20, 12, code, 7.5, False, 'CENTER', 'Code' + direction))
    return LABEL.replace('<pt:objects/>', '<pt:objects>' + ''.join(objs) + '</pt:objects>')

def write(path, ref, name):
    prop = re.sub(r'<dc:title>.*?</dc:title>', '<dc:title>' + escape(name) + '</dc:title>', PROP)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('label.xml', label_xml(ref, name))
        z.writestr('prop.xml', prop)

rows = list(csv.reader(open(sys.argv[2], encoding='utf-8-sig'), delimiter=';'))[1:]
out = Path(sys.argv[3]); out.mkdir(parents=True, exist_ok=True)
for i, (ref, name) in enumerate(rows, 1):
    write(out / f'{i:02d}_{re.sub(r"[^A-Za-z0-9._-]", "_", ref)}.lbx', ref, name)
print(len(rows), 'fichiers')
