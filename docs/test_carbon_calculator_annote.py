# ==============================================================================
# FICHIER ANNOTÉ — test_carbon_calculator.py
# Ce fichier est une copie commentée du vrai fichier de test.
# Il ne s'exécute pas (il contient des commentaires très longs).
# Son seul but : t'aider à comprendre comment fonctionne un fichier de tests.
# ==============================================================================


# ──────────────────────────────────────────────────────────────────────────────
# IMPORTS
# ──────────────────────────────────────────────────────────────────────────────

import math
# ^ Le module math de la bibliothèque standard Python.
#   On l'utilise uniquement pour math.isnan() : tester si une valeur est NaN.
#   NaN = "Not a Number", ce qu'on obtient quand un calcul flottant est invalide
#   (ex : 0/0, ou une cellule vide dans un DataFrame pandas).

import sys
# ^ sys donne accès aux entrailles de l'interpréteur Python.
#   On l'utilise ici pour deux choses :
#     1. sys.modules : le dictionnaire de tous les modules importés
#     2. sys.path    : la liste des dossiers où Python cherche les modules

import unittest
# ^ Le framework de tests intégré à Python (pas besoin d'installer quoi que ce soit).
#   Il définit la classe TestCase dont vont hériter tous nos groupes de tests.
#   "Framework" = une boîte à outils avec des règles : si ta méthode commence par
#   "test_", elle sera automatiquement détectée et exécutée comme un test.

from unittest.mock import MagicMock, patch
# ^ "mock" = faux objet qui simule un vrai.
#   Vocabulaire à retenir :
#     - MagicMock : un objet Python qui accepte n'importe quel appel sans planter.
#       dm.nimporte_quoi()  → retourne un autre MagicMock, pas d'erreur.
#       dm.nimporte_quoi.return_value = 42  → maintenant dm.nimporte_quoi() retourne 42.
#     - patch : (non utilisé directement ici, importé au cas où)
#   On importe depuis unittest.mock, un sous-module de unittest.

import pandas as pd
# ^ pandas = la bibliothèque pour manipuler des tableaux de données (DataFrames).
#   Un DataFrame, c'est comme un tableau Excel en Python.
#   On l'importe sous l'alias "pd" par convention universelle.

import numpy as np
# ^ numpy = bibliothèque de calcul numérique.
#   Importé ici mais pas vraiment utilisé directement (il l'est indirectement
#   via pandas). Alias "np" par convention.


# ──────────────────────────────────────────────────────────────────────────────
# NEUTRALISER PYSIDE6 ET HDF5 AVANT TOUT IMPORT
# ──────────────────────────────────────────────────────────────────────────────

for _mod in [
    'PySide6', 'PySide6.QtWidgets', 'PySide6.QtGui', 'PySide6.QtCore',
    'PySide6.QtCharts', 'PySide6.QtPrintSupport',
    'tables', 'tables.flavor',
]:
    sys.modules.setdefault(_mod, MagicMock())

# ^ Pourquoi ce bloc existe ?
#
#   Le fichier ui/carbon_calculator.py contient en haut des lignes comme :
#       from PySide6.QtWidgets import QWidget
#   PySide6, c'est la bibliothèque d'interface graphique (les fenêtres, boutons...).
#   Pour fonctionner, PySide6 a besoin d'un serveur graphique (un écran).
#   En test automatique, il n'y a pas d'écran → PySide6 planterait immédiatement.
#
#   La solution : avant que Python essaie d'importer carbon_calculator.py,
#   on "précharge" de faux modules dans sys.modules.
#
#   sys.modules : c'est le registre global de Python. Quand tu fais `import PySide6`,
#   Python regarde d'abord dans sys.modules. Si c'est déjà là, il prend ça
#   directement sans aller chercher le vrai fichier.
#
#   setdefault(clé, valeur) : insère la valeur SEULEMENT si la clé n'est pas déjà là.
#   Donc si PySide6 est déjà chargé (cas rare), on ne l'écrase pas.
#
#   MagicMock() en tant que module : quand carbon_calculator fait
#       from PySide6.QtWidgets import QWidget
#   Python trouve le faux PySide6 (un MagicMock), et QWidget devient aussi un MagicMock.
#   Tout ce qui utilise QWidget dans le code ne plantera pas — ça retournera juste
#   d'autres MagicMock. Ce n'est pas "correct" mais ça suffit pour tester la logique
#   de calcul, qui n'a pas besoin d'un vrai bouton Qt.
#
#   'tables' et 'tables.flavor' : même principe pour PyTables (lecture HDF5).


# ──────────────────────────────────────────────────────────────────────────────
# AJOUTER LA RACINE DU PROJET AU PATH
# ──────────────────────────────────────────────────────────────────────────────

