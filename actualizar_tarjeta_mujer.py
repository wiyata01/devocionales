
#!/usr/bin/env python3
"""
Actualiza únicamente la tarjeta bíblica motivacional para mujeres.

Fuente: Biblia Reina-Valera Contemporánea (RVC).
Los textos se descargan del JSON de la Biblia.
No se escriben versículos manualmente en este archivo.

Solo utiliza Salmos, Isaías y Juan.
No modifica los tres devocionales.
"""

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


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
    "Accept-Language": "es-ES,es;q=0.9",
}


# Referencias seleccionadas por su mensaje de:
# esperanza, fortaleza, paz, confianza, consuelo y amor.
#
# El texto de cada versículo NO está escrito aquí.
# Se obtiene directamente de la Biblia RVC.

REFERENCIAS_MOTIVACIONALES = [
    # SALMOS
    ("PSA", 23, 1),
    ("PSA", 23, 4),
    ("PSA", 27, 1),
    ("PSA", 27, 4),
    ("PSA", 27, 14),
    ("PSA", 34, 4),
    ("PSA", 34, 8),
    ("PSA", 34, 17),
    ("PSA", 37, 4),
    ("PSA", 37, 5),
    ("PSA", 37, 23),
    ("PSA", 40, 1),
    ("PSA", 46, 1),
    ("PSA", 46, 10),
    ("PSA", 55, 22),
    ("PSA", 62, 1),
    ("PSA", 62, 5),
    ("PSA", 91, 1),
    ("PSA", 91, 2),
    ("PSA", 91, 4),
    ("PSA", 103, 2),
    ("PSA", 118, 6),
    ("PSA", 121, 1),
    ("PSA", 121, 2),
    ("PSA", 126, 5),
    ("PSA", 139, 14),
    ("PSA", 145, 18),
    ("PSA", 147, 3),

    # ISAÍAS
    ("ISA", 40, 29),
    ("ISA", 40, 31),
    ("ISA", 41, 10),
    ("ISA", 43, 1),
    ("ISA", 43, 2),
    ("ISA", 43, 4),
    ("ISA", 46, 4),
    ("ISA", 49, 15),
    ("ISA", 54, 10),
    ("ISA", 58, 11),
    ("ISA", 60, 1),
    ("ISA", 61, 3),
    ("ISA", 66, 13),

    # JUAN
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


def limpiar_texto(texto):
    """Normaliza espacios sin eliminar palabras ni frases."""
    return " ".join(str(texto).split()).strip()


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
        print("Aviso: no se pudo leer data.json:", error)
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
    print("Descargando Biblia RVC...")

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

    if not isinstance(biblia.get("books"), list):
        raise RuntimeError(
            "La fuente bíblica no contiene la lista de libros esperada."
        )

    return biblia


def extraer_capitulo(biblia, codigo, numero_capitulo):
    """
    Extrae el texto completo de cada versículo del capítulo.

    Une todas las líneas asociadas al mismo número de versículo.
    Omite elementos que agrupan varios números, porque no es seguro
    atribuir el texto completo a cada número por separado.
    """

    identificador = f"{codigo}.{numero_capitulo}"

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

        numeros = item.get("verse_numbers", [])

        if not isinstance(numeros, list):
            numeros = [numeros]

        # No duplicar un texto agrupado bajo varios números.
        if len(numeros) != 1:
            continue

        try:
            numero = int(numeros[0])
        except (TypeError, ValueError):
            continue

        lineas = item.get("lines", [])

        if not isinstance(lineas, list):
            lineas = [lineas]

        texto = limpiar_texto(
            " ".join(
                str(linea)
                for linea in lineas
                if str(linea).strip()
            )
        )

        if not texto:
            continue

        partes_por_versiculo.setdefault(
            numero,
            []
        ).append(texto)

    resultado = {}

    for numero, partes in partes_por_versiculo.items():

        # Conservar todas las partes, sin repetir líneas idénticas.
        partes_unicas = []

        for parte in partes:
            if parte not in partes_unicas:
                partes_unicas.append(parte)

        texto_completo = limpiar_texto(
            " ".join(partes_unicas)
        )

        # Evitar fragmentos demasiado cortos.
        if len(texto_completo) < 20:
            continue

        referencia = (
            f"{nombre_libro} "
            f"{numero_capitulo}:{numero}"
        )

        resultado[(codigo, numero_capitulo, numero)] = {
            "referencia": referencia,
            "texto": texto_completo,
            "fuente": (
                "https://www.bible.com/es/bible/146/"
                f"{codigo}.{numero_capitulo}.RVC"
            ),
        }

    return resultado


def obtener_versiculos_motivacionales(biblia):
    """Obtiene únicamente las referencias seleccionadas."""

    capitulos = sorted({
        (codigo, capitulo)
        for codigo, capitulo, numero
        in REFERENCIAS_MOTIVACIONALES
    })

    versiculos_por_id = {}

    for codigo, capitulo in capitulos:

        extraidos = extraer_capitulo(
            biblia,
            codigo,
            capitulo
        )

        versiculos_por_id.update(extraidos)

    candidatos = []
    referencias_ausentes = []

    for identificador in REFERENCIAS_MOTIVACIONALES:

        versiculo = versiculos_por_id.get(
            identificador
        )

        if not versiculo:
            referencias_ausentes.append(
                identificador
            )
            continue

        candidatos.append(versiculo)

    if not candidatos:
        raise RuntimeError(
            "No se pudo obtener ningún versículo completo "
            "de la selección motivacional."
        )

    if referencias_ausentes:
        print(
            "Aviso: se omitieron "
            f"{len(referencias_ausentes)} referencias "
            "que no pudieron extraerse completas."
        )

    print(
        f"Versículos motivacionales disponibles: "
        f"{len(candidatos)}"
    )

    return candidatos


def seleccionar_versiculo(candidatos, historial, hoy):
    """Selecciona una referencia que todavía no se haya utilizado."""

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

    if not disponibles:
        print(
            "Se agotaron las referencias. "
            "Comienza un nuevo ciclo."
        )
        disponibles = candidatos
        historial.clear()

    inicio = dt.date(2026, 1, 1)

    dias = max(
        (hoy - inicio).days,
        0
    )

    indice = dias % len(disponibles)

    return disponibles[indice]


def main():
    data = cargar_data()

    hoy = hoy_colombia()
    fecha_iso = hoy.isoformat()

    # No cambiar el versículo más de una vez al día.
    if data.get("tarjeta_mujer_fecha") == fecha_iso:

        tarjeta = data.get("tarjeta_mujer")

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

        nuevo = seleccionar_versiculo(
            candidatos,
            historial,
            hoy
        )

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
            "OK - tarjeta mujer actualizada: "
            f"{nuevo['referencia']}"
        )

        print(
            f"Texto completo obtenido: {len(nuevo['texto'])} caracteres."
        )

    except Exception as error:
        # No borrar ni reemplazar la tarjeta anterior si falla la fuente.
        print(
            "AVISO - tarjeta mujer no actualizada:",
            error
        )


if __name__ == "__main__":
    main()
