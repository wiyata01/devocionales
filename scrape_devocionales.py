#!/usr/bin/env python3
"""
Actualizador de los tres devocionales diarios.

Fuentes:
1. En Contacto
2. Bayless Conley
3. Kenneth Copeland

Características:
- No utiliza cache_bust como argumento de requests.
- Añade un parámetro de caché a la URL.
- Busca contenido real del día.
- Cada fuente conserva su propia fecha.
- No acepta contenido viejo como actualización nueva.
- Conserva el último contenido válido si una fuente falla.
"""

import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ============================================================
# CONFIGURACIÓN
# ============================================================

DATA_FILE = Path("data.json")

TIMEOUT = 30

INTERVALO_REINTENTO = 20 * 60

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36 "
        "DevocionalesDiariosBot/3.0"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


# ============================================================
# SESIÓN HTTP
# ============================================================

def crear_sesion():
    s = requests.Session()

    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1,
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


S = crear_sesion()


# ============================================================
# FECHA
# ============================================================

MESES = [
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


def fecha_bogota():
    """
    Obtiene la fecha de Colombia sin depender de la zona horaria
    configurada en el runner.
    """

    try:
        from zoneinfo import ZoneInfo

        ahora = dt.datetime.now(
            ZoneInfo("America/Bogota")
        )

    except Exception:
        ahora = dt.datetime.now(dt.timezone.utc)

    return ahora.date()


def fecha_es(fecha):
    return (
        f"{fecha.day} de "
        f"{MESES[fecha.month - 1]} de "
        f"{fecha.year}"
    )


def fecha_iso(fecha):
    return fecha.strftime("%Y-%m-%d")


def ahora_utc():
    return dt.datetime.now(
        dt.timezone.utc
    ).isoformat().replace("+00:00", "Z")


# ============================================================
# UTILIDADES
# ============================================================

def clean(text):
    if not text:
        return ""

    text = text.replace("\xa0", " ")

    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()


def normalizar_url_sin_cache(url):
    """
    Elimina parámetros temporales de caché.
    """

    try:
        parsed = urlparse(url)

        params = []

        for key, value in (
            __import__("urllib.parse", fromlist=["parse_qsl"])
            .parse_qsl(
                parsed.query,
                keep_blank_values=True
            )
        ):
            if key.lower() not in {
                "_dc",
                "cache",
                "cache_bust",
                "cb",
                "timestamp",
                "t",
            }:
                params.append((key, value))

        query = urlencode(params)

        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                query,
                parsed.fragment,
            )
        )

    except Exception:
        return url


def url_sin_cache(url):
    """
    Añade un parámetro único para evitar que un CDN/proxy
    entregue una copia vieja de la página.

    Esto NO se pasa a requests como cache_bust.
    Se modifica correctamente la URL.
    """

    url = normalizar_url_sin_cache(url)

    separator = "&" if "?" in url else "?"

    return (
        f"{url}"
        f"{separator}"
        f"_devocionales_cache={int(time.time())}"
    )


def get(url):
    """
    Descarga una página evitando caché mediante la URL.
    """

    final_url = url_sin_cache(url)

    response = S.get(
        final_url,
        timeout=TIMEOUT,
        allow_redirects=True,
    )

    response.raise_for_status()

    return response


def soup(url):
    response = get(url)

    return BeautifulSoup(
        response.text,
        "html.parser"
    )


def extract_mp3(html, patterns):
    for pattern in patterns:

        match = re.search(
            pattern,
            html,
            flags=re.I
        )

        if match:

            value = match.group(1)

            value = (
                value
                .replace("\\/", "/")
                .replace("\\u0026", "&")
            )

            return value

    return ""


def valid(item):
    return (
        isinstance(item, dict)
        and bool(item.get("titulo"))
        and bool(item.get("parrafos"))
        and bool(item.get("fecha"))
    )


# ============================================================
# FECHAS EN TEXTO
# ============================================================

