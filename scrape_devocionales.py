#!/usr/bin/env python3
"""
Actualizador robusto de devocionales diarios.

Fuentes:
1. En Contacto
2. Bayless Conley
3. Kenneth Copeland

Funcionamiento:
- Usa la fecha de Colombia (America/Bogota).
- Comienza normalmente a las 02:10 hora de Colombia.
- Si una fuente todavía no publicó el contenido del día,
  se vuelve a consultar cada 20 minutos.
- Termina únicamente cuando las 3 fuentes están actualizadas.
- Conserva el último contenido válido mientras una fuente no esté lista.
- Evita depender de títulos específicos de días anteriores.
"""

import datetime as dt
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, quote_plus
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ============================================================
# CONFIGURACIÓN
# ============================================================

TIMEOUT = 30
RETRY_INTERVAL_SECONDS = 20 * 60
MAX_ATTEMPTS = 4

DATA_FILE = Path("data.json")

COLOMBIA = ZoneInfo("America/Bogota")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(compatible; DevocionalesDiariosBot/3.0; "
        "+https://wiyata01.github.io/devocionales/)"
    ),
    "Cache-Control": "no-cache, no-store, max-age=0",
    "Pragma": "no-cache",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
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
# UTILIDADES
# ============================================================

def ahora_colombia():
    return dt.datetime.now(COLOMBIA)


def fecha_hoy_colombia():
    return ahora_colombia().date()


def fecha_espanol(fecha):
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


def clean(text):
    if not text:
        return ""

    text = text.replace("\xa0", " ")

    return re.sub(r"\s+", " ", text).strip()


def normalizar_url(url):
    if not url:
        return ""

    return url.replace("\\/", "/").strip()


def agregar_cache_buster(url):
    """
    Agrega un parámetro diferente a cada consulta para reducir
    la posibilidad de recibir una respuesta cacheada.
    """
    separador = "&" if "?" in url else "?"

    return (
        f"{url}{separador}"
        f"_devocionales_cache={int(time.time() * 1000)}"
    )


def get(url):
    url_sin_cache = agregar_cache_buster(url)

    respuesta = S.get(
        url_sin_cache,
        timeout=TIMEOUT,
        allow_redirects=True,
    )

    respuesta.raise_for_status()

    return respuesta


def soup_from_response(response):
    return BeautifulSoup(
        response.text,
        "html.parser",
    )


def soup(url):
    return soup_from_response(get(url))


def valid(item):
    return (
        isinstance(item, dict)
        and bool(clean(item.get("titulo")))
        and isinstance(item.get("parrafos"), list)
        and len(item.get("parrafos")) > 0
    )


def extraer_mp3(html):
    """
    Busca cualquier URL MP3 absoluta o escapada.
    """

    patrones = [
        r'https?://[^"\'>\s\\]+\.mp3(?:\?[^"\'>\s\\]*)?',
        r'https?:\\/\\/[^"\'>\s]+\.mp3(?:\?[^"\'>\s]*)?',
    ]

    for patron in patrones:
        encontrados = re.findall(
            patron,
            html,
            flags=re.I,
        )

        for url in encontrados:

            url = normalizar_url(url)

            # Evitar archivos que claramente no sean audio
            # del devocional.
            if ".mp3" in url.lower():
                return url

    return ""


def limpiar_titulo_bayless(titulo):
    """
    Ejemplos:

    #227 El Consolador
    -> El Consolador

    #231 Preocupación por el trabajo
    -> Preocupación por el trabajo
    """

    titulo = clean(titulo)

    titulo = re.sub(
        r"^\s*#\s*\d+\s*[-–—:]?\s*",
        "",
        titulo,
    )

    return clean(titulo)


def extraer_numero_bayless(url):
    """
    Extrae el número del episodio de URLs como:

    /devotional/227-el-consolador/
    /devotional/231-preocupacion-por-el-trabajo/
    """

    if not url:
        return None

    m = re.search(
        r"/devotional/\s*(?:#)?(\d+)(?:[-/])",
        url,
        flags=re.I,
    )

    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass

    return None


