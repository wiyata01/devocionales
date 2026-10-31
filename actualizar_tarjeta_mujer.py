#!/usr/bin/env python3

"""
Actualiza únicamente la tarjeta bíblica para mujeres.

IMPORTANTE:
- No contiene textos bíblicos en el código.
- Consulta Bible.com directamente.
- Usa solamente Salmos, Isaías y Juan en RVC.
- Guarda únicamente referencias utilizadas, nunca los textos en el historial.
- Si el workflow se ejecuta varias veces el mismo día, mantiene el mismo versículo.
Actualiza únicamente la tarjeta bíblica motivacional ("tarjeta_mujer").

Fuente: JSON estático de la Biblia Reina Valera Contemporánea (RVC),
publicado por https://github.com/mrk214/snapshots vía GitHub Pages.
No es un scraper de una página pensada para humanos, así que no hay
bloqueos de bots ni captchas: es solo un archivo JSON servido como
cualquier otro archivo estático.

Reglas:
- Cicla entre Salmos, Isaías y Juan, un versículo distinto cada día.
- Guarda en el historial solo la REFERENCIA usada (nunca el texto),
  para no repetir versículos mientras haya otros disponibles.
- Si el workflow corre varias veces el mismo día, mantiene el mismo
  versículo (no lo vuelve a sortear).
- Si la fuente falla, NO borra la tarjeta anterior: deja la de ayer
  puesta y solo avisa en los logs.
"""

import datetime as dt
import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo


DATA_FILE = Path("data.json")

TIMEOUT = 30
TIMEOUT = 60

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36 "
        "DevocionalesDiariosBot/5.0"
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

# JSON estático con la Biblia RVC completa (español). Publicado vía
# GitHub Pages por https://github.com/mrk214/snapshots
BIBLIA_URL = "https://mrk214.github.io/snapshots/es___spa___spa/RVC_vid_146.json"