def detectar_fecha(texto):
    """
    Detecta fechas como:

    20 de agosto de 2026
    21 de agosto de 2026
    """

    if not texto:
        return None

    patron = re.compile(
        r"\b"
        r"(\d{1,2})"
        r"\s+de\s+"
        r"(enero|febrero|marzo|abril|mayo|junio|"
        r"julio|agosto|septiembre|octubre|noviembre|diciembre)"
        r"\s+de\s+"
        r"(\d{4})"
        r"\b",
        flags=re.I,
    )

    match = patron.search(texto)

    if not match:
        return None

    dia = int(match.group(1))

    mes_nombre = match.group(2).lower()

    año = int(match.group(3))

    try:
        mes = MESES.index(
            mes_nombre
        ) + 1

        return dt.date(
            año,
            mes,
            dia
        )

    except Exception:
        return None


def fecha_desde_elemento(elemento):
    if not elemento:
        return None

    texto = clean(
        elemento.get_text(
            " ",
            strip=True
        )
    )

    return detectar_fecha(texto)


# ============================================================
# EN CONTACTO
# ============================================================

def extraer_encontacto():
    """
    Extrae únicamente el devocional actual de En Contacto.

    La página contiene además:
    - menús
    - radio
    - artículos
    - destacados
    - contenidos relacionados

    Por eso no debemos recorrer todos los <p> indiscriminadamente.
    """

    url = (
        "https://www.encontactoglobal.org/"
        "lea/devocionales-diarios"
    )

    response = get(url)

    final_url = response.url

    s = BeautifulSoup(
        response.text,
        "html.parser"
    )

    # --------------------------------------------------------
    # TÍTULO
    # --------------------------------------------------------

    titulo = ""

    # Buscar encabezados razonables.
    for tag in s.find_all(
        ["h1", "h2", "h3"]
    ):

        texto = clean(
            tag.get_text(
                " ",
                strip=True
            )
        )

        if not texto:
            continue

        if texto.lower() in {
            "devocionales diarios",
            "meditaciones diarias",
            "en contacto",
        }:
            continue

        # Evitar títulos demasiado generales.
        if len(texto) < 4:
            continue

        titulo = texto

        # Preferimos títulos cortos de artículo.
        if len(texto) < 100:
            break

    # Si no se encontró, usar OpenGraph.
    if not titulo:

        og = s.find(
            "meta",
            attrs={
                "property": "og:title"
            }
        )

        if og:
            titulo = clean(
                og.get(
                    "content",
                    ""
                )
            )

    # --------------------------------------------------------
    # BUSCAR EL BLOQUE DEL DEVOCIONAL
    # --------------------------------------------------------

    # Encontramos el encabezado cuyo texto coincide con el título.
    titulo_elemento = None

    for tag in s.find_all(
        ["h1", "h2", "h3", "h4"]
    ):

        texto = clean(
            tag.get_text(
                " ",
                strip=True
            )
        )

        if (
            texto
            and titulo
            and texto.lower()
            == titulo.lower()
        ):

            titulo_elemento = tag
            break

    # --------------------------------------------------------
    # FECHA
    # --------------------------------------------------------

    fecha = None

    if titulo_elemento:

        # Buscar fecha dentro del contenedor cercano.
        padre = titulo_elemento

        for _ in range(5):

            if not padre:
                break

            texto_padre = clean(
                padre.get_text(
                    " ",
                    strip=True
                )
            )

            encontrada = detectar_fecha(
                texto_padre
            )

            if encontrada:

                fecha = encontrada
                break

            padre = padre.parent

    # Si no apareció cerca del título,
    # buscar la primera fecha de la página.
    if not fecha:

        fecha = detectar_fecha(
            clean(
                s.get_text(
                    " ",
                    strip=True
                )
            )
        )

    # --------------------------------------------------------
    # SUBTÍTULO
    # --------------------------------------------------------

    subtitulo = ""

    if titulo_elemento:

        # Buscar el primer texto razonable
        # después del título.
        for elemento in titulo_elemento.find_all_next(
            ["p", "div"],
            limit=20
        ):

            texto = clean(
                elemento.get_text(
                    " ",
                    strip=True
                )
            )

            if not texto:
                continue

            if fecha_es(fecha).lower() in texto.lower() if fecha else False:
                continue

            if len(texto) < 25:
                continue

            # Evitar elementos de navegación.
            if any(
                palabra in texto.lower()
                for palabra in (
                    "opciones de lectura",
                    "compartir",
                    "escuchar",
                    "radio",
                )
            ):
                continue

            subtitulo = texto

            break

    # --------------------------------------------------------
    # VERSÍCULO
    # --------------------------------------------------------

    versiculo = ""

    # Primero buscar enlace a BibleGateway.
    enlace_biblia = s.find(
        "a",
        href=re.compile(
            r"biblegateway",
            re.I
        )
    )

    if enlace_biblia:

        versiculo = clean(
            enlace_biblia.get_text(
                " ",
                strip=True
            )
        )

    # Si no existe, buscar patrón bíblico.
    if not versiculo:

        texto_total = clean(
            s.get_text(
                " ",
                strip=True
            )
        )

        patron_versiculo = re.search(
            r"\b"
            r"(Gálatas|Mateo|Marcos|Lucas|Juan|"
            r"Romanos|1 Corintios|2 Corintios|"
            r"Efesios|Filipenses|Colosenses|"
            r"Salmos|Proverbios|Hebreos|"
            r"Santiago|1 Pedro|2 Pedro|"
            r"1 Juan|2 Juan|3 Juan|Apocalipsis)"
            r"\s+\d+[.:]\d+(?:-\d+)?",
            texto_total,
            flags=re.I,
        )

        if patron_versiculo:
            versiculo = clean(
                patron_versiculo.group(0)
            )

    # --------------------------------------------------------
    # CUERPO
    # --------------------------------------------------------

    parrafos = []

    # Estrategia principal:
    # localizar el título y recorrer elementos posteriores.
    if titulo_elemento:

        for elemento in titulo_elemento.find_all_next(
            ["p", "li"]
        ):

            texto = clean(
                elemento.get_text(
                    " ",
                    strip=True
                )
            )

            if not texto:
                continue

            low = texto.lower()

            # Fin del artículo.
            if any(
                marca in low
                for marca in (
                    "biblia en un año",
                    "también podría interesarte",
                    "contenido relacionado",
                    "artículos destacados",
                    "suscríbete",
                    "suscribirse",
                )
            ):
                break

            # Elementos que NO son parte del artículo.
            if any(
                marca in low
                for marca in (
                    "opciones de lectura",
                    "opciones de transmisión",
                    "escuchar radio",
                    "radio 24/7",
                    "ver video",
                    "serie de sermones",
                    "historias de fe",
                    "emisoras",
                    "suscripciones",
                    "planes de lectura",
                    "descargue pdf",
                )
            ):
                continue

            if (
                fecha
                and low == fecha_es(fecha).lower()
            ):
                continue

            if (
                versiculo
                and low == versiculo.lower()
            ):
                continue

            if len(texto) < 35:
                continue

            # Evitar duplicados.
            if texto in parrafos:
                continue

            parrafos.append(texto)

            # El cuerpo de En Contacto normalmente
            # no necesita más de 12 bloques.
            if len(parrafos) >= 12:
                break

    # --------------------------------------------------------
    # LIMPIEZA ESPECÍFICA
    # --------------------------------------------------------

    limpias = []

    textos_prohibidos = (
        "explore cómo las relaciones",
        "la espera pone a prueba",
        "opciones de transmisión digital",
        "para disfrutar de excelente enseñanza",
        "escuchar radio radio",
        "ver ver video",
    )

    for texto in parrafos:

        low = texto.lower()

        if any(
            x in low
            for x in textos_prohibidos
        ):
            continue

        if len(texto) < 35:
            continue

        limpias.append(texto)

    parrafos = limpias

    # --------------------------------------------------------
    # AUDIO
    # --------------------------------------------------------

    html = str(s)

    audio = extract_mp3(
        html,
        [
            r"(https://intouch\.azureedge\.net/"
            r"spanish/devo/[A-Za-z0-9_./-]+\.mp3)",
        ],
    )

    # --------------------------------------------------------
    # VALIDACIÓN
    # --------------------------------------------------------

    if not titulo:
        raise RuntimeError(
            "En Contacto: no se encontró título."
        )

    if not fecha:
        raise RuntimeError(
            "En Contacto: no se encontró fecha."
        )

    if not parrafos:
        raise RuntimeError(
            "En Contacto: no se encontró el cuerpo del devocional."
        )

    return {
        "titulo": titulo,
        "subtitulo": subtitulo,
        "versiculo": versiculo,
        "parrafos": parrafos,
        "audio_url": audio,
        "audio_tipo": "mp3",
        "fecha": fecha_es(fecha),
        "fecha_iso": fecha_iso(fecha),
        "link": (
            "https://www.encontactoglobal.org/"
            "lea/devocionales-diarios"
        ),
    }