import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ^ sys.path : la liste des dossiers dans lesquels Python cherche les modules.
#   Quand tu fais `import ui.carbon_calculator`, Python parcourt sys.path
#   pour trouver un dossier "ui" contenant "carbon_calculator.py".
#
#   __file__ : variable spéciale Python, contient le chemin du fichier actuel.
#              ici : ".../LABeCO2/tests/test_carbon_calculator.py"
#
#   os.path.dirname(__file__)         → ".../LABeCO2/tests"
#   os.path.dirname(os.path.dirname(__file__)) → ".../LABeCO2"
#
#   sys.path.insert(0, ...)  : on insère en position 0 (= priorité maximale)
#   le dossier racine du projet LABeCO2, pour que `from ui.carbon_calculator import ...`
#   fonctionne peu importe d'où on lance pytest.


from ui.carbon_calculator import CarbonCalculator
# ^ Maintenant que le path est bon et que PySide6 est neutralisé,
#   on peut importer la vraie classe qu'on veut tester.
#   C'est LE seul vrai import de code de production dans ce fichier.


# ──────────────────────────────────────────────────────────────────────────────
# LA FABRIQUE _make_dm() — le cœur de ce fichier de tests
# ──────────────────────────────────────────────────────────────────────────────

def _make_dm(
    main_data=None,       # DataFrame de la base GES principale (facteurs CO₂)
    data_masse=None,      # DataFrame des masses de consommables solides
    data_materials=None,  # (non utilisé directement, héritage)
    material_map=None,    # dict  {nom_matériau: (co2_par_kg, incertitude)}
    liquid_row=None,      # pd.Series représentant un liquide, ou None
):
# ^ "fabrique" (ou "factory" en anglais) = une fonction dont le seul rôle
#   est de CRÉER et retourner un objet configuré.
#   Ici : crée un faux DataManager paramétrable selon le test.
#
#   Les arguments ont tous une valeur par défaut (None), ce qui permet d'écrire :
#     dm = _make_dm()                          → tout par défaut
#     dm = _make_dm(material_map={'Bois': ...}) → juste les matériaux changent

    dm = MagicMock()
    # ^ Crée le faux DataManager.
    #   MagicMock() est un objet "fourre-tout" : si carbon_calculator.py appelle
    #   dm.nimporte_quelle_methode(), ça ne plantera pas.
    #   On va ensuite configurer les méthodes dont CarbonCalculator a vraiment besoin.

    if main_data is None:
        main_data = pd.DataFrame({
            'category':        ['Achats', 'Véhicules'],
            'subcategory':     ['Consommables de laboratoire', 'Voiture'],
            'subsubcategory':  ['AA01', ''],
            'name':            ['Réactifs', 'Voiture essence'],
            'year':            ['', ''],
            'total':           [0.5, 0.25],   # facteurs CO₂ (kgCO₂/€ ou kgCO₂/km)
            'uncertainty':     [0.1, 0.05],
            'unit':            ['€', 'km'],
        })
    # ^ Si on n'a pas fourni de main_data, on en crée un minimal avec 2 lignes.
    #   Cela représente la "base GES" — la table des facteurs d'émission.
    #   pd.DataFrame({...}) : crée un tableau à partir d'un dictionnaire,
    #   où chaque clé est un nom de colonne et chaque valeur est la liste des cellules.

    dm.get_main_data.return_value = main_data
    # ^ Vocabulaire : "return_value" = "valeur de retour".
    #   On dit au MagicMock : "quand CarbonCalculator appelle dm.get_main_data(),
    #   retourne ce DataFrame".
    #   Sans cette ligne, dm.get_main_data() retournerait un autre MagicMock (inutile).

    if data_masse is None:
        data_masse = pd.DataFrame(columns=[
            'Code NACRES', 'Consommable',
            'Masse unitaire (g)', 'Matériau consommable',
            'Masse unitaire deuxieme materiaux (g)', 'Matériau deuxieme materiaux',
            'Masse emballage unitaire (g)', 'Matériau emballage',
            'Masse condionnement (g)', 'Matériau conditionnement',
            'Nbr par conditionnement',
        ])
    # ^ Par défaut : un DataFrame VIDE mais avec les bonnes colonnes.
    #   pd.DataFrame(columns=[...]) : crée un tableau à 0 lignes mais avec
    #   les colonnes définies. Utile pour les tests qui n'ont pas besoin de
    #   consommables solides : le code de production ne plantera pas en
    #   cherchant une colonne qui n'existe pas.

    dm.get_data_masse.return_value = data_masse

    # Constantes de colonnes — copiées depuis DataManager
    dm.CODE_NACRES_COL            = 'Code NACRES'
    dm.CONSOMMABLE_COL            = 'Consommable'
    dm.MASSE_G_COL                = 'Masse unitaire (g)'
    dm.MATERIAU_COL               = 'Matériau consommable'
    dm.MASSE_G2_COL               = 'Masse unitaire deuxieme materiaux (g)'
    dm.MATERIAU2_COL              = 'Matériau deuxieme materiaux'
    dm.MASSE_EMBALLAGE_COL        = 'Masse emballage unitaire (g)'
    dm.MATERIAU_EMBALLAGE_COL     = 'Matériau emballage'
    dm.MASSE_CONDITIONNEMENT_COL  = 'Masse condionnement (g)'
    dm.MATERIAU_CONDITIONNEMENT_COL = 'Matériau conditionnement'
    dm.NOMBRE_PAR_COND_COL        = 'Nbr par conditionnement'
    dm.MASSE_G3_COL               = 'Masse unitaire troisième materiaux (g)'
    dm.MATERIAU3_COL              = 'Matériau troisième materiaux'
    # ^ Dans le vrai DataManager, ces constantes sont définies comme attributs de classe :
    #       class DataManager:
    #           CODE_NACRES_COL = 'Code NACRES'
    #           ...
    #   CarbonCalculator les lit avec dm.CODE_NACRES_COL, dm.MASSE_G_COL, etc.
    #   Le MagicMock ne les a pas par défaut, donc on les branche à la main.
    #   Si on oubliait une constante, CarbonCalculator retournerait un MagicMock
    #   au lieu d'une string, et le test planterait avec une erreur bizarre.

    def _nacres_code_mask(series, code_nacres):
        code = str(code_nacres or '').strip().upper()
        prefix = code[:4]
        clean = series.fillna('').astype(str).str.strip().str.upper()
        return (clean == code) | (clean.str[:4] == prefix)

    dm.nacres_code_mask.side_effect = _nacres_code_mask
    # ^ Ici on n'utilise PAS return_value mais side_effect.
    #
    #   Différence cruciale :
    #     return_value  → retourne toujours la même valeur fixe, peu importe les arguments
    #     side_effect   → exécute UNE VRAIE FONCTION à chaque appel, avec les vrais arguments
    #
    #   nacres_code_mask() doit vraiment filtrer une série pandas selon un code.
    #   Si on utilisait return_value, on devrait deviner à l'avance ce qu'elle retourne.
    #   Avec side_effect, on branche une vraie implémentation simplifiée — elle calcule
    #   vraiment le masque booléen.
    #
    #   "masque booléen" : une Series de True/False de la même longueur qu'un DataFrame.
    #   Exemple : [True, False, True] → sélectionne la 1ère et 3ème ligne.

    if material_map is not None:
        def _get_material(name):
            return material_map.get(name, (None, None))
        dm.get_material_data.side_effect = _get_material
    else:
        dm.get_material_data.return_value = (None, None)
    # ^ Deux cas :
    #   - Si on a fourni un material_map (dict), on branche une fonction qui
    #     fait la lookup dans ce dict. Ex : material_map={'Plastique': (2.0, 0.1)}
    #     → dm.get_material_data('Plastique') retourne (2.0, 0.1)
    #     → dm.get_material_data('Inconnu')   retourne (None, None)
    #   - Si material_map est None (par défaut), toutes les lookups retournent (None, None).
    #     Utile pour les tests où les matériaux ne sont pas importants.

    dm.get_liquid_data.return_value = liquid_row
    # ^ Si liquid_row est None (défaut) : dm.get_liquid_data() retourne None.
    #   Si on passe une pd.Series, dm.get_liquid_data() retourne cette Series.

    return dm
    # ^ On retourne le MagicMock configuré. Il se comporte comme un vrai DataManager
    #   pour tout ce que CarbonCalculator va lui demander.


