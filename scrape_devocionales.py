#!/usr/bin/env python3
"""
Extrae texto 100% limpio (sin menús ni devocionales anteriores) y audios oficiales.
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
        "Chrome/151.0.0.0 Safari/537.36 "
        "DevocionalesDiariosBot/3.0"
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
    r = S.get(
        final_url,
        timeout=TIMEOUT,
        allow_redirects=True,
        headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
    )
    r.raise_for_status()
    return r

def clean_url(url):
    if not url:
        return ""
    return re.sub(r"[?&]_nocache=\d+", "", url)

def valid(item):
    return (
        isinstance(item, dict)
        and bool(item.get("titulo"))
        and isinstance(item.get("parrafos"), list)
        and any(clean(x) for x in item.get("parrafos", []))
    )

def scrape_encontacto():
    url = "https://www.encontactoglobal.org/lea/devocionales-diarios"
    r = get(url)
    s = BeautifulSoup(r.text, "html.parser")
    html = str(s)

    meditation_marker = None
    for tag in s.find_all(string=re.compile(r"^\s*Meditación diaria\s*$", re.I)):
        meditation_marker = tag.parent
        break

    title = ""
    if meditation_marker:
        for element in meditation_marker.find_all_next(["h1", "h2"]):
            texto = clean(element.get_text(" ", strip=True))
            if not texto or texto.lower() in {"opciones de lectura", "otros devocionales", "otros devocionles"}:
                continue
            title = texto
            break

    if not title and s.find("h1"):
        title = clean(s.find("h1").get_text(" ", strip=True))

    subtitle = ""
    if meditation_marker:
        encontrado_title = False
        for element in meditation_marker.find_all_next(["h1", "h2"]):
            texto = clean(element.get_text(" ", strip=True))
            if not texto:
                continue
            if texto == title:
                encontrado_title = True
                continue
            if encontrado_title:
                subtitle = texto
                break

    verse = ""
    if meditation_marker:
        for a in meditation_marker.find_all_next("a", href=True):
            if re.search(r"biblegateway\.com", a.get("href", ""), re.I):
                verse = clean(a.get_text(" ", strip=True))
                if verse:
                    break

    # Audio En Contacto
    audio = ""
    m_audio = re.search(r'(https?:\\?/\\?/[A-Za-z0-9_./-]*azureedge\.net[A-Za-z0-9_./-]+\.mp3)', html, re.I)
    if m_audio:
        audio = m_audio.group(1).replace("\\/", "/")
    else:
        for tag in s.find_all(["audio", "source"]):
            src = tag.get("src") or tag.get("data-src")
            if src and ".mp3" in src.lower():
                audio = urljoin(url, src)
                break

    # Lista de frases de menús, footers y bio institucional a descartar
    BASURA_ENCONTACTO = (
        "quiénes somos", "ministerios en contacto", "charles f. stanley",
        "fundador de ministerios", "conectar", "participar", "contactarnos",
        "cómo aportar", "suscripciones", "oración", "oportunidades de empleo",
        "redes sociales", "facebook", "instagram", "twitter", "youtube",
        "suscribir", "actualizaciones impresas", "buzón de mensajes",
        "opciones de lectura", "otros devocionales", "biblia en un año",
        "lo que creemos", "lo que hacemos", "impacto global", "nuestro fundador",
        "30 principios de vida", "¿qué sigue?", "dios no desea que vivamos como seres independientes"
    )

    paragraphs = []
    for element in s.find_all("p"):
        texto = clean(element.get_text(" ", strip=True))
        low = texto.lower()

        # Omitir si pertenece a menús/nav/footer
        if element.find_parent(["nav", "footer", "header", "aside"]):
            continue

        # Omitir si coincide con texto institucional o menús
        if any(k in low for k in BASURA_ENCONTACTO):
            continue

        if not texto or texto == verse or len(texto) < 25:
            continue

        paragraphs.append(texto)

    vistos = set()
    limpios = []
    for p in paragraphs:
        clave = p.lower()
        if clave not in vistos:
            vistos.add(clave)
            limpios.append(p)

    return {
        "titulo": title,
        "subtitulo": subtitle,
        "versiculo": verse,
        "parrafos": limpios[:20],
        "audio_url": audio,
        "audio_tipo": "mp3",
        "link": clean_url(r.url),
    }

def scrape_bayless():
    landing = "https://www.respuestasbc.com/?redirect_to=latest&post_type=devotional"
    r = get(landing)
    s = BeautifulSoup(r.text, "html.parser")

    title = ""
    article_title_tag = None
    for h1 in s.find_all("h1"):
        texto = clean(h1.get_text(" ", strip=True))
        if not texto or texto.lower() in {"devocional diario", "respuestas para cada día", "bayless conley"}:
            continue
        title = clean(re.sub(r"^\s*#?\s*\d+\s*[-–—:.]?\s*", "", texto))
        article_title_tag = h1
        break

    paragraphs = []
    article = article_title_tag.find_parent("article") if article_title_tag else s

    CORTAR_BAYLESS = (
        "leer devocionales anteriores", "¿quieres respuestas directo",
        "suscríbete a nuestro devocional", "me gustaría recibir los correos",
        "powered by kit", "necesitas ayuda", "comparte este devocional",
        "escuche este devocional", "haga click aquí", "devocionales relacionados"
    )

    for element in article.find_all(["p", "blockquote"]):
        # Omitir si pertenece a widgets de recomendados
        parent_classes = " ".join([str(c) for p in element.parents for c in p.get("class", [])]).lower()
        if any(k in parent_classes for k in ("related", "sharedaddy", "jp-relatedposts", "crp_related")):
            break

        texto = clean(element.get_text(" ", strip=True))
        if not texto:
            continue
        low = texto.lower()

        # Frenar si encuentra frases de pie de página
        if any(k in low for k in CORTAR_BAYLESS):
            break

        # DETECTAR Y CORTAR PREVISUALIZACIONES (Las que terminan en '...' o '…')
        if texto.endswith("...") or texto.endswith("…"):
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
        "titulo": title,
        "subtitulo": "",
        "versiculo": "",
        "parrafos": paragraphs[:20],
        "audio_url": audio,
        "audio_tipo": "soundcloud",
        "link": clean_url(r.url),
    }

def scrape_kenneth():
    url = "https://main.kcmlatino.org/devocional"
    r = get(url)
    s = BeautifulSoup(r.text, "html.parser")
    html = str(s)

    title = clean(s.find("h1").get_text(" ", strip=True)) if s.find("h1") else ""

    paragraphs = []
    for p in s.find_all("p"):
        text = clean(p.get_text(" ", strip=True))
        low = text.lower()
        if len(text) < 15 or any(x in low for x in ("copyright", "todos los derechos reservados", "contenido relacionado")):
            continue
        if text not in paragraphs:
            paragraphs.append(text)

    verse = ""
    for text in paragraphs[:3]:
        if "«" in text or "(" in text or "Bible Reading" in text or "Lectura" in text:
            verse = text
            break

    # Extractor de audio Kenneth Copeland
    audio = ""
    m_do = re.search(r'(https?:\\?/\\?/[A-Za-z0-9_./-]*digitaloceanspaces\.com[A-Za-z0-9_./-]+\.mp3)', html, re.I)
    if m_do:
        audio = m_do.group(1).replace("\\/", "/")
    else:
        m_general = re.search(r'(https?:\\?/\\?/[A-Za-z0-9_./-]+\.mp3)', html, re.I)
        if m_general:
            audio = m_general.group(1).replace("\\/", "/")

    return {
        "titulo": title,
        "subtitulo": "",
        "versiculo": verse,
        "parrafos": paragraphs[:25],
        "audio_url": audio,
        "audio_tipo": "mp3",
        "link": clean_url(r.url),
    }

def load_previous():
    if not DATA_FILE.exists():
        return {}
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def main():
    hoy = today_colombia()
    fecha_hoy = fecha_espanol(hoy)
    ahora = dt.datetime.now(ZoneInfo("America/Bogota"))

    old = load_previous()
    data = dict(old)
    data["fecha"] = fecha_hoy
    data["generado"] = ahora.isoformat()

    fuentes = {
        "encontacto": scrape_encontacto,
        "bayless": scrape_bayless,
        "kenneth": scrape_kenneth,
    }

    for clave, fn in fuentes.items():
        try:
            nuevo = fn()
            if valid(nuevo):
                data[clave] = nuevo
        except Exception as exc:
            print(f"Error en {clave}: {exc}", file=sys.stderr)
            if valid(old.get(clave)):
                data[clave] = old[clave]

    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

if __name__ == "__main__":
    main()
