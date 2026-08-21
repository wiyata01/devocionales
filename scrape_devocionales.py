#!/usr/bin/env python3

"""
ACTUALIZADOR DE DEVOCIONALES DIARIOS

Fuentes:
1. En Contacto
2. Bayless Conley
3. Kenneth Copeland

Características:
- Detecta la fecha actual de Colombia.
- No acepta contenido de días anteriores.
- Conserva el último contenido válido si una fuente falla.
- En Contacto busca específicamente el bloque correspondiente a la fecha.
- KCM acepta fechas del tipo "agosto 21".
- Bayless tiene conexión directa sin añadir parámetros de caché.
- No mantiene GitHub Actions ejecutándose indefinidamente.
"""

import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ============================================================
# CONFIGURACIÓN
# ============================================================

DATA_FILE = Path("data.json")

TIMEOUT = 30

# GitHub Actions hará nuevas ejecuciones según el workflow.
# No necesitamos dejar un proceso infinito durante horas.
MAX_INTENTOS = 1

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36 "
        "DevocionalesDiariosBot/4.0"
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
    session = requests.Session()

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

    session.mount("https://", adapter)
    session.mount("http://", adapter)

    session.headers.update(HEADERS)

    return session


S = crear_sesion()


# ============================================================
# MESES
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

MESES_MAP = {
    nombre: numero
    for numero, nombre in enumerate(MESES, start=1)
}


# ============================================================
# FECHA DE COLOMBIA
# ============================================================

def fecha_bogota():
    try:
        from zoneinfo import ZoneInfo

        ahora = dt.datetime.now(
            ZoneInfo("America/Bogota")
        )

        return ahora.date()

    except Exception:
        ahora = dt.datetime.now(
            dt.timezone.utc
        )

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
    return (
        dt.datetime.now(
            dt.timezone.utc
        )
        .isoformat()
        .replace("+00:00", "Z")
    )


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
    Elimina parámetros temporales.
    """

    try:
        parsed = urlparse(url)

        from urllib.parse import parse_qsl

        params = []

        for key, value in parse_qsl(
            parsed.query,
            keep_blank_values=True
        ):
            if key.lower() not in {
                "_dc",
                "cache",
                "cache_bust",
                "cb",
                "timestamp",
                "t",
                "_devocionales_cache",
            }:
                params.append(
                    (key, value)
                )

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
    Añade cache bust solamente a las fuentes
    que lo permiten.
    """

    url = normalizar_url_sin_cache(url)

    separator = (
        "&"
        if "?" in url
        else "?"
    )

    return (
        f"{url}"
        f"{separator}"
        f"_devocionales_cache={int(time.time())}"
    )


def get(url, cache=True):
    """
    Descarga una página.

    cache=True:
        añade parámetro temporal.

    cache=False:
        descarga la URL original.

    Bayless utiliza cache=False porque su servidor
    puede devolver HTTP 500 cuando recibe parámetros
    desconocidos.
    """

    final_url = (
        url_sin_cache(url)
        if cache
        else url
    )

    response = S.get(
        final_url,
        timeout=TIMEOUT,
        allow_redirects=True,
    )

    response.raise_for_status()

    return response


def soup(url, cache=True):
    response = get(
        url,
        cache=cache
    )

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
# DETECCIÓN DE FECHAS
# ============================================================