# ============================================================
# BAYLESS CONLEY
# ============================================================

def encontrar_articulo_bayless():
    """
    Obtiene la página del devocional más reciente.

    Primero intenta el endpoint de WordPress.
    Si no está disponible, utiliza la página pública.
    """

    # --------------------------------------------------------
    # OPCIÓN 1: WordPress REST API
    # --------------------------------------------------------

    api_urls = [
        (
            "https://www.respuestasbc.com/"
            "wp-json/wp/v2/devotional"
            "?per_page=1&orderby=date&order=desc"
        ),
        (
            "https://www.respuestasbc.com/"
            "wp-json/wp/v2/posts"
            "?per_page=1&orderby=date&order=desc"
        ),
    ]

    for api_url in api_urls:

        try:

            response = get(api_url)

            if response.status_code != 200:
                continue

            items = response.json()

            if not isinstance(items, list):
                continue

            if not items:
                continue

            item = items[0]

            link = item.get(
                "link"
            )

            if link:
                return link

        except Exception:
            pass

    # --------------------------------------------------------
    # OPCIÓN 2: página pública
    # --------------------------------------------------------

    landing = (
        "https://www.respuestasbc.com/"
        "devotional/"
    )

    response = get(landing)

    s = BeautifulSoup(
        response.text,
        "html.parser"
    )

    # Buscar enlaces que parezcan artículos.
    candidatos = []

    for a in s.find_all(
        "a",
        href=True
    ):

        href = a.get("href", "").strip()

        texto = clean(
            a.get_text(
                " ",
                strip=True
            )
        )

        if not href:
            continue

        if "/devotional/" not in href:
            continue

        if href.rstrip("/") == (
            "https://www.respuestasbc.com/devotional"
        ):
            continue

        # Evitar enlaces internos.
        if any(
            x in href.lower()
            for x in (
                "#",
                "facebook",
                "instagram",
                "youtube",
                "twitter",
            )
        ):
            continue

        candidatos.append(
            (
                urljoin(
                    landing,
                    href
                ),
                texto
            )
        )

    # Quitar duplicados.
    vistos = set()

    candidatos_limpios = []

    for href, texto in candidatos:

        if href in vistos:
            continue

        vistos.add(href)

        candidatos_limpios.append(
            (
                href,
                texto
            )
        )

    # --------------------------------------------------------
    # Buscar el primero que tenga estructura de artículo.
    # --------------------------------------------------------

    for href, texto in candidatos_limpios:

        try:

            r = get(href)

            ss = BeautifulSoup(
                r.text,
                "html.parser"
            )

            h1 = ss.find("h1")

            if not h1:
                continue

            titulo = clean(
                h1.get_text(
                    " ",
                    strip=True
                )
            )

            if not titulo:
                continue

            return r.url

        except Exception:
            continue

    raise RuntimeError(
        "Bayless: no se pudo localizar "
        "el devocional más reciente."
    )