def parsear_fecha_espanol(texto):
    """
    Convierte fechas como:

    19 de agosto de 2026
    19 agosto 2026
    """

    if not texto:
        return None

    meses = {
        "enero": 1,
        "febrero": 2,
        "marzo": 3,
        "abril": 4,
        "mayo": 5,
        "junio": 6,
        "julio": 7,
        "agosto": 8,
        "septiembre": 9,
        "setiembre": 9,
        "octubre": 10,
        "noviembre": 11,
        "diciembre": 12,
    }

    patron = (
        r"(\d{1,2})\s+"
        r"(?:de\s+)?"
        r"(enero|febrero|marzo|abril|mayo|junio|"
        r"julio|agosto|septiembre|setiembre|octubre|"
        r"noviembre|diciembre)"
        r"\s+(?:de\s+)?(\d{4})"
    )

    m = re.search(
        patron,
        texto.lower(),
        flags=re.I,
    )

    if not m:
        return None

    try:
        dia = int(m.group(1))
        mes = meses[m.group(2).lower()]
        anio = int(m.group(3))

        return dt.date(
            anio,
            mes,
            dia,
        )

    except Exception:
        return None


# ============================================================
# EN CONTACTO
# ============================================================

ENCONTACTO_URL = (
    "https://www.encontactoglobal.org/"
    "lea/devocionales-diarios"
)


def encontrar_fecha_encontacto(s):
    """
    Busca la fecha principal del artículo.

    La página actual contiene una estructura como:

    # Título
    ## Subtítulo
    19 de agosto de 2026
    """

    # Primero buscar texto que parezca una fecha.
    textos = []

    for tag in s.find_all(
        ["time", "p", "div", "span", "article", "main"]
    ):
        texto = clean(tag.get_text(" ", strip=True))

        if texto:
            textos.append(texto)

    for texto in textos:
        fecha = parsear_fecha_espanol(texto)

        if fecha:
            return fecha

    # Buscar directamente en todo el HTML.
    return parsear_fecha_espanol(
        s.get_text(" ", strip=True)
    )


def encontrar_audio_encontacto(s, html):
    """
    Prioridad:
    1. <audio src="">
    2. source src
    3. data-src
    4. MP3 encontrado en HTML
    """

    # <audio src="">
    for audio in s.find_all("audio"):
        src = (
            audio.get("src")
            or audio.get("data-src")
            or ""
        )

        if src and ".mp3" in src.lower():
            return normalizar_url(
                urljoin(
                    ENCONTACTO_URL,
                    src,
                )
            )

        for source in audio.find_all("source"):
            src = (
                source.get("src")
                or source.get("data-src")
                or ""
            )

            if src and ".mp3" in src.lower():
                return normalizar_url(
                    urljoin(
                        ENCONTACTO_URL,
                        src,
                    )
                )

    # Cualquier MP3 del HTML
    audio = extraer_mp3(html)

    return audio


def encontrar_bloque_principal_encontacto(s):
    """
    Intenta localizar el cuerpo real del artículo.
    """

    # Prioridad a article/main.
    candidatos = []

    for selector in [
        "article",
        "main",
        '[role="main"]',
    ]:
        for tag in s.select(selector):
            texto = clean(
                tag.get_text(
                    " ",
                    strip=True,
                )
            )

            if len(texto) > 300:
                candidatos.append(tag)

    if candidatos:
        # El candidato con menos basura suele ser
        # el artículo más específico.
        candidatos.sort(
            key=lambda x: len(
                x.get_text(
                    " ",
                    strip=True,
                )
            )
        )

        return candidatos[0]

    return s


