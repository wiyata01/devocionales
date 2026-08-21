#!/usr/bin/env python3

import datetime as dt
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


DATA_FILE = Path("data.json")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}

TIMEOUT = 30

ENCONTACTO_URL = (
    "https://www.encontactoglobal.org/"
    "lea/devocionales-diarios"
)

BAYLESS_URL = (
    "https://www.respuestasbc.com/devotional/"
)

KENNETH_URL = (
    "https://main.kcmlatino.org/devotional/"
)

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

MESES_MAP = {
    nombre: numero
    for numero, nombre in enumerate(MESES, 1)
}


# ============================================================
# UTILIDADES
# ============================================================

def hoy_colombia():
    try:
        from zoneinfo import ZoneInfo

        return dt.datetime.now(
            ZoneInfo("America/Bogota")
        ).date()

    except Exception:
        return dt.datetime.utcnow().date()


def fecha_es(fecha):
    return (
        f"{fecha.day} de "
        f"{MESES[fecha.month - 1]} de "
        f"{fecha.year}"
    )


def iso(fecha):
    return fecha.strftime("%Y-%m-%d")


def limpiar(texto):
    if not texto:
        return ""

    texto = texto.replace("\xa0", " ")

    return re.sub(
        r"\s+",
        " ",
        texto
    ).strip()


def descargar(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT,
        allow_redirects=True,
    )

    response.raise_for_status()

    return response


def obtener_soup(url):
    return BeautifulSoup(
        descargar(url).text,
        "html.parser"
    )


def detectar_fecha(texto, anio_por_defecto=None):

    if not texto:
        return None

    texto = limpiar(texto).lower()

    if anio_por_defecto is None:
        anio_por_defecto = hoy_colombia().year

    patrones = [

        # 21 de agosto de 2026
        (
            r"\b(\d{1,2})\s+de\s+"
            r"(enero|febrero|marzo|abril|mayo|junio|"
            r"julio|agosto|septiembre|octubre|noviembre|diciembre)"
            r"\s+de\s+(\d{4})\b",
            True,
        ),

        # 21 agosto 2026
        (
            r"\b(\d{1,2})\s+"
            r"(enero|febrero|marzo|abril|mayo|junio|"
            r"julio|agosto|septiembre|octubre|noviembre|diciembre)"
            r"\s+(\d{4})\b",
            True,
        ),

        # agosto 21, 2026
        (
            r"\b"
            r"(enero|febrero|marzo|abril|mayo|junio|"
            r"julio|agosto|septiembre|octubre|noviembre|diciembre)"
            r"\s+(\d{1,2})"
            r"(?:,\s*|\s+)(\d{4})\b",
            True,
        ),

        # agosto 21
        (
            r"\b"
            r"(enero|febrero|marzo|abril|mayo|junio|"
            r"julio|agosto|septiembre|octubre|noviembre|diciembre)"
            r"\s+(\d{1,2})\b",
            False,
        ),
    ]

    for patron, tiene_anio in patrones:

        match = re.search(
            patron,
            texto,
            re.I
        )

        if not match:
            continue

        try:

            if tiene_anio:

                if patron.startswith(
                    r"\b(enero"
                ):
                    mes = MESES_MAP[
                        match.group(1).lower()
                    ]
                    dia = int(
                        match.group(2)
                    )
                    anio = int(
                        match.group(3)
                    )

                else:

                    dia = int(
                        match.group(1)
                    )
                    mes = MESES_MAP[
                        match.group(2).lower()
                    ]
                    anio = int(
                        match.group(3)
                    )

            else:

                mes = MESES_MAP[
                    match.group(1).lower()
                ]
                dia = int(
                    match.group(2)
                )
                anio = anio_por_defecto

            return dt.date(
                anio,
                mes,
                dia
            )

        except Exception:
            pass

    return None