def extraer_bayless():
    """
    Extrae solamente un artículo de Bayless.
    """

    articulo_url = encontrar_articulo_bayless()

    response = get(
        articulo_url
    )

    s = BeautifulSoup(
        response.text,
        "html.parser"
    )

    html = str(s)

    # --------------------------------------------------------
    # TÍTULO
    # --------------------------------------------------------

    titulo = ""

    h1 = s.find("h1")

    if h1:

        titulo = clean(
            h1.get_text(
                " ",
                strip=True
            )
        )

    if not titulo:

        og = s.find(
            "meta",
            attrs={
                "property": "og:title"
            }
        )

        if og:

            titulo = clean(
                og.get(
                    "content",
                    ""
                )
            )

    # Eliminar número de episodio.
    titulo = re.sub(
        r"^\s*#\s*\d+\s*[-–—:]?\s*",
        "",
        titulo
    ).strip()

    # Nunca permitir títulos generales.
    if titulo.lower() in {
        "devocional diario",
        "respuestas para cada día",
        "bayless conley",
        "respuestas para cada dia",
    }:
        raise RuntimeError(
            "Bayless: se encontró el encabezado general "
            "en lugar del título del artículo."
        )

    # --------------------------------------------------------
    # FECHA
    # --------------------------------------------------------

    fecha = None

    if h1:

        padre = h1

        for _ in range(6):

            if not padre:
                break

            texto_padre = clean(
                padre.get_text(
                    " ",
                    strip=True
                )
            )

            encontrada = detectar_fecha(
                texto_padre
            )

            if encontrada:

                fecha = encontrada
                break

            padre = padre.parent

    if not fecha:

        fecha = detectar_fecha(
            clean(
                s.get_text(
                    " ",
                    strip=True
                )
            )
        )

    # --------------------------------------------------------
    # CONTENIDO
    # --------------------------------------------------------

    parrafos = []

    if h1:

        # Buscar el contenedor del artículo.
        contenedor = h1.parent

        mejor_contenedor = None

        for _ in range(6):

            if not contenedor:
                break

            cantidad_p = len(
                contenedor.find_all("p")
            )

            texto_contenedor = clean(
                contenedor.get_text(
                    " ",
                    strip=True
                )
            )

            # Un artículo real debe tener
            # varios párrafos.
            if (
                cantidad_p >= 3
                and len(texto_contenedor) > 500
            ):
                mejor_contenedor = contenedor
                break

            contenedor = contenedor.parent

        if mejor_contenedor:

            elementos = mejor_contenedor.find_all(
                ["p", "blockquote"]
            )

        else:

            elementos = h1.find_all_next(
                ["p", "blockquote"]
            )

        for elemento in elementos:

            texto = clean(
                elemento.get_text(
                    " ",
                    strip=True
                )
            )

            if not texto:
                continue

            low = texto.lower()

            # ------------------------------------------------
            # ELIMINAR CONTENIDO QUE NO PERTENECE AL ARTÍCULO
            # ------------------------------------------------

            if any(
                marca in low
                for marca in (
                    "there was an error submitting",
                    "me gustaría recibir",
                    "recibir los correos",
                    "suscrib",
                    "copyright",
                    "todos los derechos reservados",
                    "la siguiente “c” de",
                    "la siguiente “c” de “las siete",
                    "en el devocional anterior",
                    "en el devocional anterior comenzamos",
                    "las siete “c” para ganar almas",
                )
            ):
                continue

            # El pie de página no debe entrar.
            if "© 2026" in texto:
                break

            if len(texto) < 20:
                continue

            if texto in parrafos:
                continue

            parrafos.append(texto)

    # --------------------------------------------------------
    # AUDIO SOUNDCLOUD
    # --------------------------------------------------------

    audio = ""

    # Enlaces directos.
    for a in s.find_all(
        "a",
        href=True
    ):

        href = a["href"].strip()

        if (
            "soundcloud.com/respuestasbc/"
            in href
            and "/sets/" not in href
        ):

            audio = href
            break

    # HTML incrustado.
    if not audio:

        match = re.search(
            r"https?://(?:www\.)?"
            r"soundcloud\.com/"
            r"respuestasbc/"
            r"[A-Za-z0-9_-]+",
            html,
            flags=re.I,
        )

        if match:
            audio = match.group(0)

    # --------------------------------------------------------
    # VALIDACIÓN
    # --------------------------------------------------------

    if not titulo:
        raise RuntimeError(
            "Bayless: no se encontró título."
        )

    if not fecha:
        raise RuntimeError(
            "Bayless: no se encontró fecha."
        )

    if not parrafos:
        raise RuntimeError(
            "Bayless: no se encontró texto."
        )

    return {
        "titulo": titulo,
        "subtitulo": "",
        "versiculo": "",
        "parrafos": parrafos[:20],
        "audio_url": audio,
        "audio_tipo": "soundcloud",
        "fecha": fecha_es(fecha),
        "fecha_iso": fecha_iso(fecha),
        "link": articulo_url,
    }


