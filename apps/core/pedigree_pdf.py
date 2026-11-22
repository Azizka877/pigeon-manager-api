"""
apps/core/pedigree_pdf.py
=========================
Générateur de pedigree PDF imprimable (A4 portrait) avec :
  - en-tête aux couleurs PigeonManager (teal #00685f)
  - carte d'identité du sujet + badge de consanguinité (COI)
  - arbre sur 4 générations (15 cases, mâles/femelles différenciés)
  - QR code de vérification publique (lien signé, sans connexion)
  - pied de page informatif

Ne dépend PAS de Django : reçoit des données déjà extraites (dicts +
image PIL du QR). Retourne les octets du PDF.
"""

from io import BytesIO

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

# ── Palette identité PigeonManager ───────────────────────────────────────────
TEAL = HexColor('#00685f')
TEAL_FONCE = HexColor('#01352f')
TEAL_CLAIR = HexColor('#f5faf8')
TEAL_BLANC = HexColor('#cfe8e4')
MALE = HexColor('#00685f')
FEMELLE = HexColor('#b45309')
ENCRE = HexColor('#111827')
GRIS = HexColor('#6b7280')
GRIS_CLAIR = HexColor('#d1d5db')
GRIS_PALE = HexColor('#f3f4f6')
BLANC = HexColor('#ffffff')

LARGEUR, HAUTEUR = A4  # points
MARGE = 14 * mm

# Géométrie de l'arbre (mm)
BANDE_H = 24.0
IDENTITE_H = 34.0
LIGNE_H = 21.0
LIGNE_GAP = 1.5
NB_RANGS = 8
ARBRE_H = NB_RANGS * LIGNE_H + (NB_RANGS - 1) * LIGNE_GAP
COLS = [34.0, 40.0, 44.0, 48.0]   # largeurs des 4 colonnes
COL_GAP = 4.0


def _y(y_haut_mm):
    """Convertit une coordonnée mesurée du haut de page en coordonnée
    reportlab (bas de page)."""
    return HAUTEUR - y_haut_mm * mm


def _texte_ajuste(texte, police, taille, largeur_max):
    """Réduit la police puis tronque pour tenir dans largeur_max."""
    while taille > 5.2 and stringWidth(texte, police, taille) > largeur_max:
        taille -= 0.4
    if stringWidth(texte, police, taille) > largeur_max:
        while texte and stringWidth(texte + '…', police, taille) > largeur_max:
            texte = texte[:-1]
        texte += '…'
    return texte, taille


def _ecrire(c, x_mm, y_haut_mm, texte, police='Helvetica', taille=8,
            couleur=ENCRE, align='gauche', ancre='haut'):
    """Écrit une chaîne : y_haut_mm = position du haut du texte (ou de sa
    baseline si ancre='bas')."""
    if align == 'droite':
        x_mm -= stringWidth(texte, police, taille) / mm
    elif align == 'centre':
        x_mm -= stringWidth(texte, police, taille) / (2 * mm)
    if ancre == 'haut':
        y = _y(y_haut_mm) - taille * 0.82
    else:
        y = _y(y_haut_mm)
    c.setFont(police, taille)
    c.setFillColor(couleur)
    c.drawString(x_mm * mm, y, texte)


