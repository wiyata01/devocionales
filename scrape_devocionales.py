#!/usr/bin/env python3

"""
Actualiza los tres devocionales diarios.

Lógica:

1. Consulta En Contacto, Bayless Conley y Kenneth Copeland.
2. Comprueba que cada fuente tenga contenido válido.
3. Evita considerar automáticamente como "nuevo" cualquier contenido
   simplemente porque la página respondió correctamente.
4. Si todavía falta alguna fuente, vuelve a intentar cada 20 minutos.
5. Cuando las tres fuentes tienen contenido válido del día, guarda data.json.
6. Si una fuente falla, conserva su último contenido válido.
"""

import datetime as dt
import json
import re
import sys
import time
from pathlib import Path

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

# Para evitar que GitHub Actions quede ejecutándose indefinidamente.
# Se harán hasta 9 intentos:
#
# 02:10
# 02:30
# 02:50
# 03:10
# 03:30
# 03:50
# 04:10
# 04:30
# 04:50
#
# Si antes de eso aparecen los 3, termina inmediatamente.
MAX_INTENTOS = 9


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(compatible; DevocionalesDiariosBot/3.0; "
        "+https://wiyata01.github.io/devocionales/)"
    )
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
        status_forcelist=(
            429,
            500,
            502,
            503,
            504,
        ),
        allowed_methods=frozenset(["GET"]),
    )

    s.mount(
        "https://",
        HTTPAdapter(max_retries=retry)
    )

    s.headers.update(HEADERS)

    return s


S = crear_sesion()


# ============================================================
# FUNCIONES GENERALES
# ============================================================

def clean(text):

    return re.sub(
        r"\s+",
        " ",
        text or ""
    ).strip()


def get(url):

    response = S.get(
        url,
        timeout=TIMEOUT,
        allow_redirects=True
    )

    response.raise_for_status()

    return response


def extract_mp3(html, patterns):

    for pattern in patterns:

        match = re.search(
            pattern,
            html,
            flags=re.I
        )

        if match:

            return match.group(1).replace(
                "\\/",
                "/"
            )

    return ""


def valid(item):

    return (
        isinstance(item, dict)
        and bool(item.get("titulo"))
        and bool(item.get("parrafos"))
    )


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
            f"Aviso: no se pudo leer data.json anterior: {exc}",
            file=sys.stderr
        )

    return {}


# ============================================================
# EN CONTACTO
# ============================================================


    # --------------------------------------------------------
    # TEXTO
    # --------------------------------------------------------

    
# ============================================================
# EN CONTACTO
# ============================================================

