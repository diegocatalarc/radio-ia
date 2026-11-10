# Radio IA

Todo el flujo (LLM y voz) funciona con **una sola clave de API: `OPENROUTER_API_KEY`**.

Podcast privado y diario, en español, sobre inteligencia artificial y su impacto económico.
Cada madrugada un flujo de GitHub Actions lee fuentes RSS, elige las historias nuevas, le pide a
un LLM un guion, lo convierte en audio y publica un feed de podcast en
GitHub Pages. Lo escuchas suscribiéndote al feed en tu app de podcasts.

## Cómo funciona (resumen)

1. `python -m radio.run` descarga las noticias de las últimas 36 horas (`feeds` en `config.toml`),
   descarta las ya usadas en los últimos 14 días y arma un pool de hasta `pool_size` (30) titulares
   con resumen, repartidos entre fuentes. Una primera llamada barata a Claude elige las 4 a
   `max_stories` (6) más relevantes; solo de esas se descargan los artículos completos.
2. Si quedan menos de 2 historias no publica nada (código de salida 2) y **el flujo falla** con un
   `::error::` ("no episode today: fewer than 2 stories"): el correo de "run failed" de GitHub es
   tu aviso de que hoy no hay episodio. Si más de la mitad de los feeds fallan, el registro lo
   marca con una línea `ERROR` y la cuenta de feeds caídos (error o 0 entradas).
3. Claude escribe el guion, el proveedor de voz genera el MP3 y se actualizan
   `site/episodes/episodio-AAAA-MM-DD.mp3`, `site/episodes.json` y `site/feed.xml`.
4. El flujo `.github/workflows/daily.yml` corre a las 05:17 UTC (≈02:17 en Chile con horario de
   verano) y de nuevo a las 06:17 UTC como respaldo (el minuto 17 evita la congestión de las horas en
   punto): toda ejecución programada no hace nada si el episodio de hoy ya existe.
   También puedes lanzarlo a mano (`workflow_dispatch`).
5. Un fallo real (código 1) o un día sin episodio (código 2) hacen fallar el job y GitHub te envía
   un correo. Si el principal falla con código 2, el respaldo de una hora después lo reintenta y
   puede enviar un segundo correo.

### Dónde se guardan los datos

El sitio (`site/`) y `state.json` (historias usadas y correcciones pendientes) se guardan en la rama
**`gh-pages`**, la misma que sirve GitHub Pages. Cada ejecución clona esa rama, genera el episodio,
borra los MP3 que el feed ya no referencia (el feed conserva 60 episodios) y hace `push` con el
`GITHUB_TOKEN` del propio flujo. Se eligió porque no necesita tokens extra, funciona con un
repositorio público y una sola rama hace de almacenamiento y de publicación. `main` solo tiene el
código, así que su historial no se llena de MP3.

El historial de `gh-pages` se **aplasta cada día**: el flujo clona con `--depth 1` y publica el
día como un único commit huérfano con `git push --force`, de modo que la rama nunca crece. No hay
nada que reiniciar a mano. Consecuencia: si tú empujas algo a `gh-pages` (por ejemplo una
corrección), hazlo sobre el último commit, y ten en cuenta que un push tuyo durante una ejecución
del flujo puede ser sobrescrito por el push forzado.

## Puesta en marcha (una sola vez)

1. **Crea un repositorio público** en GitHub (por ejemplo `radio-ia`) y sube este código a `main`.
2. **Edita `config.toml`**: cambia `site_url` por `https://<tu-usuario>.github.io/<nombre-del-repo>`
   (sin barra final) y haz commit.