def detectar_fecha(texto):
    """
    Detecta:

    21 de agosto de 2026
    21 de agosto
    agosto 21
    agosto 21, 2026
    21 agosto 2026
    """

    if not texto:
        return None

    texto = clean(texto).lower()

    # --------------------------------------------------------
    # 21 de agosto de 2026
    # --------------------------------------------------------

    patron1 = re.compile(
        r"\b"
        r"(\d{1,2})"
        r"\s+de\s+"
        r"(enero|febrero|marzo|abril|mayo|junio|"
        r"julio|agosto|septiembre|octubre|noviembre|diciembre)"
        r"\s+de\s+"
        r"(\d{4})"
        r"\b",
        re.I,
    )

    match = patron1.search(texto)

    if match:

        dia = int(match.group(1))
        mes = MESES_MAP.get(
            match.group(2).lower()
        )
        ano = int(match.group(3))

        if mes:

            try:
                return dt.date(
                    ano,
                    mes,
                    dia
                )
            except ValueError:
                pass

    # --------------------------------------------------------
    # 21 agosto 2026
    # --------------------------------------------------------

    patron2 = re.compile(
        r"\b"
        r"(\d{1,2})"
        r"\s+"
        r"(enero|febrero|marzo|abril|mayo|junio|"
        r"julio|agosto|septiembre|octubre|noviembre|diciembre)"
        r"\s+"
        r"(\d{4})"
        r"\b",
        re.I,
    )

    match = patron2.search(texto)

    if match:

        dia = int(match.group(1))
        mes = MESES_MAP.get(
            match.group(2).lower()
        )
        ano = int(match.group(3))

        if mes:

            try:
                return dt.date(
                    ano,
                    mes,
                    dia
                )
            except ValueError:
                pass

    # --------------------------------------------------------
    # agosto 21, 2026
    # --------------------------------------------------------

    patron3 = re.compile(
        r"\b"
        r"(enero|febrero|marzo|abril|mayo|junio|"
        r"julio|agosto|septiembre|octubre|noviembre|diciembre)"
        r"\s+"
        r"(\d{1,2})"
        r"(?:,\s*|\s+)"
        r"(\d{4})"
        r"\b",
        re.I,
    )

    match = patron3.search(texto)

    if match:

        mes = MESES_MAP.get(
            match.group(1).lower()
        )
        dia = int(match.group(2))
        ano = int(match.group(3))

        if mes:

            try:
                return dt.date(
                    ano,
                    mes,
                    dia
                )
            except ValueError:
                pass

    # --------------------------------------------------------
    # agosto 21
    #
    # KCM actualmente muestra este formato.
    # El año se determina por el contexto de la ejecución.
    # --------------------------------------------------------

    patron4 = re.compile(
        r"\b"
        r"(enero|febrero|marzo|abril|mayo|junio|"
        r"julio|agosto|septiembre|octubre|noviembre|diciembre)"
        r"\s+"
        r"(\d{1,2})"
        r"\b",
        re.I,
    )

    match = patron4.search(texto)

    if match:

        mes = MESES_MAP.get(
            match.group(1).lower()
        )
        dia = int(match.group(2))

        if mes:

            ano_actual = fecha_bogota().year

            try:
                return dt.date(
                    ano_actual,
                    mes,
                    dia
                )
            except ValueError:
                pass

    return None


# ============================================================
# DETECTAR FECHA ACTUAL
# ============================================================

def contiene_fecha_del_dia(texto, hoy):

    if not texto:
        return False

    fecha = detectar_fecha(texto)

    return (
        fecha is not None
        and fecha == hoy
    )


# ============================================================
# EN CONTACTO
# ============================================================