def scrape_encontacto():

    url = (
        "https://www.encontactoglobal.org/"
        "lea/devocionales-diarios"
    )

    response = get(url)

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    html = str(soup)

    # --------------------------------------------------------
    # TÍTULO DEL DEVOCIONAL
    # --------------------------------------------------------

    title = ""

    # Primero buscamos el H1.
    h1 = soup.find("h1")

    if h1:
        title = clean(
            h1.get_text(
                " ",
                strip=True
            )
        )

    # --------------------------------------------------------
    # SUBTÍTULO
    # --------------------------------------------------------

    subtitle = ""

    h2 = soup.find("h2")

    if h2:
        subtitle = clean(
            h2.get_text(
                " ",
                strip=True
            )
        )

    # --------------------------------------------------------
    # FECHA
    #
    # La página puede mostrar la fecha como texto.
    # La guardamos para identificar el contenido actual.
    # --------------------------------------------------------

    fecha_fuente = ""

    # Buscar una fecha del tipo:
    # 20 de agosto de 2026

    patron_fecha = re.compile(
        r"\b\d{1,2}\s+de\s+"
        r"(?:enero|febrero|marzo|abril|mayo|junio|"
        r"julio|agosto|septiembre|octubre|noviembre|diciembre)"
        r"\s+de\s+\d{4}\b",
        re.I
    )

    fecha_match = patron_fecha.search(
        soup.get_text(
            " ",
            strip=True
        )
    )

    if fecha_match:
        fecha_fuente = clean(
            fecha_match.group(0)
        )

    # --------------------------------------------------------
    # VERSÍCULO / REFERENCIA BÍBLICA
    # --------------------------------------------------------

    verse = ""

    enlace_biblia = soup.find(
        "a",
        href=re.compile(
            r"biblegateway\.com",
            re.I
        )
    )

    if enlace_biblia:

        verse = clean(
            enlace_biblia.get_text(
                " ",
                strip=True
            )
        )

    # Si el enlace no contiene el texto,
    # buscamos referencias bíblicas visibles.

    if not verse:

        texto_pagina = soup.get_text(
            " ",
            strip=True
        )

        match_versiculo = re.search(
            r"\bGálatas\s+5\.17-21\b",
            texto_pagina,
            re.I
        )

        if match_versiculo:
            verse = clean(
                match_versiculo.group(0)
            )

    # --------------------------------------------------------
    # AUDIO
    # --------------------------------------------------------

    audio = extract_mp3(
        html,
        [
            r"(https://intouch\.azureedge\.net/"
            r"spanish/devo/[A-Za-z0-9_./-]+\.mp3)"
        ]
    )

    # --------------------------------------------------------
    # LOCALIZAR EL CONTENEDOR REAL DEL DEVOCIONAL
    #
    # No debemos tomar todos los <p> de la página.
    # En Contacto tiene navegación, footer y otras
    # secciones que NO pertenecen al devocional.
    # --------------------------------------------------------

    contenido = None

    # Buscamos primero elementos que tengan el título actual.

    if title:

        titulo_elemento = soup.find(
            string=re.compile(
                re.escape(title),
                re.I
            )
        )

        if titulo_elemento:

            padre = titulo_elemento.parent

            # Subimos algunos niveles buscando un contenedor
            # que tenga varios párrafos.

            for _ in range(6):

                if padre is None:
                    break

                posibles = padre.find_all(
                    ["p", "li"]
                )

                if len(posibles) >= 2:

                    contenido = padre
                    break

                padre = padre.parent

    # --------------------------------------------------------
    # EXTRAER PÁRRAFOS DEL DEVOCIONAL
    # --------------------------------------------------------

    paragraphs = []

    if contenido:

        for tag in contenido.find_all(
            ["p", "li"]
        ):

            text = clean(
                tag.get_text(
                    " ",
                    strip=True
                )
            )

            if not text:
                continue

            low = text.lower()

            # No incluir elementos de navegación,
            # suscripción o footer.

            if any(
                x in low
                for x in (
                    "suscríbase",
                    "suscribirse",
                    "correo electrónico",
                    "opciones de lectura",
                    "biblia en un año",
                    "compartir",
                    "share",
                )
            ):
                continue

            if len(text) < 25:
                continue

            # Evitar repetir la referencia bíblica
            # como párrafo.

            if (
                verse
                and text == verse
            ):
                continue

            paragraphs.append(text)

    # --------------------------------------------------------
    # RESPALDO
    #
    # Si la estructura HTML cambia, hacemos una segunda
    # búsqueda, pero seguimos evitando footer/navegación.
    # --------------------------------------------------------

    if not paragraphs:

        for tag in soup.find_all("p"):

            text = clean(
                tag.get_text(
                    " ",
                    strip=True
                )
            )

            if not text:
                continue

            low = text.lower()

            if any(
                x in low
                for x in (
                    "suscríbase",
                    "suscribirse",
                    "correo electrónico",
                    "opciones de lectura",
                    "biblia en un año",
                    "compartir",
                    "share",
                )
            ):
                continue

            if len(text) < 40:
                continue

            if (
                verse
                and text == verse
            ):
                continue

            paragraphs.append(text)

    # --------------------------------------------------------
    # LIMPIEZA FINAL
    # --------------------------------------------------------

    limpios = []

    for text in paragraphs:

        low = text.lower()

        # No permitir que contenido posterior
        # de la página se mezcle con el devocional.

        if any(
            x in low
            for x in (
                "también te puede interesar",
                "contenido relacionado",
                "suscríbete",
                "síguenos",
                "síganos",
                "recibe nuestro",
            )
        ):
            break

        limpios.append(text)

    paragraphs = limpios[:10]

    # --------------------------------------------------------
    # VALIDACIÓN
    # --------------------------------------------------------

    if not title:
        raise RuntimeError(
            "No se pudo extraer el título "
            "de En Contacto"
        )

    if not paragraphs:
        raise RuntimeError(
            "No se pudo extraer el texto "
            "del devocional de En Contacto"
        )

    # --------------------------------------------------------
    # RESULTADO
    # --------------------------------------------------------

    return {
        "titulo": title,
        "subtitulo": subtitle,
        "fecha_fuente": fecha_fuente,
        "versiculo": verse,
        "parrafos": paragraphs,
        "audio_url": audio,
        "audio_tipo": "mp3",
        "link": (
            "https://www.encontactoglobal.org/"
            "lea/devocionales-diarios"
        ),
    }
        