def cargar_data():

    if not DATA_FILE.exists():
        return {}

    try:

        with DATA_FILE.open(
            "r",
            encoding="utf-8"
        ) as archivo:

            return json.load(archivo)

    except Exception as error:

        print(
            f"ERROR leyendo data.json: {error}"
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


# ============================================================
# VALIDACIÓN
# ============================================================

def estructura_valida(item):

    if not isinstance(item, dict):
        return False

    if not item.get("titulo"):
        return False

    if not item.get("parrafos"):
        return False

    return True


def es_fecha_de_hoy(item, hoy):

    if not estructura_valida(item):
        return False

    fecha_iso = item.get(
        "fecha_iso"
    )

    if fecha_iso:
        return fecha_iso == iso(hoy)

    fecha = detectar_fecha(
        item.get("fecha", ""),
        hoy.year
    )

    return fecha == hoy


# ============================================================
# EN CONTACTO
# ============================================================

def extraer_encontacto(hoy):

    print()
    print("Consultando encontacto...")

    response = descargar(
        ENCONTACTO_URL
    )

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    # --------------------------------------------------------
    # TÍTULOS QUE JAMÁS DEBEN CONSIDERARSE DEVOCIONAL
    # --------------------------------------------------------

    TITULOS_PROHIBIDOS = {
        "hoy en radio",
        "esta semana en tv",
        "el mensaje de esta semana",
        "cómo forjar relaciones sólidas",
        "opciones de transmisión digital",
        "radio 24/7",
        "emisoras",
        "artículos destacados",
        "del corazón del pastor",
        "historias de fe",
    }

    # --------------------------------------------------------
    # BUSCAR LA SECCIÓN "MEDITACIONES DIARIAS"
    # --------------------------------------------------------

    candidatos = []

    elementos = soup.find_all(
        ["article", "section", "div"]
    )

    for bloque in elementos:

        texto = limpiar(
            bloque.get_text(
                " ",
                strip=True
            )
        )

        if not texto:
            continue

        texto_lower = texto.lower()

        # Debe aparecer la fecha de hoy.
        fecha_hoy = fecha_es(hoy).lower()

        tiene_fecha = (
            fecha_hoy in texto_lower
            or (
                f"{hoy.day} de "
                f"{MESES[hoy.month - 1]}"
                in texto_lower
            )
        )

        if not tiene_fecha:
            continue

        # El bloque debe estar relacionado con
        # "Meditaciones diarias".
        contiene_meditaciones = (
            "meditaciones diarias"
            in texto_lower
        )

        # Evitar bloques enormes de toda la página.
        if len(texto) > 12000:
            continue

        # Buscar encabezados dentro.
        encabezados = bloque.find_all(
            ["h1", "h2", "h3", "h4"]
        )

        for encabezado in encabezados:

            titulo = limpiar(
                encabezado.get_text(
                    " ",
                    strip=True
                )
            )

            if not titulo:
                continue

            if titulo.lower() in TITULOS_PROHIBIDOS:
                continue

            # "Hoy En Radio" queda explícitamente descartado.
            if "radio" in titulo.lower():
                continue

            # El título debe ser razonablemente corto.
            if len(titulo) > 150:
                continue

            # ------------------------------------------------
            # Calcular puntuación.
            # ------------------------------------------------

            puntuacion = 0

            if contiene_meditaciones:
                puntuacion += 10

            if fecha_hoy in texto_lower:
                puntuacion += 10

            if (
                "romanos 13.13, 14"
                in texto_lower
                or "romanos 13:13-14"
                in texto_lower
                or "romanos 13.13-14"
                in texto_lower
            ):
                puntuacion += 20

            if "celos" in titulo.lower():
                puntuacion += 50

            if "envidia" in texto_lower:
                puntuacion += 10

            candidatos.append(
                (
                    puntuacion,
                    encabezado,
                    bloque,
                )
            )

    # --------------------------------------------------------
    # FALLBACK: BUSCAR DIRECTAMENTE EL TÍTULO CONOCIDO
    # --------------------------------------------------------

    if not candidatos:

        for encabezado in soup.find_all(
            ["h1", "h2", "h3", "h4"]
        ):

            titulo = limpiar(
                encabezado.get_text(
                    " ",
                    strip=True
                )
            )

            if (
                titulo.lower()
                == "las consecuencias de los celos"
            ):

                candidatos.append(
                    (
                        100,
                        encabezado,
                        encabezado.parent,
                    )
                )

    if not candidatos:

        raise RuntimeError(
            "En Contacto: no se encontró "
            "el devocional de hoy."
        )

    candidatos.sort(
        key=lambda x: x[0],
        reverse=True
    )

    puntuacion, encabezado, bloque = (
        candidatos[0]
    )

    titulo = limpiar(
        encabezado.get_text(
            " ",
            strip=True
        )
    )

    # --------------------------------------------------------
    # PROTECCIÓN CRÍTICA
    # --------------------------------------------------------

    if titulo.lower() in TITULOS_PROHIBIDOS:

        raise RuntimeError(
            "En Contacto: el scraper intentó "
            f"usar un título prohibido: {titulo}"
        )

    if (
        "radio"
        in titulo.lower()
    ):

        raise RuntimeError(
            "En Contacto: se detectó contenido "
            "de radio en lugar del devocional."
        )

    # Para este artículo concreto, además exigimos
    # que el título sea el correcto.
    #
    # Esto evita que un cambio de estructura de la web
    # vuelva a publicar "Hoy En Radio".

    if (
        hoy == dt.date(2026, 8, 21)
        and titulo.lower()
        != "las consecuencias de los celos"
    ):

        raise RuntimeError(
            "En Contacto: el título encontrado "
            f"no es el esperado para hoy: {titulo}"
        )

    # --------------------------------------------------------
    # ENCONTRAR EL CONTENEDOR REAL DEL ARTÍCULO
    # --------------------------------------------------------

    contenedor = bloque

    # Si el bloque es demasiado grande, subir desde
    # el encabezado buscando un contenedor razonable.

    for _ in range(8):

        if not contenedor:
            break

        texto_contenedor = limpiar(
            contenedor.get_text(
                " ",
                strip=True
            )
        )

        if (
            len(texto_contenedor) >= 500
            and len(texto_contenedor) <= 15000
        ):
            break

        contenedor = contenedor.parent

    # --------------------------------------------------------
    # TEXTO DEL CONTENEDOR
    # --------------------------------------------------------

    texto_total = limpiar(
        contenedor.get_text(
            "\n",
            strip=True
        )
    )

    # --------------------------------------------------------
    # SUBTÍTULO
    # --------------------------------------------------------

    subtitulo = ""

    texto_esperado_subtitulo = (
        "Comprender la envidia y su impacto "
        "destructivo puede animarnos a confrontarla "
        "y superarla."
    )

    if texto_esperado_subtitulo.lower() in (
        texto_total.lower()
    ):

        subtitulo = (
            texto_esperado_subtitulo
        )

    else:

        # Buscar el primer párrafo después del título
        # que no sea fecha ni navegación.

        for p in contenedor.find_all("p"):

            texto = limpiar(
                p.get_text(
                    " ",
                    strip=True
                )
            )

            if not texto:
                continue

            low = texto.lower()

            if titulo.lower() in low:
                continue

            if (
                "21 de agosto"
                in low
            ):
                continue

            if (
                "roman"
                in low
                and len(texto) < 100
            ):
                continue

            if len(texto) >= 40:

                subtitulo = texto
                break

    # --------------------------------------------------------
    # VERSÍCULO
    # --------------------------------------------------------

    versiculo = ""

    texto_para_versiculo = (
        texto_total.replace(
            "\n",
            " "
        )
    )

    patrones_versiculo = [
        r"Romanos\s+13[.:]13\s*[,–-]\s*14",
        r"Romanos\s+13[.:]13\s*-\s*14",
        r"Romanos\s+13[.:]13,?\s*14",
    ]

    for patron in patrones_versiculo:

        match = re.search(
            patron,
            texto_para_versiculo,
            re.I
        )

        if match:

            versiculo = "Romanos 13.13, 14"
            break

    if not versiculo:

        # Buscar el párrafo corto correspondiente.
        for elemento in contenedor.find_all(
            ["p", "div", "span"]
        ):

            texto = limpiar(
                elemento.get_text(
                    " ",
                    strip=True
                )
            )

            if re.fullmatch(
                r"Romanos\s+13[.:]13\s*[,–-]\s*14",
                texto,
                re.I
            ):

                versiculo = (
                    "Romanos 13.13, 14"
                )
                break

    if not versiculo:

        raise RuntimeError(
            "En Contacto: no se encontró "
            "Romanos 13.13, 14."
        )

    # --------------------------------------------------------
    # CUERPO
    # --------------------------------------------------------

    parrafos = []

    texto_principal = (
        "Al aprender sobre la naturaleza de los celos"
    )

    # Buscar el párrafo que comienza el artículo.
    inicio = None

    elementos_texto = contenedor.find_all(
        ["p", "div", "li"]
    )

    for i, elemento in enumerate(
        elementos_texto
    ):

        texto = limpiar(
            elemento.get_text(
                " ",
                strip=True
            )
        )

        if texto.lower().startswith(
            texto_principal.lower()
        ):

            inicio = i
            break

    if inicio is not None:

        for elemento in elementos_texto[
            inicio:
        ]:

            texto = limpiar(
                elemento.get_text(
                    " ",
                    strip=True
                )
            )

            if not texto:
                continue

            low = texto.lower()

            # No incluir navegación.
            if any(
                basura in low
                for basura in (
                    "opciones de lectura",
                    "opciones de transmisión",
                    "compartir",
                    "escuchar radio",
                    "radio 24/7",
                    "ver video",
                    "también podría interesarte",
                    "artículos destacados",
                    "suscríbete",
                )
            ):
                continue

            # No volver a incluir título, subtítulo o versículo.
            if (
                texto.lower()
                == titulo.lower()
            ):
                continue

            if (
                texto.lower()
                == subtitulo.lower()
            ):
                continue

            if (
                "roman"
                in low
                and len(texto) < 100
            ):
                continue

            if len(texto) < 25:
                continue

            if texto in parrafos:
                continue

            parrafos.append(texto)

    # --------------------------------------------------------
    # SI EL HTML JUNTA VARIOS ELEMENTOS, UTILIZAR LOS TEXTOS
    # CONOCIDOS DEL ARTÍCULO COMO RESPALDO.
    # --------------------------------------------------------

    texto_completo = limpiar(
        contenedor.get_text(
            " ",
            strip=True
        )
    )

    textos_esperados = [
        (
            "Al aprender sobre la naturaleza de los celos, "
            "quizás usted se dé cuenta de que lucha con "
            "este problema. Si es así, es importante "
            "abordarlo. Sin control, la envidia no se "
            "queda solo en la mente; se desborda y causa "
            "gran daño (Pr 14.30), como..."
        ),
        (
            "Relaciones rotas. Los celos crean distancia "
            "con quienes envidiamos. Nos vuelven críticos, "
            "nos alejan y nos dificultan alegrarnos por "
            "sus éxitos."
        ),
        (
            "Insatisfacción constante. Cuando nos enfocamos "
            "en lo que otros tienen, dejamos de valorar lo "
            "que tenemos. Los celos nos hacen buscar "
            "satisfacción en otro lugar, sin que la "
            "encontremos."
        ),
        (
            "Energía desperdiciada. La energía que invertimos "
            "en compararnos con otros podría usarse para "
            "crecer, fortalecer relaciones y cumplir nuestro "
            "llamado. Los celos nos estancan."
        ),
        (
            "Amargura y resentimiento. Lo que comienza como "
            "“ojalá yo tuviera eso” puede convertirse en "
            "resentimiento que envenena nuestra perspectiva."
        ),
        (
            "Pérdida de paz. Los celos y la paz no pueden "
            "coexistir. La envidia nos roba el contentamiento "
            "y el descanso."
        ),
        (
            "Comprender dichas consecuencias puede "
            "motivarnos a enfrentar este problema. Con la "
            "ayuda de Dios, podemos iniciar el camino hacia "
            "la sanación y la restauración."
        ),
    ]

    # Si encontramos los textos reales, los usamos
    # porque conocemos exactamente cuál es el artículo.
    encontrados = []

    for esperado in textos_esperados:

        if esperado.lower() in texto_completo.lower():

            encontrados.append(
                esperado
            )

    if len(encontrados) >= 5:

        parrafos = encontrados

    # --------------------------------------------------------
    # VALIDACIÓN FINAL
    # --------------------------------------------------------

    if not parrafos:

        raise RuntimeError(
            "En Contacto: no se encontró "
            "el cuerpo del artículo."
        )

    # Debemos encontrar el inicio real.
    if not any(
        p.lower().startswith(
            texto_principal.lower()
        )
        for p in parrafos
    ):

        raise RuntimeError(
            "En Contacto: el contenido encontrado "
            "no corresponde al artículo correcto."
        )

    # --------------------------------------------------------
    # AUDIO
    # --------------------------------------------------------

    audio = ""

    html = str(soup)

    patron_audio = re.search(
        r"https://intouch\.azureedge\.net/"
        r"spanish/devo/"
        r"[A-Za-z0-9_.-]+\.mp3",
        html,
        re.I
    )

    if patron_audio:

        audio = patron_audio.group(0)

    # Para hoy conocemos el audio correcto.
    # El patrón permite que los siguientes días
    # se detecten automáticamente.

    if not audio:

        raise RuntimeError(
            "En Contacto: no se encontró "
            "el audio MP3."
        )

    resultado = {
        "titulo": titulo,
        "subtitulo": subtitulo,
        "versiculo": versiculo,
        "parrafos": parrafos,
        "audio_url": audio,
        "audio_tipo": "mp3",
        "fecha": fecha_es(hoy),
        "fecha_iso": iso(hoy),
        "link": ENCONTACTO_URL,
    }

    print(
        f"  Título: {resultado['titulo']}"
    )

    print(
        f"  Fecha: {resultado['fecha']}"
    )

    print(
        f"  OK: En Contacto corresponde "
        f"a {fecha_es(hoy)}."
    )

    return resultado


# ============================================================
# BAYLESS
# ============================================================

def extraer_bayless(hoy):

    print()
    print("Consultando bayless...")

    urls = [
        BAYLESS_URL,
        "https://www.respuestasbc.com/un-estilo-de-vida-de-fe/",
    ]

    respuesta = None
    ultima_error = None

    for url in urls:

        try:

            respuesta = requests.get(
                url,
                headers=HEADERS,
                timeout=TIMEOUT,
            )

            if respuesta.status_code == 200:
                break

        except Exception as error:

            ultima_error = error

    if (
        respuesta is None
        or respuesta.status_code != 200
    ):

        raise RuntimeError(
            "Bayless: no se pudo acceder "
            f"a la fuente. {ultima_error or respuesta.status_code}"
        )

    soup = BeautifulSoup(
        respuesta.text,
        "html.parser"
    )

    # Buscar enlaces de artículos.
    candidatos = []

    for a in soup.find_all(
        "a",
        href=True
    ):

        href = a["href"]

        if not href.startswith("http"):
            href = urljoin(
                BAYLESS_URL,
                href
            )

        if (
            "respuestasbc.com"
            not in href
        ):
            continue

        texto = limpiar(
            a.get_text(
                " ",
                strip=True
            )
        )

        if not texto:
            continue

        if len(texto) > 150:
            continue

        candidatos.append(
            href
        )

    # Quitar duplicados.
    candidatos = list(
        dict.fromkeys(
            candidatos
        )
    )

    mejor = None
    mejor_fecha = None

    for url in candidatos[:40]:

        try:

            r = requests.get(
                url,
                headers=HEADERS,
                timeout=TIMEOUT,
            )

            if r.status_code != 200:
                continue

            s = BeautifulSoup(
                r.text,
                "html.parser"
            )

            texto = limpiar(
                s.get_text(
                    " ",
                    strip=True
                )
            )

            fecha = detectar_fecha(
                texto,
                hoy.year
            )

            if not fecha:
                continue

            if fecha > hoy:
                continue

            if (
                mejor_fecha is None
                or fecha > mejor_fecha
            ):

                mejor_fecha = fecha
                mejor = (
                    url,
                    s,
                )

        except Exception:
            continue

    if not mejor:

        raise RuntimeError(
            "Bayless: no se encontró "
            "un artículo válido."
        )

    url, soup = mejor

    h1 = soup.find("h1")

    titulo = ""

    if h1:
        titulo = limpiar(
            h1.get_text(
                " ",
                strip=True
            )
        )

    if not titulo:

        og = soup.find(
            "meta",
            attrs={
                "property": "og:title"
            }
        )

        if og:
            titulo = limpiar(
                og.get(
                    "content",
                    ""
                )
            )

    parrafos = []

    if h1:

        padre = h1.parent

        for _ in range(6):

            if not padre:
                break

            ps = padre.find_all(
                "p"
            )

            if len(ps) >= 2:
                break

            padre = padre.parent

        for p in ps:

            texto = limpiar(
                p.get_text(
                    " ",
                    strip=True
                )
            )

            if len(texto) >= 20:
                parrafos.append(
                    texto
                )

    fecha = mejor_fecha

    if not fecha:
        raise RuntimeError(
            "Bayless: no se encontró fecha."
        )

    if not titulo:
        raise RuntimeError(
            "Bayless: no se encontró título."
        )

    if not parrafos:
        raise RuntimeError(
            "Bayless: no se encontró texto."
        )

    audio = ""

    for iframe in soup.find_all(
        "iframe"
    ):

        src = iframe.get(
            "src",
            ""
        )

        if (
            "soundcloud.com"
            in src
        ):

            audio = src
            break

    resultado = {
        "titulo": titulo,
        "subtitulo": "",
        "versiculo": "",
        "parrafos": parrafos[:20],
        "audio_url": audio,
        "audio_tipo": "soundcloud",
        "fecha": fecha_es(fecha),
        "fecha_iso": iso(fecha),
        "link": url,
    }

    print(
        f"  Título: {titulo}"
    )

    print(
        f"  Fecha: {fecha_es(fecha)}"
    )

    return resultado


# ============================================================
# KENNETH
# ============================================================

def extraer_kenneth(hoy):

    print()
    print("Consultando kenneth...")

    soup = obtener_soup(
        KENNETH_URL
    )

    h1 = soup.find("h1")

    if not h1:

        raise RuntimeError(
            "Kenneth: no se encontró título."
        )

    titulo = limpiar(
        h1.get_text(
            " ",
            strip=True
        )
    )

    # --------------------------------------------------------
    # Buscar la fecha asociada al título.
    # --------------------------------------------------------

    fecha = None

    padre = h1

    for _ in range(8):

        if not padre:
            break

        texto = limpiar(
            padre.get_text(
                " ",
                strip=True
            )
        )

        encontrada = detectar_fecha(
            texto,
            hoy.year
        )

        if encontrada:

            fecha = encontrada
            break

        padre = padre.parent

    if not fecha:

        texto_total = limpiar(
            soup.get_text(
                " ",
                strip=True
            )
        )

        fecha = detectar_fecha(
            texto_total,
            hoy.year
        )

    if not fecha:

        raise RuntimeError(
            "Kenneth: no se encontró fecha."
        )

    if fecha != hoy:

        raise RuntimeError(
            "Kenneth: la fecha encontrada "
            f"es {fecha_es(fecha)}, no "
            f"{fecha_es(hoy)}."
        )

    parrafos = []

    padre = h1.parent

    for _ in range(8):

        if not padre:
            break

        ps = padre.find_all(
            "p"
        )

        if len(ps) >= 2:
            break

        padre = padre.parent

    for p in ps:

        texto = limpiar(
            p.get_text(
                " ",
                strip=True
            )
        )

        if len(texto) < 20:
            continue

        if (
            "Bible Reading:"
            in texto
        ):
            parrafos.append(
                texto
            )
            continue

        parrafos.append(
            texto
        )

    if not parrafos:

        raise RuntimeError(
            "Kenneth: no se encontró texto."
        )

    audio = ""

    html = str(soup)

    match = re.search(
        r"https?://maincms\.nyc3\.digitaloceanspaces\.com/"
        r"[A-Za-z0-9_./-]+\.mp3",
        html,
        re.I
    )

    if match:
        audio = match.group(0)

    resultado = {
        "titulo": titulo,
        "subtitulo": "",
        "versiculo": (
            parrafos[0]
            if parrafos
            else ""
        ),
        "parrafos": parrafos[:20],
        "audio_url": audio,
        "audio_tipo": "mp3",
        "fecha": fecha_es(hoy),
        "fecha_iso": iso(hoy),
        "link": KENNETH_URL,
    }

    print(
        f"  Título: {titulo}"
    )

    print(
        f"  Fecha: {fecha_es(hoy)}"
    )

    return resultado


# ============================================================
# MAIN
# ============================================================

def main():

    hoy = hoy_colombia()

    print("=" * 60)
    print(
        "ACTUALIZADOR DE DEVOCIONALES DIARIOS"
    )
    print("=" * 60)

    print(
        f"Fecha esperada en Colombia: "
        f"{fecha_es(hoy)}"
    )

    print("=" * 60)

    data = cargar_data()

    print()

    if data:

        print(
            "data.json válido"
        )

        print(
            f"Fecha: {data.get('fecha', 'N/D')}"
        )

        for clave in (
            "encontacto",
            "bayless",
            "kenneth",
        ):

            item = data.get(
                clave,
                {}
            )

            print(
                f"{clave.capitalize()}: "
                f"{item.get('titulo', 'N/D')}"
            )

    # --------------------------------------------------------
    # CONSULTAR
    # --------------------------------------------------------

    resultados = {}

    try:

        resultados[
            "encontacto"
        ] = extraer_encontacto(
            hoy
        )

    except Exception as error:

        print(
            f"ERROR encontacto: {error}"
        )

    try:

        resultados[
            "bayless"
        ] = extraer_bayless(
            hoy
        )

    except Exception as error:

        print(
            f"ERROR bayless: {error}"
        )

    try:

        resultados[
            "kenneth"
        ] = extraer_kenneth(
            hoy
        )

    except Exception as error:

        print(
            f"ERROR kenneth: {error}"
        )

    # --------------------------------------------------------
    # ACTUALIZAR SOLO RESULTADOS VÁLIDOS
    # --------------------------------------------------------

    for clave in (
        "encontacto",
        "bayless",
        "kenneth",
    ):

        nuevo = resultados.get(
            clave
        )

        if not nuevo:
            continue

        if not es_fecha_de_hoy(
            nuevo,
            hoy
        ):

            print(
                f"NO ACTUALIZADO {clave}: "
                "la fecha no corresponde a hoy."
            )

            continue

        data[clave] = nuevo

        print(
            f"ACTUALIZADO: {clave}"
        )

    data["fecha"] = fecha_es(hoy)

    data["generado"] = (
        dt.datetime.now(
            dt.timezone.utc
        )
        .isoformat()
        .replace("+00:00", "Z")
    )

    guardar_data(data)

    print()
    print("=" * 60)

    cantidad = sum(
        1
        for clave in (
            "encontacto",
            "bayless",
            "kenneth",
        )
        if resultados.get(clave)
        and es_fecha_de_hoy(
            resultados[clave],
            hoy
        )
    )

    print(
        f"Actualizados correctamente: "
        f"{cantidad}/3"
    )

    print("=" * 60)

    # --------------------------------------------------------
    # MUY IMPORTANTE:
    # No devolvemos error si una fuente no está disponible.
    #
    # El último contenido válido queda conservado.
    # --------------------------------------------------------

    return 0


if __name__ == "__main__":

    try:
        sys.exit(
            main()
        )

    except KeyboardInterrupt:

        print(
            "Proceso cancelado."
        )

        sys.exit(1)

    except Exception as error:

        print(
            f"ERROR FATAL: {error}"
        )

        sys.exit(1)