def extraer_encontacto():

    url = (
        "https://www.encontactoglobal.org/"
        "lea/devocionales-diarios"
    )

    response = get(url)

    s = BeautifulSoup(
        response.text,
        "html.parser"
    )

    hoy = fecha_bogota()

    fecha_hoy_texto = fecha_es(hoy).lower()

    # --------------------------------------------------------
    # ENCONTRAR EL BLOQUE DE HOY
    # --------------------------------------------------------
    #
    # Este es el cambio más importante.
    #
    # Antes el scraper buscaba el primer h2/h3 corto,
    # lo que hacía que encontrara:
    #
    # "Cómo forjar relaciones sólidas"
    #
    # que pertenece a "El Mensaje de esta Semana".
    #
    # Ahora buscamos primero el texto que contiene la
    # fecha de HOY y luego buscamos el encabezado asociado.
    # --------------------------------------------------------

    fecha_elemento = None

    for tag in s.find_all(
        ["time", "p", "div", "span", "article"]
    ):

        texto = clean(
            tag.get_text(
                " ",
                strip=True
            )
        )

        if not texto:
            continue

        if fecha_hoy_texto in texto.lower():

            # Evitar contenedores gigantes.
            if len(texto) < 1000:

                fecha_elemento = tag
                break

    titulo = ""

    # --------------------------------------------------------
    # BUSCAR TÍTULO CERCA DE LA FECHA
    # --------------------------------------------------------

    if fecha_elemento:

        # Buscar encabezados dentro del contenedor.
        padre = fecha_elemento

        for _ in range(5):

            if not padre:
                break

            for tag in padre.find_all(
                ["h1", "h2", "h3", "h4"]
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
                    "meditaciones diarias",
                    "devocionales diarios",
                    "meditación diaria",
                    "en contacto",
                }:
                    continue

                if (
                    len(texto) >= 4
                    and len(texto) < 150
                ):
                    titulo = texto
                    break

            if titulo:
                break

            padre = padre.parent

    # --------------------------------------------------------
    # SEGUNDA ESTRATEGIA:
    # RECORRER ENCABEZADOS Y BUSCAR EL QUE TENGA LA FECHA
    # DEL DÍA EN SU CONTENEDOR.
    # --------------------------------------------------------

    if not titulo:

        for tag in s.find_all(
            ["h1", "h2", "h3", "h4"]
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
                "meditaciones diarias",
                "devocionales diarios",
                "meditación diaria",
                "en contacto",
            }:
                continue

            padre = tag

            for _ in range(5):

                if not padre:
                    break

                bloque = clean(
                    padre.get_text(
                        " ",
                        strip=True
                    )
                )

                if (
                    fecha_hoy_texto in
                    bloque.lower()
                ):

                    titulo = texto
                    break

                padre = padre.parent

            if titulo:
                break

    # --------------------------------------------------------
    # TERCERA ESTRATEGIA:
    # OPEN GRAPH
    # --------------------------------------------------------

    if not titulo:

        og = s.find(
            "meta",
            attrs={
                "property": "og:title"
            }
        )

        if og:

            posible = clean(
                og.get(
                    "content",
                    ""
                )
            )

            if posible:

                titulo = posible

    if not titulo:

        raise RuntimeError(
            "En Contacto: no se encontró "
            "el título del devocional actual."
        )

    # --------------------------------------------------------
    # ENCONTRAR EL ENCABEZADO REAL
    # --------------------------------------------------------

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
            texto.lower()
            == titulo.lower()
        ):

            titulo_elemento = tag
            break

    # --------------------------------------------------------
    # FECHA
    # --------------------------------------------------------

    fecha = hoy

    if titulo_elemento:

        padre = titulo_elemento

        for _ in range(7):

            if not padre:
                break

            texto = clean(
                padre.get_text(
                    " ",
                    strip=True
                )
            )

            encontrada = detectar_fecha(
                texto
            )

            if encontrada:

                fecha = encontrada
                break

            padre = padre.parent

    # Como ya sabemos que encontramos el bloque de hoy,
    # aceptamos explícitamente la fecha actual.
    if fecha != hoy:

        texto_total = clean(
            s.get_text(
                " ",
                strip=True
            )
        )

        if fecha_hoy_texto in texto_total.lower():
            fecha = hoy

    if fecha != hoy:

        raise RuntimeError(
            "En Contacto: el bloque encontrado "
            "no corresponde a la fecha actual."
        )

    # --------------------------------------------------------
    # SUBTÍTULO
    # --------------------------------------------------------

    subtitulo = ""

    if titulo_elemento:

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

            if (
                fecha_hoy_texto
                in texto.lower()
            ):
                continue

            if len(texto) < 25:
                continue

            low = texto.lower()

            if any(
                x in low
                for x in (
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

    texto_total = clean(
        s.get_text(
            " ",
            strip=True
        )
    )

    patron_versiculo = re.search(
        r"\b"
        r"(Génesis|Éxodo|Levítico|Números|"
        r"Deuteronomio|Josué|Jueces|Rut|"
        r"Samuel|Reyes|Crónicas|Esdras|"
        r"Nehemías|Ester|Job|Salmos|"
        r"Proverbios|Eclesiastés|Cantares|"
        r"Isaías|Jeremías|Lamentaciones|"
        r"Ezequiel|Daniel|Oseas|Joel|Amós|"
        r"Abdías|Jonás|Miqueas|Nahúm|Habacuc|"
        r"Sofonías|Hageo|Zacarías|Malaquías|"
        r"Mateo|Marcos|Lucas|Juan|Hechos|"
        r"Romanos|1 Corintios|2 Corintios|"
        r"Gálatas|Efesios|Filipenses|"
        r"Colosenses|1 Tesalonicenses|"
        r"2 Tesalonicenses|1 Timoteo|2 Timoteo|"
        r"Tito|Filemón|Hebreos|Santiago|"
        r"1 Pedro|2 Pedro|1 Juan|2 Juan|"
        r"3 Juan|Judas|Apocalipsis)"
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

            # Navegación.
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
                fecha_hoy_texto
                in low
            ):
                continue

            if (
                versiculo
                and low == versiculo.lower()
            ):
                continue

            if len(texto) < 35:
                continue

            if texto in parrafos:
                continue

            parrafos.append(texto)

            if len(parrafos) >= 20:
                break

    # --------------------------------------------------------
    # LIMPIEZA
    # --------------------------------------------------------

    limpias = []

    for texto in parrafos:

        low = texto.lower()

        if any(
            x in low
            for x in (
                "explore cómo las relaciones",
                "la espera pone a prueba",
                "opciones de transmisión digital",
                "para disfrutar de excelente enseñanza",
                "escuchar radio radio",
                "ver ver video",
            )
        ):
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

    if not parrafos:
        raise RuntimeError(
            "En Contacto: no se encontró "
            "el cuerpo del devocional."
        )

    return {
        "titulo": titulo,
        "subtitulo": subtitulo,
        "versiculo": versiculo,
        "parrafos": parrafos[:20],
        "audio_url": audio,
        "audio_tipo": "mp3",
        "fecha": fecha_es(hoy),
        "fecha_iso": fecha_iso(hoy),
        "link": url,
    }


# ============================================================
# BAYLESS CONLEY
# ============================================================

def obtener_bayless_directo(url):

    """
    Descarga Bayless SIN añadir _devocionales_cache.

    Esto es importante porque la ejecución que mostraste
    recibió HTTP 500 precisamente sobre una URL de
    respuestasbc.com con ese parámetro.
    """

    return get(
        url,
        cache=False
    )


def encontrar_articulo_bayless():

    candidatos = []

    # --------------------------------------------------------
    # 1. API WORDPRESS
    # --------------------------------------------------------

    api_urls = [
        (
            "https://www.respuestasbc.com/"
            "wp-json/wp/v2/devotional"
            "?per_page=5&orderby=date&order=desc"
        ),
        (
            "https://www.respuestasbc.com/"
            "wp-json/wp/v2/posts"
            "?per_page=10&orderby=date&order=desc"
        ),
    ]

    for api_url in api_urls:

        try:

            response = obtener_bayless_directo(
                api_url
            )

            if response.status_code != 200:
                continue

            items = response.json()

            if not isinstance(items, list):
                continue

            for item in items:

                if not isinstance(
                    item,
                    dict
                ):
                    continue

                link = item.get(
                    "link"
                )

                if link:
                    candidatos.append(
                        link
                    )

        except Exception:
            continue

    # --------------------------------------------------------
    # 2. PÁGINA DE DEVOCIONALES
    # --------------------------------------------------------

    landing_urls = [
        "https://www.respuestasbc.com/devotional/",
        "https://www.respuestasbc.com/devocionales/",
        "https://www.respuestasbc.com/un-estilo-de-vida-de-fe/",
    ]

    for landing in landing_urls:

        try:

            response = obtener_bayless_directo(
                landing
            )

            if response.status_code != 200:
                continue

            s = BeautifulSoup(
                response.text,
                "html.parser"
            )

            for a in s.find_all(
                "a",
                href=True
            ):

                href = a.get(
                    "href",
                    ""
                ).strip()

                if not href:
                    continue

                low = href.lower()

                if (
                    "respuestasbc.com"
                    not in low
                ):
                    continue

                if any(
                    x in low
                    for x in (
                        "facebook",
                        "instagram",
                        "youtube",
                        "twitter",
                        "#",
                    )
                ):
                    continue

                texto = clean(
                    a.get_text(
                        " ",
                        strip=True
                    )
                )

                if len(texto) >= 4:

                    candidatos.append(
                        href
                    )

        except Exception:
            continue

    # --------------------------------------------------------
    # QUITAR DUPLICADOS
    # --------------------------------------------------------

    unicos = []

    vistos = set()

    for url in candidatos:

        if url in vistos:
            continue

        vistos.add(url)
        unicos.append(url)

    # --------------------------------------------------------
    # PROBAR CANDIDATOS
    # --------------------------------------------------------

    hoy = fecha_bogota()

    mejor = None
    mejor_fecha = None

    for articulo_url in unicos[:30]:

        try:

            response = obtener_bayless_directo(
                articulo_url
            )

            if response.status_code != 200:
                continue

            s = BeautifulSoup(
                response.text,
                "html.parser"
            )

            texto_total = clean(
                s.get_text(
                    " ",
                    strip=True
                )
            )

            fecha = detectar_fecha(
                texto_total
            )

            if fecha is None:
                continue

            if fecha > hoy:
                continue

            if (
                mejor_fecha is None
                or fecha > mejor_fecha
            ):

                mejor_fecha = fecha
                mejor = articulo_url

        except Exception:
            continue

    if mejor:

        return mejor

    raise RuntimeError(
        "Bayless: no se pudo localizar "
        "el artículo más reciente."
    )


def extraer_bayless():

    articulo_url = (
        encontrar_articulo_bayless()
    )

    response = obtener_bayless_directo(
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

    titulo = re.sub(
        r"^\s*#\s*\d+\s*[-–—:]?\s*",
        "",
        titulo
    ).strip()

    if titulo.lower() in {
        "devocional diario",
        "respuestas para cada día",
        "bayless conley",
        "respuestas para cada dia",
    }:

        raise RuntimeError(
            "Bayless: se encontró "
            "un encabezado general."
        )

    # --------------------------------------------------------
    # FECHA
    # --------------------------------------------------------

    fecha = None

    if h1:

        padre = h1

        for _ in range(8):

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

        contenedor = h1

        mejor_contenedor = None

        for _ in range(8):

            if not contenedor:
                break

            cantidad_p = len(
                contenedor.find_all(
                    "p"
                )
            )

            texto_contenedor = clean(
                contenedor.get_text(
                    " ",
                    strip=True
                )
            )

            if (
                cantidad_p >= 3
                and len(texto_contenedor) > 500
            ):

                mejor_contenedor = (
                    contenedor
                )
                break

            contenedor = contenedor.parent

        if mejor_contenedor:

            elementos = (
                mejor_contenedor.find_all(
                    ["p", "blockquote"]
                )
            )

        else:

            elementos = (
                h1.find_all_next(
                    ["p", "blockquote"]
                )
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

            if any(
                marca in low
                for marca in (
                    "there was an error submitting",
                    "me gustaría recibir",
                    "recibir los correos",
                    "suscrib",
                    "copyright",
                    "todos los derechos reservados",
                )
            ):
                continue

            if "© 2026" in texto:
                break

            if len(texto) < 20:
                continue

            if texto in parrafos:
                continue

            parrafos.append(texto)

            if len(parrafos) >= 20:
                break

    # --------------------------------------------------------
    # AUDIO SOUNDCLOUD
    # --------------------------------------------------------

    audio = ""

    for a in s.find_all(
        "a",
        href=True
    ):

        href = a[
            "href"
        ].strip()

        if (
            "soundcloud.com/respuestasbc/"
            in href
            and "/sets/" not in href
        ):

            audio = href
            break

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

    urls = [
        "https://main.kcmlatino.org/devotional",
        "https://main.kcmlatino.org/devotional/",
    ]

    ultimo_error = None

    for url in urls:

        try:

            response = get(
                url,
                cache=True
            )

            return response

        except Exception as exc:

            ultimo_error = exc

    raise RuntimeError(
        f"Kenneth: no se pudo acceder a KCM: "
        f"{ultimo_error}"
    )


def extraer_kenneth():

    response = encontrar_kcm()

    s = BeautifulSoup(
        response.text,
        "html.parser"
    )

    html = str(s)

    hoy = fecha_bogota()

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

    # Primero intentar encontrar el bloque asociado al h1.

    if h1:

        padre = h1

        for _ in range(8):

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

    # --------------------------------------------------------
    # Si KCM está mostrando solamente:
    #
    # agosto 21
    #
    # detectar_fecha() ahora lo acepta.
    # --------------------------------------------------------

    if not fecha:

        texto_total = clean(
            s.get_text(
                " ",
                strip=True
            )
        )

        fecha = detectar_fecha(
            texto_total
        )

    # --------------------------------------------------------
    # CONTENIDO
    # --------------------------------------------------------

    parrafos = []

    if h1:

        contenedor = h1

        mejor = None

        for _ in range(8):

            if not contenedor:
                break

            cantidad = len(
                contenedor.find_all(
                    "p"
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

            elementos = (
                mejor.find_all(
                    ["p", "blockquote"]
                )
            )

        else:

            elementos = (
                h1.find_all_next(
                    ["p", "blockquote"]
                )
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

            if any(
                marca in low
                for marca in (
                    "copyright",
                    "todos los derechos reservados",
                    "contenido relacionado",
                    "devotional type",
                    "loading",
                    "más opciones para compartir",
                    "más opciones",
                    "widgets",
                )
            ):
                continue

            if len(texto) < 20:
                continue

            if texto in parrafos:
                continue

            parrafos.append(texto)

            if len(parrafos) >= 20:
                break

    # --------------------------------------------------------
    # VERSÍCULO
    # --------------------------------------------------------

    versiculo = ""

    for texto in parrafos[:5]:

        if (
            "«" in texto
            or "(" in texto
        ):

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

    # KCM puede mostrar el mes y día del artículo
    # sin año. detectar_fecha() le asigna el año actual.
    #
    # No aceptar artículos de otro día.

    if fecha != hoy:

        raise RuntimeError(
            "Kenneth: el artículo encontrado "
            f"corresponde a {fecha_es(fecha)}, "
            f"no a {fecha_es(hoy)}."
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

        if isinstance(
            data,
            dict
        ):

            return data

    except Exception as exc:

        print(
            "Aviso: no se pudo leer "
            f"data.json anterior: {exc}",
            file=sys.stderr
        )

    return {}


# ============================================================
# VALIDACIÓN DEL DÍA
# ============================================================

def es_del_dia(item, hoy):

    if not valid(item):
        return False

    fecha_item = item.get(
        "fecha_iso"
    )

    if fecha_item:

        return (
            fecha_item
            == fecha_iso(hoy)
        )

    fecha_texto = item.get(
        "fecha",
        ""
    )

    fecha_detectada = detectar_fecha(
        fecha_texto
    )

    if fecha_detectada:

        return (
            fecha_detectada
            == hoy
        )

    return False


# ============================================================
# CONSULTAR LAS TRES FUENTES
# ============================================================

def consultar_fuentes(hoy):

    funciones = {
        "encontacto": extraer_encontacto,
        "bayless": extraer_bayless,
        "kenneth": extraer_kenneth,
    }

    resultados = {}

    for clave, funcion in funciones.items():

        print()
        print(
            f"Consultando {clave}..."
        )

        try:

            item = funcion()

            print(
                f"  Título: "
                f"{item.get('titulo')}"
            )

            print(
                f"  Fecha: "
                f"{item.get('fecha')}"
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
# GUARDAR DATA.JSON
# ============================================================

def guardar_data(
    anterior,
    nuevos,
    hoy
):

    data = dict(anterior)

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

            # Conservar el último contenido válido.
            data[clave] = anterior[
                clave
            ]

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
    print(
        "ACTUALIZADOR DE DEVOCIONALES DIARIOS"
    )
    print("=" * 60)

    print(
        f"Fecha esperada en Colombia: "
        f"{fecha_es(hoy)}"
    )

    print(
        "Modo: una consulta por ejecución"
    )

    print("=" * 60)

    anterior = load_previous()

    for intento in range(
        1,
        MAX_INTENTOS + 1
    ):

        print()
        print("=" * 60)
        print(
            f"INTENTO {intento}/{MAX_INTENTOS}"
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

            if resultados.get(
                clave
            ):

                actualizados.append(
                    clave
                )

            else:

                pendientes.append(
                    clave
                )

        # ----------------------------------------------------
        # GUARDAR INMEDIATAMENTE LO QUE SÍ ESTÉ ACTUALIZADO
        # ----------------------------------------------------

        guardar_data(
            anterior,
            resultados,
            hoy
        )

        anterior = load_previous()

        print()
        print(
            f"Actualizados correctamente: "
            f"{len(actualizados)}/3"
        )

        for clave in actualizados:

            print(
                f"  OK - {clave}: "
                f"{resultados[clave]['titulo']}"
            )

        if pendientes:

            print()
            print(
                "Pendientes:"
            )

            for clave in pendientes:

                print(
                    f"  - {clave}"
                )

        # ----------------------------------------------------
        # LOS TRES ESTÁN ACTUALIZADOS
        # ----------------------------------------------------

        if len(actualizados) == 3:

            print()
            print("=" * 60)
            print(
                "LOS 3 DEVOCIONALES "
                "ESTÁN ACTUALIZADOS."
            )
            print("=" * 60)

            return 0

        # ----------------------------------------------------
        # NO FALLAR EL WORKFLOW
        # ----------------------------------------------------
        #
        # Si una fuente todavía no publicó el devocional,
        # conservamos el último dato válido y terminamos.
        #
        # El workflow volverá a ejecutarse en su próximo
        # horario programado.
        # ----------------------------------------------------

        print()
        print(
            "Todavía faltan fuentes."
        )

        print(
            "Se conserva el último contenido "
            "válido y esta ejecución termina."
        )

        return 0


# ============================================================
# EJECUTAR
# ============================================================

if __name__ == "__main__":

    try:

        sys.exit(
            main()
        )

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