def _boite(c, x_mm, y_haut_mm, w_mm, h_mm, donnee, sujet=False):
    """Une case du pedigree. `donnee` = dict (matricule, sexe, race, annee)
    ou None (case en pointillés « Non enregistré »)."""
    rayon = 2.2 * mm
    x = x_mm * mm
    y = _y(y_haut_mm + h_mm)
    if donnee is None:
        c.setStrokeColor(GRIS_CLAIR)
        c.setFillColor(GRIS_PALE)
        c.setLineWidth(0.8)
        c.setDash(2.5, 2)
        c.roundRect(x, y, w_mm * mm, h_mm * mm, rayon, stroke=1, fill=1)
        c.setDash()
        _ecrire(c, x_mm + w_mm / 2, y_haut_mm + h_mm / 2, 'Non enregistré',
                'Helvetica-Oblique', 6.8, GRIS, align='centre', ancre='bas')
        return

    bordure = MALE if donnee.get('sexe') == 'M' else FEMELLE
    c.setStrokeColor(bordure)
    c.setFillColor(BLANC)
    c.setLineWidth(1.1 if not sujet else 1.5)
    c.roundRect(x, y, w_mm * mm, h_mm * mm, rayon, stroke=1, fill=1)
    # pastille sexe en haut à droite
    r = 1.6 * mm
    c.setFillColor(bordure)
    c.circle(x + w_mm * mm - r - 1.6 * mm, y + h_mm * mm - r - 1.6 * mm, r,
             stroke=0, fill=1)
    c.setFont('Helvetica-Bold', 4.6)
    c.setFillColor(BLANC)
    c.drawCentredString(x + w_mm * mm - r - 1.6 * mm,
                        y + h_mm * mm - r - 1.6 * mm - 1.5,
                        donnee.get('sexe') or '?')

    texte_mat = donnee.get('matricule') or '?'
    taille_mat = 9.2 if not sujet else 13.5
    marge_txt = 3.0 * mm / mm
    # réserve la place de la pastille sexe à droite
    texte_mat, taille_mat = _texte_ajuste(
        texte_mat, 'Helvetica-Bold', taille_mat, (w_mm - 11) * mm)
    _ecrire(c, x_mm + marge_txt, y_haut_mm + 3.2, texte_mat,
            'Helvetica-Bold', taille_mat, ENCRE, ancre='haut')

    ligne2 = donnee.get('race') or ''
    if ligne2:
        ligne2, t2 = _texte_ajuste(ligne2, 'Helvetica', 7.0, (w_mm - 8) * mm)
        _ecrire(c, x_mm + marge_txt, y_haut_mm + 3.2 + taille_mat + 1.6,
                ligne2, 'Helvetica', t2, GRIS)

    if donnee.get('annee'):
        _ecrire(c, x_mm + marge_txt, y_haut_mm + h_mm - 4.6,
                f"{donnee['annee']}", 'Helvetica', 6.4, GRIS_CLAIR)


def _connecteur(c, x_gauche_mm, y_depart_mm, x_droite_mm, y_arrivee_mm):
    """Ligne en coude : sortie horizontale, verticale, entrée horizontale."""
    coude = x_gauche_mm + (x_droite_mm - x_gauche_mm) / 2
    c.setStrokeColor(HexColor('#9ca3af'))
    c.setLineWidth(1.0)
    p = c.beginPath()
    p.moveTo(x_gauche_mm * mm, _y(y_depart_mm))
    p.lineTo(coude * mm, _y(y_depart_mm))
    p.lineTo(coude * mm, _y(y_arrivee_mm))
    p.lineTo(x_droite_mm * mm, _y(y_arrivee_mm))
    c.drawPath(p, stroke=1, fill=0)


