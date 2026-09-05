#!/usr/bin/env python3
"""
Extrae texto limpio y asegura la captura exacta del subtítulo en En Contacto.
También obtiene correctamente el episodio actual de Bayless Conley.
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
        "DevocionalesDiariosBot/4.5"
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

    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=10,
        pool_maxsize=10,
    )

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
    return dt.datetime.now(
        ZoneInfo("America/Bogota")
    ).date()


def fecha_espanol(fecha=None):
    if fecha is None:
        fecha = today_colombia()

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

    return (
        f"{fecha.day} de "
        f"{meses[fecha.month - 1]} de "
        f"{fecha.year}"
    )


def url_no_cache(url):
    separador = "&" if "?" in url else "?"

    ahora = dt.datetime.now(
        dt.timezone.utc
    ).strftime("%Y%m%d%H%M%S")

    return (
        f"{url}{separador}"
        f"_nocache={ahora}"
    )


def get(url):
    r = S.get(
        url_no_cache(url),
        timeout=TIMEOUT,
        allow_redirects=True,
        headers={
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
    )

    r.raise_for_status()

    return r


def clean_url(url):
    if not url:
        return ""

    return re.sub(
        r"[?&]_nocache=\d+",
        "",
        url,
    )


def valid(item):
    return (
        isinstance(item, dict)
        and bool(item.get("titulo"))
        and isinstance(
            item.get("parrafos"),
            list,
        )
        and any(
            clean(x)
            for x in item.get(
                "parrafos",
                [],
            )
        )
    )


def es_extracto_relacionado(texto):
    texto_low = texto.lower()

    return (
        len(texto_low) < 250
        and re.search(
            r"(\.\.\.|…)\s*"
            r"(?:leer m[aá]s|read more|\])?\s*$",
            texto_low,
        )
    )


def destroy_garbage(soup):
    for trash in soup.find_all(
        [
            "div",
            "section",
            "aside",
            "footer",
            "ul",
            "nav",
        ],
        class_=lambda c: (
            c
            and any(
                k in str(c).lower()
                for k in (
                    "related",
                    "card",
                    "sidebar",
                    "footer",
                    "recommended",
                    "more-devotionals",
                    "author-bio",
                    "widget",
                    "social",
                    "share",
                    "awac",
                    "post-nav",
                    "jp-relatedposts",
                    "crp_related",
                )
            )
        ),
    ):
        trash.decompose()

    for trash in soup.find_all(
        id=lambda i: (
            i
            and any(
                k in str(i).lower()
                for k in (
                    "jp-relatedposts",
                    "sharedaddy",
                    "crp_related",
                    "secondary",
                    "sidebar",
                )
            )
        )
    ):
        trash.decompose()

    for btn in soup.find_all(
        lambda tag: (
            tag.name
            in [
                "a",
                "button",
                "div",
                "span",
            ]
            and "compartir este devocional"
            in tag.get_text(strip=True).lower()
        )
    ):
        btn.decompose()


def agregar_sin_duplicar(lista, texto):
    if not texto or len(texto) < 15:
        return

    texto_low = texto.lower()

    for p in lista:
        p_low = p.lower()

        if texto_low == p_low:
            return

        if texto_low in p_low:
            return

        if p_low in texto_low:
            return

    lista.append(texto)


# ==========================================================
# EN CONTACTO
# ==========================================================

def scrape_encontacto():
    url = (
        "https://www.encontactoglobal.org/"
        "lea/devocionales-diarios"
    )

    r = get(url)

    s = BeautifulSoup(
        r.text,
        "html.parser",
    )

    destroy_garbage(s)

    meditation_marker = None

    for tag in s.find_all(
        string=re.compile(
            r"^\s*Meditación diaria\s*$",
            re.I,
        )
    ):
        meditation_marker = tag.parent
        break

    title = ""

    if meditation_marker:
        for element in meditation_marker.find_all_next(
            ["h1", "h2"]
        ):
            texto = clean(
                element.get_text(
                    " ",
                    strip=True,
                )
            )

            if not texto:
                continue

            low = texto.lower()

            if low in {
                "opciones de lectura",
                "otros devocionales",
            }:
                continue

            if low.startswith(
                "opciones de lectura"
            ):
                continue

            title = texto
            break

    if not title and s.find("h1"):
        title = clean(
            s.find("h1").get_text(
                " ",
                strip=True,
            )
        )

    title_tag = None

    for h in s.find_all(
        ["h1", "h2"]
    ):
        if (
            clean(
                h.get_text(
                    " ",
                    strip=True,
                )
            )
            == title
        ):
            title_tag = h
            break

    # ======================================================
    # SUBTÍTULO
    # ======================================================

    subtitle = ""

    if title_tag:
        for element in title_tag.find_all_next(
            ["h2", "p"]
        ):
            texto = clean(
                element.get_text(
                    " ",
                    strip=True,
                )
            )

            if not texto:
                continue

            low = texto.lower()

            # No aceptar el propio título.
            if texto == title:
                continue

            # No aceptar elementos de interfaz.
            if (
                low == "opciones de lectura"
                or low.startswith(
                    "opciones de lectura"
                )
            ):
                continue

            # No aceptar otros encabezados de navegación.
            if (
                low == "otros devocionales"
                or low.startswith(
                    "otros devocionales"
                )
            ):
                continue

            # No aceptar "Meditación diaria".
            if low == "meditación diaria":
                continue

            # No aceptar textos formados únicamente
            # por letras de los controles A A A.
            if re.fullmatch(
                r"[a\s]+",
                texto,
                re.I,
            ):
                continue

            # No aceptar fechas.
            if re.search(
                r"\d{1,2}\s+de\s+[a-záéíóú]+"
                r"\s+de\s+\d{4}",
                texto,
                re.I,
            ):
                continue

            # El subtítulo debe ser un texto descriptivo
            # suficientemente largo.
            if (
                40 <= len(texto) <= 300
                and re.search(
                    r"[a-záéíóú]",
                    texto,
                    re.I,
                )
            ):
                subtitle = texto
                break

    # ======================================================
    # VERSÍCULO
    # ======================================================

    verse = ""

    if meditation_marker:
        for a in meditation_marker.find_all_next(
            "a",
            href=True,
        ):
            if re.search(
                r"biblegateway\.com",
                a.get("href", ""),
                re.I,
            ):
                verse = clean(
                    a.get_text(
                        " ",
                        strip=True,
                    )
                )

                if verse:
                    break

    # ======================================================
    # AUDIO
    # ======================================================

    audio = ""

    m_audio = re.search(
        r"(https?:\\?/\\?/"
        r"[A-Za-z0-9_./-]*azureedge\.net"
        r"[A-Za-z0-9_./-]+\.mp3)",
        str(s),
        re.I,
    )

    if m_audio:
        audio = (
            m_audio.group(1)
            .replace(
                "\\/",
                "/",
            )
        )

    # ======================================================
    # PÁRRAFOS
    # ======================================================

    paragraphs = []

    start_node = (
        title_tag
        if title_tag
        else meditation_marker
    )

    CORTAR_ENCONTACTO = (
        "biblia en un año",
        "otros devocionales",
        "opciones de lectura",
        "quiénes somos",
        "ministerios en contacto",
        "conectar",
        "participar",
        "suscríbase",
        "suscribirse",
        "correo electrónico",
        "artículos destacados",
    )

    encontro_subtitulo = False

    if start_node:

        for element in start_node.find_all_next(
            "p"
        ):

            if element.find_parent(
                [
                    "nav",
                    "footer",
                    "aside",
                ]
            ):
                continue

            texto = clean(
                element.get_text(
                    " ",
                    strip=True,
                )
            )

            low = texto.lower()

            if any(
                k in low
                for k in CORTAR_ENCONTACTO
            ):
                break

            if es_extracto_relacionado(
                texto
            ):
                break

            if not texto:
                continue

            if texto == verse:
                continue

            if (
                subtitle
                and texto == subtitle
                and not encontro_subtitulo
            ):
                encontro_subtitulo = True
                continue

            agregar_sin_duplicar(
                paragraphs,
                texto,
            )

    return {
        "titulo": title,
        "subtitulo": subtitle,
        "versiculo": verse,
        "parrafos": paragraphs[:20],
        "audio_url": audio,
        "audio_tipo": "mp3",
        "link": clean_url(r.url),
    }


# ==========================================================
# BAYLESS CONLEY
# ==========================================================

def extraer_numero_bayless(
    href,
    texto,
):
    texto = clean(
        texto or ""
    )

    href = (
        href or ""
    ).strip()

    m = re.search(
        r"#\s*(\d+)\b",
        texto,
        re.I,
    )

    if m:
        return int(
            m.group(1)
        )

    m = re.search(
        r"/devotional/(\d+)-",
        href.lower(),
        re.I,
    )

    if m:
        return int(
            m.group(1)
        )

    return -1


def encontrar_url_bayless_actual(
    listado,
):
    candidatos = []

    for a in listado.find_all(
        "a",
        href=True,
    ):

        href = a.get(
            "href",
            "",
        ).strip()

        if not href:
            continue

        if "/devotional/" not in href.lower():
            continue

        texto = clean(
            a.get_text(
                " ",
                strip=True,
            )
        )

        numero = extraer_numero_bayless(
            href,
            texto,
        )

        if numero < 0:
            continue

        candidatos.append(
            {
                "numero": numero,
                "url": urljoin(
                    "https://www.respuestasbc.com/",
                    href,
                ),
                "texto": texto,
            }
        )

    if not candidatos:
        raise RuntimeError(
            "No se encontraron episodios "
            "numerados de Bayless en el listado"
        )

    candidatos.sort(
        key=lambda x: x["numero"],
        reverse=True,
    )

    return candidatos[0]


def encontrar_titulo_bayless(
    soup,
):
    titulo = ""
    titulo_tag = None
    numero = -1

    for h in soup.find_all(
        ["h1", "h2"]
    ):

        texto = clean(
            h.get_text(
                " ",
                strip=True,
            )
        )

        if not texto:
            continue

        if texto.lower() in {
            "devocional diario",
            "respuestas para cada día",
        }:
            continue

        m = re.search(
            r"#\s*(\d+)\b",
            texto,
            re.I,
        )

        if m:

            numero = int(
                m.group(1)
            )

            titulo = clean(
                re.sub(
                    r"^\s*#?\s*\d+"
                    r"\s*[-–—:.]?\s*",
                    "",
                    texto,
                )
            )

            titulo_tag = h

            break

    if not titulo:

        for h in soup.find_all(
            ["h1", "h2"]
        ):

            texto = clean(
                h.get_text(
                    " ",
                    strip=True,
                )
            )

            if not texto:
                continue

            if texto.lower() in {
                "devocional diario",
                "respuestas para cada día",
            }:
                continue

            titulo = clean(
                re.sub(
                    r"^\s*#?\s*\d+"
                    r"\s*[-–—:.]?\s*",
                    "",
                    texto,
                )
            )

            titulo_tag = h

            break

    return (
        titulo,
        titulo_tag,
        numero,
    )


def scrape_bayless():
    listado_url = (
        "https://www.respuestasbc.com/devotional/"
    )

    # ======================================================
    # 1. OBTENER EL LISTADO
    # ======================================================

    r_listado = get(listado_url)

    listado = BeautifulSoup(
        r_listado.text,
        "html.parser"
    )

    candidatos = []

    for a in listado.find_all(
        "a",
        href=True,
    ):

        href = a.get(
            "href",
            "",
        ).strip()

        if not href:
            continue

        if "/devotional/" not in href.lower():
            continue

        texto = clean(
            a.get_text(
                " ",
                strip=True,
            )
        )

        numero = -1

        # Número en el texto: #246
        m = re.search(
            r"#\s*(\d+)\b",
            texto,
            re.I
        )

        if m:
            numero = int(
                m.group(1)
            )

        # Número en la URL: /devotional/246-
        if numero < 0:

            m = re.search(
                r"/devotional/(\d+)-",
                href,
                re.I
            )

            if m:
                numero = int(
                    m.group(1)
                )

        if numero < 0:
            continue

        candidatos.append(
            {
                "numero": numero,
                "url": urljoin(
                    r_listado.url,
                    href
                ),
                "texto": texto
            }
        )

    if not candidatos:
        raise RuntimeError(
            "No se encontraron episodios "
            "numerados de Bayless"
        )

    # El episodio más reciente es el número mayor.
    candidatos.sort(
        key=lambda x: x["numero"],
        reverse=True
    )

    candidato = candidatos[0]

    articulo_url = candidato["url"]
    numero_actual = candidato["numero"]

    print(
        f"Bayless seleccionado: "
        f"#{numero_actual} -> {articulo_url}"
    )

    # ======================================================
    # 2. OBTENER LA PÁGINA DEL EPISODIO
    # ======================================================

    r = get(articulo_url)

    s = BeautifulSoup(
        r.text,
        "html.parser"
    )

    # ======================================================
    # 3. TÍTULO
    # ======================================================

    title = ""
    title_tag = None

    for h in s.find_all(
        ["h1", "h2", "h3"]
    ):

        texto = clean(
            h.get_text(
                " ",
                strip=True
            )
        )

        if not texto:
            continue

        low = texto.lower()

        if low in (
            "devocional diario",
            "respuestas para cada día",
        ):
            continue

        # Preferimos el encabezado que contiene #246.
        if re.search(
            r"#\s*" + str(numero_actual) + r"\b",
            texto,
            re.I
        ):

            title = clean(
                re.sub(
                    r"^\s*#?\s*\d+"
                    r"\s*[-–—:.]?\s*",
                    "",
                    texto
                )
            )

            title_tag = h
            break

    # Respaldo.
    if not title:

        for h in s.find_all(
            ["h1", "h2", "h3"]
        ):

            texto = clean(
                h.get_text(
                    " ",
                    strip=True
                )
            )

            if not texto:
                continue

            if texto.lower() in (
                "devocional diario",
                "respuestas para cada día",
            ):
                continue

            title = clean(
                re.sub(
                    r"^\s*#?\s*\d+"
                    r"\s*[-–—:.]?\s*",
                    "",
                    texto
                )
            )

            title_tag = h
            break

    if not title:
        raise RuntimeError(
            "No se encontró el título "
            "del devocional de Bayless"
        )

    print(
        f"Bayless título: {title}"
    )

    # ======================================================
    # 4. COMPROBAR QUE ES EL EPISODIO CORRECTO
    # ======================================================

    texto_total = clean(
        s.get_text(
            " ",
            strip=True
        )
    )

    if not re.search(
        r"#\s*" + str(numero_actual) + r"\b",
        texto_total,
        re.I
    ):

        if not re.search(
            r"/devotional/"
            + str(numero_actual)
            + r"-",
            clean_url(r.url).lower()
        ):

            raise RuntimeError(
                "La página de Bayless no corresponde "
                f"al episodio #{numero_actual}"
            )

    # ======================================================
    # 5. LOCALIZAR EL CONTENEDOR DEL ARTÍCULO
    # ======================================================

    contenedor = None

    selectores = [
        "article",
        ".entry-content",
        ".post-content",
        ".entry-content-single",
        ".single-post-content",
        ".td-post-content",
        ".post-body",
        ".article-content",
        ".content-area",
        "main",
    ]

    for selector in selectores:

        encontrado = s.select_one(
            selector
        )

        if not encontrado:
            continue

        texto_encontrado = clean(
            encontrado.get_text(
                " ",
                strip=True
            )
        )

        if len(texto_encontrado) > 300:

            contenedor = encontrado
            break

    if contenedor is None:
        contenedor = s

    # ======================================================
    # 6. EXTRAER TEXTO
    # ======================================================

    paragraphs = []

    elementos = contenedor.find_all(
        ["p", "blockquote", "li"]
    )

    for element in elementos:

        if element.find_parent(
            [
                "nav",
                "footer",
                "aside",
            ]
        ):
            continue

        texto = clean(
            element.get_text(
                " ",
                strip=True
            )
        )

        if not texto:
            continue

        low = texto.lower()

        if (
            "escuche este devocional"
            in low
            or "escucha este devocional"
            in low
        ):
            break

        if any(
            basura in low
            for basura in (
                "leer devocionales anteriores",
                "¿quieres respuestas directo",
                "suscríbete a nuestro devocional",
                "me gustaría recibir los correos",
                "powered by kit",
                "necesitas ayuda",
                "compartir este devocional",
                "comparte este devocional",
                "haga click",
                "haga clic",
                "previous",
                "next",
            )
        ):
            break

        if len(texto) < 15:
            continue

        if es_extracto_relacionado(texto):
            continue

        agregar_sin_duplicar(
            paragraphs,
            texto
        )

    # ======================================================
    # 7. RESPALDO IMPORTANTE
    # ======================================================

    if not paragraphs:

        texto_contenedor = clean(
            contenedor.get_text(
                "\n",
                strip=True
            )
        )

        lineas = []

        for linea in texto_contenedor.splitlines():

            linea = clean(linea)

            if not linea:
                continue

            lineas.append(linea)

        iniciar = False

        for linea in lineas:

            low = linea.lower()

            if title.lower() in low:
                iniciar = True
                continue

            if not iniciar:
                continue

            if (
                "escuche este devocional"
                in low
                or "escucha este devocional"
                in low
            ):
                break

            if any(
                basura in low
                for basura in (
                    "leer devocionales anteriores",
                    "¿quieres respuestas directo",
                    "suscríbete a nuestro devocional",
                    "me gustaría recibir los correos",
                    "powered by kit",
                    "compartir este",
                    "comparte este",
                    "haga click",
                    "haga clic",
                )
            ):
                break

            if len(linea) < 15:
                continue

            agregar_sin_duplicar(
                paragraphs,
                linea
            )

    # ======================================================
    # 8. ÚLTIMO RESPALDO
    # ======================================================

    if not paragraphs:

        texto_plano = s.get_text(
            "\n",
            strip=True
        )

        lineas = [
            clean(x)
            for x in texto_plano.splitlines()
            if clean(x)
        ]

        indice_titulo = -1

        for i, linea in enumerate(lineas):

            if (
                title.lower()
                in linea.lower()
            ):
                indice_titulo = i
                break

        if indice_titulo >= 0:

            for linea in lineas[
                indice_titulo + 1:
            ]:

                low = linea.lower()

                if (
                    "escuche este devocional"
                    in low
                    or "escucha este devocional"
                    in low
                ):
                    break

                if len(linea) < 15:
                    continue

                if any(
                    basura in low
                    for basura in (
                        "leer devocionales anteriores",
                        "suscríbete",
                        "powered by kit",
                        "compartir este",
                        "comparte este",
                    )
                ):
                    break

                agregar_sin_duplicar(
                    paragraphs,
                    linea
                )

    # ======================================================
    # 9. VALIDAR TEXTO
    # ======================================================

    if not paragraphs:

        raise RuntimeError(
            "No se encontró el texto del "
            "devocional actual de Bayless"
        )

    print(
        f"Bayless párrafos encontrados: "
        f"{len(paragraphs)}"
    )

    # ======================================================
    # 10. AUDIO SOUNDCLOUD
    # ======================================================

    audio = ""

    # A) enlaces normales
    for a in s.find_all(
        "a",
        href=True
    ):

        href = a.get(
            "href",
            ""
        ).strip()

        if (
            "soundcloud.com/respuestasbc/"
            in href.lower()
            and "/sets/" not in href.lower()
        ):

            audio = href
            break

    # B) iframe / embed
    if not audio:

        for elemento in s.find_all(
            ["iframe", "embed"]
        ):

            for atributo in (
                "src",
                "data-src",
                "data-url",
            ):

                valor = elemento.get(
                    atributo,
                    ""
                ).strip()

                if (
                    "soundcloud.com/respuestasbc/"
                    in valor.lower()
                    and "/sets/"
                    not in valor.lower()
                ):

                    audio = valor
                    break

            if audio:
                break

    # C) HTML directo
    if not audio:

        patrones_audio = [
            r"https?://(?:www\.)?"
            r"soundcloud\.com/respuestasbc/"
            r"[A-Za-z0-9_-]+",

            r"https:\\/\\/(?:www\.)?"
            r"soundcloud\.com\\/respuestasbc\\/"
            r"[A-Za-z0-9_-]+",
        ]

        for patron in patrones_audio:

            m_audio = re.search(
                patron,
                r.text,
                re.I
            )

            if m_audio:

                audio = (
                    m_audio.group(0)
                    .replace(
                        "\\/",
                        "/"
                    )
                )

                break

    if not audio:

        raise RuntimeError(
            "No se encontró el audio SoundCloud "
            "del devocional actual de Bayless"
        )

    print(
        f"Bayless audio: {audio}"
    )

    # ======================================================
    # 11. DEVOLVER DATOS
    # ======================================================

    return {
        "titulo": title,
        "subtitulo": "",
        "versiculo": "",
        "parrafos": paragraphs[:20],
        "audio_url": audio,
        "audio_tipo": "soundcloud",
        "link": clean_url(r.url),
    }


# ==========================================================
# KENNETH COPELAND
# ==========================================================

def scrape_kenneth():

    url = (
        "https://main.kcmlatino.org/"
        "devocional"
    )

    r = get(url)

    s = BeautifulSoup(
        r.text,
        "html.parser",
    )

    destroy_garbage(s)

    title = (
        clean(
            s.find("h1").get_text(
                " ",
                strip=True,
            )
        )
        if s.find("h1")
        else ""
    )

    CORTAR_KCM = (
        "copyright",
        "todos los derechos reservados",
        "contenido relacionado",
        "suscripción",
        "política de privacidad",
        "conéctate con nosotros",
    )

    paragraphs = []

    for element in s.find_all(
        "p"
    ):

        if element.find_parent(
            [
                "nav",
                "footer",
                "aside",
            ]
        ):
            continue

        text = clean(
            element.get_text(
                " ",
                strip=True,
            )
        )

        low = text.lower()

        if any(
            x in low
            for x in CORTAR_KCM
        ):
            break

        if es_extracto_relacionado(
            text
        ):
            break

        agregar_sin_duplicar(
            paragraphs,
            text,
        )

    verse = ""

    for text in paragraphs[:3]:

        if (
            "«" in text
            or "(" in text
            or "Bible Reading" in text
            or "Lectura" in text
        ):

            verse = text

            break

    audio = ""

    html = r.text

    m_do = re.search(
        r'https?://(?:[a-zA-Z0-9_-]+\\?/?)*'
        r'digitaloceanspaces\.com'
        r'(?:[a-zA-Z0-9_./-]|\\/)*\.mp3',
        html,
        re.I,
    )

    if m_do:

        audio = (
            m_do.group(0)
            .replace("\\/", "/")
        )

    else:

        m_general = re.search(
            r'https?://'
            r'(?:[a-zA-Z0-9_./-]|\\/)*\.mp3',
            html,
            re.I,
        )

        if m_general:

            audio = (
                m_general.group(0)
                .replace("\\/", "/")
            )

    return {
        "titulo": title,
        "subtitulo": "",
        "versiculo": verse,
        "parrafos": paragraphs[:25],
        "audio_url": audio,
        "audio_tipo": "mp3",
        "link": clean_url(r.url),
    }


# ==========================================================
# DATOS ANTERIORES
# ==========================================================

def load_previous():

    if not DATA_FILE.exists():
        return {}

    try:

        with DATA_FILE.open(
            "r",
            encoding="utf-8",
        ) as f:

            return json.load(f)

    except Exception:

        return {}


# ==========================================================
# PRINCIPAL
# ==========================================================

def main():

    hoy = today_colombia()

    fecha_hoy = fecha_espanol(
        hoy
    )

    ahora = dt.datetime.now(
        ZoneInfo(
            "America/Bogota"
        )
    )

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

                print(
                    f"OK - {clave}: "
                    f"{nuevo.get('titulo', '')}"
                )

            else:

                raise RuntimeError(
                    f"Datos inválidos para {clave}"
                )

        except Exception as exc:

            print(
                f"Error en {clave}: {exc}",
                file=sys.stderr,
            )

            if valid(
                old.get(clave)
            ):

                data[clave] = old[clave]

    with DATA_FILE.open(
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )

        f.write("\n")


if __name__ == "__main__":
    main()