def scrape_encontacto():
    respuesta = get(ENCONTACTO_URL)

    s = soup_from_response(respuesta)
    html = respuesta.text

    hoy = fecha_hoy_colombia()

    # --------------------------------------------------------
    # FECHA
    # --------------------------------------------------------

    fecha_fuente = encontrar_fecha_encontacto(s)

    if fecha_fuente != hoy:

        raise RuntimeError(
            "En Contacto todavía no muestra el devocional "
            f"del {fecha_espanol(hoy)}. "
            f"Fecha encontrada: "
            f"{fecha_espanol(fecha_fuente) if fecha_fuente else 'ninguna'}"
        )

    # --------------------------------------------------------
    # TÍTULO
    # --------------------------------------------------------

    titulo = ""

    h1 = s.find("h1")

    if h1:
        titulo = clean(
            h1.get_text(
                " ",
                strip=True,
            )
        )

    # --------------------------------------------------------
    # SUBTÍTULO
    # --------------------------------------------------------

    subtitulo = ""

    h2 = s.find("h2")

    if h2:
        subtitulo = clean(
            h2.get_text(
                " ",
                strip=True,
            )
        )

    # --------------------------------------------------------
    # CUERPO
    # --------------------------------------------------------

    cuerpo = encontrar_bloque_principal_encontacto(s)

    parrafos = []

    # Buscar párrafos reales.
    for p in cuerpo.find_all("p"):

        texto = clean(
            p.get_text(
                " ",
                strip=True,
            )
        )

        if not texto:
            continue

        low = texto.lower()

        # Basura habitual del sitio.
        if any(
            palabra in low
            for palabra in [
                "biblia en un año",
                "suscríbase",
                "suscribirse",
                "correo electrónico",
                "recibir devocionales",
                "todos los derechos reservados",
            ]
        ):
            continue

        if len(texto) < 25:
            continue

        parrafos.append(texto)

    # Si no hubo <p>, buscar bloques de texto.
    if not parrafos:

        for tag in cuerpo.find_all(
            ["div", "section"]
        ):

            texto = clean(
                tag.get_text(
                    " ",
                    strip=True,
                )
            )

            if len(texto) >= 80:
                parrafos.append(texto)

    # Eliminar duplicados conservando orden.
    parrafos_finales = []

    vistos = set()

    for p in parrafos:

        clave = p.lower()

        if clave in vistos:
            continue

        vistos.add(clave)

        parrafos_finales.append(p)

    parrafos = parrafos_finales

    # --------------------------------------------------------
    # VERSÍCULO
    # --------------------------------------------------------

    versiculo = ""

    enlace_biblia = s.find(
        "a",
        href=re.compile(
            r"biblegateway\.com",
            re.I,
        ),
    )

    if enlace_biblia:
        versiculo = clean(
            enlace_biblia.get_text(
                " ",
                strip=True,
            )
        )

    # --------------------------------------------------------
    # AUDIO
    # --------------------------------------------------------

    audio = encontrar_audio_encontacto(
        s,
        html,
    )

    if not titulo or not parrafos:
        raise RuntimeError(
            "En Contacto respondió, pero no se pudo "
            "extraer correctamente título y texto."
        )

    return {
        "titulo": titulo,
        "subtitulo": subtitulo,
        "versiculo": versiculo,
        "parrafos": parrafos[:20],
        "audio_url": audio,
        "audio_tipo": "mp3",
        "link": ENCONTACTO_URL,
        "fecha_fuente": hoy.isoformat(),
    }


# ============================================================
# BAYLESS CONLEY
# ============================================================

BAYLESS_LANDING = (
    "https://www.respuestasbc.com/"
    "?redirect_to=latest&post_type=devotional"
)


def buscar_ultimo_enlace_bayless(s):
    """
    Busca enlaces del tipo:

    /devotional/231-titulo/

    y selecciona el número de episodio más alto.
    """

    encontrados = {}

    for a in s.find_all(
        "a",
        href=True,
    ):

        href = a.get("href", "").strip()

        numero = extraer_numero_bayless(
            href
        )

        if numero is None:
            continue

        href_abs = urljoin(
            BAYLESS_LANDING,
            href,
        )

        # Mantener el mayor número encontrado.
        if (
            numero not in encontrados
            or len(href_abs)
            > len(encontrados[numero])
        ):
            encontrados[numero] = href_abs

    if not encontrados:
        return "", None

    numero_max = max(
        encontrados.keys()
    )

    return (
        encontrados[numero_max],
        numero_max,
    )


