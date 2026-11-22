"""
apps/core/coi.py
================
Moteur de calcul du coefficient de consanguinité (COI, coefficient de
Wright) d'un descendant prévu, à partir de la généalogie enregistrée.

Méthode : déroulage exact de la relation d'apparentement additive
(méthode tabulaire de Wright/Henderson) :

    a(x, y) = 0.5 * a(père(x), y) + 0.5 * a(mère(x), y)   si x ≠ y
    a(x, x) = 1 + F(x)
    F(descendant de x et y) = 0.5 * a(x, y)

Point mathématique crucial : la récurrence n'est valable qu'en développant
l'individu le PLUS RÉCENT (jamais un ancêtre de l'autre côté), sinon les
chemins corrélés sont comptés deux fois. Le moteur respecte cette règle
via un rang topologique (profondeur généalogique), ce qui restitue
EXACTEMENT la valeur tabulaire même sur les pedigrees très consanguins.

Chaque rencontre A des deux lignées contribue `facteur * a(A, A)` ; la
partie F(A) est décomposée à son tour dans les ancêtres de A. La somme des
parts affichées est donc EXACTEMENT égale au COI (100 % traçable).

Le moteur ne dépend PAS de Django : il ne lit que les attributs
.id / .pere / .mere / .matricule / .sexe / .race des objets reçus.
"""

# Profondeur maximale d'analyse généalogique (en générations).
MAX_GENERATIONS = 6

# Seuils de consanguinité usuels en colombiculture.
# ( borne supérieure, code, libellé, couleur hex, message )
NIVEAUX = [
    (0.02, 'faible', 'Faible', '#16a34a',
     "Croisement recommandé : aucune consanguinité notable détectée."),
    (0.0625, 'modere', 'Modéré', '#d97706',
     "Lien de parenté lointain : acceptable, à surveiller sur les générations suivantes."),
    (0.125, 'eleve', 'Élevé', '#ea580c',
     "Parents proches : à réserver au fixage de traits précis, sous suivi rapproché."),
    (1.0, 'tres_eleve', 'Très élevé', '#dc2626',
     "Croisement très proche (frère/sœur, parent/enfant) : fortement déconseillé."),
]


def _cle(objet):
    """Clé stable d'identité (les Pigeon ont des UUID)."""
    return str(objet.id) if objet is not None else None


def _collecter_rangs(racine, rangs):
    """
    Rang topologique (profondeur généalogique) de tous les ancêtres de
    `racine`, fusionné dans `rangs` en prenant le maximum. Garantie :
    rang(enfant) = rang(parent) + 1 sur chaque arête -> développer
    l'individu de rang supérieur est toujours exact.
    """
    def visiter(objet):
        if objet is None:
            return -1
        cle = _cle(objet)
        if cle in rangs:
            return rangs[cle]
        rangs[cle] = -1  # sentinelle anti-boucle (données aberrantes)
        p = visiter(objet.pere)
        m = visiter(objet.mere)
        rang = 1 + max(p, m) if max(p, m) >= 0 else 0
        rangs[cle] = rang
        return rang

    visiter(racine)


def _decomposer(x, y, facteur_x, facteur_y, n1, n2,
                chemin_x, chemin_y, rangs, termes, max_gen, profondeur):
    """
    Déroule a(x, y) en développant TOUJOURS le côté au rang topologique
    supérieur (l'individu le plus récent). Les rencontres (x == y) émettent
    un terme (ancêtre, facteur, n1, n2) ; la partie F(x) de a(x, x) est
    décomposée récursivement dans les parents de x.
    """
    if x is None or y is None or profondeur > 60:
        return
    if _cle(x) == _cle(y):
        termes.append((x, facteur_x * facteur_y, n1, n2))
        # a(x, x) = 1 + F(x) avec F(x) = 0.5 * a(père(x), mère(x))
        if x.pere is not None or x.mere is not None:
            _decomposer(x.pere, x.mere, facteur_x * facteur_y * 0.5, 1.0,
                        n1 + 1, n2 + 1,
                        frozenset({_cle(x.pere)}) if x.pere else frozenset(),
                        frozenset({_cle(x.mere)}) if x.mere else frozenset(),
                        rangs, termes, max_gen, profondeur + 1)
        return

    rang_x = rangs.get(_cle(x), 0)
    rang_y = rangs.get(_cle(y), 0)
    a_parents_x = x.pere is not None or x.mere is not None
    a_parents_y = y.pere is not None or y.mere is not None

    if rang_x > rang_y:
        cote_x = True          # x est le plus récent -> on le développe
    elif rang_y > rang_x:
        cote_x = False
    else:
        # rangs égaux : aucun des deux n'est ancêtre de l'autre,
        # développer l'un ou l'autre est exact.
        cote_x = a_parents_x

    if cote_x and a_parents_x and n1 < max_gen:
        for parent in (x.pere, x.mere):
            if parent is None or _cle(parent) in chemin_x:
                continue  # boucle de données : branche coupée
            _decomposer(parent, y, facteur_x * 0.5, facteur_y, n1 + 1, n2,
                        chemin_x | {_cle(parent)}, chemin_y,
                        rangs, termes, max_gen, profondeur + 1)
    elif a_parents_y and n2 < max_gen:
        for parent in (y.pere, y.mere):
            if parent is None or _cle(parent) in chemin_y:
                continue
            _decomposer(x, parent, facteur_x, facteur_y * 0.5, n1, n2 + 1,
                        chemin_x, chemin_y | {_cle(parent)},
                        rangs, termes, max_gen, profondeur + 1)
    # sinon : deux fondateurs distincts -> aucune contribution


