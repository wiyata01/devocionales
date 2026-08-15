# Devocionales Diarios y Radio Cristiana

Sitio estático que muestra los devocionales del día de **En Contacto**,
**Bayless Conley** y **Kenneth Copeland**, más un reproductor de radio
cristiana. El contenido diario se actualiza automáticamente vía
GitHub Actions — no necesitas servidor propio.

## Cómo funciona

```
scrape_devocionales.py  →  data.json  →  index.html lo lee con fetch()
        ↑
   corre 1 vez al día vía GitHub Actions (.github/workflows/update-devocionales.yml)
```

## Publicarlo (primera vez)

1. Crea un repositorio nuevo en GitHub (público o privado, ambos sirven
   para GitHub Pages en cuentas gratuitas si es público; si es privado
   necesitas GitHub Pro).
2. Sube estos archivos tal cual (mantén la carpeta `.github/workflows/`).
3. En el repo: **Settings → Pages → Build and deployment → Source:
   "Deploy from a branch"**, elige la rama `main` y carpeta `/ (root)`.
4. En **Settings → Actions → General → Workflow permissions**, marca
   **"Read and write permissions"** (el workflow necesita poder hacer
   `git push` de `data.json`).
5. Ve a la pestaña **Actions** del repo → selecciona
   "Actualizar devocionales diarios" → **Run workflow** (para probarlo
   ya mismo en vez de esperar al cron).
6. Entra a la URL que te da GitHub Pages (algo como
   `https://tu-usuario.github.io/tu-repo/`) y confirma que carga bien.

Desde ese momento, el workflow corre solo todos los días a la hora
definida en el cron (`0 9 * * *` = 9:00 UTC ≈ 4:00 am Colombia) y hace
commit del `data.json` nuevo. La página siempre lee el archivo más
reciente.

## Probar el scraper en tu computadora (opcional)

```bash
pip install requests beautifulsoup4
python3 scrape_devocionales.py
```

Esto genera/actualiza `data.json` localmente. Ábrelo para revisar que
el texto y el audio salieron bien antes de confiar en el cron.

## Si un sitio cambia de diseño

Cada fuente tiene su propia función en `scrape_devocionales.py`
(`scrape_encontacto`, `scrape_bayless`, `scrape_kenneth`). Si algún día
uno de los tres ministerios rediseña su web y el scraper deja de
encontrar el título, versículo o audio de esa fuente en particular:

1. Corre el script localmente y mira el `FAIL - <fuente>: ...` que
   imprime en la terminal.
2. Abre la página fuente en el navegador, botón derecho → Inspeccionar,
   sobre el elemento que falló (título / versículo / enlace de audio).
3. Ajusta el selector correspondiente en esa función. Las otras dos
   fuentes no se ven afectadas.

El script está escrito para que, si una sola fuente falla un día,
**las otras dos igual se publiquen** (no se cae todo el sitio por un
solo error).
