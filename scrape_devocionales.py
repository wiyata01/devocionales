#!/usr/bin/env python3

"""
scrape_devocionales.py

Actualiza los tres devocionales diarios y la tarjeta bíblica para mujeres.

La tarjeta bíblica:
- Consulta Bible.com directamente.
- Usa únicamente Salmos, Isaías y Juan.
- Usa la versión RVC.
- No contiene versículos escritos dentro del código.
- Guarda únicamente las referencias ya utilizadas para evitar repeticiones.
"""

import json
import re
import sys
import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo


DATA_FILE = Path("data.json")

TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36 "
        "DevocionalesDiariosBot/5.0"
    )
}


# =========================================================
# UTILIDADES
# =========================================================

def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def get_soup(url):
    r = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT
    )
    r.raise_for_status()

    return BeautifulSoup(
        r.text,
        "html.parser"
    )


# =========================================================
# 1) EN CONTACTO
# =========================================================

def scrape_encontacto():

    url = "https://www.encontacto.org/lea/devocionales-diarios"

    soup = get_soup(url)
    html = str(soup)

    h1 = soup.find("h1")
    title = clean(
        h1.get_text()
    ) if h1 else ""

    h2 = soup.find("h2")
    subtitle = clean(
        h2.get_text()
    ) if h2 else ""

    verse = ""

    verse_link = soup.find(
        "a",
        href=re.compile(
            r"biblegateway\.com"
        )
    )

    if verse_link:

        verse = clean(
            verse_link.get_text()
        )

    audio = ""

    m = re.search(
        r"https://intouch\.azureedge\.net/spanish/devo/[\w\-.]+\.mp3",
        html
    )

    if m:
        audio = m.group(0)

    paragraphs = []

    for tag in soup.find_all(
        ["p", "li"]
    ):

        t = clean(
            tag.get_text()
        )

        if not t:
            continue

        if t == verse:
            continue

        if "BIBLIA EN UN" in t.upper():
            break

        if "suscríbase" in t.lower():
            continue

        if "suscribir" in t.lower():
            continue

        paragraphs.append(t)

        if len(paragraphs) >= 8:
            break

    return {
        "titulo": title or subtitle,
        "subtitulo": subtitle if title else "",
        "versiculo": verse,
        "parrafos": paragraphs,
        "audio_url": audio,
        "audio_tipo": "mp3",
        "link": url,
    }


# =========================================================
# 2) BAYLESS CONLEY
# =========================================================

def scrape_bayless():

    landing = (
        "https://www.respuestasbc.com/devotional/"
    )

    r = requests.get(
        landing,
        headers=HEADERS,
        timeout=TIMEOUT,
        allow_redirects=True
    )

    r.raise_for_status()

    soup = BeautifulSoup(
        r.text,
        "html.parser"
    )

    links = []

    for a in soup.find_all(
        "a",
        href=True
    ):

        href = urljoin(
            r.url,
            a["href"]
        )

        if "/devotional/" in href:

            links.append(href)

    if not links:

        raise RuntimeError(
            "No se encontró el devocional actual de Bayless Conley"
        )

    # El listado normalmente coloca primero
    # el devocional más reciente.
    final_url = links[0]

    soup = get_soup(
        final_url
    )

    h1 = soup.find("h1")

    title = clean(
        h1.get_text()
    ) if h1 else ""

    paragraphs = []

    for p in soup.find_all("p"):

        t = clean(
            p.get_text()
        )

        if not t:
            continue

        low = t.lower()

        if "escuche este devocional" in low:
            break

        if "suscrib" in low:
            continue

        if "recibir devocionales" in low:
            continue

        paragraphs.append(t)

    audio = ""

    sc_link = soup.find(
        "a",
        href=re.compile(
            r"soundcloud\.com"
        )
    )

    if sc_link:

        audio = sc_link["href"]

    return {
        "titulo": title,
        "subtitulo": "",
        "versiculo": "",
        "parrafos": paragraphs,
        "audio_url": audio,
        "audio_tipo": "soundcloud",
        "link": final_url,
    }


# =========================================================
# 3) KENNETH COPELAND
# =========================================================

