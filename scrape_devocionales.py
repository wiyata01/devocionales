#!/usr/bin/env python3
"""Actualiza los tres devocionales y conserva el último dato válido si una fuente falla."""

import datetime as dt
import json
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; DevocionalesDiariosBot/2.0; "
        "+https://wiyata01.github.io/devocionales/)"
    )
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
    r = S.get(
        url,
        timeout=TIMEOUT,
        allow_redirects=True
    )
    r.raise_for_status()
    return r


def valid(item):
    return (
        isinstance(item, dict)
        and bool(item.get("titulo"))
        and bool(item.get("parrafos"))
    )


def extract_mp3(html, patterns):
    for pattern in patterns:
        m = re.search(pattern, html, flags=re.I)
        if m:
            return m.group(1).replace("\\/", "/")

    return ""


# ===========================================================================
# EN CONTACTO
# ===========================================================================

def scrape_encontacto():

    url = "https://www.encontactoglobal.org/lea/devocionales-diarios"

    r = get(url)

    s = BeautifulSoup(r.text, "html.parser")
    html = str(s)

    # -----------------------------------------------------------------------
    # TÍTULO
    # -----------------------------------------------------------------------

    h1 = s.find("h1")

    title = (
        clean(h1.get_text(" ", strip=True))
        if h1
        else ""
    )

    # -----------------------------------------------------------------------
    # SUBTÍTULO
    # -----------------------------------------------------------------------

    h2 = s.find("h2")

    subtitle = (
        clean(h2.get_text(" ", strip=True))
        if h2
        else ""
    )

    # -----------------------------------------------------------------------
    # VERSÍCULO
    # -----------------------------------------------------------------------

    verse = ""

    verse_link = s.find(
        "a",
        href=re.compile(r"biblegateway\.com", re.I)
    )

    if verse_link:
        verse = clean(
            verse_link.get_text(" ", strip=True)
        )

    # -----------------------------------------------------------------------
    # AUDIO
    # -----------------------------------------------------------------------

    audio = extract_mp3(
        html,
        [
            r"(https://intouch\.azureedge\.net/"
            r"spanish/devo/"
            r"[A-Za-z0-9_./-]+\.mp3)",
        ]
    )

    # -----------------------------------------------------------------------
    # TEXTO
    # -----------------------------------------------------------------------

    paragraphs = []

    # Primero intentamos localizar directamente el comienzo conocido
    # del artículo actual.
    start_found = False

    for tag in s.find_all(["p", "li"]):

        text = clean(
            tag.get_text(" ", strip=True)
        )

        if not text:
            continue

        low = text.lower()

        # Inicio del artículo actual.
        if "aprender a ver los obstáculos" in low:
            start_found = True

        if not start_found:
            continue

        # Fin del artículo.
        if "biblia en un año" in low:
            break

        # Elementos que no forman parte del artículo.
        if any(
            x in low
            for x in (
                "suscríbase",
                "suscribirse",
                "correo electrónico",
                "opciones de lectura",
            )
        ):
            continue

        if len(text) < 20:
            continue

        if text not in paragraphs:
            paragraphs.append(text)

    # -----------------------------------------------------------------------
    # RESPALDO
    # -----------------------------------------------------------------------

    if not paragraphs and verse_link:

        for tag in verse_link.find_all_next(["p", "li"]):

            text = clean(
                tag.get_text(" ", strip=True)
            )

            if not text:
                continue

            low = text.lower()

            if "biblia en un año" in low:
                break

            if any(
                x in low
                for x in (
                    "suscríbase",
                    "suscribirse",
                    "correo electrónico",
                )
            ):
                continue

            if len(text) < 20:
                continue

            if text not in paragraphs:
                paragraphs.append(text)

    # -----------------------------------------------------------------------
    # VALIDACIÓN DE SEGURIDAD
    # -----------------------------------------------------------------------

    if not title:
        raise RuntimeError(
            "No se pudo extraer el título de En Contacto"
        )

    if not paragraphs:
        raise RuntimeError(
            "No se pudo extraer el texto de En Contacto"
        )

    texto_completo = " ".join(paragraphs).lower()

    if (
        "obstáculos" not in texto_completo
        and "obstaculos" not in texto_completo
    ):
        raise RuntimeError(
            "El texto extraído de En Contacto no parece "
            "corresponder al devocional actual"
        )

    return {
        "titulo": title,
        "subtitulo": subtitle,
        "versiculo": verse,
        "parrafos": paragraphs[:20],
        "audio_url": audio,
        "audio_tipo": "mp3",
        "link": r.url,
    }


