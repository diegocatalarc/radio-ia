# Radio IA

Podcast privado y diario, en español, sobre inteligencia artificial y su impacto económico.
Cada madrugada un flujo de GitHub Actions lee fuentes RSS, elige las historias nuevas, le pide a
Claude un guion, lo convierte en audio (OpenAI o ElevenLabs) y publica un feed de podcast en
GitHub Pages. Lo escuchas suscribiéndote al feed en tu app de podcasts.

## Cómo funciona (resumen)

1. `python -m radio.run` descarga las noticias de las últimas 36 horas (`feeds` en `config.toml`),
   descarta las ya usadas en los últimos 14 días y se queda con un máximo de `max_stories`.
2. Si hay menos de 2 historias nuevas no publica nada (código de salida 2; el flujo lo marca con un
   aviso, no como fallo).
3. Claude escribe el guion, el proveedor de voz genera el MP3 y se actualizan
   `site/episodes/episodio-AAAA-MM-DD.mp3`, `site/episodes.json` y `site/feed.xml`.
4. El flujo `.github/workflows/daily.yml` corre a las 05:00 UTC (≈02:00 en Chile con horario de
   verano) y de nuevo a las 06:00 UTC como respaldo: toda ejecución programada no hace nada si el episodio de hoy ya existe.
   También puedes lanzarlo a mano (`workflow_dispatch`).
5. Un fallo real (código 1) hace fallar el job y GitHub te envía un correo.

### Dónde se guardan los datos

El sitio (`site/`) y `state.json` (historias usadas y correcciones pendientes) se guardan en la rama
**`gh-pages`**, la misma que sirve GitHub Pages. Cada ejecución clona esa rama, genera el episodio,
borra los MP3 que el feed ya no referencia (el feed conserva 60 episodios) y hace `push` con el
`GITHUB_TOKEN` del propio flujo. Se eligió porque no necesita tokens extra, funciona con un
repositorio público y una sola rama hace de almacenamiento y de publicación. `main` solo tiene el
código, así que su historial no se llena de MP3. Como `gh-pages` sí acumula commits con audio,
puedes reiniciar su historial cuando quieras (ver "Mantenimiento").

## Puesta en marcha (una sola vez)

1. **Crea un repositorio público** en GitHub (por ejemplo `radio-ia`) y sube este código a `main`.
2. **Edita `config.toml`**: cambia `site_url` por `https://<tu-usuario>.github.io/<nombre-del-repo>`
   (sin barra final) y haz commit.
3. **Añade los secretos** en *Settings > Secrets and variables > Actions > New repository secret*:
   - `ANTHROPIC_API_KEY` (siempre)
   - `OPENAI_API_KEY` si `tts_provider = "openai"`
   - `ELEVENLABS_API_KEY` si `tts_provider = "elevenlabs"` (puedes crear ambos; solo se usa el configurado)
4. **Lanza el flujo una vez a mano**: pestaña *Actions > Episodio diario > Run workflow*. En la
   primera ejecución crea la rama `gh-pages` con el primer episodio.
5. **Activa Pages**: *Settings > Pages > Source: Deploy from a branch > Branch `gh-pages`, carpeta
   `/ (root)`*. En un minuto o dos el feed estará en
   `https://<tu-usuario>.github.io/<nombre-del-repo>/feed.xml`.
6. **Suscríbete** en tu app de podcasts con esa URL (en Apple Podcasts: *Archivo > Seguir un
   programa por URL*; en Pocket Casts, Overcast, AntennaPod etc. hay una opción equivalente).

> El feed es **público pero no listado**: no aparece en directorios de podcasts, pero cualquiera
> que conozca la URL puede escucharlo. No compartas el enlace si quieres que siga siendo privado.

## Elegir la voz

```bash
python -m venv .venv && .venv/bin/pip install -e .
OPENAI_API_KEY=... ELEVENLABS_API_KEY=... .venv/bin/python scripts/make_voice_samples.py
```

Genera muestras en `samples/<proveedor>-<voz>.mp3`. Con `SAMPLE_OPENAI_VOICES="alloy,nova"` o
`SAMPLE_ELEVENLABS_VOICES="<voice_id>"` eliges qué voces probar. Cuando decidas, pon en
`config.toml` el `tts_provider` y la `tts_voice` (el nombre en OpenAI, el `voice_id` en ElevenLabs).

## Cambiar la zona horaria (y el cron)

La zona de `config.toml` (`timezone`) define qué es "hoy" y la fecha de cada episodio. El cron de
GitHub Actions **siempre va en UTC** y no entiende de horario de verano, así que hay que calcularlo:

- Chile alterna entre UTC-4 (invierno) y UTC-3 (verano). `0 5 * * *` UTC son las 02:00 con UTC-3 y
  las 01:00 con UTC-4; en ambos casos cae de madrugada y en el día local correcto, así que no hace
  falta tocarlo por el cambio de hora.
- Si te mudas, elige la hora local deseada y súmale el desfase: hora UTC = hora local − desfase
  (con UTC-3, 02:00 local = 05:00 UTC; con UTC+1, 02:00 local = 01:00 UTC). El respaldo es
  siempre una hora después. Cuida que la hora UTC elegida siga cayendo **el mismo día local** que
  esperas para el episodio.
- Después del **7 de diciembre de 2026**, cuando estés en tu nueva zona, actualiza dos cosas:
  `timezone` en `config.toml` (por ejemplo `Europe/Madrid`) y las dos líneas `cron` de
  `.github/workflows/daily.yml`. No hay nada más que tocar: toda ejecución programada
  (principal o respaldo) comprueba si el episodio de hoy ya existe y, si es así, no hace nada.
- GitHub puede retrasar los crons varios minutos en horas de alta carga; es normal.

## Añadir una corrección

Si un episodio dijo algo erróneo, añade una corrección; el siguiente episodio la mencionará una
sola vez. Los datos viven en `gh-pages`:

```bash
git clone --branch gh-pages https://github.com/<tu-usuario>/<repo>.git datos
cd datos
python -m radio.correct "En el episodio del 12 dijimos 5 %; la cifra correcta es 3 %."
git add state.json && git commit -m "Corrección" && git push origin gh-pages
```

(`radio.correct` necesita el proyecto instalado con `pip install -e .` en tu copia de `main`, o
ejecutarse desde ella con `--state ../datos/state.json`.) El commit de `state.json` lo haces tú a
mano; el flujo no se ejecuta con ese push, así que la corrección se usa en la próxima ejecución.

## Añadir fuentes

Edita la lista `feeds` de `config.toml` y añade la URL del RSS/Atom. Haz commit en `main`; se usa
desde la siguiente ejecución. Quita o ajusta `max_stories` si quieres episodios más cortos o largos.

## Mantenimiento

- Ejecución manual: *Actions > Episodio diario > Run workflow*. Si ya hay episodio de hoy, se
  regenera y reemplaza al anterior.
- Si `gh-pages` crece demasiado, puedes recrearla desde cero conservando el contenido actual
  (`git checkout --orphan nueva && git commit && git push -f origin nueva:gh-pages`).
- Pruebas: `.venv/bin/python -m pytest`.