def scrape_kenneth():

    try:

        api = (
            "https://main.kcmlatino.org/wp-json/wp/v2/devotional"
            "?per_page=1&orderby=date&order=desc"
        )

        r = requests.get(
            api,
            headers=HEADERS,
            timeout=TIMEOUT
        )

        if r.ok and r.json():

            post = r.json()[0]

            title = clean(
                BeautifulSoup(
                    post["title"]["rendered"],
                    "html.parser"
                ).get_text()
            )

            body_soup = BeautifulSoup(
                post["content"]["rendered"],
                "html.parser"
            )

            paragraphs = [
                clean(p.get_text())
                for p in body_soup.find_all("p")
                if clean(p.get_text())
            ]

            link = post.get(
                "link",
                "https://main.kcmlatino.org/devotional"
            )

            audio = _find_kcm_audio(
                link
            )

            verse = ""

            if (
                paragraphs
                and len(paragraphs[0]) < 160
                and "«" in paragraphs[0]
            ):

                verse = paragraphs[0]

            return {
                "titulo": title,
                "subtitulo": "",
                "versiculo": verse,
                "parrafos": paragraphs,
                "audio_url": audio,
                "audio_tipo": "mp3",
                "link": link,
            }

    except Exception:
        pass

    soup = get_soup(
        "https://main.kcmlatino.org/devotional"
    )

    first_link = soup.find(
        "a",
        href=re.compile(
            r"/devotional/[\w\-]+/?$"
        )
    )

    if not first_link:

        raise RuntimeError(
            "No se encontró enlace a devocional de Kenneth Copeland"
        )

    return _scrape_kcm_post(
        urljoin(
            "https://main.kcmlatino.org",
            first_link["href"]
        )
    )


def _scrape_kcm_post(url):

    soup = get_soup(
        url
    )

    h1 = soup.find("h1")

    title = clean(
        h1.get_text()
    ) if h1 else ""

    paragraphs = [
        clean(p.get_text())
        for p in soup.find_all("p")
        if clean(p.get_text())
    ]

    audio = _find_kcm_audio(
        url,
        soup
    )

    verse = ""

    if (
        paragraphs
        and "«" in paragraphs[0]
    ):

        verse = paragraphs[0]

    return {
        "titulo": title,
        "subtitulo": "",
        "versiculo": verse,
        "parrafos": paragraphs,
        "audio_url": audio,
        "audio_tipo": "mp3",
        "link": url,
    }


def _find_kcm_audio(
    url,
    soup=None
):

    if soup is None:
        soup = get_soup(url)

    html = str(soup)

    m = re.search(
        r"https://maincms\.nyc3\.digitaloceanspaces\.com/[\w/\-.]+\.mp3",
        html
    )

    return m.group(0) if m else ""


# =========================================================
# 4) TARJETA BÍBLICA PARA MUJERES
# =========================================================

# SOLO se guardan los códigos de los tres libros.
#
# NO se guardan versículos.
# NO se guardan textos bíblicos.
#
# Los textos se obtienen diariamente desde Bible.com.

BIBLE_BOOKS = [
    ("PSA", "Salmos", 150),
    ("ISA", "Isaías", 66),
    ("JHN", "Juan", 21),
]


def cargar_historial_tarjeta(data):

    historial = data.get(
        "tarjeta_mujer_historial",
        []
    )

    if not isinstance(
        historial,
        list
    ):

        historial = []

    return historial


def guardar_historial_tarjeta(
    data,
    historial
):

    # Solamente referencias usadas.
    #
    # Nunca guardamos aquí el texto bíblico.

    data[
        "tarjeta_mujer_historial"
    ] = historial


# =========================================================
# EXTRACTOR BIBLE.COM
# =========================================================