# ============================================================
# BAYLESS CONLEY
# ============================================================

def scrape_bayless():

    landing = (
        "https://www.respuestasbc.com/"
        "?redirect_to=latest&post_type=devotional"
    )

    response = get(landing)

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    html = str(soup)

    # --------------------------------------------------------
    # TÍTULO
    # --------------------------------------------------------

    title = ""

    candidatos = []

    for tag in soup.find_all(
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
            r"(#\s*\d+\s+)?"
            r"[A-Za-zÁÉÍÓÚáéíóúÑñÜü]",
            candidato
        ):

            title = candidato
            break

    # OpenGraph

    if not title:

        og = soup.find(
            "meta",
            attrs={
                "property": "og:title"
            }
        )

        if og:

            title = clean(
                og.get(
                    "content",
                    ""
                )
            )

    # Title HTML

    if not title:

        title_tag = soup.find("title")

        if title_tag:

            title = clean(
                title_tag.get_text()
            )

    # --------------------------------------------------------
    # LIMPIAR TÍTULO
    # --------------------------------------------------------

    title = re.sub(
        r"^\s*#\s*\d+\s*[-–—:]?\s*",
        "",
        title
    ).strip()

    # Nunca aceptar "Devocional Diario"

    if title.lower() in {
        "devocional diario",
        "respuestas para cada día",
        "bayless conley",
    }:

        title = ""

    # --------------------------------------------------------
    # TEXTO
    # --------------------------------------------------------

    paragraphs = []

    for p in soup.find_all("p"):

        text = clean(
            p.get_text(
                " ",
                strip=True
            )
        )

        if not text:
            continue

        low = text.lower()

        # Elimina contenido que NO pertenece
        # al devocional actual.

        if any(
            x in low
            for x in (
                "suscrib",
                "recibir devocionales",
                "escuche este devocional",
                "share",
                "compartir",
                "there was an error submitting",
                "me gustaría recibir",
                "© 2026 bayless conley",
                "todos los derechos reservados",
            )
        ):

            continue

        if len(text) < 20:
            continue

        paragraphs.append(text)

    # --------------------------------------------------------
    # IMPORTANTE:
    #
    # Evitamos arrastrar textos de "devocional anterior",
    # recomendaciones y footer.
    #
    # Si encontramos bloques que claramente pertenecen
    # a devocionales anteriores, dejamos de agregarlos.
    # --------------------------------------------------------

    limpios = []

    marcadores_fin = (
        "la siguiente “c”",
        'la siguiente "c"',
        "la siguiente 'c'",
        "en el devocional anterior",
        "el devocional anterior",
        "la siguiente c de",
        "la próxima “c”",
        'la próxima "c"',
    )

    for text in paragraphs:

        low = text.lower()

        if any(
            marcador in low
            for marcador in marcadores_fin
        ):

            break

        limpios.append(text)

    paragraphs = limpios

    # --------------------------------------------------------
    # AUDIO SOUNDCLOUD
    # --------------------------------------------------------

    audio = ""

    for a in soup.find_all(
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

    if not audio:

        match = re.search(
            r"https?://(?:www\.)?"
            r"soundcloud\.com/"
            r"respuestasbc/"
            r"[A-Za-z0-9_-]+",
            html,
            flags=re.I
        )

        if match:

            audio = match.group(0)

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
        "link": (
            "https://www.respuestasbc.com/"
            "devotional/"
        ),
    }


