# Scraper prudent de references fournisseurs

Ce module sert a constituer progressivement une base de references fournisseurs
utilisable par LABeCO2, sans aspirer massivement les catalogues et sans stocker
les prix publics dans la base distribuee.

## Principes

- Les fournisseurs sont des sources de references, pas des donnees validees.
- Les fournisseurs doivent rester limites a quelques URLs utiles dans `config.yaml`.
- Le scraper ne contourne pas les protections: pas de CAPTCHA bypass, pas de VPN,
  pas d'authentification simulee.
- Les requetes sont lentes et sequentielles: delai configure entre 10 et 30 s.
- Les codes HTTP `403` et `429`, ou une page de blocage evidente, arretent le run.
- Les pages HTML sont mises en cache localement pour eviter les rechargements.
- Les prix ne sont pas stockes comme valeurs de reference. Seuls
  `price_publicly_visible` et `currency_detected` indiquent si un prix semble
  visible publiquement au moment du passage.
- Une base SQLite privee peut capturer les observations larges, prix inclus,
  dans `private/supplier_scraping_lab.sqlite`. Elle sert au tri interne et ne doit
  pas etre distribuee.

## Tables ajoutees a la base LABeCO2

Les tables sont creees par `ui.sqlite_schema.ensure_app_schema`, donc le scraper
reste integre a la base LABeCO2 existante:

- `supplier_generic_products`: produit generique court.
- `supplier_references`: reference fournisseur, URL, conditionnement, indicateurs.
- `supplier_price_cache`: cache local date pour prix recuperes plus tard par
  l'utilisateur.
- `supplier_scrape_runs`: historique des runs.
- `supplier_fetch_log`: journal des URLs chargees, ignorees ou bloquees.

La cle principale metier de reference est `supplier + supplier_product_ref`.
Une meme URL peut exposer plusieurs variantes fournisseur, donc l'URL est indexee
pour la recherche mais n'est pas unique.

## Base privee de capture

`local_capture` dans `config.yaml` active une base SQLite a part:

- `supplier_scrape_observations`: capture large des champs observes, URL, hash,
  chemin du cache HTML, variantes detectees, attributs de variante, prix texte
  et prix numerique.
- `supplier_local_price_snapshots`: historique local des prix observes.

Par defaut, `dry_run: true` empeche l'ecriture dans la base LABeCO2. Avec
`local_capture.capture_during_dry_run: true`, le scraper peut quand meme ecrire
dans cette base privee pour eviter de refaire plusieurs fois les memes passages.

## Utilisation

Dry-run sans ecriture effective:

```bash
python -m tools.supplier_scraper.main \
  --config tools/supplier_scraper/config.yaml \
  --dry-run
```

Avec la configuration actuelle, cette commande n'ecrit pas dans la base LABeCO2,
mais alimente la base privee de capture `private/supplier_scraping_lab.sqlite`.

Exporter les references deja presentes:

```bash
python -m tools.supplier_scraper.main \
  --config tools/supplier_scraper/config.yaml \
  --export-csv exports/supplier_references.csv
```

Importer la base privee de capture vers la base LABeCO2 en apercu:

```bash
python tools/supplier_scraper/import_to_labeco2.py \
  --source-db private/supplier_scraping_lab.sqlite \
  --target-db private/labeco2.sqlite
```

Appliquer l'import apres verification de l'apercu:

```bash
python tools/supplier_scraper/import_to_labeco2.py \
  --source-db private/supplier_scraping_lab.sqlite \
  --target-db private/labeco2.sqlite \
  --apply
```

Cet import ne valide rien automatiquement. Il ajoute/met a jour les references
fournisseur, historise les prix observes dans `supplier_price_cache`, cree les
lignes de catalogue fournisseur, puis cree seulement des `commercial_products`
en statut `pending` quand la reference n'existe pas deja. Les produits valides
existants ne sont pas ecrases.

Pour activer un fournisseur, modifier `enabled: true` dans `config.yaml`, verifier
les domaines autorises, les URLs de depart et les regex d'extraction, puis lancer
d'abord en `--dry-run`.

La configuration contient actuellement un essai VWR limite a une seule URL produit:
`https://www.vwr.com/fr/en/product/9695384/vwr-nitrilelight-nitrile-gloves`.
Si VWR sert une coque JavaScript ou une page Cloudflare Turnstile sans contenu
produit exploitable, le scraper s'arrete proprement et ne cree pas de reference.

## Adaptation fournisseur

Chaque fournisseur de `config.yaml` declare:

- `start_urls`: pages publiques de recherche ou categorie a explorer.
- `allowed_domains`: domaines acceptes.
- `product_url_patterns`: regex identifiant les URLs produit.
- `crawl_url_patterns`: regex identifiant les pages de navigation autorisees.
- `deny_url_patterns`: regex a ignorer.
- `ref_patterns`, `name_patterns`, `packaging_patterns`: extraction produit.
- `url_ref_patterns`: fallback pour extraire une reference depuis l'URL produit.
- `variant_ref_patterns`: extraction des autres codes catalogue d'une meme
  famille produit. Pour Fisher, ce sont les references associees au meme produit
  decline en plusieurs tailles ou conditionnements.
- `generic_category`: categorie generique appliquee par defaut.

Le crawler peut partir d'une page de recherche ou de categorie si elle est ajoutee
dans `start_urls`. Il ne parcourt que les liens autorises par `allowed_domains`,
`crawl_url_patterns`, `product_url_patterns` et `deny_url_patterns`, avec les
limites `max_pages_per_run` et `max_products_per_run`. Pour un fournisseur reel,
il faut donc ajouter quelques pages de depart ciblees, pas la racine du site.

Les parsers doivent rester conservateurs: en cas de doute, laisser une valeur vide
et noter le contexte dans `scraping_notes` plutot que deviner.

## Tests

Les tests unitaires utilisent un HTML sauvegarde:

```bash
python -m pytest tests/test_supplier_scraper.py -q
```