def extraer_versiculos_bible_com(
    soup,
    codigo,
    nombre_libro,
    capitulo
):

    """
    Extrae los versículos visibles de Bible.com/RVC.

    Bible.com puede presentar el número del versículo
    de varias formas:

        1 Texto del versículo

    o:

        1
        Texto del versículo

    o:

        7¡Tú eres mi refugio!

    Además, el texto de un versículo puede ocupar
    varias líneas.

    Esta función soporta esas variantes.
    """

    texto = soup.get_text(
        "\n"
    )

    lineas = []

    for linea in texto.splitlines():

        linea = clean(
            linea
        )

        if linea:
            lineas.append(
                linea
            )

    candidatos = []

    numero_actual = None
    contenido_actual = []

    siguiente_numero = 1
    esperando_texto_para = None

    def guardar_actual():

        nonlocal numero_actual
        nonlocal contenido_actual

        if numero_actual is None:
            return

        contenido = clean(
            " ".join(
                contenido_actual
            )
        )

        if not contenido:
            return

        if len(contenido) < 3:
            return

        referencia = (
            f"{nombre_libro} "
            f"{capitulo}:"
            f"{numero_actual}"
        )

        candidatos.append(
            {
                "referencia": referencia,
                "texto": contenido,
                "url": (
                    "https://www.bible.com/es/bible/146/"
                    f"{codigo}.{capitulo}.RVC"
                )
            }
        )

    def comenzar_versiculo(
        numero,
        contenido=""
    ):

        nonlocal numero_actual
        nonlocal contenido_actual
        nonlocal siguiente_numero
        nonlocal esperando_texto_para

        # Solo aceptamos la secuencia correcta:
        #
        # 1, 2, 3, 4, 5...
        #
        # Esto evita confundir números de navegación,
        # capítulos o elementos externos.

        if numero != siguiente_numero:
            return False

        guardar_actual()

        numero_actual = numero

        contenido_actual = []

        if contenido:
            contenido_actual.append(
                contenido
            )

            esperando_texto_para = None

        else:

            esperando_texto_para = numero

        siguiente_numero += 1

        return True

    for linea in lineas:

        low = linea.lower()

        # -------------------------------------------------
        # FIN DEL TEXTO BÍBLICO
        # -------------------------------------------------

        if low.startswith(
            "actualmente seleccionado"
        ):

            break

        if low.startswith(
            "destacar"
        ):

            break

        if low.startswith(
            "copiar"
        ):

            break

        if low.startswith(
            "comparar"
        ):

            break

        if low.startswith(
            "compartir"
        ):

            break

        # -------------------------------------------------
        # SI EL NÚMERO DEL VERSÍCULO ESTABA SOLO
        # -------------------------------------------------

        if esperando_texto_para is not None:

            # Si aparece otra línea numérica antes
            # del texto, la ignoramos y seguimos esperando.

            if re.fullmatch(
                r"\d{1,3}",
                linea
            ):

                continue

            contenido = clean(
                linea
            )

            if contenido:

                contenido_actual = [
                    contenido
                ]

                esperando_texto_para = None

            continue

        # -------------------------------------------------
        # NÚMERO DE VERSÍCULO + TEXTO
        # -------------------------------------------------

        m = re.match(
            r"^(\d{1,3})(.*)$",
            linea
        )

        if m:

            numero = int(
                m.group(1)
            )

            resto = clean(
                m.group(2)
            )

            # ---------------------------------------------
            # CASO NORMAL:
            #
            # 1 Dichoso aquel...
            #
            # 7¡Tú eres mi refugio!
            #
            # 8«Yo te voy...
            # ---------------------------------------------

            if (
                1 <= numero <= 200
                and numero == siguiente_numero
            ):

                comenzar_versiculo(
                    numero,
                    resto
                )

                continue

        # -------------------------------------------------
        # NÚMERO DE VERSÍCULO SOLO
        # -------------------------------------------------

        if re.fullmatch(
            r"\d{1,3}",
            linea
        ):

            numero = int(
                linea
            )

            if (
                1 <= numero <= 200
                and numero == siguiente_numero
            ):

                comenzar_versiculo(
                    numero,
                    ""
                )

                continue

        # -------------------------------------------------
        # TEXTO CONTINUACIÓN
        # -------------------------------------------------

        if numero_actual is not None:

            contenido_actual.append(
                linea
            )

    # Guardar el último versículo.
    guardar_actual()

    # -----------------------------------------------------
    # ELIMINAR DUPLICADOS
    # -----------------------------------------------------

    resultado = []

    vistos = set()

    for item in candidatos:

        referencia = item[
            "referencia"
        ]

        if referencia in vistos:
            continue

        vistos.add(
            referencia
        )

        resultado.append(
            item
        )

    return resultado