# ============================================================
# KENNETH COPELAND
# ============================================================

def encontrar_kcm():
    """
    Obtiene el devocional actual.
    """

    url = (
        "https://main.kcmlatino.org/"
        "devotional"
    )

    response = get(url)

    return response


def extraer_kenneth():
    """
    Extrae únicamente el artículo principal de KCM.
    """

    response = encontrar_kcm()

    final_url = response.url

    s = BeautifulSoup(
        response.text,
        "html.parser"
    )

    html = str(s)

    # --------------------------------------------------------
    # TÍTULO
    # --------------------------------------------------------

    titulo = ""

    h1 = s.find("h1")

    if h1:

        titulo = clean(
            h1.get_text(
                " ",
                strip=True
            )
        )

    if not titulo:

        og = s.find(
            "meta",
            attrs={
                "property": "og:title"
            }
        )

        if og:

            titulo = clean(
                og.get(
                    "content",
                    ""
                )
            )

    # --------------------------------------------------------
    # FECHA
    # --------------------------------------------------------

    fecha = None

    if h1:

        padre = h1

        for _ in range(6):

            if not padre:
                break

            texto_padre = clean(
                padre.get_text(
                    " ",
                    strip=True
                )
            )

            encontrada = detectar_fecha(
                texto_padre
            )

            if encontrada:

                fecha = encontrada
                break

            padre = padre.parent

    if not fecha:

        fecha = detectar_fecha(
            clean(
                s.get_text(
                    " ",
                    strip=True
                )
            )
        )

    # --------------------------------------------------------
    # CONTENIDO
    # --------------------------------------------------------

    parrafos = []

    if h1:

        # Buscar un contenedor razonable.
        contenedor = h1.parent

        mejor = None

        for _ in range(7):

            if not contenedor:
                break

            cantidad = len(
                contenedor.find_all(
                    ["p"]
                )
            )

            texto = clean(
                contenedor.get_text(
                    " ",
                    strip=True
                )
            )

            if (
                cantidad >= 2
                and len(texto) > 500
            ):
                mejor = contenedor
                break

            contenedor = contenedor.parent

        if mejor:

            elementos = mejor.find_all(
                ["p", "blockquote"]
            )

        else:

            elementos = h1.find_all_next(
                ["p", "blockquote"]
            )

        for elemento in elementos:

            texto = clean(
                elemento.get_text(
                    " ",
                    strip=True
                )
            )

            if not texto:
                continue

            low = texto.lower()

            # ----------------------------------------------
            # ELEMENTOS QUE NO SON EL DEVOCIONAL
            # ----------------------------------------------

            if any(
                marca in low
                for marca in (
                    "copyright",
                    "todos los derechos reservados",
                    "contenido relacionado",
                    "devotional type",
                    "loading",
                    "más opciones para compartir",
                    "devocional",
                )
            ):

                # "devocional" solo no es contenido,
                # pero no descartamos textos largos.
                if len(texto) < 100:
                    continue

            if len(texto) < 20:
                continue

            if texto in parrafos:
                continue

            parrafos.append(texto)

    # --------------------------------------------------------
    # LIMPIAR FOOTER
    # --------------------------------------------------------

    limpias = []

    for texto in parrafos:

        low = texto.lower()

        if (
            "© 1997" in texto
            or "© 1997 - 2026" in texto
        ):
            break

        if low.startswith(
            "bible reading:"
        ):
            # Lo conservamos como último dato bíblico.
            limpias.append(texto)
            break

        if any(
            x in low
            for x in (
                "contenido relacionado",
                "visualízate resucitado",
                "cuando el amor se enfada",
                "el consejo del señor",
                "mayo 26",
                "devotional type",
            )
        ):
            break

        limpias.append(texto)

    parrafos = limpias

    # --------------------------------------------------------
    # VERSÍCULO
    # --------------------------------------------------------

    versiculo = ""

    for texto in parrafos[:4]:

        if (
            "«" in texto
            or
            "(" in texto
        ):

            # Evitar tomar un párrafo demasiado largo
            # como versículo.
            if len(texto) < 700:

                versiculo = texto
                break

    # --------------------------------------------------------
    # AUDIO MP3
    # --------------------------------------------------------

    audio = extract_mp3(
        html,
        [
            r"(https://maincms\.nyc3\.digitaloceanspaces\.com/"
            r"[A-Za-z0-9_./-]+\.mp3)",

            r"(?:src|data-src|audio)"
            r"[\"'=:\s]+"
            r"(https://maincms\.nyc3\.digitaloceanspaces\.com/"
            r"[A-Za-z0-9_./-]+\.mp3)",
        ],
    )

    if not audio:

        match = re.search(
            r"(https?:\\?/\\?/"
            r"maincms\.nyc3\.digitaloceanspaces\.com"
            r"\\?/[A-Za-z0-9_./-]+\.mp3)",
            html,
            flags=re.I,
        )

        if match:

            audio = (
                match.group(1)
                .replace("\\/", "/")
            )

    # --------------------------------------------------------
    # VALIDACIÓN
    # --------------------------------------------------------

    if not titulo:
        raise RuntimeError(
            "Kenneth: no se encontró título."
        )

    if not fecha:
        raise RuntimeError(
            "Kenneth: no se encontró fecha."
        )

    if not parrafos:
        raise RuntimeError(
            "Kenneth: no se encontró texto."
        )

    return {
        "titulo": titulo,
        "subtitulo": "",
        "versiculo": versiculo,
        "parrafos": parrafos[:20],
        "audio_url": audio,
        "audio_tipo": "mp3",
        "fecha": fecha_es(fecha),
        "fecha_iso": fecha_iso(fecha),
        "link": (
            "https://main.kcmlatino.org/"
            "devotional"
        ),
    }