def extraer_titulo_bayless(s):
    """
    Extrae el título del artículo actual.
    """

    candidatos = []

    for tag in s.find_all(
        ["h1", "h2", "h3"]
    ):

        texto = clean(
            tag.get_text(
                " ",
                strip=True,
            )
        )

        if not texto:
            continue

        titulo = limpiar_titulo_bayless(
            texto
        )

        low = titulo.lower()

        if low in {
            "devocional diario",
            "respuestas para cada día",
            "bayless conley",
        }:
            continue

        if len(titulo) >= 3:
            candidatos.append(titulo)

    if candidatos:
        # Preferir el título que contiene número
        # en el original.
        for candidato in candidatos:
            if candidato:
                return candidato

    # OpenGraph
    og = s.find(
        "meta",
        attrs={
            "property": "og:title"
        },
    )

    if og:
        return limpiar_titulo_bayless(
            og.get("content", "")
        )

    title = s.find("title")

    if title:
        return limpiar_titulo_bayless(
            title.get_text()
        )

    return ""


def extraer_texto_bayless(s):
    """
    Extrae exclusivamente párrafos del artículo.

    Se evita utilizar todo el documento porque la página
    contiene navegación, suscripciones y otros devocionales.
    """

    candidatos = []

    # Primero buscar article.
    for article in s.find_all(
        "article"
    ):

        cantidad = len(
            article.find_all("p")
        )

        if cantidad >= 2:
            candidatos.append(article)

    # Después contenedores habituales.
    if not candidatos:

        for selector in [
            ".entry-content",
            ".post-content",
            ".single-content",
            ".elementor-widget-theme-post-content",
            "main",
        ]:

            for tag in s.select(
                selector
            ):

                if len(
                    tag.find_all("p")
                ) >= 2:

                    candidatos.append(tag)

    if not candidatos:
        candidatos = [s]

    # Elegir el contenedor que tenga más
    # párrafos, pero no simplemente todo el HTML.
    candidatos.sort(
        key=lambda x: len(
            x.find_all("p")
        ),
        reverse=True,
    )

    cuerpo = candidatos[0]

    parrafos = []

    for p in cuerpo.find_all("p"):

        texto = clean(
            p.get_text(
                " ",
                strip=True,
            )
        )

        if not texto:
            continue

        low = texto.lower()

        # Eliminar elementos que no forman parte
        # del artículo.
        if any(
            palabra in low
            for palabra in [
                "there was an error submitting",
                "me gustaría recibir",
                "recibir los correos",
                "suscrib",
                "copyright",
                "todos los derechos reservados",
                "bayless conley",
                "la siguiente “c”",
                "la siguiente 'c'",
            ]
        ):
            continue

        if len(texto) < 20:
            continue

        parrafos.append(texto)

    # Eliminar duplicados.
    resultado = []
    vistos = set()

    for texto in parrafos:

        clave = texto.lower()

        if clave in vistos:
            continue

        vistos.add(clave)
        resultado.append(texto)

    return resultado


def extraer_audio_bayless(s):
    """
    Obtiene el enlace del episodio de SoundCloud,
    si está presente.
    """

    # Primero enlaces explícitos.
    for a in s.find_all(
        "a",
        href=True,
    ):

        href = a.get(
            "href",
            "",
        ).strip()

        if (
            "soundcloud.com/respuestasbc/"
            in href.lower()
            and "/sets/" not in href.lower()
        ):
            return href

    # Después HTML completo.
    html = str(s)

    m = re.search(
        r"https?://(?:www\.)?soundcloud\.com/"
        r"respuestasbc/"
        r"[A-Za-z0-9_-]+",
        html,
        flags=re.I,
    )

    if m:
        return m.group(0)

    return ""


