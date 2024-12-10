import matplotlib.colors

# Constantes de couleurs
CATEGORY_COLORS = {
    'Véhicules': '#2e8b57',          # Sea Green
    'Achats': '#07bc52',             # Green
    'Machine': '#20B2AA',            # Light Sea Green
    'Activités agricoles': '#4682B4',# Steel Blue
    'Infra. de recherche': '#0d89c8' # Deep Sky Blue
}

CATEGORY_ORDER = [
    'Véhicules',
    'Achats',
    'Machine',
    'Activités agricoles',
    'Infra. de recherche'
]

def generate_color_shades(base_color, num_shades):
    """
    Génère des nuances de couleur à partir d'une couleur de base.

    Paramètres :
    ------------
    base_color : str
        Couleur de base (hexadécimal ou nom HTML, ex : '#ff0000').
    num_shades : int
        Nombre de nuances à générer.

    Retour :
    --------
    list :
        Liste de couleurs en format hexadécimal.
    """
    base_rgb = matplotlib.colors.to_rgb(base_color)
    shades = []
    for i in range(num_shades):
        factor = 0.6 + 0.4 * (i / max(1, num_shades - 1))  # Variation entre 0.6 et 1
        shade = tuple(min(1, base_rgb[j] * factor + (1 - factor)) for j in range(3))
        shades.append(matplotlib.colors.to_hex(shade))
    return shades