# ============================================================
# DATA.JSON ANTERIOR
# ============================================================

def load_previous():

    if not DATA_FILE.exists():
        return {}

    try:

        with DATA_FILE.open(
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        if isinstance(data, dict):
            return data

    except Exception as exc:

        print(
            "Aviso: no se pudo leer "
            f"data.json anterior: {exc}",
            file=sys.stderr
        )

    return {}


# ============================================================
# VALIDAR QUE SEA EL DÍA CORRECTO
# ============================================================

def es_del_dia(item, hoy):
    """
    Comprueba que la fuente realmente corresponda
    al día actual.

    Esto es MUY importante:
    no aceptamos simplemente que la página responda 200.
    """

    if not valid(item):
        return False

    fecha_item = item.get(
        "fecha_iso"
    )

    if fecha_item:

        return fecha_item == fecha_iso(hoy)

    fecha_texto = item.get(
        "fecha",
        ""
    )

    fecha_detectada = detectar_fecha(
        fecha_texto
    )

    if fecha_detectada:

        return fecha_detectada == hoy

    return False


# ============================================================
# UNA CONSULTA A LAS TRES FUENTES
# ============================================================

def consultar_fuentes(hoy):

    funciones = {
        "encontacto": extraer_encontacto,
        "bayless": extraer_bayless,
        "kenneth": extraer_kenneth,
    }

    resultados = {}

    for clave, funcion in funciones.items():

        print(
            f"\nConsultando {clave}..."
        )

        try:

            item = funcion()

            print(
                f"  Título: {item.get('titulo')}"
            )

            print(
                f"  Fecha: {item.get('fecha')}"
            )

            if es_del_dia(
                item,
                hoy
            ):

                print(
                    f"  OK: {clave} "
                    f"está actualizado."
                )

                resultados[clave] = item

            else:

                print(
                    f"  PENDIENTE: {clave} "
                    f"todavía no corresponde "
                    f"a {fecha_es(hoy)}."
                )

                resultados[clave] = None

        except Exception as exc:

            print(
                f"  ERROR {clave}: {exc}",
                file=sys.stderr
            )

            resultados[clave] = None

    return resultados


# ============================================================
# ACTUALIZAR DATA.JSON
# ============================================================

def guardar_data(
    anterior,
    nuevos,
    hoy
):

    data = dict(anterior)

    # Fecha general del día de la ejecución.
    data["fecha"] = fecha_es(hoy)

    data["generado"] = ahora_utc()

    for clave in (
        "encontacto",
        "bayless",
        "kenneth",
    ):

        nuevo = nuevos.get(
            clave
        )

        if nuevo:

            data[clave] = nuevo

        elif valid(
            anterior.get(clave)
        ):

            # Conservamos el último dato válido.
            data[clave] = anterior[clave]

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


# ============================================================
# MAIN
# ============================================================

def main():

    hoy = fecha_bogota()

    print("=" * 60)
    print("ACTUALIZADOR DE DEVOCIONALES DIARIOS")
    print("=" * 60)
    print(
        f"Fecha esperada en Colombia: "
        f"{fecha_es(hoy)}"
    )
    print(
        "Intervalo de comprobación: "
        "20 minutos"
    )
    print("=" * 60)

    anterior = load_previous()

    while True:

        print()
        print("=" * 60)
        print(
            "NUEVO INTENTO"
        )
        print(
            f"Hora UTC: {ahora_utc()}"
        )
        print("=" * 60)

        resultados = consultar_fuentes(
            hoy
        )

        actualizados = []

        pendientes = []

        for clave in (
            "encontacto",
            "bayless",
            "kenneth",
        ):

            if resultados.get(clave):

                actualizados.append(
                    clave
                )

            else:

                pendientes.append(
                    clave
                )

        # Guardar inmediatamente cualquier fuente
        # que sí haya llegado al día correcto.
        guardar_data(
            anterior,
            resultados,
            hoy
        )

        # Actualizar la referencia para que una fuente
        # ya actualizada no se pierda en los siguientes intentos.
        anterior = load_previous()

        print()
        print(
            f"Actualizados correctamente: "
            f"{len(actualizados)}/3"
        )

        if actualizados:

            for clave in actualizados:

                print(
                    f"  OK  - {clave}: "
                    f"{resultados[clave]['titulo']}"
                )

        if pendientes:

            print(
                "Pendientes:"
            )

            for clave in pendientes:

                print(
                    f"  - {clave}"
                )

        # ----------------------------------------------------
        # TERMINAR CUANDO LOS TRES ESTÉN AL DÍA
        # ----------------------------------------------------

        if len(actualizados) == 3:

            print()
            print("=" * 60)
            print(
                "LOS 3 DEVOCIONALES ESTÁN ACTUALIZADOS."
            )
            print("=" * 60)

            break

        # ----------------------------------------------------
        # ESPERAR 20 MINUTOS
        # ----------------------------------------------------

        print()
        print(
            "Todavía faltan fuentes."
        )

        print(
            "Esperando 20 minutos antes "
            "del siguiente intento..."
        )

        time.sleep(
            INTERVALO_REINTENTO
        )


# ============================================================
# EJECUTAR
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print(
            "\nActualización cancelada."
        )

        sys.exit(1)

    except Exception as exc:

        print(
            f"\nERROR FATAL: {exc}",
            file=sys.stderr
        )

        sys.exit(1)