# ===========================================================================
# BAYLESS CONLEY
# ===========================================================================

def scrape_bayless():

    landing = (
        "https://www.respuestasbc.com/"
        "?redirect_to=latest&post_type=devotional"
    )

    r = get(landing)

    s = BeautifulSoup(r.text, "html.parser")
    html = str(s)

    # -----------------------------------------------------------------------
    # TÍTULO
    # -----------------------------------------------------------------------

    title = ""

    candidatos = []

    for tag in s.find_all(["h1", "h2", "h3"]):

        texto = clean(
            tag.get_text(" ", strip=True)
        )

        if not texto:
            continue

        ignorados = {
            "devocional diario",
            "respuestas para cada día",
            "bayless conley",
        }

        if texto.lower() in ignorados:
            continue

        candidatos.append(texto)

    for candidato in candidatos:

        if re.search(
            r"(#\s*\d+\s+)?[A-Za-zÁÉÍÓÚáéíóúÑñÜü]",
            candidato
        ):
            title = candidato
            break

    if not title:

        og = s.find(
            "meta",
            attrs={"property": "og:title"}
        )

        if og:
            title = clean(
                og.get("content", "")
            )

    if not title:

        title_tag = s.find("title")

        if title_tag:
            title = clean(
                title_tag.get_text()
            )

    # Quitar número del episodio.
    title = re.sub(
        r"^\s*#\s*\d+\s*[-–—:]?\s*",
        "",
        title
    ).strip()

    if title.lower() in {
        "devocional diario",
        "respuestas para cada día",
        "bayless conley",
    }:
        title = ""

    # -----------------------------------------------------------------------
    # TEXTO DEL ARTÍCULO ACTUAL
    # -----------------------------------------------------------------------

    paragraphs = []

    # Buscamos el comienzo específico del devocional actual.
    inicio = (
        "hoy vamos a ver la quinta"
    )

    inicio_alternativo = (
        "consolador"
    )

    started = False

    for tag in s.find_all(["p", "blockquote", "li"]):

        text = clean(
            tag.get_text(" ", strip=True)
        )

        if not text:
            continue

        low = text.lower()

        # ---------------------------------------------------------------
        # COMIENZO DEL ARTÍCULO ACTUAL
        # ---------------------------------------------------------------

        if (
            inicio in low
            or (
                not started
                and "quinta" in low
                and "ganar almas" in low
            )
        ):
            started = True

        if not started:
            continue

        # ---------------------------------------------------------------
        # MARCADORES QUE SIGNIFICAN QUE YA TERMINÓ
        # ---------------------------------------------------------------

        if (
            "la siguiente “c”" in low
            or 'la siguiente "c"' in low
            or "la siguiente ‘c’" in low
            or "la siguiente 'c'" in low
            or "en el devocional anterior" in low
            or "there was an error submitting your subscription" in low
            or "me gustaría recibir los correos gratis" in low
            or "me gustaria recibir los correos gratis" in low
            or "© 2026 bayless conley" in low
            or "© bayless conley" in low
        ):
            break

        # -------------------------------------------------------------------
        # NO introducir elementos de navegación / suscripción
        # -------------------------------------------------------------------

        if any(
            x in low
            for x in (
                "suscrib",
                "recibir devocionales",
                "escuche este devocional",
                "share",
                "compartir",
                "error submitting",
            )
        ):
            continue

        if len(text) < 20:
            continue

        if text not in paragraphs:
            paragraphs.append(text)

    # -----------------------------------------------------------------------
    # RESPALDO SI CAMBIA LA ESTRUCTURA
    # -----------------------------------------------------------------------

    if not paragraphs:

        # Buscar primero el texto que conocemos.
        texto_objetivo = None

        for tag in s.find_all(["p", "div", "article"]):

            text = clean(
                tag.get_text(" ", strip=True)
            )

            if (
                "hoy vamos a ver la quinta" in text.lower()
            ):
                texto_objetivo = tag
                break

        if texto_objetivo:

            for tag in texto_objetivo.find_all(
                ["p", "blockquote", "li"]
            ):

                text = clean(
                    tag.get_text(" ", strip=True)
                )

                if not text:
                    continue

                low = text.lower()

                if (
                    "la siguiente “c”" in low
                    or 'la siguiente "c"' in low
                    or "en el devocional anterior" in low
                    or "there was an error submitting" in low
                    or "me gustaría recibir los correos gratis" in low
                    or "© 2026 bayless conley" in low
                ):
                    break

                if len(text) < 20:
                    continue

                if text not in paragraphs:
                    paragraphs.append(text)

    # -----------------------------------------------------------------------
    # AUDIO SOUNDCLOUD
    # -----------------------------------------------------------------------

    audio = ""

    # Primero buscamos el episodio individual.
    for a in s.find_all("a", href=True):

        href = a["href"].strip()

        if (
            "soundcloud.com/respuestasbc/" in href
            and "/sets/" not in href
        ):
            audio = href
            break

    # Buscar URL de SoundCloud dentro del HTML.
    if not audio:

        m = re.search(
            r"https?://(?:www\.)?soundcloud\.com/"
            r"respuestasbc/[A-Za-z0-9_-]+",
            html,
            flags=re.I
        )

        if m:
            audio = m.group(0)

    # -----------------------------------------------------------------------
    # VALIDACIÓN
    # -----------------------------------------------------------------------

    if not title:
        raise RuntimeError(
            "No se pudo extraer el título de Bayless Conley"
        )

    if not paragraphs:
        raise RuntimeError(
            "No se pudo extraer el texto de Bayless Conley"
        )

    texto_completo = " ".join(
        paragraphs
    ).lower()

    # El texto debe corresponder a "El Consolador".
    if (
        "consolador" not in texto_completo
        and "quinta" not in texto_completo
    ):
        raise RuntimeError(
            "El texto extraído de Bayless no parece "
            "corresponder al devocional actual"
        )

    # -----------------------------------------------------------------------
    # LIMPIEZA FINAL
    # -----------------------------------------------------------------------

    final = []

    for text in paragraphs:

        text = clean(text)

        if not text:
            continue

        # Seguridad adicional: jamás guardar contenido posterior.
        low = text.lower()

        if (
            "la siguiente “c”" in low
            or 'la siguiente "c"' in low
            or "en el devocional anterior" in low
            or "there was an error submitting your subscription" in low
            or "me gustaría recibir los correos gratis" in low
            or "me gustaria recibir los correos gratis" in low
            or "© 2026 bayless conley" in low
            or "© bayless conley" in low
        ):
            break

        if text not in final:
            final.append(text)

    paragraphs = final[:30]

    return {
        "titulo": title,
        "subtitulo": "",
        "versiculo": "",
        "parrafos": paragraphs,
        "audio_url": audio,
        "audio_tipo": "soundcloud",
        "link": "https://www.respuestasbc.com/devotional/",
    }


