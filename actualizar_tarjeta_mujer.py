
#!/usr/bin/env python3
"""
Actualiza únicamente la tarjeta bíblica motivacional.

El texto bíblico se obtiene de la fuente de la Biblia RVC.
Las referencias de este archivo sirven solamente para seleccionar
versículos de ánimo, esperanza, paz, confianza y fortaleza.

No modifica En Contacto, Bayless ni Kenneth.
"""

import datetime as dt
import json
from pathlib import Path

import requests
from zoneinfo import ZoneInfo


DATA_FILE = Path("data.json")
TIMEOUT = 60

BIBLIA_URL = (
    "https://mrk214.github.io/snapshots/"
    "es___spa___spa/RVC_vid_146.json"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


# Referencias seleccionadas por sus mensajes de ánimo.
# Aquí NO se escriben los textos de los versículos.
# Los textos se obtienen de la Biblia RVC.

REFERENCIAS_MOTIVACIONALES = [
    # SALMOS: confianza, protección, esperanza y fortaleza
    ("PSA", 23, 1),
    ("PSA", 23, 4),
    ("PSA", 27, 1),
    ("PSA", 27, 14),
    ("PSA", 34, 4),
    ("PSA", 34, 8),
    ("PSA", 37, 4),
    ("PSA", 46, 1),
    ("PSA", 46, 10),
    ("PSA", 55, 22),
    ("PSA", 91, 1),
    ("PSA", 91, 2),
    ("PSA", 91, 4),
    ("PSA", 91, 11),
    ("PSA", 103, 2),
    ("PSA", 118, 6),
    ("PSA", 121, 1),
    ("PSA", 121, 2),
    ("PSA", 126, 5),
    ("PSA", 139, 14),
    ("PSA", 145, 18),
    ("PSA", 147, 3),
    ("PSA", 147, 11),

    # ISAÍAS: consuelo, renovación y presencia de Dios
    ("ISA", 40, 29),
    ("ISA", 40, 31),
    ("ISA", 41, 10),
    ("ISA", 43, 1),
    ("ISA", 43, 2),
    ("ISA", 43, 4),
    ("ISA", 43, 18),
    ("ISA", 46, 4),
    ("ISA", 49, 15),
    ("ISA", 54, 10),
    ("ISA", 58, 11),
    ("ISA", 60, 1),
    ("ISA", 61, 3),
    ("ISA", 66, 13),

    # JUAN: vida, paz, amor y esperanza en Jesús
    ("JHN", 1, 5),
    ("JHN", 6, 35),
    ("JHN", 8, 12),
    ("JHN", 10, 10),
    ("JHN", 10, 27),
    ("JHN", 10, 28),
    ("JHN", 11, 25),
    ("JHN", 14, 1),
    ("JHN", 14, 18),
    ("JHN", 14, 27),
    ("JHN", 15, 5),
    ("JHN", 15, 9),
    ("JHN", 16, 22),
    ("JHN", 16, 33),
]


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

        return data if isinstance(data, dict) else {}

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


def descargar_biblia():
    print(
        "Descargando Biblia RVC desde la fuente bíblica..."
    )

    respuesta = requests.get(
        BIBLIA_URL,
        headers=HEADERS,
        timeout=TIMEOUT
    )

    print(
        f"HTTP {respuesta.status_code} - "
        f"{len(respuesta.content)} bytes"
    )

    respuesta.raise_for_status()

    biblia = respuesta.json()

    if not isinstance(
        biblia.get("books"),
        list
    ):
        raise RuntimeError(
            "La fuente no contiene la lista de libros esperada."
        )

    return biblia


def extraer_versiculos_capitulo(
    biblia,
    codigo,
    numero_capitulo
):
    """
    Reúne las líneas asociadas a cada versículo del capítulo.
    No resume ni reescribe el texto obtenido de la fuente.
    """

    identificador = (
        f"{codigo}.{numero_capitulo}"
    )

    libro = next(
        (
            item
            for item in biblia.get("books", [])
            if item.get("usfm") == codigo
        ),
        None
    )

    if not libro:
        raise RuntimeError(
            f"No se encontró el libro {codigo}."
        )

    capitulo = next(
        (
            item
            for item in libro.get("chapters", [])
            if item.get("usfm") == identificador
        ),
        None
    )

    if not capitulo:
        raise RuntimeError(
            f"No se encontró el capítulo {identificador}."
        )

    nombre_libro = libro.get("human", codigo)

    partes_por_versiculo = {}

    for item in capitulo.get("items", []):

        if item.get("type") != "verse":
            continue

        lineas = [
            str(linea).strip()
            for linea in item.get("lines", [])
            if str(linea).strip()
        ]

        texto = " ".join(lineas).strip()

        if not texto:
            continue

        numeros = item.get("verse_numbers", [])

        if not isinstance(numeros, list):
            numeros = [numeros]

        for numero in numeros:
            try:
                numero = int(numero)
            except (TypeError, ValueError):
                continue

            partes_por_versiculo.setdefault(
                numero,
                []
            ).append(texto)

    resultado = []

    for numero in sorted(partes_por_versiculo):

        partes = []

        for parte in partes_por_versiculo[numero]:
            if parte not in partes:
                partes.append(parte)

        texto = " ".join(partes).strip()

        if not texto:
            continue

        resultado.append({
            "id": (
                codigo,
                numero_capitulo,
                numero
            ),
            "referencia": (
                f"{nombre_libro} "
                f"{numero_capitulo}:{numero}"
            ),
            "texto": texto,
            "fuente": (
                "https://www.bible.com/es/bible/146/"
                f"{codigo}.{numero_capitulo}.RVC"
            ),
        })

    return resultado


def obtener_versiculos_motivacionales(biblia):

    por_id = {}

    capitulos_necesarios = sorted({
        (codigo, capitulo)
        for codigo, capitulo, numero_versiculo
        in REFERENCIAS_MOTIVACIONALES
    })

    for codigo, capitulo in capitulos_necesarios:

        versiculos = extraer_versiculos_capitulo(
            biblia,
            codigo,
            capitulo
        )

        for versiculo in versiculos:
            por_id[versiculo["id"]] = versiculo

    candidatos = []
    faltantes = []

    for referencia_id in REFERENCIAS_MOTIVACIONALES:

        versiculo = por_id.get(
            referencia_id
        )

        if not versiculo:
            faltantes.append(
                referencia_id
            )
            continue

        texto = versiculo["texto"].strip()

        # Evitar textos vacíos o fragmentos demasiado cortos.
        # El texto aceptado se conserva sin resumir ni modificar.
        if len(texto) < 15:
            faltantes.append(
                referencia_id
            )
            continue

        candidatos.append(
            versiculo
        )

    if not candidatos:
        raise RuntimeError(
            "No se pudo obtener ningún versículo motivacional."
        )

    if faltantes:
        print(
            "Aviso: se omitieron "
            f"{len(faltantes)} referencias ausentes o vacías."
        )

    return candidatos


def main():

    data = cargar_data()

    hoy = hoy_colombia()
    fecha_iso = hoy.isoformat()

    # No cambiar el versículo varias veces el mismo día.
    if data.get("tarjeta_mujer_fecha") == fecha_iso:

        tarjeta = data.get(
            "tarjeta_mujer"
        )

        if (
            isinstance(tarjeta, dict)
            and tarjeta.get("texto")
            and tarjeta.get("referencia")
        ):
            print(
                "OK - tarjeta mujer: ya estaba actualizada "
                f"para {fecha_iso}: "
                f"{tarjeta['referencia']}"
            )
            return

    try:

        biblia = descargar_biblia()

        candidatos = obtener_versiculos_motivacionales(
            biblia
        )

        historial = data.get(
            "tarjeta_mujer_historial",
            []
        )

        if not isinstance(historial, list):
            historial = []

        usados = {
            referencia
            for referencia in historial
            if isinstance(referencia, str)
        }

        disponibles = [
            versiculo
            for versiculo in candidatos
            if versiculo["referencia"] not in usados
        ]

        # Cuando se agoten las referencias seleccionadas,
        # comenzar un nuevo ciclo sin salir de los tres libros.
        if not disponibles:
            disponibles = candidatos
            print(
                "Se agotaron las referencias motivacionales. "
                "Comienza un nuevo ciclo."
            )

        inicio = dt.date(2026, 1, 1)

        dias = max(
            (hoy - inicio).days,
            0
        )

        nuevo = disponibles[
            dias % len(disponibles)
        ]

        if nuevo["referencia"] not in historial:
            historial.append(
                nuevo["referencia"]
            )

        data["tarjeta_mujer_historial"] = historial
        data["tarjeta_mujer_fecha"] = fecha_iso

        data["tarjeta_mujer"] = {
            "referencia": nuevo["referencia"],
            "texto": nuevo["texto"],
            "fuente": nuevo["fuente"],
            "version": "RVC",
        }

        guardar_data(data)

        print(
            "OK - tarjeta mujer: "
            f"{nuevo['referencia']}"
        )

    except Exception as error:

        # Si la fuente falla, conservar la tarjeta anterior.
        print(
            "AVISO - tarjeta mujer no actualizada:",
            error
        )


if __name__ == "__main__":
    main()