# =========================================================
# OBTENER CAPÍTULO BIBLE.COM
# =========================================================

def obtener_capitulo_bible(
    codigo,
    nombre_libro,
    capitulo
):

    url = (
        "https://www.bible.com/es/bible/146/"
        f"{codigo}.{capitulo}.RVC"
    )

    print(
        f"Buscando Biblia: "
        f"{nombre_libro} "
        f"{capitulo} RVC"
    )

    soup = get_soup(
        url
    )

    versiculos = (
        extraer_versiculos_bible_com(
            soup,
            codigo,
            nombre_libro,
            capitulo
        )
    )

    if not versiculos:

        raise RuntimeError(
            "No se pudieron extraer versículos de "
            f"{url}"
        )

    return versiculos


# =========================================================
# ELEGIR NUEVO VERSÍCULO
# =========================================================

def obtener_nuevo_versiculo_mujer(
    data
):

    historial = (
        cargar_historial_tarjeta(
            data
        )
    )

    usados = set(
        historial
    )

    # -----------------------------------------------------
    # FECHA COLOMBIA
    # -----------------------------------------------------

    fecha = datetime.datetime.now(
        ZoneInfo(
            "America/Bogota"
        )
    ).date()

    inicio = datetime.date(
        2026,
        1,
        1
    )

    dia_del_periodo = (
        fecha - inicio
    ).days

    # -----------------------------------------------------
    # TOTAL DE CAPÍTULOS
    #
    # Salmos = 150
    # Isaías = 66
    # Juan = 21
    # -----------------------------------------------------

    total_capitulos = sum(
        cantidad
        for _, _, cantidad
        in BIBLE_BOOKS
    )

    posicion = (
        dia_del_periodo
        % total_capitulos
    )

    # -----------------------------------------------------
    # DETERMINAR LIBRO Y CAPÍTULO
    # -----------------------------------------------------

    acumulado = 0

    libro_seleccionado = None
    capitulo_seleccionado = None

    for (
        codigo,
        nombre,
        cantidad
    ) in BIBLE_BOOKS:

        if (
            posicion
            <
            acumulado + cantidad
        ):

            libro_seleccionado = (
                codigo,
                nombre
            )

            capitulo_seleccionado = (
                posicion
                - acumulado
                + 1
            )

            break

        acumulado += cantidad

    if libro_seleccionado is None:

        raise RuntimeError(
            "No se pudo determinar "
            "el capítulo bíblico."
        )

    codigo, nombre = (
        libro_seleccionado
    )

    # -----------------------------------------------------
    # PRIMER INTENTO:
    # CAPÍTULO DETERMINADO POR LA FECHA
    # -----------------------------------------------------

    candidatos = (
        obtener_capitulo_bible(
            codigo,
            nombre,
            capitulo_seleccionado
        )
    )

    nuevos = [
        item
        for item in candidatos
        if item["referencia"]
        not in usados
    ]

    if nuevos:

        indice = (
            abs(dia_del_periodo)
            % len(nuevos)
        )

        return nuevos[
            indice
        ]

    # -----------------------------------------------------
    # SI TODOS LOS VERSÍCULOS DE ESE CAPÍTULO
    # YA FUERON USADOS
    #
    # BUSCAR EN LOS TRES LIBROS.
    # -----------------------------------------------------

    for (
        codigo,
        nombre,
        cantidad
    ) in BIBLE_BOOKS:

        for capitulo in range(
            1,
            cantidad + 1
        ):

            try:

                candidatos = (
                    obtener_capitulo_bible(
                        codigo,
                        nombre,
                        capitulo
                    )
                )

            except Exception:

                continue

            nuevos = [
                item
                for item in candidatos
                if item["referencia"]
                not in usados
            ]

            if nuevos:

                indice = (
                    abs(dia_del_periodo)
                    % len(nuevos)
                )

                return nuevos[
                    indice
                ]

    raise RuntimeError(
        "No se encontró un versículo nuevo "
        "en Salmos, Isaías o Juan."
    )