# ============================================================
# KENNETH COPELAND
# ============================================================

def scrape_kenneth():

    url = (
        "https://main.kcmlatino.org/"
        "devocional"
    )

    response = get(url)

    return _scrape_kcm_page(
        response.url,
        response.text
    )


def _scrape_kcm_page(
    url,
    html
):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    # --------------------------------------------------------
    # TÍTULO
    # --------------------------------------------------------

    title = ""

    h1 = soup.find("h1")

    if h1:

        title = clean(
            h1.get_text(
                " ",
                strip=True
            )
        )

    if not title:

        og = soup.find(
            "meta",
            attrs={
                "property": "og:title"
            }
        )

        if og:

            title = clean(
                og.get(
                    "content",
                    ""
                )
            )

    # --------------------------------------------------------
    # TEXTO
    # --------------------------------------------------------

    paragraphs = []

    for p in soup.find_all("p"):

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
            r"(https://maincms\.nyc3\."
            r"digitaloceanspaces\.com/"
            r"[A-Za-z0-9_./-]+\.mp3)",

            r'(?:src|data-src|audio)'
            r'["\'=:\s]+'
            r'(https://maincms\.nyc3\.'
            r'digitaloceanspaces\.com/'
            r'[A-Za-z0-9_./-]+\.mp3)',
        ]
    )

    if not audio:

        match = re.search(
            r"(https?:\\?/\\?/"
            r"maincms\.nyc3\."
            r"digitaloceanspaces\.com"
            r"\\?/[A-Za-z0-9_./-]+\.mp3)",
            html,
            flags=re.I
        )

        if match:

            audio = match.group(1).replace(
                "\\/",
                "/"
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
        "link": (
            "https://main.kcmlatino.org/"
            "devotional"
        ),
    }


# ============================================================
# COMPROBACIÓN DEL CONTENIDO
# ============================================================

def firma_contenido(item):

    """
    Crea una firma del título + texto.

    Sirve para saber si el contenido obtenido
    realmente cambió respecto al contenido anterior.
    """

    if not valid(item):
        return ""

    titulo = clean(
        item.get("titulo", "")
    ).lower()

    texto = clean(
        " ".join(
            item.get(
                "parrafos",
                []
            )
        )
    ).lower()

    return (
        titulo
        + "|"
        + texto
    )


def contenido_cambio(
    anterior,
    nuevo
):

    if not valid(nuevo):
        return False

    if not valid(anterior):
        return True

    return (
        firma_contenido(anterior)
        != firma_contenido(nuevo)
    )


# ============================================================
# FECHA
# ============================================================

def fecha_actual():

    # Colombia está en UTC-5.
    # Para la fecha del devocional usamos UTC-5
    # explícitamente.

    ahora_utc = dt.datetime.now(
        dt.timezone.utc
    )

    ahora_colombia = (
        ahora_utc
        - dt.timedelta(hours=5)
    )

    return ahora_colombia.date()


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


# ============================================================
# INTENTO DE ACTUALIZACIÓN
# ============================================================

