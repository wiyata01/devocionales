#!/usr/bin/env python3

"""
Actualizador de devocionales diarios.

Funcionamiento:

1. Consulta las tres fuentes.
2. Compara el contenido obtenido con el contenido anterior.
3. Si los tres ya cambiaron, guarda data.json y termina.
4. Si alguno todavía tiene el contenido anterior:
       espera 20 minutos
       vuelve a consultar.
5. Continúa hasta que los tres estén actualizados o GitHub
   Actions alcance el límite máximo de ejecución.

Fuentes:

En Contacto:
https://www.encontactoglobal.org/lea/devocionales-diarios

Bayless Conley:
https://www.respuestasbc.com/devotional/

Kenneth Copeland:
https://main.kcmlatino.org/devotional
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

# 20 minutos entre intentos
ESPERA_ENTRE_INTENTOS = 20 * 60

# GitHub Actions permite aproximadamente 6 horas por job.
# 18 intentos separados por 20 minutos = aproximadamente 6 horas.
MAX_INTENTOS = 18


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

    adapter = HTTPAdapter(
        max_retries=retry
    )

    s.mount(
        "https://",
        adapter
    )

    s.headers.update(HEADERS)

    return s


S = crear_sesion()


# ============================================================
# UTILIDADES
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
        allow_redirects=True,
        cache_bust=True if False else False,
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

            return (
                match.group(1)
                .replace("\\/", "/")
            )

    return ""


def normalizar_texto(texto):

    texto = texto or ""

    texto = texto.lower()

    texto = re.sub(
        r"\s+",
        " ",
        texto
    )

    return texto.strip()


def contenido_valido(item):

    return (
        isinstance(item, dict)
        and bool(item.get("titulo"))
        and isinstance(
            item.get("parrafos"),
            list
        )
        and any(
            clean(x)
            for x in item.get(
                "parrafos",
                []
            )
        )
    )


def firma_contenido(item):

    """
    Genera una firma del contenido.

    Se utiliza para saber si el devocional realmente cambió.
    """

    if not isinstance(item, dict):

        return ""

    partes = [

        clean(
            item.get(
                "titulo",
                ""
            )
        ),

        clean(
            item.get(
                "subtitulo",
                ""
            )
        ),

        clean(
            item.get(
                "versiculo",
                ""
            )
        ),

    ]

    partes.extend(
        clean(x)
        for x in item.get(
            "parrafos",
            []
        )
    )

    return normalizar_texto(
        "\n".join(partes)
    )


# ============================================================
# CARGAR DATA ANTERIOR
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

        return {}

    except Exception as exc:

        print(
            "Aviso: no se pudo leer "
            f"data.json anterior: {exc}",
            file=sys.stderr
        )

        return {}


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
    # VERSÍCULO
    # --------------------------------------------------------

    verse = ""

    link_bible = soup.find(
        "a",
        href=re.compile(
            r"biblegateway\.com",
            re.I
        )
    )

    if link_bible:

        verse = clean(
            link_bible.get_text(
                " ",
                strip=True
            )
        )

    # --------------------------------------------------------
    # AUDIO
    # --------------------------------------------------------

    audio = extract_mp3(
        html,
        [
            r"(https://intouch\.azureedge\.net/"
            r"spanish/devo/"
            r"[A-Za-z0-9_./-]+\.mp3)"
        ]
    )

    # --------------------------------------------------------
    # TEXTO
    # --------------------------------------------------------

    paragraphs = []

    for tag in soup.find_all(
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

        if text == verse:

            continue

        low = text.lower()

        if "biblia en un año" in low:

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

        if len(text) < 25:

            continue

        paragraphs.append(text)

    # Evitar arrastrar footer
    paragraphs = paragraphs[:10]

    if not title:

        raise RuntimeError(
            "En Contacto no proporcionó título"
        )

    if not paragraphs:

        raise RuntimeError(
            "En Contacto no proporcionó texto"
        )

    return {

        "titulo": title,

        "subtitulo": subtitle,

        "versiculo": verse,

        "parrafos": paragraphs,

        "audio_url": audio,

        "audio_tipo": "mp3",

        "link":
            "https://www.encontactoglobal.org/"
            "lea/devocionales-diarios",

    }


# ============================================================
# BAYLESS CONLEY
# ============================================================

def scrape_bayless():

    url = (
        "https://www.respuestasbc.com/"
        "?redirect_to=latest&post_type=devotional"
    )

    response = get(url)

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    html = str(soup)

    # --------------------------------------------------------
    # TÍTULO
    # --------------------------------------------------------

    title = ""

    ignorados = {
        "devocional diario",
        "respuestas para cada día",
        "bayless conley",
    }

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

    # Último recurso
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

    if title.lower() in ignorados:

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

        # ----------------------------------------------------
        # ELIMINAR NAVEGACIÓN / SUSCRIPCIÓN / FOOTER
        # ----------------------------------------------------

        if any(
            palabra in low
            for palabra in (
                "suscrib",
                "recibir devocionales",
                "escuche este devocional",
                "share",
                "compartir",
                "there was an error submitting your subscription",
                "me gustaría recibir los correos gratis",
                "© 2026 bayless conley",
                "todos los derechos reservados",
            )
        ):

            continue

        # ----------------------------------------------------
        # ELIMINAR TEXTO DE OTROS DEVOCIONALES
        # ----------------------------------------------------

        if (
            "la siguiente “c”" in low
            or "la siguiente \"c\"" in low
            or "en el devocional anterior" in low
        ):

            continue

        # ----------------------------------------------------
        # EVITAR FOOTER Y CONTENIDO RELACIONADO
        # ----------------------------------------------------

        if any(
            palabra in low
            for palabra in (
                "contenido relacionado",
                "devocional anterior",
                "devocional siguiente",
                "último devocional",
                "siguiente devocional",
            )
        ):

            continue

        if len(text) < 20:

            continue

        paragraphs.append(text)

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
            r"https?://(?:www\.)?soundcloud\.com/"
            r"respuestasbc/[A-Za-z0-9_-]+",
            html,
            flags=re.I
        )

        if match:

            audio = match.group(0)

    # --------------------------------------------------------
    # VALIDAR
    # --------------------------------------------------------

    if not title:

        raise RuntimeError(
            "Bayless no proporcionó título"
        )

    if not paragraphs:

        raise RuntimeError(
            "Bayless no proporcionó texto"
        )

    return {

        "titulo": title,

        "subtitulo": "",

        "versiculo": "",

        "parrafos": paragraphs[:20],

        "audio_url": audio,

        "audio_tipo": "soundcloud",

        "link":
            "https://www.respuestasbc.com/"
            "devotional/",

    }


# ============================================================
# KENNETH COPELAND
# ============================================================

def scrape_kenneth():

    url = (
        "https://main.kcmlatino.org/"
        "devotional"
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
            palabra in low
            for palabra in (
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

            r"(?:src|data-src|audio)"
            r"[\"'=:\s]+"
            r"(https://maincms\.nyc3\."
            r"digitaloceanspaces\.com/"
            r"[A-Za-z0-9_./-]+\.mp3)",
        ]
    )

    if not audio:

        match = re.search(
            r"(https?:\\?/\\?/"
            r"maincms\.nyc3\."
            r"digitaloceanspaces\.com"
            r"\\?/"
            r"[A-Za-z0-9_./-]+\.mp3)",
            html,
            flags=re.I
        )

        if match:

            audio = (
                match.group(1)
                .replace("\\/", "/")
            )

    if not title:

        raise RuntimeError(
            "Kenneth no proporcionó título"
        )

    if not paragraphs:

        raise RuntimeError(
            "Kenneth no proporcionó texto"
        )

    return {

        "titulo": title,

        "subtitulo": "",

        "versiculo": verse,

        "parrafos": paragraphs[:20],

        "audio_url": audio,

        "audio_tipo": "mp3",

        "link":
            "https://main.kcmlatino.org/"
            "devotional",

    }


# ============================================================
# FECHA
# ============================================================

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

def consultar_fuentes():

    fuentes = {

        "encontacto":
            scrape_encontacto,

        "bayless":
            scrape_bayless,

        "kenneth":
            scrape_kenneth,

    }

    resultados = {}

    errores = {}

    for clave, funcion in fuentes.items():

        try:

            print(
                f"\nConsultando {clave}..."
            )

            nuevo = funcion()

            if not contenido_valido(nuevo):

                raise RuntimeError(
                    "La fuente respondió, "
                    "pero el contenido no es válido"
                )

            resultados[clave] = nuevo

            print(
                f"OK  - {clave}: "
                f"{nuevo['titulo']!r}"
            )

        except Exception as exc:

            errores[clave] = str(exc)

            print(
                f"FAIL - {clave}: {exc}",
                file=sys.stderr
            )

    return resultados, errores


# ============================================================
# COMPROBAR SI LOS TRES CAMBIARON
# ============================================================

def comprobar_actualizacion(
    anteriores,
    nuevos
):

    pendientes = []

    for clave in (
        "encontacto",
        "bayless",
        "kenneth"
    ):

        nuevo = nuevos.get(clave)

        anterior = anteriores.get(
            clave
        )

        if not contenido_valido(nuevo):

            pendientes.append(
                f"{clave}: sin contenido válido"
            )

            continue

        # Si no existe contenido anterior,
        # lo consideramos nuevo.
        if not contenido_valido(anterior):

            print(
                f"{clave}: no había "
                "contenido anterior"
            )

            continue

        firma_nueva = firma_contenido(
            nuevo
        )

        firma_anterior = firma_contenido(
            anterior
        )

        if (
            firma_nueva
            == firma_anterior
        ):

            pendientes.append(
                f"{clave}: todavía muestra "
                "el contenido anterior"
            )

        else:

            print(
                f"{clave}: NUEVO contenido detectado"
            )

    return pendientes


# ============================================================
# GUARDAR DATA.JSON
# ============================================================

def guardar_data(
    anterior,
    nuevos
):

    ahora = dt.datetime.now(
        dt.timezone.utc
    )

    hoy = ahora.date()

    data = dict(anterior)

    data["fecha"] = fecha_espanol(
        hoy
    )

    data["generado"] = (
        ahora.isoformat()
        .replace(
            "+00:00",
            "Z"
        )
    )

    for clave in (
        "encontacto",
        "bayless",
        "kenneth"
    ):

        data[clave] = nuevos[clave]

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

    anteriores = load_previous()

    print(
        "=========================================="
    )

    print(
        " ACTUALIZADOR DE DEVOCIONALES DIARIOS"
    )

    print(
        "=========================================="
    )

    print(
        "Se intentará actualizar hasta encontrar "
        "los tres devocionales nuevos."
    )

    print(
        f"Intervalo entre intentos: "
        f"{ESPERA_ENTRE_INTENTOS // 60} minutos"
    )

    for intento in range(
        1,
        MAX_INTENTOS + 1
    ):

        print(
            "\n"
            "=========================================="
        )

        print(
            f"INTENTO {intento}/{MAX_INTENTOS}"
        )

        print(
            "Hora UTC:",
            dt.datetime.now(
                dt.timezone.utc
            ).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        )

        print(
            "=========================================="
        )

        nuevos, errores = consultar_fuentes()

        # ----------------------------------------------------
        # Si una fuente falló, no se considera actualizada.
        # ----------------------------------------------------

        pendientes = comprobar_actualizacion(
            anteriores,
            nuevos
        )

        for clave in (
            "encontacto",
            "bayless",
            "kenneth"
        ):

            if clave not in nuevos:

                if not any(
                    p.startswith(
                        f"{clave}:"
                    )
                    for p in pendientes
                ):

                    pendientes.append(
                        f"{clave}: error de consulta"
                    )

        # ----------------------------------------------------
        # LOS TRES ESTÁN NUEVOS
        # ----------------------------------------------------

        if not pendientes:

            print(
                "\n"
                "=========================================="
            )

            print(
                "LOS 3 DEVOCIONALES ESTÁN ACTUALIZADOS"
            )

            print(
                "=========================================="
            )

            guardar_data(
                anteriores,
                nuevos
            )

            print(
                "data.json actualizado correctamente."
            )

            print(
                "El workflow puede hacer git push."
            )

            return

        # ----------------------------------------------------
        # MOSTRAR PENDIENTES
        # ----------------------------------------------------

        print(
            "\nDevocionales pendientes:"
        )

        for pendiente in pendientes:

            print(
                f"  - {pendiente}"
            )

        # ----------------------------------------------------
        # Si todavía quedan intentos
        # ----------------------------------------------------

        if intento < MAX_INTENTOS:

            print(
                "\nTodavía no están los tres "
                "actualizados."
            )

            print(
                f"Esperando "
                f"{ESPERA_ENTRE_INTENTOS // 60} "
                "minutos antes de volver a consultar..."
            )

            time.sleep(
                ESPERA_ENTRE_INTENTOS
            )

        else:

            print(
                "\nSe alcanzó el límite máximo "
                "de ejecución del workflow."
            )

            print(
                "No se publicará contenido "
                "parcial como si estuviera actualizado."
            )

            raise RuntimeError(
                "Los tres devocionales no "
                "estuvieron disponibles durante "
                "el periodo de reintentos."
            )


if __name__ == "__main__":

    main()