# =========================================================
# TARJETA MUJER
# =========================================================

def scrape_tarjeta_mujer(
    data
):

    nuevo = (
        obtener_nuevo_versiculo_mujer(
            data
        )
    )

    historial = (
        cargar_historial_tarjeta(
            data
        )
    )

    referencia = (
        nuevo["referencia"]
    )

    if referencia not in historial:

        historial.append(
            referencia
        )

    # Guardamos únicamente referencias.
    guardar_historial_tarjeta(
        data,
        historial
    )

    return {
        "referencia": nuevo[
            "referencia"
        ],
        "texto": nuevo[
            "texto"
        ],
        "fuente": nuevo[
            "url"
        ],
        "version": "RVC"
    }


# =========================================================
# MAIN
# =========================================================

def main():

    ahora = datetime.datetime.now(
        ZoneInfo(
            "America/Bogota"
        )
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
        f"{ahora.day} de "
        f"{meses[ahora.month - 1]} de "
        f"{ahora.year}"
    )

    data = {
        "fecha": fecha_es,
        "generado": ahora.isoformat()
    }

    # =====================================================
    # RECUPERAR HISTORIAL ANTERIOR
    # =====================================================

    if DATA_FILE.exists():

        try:

            with open(
                DATA_FILE,
                "r",
                encoding="utf-8"
            ) as f:

                anterior = json.load(f)

            if isinstance(
                anterior,
                dict
            ):

                historial = (
                    anterior.get(
                        "tarjeta_mujer_historial",
                        []
                    )
                )

                if isinstance(
                    historial,
                    list
                ):

                    data[
                        "tarjeta_mujer_historial"
                    ] = historial

        except Exception as e:

            print(
                "Aviso: no se pudo leer "
                "historial anterior:",
                e
            )

    # =====================================================
    # DEVOCIONALES
    # =====================================================

    fuentes = {
        "encontacto": scrape_encontacto,
        "bayless": scrape_bayless,
        "kenneth": scrape_kenneth,
    }

    errores = []

    for clave, fn in fuentes.items():

        try:

            data[clave] = fn()

            print(
                f"OK - {clave}: "
                f"{data[clave]['titulo']!r}"
            )

        except Exception as e:

            errores.append(
                f"{clave}: {e}"
            )

            print(
                f"FAIL - {clave}: {e}",
                file=sys.stderr
            )

            data[clave] = None

    # =====================================================
    # TARJETA PARA MUJERES
    # =====================================================

    try:

        data[
            "tarjeta_mujer"
        ] = scrape_tarjeta_mujer(
            data
        )

        print(
            "OK - tarjeta mujer: "
            f"{data['tarjeta_mujer']['referencia']}"
        )

    except Exception as e:

        errores.append(
            f"tarjeta_mujer: {e}"
        )

        print(
            f"FAIL - tarjeta_mujer: {e}",
            file=sys.stderr
        )

        # -------------------------------------------------
        # SI BIBLE.COM FALLA:
        # CONSERVAR TARJETA ANTERIOR
        # -------------------------------------------------

        if DATA_FILE.exists():

            try:

                with open(
                    DATA_FILE,
                    "r",
                    encoding="utf-8"
                ) as f:

                    anterior = json.load(f)

                if anterior.get(
                    "tarjeta_mujer"
                ):

                    data[
                        "tarjeta_mujer"
                    ] = anterior[
                        "tarjeta_mujer"
                    ]

            except Exception:

                data[
                    "tarjeta_mujer"
                ] = None

        else:

            data[
                "tarjeta_mujer"
            ] = None

    # =====================================================
    # GUARDAR DATA.JSON
    # =====================================================

    with open(
        DATA_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

    # =====================================================
    # MOSTRAR ERRORES
    # =====================================================

    if errores:

        print(
            "\nAlgunas fuentes fallaron hoy:\n - "
            + "\n - ".join(
                errores
            ),
            file=sys.stderr
        )


# =========================================================
# EJECUCIÓN
# =========================================================

if __name__ == "__main__":

    main()