def generer_pdf(donnees):
    """
    donnees = {
        'colombier': str,
        'genere_le': 'JJ/MM/AAAA',
        'pigeon': {'matricule', 'sexe', 'race', 'couleur',
                   'date_naissance': date | None},
        'coi': float | None,
        'niveau_label': str,
        'couleur_niveau': '#rrggbb',
        'arbre': {'matricule','sexe','race','annee','pere':…,'mere':…},
        'qr_image': PIL.Image | None,
        'profondeur': int,
    }
    -> bytes du PDF
    """
    sujet = donnees['pigeon']
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Pedigree - {sujet.get('matricule', '')}")

    # ── Bande d'en-tête ──────────────────────────────────────────────────
    c.setFillColor(TEAL)
    c.rect(0, _y(BANDE_H), LARGEUR, BANDE_H * mm, stroke=0, fill=1)
    c.setFillColor(TEAL_FONCE)
    c.rect(0, _y(BANDE_H), LARGEUR, 1.6 * mm, stroke=0, fill=1)
    _ecrire(c, MARGE / mm + 1, 5.2, 'PEDIGREE', 'Helvetica-Bold', 19, BLANC)
    _ecrire(c, (LARGEUR - MARGE) / mm, 6.0,
            donnees.get('colombier') or 'PigeonManager',
            'Helvetica-Bold', 10, BLANC, align='droite')
    _ecrire(c, (LARGEUR - MARGE) / mm, 13.5,
            f"Généré le {donnees.get('genere_le', '')}",
            'Helvetica', 7.5, TEAL_BLANC, align='droite')

    # ── Carte d'identité du sujet ────────────────────────────────────────
    id_haut = BANDE_H + 7
    c.setFillColor(TEAL_CLAIR)
    c.roundRect(MARGE, _y(id_haut + IDENTITE_H), LARGEUR - 2 * MARGE,
                IDENTITE_H * mm, 3 * mm, stroke=0, fill=1)
    c.setFillColor(TEAL)
    c.roundRect(MARGE, _y(id_haut + IDENTITE_H), 3 * mm, IDENTITE_H * mm,
                1.5 * mm, stroke=0, fill=1)

    ix = MARGE / mm + 6
    matricule, taille_mat = _texte_ajuste(
        sujet.get('matricule') or '?', 'Helvetica-Bold', 16, 90 * mm)
    _ecrire(c, ix, id_haut + 4.5, matricule, 'Helvetica-Bold',
            taille_mat, ENCRE)
    sexe_txt = {'M': 'Mâle', 'F': 'Femelle'}.get(sujet.get('sexe'), '—')
    lignes = [part for part in (sujet.get('race'), sujet.get('couleur'),
                                sexe_txt) if part]
    _ecrire(c, ix, id_haut + 16.5, '  •  '.join(lignes) if lignes else '—',
            'Helvetica', 9, GRIS)
    naissance = sujet.get('date_naissance')
    _ecrire(c, ix, id_haut + 23.5,
            f"Né(e) le {naissance.strftime('%d/%m/%Y')}" if naissance
            else 'Date de naissance non renseignée',
            'Helvetica', 8.5, GRIS)

    # Badge COI
    coi = donnees.get('coi')
    if coi is None:
        chip_txt = 'Consanguinité : non calculable (généalogie incomplète)'
        chip_couleur = GRIS
    else:
        from apps.core.coi import classifier, en_pourcent
        niveau = classifier(coi)
        chip_txt = (f"Consanguinité (COI) : {en_pourcent(coi)} % — "
                    f"{niveau['niveau_label']}")
        chip_couleur = HexColor(donnees.get('couleur_niveau')
                                or niveau['couleur'])
    largeur_chip = stringWidth(chip_txt, 'Helvetica-Bold', 8.5) + 7 * mm
    c.setFillColor(chip_couleur)
    c.roundRect(ix * mm, _y(id_haut + IDENTITE_H - 2.5), largeur_chip,
                6.4 * mm, 3.2 * mm, stroke=0, fill=1)
    c.setFont('Helvetica-Bold', 8.5)
    c.setFillColor(BLANC)
    c.drawString(ix * mm + 3.5 * mm, _y(id_haut + IDENTITE_H - 2.5) + 2 * mm,
                 chip_txt)

    # ── QR code de vérification publique ─────────────────────────────────
    qr_img = donnees.get('qr_image')
    if qr_img is not None:
        q = 24.0
        qx = (LARGEUR - MARGE) / mm - q - 3
        qy_haut = id_haut + (IDENTITE_H - q - 4) / 2
        c.setFillColor(BLANC)
        c.roundRect(qx * mm - 1.2 * mm, _y(qy_haut + q + 1.2),
                    (q + 2.4) * mm, (q + 2.4) * mm, 1.5 * mm,
                    stroke=0, fill=1)
        c.drawImage(ImageReader(qr_img), qx * mm, _y(qy_haut + q),
                    q * mm, q * mm)
        _ecrire(c, qx + q / 2, qy_haut + q + 1.6, 'Vérification en ligne',
                'Helvetica', 5.8, GRIS, align='centre')

    # ── Arbre généalogique sur 4 colonnes ────────────────────────────────
    arbre_haut = id_haut + IDENTITE_H + 6
    x0 = MARGE / mm
    x1 = x0 + COLS[0] + COL_GAP
    x2 = x1 + COLS[1] + COL_GAP
    x3 = x2 + COLS[2] + COL_GAP

    def hauteur_cases(nb):
        return nb * LIGNE_H + (nb - 1) * LIGNE_GAP

    arbre = donnees.get('arbre') or {}

    # extraction des 4 colonnes depuis l'arbre imbriqué
    col1 = [arbre.get('pere'), arbre.get('mere')]
    col2, col3 = [], []
    for parent in col1:
        if parent:
            col2 += [parent.get('pere'), parent.get('mere')]
        else:
            col2 += [None, None]
    for grand in col2:
        if grand:
            col3 += [grand.get('pere'), grand.get('mere')]
        else:
            col3 += [None, None]

    # connecteurs (sous les boîtes)
    yc0 = arbre_haut + ARBRE_H / 2
    for k, parent in enumerate(col1):
        y_p = arbre_haut + k * hauteur_cases(4) + hauteur_cases(4) / 2
        if parent is not None or arbre:
            _connecteur(c, x0 + COLS[0], yc0, x1, y_p)
        for j in range(2):
            grand = col2[2 * k + j]
            y_g = arbre_haut + (2 * k + j) * hauteur_cases(2) \
                + hauteur_cases(2) / 2
            if parent is not None:
                _connecteur(c, x1 + COLS[1], y_p, x2, y_g)
            for i in range(2):
                if grand is not None:
                    y_a = arbre_haut + (4 * k + 2 * j + i) * LIGNE_H \
                        + LIGNE_H / 2 + (4 * k + 2 * j + i) * LIGNE_GAP
                    _connecteur(c, x2 + COLS[2], y_g, x3, y_a)

    # boîtes
    _boite(c, x0, arbre_haut, COLS[0], ARBRE_H,
           {'matricule': sujet.get('matricule'), 'sexe': sujet.get('sexe'),
            'race': sujet.get('race'), 'annee':
                sujet.get('date_naissance').year
                if sujet.get('date_naissance') else None},
           sujet=True)
    for k, parent in enumerate(col1):
        _boite(c, x1, arbre_haut + k * hauteur_cases(4), COLS[1],
               hauteur_cases(4), parent)
        for j in range(2):
            grand = col2[2 * k + j]
            _boite(c, x2, arbre_haut + (2 * k + j) * hauteur_cases(2),
                   COLS[2], hauteur_cases(2), grand)
            for i in range(2):
                arriere = col3[4 * k + 2 * j + i]
                idx = 4 * k + 2 * j + i
                _boite(c, x3, arbre_haut + idx * (LIGNE_H + LIGNE_GAP),
                       COLS[3], LIGNE_H, arriere)

    # ── Pied de page ─────────────────────────────────────────────────────
    pied = arbre_haut + ARBRE_H + 7
    c.setStrokeColor(GRIS_CLAIR)
    c.setLineWidth(0.7)
    c.line(MARGE, _y(pied), LARGEUR - MARGE, _y(pied))
    _ecrire(c, LARGEUR / (2 * mm), pied + 3,
            "Document généré par PigeonManager — coefficient de "
            f"consanguinité calculé sur {donnees.get('profondeur', 6)} "
            "générations", 'Helvetica', 7.2, HexColor('#4b5563'),
            align='centre')
    _ecrire(c, LARGEUR / (2 * mm), pied + 8,
            "Méthode tabulaire de Wright  •  les ascendants non enregistrés "
            "ne sont pas assimilés à des fondateurs distincts  •  le QR code "
            "ouvre le pedigree officiel en ligne",
            'Helvetica', 6.2, GRIS, align='centre')

    c.showPage()
    c.save()
    return buf.getvalue()