def scrape_bayless():
    """
    Obtiene el episodio de Bayless con el número más alto
    encontrado en la página de últimos devocionales.
    """

    landing_response = get(
        BAYLESS_LANDING
    )

    landing_soup = soup_from_response(
        landing_response
    )

    articulo_url, numero = (
        buscar_ultimo_enlace_bayless(
            landing_soup
        )
    )

    if not articulo_url:
        raise RuntimeError(
            "No se encontró ningún episodio "
            "de Bayless en la página de últimos devocionales."
        )

    # Consultar el artículo concreto.
    articulo_response = get(
        articulo_url
    )

    s = soup_from_response(
        articulo_response
    )

    titulo = extraer_titulo_bayless(
        s
    )

    titulo = limpiar_titulo_bayless(
        titulo
    )

    parrafos = extraer_texto_bayless(
        s
    )

    audio = extraer_audio_bayless(
        s
    )

    if not titulo or not parrafos:
        raise RuntimeError(
            "No se pudo extraer correctamente "
            "el título o texto del episodio Bayless."
        )

    return {
        "titulo": titulo,
        "subtitulo": "",
        "versiculo": "",
        "parrafos": parrafos[:30],
        "audio_url": audio,
        "audio_tipo": "soundcloud",
        "link": articulo_url,
        "numero_episodio": numero,
    }


# ============================================================
# KENNETH COPELAND
# ============================================================

KENNETH_URL = (
    "https://main.kcmlatino.org/devotional"
)


def encontrar_fecha_kenneth(s):
    """
    Busca fechas visibles en la página.
    """

    texto = s.get_text(
        " ",
        strip=True,
    )

    return parsear_fecha_espanol(
        texto
    )


def scrape_kenneth():
    """
    Kenneth ya estaba funcionando correctamente.
    Se conserva la lógica de extracción directa,
    pero con mejor limpieza y sin depender de
    títulos específicos.
    """

    response = get(
        KENNETH_URL
    )

    s = soup_from_response(
        response
    )

    html = response.text

    titulo = ""

    h1 = s.find("h1")

    if h1:
        titulo = clean(
            h1.get_text(
                " ",
                strip=True,
            )
        )

    if not titulo:

        og = s.find(
            "meta",
            attrs={
                "property": "og:title"
            },
        )

        if og:
            titulo = clean(
                og.get(
                    "content",
                    "",
                )
            )

    # --------------------------------------------------------
    # TEXTO
    # --------------------------------------------------------

    candidatos = []

    for article in s.find_all(
        "article"
    ):

        if len(
            article.find_all("p")
        ) >= 2:

            candidatos.append(article)

    if not candidatos:

        candidatos = [s]

    candidatos.sort(
        key=lambda x: len(
            x.find_all("p")
        ),
        reverse=True,
    )

    cuerpo = candidatos[0]

    parrafos = []

    for p in cuerpo.find_all(
        "p"
    ):

        texto = clean(
            p.get_text(
                " ",
                strip=True,
            )
        )

        if not texto:
            continue

        low = texto.lower()

        if any(
            palabra in low
            for palabra in [
                "copyright",
                "todos los derechos reservados",
                "contenido relacionado",
                "loading",
                "devocional type",
            ]
        ):
            continue

        if len(texto) < 20:
            continue

        parrafos.append(texto)

    # Eliminar duplicados.
    resultado = []
    vistos = set()

    for texto in parrafos:

        clave = texto.lower()

        if clave in vistos:
            continue

        vistos.add(clave)
        resultado.append(texto)

    parrafos = resultado

    # --------------------------------------------------------
    # VERSÍCULO
    # --------------------------------------------------------

    versiculo = ""

    for texto in parrafos[:5]:

        low = texto.lower()

        if (
            "«" in texto
            or "(hebreos" in low
            or "(romanos" in low
            or "(salmos" in low
            or "(juan" in low
            or "(proverbios" in low
        ):
            versiculo = texto
            break

    # --------------------------------------------------------
    # AUDIO
    # --------------------------------------------------------

    audio = ""

    # Buscar <audio>
    for tag in s.find_all(
        "audio"
    ):

        src = (
            tag.get("src")
            or tag.get("data-src")
            or ""
        )

        if ".mp3" in src.lower():

            audio = normalizar_url(
                urljoin(
                    KENNETH_URL,
                    src,
                )
            )

            break

        for source in tag.find_all(
            "source"
        ):

            src = (
                source.get("src")
                or source.get("data-src")
                or ""
            )

            if ".mp3" in src.lower():

                audio = normalizar_url(
                    urljoin(
                        KENNETH_URL,
                        src,
                    )
                )

                break

        if audio:
            break

    if not audio:
        audio = extraer_mp3(
            html
        )

    # --------------------------------------------------------
    # VALIDACIÓN
    # --------------------------------------------------------

    if not titulo or not parrafos:
        raise RuntimeError(
            "No se pudo extraer correctamente "
            "el título o texto de Kenneth Copeland."
        )

    return {
        "titulo": titulo,
        "subtitulo": "",
        "versiculo": versiculo,
        "parrafos": parrafos[:30],
        "audio_url": audio,
        "audio_tipo": "mp3",
        "link": response.url,
    }