# ──────────────────────────────────────────────────────────────────────────────
# GROUPE 1 : TestMachine
# ──────────────────────────────────────────────────────────────────────────────

class TestMachine(unittest.TestCase):
# ^ On définit une classe qui hérite de unittest.TestCase.
#   "hérite" : TestMachine récupère toutes les méthodes de TestCase,
#   notamment assertEqual, assertAlmostEqual, assertIsNone, etc.
#   unittest.TestCase, c'est la classe mère fournie par Python qui fait
#   tout le travail de détection et d'exécution des tests.
#   pytest sait aussi lire les classes TestCase sans avoir besoin de rien ajouter.

    def _make_main_data_elec(self, factor=0.4, uncert=0.1):
        return pd.DataFrame({
            'category':    ['Électricité'],
            'subcategory': [''],
            'name':        ['Réseau France'],
            'total':       [factor],
            'uncertainty': [uncert],
        })
    # ^ Méthode helper PRIVÉE à cette classe (convention : nom commence par _).
    #   Elle n'est pas un test (ne commence pas par "test_"), pytest l'ignorera.
    #   Son rôle : éviter de dupliquer la construction du DataFrame dans chaque test.
    #   Le paramètre `self` : obligatoire dans toute méthode d'une classe Python,
    #   il représente l'instance elle-même (comme "this" en Java/JS).

    def test_machine_calcul_nominal(self):
        """kWh × facteur = émissions correctes."""
        # ^ La docstring (entre """) décrit ce que le test vérifie.
        #   pytest l'affiche si le test échoue, ce qui aide à comprendre le problème.

        dm = _make_dm(main_data=self._make_main_data_elec(factor=0.4, uncert=0.1))
        # ^ On crée le faux DataManager avec un facteur électricité de 0.4 kgCO₂/kWh.
        #   On passe main_data= explicitement pour remplacer le DataFrame par défaut
        #   (qui ne contenait pas de catégorie "Électricité").

        calc = CarbonCalculator(dm)
        # ^ On instancie le VRAI CarbonCalculator avec le faux DataManager.
        #   C'est ça, le test unitaire : on isole CarbonCalculator en lui donnant
        #   de fausses dépendances contrôlées.

        result = calc.compute_emission_data({
            'category': 'Machine',
            'electricity_type': 'Réseau France',
            'value': 10.0,
        })
        # ^ On appelle la vraie méthode de calcul avec un dictionnaire de saisie.
        #   10.0 représente 10 kWh consommés par la machine.

        ep, ep_err, em, em_err, tm, msg = result
        # ^ Déballage du tuple retourné ("tuple unpacking").
        #   compute_emission_data retourne 6 valeurs dans un tuple.
        #   On les récupère dans 6 variables en une ligne.
        #   ep     = émissions électricité (kgCO₂)
        #   ep_err = incertitude sur ep
        #   em     = émissions matériaux (0 pour une machine)
        #   em_err = incertitude sur em
        #   tm     = masse totale
        #   msg    = message d'erreur (None si tout va bien)

        self.assertAlmostEqual(ep, 4.0)
        # ^ assertAlmostEqual vérifie que ep ≈ 4.0 (à 7 décimales près par défaut).
        #   On utilise ça plutôt que assertEqual pour les floats car :
        #     0.1 + 0.2 == 0.3   →  False en Python !  (imprécision float)
        #     assertAlmostEqual(0.1 + 0.2, 0.3)  →  OK
        #   Calcul attendu : 10 kWh × 0.4 kgCO₂/kWh = 4.0 kgCO₂

        self.assertAlmostEqual(ep_err, 0.4)
        # ^ Incertitude = émission × taux d'incertitude = 4.0 × 0.1 = 0.4

        self.assertEqual(em, 0.0)
        # ^ Pas de matériau → émission matériaux = 0. Ici assertEqual est ok (0.0 exact).

        self.assertIsNone(msg)
        # ^ Pas d'erreur → msg doit être None (pas un string d'erreur).

    def test_machine_type_elec_inconnu(self):
        """Facteur introuvable → message d'erreur, résultat nul."""
        dm = _make_dm(main_data=self._make_main_data_elec())
        calc = CarbonCalculator(dm)
        ep, ep_err, em, em_err, tm, msg = calc.compute_emission_data({
            'category': 'Machine',
            'electricity_type': 'Énergie inconnue',  # ← n'existe pas dans main_data
            'value': 10.0,
        })
        self.assertEqual(ep, 0.0)
        # ^ Facteur inconnu → impossible de calculer → émission = 0.

        self.assertIsNotNone(msg)
        # ^ assertIsNotNone : vérifie que msg n'est PAS None.
        #   On ne teste pas le texte exact du message (il peut changer),
        #   juste qu'il y en a un — ça confirme que le code a bien détecté l'erreur.


