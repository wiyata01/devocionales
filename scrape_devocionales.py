#!/usr/bin/env python3
"""
scrape_devocionales.py
-----------------------
Visita las 3 páginas fuente (siempre muestran el devocional "de hoy" en la
misma URL), extrae título, versículo, texto y audio, y escribe data.json.

Pensado para correr una vez al día vía GitHub Actions (ver
.github/workflows/update-devocionales.yml), pero también puedes ejecutarlo
a mano:  python3 scrape_devocionales.py

IMPORTANTE: este script fue escrito revisando el HTML de cada sitio el
15-ago-2026. Si un sitio rediseña su página, los selectores de esa función
(y solo esa) pueden necesitar un ajuste. Cada función tiene comentarios de
dónde mirar si deja de funcionar (usa "Inspeccionar" en el navegador sobre
el título / versículo / audio).
"""

import json
import re
import sys
import datetime
import unicodedata

import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; DevocionalesBot/1.0)"}
TIMEOUT = 20


def clean(text: str) -> str:
    """Colapsa espacios/saltos de línea sobrantes."""
    return re.sub(r"\s+", " ", text or "").strip()


def get_soup(url: str) -> BeautifulSoup:
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


# ---------------------------------------------------------------------------
# 1) EN CONTACTO (Charles Stanley)
# ---------------------------------------------------------------------------
def scrape_encontacto():
    url = "https://www.encontacto.org/lea/devocionales-diarios"
    soup = get_soup(url)
    html = str(soup)

    h1 = soup.find("h1")
    title = clean(h1.get_text()) if h1 else ""

    h2 = soup.find("h2")
    subtitle = clean(h2.get_text()) if h2 else ""

    # Referencia bíblica: normalmente el primer enlace en negrita hacia
    # biblegateway.com, justo debajo del título.
    verse = ""
    verse_link = soup.find("a", href=re.compile(r"biblegateway\.com"))
    if verse_link:
        verse = clean(verse_link.get_text())

    # Audio mp3 (hospedado en intouch.azureedge.net)
    audio = ""
    m = re.search(r"https://intouch\.azureedge\.net/spanish/devo/[\w\-.]+\.mp3", html)
    if m:
        audio = m.group(0)

    # Cuerpo del texto: párrafos y viñetas entre el versículo y "BIBLIA EN UN AÑO"
    paragraphs = []
    for tag in soup.find_all(["p", "li"]):
        t = clean(tag.get_text())
        if not t or t == verse:
            continue
        if "BIBLIA EN UN" in t.upper():
            break
        if "suscríbase" in t.lower() or "suscribir" in t.lower():
            continue
        paragraphs.append(t)
        if len(paragraphs) >= 8:
            break

    return {
        "titulo": title or subtitle,
        "subtitulo": subtitle if title else "",
        "versiculo": verse,
        "parrafos": paragraphs,
        "audio_url": audio,
        "audio_tipo": "mp3",
        "link": url,
    }


