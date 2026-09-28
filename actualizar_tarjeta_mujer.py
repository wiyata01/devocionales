#!/usr/bin/env python3

"""
Actualiza únicamente la tarjeta bíblica para mujeres.

IMPORTANTE:
- No contiene textos bíblicos en el código.
- Consulta Bible.com directamente.
- Usa solamente Salmos, Isaías y Juan en RVC.
- Guarda únicamente referencias utilizadas, nunca los textos en el historial.
- Si el workflow se ejecuta varias veces el mismo día, mantiene el mismo versículo.
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

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0.0.0 Safari/537.36 "
        "DevocionalesDiariosBot/5.0"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


BIBLE_BOOKS = [
    ("PSA", "Salmos", 150),
    ("ISA", "Isaías", 66),
    ("JHN", "Juan", 21),
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

    except Exception as error:

        print(
            "Aviso: no se pudo leer data.json:",
            error
        )

        return {}


def guardar_data(data):

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


def obtener_capitulo(
    codigo,
    nombre,
    capitulo
):

    url = (
        f"https://www.bible.com/es/bible/146/"
        f"{codigo}.{capitulo}.RVC"
    )

    print(
        f"Buscando Biblia: "
        f"{nombre} {capitulo} RVC"
    )

    respuesta = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT
    )

    respuesta.raise_for_status()

    soup = BeautifulSoup(
        respuesta.text,
        "html.parser"
    )

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

    if not resultado:

        raise RuntimeError(
            f"No se pudieron extraer "
            f"versículos de {url}"
        )

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
        historial = []

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

    # Alternamos:
    #
    # Salmos
    # Isaías
    # Juan
    #
    # De esta forma los tres libros
    # participan continuamente.

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

    if nuevos:

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

            try:

                candidatos = (
                    obtener_capitulo(
                        codigo,
                        nombre,
                        numero_capitulo
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
                    dias
                    % len(nuevos)
                )

                return nuevos[indice]

    raise RuntimeError(
        "No se encontró un versículo "
        "nuevo en Salmos, Isaías o Juan."
    )


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

            return

    try:

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
            historial = []

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

        data["tarjeta_mujer"] = {

            "referencia":
                nuevo["referencia"],

            "texto":
                nuevo["texto"],

            "fuente":
                nuevo["fuente"],

            "version":
                "RVC"
        }

        guardar_data(
            data
        )

        print(
            "OK - tarjeta mujer: "
            f"{nuevo['referencia']}"
        )

    except Exception as error:

        # Si Bible.com falla,
        # NO borramos la tarjeta anterior.
        # Y NO afectamos los devocionales.

        print(
            "AVISO - tarjeta mujer "
            f"no actualizada: {error}"
        )


if __name__ == "__main__":
    main()