# ──────────────────────────────────────────────────────────────────────────────
# GROUPE 2 : TestVehicules
# ──────────────────────────────────────────────────────────────────────────────

class TestVehicules(unittest.TestCase):

    def _main_data_vehicule(self, factor=0.25):
        return pd.DataFrame({
            'category':        ['Véhicules'],
            'subcategory':     ['Voiture'],
            'subsubcategory':  [''],
            'name':            ['Voiture essence'],
            'year':            [''],
            'total':           [factor],    # 0.25 kgCO₂/km
            'uncertainty':     [0.0],
            'unit':            ['km'],
        })

    def test_vehicule_multiplie_par_days(self):
        """val (km/jour) × days doit être multiplié dans le calcul."""
        dm = _make_dm(main_data=self._main_data_vehicule(factor=0.25))
        calc = CarbonCalculator(dm)

        ep, *_, msg = calc.compute_emission_data({
            'category': 'Véhicules',
            'subcategory': 'Voiture',
            'subsubcategory': '',
            'name': 'Voiture essence',
            'year': '',
            'value': 100.0,   # 100 km/jour
            'days': 5,
            'code_nacres': 'NA',
        })
        # ^ ep, *_, msg  : une autre syntaxe de déballage.
        #   ep   = première valeur du tuple
        #   *_   = "le reste" (toutes les valeurs du milieu), qu'on ignore (convention _)
        #   msg  = dernière valeur du tuple
        #   C'est utile quand on n'a besoin que de la première et de la dernière valeur.

        # total_value = 100 km/jour × 5 jours = 500 km
        # ep = 500 km × 0.25 kgCO₂/km = 125 kgCO₂
        self.assertAlmostEqual(ep, 125.0)
        self.assertIsNone(msg)

    def test_vehicule_valeur_stockee_est_km_par_jour(self):
        """Après édition, 'value' doit rester km/jour (pas km total)."""
        dm = _make_dm(main_data=self._main_data_vehicule(factor=0.25))
        calc = CarbonCalculator(dm)

        data = {
            'category': 'Véhicules',
            'subcategory': 'Voiture',
            'subsubcategory': '',
            'name': 'Voiture essence',
            'year': '',
            'value': 100.0,
            'days': 5,
            'code_nacres': 'NA',
        }
        ep1, *_ = calc.compute_emission_data(data)
        ep2, *_ = calc.compute_emission_data(data)
        # ^ On appelle compute_emission_data DEUX FOIS avec le MÊME dict.
        #   Pourquoi ? On vérifie que la fonction n'a pas MODIFIÉ le dict en place
        #   lors du premier appel (ex : data['value'] *= days, ce qui ferait que
        #   le deuxième appel calculerait 100×5×5 = 2500 km au lieu de 500).
        #   C'est un test d'idempotence : appeler N fois = même résultat que 1 fois.
        #   "Idempotent" : terme technique qui signifie "le résultat ne change pas
        #   si on répète l'opération".

        self.assertAlmostEqual(ep1, ep2, msg="Résultat doit être idempotent")
        # ^ Le paramètre msg= dans assertAlmostEqual : c'est le message affiché
        #   si le test échoue. Aide à comprendre pourquoi sans relire le code.