BIBLE_BOOKS = [
    ("PSA", "Salmos", 150),
    ("ISA", "Isaías", 66),
    ("JHN", "Juan", 21),
# (book_usfm, cantidad_de_capitulos) - alternamos entre los tres libros
LIBROS = [
    ("PSA", 150),  # Salmos
    ("ISA", 66),   # Isaías
    ("JHN", 21),   # Juan
]


def clean(text):
    return re.sub(
        r"\s+",
        " ",
        text or ""
    ).strip()


def hoy_colombia():
    return dt.datetime.now(
        ZoneInfo("America/Bogota")
    ).date()
    return dt.datetime.now(ZoneInfo("America/Bogota")).date()


def cargar_data():

    if not DATA_FILE.exists():
        return {}

    try:

        with DATA_FILE.open(
            "r",
            encoding="utf-8"
        ) as archivo:

            data = json.load(archivo)

        return (
            data
            if isinstance(data, dict)
            else {}
        )

        with DATA_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as error:

        print(
            "Aviso: no se pudo leer data.json:",
            error
        )

        print("Aviso: no se pudo leer data.json:", error)
        return {}


def guardar_data(data):
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    with DATA_FILE.open(
        "w",
        encoding="utf-8"
    ) as archivo:

        json.dump(
            data,
            archivo,
            ensure_ascii=False,
            indent=2
        )

        archivo.write("\n")
def descargar_biblia():
    print(f"Descargando Biblia RVC desde: {BIBLIA_URL}")
    r = requests.get(BIBLIA_URL, headers=HEADERS, timeout=TIMEOUT)
    print(f"  HTTP {r.status_code} - {len(r.content)} bytes")
    r.raise_for_status()
    return r.json()


def obtener_capitulo(
    codigo,
    nombre,
    capitulo
):
def extraer_versiculos_capitulo(biblia, book_usfm, numero_capitulo):
    """Devuelve una lista de {referencia, texto} para cada versículo de
    ese capítulo, usando el JSON completo ya descargado.

    url = (
        f"https://www.bible.com/es/bible/146/"
        f"{codigo}.{capitulo}.RVC"
    )
    NOTA: el JSON de producción (mrk214/snapshots) usa las llaves "usfm"
    y "human" tanto en libros como en capítulos (no "book_usfm"/"name"
    como documenta el types.ts de ese proyecto, que describe el esquema
    de desarrollo, no el de producción). Ya verificado contra el archivo
    real.
    """

    print(
        f"Buscando Biblia: "
        f"{nombre} {capitulo} RVC"
    )
    chapter_usfm = f"{book_usfm}.{numero_capitulo}"

    respuesta = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT
    libro = next(
        (b for b in biblia.get("books", []) if b.get("usfm") == book_usfm),
        None,
    )
    if not libro:
        raise RuntimeError(f"No se encontró el libro {book_usfm} en el JSON.")

    respuesta.raise_for_status()

    soup = BeautifulSoup(
        respuesta.text,
        "html.parser"
    capitulo = next(
        (c for c in libro.get("chapters", []) if c.get("usfm") == chapter_usfm),
        None,
    )
    if not capitulo:
        raise RuntimeError(f"No se encontró el capítulo {chapter_usfm} en el JSON.")

    texto = soup.get_text("\n")

    lineas = [
        clean(linea)
        for linea in texto.splitlines()
        if clean(linea)
    ]

    candidatos = []

    numero_actual = None
    contenido_actual = []

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

        referencia = (
            f"{nombre} "
            f"{capitulo}:"
            f"{numero_actual}"
        )

        candidatos.append(
            {
                "referencia": referencia,
                "texto": contenido,
                "fuente": url
            }
        )

    for linea in lineas:

        low = linea.lower()

        if low.startswith(
            "actualmente seleccionado"
        ):
            break

        # Bible.com puede entregar:
        #
        # 1 Texto...
        #
        # o:
        #
        # 7¡Tú eres mi refugio!
        #
        # Por eso no exigimos obligatoriamente
        # un espacio después del número.

        match = re.match(
            r"^(\d{1,3})"
            r"(?:\s+|"
            r"(?=[¡«¿A-ZÁÉÍÓÚÑ]))"
            r"(.+)$",
            linea
        )

        if match:

            numero = int(
                match.group(1)
            )

            resto = clean(
                match.group(2)
            )

            if 1 <= numero <= 200:

                guardar_actual()

                numero_actual = numero

                contenido_actual = [
                    resto
                ]

                continue

        if numero_actual is not None:

            if low in {
                "destacar",
                "compartir",
                "copiar",
                "comparar",
            }:
                break

            contenido_actual.append(
                linea
            )

    guardar_actual()

    resultado = []

    vistos = set()
    nombre_libro = libro.get("human", book_usfm)

    for item in candidatos:

        referencia = item[
            "referencia"
        ]

        if referencia in vistos:
    versos = {}
    for item in capitulo.get("items", []):
        if item.get("type") != "verse":
            continue
        texto = " ".join(item.get("lines", [])).strip()
        if not texto:
            continue
        for vn in item.get("verse_numbers", []):
            versos.setdefault(vn, []).append(texto)

        vistos.add(
            referencia
        )

        resultado.append(
            item
        )
    resultado = []
    for vn in sorted(versos):
        resultado.append({
            "referencia": f"{nombre_libro} {numero_capitulo}:{vn}",
            "texto": " ".join(versos[vn]),
            "fuente": BIBLIA_URL,
        })

    if not resultado:

        raise RuntimeError(
            f"No se pudieron extraer "
            f"versículos de {url}"
        )
        raise RuntimeError(f"El capítulo {chapter_usfm} no tiene versículos.")

    return resultado


def obtener_nuevo_versiculo(
    data,
    hoy
):

    historial = data.get(
        "tarjeta_mujer_historial",
        []
    )

    if not isinstance(
        historial,
        list
    ):
def obtener_nuevo_versiculo(biblia, data, hoy):
    historial = data.get("tarjeta_mujer_historial", [])
    if not isinstance(historial, list):
        historial = []
    usados = {item for item in historial if isinstance(item, str)}

    usados = {
        item
        for item in historial
        if isinstance(
            item,
            str
        )
    }

    inicio = dt.date(
        2026,
        1,
        1
    )

    dias = (
        hoy - inicio
    ).days

    if dias < 0:
        dias = 0
    inicio = dt.date(2026, 1, 1)
    dias = max((hoy - inicio).days, 0)

    # Alternamos:
    #
    # Salmos
    # Isaías
    # Juan
    #
    # De esta forma los tres libros
    # participan continuamente.
    # Alternamos: Salmos, Isaías, Juan, Salmos, Isaías, Juan...
    indice_libro = dias % len(LIBROS)
    book_usfm, cantidad_capitulos = LIBROS[indice_libro]
    capitulo = (dias // len(LIBROS)) % cantidad_capitulos + 1

    indice_libro = (
        dias % len(BIBLE_BOOKS)
    )

    codigo, nombre, cantidad_capitulos = (
        BIBLE_BOOKS[indice_libro]
    )

    capitulo = (
        (
            dias
            // len(BIBLE_BOOKS)
        )
        % cantidad_capitulos
    ) + 1

    candidatos = obtener_capitulo(
        codigo,
        nombre,
        capitulo
    )

    nuevos = [
        item
        for item in candidatos
        if item["referencia"]
        not in usados
    ]
    candidatos = extraer_versiculos_capitulo(biblia, book_usfm, capitulo)
    nuevos = [c for c in candidatos if c["referencia"] not in usados]

    if nuevos:
        return nuevos[dias % len(nuevos)]

        indice = (
            dias
            % len(nuevos)
        )

        return nuevos[indice]

    # Si todos los versículos de ese capítulo
    # ya fueron utilizados, buscamos otro
    # capítulo dentro de los tres libros.

    for codigo, nombre, cantidad in (
        BIBLE_BOOKS
    ):

        for numero_capitulo in range(
            1,
            cantidad + 1
        ):

    # Si ya se usaron todos los versículos de ese capítulo puntual,
    # buscamos el primer capítulo (de cualquiera de los 3 libros) que
    # todavía tenga un versículo sin usar.
    for book_usfm, cantidad_capitulos in LIBROS:
        for numero_capitulo in range(1, cantidad_capitulos + 1):
            try:

                candidatos = (
                    obtener_capitulo(
                        codigo,
                        nombre,
                        numero_capitulo
                    )
                )

                candidatos = extraer_versiculos_capitulo(biblia, book_usfm, numero_capitulo)
            except Exception:

                continue

            nuevos = [
                item
                for item in candidatos
                if item["referencia"]
                not in usados
            ]

            nuevos = [c for c in candidatos if c["referencia"] not in usados]
            if nuevos:
                return nuevos[dias % len(nuevos)]

                indice = (
                    dias
                    % len(nuevos)
                )

                return nuevos[indice]

    raise RuntimeError(
        "No se encontró un versículo "
        "nuevo en Salmos, Isaías o Juan."
    )
    raise RuntimeError("No se encontró un versículo nuevo en Salmos, Isaías o Juan.")


def main():

    data = cargar_data()

    hoy = hoy_colombia()

    fecha_iso = hoy.isoformat()

    # -----------------------------------------------------
    # EVITAR CAMBIAR LA TARJETA VARIAS VECES EL MISMO DÍA
    # -----------------------------------------------------

    if (
        data.get(
            "tarjeta_mujer_fecha"
        )
        == fecha_iso
    ):

        tarjeta = data.get(
            "tarjeta_mujer"
        )

        if (
            isinstance(
                tarjeta,
                dict
            )
            and tarjeta.get("texto")
        ):

            print(
                "OK - tarjeta mujer: "
                "ya estaba actualizada para "
                f"{fecha_iso}: "
                f"{tarjeta.get('referencia', '')}"
            )

    # Evitar cambiar la tarjeta varias veces el mismo día
    if data.get("tarjeta_mujer_fecha") == fecha_iso:
        tarjeta = data.get("tarjeta_mujer")
        if isinstance(tarjeta, dict) and tarjeta.get("texto"):
            print(f"OK - tarjeta mujer: ya estaba actualizada para {fecha_iso}: "
                  f"{tarjeta.get('referencia', '')}")
            return

    try:
        biblia = descargar_biblia()
        nuevo = obtener_nuevo_versiculo(biblia, data, hoy)

        nuevo = obtener_nuevo_versiculo(
            data,
            hoy
        )

        # -------------------------------------------------
        # HISTORIAL
        #
        # Solo se guarda la referencia.
        # Nunca se guarda el texto aquí.
        # -------------------------------------------------

        historial = data.get(
            "tarjeta_mujer_historial",
            []
        )

        if not isinstance(
            historial,
            list
        ):
        historial = data.get("tarjeta_mujer_historial", [])
        if not isinstance(historial, list):
            historial = []
        if nuevo["referencia"] not in historial:
            historial.append(nuevo["referencia"])

        if (
            nuevo["referencia"]
            not in historial
        ):

            historial.append(
                nuevo["referencia"]
            )

        data[
            "tarjeta_mujer_historial"
        ] = historial

        data[
            "tarjeta_mujer_fecha"
        ] = fecha_iso

        # -------------------------------------------------
        # TARJETA ACTUAL
        # -------------------------------------------------

        data["tarjeta_mujer_historial"] = historial
        data["tarjeta_mujer_fecha"] = fecha_iso
        data["tarjeta_mujer"] = {

            "referencia":
                nuevo["referencia"],

            "texto":
                nuevo["texto"],

            "fuente":
                nuevo["fuente"],

            "version":
                "RVC"
            "referencia": nuevo["referencia"],
            "texto": nuevo["texto"],
            "fuente": nuevo["fuente"],
            "version": "RVC",
        }

        guardar_data(
            data
        )

        print(
            "OK - tarjeta mujer: "
            f"{nuevo['referencia']}"
        )
        guardar_data(data)
        print(f"OK - tarjeta mujer: {nuevo['referencia']}")

    except Exception as error:

        # Si Bible.com falla,
        # NO borramos la tarjeta anterior.
        # Y NO afectamos los devocionales.

        print(
            "AVISO - tarjeta mujer "
            f"no actualizada: {error}"
        )
        # Si la fuente falla, NO borramos la tarjeta anterior.
        print(f"AVISO - tarjeta mujer no actualizada: {error}")


if __name__ == "__main__":
    main()
    main()