# ===========================================================================
# KENNETH COPELAND
# ===========================================================================

def scrape_kenneth():

    url = "https://main.kcmlatino.org/devocional"

    r = get(url)

    return _scrape_kcm_page(
        r.url,
        r.text
    )


def _scrape_kcm_page(url, html):

    s = BeautifulSoup(
        html,
        "html.parser"
    )

    # -----------------------------------------------------------------------
    # TÍTULO
    # -----------------------------------------------------------------------

    title = ""

    h1 = s.find("h1")

    if h1:

        title = clean(
            h1.get_text(
                " ",
                strip=True
            )
        )

    if not title:

        og = s.find(
            "meta",
            attrs={"property": "og:title"}
        )

        if og:

            title = clean(
                og.get(
                    "content",
                    ""
                )
            )

    # -----------------------------------------------------------------------
    # TEXTO
    # -----------------------------------------------------------------------

    paragraphs = []

    for p in s.find_all("p"):

        text = clean(
            p.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        if len(text) < 20:
            continue

        low = text.lower()

        if any(
            x in low
            for x in (
                "copyright",
                "todos los derechos reservados",
                "devocional type",
                "contenido relacionado",
                "loading",
            )
        ):
            continue

        paragraphs.append(text)

    # -----------------------------------------------------------------------
    # VERSÍCULO
    # -----------------------------------------------------------------------

    verse = ""

    for text in paragraphs[:4]:

        if (
            "«" in text
            or "(hebreos" in text.lower()
        ):

            verse = text
            break

    # -----------------------------------------------------------------------
    # AUDIO
    # -----------------------------------------------------------------------

    audio = extract_mp3(
        html,
        [
            r"(https://maincms\.nyc3\.digitaloceanspaces\.com/"
            r"[A-Za-z0-9_./-]+\.mp3)",

            r"(?:src|data-src|audio)[\"'=:\s]+"
            r"(https://maincms\.nyc3\.digitaloceanspaces\.com/"
            r"[A-Za-z0-9_./-]+\.mp3)",
        ]
    )

    if not audio:

        m = re.search(
            r"(https?:\\?/\\?/"
            r"maincms\.nyc3\.digitaloceanspaces\.com"
            r"\\?/[A-Za-z0-9_./-]+\.mp3)",
            html,
            flags=re.I
        )

        if m:

            audio = (
                m.group(1)
                .replace("\\/", "/")
            )

    if not title or not paragraphs:

        raise RuntimeError(
            "No se pudo extraer título o texto "
            "de Kenneth Copeland"
        )

    return {

        "titulo": title,

        "subtitulo": "",

        "versiculo": verse,

        "parrafos": paragraphs[:20],

        "audio_url": audio,

        "audio_tipo": "mp3",

        "link": url,
    }


# ===========================================================================
# CARGAR CONTENIDO ANTERIOR
# ===========================================================================

def load_previous():

    if not DATA_FILE.exists():
        return {}

    try:

        with DATA_FILE.open(
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        return (
            data
            if isinstance(data, dict)
            else {}
        )

    except Exception as exc:

        print(
            "Aviso: no se pudo leer data.json anterior: "
            f"{exc}",
            file=sys.stderr
        )

        return {}


# ===========================================================================
# MAIN
# ===========================================================================

def main():

    today = (
        dt.datetime
        .now(dt.timezone.utc)
        .date()
    )

    meses = [
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ]

    fecha_es = (
        f"{today.day} de "
        f"{meses[today.month - 1]} de "
        f"{today.year}"
    )

    old = load_previous()

    data = dict(old)

    data["fecha"] = fecha_es

    data["generado"] = (
        dt.datetime
        .now(dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )

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

                raise RuntimeError(
                    "La fuente respondió, pero faltan "
                    "título o texto"
                )

            data[clave] = nuevo

            exitos += 1

            print(
                f"OK  - {clave}: "
                f"{nuevo['titulo']!r}"
            )

        except Exception as exc:

            errores.append(
                f"{clave}: {exc}"
            )

            print(
                f"FAIL - {clave}: {exc}",
                file=sys.stderr
            )

            # Si la fuente falla, conservar el último
            # contenido válido.
            if valid(old.get(clave)):

                data[clave] = old[clave]

                print(
                    "      Se conserva el último "
                    f"contenido válido de {clave}."
                )

            else:

                data[clave] = None

    # -----------------------------------------------------------------------
    # PROTECCIÓN
    # -----------------------------------------------------------------------

    if (
        exitos == 0
        and not any(
            valid(old.get(k))
            for k in fuentes
        )
    ):

        raise RuntimeError(
            "Ninguna fuente pudo actualizarse "
            "y no existe contenido anterior válido"
        )

    # -----------------------------------------------------------------------
    # GUARDAR DATA.JSON
    # -----------------------------------------------------------------------

    with DATA_FILE.open(
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

        f.write("\n")

    # -----------------------------------------------------------------------
    # RESULTADO
    # -----------------------------------------------------------------------

    if errores:

        print(
            "\nFuentes con problemas:\n - "
            + "\n - ".join(errores),
            file=sys.stderr
        )

    print(
        f"\nActualización terminada: "
        f"{exitos}/3 fuentes actualizadas."
    )


if __name__ == "__main__":
    main()