# ──────────────────────────────────────────────────────────────────────────────
# GROUPE 3 : TestMassBasedEmissions
# ──────────────────────────────────────────────────────────────────────────────

class TestMassBasedEmissions(unittest.TestCase):

    def _make_data_masse(self, masse_g=50.0, materiau='Plastique', masse_emb=10.0, mat_emb='Carton'):
        return pd.DataFrame([{
            'Code NACRES': 'AA01',
            'Consommable': 'Tube Eppendorf',
            'Masse unitaire (g)': masse_g,
            'Matériau consommable': materiau,
            'Masse unitaire deuxieme materiaux (g)': 0.0,
            'Matériau deuxieme materiaux': '',
            'Masse emballage unitaire (g)': masse_emb,
            'Matériau emballage': mat_emb,
            'Masse condionnement (g)': 0.0,
            'Matériau conditionnement': '',
            'Nbr par conditionnement': 1,
        }])
        # ^ pd.DataFrame([{...}]) : on passe une LISTE de dicts.
        #   Chaque dict = une ligne. Ici il n'y a qu'une ligne.
        #   C'est l'équivalent d'un tableau Excel avec 1 seule ligne de données.

    def test_calcul_nominal_deux_materiaux(self):
        """Produit + emballage → somme des émissions."""
        dm = _make_dm(
            data_masse=self._make_data_masse(masse_g=50.0, materiau='Plastique',
                                              masse_emb=10.0, mat_emb='Carton'),
            material_map={
                'Plastique': (2.0, 0.1),   # 2.0 kgCO₂/kg, incertitude 10%
                'Carton':    (1.0, 0.05),  # 1.0 kgCO₂/kg, incertitude 5%
            }
        )
        # ^ On configure le mock avec :
        #   - Un consommable "Tube Eppendorf" : 50g plastique + 10g carton
        #   - Les facteurs CO₂ des deux matériaux

        calc = CarbonCalculator(dm)
        emission, masse, unc, missing = calc._calculate_mass_based_emissions_old(
            'AA01', 'Tube Eppendorf', quantity=10
        )
        # ^ On appelle directement une méthode "interne" de CarbonCalculator.
        #   Le _ au début du nom (_calculate_mass_based_emissions_old) est la
        #   convention Python pour "méthode privée" = pas censée être appelée
        #   depuis l'extérieur de la classe. Mais en test, on peut quand même le faire
        #   pour tester une partie précise du calcul.
        #   C'est utile pour tester un cas difficile à déclencher autrement.
        #
        #   Les 4 valeurs retournées :
        #   emission = kgCO₂ total
        #   masse    = kg total de matière
        #   unc      = incertitude
        #   missing  = liste des matériaux dont le facteur CO₂ est inconnu

        # Calcul manuel qu'on vérifie :
        # Plastique : 10 tubes × 50g ÷ 1000 = 0.5 kg × 2.0 kgCO₂/kg = 1.0 kgCO₂
        # Carton    : 10 tubes × 10g ÷ 1000 = 0.1 kg × 1.0 kgCO₂/kg = 0.1 kgCO₂
        # Total émission = 1.1 kgCO₂  /  Total masse = 0.6 kg
        self.assertAlmostEqual(emission, 1.1)
        self.assertAlmostEqual(masse, 0.6)
        self.assertEqual(missing, [])
        # ^ assertEqual sur une liste vide : vérifie qu'aucun matériau n'est inconnu.

    def test_materiau_manquant_signale_et_non_comptabilise(self):
        """Matériau absent → apparaît dans missing, masse NON comptée."""
        dm = _make_dm(
            data_masse=self._make_data_masse(masse_g=50.0, materiau='MatériauInconnu',
                                              masse_emb=10.0, mat_emb='Carton'),
            material_map={
                'Carton': (1.0, 0.0),
                # 'MatériauInconnu' absent intentionnellement
            }
        )
        calc = CarbonCalculator(dm)
        emission, masse, unc, missing = calc._calculate_mass_based_emissions_old(
            'AA01', 'Tube Eppendorf', quantity=10
        )
        self.assertAlmostEqual(emission, 0.1)     # seul Carton contribue
        self.assertAlmostEqual(masse, 0.1)        # masse plastique ignorée car inconnu
        self.assertIn('MatériauInconnu', missing)
        # ^ assertIn(a, b) : vérifie que a est dans b.
        #   Ici : que la string 'MatériauInconnu' est dans la liste missing.
        #   Équivalent de : self.assertTrue('MatériauInconnu' in missing)

    def test_materiau_manquant_masse_non_comptee(self):
        """Régression bug #1 : la masse du composant inconnu ne doit pas être dans le total."""
        # ^ "Régression" = un bug qui avait été corrigé mais qui pourrait réapparaître.
        #   Un test de régression documente le bug et s'assure qu'il ne revient pas.
        dm = _make_dm(
            data_masse=self._make_data_masse(masse_g=500.0, materiau='Inconnu',
                                              masse_emb=0.0, mat_emb=''),
            material_map={}   # aucun matériau connu du tout
        )
        calc = CarbonCalculator(dm)
        _, masse, _, missing = calc._calculate_mass_based_emissions_old(
            'AA01', 'Tube Eppendorf', quantity=1
        )
        # ^ _ (underscore seul) : convention pour "je reçois cette valeur
        #   mais je ne l'utilise pas". Ici on ne teste que masse et missing.

        self.assertEqual(masse, 0.0, "La masse ne doit pas être comptée si le matériau est inconnu")
        # ^ Le 3ème argument de assertEqual est un message d'échec personnalisé.
        #   Si masse != 0.0, pytest affichera ce message pour expliquer le problème.

        self.assertIn('Inconnu', missing)

    def test_nan_dans_masse_traite_comme_zero(self):
        """Régression bug NaN : une masse NaN ne doit pas propager NaN."""
        # ^ NaN = Not a Number. Dans un DataFrame pandas, une cellule vide ou
        #   invalide est souvent représentée par float('nan').
        #   Le danger : NaN est "contagieux" — n'importe quelle opération avec NaN
        #   retourne NaN (NaN + 5 = NaN, NaN × 2 = NaN).
        #   Ce test vérifie que le code gère proprement ce cas.

        df = pd.DataFrame([{
            'Code NACRES': 'AA01',
            'Consommable': 'Tube Eppendorf',
            'Masse unitaire (g)': float('nan'),      # ← masse invalide
            'Matériau consommable': 'Plastique',
            'Masse unitaire deuxieme materiaux (g)': float('nan'),
            'Matériau deuxieme materiaux': '',
            'Masse emballage unitaire (g)': 10.0,    # ← emballage normal
            'Matériau emballage': 'Carton',
            'Masse condionnement (g)': float('nan'),
            'Matériau conditionnement': '',
            'Nbr par conditionnement': 1,
        }])
        # ^ float('nan') : crée explicitement une valeur NaN en Python.
        #   On teste le pire cas : presque toutes les masses sont NaN.

        dm = _make_dm(
            data_masse=df,
            material_map={'Plastique': (2.0, 0.1), 'Carton': (1.0, 0.0)}
        )
        calc = CarbonCalculator(dm)
        emission, masse, unc, missing = calc._calculate_mass_based_emissions_old(
            'AA01', 'Tube Eppendorf', quantity=5
        )
        self.assertFalse(math.isnan(emission), "emission ne doit pas être NaN")
        # ^ assertFalse(x) : vérifie que x est False (ou falsy).
        #   math.isnan(emission) retourne True si emission est NaN.
        #   assertFalse(math.isnan(...)) : "le résultat ne doit PAS être NaN".
        #   C'est l'inverse de assertTrue — on vérifie qu'une condition est fausse.

        self.assertFalse(math.isnan(masse), "masse ne doit pas être NaN")
        self.assertEqual(missing, [])
        # ^ Les NaN ne doivent pas créer de "matériau manquant" non plus.

    def test_code_nacres_na_retourne_zero(self):
        """Code NACRES 'NA' → résultat nul sans erreur."""
        # ^ Code NACRES 'NA' : valeur spéciale dans l'appli qui signifie
        #   "pas de consommable associé". Le calcul masse doit simplement
        #   retourner 0 sans essayer de chercher quoi que ce soit.
        dm = _make_dm()   # mock minimal, pas de data_masse particulière
        calc = CarbonCalculator(dm)
        emission, masse, unc, missing = calc._calculate_mass_based_emissions_old('NA', 'x', 1)
        self.assertEqual(emission, 0.0)
        self.assertEqual(masse, 0.0)
        self.assertEqual(missing, [])

    def test_consommable_introuvable_retourne_zero(self):
        """Consommable absent de data_masse → résultat nul."""
        dm = _make_dm(data_masse=self._make_data_masse())
        # ^ data_masse contient 'AA01 / Tube Eppendorf', rien d'autre.
        calc = CarbonCalculator(dm)
        emission, masse, unc, missing = calc._calculate_mass_based_emissions_old(
            'ZZ99', 'Inconnu', quantity=5
        )
        # ^ On cherche un code NACRES 'ZZ99' qui n'existe pas dans data_masse.
        self.assertEqual(emission, 0.0)
        self.assertEqual(missing, [])
        # ^ Pas d'erreur, juste 0 : le code gère silencieusement les absences.