# ---------------------------------------------------------------------------
# 2) BAYLESS CONLEY
# ---------------------------------------------------------------------------
def scrape_bayless():
    # Este enlace siempre redirige al devocional más reciente
    landing = "https://www.respuestasbc.com/?redirect_to=latest&post_type=devotional"
    r = requests.get(landing, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    final_url = r.url
    soup = BeautifulSoup(r.text, "html.parser")

    h1 = soup.find("h1")
    title = clean(h1.get_text()) if h1 else ""

    # El cuerpo del devocional vive en párrafos normales del artículo.
    paragraphs = []
    for p in soup.find_all("p"):
        t = clean(p.get_text())
        if not t:
            continue
        low = t.lower()
        if "escuche este devocional" in low:
            break
        if "suscrib" in low or "recibir devocionales" in low:
            continue
        paragraphs.append(t)

    # Enlace de audio (SoundCloud)
    audio = ""
    sc_link = soup.find("a", href=re.compile(r"soundcloud\.com"))
    if sc_link:
        audio = sc_link["href"]

    return {
        "titulo": title,
        "subtitulo": "",
        "versiculo": "",
        "parrafos": paragraphs,
        "audio_url": audio,
        "audio_tipo": "soundcloud",
        "link": final_url,
    }


# ---------------------------------------------------------------------------
# 3) KENNETH COPELAND
# ---------------------------------------------------------------------------
def scrape_kenneth():
    # Intento 1: API REST de WordPress (el sitio corre en WP; suele exponer
    # /wp-json/wp/v2/devotional). Es más confiable que raspar HTML.
    try:
        api = "https://main.kcmlatino.org/wp-json/wp/v2/devotional?per_page=1&orderby=date&order=desc"
        r = requests.get(api, headers=HEADERS, timeout=TIMEOUT)
        if r.ok and r.json():
            post = r.json()[0]
            title = clean(BeautifulSoup(post["title"]["rendered"], "html.parser").get_text())
            body_soup = BeautifulSoup(post["content"]["rendered"], "html.parser")
            paragraphs = [clean(p.get_text()) for p in body_soup.find_all("p") if clean(p.get_text())]
            link = post.get("link", "https://main.kcmlatino.org/devocional")
            audio = _find_kcm_audio(link)
            verse = paragraphs[0] if paragraphs and len(paragraphs[0]) < 160 and "«" in paragraphs[0] else ""
            return {
                "titulo": title,
                "subtitulo": "",
                "versiculo": verse,
                "parrafos": paragraphs,
                "audio_url": audio,
                "audio_tipo": "mp3",
                "link": link,
            }
    except Exception:
        pass  # cae al plan B

    # Intento 2 (respaldo): raspar la página listado /devocional y seguir el
    # primer enlace a un devotional individual.
    soup = get_soup("https://main.kcmlatino.org/devocional")
    first_link = soup.find("a", href=re.compile(r"/devotional/[\w\-]+/?$"))
    if not first_link:
        raise RuntimeError("No se encontró enlace a devocional de Kenneth Copeland")
    return _scrape_kcm_post(first_link["href"])


def _scrape_kcm_post(url):
    soup = get_soup(url)
    h1 = soup.find("h1")
    title = clean(h1.get_text()) if h1 else ""
    paragraphs = [clean(p.get_text()) for p in soup.find_all("p") if clean(p.get_text())]
    audio = _find_kcm_audio(url, soup)
    verse = paragraphs[0] if paragraphs and "«" in paragraphs[0] else ""
    return {
        "titulo": title,
        "subtitulo": "",
        "versiculo": verse,
        "parrafos": paragraphs,
        "audio_url": audio,
        "audio_tipo": "mp3",
        "link": url,
    }


def _find_kcm_audio(url, soup=None):
    if soup is None:
        soup = get_soup(url)
    html = str(soup)
    m = re.search(r"https://maincms\.nyc3\.digitaloceanspaces\.com/[\w/\-.]+\.mp3", html)
    return m.group(0) if m else ""


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def main():
    today = datetime.date.today()
    meses = ["enero","febrero","marzo","abril","mayo","junio","julio",
             "agosto","septiembre","octubre","noviembre","diciembre"]
    fecha_es = f"{today.day} de {meses[today.month-1]} de {today.year}"

    data = {"fecha": fecha_es, "generado": datetime.datetime.utcnow().isoformat() + "Z"}

    fuentes = {
        "encontacto": scrape_encontacto,
        "bayless": scrape_bayless,
        "kenneth": scrape_kenneth,
    }

    errores = []
    for clave, fn in fuentes.items():
        try:
            data[clave] = fn()
            print(f"OK  - {clave}: {data[clave]['titulo']!r}")
        except Exception as e:
            errores.append(f"{clave}: {e}")
            print(f"FAIL - {clave}: {e}", file=sys.stderr)
            # Deja el campo ausente en vez de romper todo el archivo;
            # el frontend debe manejar la ausencia con un mensaje amable.
            data[clave] = None

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    if errores:
        print("\nAlgunas fuentes fallaron hoy:\n - " + "\n - ".join(errores), file=sys.stderr)
        # No usamos sys.exit(1) para que el workflow igual publique lo que
        # sí se pudo obtener, en vez de dejar el sitio sin actualizar.


if __name__ == "__main__":
    main()
