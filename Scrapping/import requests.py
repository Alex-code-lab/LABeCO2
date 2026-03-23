from playwright.sync_api import sync_playwright

url = "https://www.starlabgroup.com/FR-fr/product/200-ul-pointe-tipone-naturel-pf-sl-920673.html"

with sync_playwright() as p:

    browser = p.firefox.launch(
        headless=True
    )

    context = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
        locale="fr-FR"
    )

    page = context.new_page()

    page.goto(url, timeout=60000, wait_until="commit")

    page.wait_for_timeout(5000)

    html = page.content()

    page.screenshot(path="debug_page.png")

    print("Taille HTML:", len(html))

    import re

    texte = page.inner_text("body")

    match = re.search(r"(\d+[.,]\d+)\s*€", texte)

    if match:
        prix = float(match.group(1).replace(",", "."))
        print("Prix:", prix)
    else:
        print("Prix non trouvé")

    browser.close()