# ──────────────────────────────────────────────────────────────────────────────
# GROUPE 4 : TestLiquidEmissions
# ──────────────────────────────────────────────────────────────────────────────

class TestLiquidEmissions(unittest.TestCase):

    def test_calcul_nominal_liquide(self):
        """volume (mL) × densité × facteur CO2 → émissions."""
        liquid_row = pd.Series({
            'Code NACRES': 'LA01',
            'Densité (g/mL)': 0.8,
            'Facteur CO₂ (kg CO₂e/kg)': 3.0,
            'Incertitude (%)': 10.0,
        })
        # ^ pd.Series({...}) : comme un DataFrame à une seule ligne,
        #   ou un dictionnaire avec des types homogènes.
        #   Ici ça représente une ligne de la table des liquides.

        dm = _make_dm(liquid_row=liquid_row)
        calc = CarbonCalculator(dm)
        emission, masse, err = calc._calculate_liquid_emissions('LA01', volume_ml=500)

        # Calcul manuel :
        # masse   = densité × volume = 0.8 g/mL × 500 mL = 400 g = 0.4 kg
        # emission = masse × facteur = 0.4 kg × 3.0 kgCO₂/kg = 1.2 kgCO₂
        # err     = emission × incertitude = 1.2 × 10% = 0.12 kgCO₂
        self.assertAlmostEqual(masse, 0.4)
        self.assertAlmostEqual(emission, 1.2)
        self.assertAlmostEqual(err, 0.12)

    def test_liquide_introuvable_retourne_zero(self):
        """Code NACRES absent → résultat nul."""
        dm = _make_dm(liquid_row=None)
        # ^ liquid_row=None → dm.get_liquid_data() retournera None.
        #   On simule le cas où le liquide n'est pas dans la base.
        calc = CarbonCalculator(dm)
        emission, masse, err = calc._calculate_liquid_emissions('ZZ99', volume_ml=100)
        self.assertEqual(emission, 0.0)
        self.assertEqual(masse, 0.0)


