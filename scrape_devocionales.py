#!/usr/bin/env python3
"""
Extrae texto 100% limpio y unificado para En Contacto, Bayless Conley y Kenneth Copeland.
"""

import datetime as dt
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from zoneinfo import ZoneInfo

DATA_FILE = Path("data.json")
TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36 "
        "DevocionalesDiariosBot/4.1"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

def create_session():
    s = requests.Session()
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update(HEADERS)
    return s

S = create_session()

def clean(text):
    if not text:
        return ""
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()

def today_colombia():
    return dt.datetime.now(ZoneInfo("America/Bogota")).date()

def fecha_espanol(fecha=None):
    if fecha is None:
        fecha = today_colombia()
    meses = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ]
    return f"{fecha.day} de {meses[fecha.month - 1]} de {fecha.year}"

def url_no_cache(url):
    separador = "&" if "?" in url else "?"
    ahora = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{url}{separador}_nocache={ahora}"

def get(url):
    final_url = url_no_cache(url)
    r = S.get(final_url, timeout=TIMEOUT, allow_redirects=True, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"})
    r.raise_for_status()
    return r

def clean_url(url):
    return re.sub(r"[?&]_nocache=\d+", "", url) if url else ""

def valid(item):
    return (
        isinstance(item, dict)
        and bool(item.get("titulo"))
        and isinstance(item.get("parrafos"), list)
        and any(clean(x) for x in item.get("parrafos", []))
    )

def es_extracto_relacionado(texto):
    texto_low = texto.lower()
    return len(texto_low) < 250 and re.search(r'(\.\.\.|…)\s*(?:leer m[aá]s|read more|\])?\s*$', texto_low)

def destroy_garbage(soup):
    for trash in soup.find_all(["div", "section", "aside", "footer", "ul", "nav"], class_=lambda c: c and any(k in str(c).lower() for k in ("related", "card", "sidebar", "footer", "recommended", "more-devotionals", "author-bio", "widget", "social", "share", "awac", "post-nav", "jp-relatedposts", "crp_related"))):
        trash.decompose()
    for trash in soup.find_all(id=lambda i: i and any(k in str(i).lower() for k in ("jp-relatedposts", "sharedaddy", "crp_related", "secondary", "sidebar"))):
        trash.decompose()
    for btn in soup.find_all(lambda tag: tag.name in ["a", "button", "div", "span"] and "compartir este devocional" in tag.get_text(strip=True).lower()):
        btn.decompose()

def scrape_encontacto():
    url = "https://www.encontactoglobal.org/lea/devocionales-diarios"
    r = get(url)
    s = BeautifulSoup(r.text, "html.parser")
    destroy_garbage(s)

    meditation_marker = None
    for tag in s.find_all(string=re.compile(r"^\s*Meditación diaria\s*$", re.I)):
        meditation_marker = tag.parent
        break

    title = ""
    if meditation_marker:
        for element in meditation_marker.find_all_next(["h1", "h2"]):
            texto = clean(element.get_text(" ", strip=True))
            if not texto or texto.lower() in {"opciones de lectura", "otros devocionales"}:
                continue
            title = texto
            break
    if not title and s.find("h1"):
        title = clean(s.find("h1").get_text(" ", strip=True))

    subtitle = ""
    verse = ""
    if meditation_marker:
        encontrado_title = False
        for element in meditation_marker.find_all_next(["h1", "h2"]):
            texto = clean(element.get_text(" ", strip=True))
            if texto == title:
                encontrado_title = True
                continue
            if encontrado_title and texto:
                subtitle = texto
                break
        for a in meditation_marker.find_all_next("a", href=True):
            if re.search(r"biblegateway\.com", a.get("href", ""), re.I):
                verse = clean(a.get_text(" ", strip=True))
                if verse: break

    audio = ""
    m_audio = re.search(r'(https?:\\?/\\?/[A-Za-z0-9_./-]*azureedge\.net[A-Za-z0-9_./-]+\.mp3)', str(s), re.I)
    if m_audio:
        audio = m_audio.group(1).replace("\\/", "/")

    title_tag = None
    for h in s.find_all(["h1", "h2"]):
        if clean(h.get_text(" ", strip=True)) == title:
            title_tag = h
            break

    paragraphs = []
    start_node = title_tag if title_tag else meditation_marker

    CORTAR_ENCONTACTO = (
        "biblia en un año", "otros devocionales", "opciones de lectura",
        "quiénes somos", "ministerios en contacto", "conectar", "participar",
        "suscríbase", "suscribirse", "correo electrónico", "artículos destacados"
    )

    if start_node:
        for element in start_node.find_all_next(["p", "li"]):
            if element.find_parent(["nav", "footer", "aside"]):
                continue

            texto = clean(element.get_text(" ", strip=True))
            low = texto.lower()

            if any(k in low for k in CORTAR_ENCONTACTO) or es_extracto_relacionado(texto):
                break

            if not texto or texto == verse or len(texto) < 15:
                continue
            
            # Limpiamos cualquier viñeta inicial si el sitio ya la traía pegada
            texto = re.sub(r"^[\•\-\*]\s*", "", texto)

            if texto not in paragraphs:
                paragraphs.append(texto)

    return {
        "titulo": title, "subtitulo": subtitle, "versiculo": verse,
        "parrafos": paragraphs[:20], "audio_url": audio, "audio_tipo": "mp3", "link": clean_url(r.url),
    }

def scrape_bayless():
    landing = "https://www.respuestasbc.com/?redirect_to=latest&post_type=devotional"
    r = get(landing)
    s = BeautifulSoup(r.text, "html.parser")
    destroy_garbage(s)

    title = ""
    article_title_tag = None
    for h1 in s.find_all("h1"):
        texto = clean(h1.get_text(" ", strip=True))
        if not texto or texto.lower() in {"devocional diario", "respuestas para cada día"}:
            continue
        title = clean(re.sub(r"^\s*#?\s*\d+\s*[-–—:.]?\s*", "", texto))
        article_title_tag = h1
        break

    paragraphs = []
    article = article_title_tag.find_parent("article") if article_title_tag else s

    CORTAR_BAYLESS = (
        "leer devocionales anteriores", "¿quieres respuestas directo",
        "suscríbete a nuestro devocional", "me gustaría recibir los correos",
        "powered by kit", "necesitas ayuda", "compartir este", "comparte este",
        "escuche este devocional", "haga click", "haga clic"
    )

    for element in article.find_all(["p", "blockquote"]):
        texto = clean(element.get_text(" ", strip=True))
        if not texto: continue
        low = texto.lower()

        if any(k in low for k in CORTAR_BAYLESS) or es_extracto_relacionado(texto):
            break

        if len(texto) < 25 or texto in paragraphs:
            continue

        paragraphs.append(texto)

    audio = ""
    for a in article.find_all("a", href=True):
        href = a.get("href", "").strip()
        if "soundcloud.com/respuestasbc/" in href.lower() and "/sets/" not in href.lower():
            audio = href
            break

    return {
        "titulo": title, "subtitulo": "", "versiculo": "",
        "parrafos": paragraphs[:20], "audio_url": audio, "audio_tipo": "soundcloud", "link": clean_url(r.url),
    }

def scrape_kenneth():
    url = "https://main.kcmlatino.org/devocional"
    r = get(url)
    s = BeautifulSoup(r.text, "html.parser")
    destroy_garbage(s)

    title = clean(s.find("h1").get_text(" ", strip=True)) if s.find("h1") else ""

    CORTAR_KCM = (
        "copyright", "todos los derechos reservados", "contenido relacionado",
        "suscripción", "política de privacidad", "conéctate con nosotros"
    )

    paragraphs = []
    for element in s.find_all(["p", "li"]):
        if element.find_parent(["nav", "footer", "aside"]):
            continue
        text = clean(element.get_text(" ", strip=True))
        low = text.lower()
        
        if any(x in low for x in CORTAR_KCM) or es_extracto_relacionado(text):
            break
            
        if len(text) < 15 or text in paragraphs:
            continue
            
        text = re.sub(r"^[\•\-\*]\s*", "", text)
        paragraphs.append(text)

    verse = ""
    for text in paragraphs[:3]:
        if "«" in text or "(" in text or "Bible Reading" in text or "Lectura" in text:
            verse = text
            break

    audio = ""
    html = str(s)
    m_do = re.search(r'(https?:\\?/\\?/[A-Za-z0-9_./-]*digitaloceanspaces\.com[A-Za-z0-9_./-]+\.mp3)', html, re.I)
    if m_do:
        audio = m_do.group(1).replace("\\/", "/")
    else:
        m_general = re.search(r'(https?:\\?/\\?/[A-Za-z0-9_./-]+\.mp3)', html, re.I)
        if m_general:
            audio = m_general.group(1).replace("\\/", "/")

    return {
        "titulo": title, "subtitulo": "", "versiculo": verse,
        "parrafos": paragraphs[:25], "audio_url": audio, "audio_tipo": "mp3", "link": clean_url(r.url),
    }

def load_previous():
    if not DATA_FILE.exists(): return {}
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f: return json.load(f)
    except Exception: return {}

def main():
    hoy = today_colombia()
    fecha_hoy = fecha_espanol(hoy)
    ahora = dt.datetime.now(ZoneInfo("America/Bogota"))

    old = load_previous()
    data = dict(old)
    data["fecha"] = fecha_hoy
    data["generado"] = ahora.isoformat()

    fuentes = {"encontacto": scrape_encontacto, "bayless": scrape_bayless, "kenneth": scrape_kenneth}

    for clave, fn in fuentes.items():
        try:
            nuevo = fn()
            if valid(nuevo): data[clave] = nuevo
        except Exception as exc:
            print(f"Error en {clave}: {exc}", file=sys.stderr)
            if valid(old.get(clave)): data[clave] = old[clave]

    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

if __name__ == "__main__":
    main()
