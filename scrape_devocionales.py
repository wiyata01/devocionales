#!/usr/bin/env python3
"""
Actualiza los tres devocionales diarios.

Características:
- Evita caché agregando un parámetro único a las URLs.
- Usa la fecha de Colombia (America/Bogota).
- No acepta una página que todavía tenga el día anterior.
- En Contacto: extrae únicamente la meditación actual.
- Bayless: extrae únicamente el artículo actual y elimina
  "Leer devocionales anteriores", suscripción y pie de página.
- Kenneth: extrae únicamente el contenido del devocional.
- Si una fuente falla, conserva el último contenido válido.
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


# ============================================================
# CONFIGURACIÓN
# ============================================================

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


# ============================================================
# SESIÓN HTTP
# ============================================================

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


# ============================================================
# UTILIDADES
# ============================================================

def clean(text):
    if not text:
        return ""

    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def today_colombia():
    """
    Fecha real de Colombia.
    """
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


def fecha_ingles(fecha=None):
    if fecha is None:
        fecha = today_colombia()

    meses = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]

    return (
        f"{meses[fecha.month - 1]} "
        f"{fecha.day}, "
        f"{fecha.year}"
    )


def url_no_cache(url):
    """
    Agrega un parámetro único para evitar que el servidor/CDN
    entregue una versión vieja de la página.
    """
    separador = "&" if "?" in url else "?"

    ahora = dt.datetime.now(
        dt.timezone.utc
    ).strftime("%Y%m%d%H%M%S")

    return f"{url}{separador}_nocache={ahora}"


def get(url):
    final_url = url_no_cache(url)

    r = S.get(
        final_url,
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
    """
    Elimina parámetros de caché de nuestras propias peticiones.
    """
    if not url:
        return ""

    url = re.sub(
        r"[?&]_nocache=\d+",
        "",
        url,
    )

    return url


def extract_mp3(html, patterns):
    for pattern in patterns:
        m = re.search(
            pattern,
            html,
            flags=re.I,
        )

        if m:
            return m.group(1).replace(
                "\\/",
                "/",
            )

    return ""


def valid(item):
    return (
        isinstance(item, dict)
        and bool(item.get("titulo"))
        and isinstance(item.get("parrafos"), list)
        and any(
            clean(x)
            for x in item.get("parrafos", [])
        )
    )


def normalizar_titulo_bayless(title):
    """
    Convierte:

    #227 El Consolador
    # 227 El Consolador
    227 El Consolador

    en:

    El Consolador
    """

    title = clean(title)

    title = re.sub(
        r"^\s*#?\s*\d+\s*[-–—:.]?\s*",
        "",
        title,
    )

    return clean(title)


# ============================================================
# VALIDACIÓN DE FECHA
# ============================================================

def validar_fecha_encontacto(s):
    """
    Comprueba que En Contacto realmente tenga la fecha de hoy.

    Acepta:
    28 de agosto de 2026
    """

    hoy = today_colombia()

    texto = s.get_text(
        " ",
        strip=True,
    )

    fecha_hoy = fecha_espanol(hoy)

    if fecha_hoy.lower() not in texto.lower():
        raise RuntimeError(
            "En Contacto todavía no muestra la fecha de hoy "
            f"({fecha_hoy}). Se conserva el contenido anterior."
        )


def validar_fecha_bayless(s):
    """
    Comprueba que Bayless tenga el día actual.

    La página usa formato:
    Today, August 28, 2026
    """

    hoy = today_colombia()

    texto = s.get_text(
        " ",
        strip=True,
    )

    fecha_hoy = fecha_ingles(hoy)

    if fecha_hoy.lower() not in texto.lower():
        raise RuntimeError(
            "Bayless todavía no muestra la fecha de hoy "
            f"({fecha_hoy}). Se conserva el contenido anterior."
        )


# ============================================================
# EN CONTACTO
# ============================================================

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

    html = str(s)

    # --------------------------------------------------------
    # IMPORTANTE:
    # No aceptamos una página atrasada.
    # --------------------------------------------------------

    validar_fecha_encontacto(s)

    # --------------------------------------------------------
    # LOCALIZAR "MEDITACIÓN DIARIA"
    # --------------------------------------------------------

    meditation_marker = None

    for tag in s.find_all(
        string=re.compile(
            r"^\s*Meditación diaria\s*$",
            re.I,
        )
    ):
        meditation_marker = tag.parent
        break

    # --------------------------------------------------------
    # TÍTULO
    # --------------------------------------------------------

    title = ""

    if meditation_marker:

        # Buscar el primer H1 posterior al marcador.
        for element in meditation_marker.find_all_next(
            ["h1", "h2"],
        ):

            texto = clean(
                element.get_text(
                    " ",
                    strip=True,
                )
            )

            if not texto:
                continue

            # Evitar títulos de navegación.
            if texto.lower() in {
                "opciones de lectura",
                "otros devocionles",
                "otros devocionales",
            }:
                continue

            title = texto
            break

    # Fallback
    if not title:

        h1 = s.find("h1")

        if h1:
            title = clean(
                h1.get_text(
                    " ",
                    strip=True,
                )
            )

    # --------------------------------------------------------
    # SUBTÍTULO
    # --------------------------------------------------------

    subtitle = ""

    if meditation_marker:

        encontrado_title = False

        for element in meditation_marker.find_all_next(
            ["h1", "h2"],
        ):

            texto = clean(
                element.get_text(
                    " ",
                    strip=True,
                )
            )

            if not texto:
                continue

            if texto == title:
                encontrado_title = True
                continue

            if encontrado_title:
                subtitle = texto
                break

    # --------------------------------------------------------
    # VERSÍCULO
    # --------------------------------------------------------

    verse = ""

    if meditation_marker:

        for a in meditation_marker.find_all_next(
            "a",
            href=True,
        ):

            href = a.get("href", "")

            if re.search(
                r"biblegateway\.com",
                href,
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

    # --------------------------------------------------------
    # AUDIO
    # --------------------------------------------------------

    audio = extract_mp3(
        html,
        [
            r"("
            r"https://intouch\.azureedge\.net/"
            r"spanish/devo/"
            r"[A-Za-z0-9_./-]+"
            r"\.mp3"
            r")",
        ],
    )

    # --------------------------------------------------------
    # TEXTO DEL DEVOCIONAL
    # --------------------------------------------------------

    paragraphs = []

    # Localizamos el título real.
    title_tag = None

    for h in s.find_all("h1"):
        if clean(
            h.get_text(
                " ",
                strip=True,
            )
        ) == title:
            title_tag = h
            break

    if title_tag:

        # Empezamos DESPUÉS del H1.
        for element in title_tag.find_all_next():

            # ------------------------------------------------
            # PARAR antes de "Otros devocionales"
            # ------------------------------------------------

            if element.name in ["h2", "h3"]:

                texto_h = clean(
                    element.get_text(
                        " ",
                        strip=True,
                    )
                ).lower()

                if (
                    "otros devoc" in texto_h
                    or "biblia en un año" in texto_h
                ):
                    break

            # ------------------------------------------------
            # PARAR en la sección de Biblia en un año
            # ------------------------------------------------

            texto = clean(
                element.get_text(
                    " ",
                    strip=True,
                )
            )

            low = texto.lower()

            if (
                "biblia en un año:" in low
                or low == "biblia en un año"
            ):
                break

            # ------------------------------------------------
            # Solo P y LI
            # ------------------------------------------------

            if element.name not in ["p", "li"]:
                continue

            # Evitar elementos que estén dentro de otro
            # P/LI y así evitar duplicaciones.
            if element.find_parent(
                ["p", "li"]
            ):
                continue

            if not texto:
                continue

            # El versículo no forma parte del cuerpo.
            if texto == verse:
                continue

            # El texto de navegación no forma parte.
            if len(texto) < 25:
                continue

            if any(
                x in low
                for x in (
                    "suscríbase",
                    "suscribirse",
                    "correo electrónico",
                    "opciones de lectura",
                    "facebook",
                    "instagram",
                    "twitter",
                    "youtube",
                )
            ):
                continue

            paragraphs.append(texto)

    # --------------------------------------------------------
    # Si el selector anterior no encontró suficiente texto,
    # usamos una segunda estrategia limitada.
    # --------------------------------------------------------

    if len(paragraphs) < 1:

        paragraphs = []

        started = False

        for element in s.find_all(
            ["p", "li"]
        ):

            texto = clean(
                element.get_text(
                    " ",
                    strip=True,
                )
            )

            if not texto:
                continue

            if title and title in texto:
                started = True
                continue

            if not started:
                continue

            low = texto.lower()

            if (
                "biblia en un año" in low
                or "otros devoc" in low
            ):
                break

            if len(texto) < 25:
                continue

            paragraphs.append(texto)

    # --------------------------------------------------------
    # Eliminar duplicados manteniendo orden.
    # --------------------------------------------------------

    vistos = set()
    limpios = []

    for p in paragraphs:

        clave = clean(p).lower()

        if clave in vistos:
            continue

        vistos.add(clave)
        limpios.append(p)

    paragraphs = limpios[:20]

    # --------------------------------------------------------
    # VALIDACIÓN
    # --------------------------------------------------------

    if not title:
        raise RuntimeError(
            "En Contacto: no se encontró el título."
        )

    if not paragraphs:
        raise RuntimeError(
            "En Contacto: no se encontró el cuerpo "
            "del devocional."
        )

    # Evitar títulos generales.
    if title.lower() in {
        "meditación diaria",
        "devocional diario",
    }:
        raise RuntimeError(
            "En Contacto: se obtuvo un título general "
            "en lugar del título del devocional."
        )

    return {
        "titulo": title,
        "subtitulo": subtitle,
        "versiculo": verse,
        "parrafos": paragraphs,
        "audio_url": audio,
        "audio_tipo": "mp3",
        "link": clean_url(r.url),
    }


# ============================================================
# BAYLESS CONLEY
# ============================================================

def scrape_bayless():

    landing = (
        "https://www.respuestasbc.com/"
        "?redirect_to=latest&post_type=devotional"
    )

    r = get(landing)

    s = BeautifulSoup(
        r.text,
        "html.parser",
    )

    html = str(s)

    # --------------------------------------------------------
    # NO aceptar contenido de ayer.
    # --------------------------------------------------------

    validar_fecha_bayless(s)

    # --------------------------------------------------------
    # ENCONTRAR EL TÍTULO REAL DEL ARTÍCULO
    # --------------------------------------------------------

    title = ""

    article_title_tag = None

    for h1 in s.find_all("h1"):

        texto = clean(
            h1.get_text(
                " ",
                strip=True,
            )
        )

        if not texto:
            continue

        normalizado = texto.lower()

        if normalizado in {
            "devocional diario",
            "respuestas para cada día",
            "bayless conley",
        }:
            continue

        if re.match(
            r"^#?\s*\d+",
            texto,
        ):

            title = normalizar_titulo_bayless(
                texto
            )

            article_title_tag = h1
            break

    # Si no encontramos un H1 con número,
    # buscar otros encabezados.
    if not title:

        for tag in s.find_all(
            ["h2", "h3"]
        ):

            texto = clean(
                tag.get_text(
                    " ",
                    strip=True,
                )
            )

            if not texto:
                continue

            if texto.lower() in {
                "devocional diario",
                "respuestas para cada día",
                "bayless conley",
                "leer devocionales anteriores",
            }:
                continue

            if re.match(
                r"^#?\s*\d+",
                texto,
            ):

                title = normalizar_titulo_bayless(
                    texto
                )

                article_title_tag = tag
                break

    # OpenGraph como respaldo.
    if not title:

        og = s.find(
            "meta",
            attrs={
                "property": "og:title"
            },
        )

        if og:

            title = normalizar_titulo_bayless(
                og.get(
                    "content",
                    "",
                )
            )

    if not title:
        raise RuntimeError(
            "Bayless: no se encontró el título "
            "del artículo."
        )

    # Nunca permitir un título general.
    if title.lower() in {
        "devocional diario",
        "respuestas para cada día",
        "bayless conley",
    }:
        raise RuntimeError(
            "Bayless: se obtuvo el título general "
            "del sitio."
        )

    # --------------------------------------------------------
    # TEXTO DEL ARTÍCULO
    # --------------------------------------------------------

    paragraphs = []

    # Buscar el contenedor del artículo.
    article = None

    if article_title_tag:

        # Intentar encontrar el ARTICLE más cercano.
        article = article_title_tag.find_parent(
            "article"
        )

        # Si no existe, buscar un contenedor razonable.
        if article is None:

            parent = article_title_tag.parent

            for _ in range(5):

                if parent is None:
                    break

                texto_parent = clean(
                    parent.get_text(
                        " ",
                        strip=True,
                    )
                )

                if len(texto_parent) > 500:
                    article = parent
                    break

                parent = parent.parent

    if article is None:
        article = s

    # --------------------------------------------------------
    # Extraer P y BLOCKQUOTE del artículo.
    # --------------------------------------------------------

    for element in article.find_all(
        ["p", "blockquote"]
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

        # ----------------------------------------------------
        # CORTES IMPORTANTES
        # ----------------------------------------------------

        if (
            "leer devocionales anteriores" in low
            or "¿quieres respuestas directo" in low
            or "suscríbete a nuestro devocional" in low
            or "me gustaría recibir los correos" in low
            or "there was an error submitting" in low
            or "no te enviaremos spam" in low
            or "powered by kit" in low
            or "necesitas ayuda" in low
        ):
            break

        # ----------------------------------------------------
        # No incluir el enlace de audio como texto.
        # ----------------------------------------------------

        if (
            "escuche este devocional" in low
            or "haga click aquí" in low
            or "hacer click" in low
        ):
            continue

        # ----------------------------------------------------
        # Evitar navegación.
        # ----------------------------------------------------

        if any(
            x in low
            for x in (
                "recibir devocionales diarios",
                "devocionales diarios gratis",
                "suscrib",
            )
        ):
            continue

        if len(texto) < 20:
            continue

        # Evitar duplicados.
        if texto in paragraphs:
            continue

        paragraphs.append(texto)

    # --------------------------------------------------------
    # IMPORTANTE:
    # Nunca usar todos los <p> de la página como fallback
    # porque eso es precisamente lo que estaba arrastrando
    # el devocional anterior y el formulario.
    # --------------------------------------------------------

    if not paragraphs:
        raise RuntimeError(
            "Bayless: no se encontró el cuerpo "
            "del devocional."
        )

    # --------------------------------------------------------
    # AUDIO SOUNDCLOUD
    # --------------------------------------------------------

    audio = ""

    # Primero buscar enlace dentro del artículo.
    for a in article.find_all(
        "a",
        href=True,
    ):

        href = a.get("href", "").strip()

        if (
            "soundcloud.com/respuestasbc/"
            in href.lower()
            and "/sets/" not in href.lower()
        ):

            audio = href
            break

    # Buscar también URLs incrustadas.
    if not audio:

        m = re.search(
            r"https?://(?:www\.)?"
            r"soundcloud\.com/"
            r"respuestasbc/"
            r"[A-Za-z0-9_-]+",
            html,
            flags=re.I,
        )

        if m:
            audio = m.group(0)

    return {
        "titulo": title,
        "subtitulo": "",
        "versiculo": "",
        "parrafos": paragraphs[:30],
        "audio_url": audio,
        "audio_tipo": "soundcloud",
        "link": clean_url(r.url),
    }


# ============================================================
# KENNETH COPELAND
# ============================================================

def scrape_kenneth():

    url = "https://main.kcmlatino.org/devocional"

    r = get(url)

    return _scrape_kcm_page(
        clean_url(r.url),
        r.text,
    )


def _scrape_kcm_page(
    url,
    html,
):

    s = BeautifulSoup(
        html,
        "html.parser",
    )

    # --------------------------------------------------------
    # TÍTULO
    # --------------------------------------------------------

    title = ""

    h1 = s.find("h1")

    if h1:

        title = clean(
            h1.get_text(
                " ",
                strip=True,
            )
        )

    if not title:

        og = s.find(
            "meta",
            attrs={
                "property": "og:title"
            },
        )

        if og:

            title = clean(
                og.get(
                    "content",
                    "",
                )
            )

    # --------------------------------------------------------
    # TEXTO
    # --------------------------------------------------------

    paragraphs = []

    for p in s.find_all("p"):

        text = clean(
            p.get_text(
                " ",
                strip=True,
            )
        )

        if not text:
            continue

        low = text.lower()

        if len(text) < 20:
            continue

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

        if text in paragraphs:
            continue

        paragraphs.append(text)

    # --------------------------------------------------------
    # VERSÍCULO
    # --------------------------------------------------------

    verse = ""

    for text in paragraphs[:6]:

        low = text.lower()

        if (
            "«" in text
            or "(hebreos" in low
            or "(salmos" in low
            or "(juan" in low
            or "(romanos" in low
        ):

            verse = text
            break

    # --------------------------------------------------------
    # AUDIO
    # --------------------------------------------------------

    audio = extract_mp3(
        html,
        [
            r"("
            r"https://maincms\.nyc3\.digitaloceanspaces\.com/"
            r"[A-Za-z0-9_./-]+\.mp3"
            r")",

            r"(?:src|data-src|audio)"
            r"[\"'=:\s]+"
            r"(https://maincms\.nyc3\.digitaloceanspaces\.com/"
            r"[A-Za-z0-9_./-]+\.mp3)",
        ],
    )

    # URLs escapadas.
    if not audio:

        m = re.search(
            r"(https?:\\?/\\?/"
            r"maincms\.nyc3\.digitaloceanspaces\.com"
            r"\\?/"
            r"[A-Za-z0-9_./-]+\.mp3)",
            html,
            flags=re.I,
        )

        if m:

            audio = m.group(
                1
            ).replace(
                "\\/",
                "/",
            )

    # --------------------------------------------------------
    # VALIDACIÓN
    # --------------------------------------------------------

    if not title:
        raise RuntimeError(
            "Kenneth: no se encontró título."
        )

    if not paragraphs:
        raise RuntimeError(
            "Kenneth: no se encontró texto."
        )

    return {
        "titulo": title,
        "subtitulo": "",
        "versiculo": verse,
        "parrafos": paragraphs[:30],
        "audio_url": audio,
        "audio_tipo": "mp3",
        "link": url,
    }


# ============================================================
# CARGAR DATOS ANTERIORES
# ============================================================

def load_previous():

    if not DATA_FILE.exists():
        return {}

    try:

        with DATA_FILE.open(
            "r",
            encoding="utf-8",
        ) as f:

            data = json.load(f)

        if isinstance(data, dict):
            return data

        return {}

    except Exception as exc:

        print(
            "Aviso: no se pudo leer data.json anterior:",
            exc,
            file=sys.stderr,
        )

        return {}


# ============================================================
# MAIN
# ============================================================

def main():

    hoy = today_colombia()

    fecha_hoy = fecha_espanol(hoy)

    ahora = dt.datetime.now(
        ZoneInfo("America/Bogota")
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

    errores = []

    exitos = 0

    for clave, fn in fuentes.items():

        try:

            print(
                f"\n--- Actualizando {clave} ---"
            )

            nuevo = fn()

            if not valid(nuevo):

                raise RuntimeError(
                    "La fuente respondió, pero "
                    "faltan título o texto válido."
                )

            # ------------------------------------------------
            # Validaciones específicas adicionales.
            # ------------------------------------------------

            if clave == "encontacto":

                if nuevo["titulo"].lower() in {
                    "meditación diaria",
                    "devocional diario",
                }:
                    raise RuntimeError(
                        "En Contacto devolvió un título general."
                    )

            if clave == "bayless":

                if nuevo["titulo"].lower() in {
                    "devocional diario",
                    "respuestas para cada día",
                    "bayless conley",
                }:
                    raise RuntimeError(
                        "Bayless devolvió un título general."
                    )

            # ------------------------------------------------
            # Guardar.
            # ------------------------------------------------

            data[clave] = nuevo

            exitos += 1

            print(
                f"OK  - {clave}: "
                f"{nuevo['titulo']!r}"
            )

            print(
                f"      Párrafos: "
                f"{len(nuevo['parrafos'])}"
            )

            if nuevo.get("audio_url"):
                print(
                    "      Audio: OK"
                )
            else:
                print(
                    "      Audio: no encontrado"
                )

        except Exception as exc:

            errores.append(
                f"{clave}: {exc}"
            )

            print(
                f"FAIL - {clave}: {exc}",
                file=sys.stderr,
            )

            # ------------------------------------------------
            # MUY IMPORTANTE:
            # si falla una fuente, NO destruimos el contenido
            # anterior que sí era válido.
            # ------------------------------------------------

            if valid(
                old.get(clave)
            ):

                data[clave] = old[clave]

                print(
                    f"      Se conserva el último "
                    f"contenido válido de {clave}."
                )

            else:

                data[clave] = None

    # --------------------------------------------------------
    # Nunca guardar un data.json vacío.
    # --------------------------------------------------------

    if (
        exitos == 0
        and not any(
            valid(old.get(k))
            for k in fuentes
        )
    ):

        raise RuntimeError(
            "Ninguna fuente pudo actualizarse "
            "y no existe contenido anterior válido."
        )

    # --------------------------------------------------------
    # GUARDAR JSON
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # RESUMEN
    # --------------------------------------------------------

    print(
        "\n========================================"
    )

    print(
        f"Fecha Colombia: {fecha_hoy}"
    )

    print(
        f"Actualización terminada: "
        f"{exitos}/3 fuentes actualizadas."
    )

    if errores:

        print(
            "\nFuentes con problemas:",
            file=sys.stderr,
        )

        for error in errores:

            print(
                f" - {error}",
                file=sys.stderr,
            )

    print(
        "========================================"
    )


if __name__ == "__main__":
    main()