# ============================================================
# DATA.JSON
# ============================================================

def cargar_anterior():

    if not DATA_FILE.exists():
        return {}

    try:

        with DATA_FILE.open(
            "r",
            encoding="utf-8",
        ) as f:

            data = json.load(f)

        if isinstance(
            data,
            dict,
        ):
            return data

    except Exception as exc:

        print(
            "Aviso: no se pudo leer data.json anterior:",
            exc,
            file=sys.stderr,
        )

    return {}


def guardar_data(data):

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


# ============================================================
# VALIDACIÓN ESPECÍFICA DE CADA FUENTE
# ============================================================

def fuente_actualizada(
    clave,
    nuevo,
    hoy,
):
    """
    Determina si realmente podemos considerar que la fuente
    está actualizada.

    En Contacto:
        exige fecha exacta.

    Bayless:
        exige que exista un episodio válido.
        No depende de una fecha publicada por WordPress,
        porque el sitio identifica sus devocionales por número.

    Kenneth:
        se acepta el contenido actual obtenido de la página,
        porque su página /devotional apunta al devocional vigente.
    """

    if not valid(nuevo):
        return False

    # --------------------------------------------------------
    # EN CONTACTO
    # --------------------------------------------------------

    if clave == "encontacto":

        fecha = nuevo.get(
            "fecha_fuente"
        )

        return fecha == hoy.isoformat()

    # --------------------------------------------------------
    # BAYLESS
    # --------------------------------------------------------

    if clave == "bayless":

        numero = nuevo.get(
            "numero_episodio"
        )

        return (
            isinstance(
                numero,
                int,
            )
            and numero > 0
            and len(
                nuevo.get(
                    "parrafos",
                    [],
                )
            ) > 0
        )

    # --------------------------------------------------------
    # KENNETH
    # --------------------------------------------------------

    if clave == "kenneth":

        return (
            bool(
                nuevo.get("titulo")
            )
            and len(
                nuevo.get(
                    "parrafos",
                    [],
                )
            ) > 0
        )

    return False


# ============================================================
# EJECUCIÓN DE UNA FUENTE
# ============================================================

FUENTES = {
    "encontacto": scrape_encontacto,
    "bayless": scrape_bayless,
    "kenneth": scrape_kenneth,
}


def intentar_fuente(
    clave,
    anterior,
    data,
    hoy,
):
    """
    Intenta actualizar una sola fuente.

    Devuelve True solamente cuando el nuevo contenido
    pasa las validaciones.
    """

    funcion = FUENTES[clave]

    try:

        nuevo = funcion()

        if not fuente_actualizada(
            clave,
            nuevo,
            hoy,
        ):

            print(
                f"{clave}: respondió, pero "
                "el contenido todavía no se considera "
                "actualizado."
            )

            return False

        data[clave] = nuevo

        print(
            f"{clave}: ACTUALIZADO ✓ "
            f"→ {nuevo.get('titulo', '')}"
        )

        if clave == "bayless":

            print(
                f"    Episodio Bayless: "
                f"#{nuevo.get('numero_episodio')}"
            )

        if nuevo.get(
            "audio_url"
        ):

            print(
                "    Audio: encontrado ✓"
            )

        else:

            print(
                "    Audio: todavía no encontrado"
            )

        return True

    except Exception as exc:

        print(
            f"{clave}: todavía no disponible → {exc}"
        )

        return False


