#!/usr/bin/env python3
"""Actualiza los tres devocionales y conserva el último dato válido si una fuente falla."""
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DevocionalesDiariosBot/2.0; +https://wiyata01.github.io/devocionales/)"
}
TIMEOUT = 30
DATA_FILE = Path("data.json")


def session():
    s = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update(HEADERS)
    return s

S = session()


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def get(url):
    r = S.get(url, timeout=TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    return r


def soup(url):
    return BeautifulSoup(get(url).text, "html.parser")


def first_nonempty(values):
    for v in values:
        v = clean(v)
        if v:
            return v
    return ""


def valid(item):
    return isinstance(item, dict) and bool(item.get("titulo")) and bool(item.get("parrafos"))


def extract_mp3(html, patterns):
    for pattern in patterns:
        m = re.search(pattern, html, flags=re.I)
        if m:
            return m.group(1).replace("\\/", "/")
    return ""


# ---------------------------------------------------------------------------
# EN CONTACTO
# ---------------------------------------------------------------------------
def scrape_encontacto():
    url = "https://www.encontactoglobal.org/lea/devocionales-diarios"
    r = get(url)
    s = BeautifulSoup(r.text, "html.parser")
    html = str(s)

    h1 = s.find("h1")
    title = clean(h1.get_text(" ", strip=True)) if h1 else ""

    h2 = s.find("h2")
    subtitle = clean(h2.get_text(" ", strip=True)) if h2 else ""

    verse = ""
    a = s.find("a", href=re.compile(r"biblegateway\.com", re.I))
    if a:
        verse = clean(a.get_text(" ", strip=True))

    # El MP3 actual se sirve desde Azure Edge. Se acepta también el formato
    # ec_devo_YYYY_MM_DD_XXXXX.mp3 si el nombre cambia.
    audio = extract_mp3(html, [
        r"(https://intouch\.azureedge\.net/spanish/devo/[A-Za-z0-9_./-]+\.mp3)",
    ])

    paragraphs = []
    stop = False
    for tag in s.find_all(["p", "li"]):
        text = clean(tag.get_text(" ", strip=True))
        if not text or text == verse:
            continue
        low = text.lower()
        if "biblia en un año" in low:
            break
        if any(x in low for x in ("suscríbase", "suscribirse", "correo electrónico")):
            continue
        # Evita menús, cookies y textos de navegación accidentales.
        if len(text) < 25:
            continue
        paragraphs.append(text)

    # El cuerpo actual tiene 5-8 bloques; limitamos para no arrastrar footer.
    paragraphs = paragraphs[:10]

    if not title or not paragraphs:
        raise RuntimeError("No se pudo extraer título o texto de En Contacto")

    return {
        "titulo": title,
        "subtitulo": subtitle,
        "versiculo": verse,
        "parrafos": paragraphs,
        "audio_url": audio,
        "audio_tipo": "mp3",
        "link": r.url,
    }


# ---------------------------------------------------------------------------
# BAYLESS CONLEY
# ---------------------------------------------------------------------------
def scrape_bayless():
    landing = "https://www.respuestasbc.com/?redirect_to=latest&post_type=devotional"
    r = get(landing)
    s = BeautifulSoup(r.text, "html.parser")
    html = str(s)

    # ---------------------------------------------------------------
    # TÍTULO DEL DEVOCIONAL
    # ---------------------------------------------------------------
    # No usamos simplemente el primer H1 porque Bayless coloca
    # "Devocional Diario" como encabezado general del sitio.
    # Buscamos primero un título que corresponda al artículo.
    title = ""

    candidatos = []

    # H1, H2 y H3 pueden variar según la plantilla de WordPress.
    for tag in s.find_all(["h1", "h2", "h3"]):
        texto = clean(tag.get_text(" ", strip=True))
        if not texto:
            continue

        # Ignorar títulos generales del sitio.
        ignorados = {
            "devocional diario",
            "respuestas para cada día",
            "bayless conley",
        }

        if texto.lower() in ignorados:
            continue

        candidatos.append(texto)

    # Preferimos un título que tenga estructura de artículo.
    for candidato in candidatos:
        # El artículo actual aparece como:
        # "#227 El Consolador"
        # o simplemente:
        # "El Consolador"
        if re.search(r"(#\s*\d+\s+)?[A-Za-zÁÉÍÓÚáéíóúÑñÜü]", candidato):
            title = candidato
            break

    # Si todavía no encontramos título, probar OpenGraph.
    if not title:
        og = s.find("meta", attrs={"property": "og:title"})
        if og:
            title = clean(og.get("content", ""))

    # Último recurso: title de la página.
    if not title:
        title_tag = s.find("title")
        if title_tag:
            title = clean(title_tag.get_text())

    # ---------------------------------------------------------------
    # LIMPIAR EL TÍTULO
    # ---------------------------------------------------------------
    # Quitar el número del episodio:
    # "#227 El Consolador" -> "El Consolador"
    title = re.sub(r"^\s*#\s*\d+\s*[-–—:]?\s*", "", title).strip()

    # Por seguridad, nunca permitir que el nombre general del sitio
    # termine siendo el título del devocional.
    if title.lower() in {
        "devocional diario",
        "respuestas para cada día",
        "bayless conley",
    }:
        title = ""

    # ---------------------------------------------------------------
    # TEXTO
    # ---------------------------------------------------------------
    paragraphs = []

    for p in s.find_all("p"):
        text = clean(p.get_text(" ", strip=True))

        if not text:
            continue

        low = text.lower()

        if any(x in low for x in (
            "suscrib",
            "recibir devocionales",
            "escuche este devocional",
            "share",
            "compartir",
        )):
            continue

        if len(text) < 20:
            continue

        paragraphs.append(text)

    # ---------------------------------------------------------------
    # AUDIO SOUNDCLOUD
    # ---------------------------------------------------------------
    audio = ""

    # Primero buscamos el enlace directo al episodio.
    for a in s.find_all("a", href=True):
        href = a["href"].strip()

        if (
            "soundcloud.com/respuestasbc/" in href
            and "/sets/" not in href
        ):
            audio = href
            break

    # Después buscamos una URL incrustada en el HTML.
    if not audio:
        m = re.search(
            r"https?://(?:www\.)?soundcloud\.com/"
            r"respuestasbc/[A-Za-z0-9_-]+",
            html,
            flags=re.I,
        )

        if m:
            audio = m.group(0)

    # ---------------------------------------------------------------
    # VALIDACIÓN
    # ---------------------------------------------------------------
    if not title or not paragraphs:
        raise RuntimeError(
            "No se pudo extraer título o texto de Bayless Conley"
        )

    return {
        "titulo": title,
        "subtitulo": "",
        "versiculo": "",
        "parrafos": paragraphs[:20],
        "audio_url": audio,
        "audio_tipo": "soundcloud",
        "link": r.url,
    }


# ---------------------------------------------------------------------------
# KENNETH COPELAND
# ---------------------------------------------------------------------------
def scrape_kenneth():
    # Esta URL actualmente redirige al devocional más reciente.
    url = "https://main.kcmlatino.org/devocional"
    r = get(url)
    return _scrape_kcm_page(r.url, r.text)


def _scrape_kcm_page(url, html):
    s = BeautifulSoup(html, "html.parser")
    title = ""
    h1 = s.find("h1")
    if h1:
        title = clean(h1.get_text(" ", strip=True))

    if not title:
        og = s.find("meta", attrs={"property": "og:title"})
        title = clean(og.get("content", "")) if og else ""

    paragraphs = []
    for p in s.find_all("p"):
        text = clean(p.get_text(" ", strip=True))
        if not text or len(text) < 20:
            continue
        low = text.lower()
        if any(x in low for x in (
            "copyright", "todos los derechos reservados", "devocional type",
            "contenido relacionado", "loading"
        )):
            continue
        paragraphs.append(text)

    # La página actual muestra la cita bíblica en un bloque con comillas.
    verse = ""
    for text in paragraphs[:4]:
        if "«" in text or "(hebreos" in text.lower():
            verse = text
            break

    # KCM construye el reproductor con un MP3 alojado en DigitalOcean.
    audio = extract_mp3(html, [
        r"(https://maincms\.nyc3\.digitaloceanspaces\.com/[A-Za-z0-9_./-]+\.mp3)",
        r"(?:src|data-src|audio)[\"'=:\s]+(https://maincms\.nyc3\.digitaloceanspaces\.com/[A-Za-z0-9_./-]+\.mp3)",
    ])

    # Algunos templates escapan la URL como https:\/\/...
    if not audio:
        m = re.search(
            r"(https?:\\?/\\?/maincms\.nyc3\.digitaloceanspaces\.com\\?/[A-Za-z0-9_./-]+\.mp3)",
            html,
            flags=re.I,
        )
        if m:
            audio = m.group(1).replace("\\/", "/")

    if not title or not paragraphs:
        raise RuntimeError("No se pudo extraer título o texto de Kenneth Copeland")

    return {
        "titulo": title,
        "subtitulo": "",
        "versiculo": verse,
        "parrafos": paragraphs[:20],
        "audio_url": audio,
        "audio_tipo": "mp3",
        "link": url,
    }


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------
def load_previous():
    if not DATA_FILE.exists():
        return {}
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        print(f"Aviso: no se pudo leer data.json anterior: {exc}", file=sys.stderr)
        return {}


def main():
    today = dt.datetime.now(dt.timezone.utc).date()
    meses = [
        "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ]
    fecha_es = f"{today.day} de {meses[today.month - 1]} de {today.year}"

    old = load_previous()
    data = dict(old)
    data["fecha"] = fecha_es
    data["generado"] = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

    fuentes = {
        "encontacto": scrape_encontacto,
        "bayless": scrape_bayless,
        "kenneth": scrape_kenneth,
    }

    errores = []
    exitos = 0

    for clave, fn in fuentes.items():
        try:
            nuevo = fn()
            if not valid(nuevo):
                raise RuntimeError("La fuente respondió, pero faltan título o texto")
            data[clave] = nuevo
            exitos += 1
            print(f"OK  - {clave}: {nuevo['titulo']!r}")
        except Exception as exc:
            errores.append(f"{clave}: {exc}")
            print(f"FAIL - {clave}: {exc}", file=sys.stderr)
            if valid(old.get(clave)):
                data[clave] = old[clave]
                print(f"      Se conserva el último contenido válido de {clave}.")
            else:
                data[clave] = None

    if exitos == 0 and not any(valid(old.get(k)) for k in fuentes):
        raise RuntimeError("Ninguna fuente pudo actualizarse y no existe contenido anterior válido")

    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    if errores:
        print("\nFuentes con problemas:\n - " + "\n - ".join(errores), file=sys.stderr)

    print(f"\nActualización terminada: {exitos}/3 fuentes actualizadas.")


if __name__ == "__main__":
    main()
