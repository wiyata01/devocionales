#!/usr/bin/env python3
"""
Actualiza los tres devocionales diarios.

- En Contacto:
  Busca específicamente la Meditación diaria del día actual.
  No acepta contenido de una fecha anterior.
  Conserva el último dato válido si la fuente todavía no publicó el día.

- Bayless Conley:
  Busca el devocional actual y evita arrastrar devocionales anteriores,
  suscripciones y contenido del pie de página.

- Kenneth Copeland:
  Conserva la lógica de extracción del MP3 y del contenido.

Si una fuente falla, se conserva el último contenido válido.
"""

import datetime as dt
import json
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


# ============================================================
# CONFIGURACIÓN
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; DevocionalesDiariosBot/3.0; "
        "+https://wiyata01.github.io/devocionales/)"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.7",
}

TIMEOUT = 30

DATA_FILE = Path("data.json")


# ============================================================
# SESIÓN HTTP
# ============================================================

def session():
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

    s.mount(
        "https://",
        HTTPAdapter(max_retries=retry)
    )

    s.headers.update(HEADERS)

    return s


S = session()


# ============================================================
# UTILIDADES
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


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def get(url):
    r = S.get(
        url,
        timeout=TIMEOUT,
        allow_redirects=True,
        cache_bust=True if False else None,
    )

    r.raise_for_status()

    return r


def soup_from_response(response):
    return BeautifulSoup(
        response.text,
        "html.parser"
    )


def first_nonempty(values):
    for value in values:
        value = clean(value)

        if value:
            return value

    return ""


def valid(item):
    return (
        isinstance(item, dict)
        and bool(item.get("titulo"))
        and isinstance(item.get("parrafos"), list)
        and any(
            clean(str(p))
            for p in item.get("parrafos", [])
        )
    )


def extract_mp3(html, patterns):
    for pattern in patterns:

        m = re.search(
            pattern,
            html,
            flags=re.I
        )

        if m:
            return (
                m.group(1)
                .replace("\\/", "/")
            )

    return ""


def fecha_hoy_colombia():
    """
    Obtiene la fecha actual usando la hora de Colombia.
    America/Bogota es UTC-5 durante todo el año.
    """

    now_utc = dt.datetime.now(
        dt.timezone.utc
    )

    colombia = now_utc - dt.timedelta(
        hours=5
    )

    return colombia.date()


def fecha_espanol(fecha):
    return (
        f"{fecha.day} de "
        f"{MESES[fecha.month - 1]} de "
        f"{fecha.year}"
    )


def normalizar_fecha(texto):
    """
    Convierte una fecha encontrada en una página a date.

    Acepta:
        28 de agosto de 2026
        28 agosto 2026
        28/08/2026
        28-08-2026
    """

    texto = clean(texto).lower()

    patron = re.search(
        r"\b(\d{1,2})\s+de\s+"
        r"(enero|febrero|marzo|abril|mayo|junio|"
        r"julio|agosto|septiembre|octubre|noviembre|diciembre)"
        r"\s+de\s+(\d{4})\b",
        texto,
        flags=re.I,
    )

    if patron:

        dia = int(patron.group(1))
        mes_nombre = patron.group(2).lower()
        anio = int(patron.group(3))

        try:
            mes = MESES.index(mes_nombre) + 1

            return dt.date(
                anio,
                mes,
                dia
            )

        except ValueError:
            return None

    patron = re.search(
        r"\b(\d{1,2})[/-]"
        r"(\d{1,2})[/-]"
        r"(\d{4})\b",
        texto
    )

    if patron:

        try:
            return dt.date(
                int(patron.group(3)),
                int(patron.group(2)),
                int(patron.group(1)),
            )

        except ValueError:
            return None

    return None


# ============================================================
# EN CONTACTO
# ============================================================