def intentar_actualizacion(
    old,
    fecha
):

    data = dict(old)

    resultados = {}

    fuentes = {
        "encontacto": scrape_encontacto,
        "bayless": scrape_bayless,
        "kenneth": scrape_kenneth,
    }

    for clave, funcion in fuentes.items():

        try:

            nuevo = funcion()

            if not valid(nuevo):

                raise RuntimeError(
                    "La fuente respondió, "
                    "pero faltan título o texto."
                )

            anterior = old.get(clave)

            cambio = contenido_cambio(
                anterior,
                nuevo
            )

            resultados[clave] = {
                "nuevo": nuevo,
                "cambio": cambio,
            }

            if cambio:

                data[clave] = nuevo

                print(
                    f"OK  - {clave}: "
                    f"{nuevo['titulo']!r} "
                    f"(contenido nuevo)"
                )

            else:

                print(
                    f"ESPERANDO - {clave}: "
                    f"la página respondió, "
                    f"pero el contenido es "
                    f"igual al anterior."
                )

        except Exception as exc:

            print(
                f"FAIL - {clave}: {exc}",
                file=sys.stderr
            )

            resultados[clave] = {
                "nuevo": None,
                "cambio": False,
            }

            if valid(old.get(clave)):

                data[clave] = old[clave]

                print(
                    f"      Se conserva "
                    f"el último contenido válido "
                    f"de {clave}."
                )

    data["fecha"] = fecha_espanol(fecha)

    data["generado"] = (
        dt.datetime.now(
            dt.timezone.utc
        )
        .isoformat()
        .replace("+00:00", "Z")
    )

    return data, resultados


# ============================================================
# GUARDAR DATA.JSON
# ============================================================

def guardar(data):

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
# MODO NORMAL
# ============================================================

def ejecucion_normal():

    old = load_previous()

    fecha = fecha_actual()

    data, resultados = intentar_actualizacion(
        old,
        fecha
    )

    guardar(data)

    print(
        "\nActualización terminada."
    )


# ============================================================
# MODO REINTENTOS
# ============================================================

def ejecucion_con_reintentos():

    old = load_previous()

    fecha = fecha_actual()

    data_final = dict(old)

    for intento in range(
        1,
        MAX_INTENTOS + 1
    ):

        print(
            "\n"
            + "=" * 70
        )

        print(
            f"INTENTO {intento}/{MAX_INTENTOS}"
        )

        ahora = dt.datetime.now(
            dt.timezone.utc
        )

        print(
            "Hora UTC:",
            ahora.strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

        print(
            "Hora Colombia:",
            (
                ahora
                - dt.timedelta(hours=5)
            ).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

        print(
            "=" * 70
        )

        data, resultados = intentar_actualizacion(
            old,
            fecha
        )

        data_final = data

        pendientes = []

        for clave in (
            "encontacto",
            "bayless",
            "kenneth",
        ):

            resultado = resultados.get(
                clave,
                {}
            )

            if not resultado.get(
                "cambio",
                False
            ):

                pendientes.append(
                    clave
                )

        # ----------------------------------------------------
        # LOS 3 CAMBIARON
        # ----------------------------------------------------

        if not pendientes:

            print(
                "\n"
                + "=" * 70
            )

            print(
                "TODOS LOS DEVOCIONALES "
                "ESTÁN ACTUALIZADOS."
            )

            print(
                "=" * 70
            )

            guardar(data_final)

            print(
                "data.json guardado correctamente."
            )

            return

        # ----------------------------------------------------
        # TODAVÍA FALTA ALGUNO
        # ----------------------------------------------------

        print(
            "\nPENDIENTES:"
        )

        for clave in pendientes:

            print(
                f" - {clave}"
            )

        # Guardamos los que sí hayan cambiado.

        guardar(data_final)

        # ----------------------------------------------------
        # SI NO ES EL ÚLTIMO INTENTO,
        # ESPERAMOS 20 MINUTOS.
        # ----------------------------------------------------

        if intento < MAX_INTENTOS:

            print(
                "\nEsperando "
                "20 minutos antes "
                "del siguiente intento..."
            )

            time.sleep(
                INTERVALO_REINTENTO
            )

            # Volvemos a leer data.json porque durante
            # el proceso ya pueden haberse actualizado
            # algunas fuentes.

            old = load_previous()

    # ========================================================
    # TERMINÓ LA VENTANA DE INTENTOS
    # ========================================================

    print(
        "\n"
        + "=" * 70
    )

    print(
        "La ventana de reintentos terminó."
    )

    print(
        "Las fuentes que todavía no cambiaron "
        "conservaron el contenido anterior."
    )

    print(
        "=" * 70
    )

    guardar(data_final)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    if (
        len(sys.argv) > 1
        and sys.argv[1] == "--reintentos"
    ):

        ejecucion_con_reintentos()

    else:

        ejecucion_normal()