3. **Añade el secreto** `OPENROUTER_API_KEY` (la única clave necesaria; créala en
   https://openrouter.ai/keys). Con la CLI de GitHub:
   `gh secret set OPENROUTER_API_KEY -R diegocatalarc/radio-ia`
   (o en *Settings > Secrets and variables > Actions > New repository secret*). Solo si cambias de
   proveedor (ver "Cambiar de proveedor") hacen falta `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` o
   `ELEVENLABS_API_KEY`; son opcionales.
4. **Revisa los feeds antes de la primera noche**: ejecuta `python scripts/check_feeds.py` (con el
   proyecto instalado, `pip install -e .`). Para cada feed imprime si responde, cuántas entradas
   tiene, cuántas de las últimas 36 h y si se puede extraer el cuerpo de un par de artículos. Lo
   ideal es repetirlo también desde GitHub: *Actions > Episodio diario > Run workflow* con
   `check_feeds=true`, que ejecuta solo el diagnóstico y termina sin generar episodio.
5. **Lanza el flujo una vez a mano**: pestaña *Actions > Episodio diario > Run workflow*. En la
   primera ejecución crea la rama `gh-pages` con el primer episodio.
6. **Activa Pages**: *Settings > Pages > Source: Deploy from a branch > Branch `gh-pages`, carpeta
   `/ (root)`*. En un minuto o dos el feed estará en
   `https://<tu-usuario>.github.io/<nombre-del-repo>/feed.xml`.
7. **Suscríbete** en tu app de podcasts con esa URL (en Apple Podcasts: *Archivo > Seguir un
   programa por URL*; en Pocket Casts, Overcast, AntennaPod etc. hay una opción equivalente).

Checklist del primer día: `site_url` real en `config.toml` (el programa lo rechaza si sigue la de
ejemplo), los secretos creados, `scripts/check_feeds.py` sin feeds caídos, una ejecución manual
con éxito, Pages activado desde `gh-pages` y el feed abierto en tu app de podcasts.

> GitHub **desactiva los flujos programados** de los repositorios públicos tras 60 días sin
> actividad en el repositorio. Si dejan de llegar episodios, entra en la pestaña *Actions*, elige
> "Episodio diario" y pulsa *Enable workflow* (un commit en `main` también reinicia el contador).

> El feed es **público pero no listado**: no aparece en directorios de podcasts, pero cualquiera
> que conozca la URL puede escucharlo. No compartas el enlace si quieres que siga siendo privado.

## Configuración de proveedores

Campos de `config.toml`:

| Campo | Valor por defecto | Significado |
| - | - | - |
| `llm_provider` | `"openrouter"` | `"openrouter"` o `"anthropic"` |
| `model` | `anthropic/claude-sonnet-5.5` | id del modelo **del proveedor elegido** |
| `tts_provider` | `"openrouter"` | `"openrouter"`, `"openai"` o `"elevenlabs"` |
| `tts_model` | `""` | modelo de voz de OpenRouter (vacío = `microsoft/mai-voice-2.1-flash`) |
| `tts_voice` | `""` | voz; vacío = `es-MX-Valeria:MAI-Voice-2.1-Flash` con el modelo por defecto |

Un `llm_provider` o `tts_provider` desconocido se rechaza al arrancar con un mensaje claro.

### Cambiar de proveedor

- **LLM directo con Anthropic**: `llm_provider = "anthropic"`, `model = "claude-sonnet-5-5"`, instala el
  extra (`pip install '.[anthropic]'`; en el flujo cambia `pip install .` por `pip install '.[anthropic]'`)
  y define el secreto `ANTHROPIC_API_KEY`.
- **Voz con OpenAI**: `tts_provider = "openai"`, `tts_voice = "alloy"` (u otra) y `OPENAI_API_KEY`.
  **Voz con ElevenLabs**: `tts_provider = "elevenlabs"`, `tts_voice = "<voice_id>"` y `ELEVENLABS_API_KEY`.
- **Otro modelo de voz en OpenRouter**: pon `tts_model` y `tts_voice` (obligatoria si cambias el modelo).
  Las voces de cada modelo están en el campo `supported_voices` de
  `https://openrouter.ai/api/v1/models?output_modalities=speech`. Para el MP3 el modelo debe admitir
  `mp3` (algunos, como Gemini TTS y HeyGen, solo devuelven `pcm`). Las `instructions` de estilo
  (español latinoamericano neutro) solo se envían a modelos de OpenAI, Google y Fish Audio, que las
  usan según la documentación de OpenRouter.

## Elegir la voz

```bash
python -m venv .venv && .venv/bin/pip install -e .
OPENROUTER_API_KEY=... .venv/bin/python scripts/make_voice_samples.py
```

Genera muestras en `samples/<proveedor>-<voz>.mp3` (sin claves no hace nada). Para OpenRouter lee las
voces en español del modelo en el listado público; también puedes fijarlas con
`SAMPLE_OPENROUTER_MODEL` y `SAMPLE_OPENROUTER_VOICES="voz1,voz2"` (y `SAMPLE_OPENAI_VOICES`,
`SAMPLE_ELEVENLABS_VOICES` para los otros). **La calidad de la voz hay que comprobarla escuchando**:
la voz por defecto se eligió por el listado (modelo con voces `es-MX` y salida MP3), no por haberla
oído. Cuando decidas, ajusta `tts_model` y `tts_voice` en `config.toml`.

> **Límite por petición sin verificar.** El límite de caracteres por petición del modelo de voz por
> defecto (`microsoft/mai-voice-2.1-flash`) no está verificado; el adaptador de OpenRouter trocea el
> guion en trozos de `max_chars = 2500` (en `OpenRouterTts`, `radio/tts.py`), un valor conservador.
> Si la primera ejecución devuelve un 400 que habla de longitud, baja `max_chars` (por ejemplo a
> 1500 o 1000) y vuelve a lanzar: el troceado por frases se adapta solo. Además, el adaptador rechaza
> respuestas 2xx que no sean un MP3 real (JSON de error, HTML, vacías) en lugar de publicarlas, y
> reintenta hasta 2 veces (0,5 s y 2 s) ante 408, 429, 5xx y errores de red.

### Costes

Verificado en el listado de modelos de OpenRouter (10-nov-2026): `anthropic/claude-sonnet-5.5`
cuesta 2 USD por millón de tokens de entrada y 10 USD por millón de salida, con 1.000.000 de tokens de
contexto; `microsoft/mai-voice-2.1-flash` cuesta 0,000015 USD por carácter de texto (15 USD por millón
de caracteres). El resto es estimación: un guion de ~1.500 palabras son unos 9.000 caracteres, así que
la voz costaría del orden de 0,14 USD por episodio (estimación) y el LLM unos centavos (estimación,
depende del tamaño de las fuentes y de los tokens de razonamiento). Los precios cambian: compruébalos
en https://openrouter.ai/models. ElevenLabs probablemente exige un plan de pago (estimación).

## Cambiar la zona horaria (y el cron)

La zona de `config.toml` (`timezone`) define qué es "hoy" y la fecha de cada episodio. El cron de
GitHub Actions **siempre va en UTC** y no entiende de horario de verano, así que hay que calcularlo:

- Chile alterna entre UTC-4 (invierno) y UTC-3 (verano). `17 5 * * *` UTC son las 02:17 con UTC-3 y
  las 01:17 con UTC-4; en ambos casos cae de madrugada y en el día local correcto, así que no hace
  falta tocarlo por el cambio de hora.
- Si te mudas, elige la hora local deseada y súmale el desfase: hora UTC = hora local − desfase
  (con UTC-3, 02:00 local = 05:00 UTC; con UTC+1, 02:00 local = 01:00 UTC); conserva el minuto
  17 (u otro que no sea :00). El respaldo es siempre una hora después. Cuida que la hora UTC elegida siga cayendo **el mismo día local** que
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
git clone --depth 1 --branch gh-pages https://github.com/<tu-usuario>/<repo>.git datos
cd datos
python -m radio.correct "En el episodio del 12 dijimos 5 %; la cifra correcta es 3 %."
git add state.json && git commit -m "Corrección" && git push origin gh-pages
```

Como `gh-pages` se reescribe cada noche, aplica la corrección sobre el último commit (clona justo
antes) y no empujes mientras el flujo esté corriendo: el push forzado del flujo podría sobrescribirlo.

(`radio.correct` necesita el proyecto instalado con `pip install -e .` en tu copia de `main`, o
ejecutarse desde ella con `--state ../datos/state.json`.) El commit de `state.json` lo haces tú a
mano; el flujo no se ejecuta con ese push, así que la corrección se usa en la próxima ejecución.

## Añadir fuentes

Edita la lista `feeds` de `config.toml` y añade la URL del RSS/Atom. Haz commit en `main`; se usa
desde la siguiente ejecución. Comprueba la nueva fuente con `python scripts/check_feeds.py`. Ajusta `max_stories` (máximo de
historias por episodio) o `pool_size` (candidatas que ve Claude) si quieres cambiar el episodio.

## Mantenimiento

- Ejecución manual: *Actions > Episodio diario > Run workflow*. Si ya hay episodio de hoy, se
  regenera y reemplaza al anterior.
- `gh-pages` no necesita mantenimiento: su historial se aplasta a un commit cada noche.
- Pruebas: `.venv/bin/python -m pytest`.