# ──────────────────────────────────────────────────────────────────────────────
# GROUPE 5 : TestGetMaterialData
# ──────────────────────────────────────────────────────────────────────────────

class TestGetMaterialData(unittest.TestCase):
    """Tests directs sur DataManager.get_material_data (pas de mock)."""
    # ^ Différence avec les groupes précédents :
    #   ici on teste le VRAI DataManager (une méthode précise),
    #   et c'est CarbonCalculator qui est absent.
    #   Pas de règle absolue sur ce qu'on doit mocker — l'objectif est
    #   toujours d'isoler la logique qu'on veut vérifier.

    def _make_real_dm(self, co2_value, uncert_value):
        from ui.data_manager import DataManager
        # ^ Import local à la méthode (pas en haut du fichier).
        #   Ça fonctionne, Python permet ça. C'est utile pour retarder l'import
        #   ou l'isoler dans la méthode qui en a besoin.

        dm = DataManager.__new__(DataManager)
        # ^ DataManager.__new__(DataManager) : instancie la classe SANS appeler __init__.
        #   __init__ lirait les vrais fichiers HDF5 → on ne veut pas ça en test.
        #   __new__ est la méthode de bas niveau qui alloue la mémoire pour l'objet,
        #   AVANT que __init__ soit appelé. En l'appelant directement, on crée
        #   un objet DataManager "vide", qu'on remplit ensuite à la main.

        dm.data_materials = pd.DataFrame([{
            'Materiau': 'Plastique',
            'Equivalent CO₂ (kg eCO₂/kg)': co2_value,
            'uncertainty': uncert_value,
        }])
        dm.MATERIAU_NAME_COL = 'Materiau'
        dm.EQUIV_CO2_COL     = 'Equivalent CO₂ (kg eCO₂/kg)'
        dm.UNCERTAINTY_COL   = 'uncertainty'
        # ^ On injecte directement les données et les constantes de colonnes
        #   dont get_material_data() a besoin pour fonctionner.
        #   Le reste de DataManager n'existe pas — si get_material_data() essayait
        #   d'utiliser autre chose, Python lèverait une AttributeError.

        return dm

    def test_valeur_normale(self):
        dm = self._make_real_dm(co2_value=2.5, uncert_value=0.1)
        co2, unc = dm.get_material_data('Plastique')
        self.assertAlmostEqual(co2, 2.5)
        self.assertAlmostEqual(unc, 0.1)

    def test_co2_nan_retourne_zero(self):
        """Régression : NaN dans la colonne CO2 → 0.0, pas NaN."""
        dm = self._make_real_dm(co2_value=float('nan'), uncert_value=0.1)
        co2, unc = dm.get_material_data('Plastique')
        self.assertFalse(math.isnan(co2), "co2 ne doit pas être NaN")
        self.assertEqual(co2, 0.0)

    def test_incert_nan_retourne_zero(self):
        """Régression : NaN dans l'incertitude → 0.0, pas NaN."""
        dm = self._make_real_dm(co2_value=2.5, uncert_value=float('nan'))
        co2, unc = dm.get_material_data('Plastique')
        self.assertFalse(math.isnan(unc), "incertitude ne doit pas être NaN")
        self.assertEqual(unc, 0.0)

    def test_materiau_inconnu_retourne_none(self):
        dm = self._make_real_dm(co2_value=2.5, uncert_value=0.1)
        co2, unc = dm.get_material_data('MatériauInexistant')
        self.assertIsNone(co2)
        self.assertIsNone(unc)

    def test_materiau_nan_retourne_none(self):
        dm = self._make_real_dm(co2_value=2.5, uncert_value=0.1)
        co2, unc = dm.get_material_data(float('nan'))
        # ^ On passe NaN comme NOM de matériau. Cas limite : que se passe-t-il si
        #   une cellule "nom de matériau" est vide/NaN dans le DataFrame source ?
        self.assertIsNone(co2)

    def test_materiau_non_string_retourne_none(self):
        dm = self._make_real_dm(co2_value=2.5, uncert_value=0.1)
        co2, unc = dm.get_material_data(42)
        # ^ On passe un entier au lieu d'une string. Cas défensif :
        #   la méthode doit survivre aux types inattendus.
        self.assertIsNone(co2)


# ──────────────────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    unittest.main()
# ^ Permet d'exécuter ce fichier directement :
#     python tests/test_carbon_calculator.py
#   unittest.main() détecte et lance tous les tests du fichier.
#   Avec pytest (python -m pytest tests/), cette ligne est ignorée —
#   pytest a son propre mécanisme de découverte.
