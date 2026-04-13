"""
Génération PDF de la lettre de plainte (en mémoire, pour téléchargement web).
Adapté de la V2 — génère les bytes du PDF via ReportLab.
"""
import io
from datetime import datetime


def generer_plainte_pdf_bytes(profil, vol, destinataire):
    """
    Génère un PDF de plainte en mémoire et retourne les bytes.
    Lève RuntimeError si ReportLab n'est pas installé.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        from reportlab.lib.enums import TA_RIGHT, TA_JUSTIFY
    except ImportError:
        raise RuntimeError(
            "Le module reportlab n'est pas installé.\n"
            "Ouvrez un terminal et tapez : pip install reportlab")

    prenom   = profil.get("prenom", "").upper()
    nom      = profil.get("nom", "").upper()
    adresse  = profil.get("adresse", "")
    cp       = profil.get("code_postal", "")
    ville_pl = profil.get("ville", "")

    date_vol  = vol.get("date", "")
    heure_vol = vol.get("heure", "")
    indicatif = vol.get("indicatif", "")
    icao24    = vol.get("icao24", "")

    date_sign = datetime.now().strftime("%d/%m/%Y")

    if indicatif and indicatif != "-":
        ref_vol = indicatif.strip()
    elif icao24:
        ref_vol = icao24.strip()
    else:
        ref_vol = "référence inconnue"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
        topMargin=2.5*cm, bottomMargin=2.5*cm,
        leftMargin=3*cm, rightMargin=2.5*cm)

    s_normal = ParagraphStyle('n', fontName='Helvetica',      fontSize=10, leading=14, spaceAfter=2)
    s_bold   = ParagraphStyle('b', fontName='Helvetica-Bold', fontSize=10, leading=14, spaceAfter=2)
    s_right  = ParagraphStyle('r', fontName='Helvetica',      fontSize=10, leading=14, alignment=TA_RIGHT)
    s_objet  = ParagraphStyle('o', fontName='Helvetica-Bold', fontSize=11, leading=15, spaceAfter=4)
    s_body   = ParagraphStyle('c', fontName='Helvetica',      fontSize=11, leading=18, spaceAfter=4, alignment=TA_JUSTIFY)

    bleu  = colors.HexColor('#4472C4')
    story = []

    # Expéditeur
    story.append(Paragraph(f"{prenom} {nom}", s_bold))
    if adresse:
        story.append(Paragraph(adresse, s_normal))
    story.append(Paragraph(f"{cp} {ville_pl}".strip(), s_normal))
    story.append(Spacer(1, 0.8*cm))

    # Destinataire
    dest_nom     = destinataire.get("nom", "")
    dest_adresse = destinataire.get("adresse", "")
    dest_cp      = destinataire.get("cp_ville", "")
    dest_bloc = f"{dest_nom}<br/>{dest_adresse}<br/>{dest_cp}"
    story.append(Paragraph(dest_bloc, s_right))
    story.append(Spacer(1, 0.6*cm))

    # Lieu et date
    story.append(Paragraph(f"{ville_pl}, le {date_sign}", s_right))
    story.append(Spacer(1, 0.6*cm))

    # Objet
    heure_obj = heure_vol[:5] if len(heure_vol) >= 5 else heure_vol
    story.append(Paragraph(
        f"Objet : Plainte pour nuisance aérienne — vol du {date_vol} à {heure_obj}", s_objet))

    story.append(HRFlowable(width="100%", thickness=1.5, color=bleu))
    story.append(Spacer(1, 0.5*cm))

    # Corps
    code_infr = vol.get("code", "") or ""
    alt_m     = vol.get("altitude_m")
    alt_str   = f"{int(alt_m)} m" if alt_m is not None else "altitude inconnue"

    if code_infr == "ALT":
        motif = f"à basse altitude ({alt_str}) le {date_vol} à {heure_vol}"
    elif code_infr == "NUIT":
        motif = f"en dehors des horaires autorisés le {date_vol} à {heure_vol}"
    elif code_infr == "ALT+NUIT":
        motif = (f"à basse altitude ({alt_str}) et en dehors des horaires autorisés"
                 f" le {date_vol} à {heure_vol}")
    else:
        motif = f"à basse altitude le {date_vol} à {heure_vol}"

    lignes = [
        f"Je soussigné(e) {prenom} {nom}, demeurant au {adresse}, {cp}, {ville_pl},",
        f"déclare avoir été gêné(e) par un avion volant {motif}, au-dessus de {ville_pl}.",
        None,
        "Je souhaite que ma plainte soit enregistrée et qu'une réponse circonstanciée me soit adressée.",
        None,
        "Si une infraction était constatée, je souhaite que des sanctions soient prises contre les responsables.",
        None,
        f"Pour information, il semblerait que le vol concerné soit le vol : {ref_vol}"
         + (f" ({icao24})" if icao24 and icao24.strip() != ref_vol else "") + ",",
    ]
    for ligne in lignes:
        if ligne:
            story.append(Paragraph(ligne, s_body))
        else:
            story.append(Spacer(1, 0.25*cm))

    story.append(Spacer(1, 0.5*cm))
    story.append(Paragraph(
        "Veuillez agréer, Madame, Monsieur, l'expression de mes salutations distinguées.", s_body))
    story.append(Spacer(1, 1.5*cm))

    # Signature
    story.append(Paragraph("Signature :", s_normal))
    story.append(Spacer(1, 1.8*cm))
    story.append(Paragraph("_______________________________", s_normal))
    story.append(Paragraph(f"{prenom} {nom}", s_normal))

    doc.build(story)
    buf.seek(0)
    return buf.read()