def scrape_encontacto():

    url = (
        "https://www.encontactoglobal.org/"
        "lea/devocionales-diarios"
    )

    r = get(url)

    s = soup_from_response(r)

    html = str(s)

    hoy = fecha_hoy_colombia()

    fecha_esperada = fecha_espanol(hoy)

    # --------------------------------------------------------
    # BUSCAR EL ARTÍCULO ACTUAL
    # --------------------------------------------------------

    h1 = None

    for candidato in s.find_all("h1"):

        texto = clean(
            candidato.get_text(
                " ",
                strip=True
            )
        )

        if texto:
            h1 = candidato
            break

    if not h1:

        raise RuntimeError(
            "En Contacto: no se encontró el título h1"
        )

    titulo = clean(
        h1.get_text(
            " ",
            strip=True
        )
    )

    if not titulo:

        raise RuntimeError(
            "En Contacto: título vacío"
        )

    # --------------------------------------------------------
    # BUSCAR EL CONTENEDOR DEL ARTÍCULO
    # --------------------------------------------------------

    articulo = None

    actual = h1

    # Subimos varios niveles buscando article/main/section
    for _ in range(8):

        actual = actual.parent

        if actual is None:
            break

        if getattr(actual, "name", None) in (
            "article",
            "main",
            "section",
        ):

            texto_contenedor = clean(
                actual.get_text(
                    " ",
                    strip=True
                )
            )

            if (
                fecha_esperada.lower()
                in texto_contenedor.lower()
            ):

                articulo = actual

                break

    # Si no encontramos contenedor adecuado,
    # usamos el padre inmediato del H1 como respaldo.
    if articulo is None:

        articulo = h1.parent

    if articulo is None:

        raise RuntimeError(
            "En Contacto: no se encontró el bloque del artículo"
        )

    # --------------------------------------------------------
    # BUSCAR FECHA
    # --------------------------------------------------------

    fecha_encontrada = None

    # Primero buscamos cerca del título.
    for tag in articulo.find_all(
        ["time", "p", "div", "span"],
        limit=80
    ):

        texto = clean(
            tag.get_text(
                " ",
                strip=True
            )
        )

        fecha = normalizar_fecha(texto)

        if fecha:

            fecha_encontrada = fecha

            break

    # También buscamos directamente en todo el documento
    # si el contenedor no tenía la fecha.
    if fecha_encontrada is None:

        for tag in s.find_all(
            ["time", "p", "div", "span"]
        ):

            texto = clean(
                tag.get_text(
                    " ",
                    strip=True
                )
            )

            if fecha_esperada.lower() in texto.lower():

                fecha = normalizar_fecha(texto)

                if fecha:

                    fecha_encontrada = fecha

                    break

    # --------------------------------------------------------
    # VALIDACIÓN CRÍTICA DE FECHA
    # --------------------------------------------------------

    if fecha_encontrada != hoy:

        encontrada = (
            fecha_espanol(fecha_encontrada)
            if fecha_encontrada
            else "ninguna"
        )

        raise RuntimeError(
            "En Contacto todavía no tiene el devocional "
            f"de hoy ({fecha_esperada}). "
            f"Se encontró: {encontrada}"
        )

    # --------------------------------------------------------
    # SUBTÍTULO
    # --------------------------------------------------------

    subtitle = ""

    h2 = h1.find_next("h2")

    if h2:

        subtitle = clean(
            h2.get_text(
                " ",
                strip=True
            )
        )

    # --------------------------------------------------------
    # VERSÍCULO
    # --------------------------------------------------------

    verse = ""

    for a in articulo.find_all(
        "a",
        href=True
    ):

        href = a.get("href", "")

        if "biblegateway.com" in href.lower():

            verse = clean(
                a.get_text(
                    " ",
                    strip=True
                )
            )

            if verse:
                break

    # --------------------------------------------------------
    # TEXTO DEL DEVOCIONAL
    # --------------------------------------------------------

    paragraphs = []

    # Primero encontramos el H1 dentro del artículo.
    # Todo lo que aparece después será examinado.
    encontrado_h1 = False

    for tag in articulo.find_all(
        ["h1", "h2", "h3", "p", "li"]
    ):

        if tag is h1:

            encontrado_h1 = True

            continue

        if not encontrado_h1:
            continue

        # ----------------------------------------------------
        # DETENER ANTES DEL CONTENIDO POSTERIOR
        # ----------------------------------------------------

        if tag.name in ("h2", "h3"):

            encabezado = clean(
                tag.get_text(
                    " ",
                    strip=True
                )
            ).lower()

            if encabezado in (
                "opciones de lectura",
                "otros devocionales",
                "otros devocionles",
                "biblia en un año",
            ):

                break

        text = clean(
            tag.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        low = text.lower()

        # ----------------------------------------------------
        # CONTENIDO QUE NO FORMA PARTE DEL DEVOCIONAL
        # ----------------------------------------------------

        if low in (
            "meditación diaria",
            "opciones de lectura",
            "sociales",
            "donar",
            "leer",
        ):
            continue

        if "biblia en un año" in low:
            break

        if "otros devocional" in low:
            break

        if low.startswith(
            "todas las meditaciones diarias"
        ):
            break

        if any(
            palabra in low
            for palabra in (
                "suscríbase",
                "suscribirse",
                "correo electrónico",
            )
        ):
            continue

        # Los textos demasiado pequeños suelen ser
        # controles, botones o navegación.
        if len(text) < 25:
            continue

        # No guardar la fecha como párrafo.
        if normalizar_fecha(text) == hoy:
            continue

        # No guardar el versículo como párrafo.
        if text == verse:
            continue

        paragraphs.append(text)

    # --------------------------------------------------------
    # LIMPIEZA FINAL
    # --------------------------------------------------------

    # Elimina duplicados consecutivos.
    limpios = []

    for p in paragraphs:

        if not limpios or p != limpios[-1]:

            limpios.append(p)

    paragraphs = limpios

    # En el devocional actual esperamos varios bloques.
    if len(paragraphs) < 2:

        raise RuntimeError(
            "En Contacto: se encontró la fecha correcta "
            "pero no se pudo extraer suficiente texto"
        )

    # --------------------------------------------------------
    # AUDIO
    # --------------------------------------------------------

    audio = extract_mp3(
        html,
        [
            r"(https://intouch\.azureedge\.net/"
            r"spanish/devo/[A-Za-z0-9_./-]+\.mp3)",
        ],
    )

    # --------------------------------------------------------
    # RESULTADO
    # --------------------------------------------------------

    return {
        "titulo": titulo,
        "subtitulo": subtitle,
        "versiculo": verse,
        "parrafos": paragraphs[:20],
        "audio_url": audio,
        "audio_tipo": "mp3",
        "link": r.url,
        "fecha_fuente": fecha_esperada,
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

    s = soup_from_response(r)

    html = str(s)

    # --------------------------------------------------------
    # TÍTULO
    # --------------------------------------------------------

    title = ""

    candidatos = []

    ignorados = {
        "devocional diario",
        "respuestas para cada día",
        "bayless conley",
    }

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

        if texto.lower() in ignorados:
            continue

        candidatos.append(texto)

    for candidato in candidatos:

        if re.search(
            r"(#\s*\d+\s+)?"
            r"[A-Za-zÁÉÍÓÚáéíóúÑñÜü]",
            candidato
        ):

            title = candidato

            break

    if not title:

        og = s.find(
            "meta",
            attrs={
                "property": "og:title"
            }
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

    # Quitar número de episodio.
    title = re.sub(
        r"^\s*#\s*\d+\s*[-–—:]?\s*",
        "",
        title
    ).strip()

    if title.lower() in ignorados:

        title = ""

    # --------------------------------------------------------
    # TEXTO
    # --------------------------------------------------------

    paragraphs = []

    # Palabras que indican que ya terminó el artículo.
    palabras_fin = (
        "la siguiente “c”",
        "la siguiente \"c\"",
        "el devocional anterior",
        "recibir los correos gratis",
        "me gustaría recibir",
        "there was an error submitting",
        "copyright",
        "© 2026",
        "todos los derechos reservados",
    )

    for p in s.find_all("p"):

        text = clean(
            p.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        low = text.lower()

        # Detenernos cuando aparece contenido posterior.
        if any(
            x in low
            for x in palabras_fin
        ):

            break

        if any(
            x in low
            for x in (
                "suscrib",
                "recibir devocionales",
                "escuche este devocional",
                "share",
                "compartir",
            )
        ):

            continue

        if len(text) < 20:
            continue

        paragraphs.append(text)

    # Evitar duplicados consecutivos.
    limpios = []

    for p in paragraphs:

        if not limpios or p != limpios[-1]:

            limpios.append(p)

    paragraphs = limpios

    # --------------------------------------------------------
    # AUDIO SOUNDCLOUD
    # --------------------------------------------------------

    audio = ""

    # Primero enlace directo al episodio.
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

    # Segundo intento: URL en HTML.
    if not audio:

        m = re.search(
            r"https?://(?:www\.)?soundcloud\.com/"
            r"respuestasbc/[A-Za-z0-9_-]+",
            html,
            flags=re.I,
        )

        if m:

            audio = m.group(0)

    # --------------------------------------------------------
    # VALIDACIÓN
    # --------------------------------------------------------

    if not title or not paragraphs:

        raise RuntimeError(
            "No se pudo extraer título o texto "
            "de Bayless Conley"
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


# ============================================================
# KENNETH COPELAND
# ============================================================

def scrape_kenneth():

    url = (
        "https://main.kcmlatino.org/devocional"
    )

    r = get(url)

    return _scrape_kcm_page(
        r.url,
        r.text
    )


def _scrape_kcm_page(
    url,
    html
):

    s = BeautifulSoup(
        html,
        "html.parser"
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
                strip=True
            )
        )

    if not title:

        og = s.find(
            "meta",
            attrs={
                "property": "og:title"
            }
        )

        if og:

            title = clean(
                og.get("content", "")
            )

    # --------------------------------------------------------
    # PÁRRAFOS
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # VERSÍCULO
    # --------------------------------------------------------

    verse = ""

    for text in paragraphs[:4]:

        if (
            "«" in text
            or "(hebreos" in text.lower()
        ):

            verse = text

            break

    # --------------------------------------------------------
    # AUDIO
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

    # Algunos templates escapan las barras.
    if not audio:

        m = re.search(
            r"(https?:\\?/\\?/"
            r"maincms\.nyc3\.digitaloceanspaces\.com"
            r"\\?/[A-Za-z0-9_./-]+\.mp3)",
            html,
            flags=re.I,
        )

        if m:

            audio = (
                m.group(1)
                .replace("\\/", "/")
            )

    # --------------------------------------------------------
    # VALIDACIÓN
    # --------------------------------------------------------

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


# ============================================================
# DATA ANTERIOR
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

        return (
            data
            if isinstance(data, dict)
            else {}
        )

    except Exception as exc:

        print(
            "Aviso: no se pudo leer data.json "
            f"anterior: {exc}",
            file=sys.stderr,
        )

        return {}


# ============================================================
# MAIN
# ============================================================

def main():

    # Fecha REAL de Colombia.
    today = fecha_hoy_colombia()

    fecha_es = fecha_espanol(today)

    old = load_previous()

    data = dict(old)

    data["fecha"] = fecha_es

    data["generado"] = (
        dt.datetime.now(
            dt.timezone.utc
        )
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

    # --------------------------------------------------------
    # ACTUALIZAR CADA FUENTE
    # --------------------------------------------------------

    for clave, fn in fuentes.items():

        try:

            print(
                f"\nConsultando {clave}..."
            )

            nuevo = fn()

            if not valid(nuevo):

                raise RuntimeError(
                    "La fuente respondió, pero faltan "
                    "título o texto válido"
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
                file=sys.stderr,
            )

            # IMPORTANTE:
            # si la fuente no está lista,
            # conservamos el contenido anterior.
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
    # SEGURIDAD
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
            "y no existe contenido anterior válido"
        )

    # --------------------------------------------------------
    # GUARDAR
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # INFORME
    # --------------------------------------------------------

    if errores:

        print(
            "\nFuentes con problemas:",
            file=sys.stderr
        )

        for error in errores:

            print(
                f" - {error}",
                file=sys.stderr
            )

    print(
        f"\nActualización terminada: "
        f"{exitos}/3 fuentes actualizadas."
    )

    print(
        f"Fecha Colombia: {fecha_es}"
    )

    # Mostrar el resultado final de cada fuente.
    print("\nEstado final de data.json:")

    for clave in fuentes:

        item = data.get(clave)

        if valid(item):

            print(
                f"  {clave}: {item['titulo']}"
            )

        else:

            print(
                f"  {clave}: SIN DATOS VÁLIDOS"
            )


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":
    main()