# ============================================================
# MAIN
# ============================================================

def main():

    hoy = fecha_hoy_colombia()

    print("=" * 70)

    print(
        "ACTUALIZADOR DE DEVOCIONALES"
    )

    print(
        f"Fecha Colombia: "
        f"{fecha_espanol(hoy)}"
    )

    print(
        f"Hora Colombia: "
        f"{ahora_colombia().strftime('%H:%M:%S')}"
    )

    print("=" * 70)

    old = cargar_anterior()

    data = dict(old)

    data["fecha"] = fecha_espanol(
        hoy
    )

    actualizados = set()

    intento = 0

    # ========================================================
    # BUCLE PRINCIPAL
    # ========================================================

    while len(actualizados) < len(FUENTES) and intento < MAX_ATTEMPTS:

        intento += 1

        print()
        print(
            "=" * 70
        )

        print(
            f"INTENTO #{intento}"
        )

        print(
            f"Hora Colombia: "
            f"{ahora_colombia().strftime('%H:%M:%S')}"
        )

        print(
            "Fuentes actualizadas: "
            f"{len(actualizados)}/3"
        )

        print(
            "=" * 70
        )

        # ----------------------------------------------------
        # SOLO CONSULTAR LAS PENDIENTES
        # ----------------------------------------------------

        for clave in FUENTES:

            if clave in actualizados:
                continue

            print()
            print(
                f"Consultando {clave}..."
            )

            ok = intentar_fuente(
                clave,
                old.get(clave),
                data,
                hoy,
            )

            if ok:

                actualizados.add(
                    clave
                )

                # Guardar inmediatamente.
                data["generado"] = (
                    dt.datetime.now(
                        dt.timezone.utc
                    )
                    .isoformat()
                    .replace(
                        "+00:00",
                        "Z",
                    )
                )

                guardar_data(
                    data
                )

                print(
                    f"{clave}: guardado en data.json ✓"
                )

        # ----------------------------------------------------
        # COMPROBAR SI TERMINAMOS
        # ----------------------------------------------------

        if len(actualizados) == 3:

            print()
            print(
                "=" * 70
            )

            print(
                "✓ LAS 3 FUENTES ESTÁN ACTUALIZADAS"
            )

            print(
                f"Fecha: {fecha_espanol(hoy)}"
            )

            print(
                "Proceso terminado correctamente."
            )

            print(
                "=" * 70
            )

            break

        # ----------------------------------------------------
        # ESPERAR 20 MINUTOS
        # ----------------------------------------------------

        pendientes = [
            clave
            for clave in FUENTES
            if clave not in actualizados
        ]

        print()
        print(
            "Todavía pendientes:"
        )

        for clave in pendientes:
            print(
                f"  - {clave}"
            )

        print()
        if intento < MAX_ATTEMPTS:
            print(
                "Se volverá a intentar en "
                "20 minutos."
            )
            time.sleep(RETRY_INTERVAL_SECONDS)

    if len(actualizados) < len(FUENTES):
        pendientes = [
            clave
            for clave in FUENTES
            if clave not in actualizados
        ]
        mensaje = (
            f"No se actualizaron todas las fuentes después de "
            f"{MAX_ATTEMPTS} intentos. Pendientes: "
            + ", ".join(pendientes)
        )
        print()
        print(f"ERROR: {mensaje}", file=sys.stderr)
        raise RuntimeError(mensaje)


# ============================================================
# EJECUTAR
# ============================================================

if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:

        print(
            "\nProceso cancelado manualmente."
        )

        sys.exit(1)

    except Exception as exc:

        print(
            "\nERROR FATAL:",
            exc,
            file=sys.stderr,
        )

        sys.exit(1)