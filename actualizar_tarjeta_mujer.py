#!/usr/bin/env python3

"""
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
from pathlib import Path

import requests
from zoneinfo import ZoneInfo


DATA_FILE = Path("data.json")
TIMEOUT = 60

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}

# JSON estático con la Biblia RVC completa (español). Publicado vía
# GitHub Pages por https://github.com/mrk214/snapshots
BIBLIA_URL = "https://mrk214.github.io/snapshots/es___spa___spa/RVC_vid_146.json"

# (book_usfm, cantidad_de_capitulos) - alternamos entre los tres libros
LIBROS = [
    ("PSA", 150),  # Salmos
    ("ISA", 66),   # Isaías
    ("JHN", 21),   # Juan
]


def hoy_colombia():
    return dt.datetime.now(ZoneInfo("America/Bogota")).date()


def cargar_data():
    if not DATA_FILE.exists():
        return {}
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as error:
        print("Aviso: no se pudo leer data.json:", error)
        return {}


def guardar_data(data):
    with DATA_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def descargar_biblia():
    print(f"Descargando Biblia RVC desde: {BIBLIA_URL}")
    r = requests.get(BIBLIA_URL, headers=HEADERS, timeout=TIMEOUT)
    print(f"  HTTP {r.status_code} - {len(r.content)} bytes")
    r.raise_for_status()
    return r.json()


def extraer_versiculos_capitulo(biblia, book_usfm, numero_capitulo):
    """Devuelve una lista de {referencia, texto} para cada versículo de
    ese capítulo, usando el JSON completo ya descargado.

    NOTA: el JSON de producción (mrk214/snapshots) usa las llaves "usfm"
    y "human" tanto en libros como en capítulos (no "book_usfm"/"name"
    como documenta el types.ts de ese proyecto, que describe el esquema
    de desarrollo, no el de producción). Ya verificado contra el archivo
    real.
    """

    chapter_usfm = f"{book_usfm}.{numero_capitulo}"

    libro = next(
        (b for b in biblia.get("books", []) if b.get("usfm") == book_usfm),
        None,
    )
    if not libro:
        raise RuntimeError(f"No se encontró el libro {book_usfm} en el JSON.")

    capitulo = next(
        (c for c in libro.get("chapters", []) if c.get("usfm") == chapter_usfm),
        None,
    )
    if not capitulo:
        raise RuntimeError(f"No se encontró el capítulo {chapter_usfm} en el JSON.")

    nombre_libro = libro.get("human", book_usfm)

    versos = {}
    for item in capitulo.get("items", []):
        if item.get("type") != "verse":
            continue
        texto = " ".join(item.get("lines", [])).strip()
        if not texto:
            continue
        for vn in item.get("verse_numbers", []):
            versos.setdefault(vn, []).append(texto)

    resultado = []
    for vn in sorted(versos):
        resultado.append({
            "referencia": f"{nombre_libro} {numero_capitulo}:{vn}",
            "texto": " ".join(versos[vn]),
            "fuente": BIBLIA_URL,
        })

    if not resultado:
        raise RuntimeError(f"El capítulo {chapter_usfm} no tiene versículos.")

    return resultado


def obtener_nuevo_versiculo(biblia, data, hoy):
    historial = data.get("tarjeta_mujer_historial", [])
    if not isinstance(historial, list):
        historial = []
    usados = {item for item in historial if isinstance(item, str)}

    inicio = dt.date(2026, 1, 1)
    dias = max((hoy - inicio).days, 0)

    # Alternamos: Salmos, Isaías, Juan, Salmos, Isaías, Juan...
    indice_libro = dias % len(LIBROS)
    book_usfm, cantidad_capitulos = LIBROS[indice_libro]
    capitulo = (dias // len(LIBROS)) % cantidad_capitulos + 1

    candidatos = extraer_versiculos_capitulo(biblia, book_usfm, capitulo)
    nuevos = [c for c in candidatos if c["referencia"] not in usados]

    if nuevos:
        return nuevos[dias % len(nuevos)]

    # Si ya se usaron todos los versículos de ese capítulo puntual,
    # buscamos el primer capítulo (de cualquiera de los 3 libros) que
    # todavía tenga un versículo sin usar.
    for book_usfm, cantidad_capitulos in LIBROS:
        for numero_capitulo in range(1, cantidad_capitulos + 1):
            try:
                candidatos = extraer_versiculos_capitulo(biblia, book_usfm, numero_capitulo)
            except Exception:
                continue
            nuevos = [c for c in candidatos if c["referencia"] not in usados]
            if nuevos:
                return nuevos[dias % len(nuevos)]

    raise RuntimeError("No se encontró un versículo nuevo en Salmos, Isaías o Juan.")


def main():
    data = cargar_data()
    hoy = hoy_colombia()
    fecha_iso = hoy.isoformat()

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

        historial = data.get("tarjeta_mujer_historial", [])
        if not isinstance(historial, list):
            historial = []
        if nuevo["referencia"] not in historial:
            historial.append(nuevo["referencia"])

        data["tarjeta_mujer_historial"] = historial
        data["tarjeta_mujer_fecha"] = fecha_iso
        data["tarjeta_mujer"] = {
            "referencia": nuevo["referencia"],
            "texto": nuevo["texto"],
            "fuente": nuevo["fuente"],
            "version": "RVC",
        }

        guardar_data(data)
        print(f"OK - tarjeta mujer: {nuevo['referencia']}")

    except Exception as error:
        # Si la fuente falla, NO borramos la tarjeta anterior.
        print(f"AVISO - tarjeta mujer no actualizada: {error}")


if __name__ == "__main__":
    main()