def analyser_croisement(pere, mere, _memo=None, max_gen=MAX_GENERATIONS):
    """
    Analyse exacte d'un croisement :
      - 'coi' : coefficient de consanguinité du descendant prévu (0..1)
      - 'ancetres_communs' : détail par ancêtre (parts qui somment
        EXACTEMENT au COI), trié par contribution décroissante
      - 'profondeur_analyse'
    """
    if _memo is None:
        _memo = {}
    rangs = {}
    _collecter_rangs(pere, rangs)
    _collecter_rangs(mere, rangs)

    termes = []
    _decomposer(pere, mere, 1.0, 1.0, 0, 0,
                frozenset({_cle(pere)}) if pere else frozenset(),
                frozenset({_cle(mere)}) if mere else frozenset(),
                rangs, termes, max_gen, 0)

    par_ancetre = {}
    for ancetre, facteur, d1, d2 in termes:
        f_ancetre = consanguinite(ancetre, _memo, max_gen)
        cle = _cle(ancetre)
        entree = par_ancetre.get(cle)
        if entree is None:
            entree = {
                'id': cle,
                'objet': ancetre,
                'matricule': getattr(ancetre, 'matricule', '?'),
                'sexe': getattr(ancetre, 'sexe', None),
                'race': getattr(ancetre, 'race', None),
                'coi_ancetre': f_ancetre,
                'contribution': 0.0,   # part du COI (somme = coi)
                'gen_male': d1,
                'gen_femelle': d2,
            }
            par_ancetre[cle] = entree
        entree['contribution'] += facteur * 0.5
        entree['gen_male'] = min(entree['gen_male'], d1)
        entree['gen_femelle'] = min(entree['gen_femelle'], d2)

    ancetres_communs = sorted(
        par_ancetre.values(), key=lambda a: -a['contribution'],
    )
    return {
        'coi': sum(a['contribution'] for a in ancetres_communs),
        'ancetres_communs': ancetres_communs,
        'profondeur_analyse': max_gen,
    }


def consanguinite(pigeon, _memo=None, max_gen=MAX_GENERATIONS):
    """
    F du pigeon donné (0.0 si fondateur ou parents incomplets).
    Récursif, mémoïsé, avec sentinelle anti-boucle sur données aberrantes.
    """
    if pigeon is None or pigeon.pere is None or pigeon.mere is None:
        return 0.0
    if _memo is None:
        _memo = {}
    cle = _cle(pigeon)
    if cle in _memo:
        return _memo[cle]
    _memo[cle] = 0.0  # sentinelle : coupe la récursion sur données cycliques
    valeur = analyser_croisement(pigeon.pere, pigeon.mere, _memo, max_gen)['coi']
    _memo[cle] = valeur
    return valeur


# ── Interprétation ───────────────────────────────────────────────────────────

def classifier(coi):
    """Niveau de risque associé à un COI (float 0..1)."""
    for seuil, code, libelle, couleur, message in NIVEAUX:
        if coi <= seuil:
            return {
                'niveau': code,
                'niveau_label': libelle,
                'couleur': couleur,
                'message': message,
            }
    code, libelle, couleur, message = NIVEAUX[-1][1:]
    return {'niveau': code, 'niveau_label': libelle, 'couleur': couleur,
            'message': message}


def en_pourcent(coi):
    """0.03125 -> '3,13' (chaîne prête à afficher, virgule française,
    arrondi classique demi-point supérieur)."""
    from decimal import Decimal, ROUND_HALF_UP
    centieme = (Decimal(str(coi)) * 100).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP,
    )
    return f"{centieme}".replace('.', ',')
