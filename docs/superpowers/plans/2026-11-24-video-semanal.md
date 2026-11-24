# Video semanal de Radio IA — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cada semana, a partir de lo publicado en los episodios diarios, generar y publicar un video-resumen de motion graphics en 16:9 y 9:16, producido por tres etapas: Director, Editor y Montaje.

**Architecture:** El pipeline diario guarda ahora un registro por día (`site/days/AAAA-MM-DD.json`). Un flujo semanal (`python -m radio.weekly`) lee los registros de la semana y encadena llamadas LLM con salida estructurada: Director (briefing) → Editor (guion de escenas en JSON) → voz por escena → Montaje (Remotion renderiza el JSON a MP4). El JSON de escenas es el único contrato entre Editor y Montaje; la duración real del audio de cada escena fija la duración de esa escena.

**Tech Stack:** Python 3.11+ (el existente: httpx, pytest), Node 20+ con Remotion 4 (React/TypeScript) en `video/`, GitHub Actions, rama `gh-pages` como almacenamiento.

**Spec:** El diseño acordado en la conversación está resumido en este documento (secciones Architecture, Global Constraints y Tasks). Base del proyecto: `docs/2026-11-10-radio-ia-design.md`.

## Global Constraints

- Idioma de toda la narración y del texto en pantalla: español.
- El video dura entre 5 y 8 minutos en 16:9 (narración de 700 a 1200 palabras) y como máximo 90 segundos en 9:16 (narración de las escenas marcadas `short` ≤ 230 palabras en total).
- Escenas del Editor: `kind` ∈ `titular`, `cifra`, `grafico`, `tarjeta`, `cierre`; el texto en pantalla (`on_screen`) ≤ 90 caracteres.
- Una cifra solo puede aparecer en narración, `on_screen`, `value` o `chart` si está en el material de la semana (guiones diarios, títulos, resúmenes y cuerpos guardados). Si el chequeo falla tras un reintento, no se publica nada (exit 1).
- Semana = los 7 días que terminan hoy (zona horaria de `config.timezone`). Con menos de 4 registros diarios no se publica (exit 2).
- Resolución: 1920×1080 (16:9) y 1080×1920 (9:16), 30 fps, MP4 H.264.
- Se conservan en `gh-pages` solo los últimos 4 videos semanales y los últimos 60 registros diarios.
- Los flujos diario y semanal comparten el grupo de concurrencia `radio-ia-daily`.
- Se reutilizan sin duplicar: `Llm.complete` (`radio/llm.py`), `synthesize` y `provider_from_config` (`radio/tts.py`), `unsupported_numbers` (`radio/script.py`), `Story` (`radio/models.py`). Ningún secreto nuevo.

## Review Focus

- Días sin registro dentro de la semana (huecos, o días saltados con exit 2): el semanal debe funcionar con ≥ 4 registros y etiquetar con las fechas reales. Test en Task 1 y Task 8.
- El Director devuelve `story_ids` que no existen en la semana: debe rechazarse y reintentarse, no pasar al Editor. Test en Task 3.
- El Editor inventa una cifra: reintento una vez con retroalimentación y, si persiste, fallo sin publicar. Test en Task 4.
- La voz falla a mitad de las escenas (o devuelve audio vacío): no debe quedar nada publicado ni archivos a medias en `site/`. Test en Task 5 y Task 8.
- Texto en pantalla demasiado largo, gráfico con 0 o 1 punto, o cifra con formato raro: la validación de escenas lo rechaza antes de renderizar. Test en Task 2.
- Reejecución en la misma semana: no regenera ni sobrescribe si el video ya existe (salvo ejecución manual forzada). Test en Task 8.

---

### Task 1: Registro diario persistente

**Files:**
- Create: `radio/archive.py`
- Modify: `radio/run.py` (en `_run`, antes de `state.save`)
- Test: `tests/test_archive.py`, `tests/test_run.py`

**Interfaces:**
- Produces:
  - `@dataclass class ArchivedStory: id: str; title: str; url: str; source: str; summary: str; body: str | None`
  - `@dataclass class DayRecord: day: date; title: str; script: str; stories: list[ArchivedStory]`
  - `save_day(site_dir: Path, record: DayRecord) -> Path` escribe `site_dir/days/AAAA-MM-DD.json` de forma atómica (usar `_atomic_write` de `radio/run.py` movido a `radio/archive.py` y reimportado en `run.py`).
  - `load_week(site_dir: Path, end_day: date, days: int = 7) -> list[DayRecord]` devuelve los registros existentes con `end_day - days < day <= end_day`, ordenados por día; ignora los que no existen.
  - `prune_days(site_dir: Path, keep: int = 60) -> list[str]` borra los registros más antiguos y devuelve los nombres borrados.
  - `story_to_archived(s: Story, max_body: int = 4000) -> ArchivedStory`

- [ ] **Step 1: Write the failing tests** en `tests/test_archive.py`: `test_save_and_load_roundtrip` (guardar dos días, `load_week` devuelve ambos en orden con los mismos campos), `test_load_week_skips_missing_days_and_out_of_window` (existen 3 de 7 días y uno fuera de ventana → devuelve 3), `test_story_body_is_truncated_to_max_body` (cuerpo de 5000 caracteres → 4000), `test_prune_days_keeps_newest` (62 archivos, `keep=60` → borra los 2 más antiguos). En `tests/test_run.py` añadir `test_run_writes_day_record`: tras un `run` publicado existe `site/days/<día>.json` con el título, el guion y las historias usadas.
- [ ] **Step 2: Run** `pytest tests/test_archive.py tests/test_run.py -v`. Expected: FAIL (módulo `radio.archive` no existe).
- [ ] **Step 3: Implement** `radio/archive.py` con las firmas de arriba (JSON con `ensure_ascii=False`). En `radio/run.py::_run`, después de escribir el feed y antes de `state.save`, llamar a `save_day(deps.site_dir, DayRecord(...))` con `result.text` y `result.used`; mover `_atomic_write` a `archive.py` e importarlo.
- [ ] **Step 4: Run** `pytest -q`. Expected: todos PASS.
- [ ] **Step 5: Commit** `git add radio/archive.py radio/run.py tests/test_archive.py tests/test_run.py && git commit -m "feat: guarda un registro por día (guion y fuentes)"`

---

### Task 2: Esquema de escenas y validación

**Files:**
- Create: `radio/video/__init__.py`, `radio/video/scenes.py`
- Test: `tests/test_scenes.py`

**Interfaces:**
- Produces:
  - `Kind = Literal["titular", "cifra", "grafico", "tarjeta", "cierre"]`
  - `@dataclass class Scene: id: str; kind: Kind; narration: str; on_screen: str; source: str | None = None; value: str | None = None; chart: list[tuple[str, float]] | None = None; short: bool = False`
  - `@dataclass class SceneScript: title: str; scenes: list[Scene]`
  - `class SceneError(ValueError)`
  - `parse_scene_script(raw: str) -> SceneScript` parsea JSON (tolera una valla ```json), valida y lanza `SceneError` con mensaje accionable.
  - `scene_texts(script: SceneScript) -> str` concatena narración, `on_screen`, `value` y etiquetas/valores de `chart` (lo que revisa el chequeo de cifras).
  - `short_scenes(script: SceneScript) -> list[Scene]` escenas `short`, más el cierre.
- Validaciones: ids únicos; `on_screen` ≤ 90 caracteres; `cifra` exige `value`; `grafico` exige `chart` con 2 a 6 puntos y valores > 0; narración no vacía; último elemento `cierre`; al menos una escena `short` y como máximo 230 palabras de narración en `short_scenes`; total de palabras de narración entre 700 y 1200.

- [ ] **Step 1: Write the failing tests**: `test_parse_valid_script`, `test_parse_accepts_json_fence`, `test_on_screen_over_90_chars_rejected`, `test_chart_with_one_point_rejected`, `test_chart_with_non_positive_value_rejected`, `test_cifra_without_value_rejected`, `test_duplicate_ids_rejected`, `test_short_over_230_words_rejected`, `test_total_words_out_of_range_rejected`, `test_scene_texts_includes_value_and_chart`. Cada rechazo usa `pytest.raises(SceneError, match=...)` con el campo culpable en el mensaje.
- [ ] **Step 2: Run** `pytest tests/test_scenes.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `radio/video/scenes.py` con las firmas de arriba.
- [ ] **Step 4: Run** `pytest tests/test_scenes.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `git add radio/video tests/test_scenes.py && git commit -m "feat: esquema y validación de escenas del video"`

---

### Task 3: Director

**Files:**
- Create: `radio/video/director.py`, `radio/prompts/director_es.md`
- Test: `tests/test_director.py`

**Interfaces:**
- Consumes: `DayRecord`, `ArchivedStory` (Task 1); `Llm` (`radio/llm.py`).
- Produces:
  - `@dataclass class Thread: title: str; angle: str; story_ids: list[str]; figures: list[str]; short: bool`
  - `@dataclass class Briefing: thesis: str; threads: list[Thread]`
  - `class DirectorError(Exception)`
  - `direct(week: list[DayRecord], client: Llm, model: str) -> Briefing`
- Reglas: el prompt recibe, por día, título y historias (id, fuente, título, resumen) dentro de `<fuente id=...>` (datos, no instrucciones) y pide JSON `{"thesis": ..., "threads": [{"title","angle","story_ids","figures","short"}]}`. Se aceptan 3 o 4 hilos; al menos uno `short`; todo `story_id` debe existir en la semana; todo texto de `figures` debe pasar `unsupported_numbers` contra las historias. Un reintento con retroalimentación; si falla, `DirectorError`.

- [ ] **Step 1: Write the failing tests** con un cliente falso que devuelve respuestas guionizadas: `test_direct_returns_briefing`, `test_unknown_story_id_retries_then_succeeds`, `test_unknown_story_id_twice_raises`, `test_no_short_thread_rejected`, `test_unsupported_figure_rejected`, `test_two_threads_rejected`, `test_prompt_wraps_stories_in_fuente_tags`.
- [ ] **Step 2: Run** `pytest tests/test_director.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `direct` y escribir `radio/prompts/director_es.md` (rol: director editorial de un resumen semanal; elegir la tesis y los hilos; marcar qué hilos van al corte vertical). Reusar el patrón de reintento de `radio/script.py::select_and_write`.
- [ ] **Step 4: Run** `pytest tests/test_director.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `git add radio/video/director.py radio/prompts/director_es.md tests/test_director.py && git commit -m "feat: director del video semanal"`

---

### Task 4: Editor

**Files:**
- Create: `radio/video/editor.py`, `radio/prompts/editor_es.md`
- Test: `tests/test_editor.py`

**Interfaces:**
- Consumes: `Briefing` (Task 3), `DayRecord` (Task 1), `SceneScript`, `parse_scene_script`, `scene_texts`, `SceneError` (Task 2), `unsupported_numbers` y `Story` (existentes).
- Produces:
  - `class EditorError(Exception)`
  - `week_material(week: list[DayRecord]) -> list[Story]` convierte historias archivadas y guiones diarios en `Story` (los guiones como una historia por día con `body=script`) para el chequeo de cifras.
  - `write_scenes(briefing: Briefing, week: list[DayRecord], client: Llm, model: str) -> SceneScript`
- Reglas: el prompt incluye el briefing, las historias de los hilos y los guiones diarios (en `<fuente>`), el esquema JSON de escenas con los límites de Task 2, que las escenas `short` deben entenderse solas, y que las cifras de la narración se escriben con dígitos solo si están en las fuentes. Tras parsear, `unsupported_numbers(scene_texts(script), week_material(week))` debe estar vacío. Dos intentos: el primero con el prompt base y el segundo con la retroalimentación del error (`SceneError` o cifras). Si ambos fallan, `EditorError`.

- [ ] **Step 1: Write the failing tests** con cliente falso: `test_write_scenes_returns_valid_script`, `test_invented_number_retries_with_feedback` (el segundo prompt contiene la cifra culpable), `test_invented_number_twice_raises_editor_error`, `test_scene_error_retries_once`, `test_figure_from_daily_script_is_allowed`, `test_week_material_includes_scripts_and_story_bodies`.
- [ ] **Step 2: Run** `pytest tests/test_editor.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `radio/video/editor.py` y `radio/prompts/editor_es.md`.
- [ ] **Step 4: Run** `pytest tests/test_editor.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `git add radio/video/editor.py radio/prompts/editor_es.md tests/test_editor.py && git commit -m "feat: editor del video semanal con chequeo de cifras"`

---

### Task 5: Voz por escena

**Files:**
- Create: `radio/audio.py`, `radio/video/voice.py`
- Modify: `radio/run.py` (`estimate_mp3_duration_s` delega en `radio/audio.py`)
- Test: `tests/test_voice.py`, `tests/test_run.py` (los existentes de `estimate_mp3_duration_s` deben seguir pasando)

**Interfaces:**
- Consumes: `SceneScript`, `Scene` (Task 2); `synthesize`, `TtsProvider` (`radio/tts.py`).
- Produces:
  - `radio/audio.py::mp3_duration(data: bytes) -> float` (la lógica actual de `estimate_mp3_duration_s`, sin redondear ni forzar ≥ 1); `estimate_mp3_duration_s(data) = max(1, round(mp3_duration(data)))` queda en `run.py`.
  - `@dataclass class SceneAudio: scene_id: str; mp3: bytes; duration_s: float`
  - `class VoiceError(Exception)`
  - `narrate(script: SceneScript, tts: TtsProvider) -> list[SceneAudio]` una locución por escena, en orden; audio vacío o con duración 0 → `VoiceError` nombrando la escena.

- [ ] **Step 1: Write the failing tests**: `test_mp3_duration_matches_old_estimate` (mismos bytes de los tests existentes → `round()` coincide), `test_narrate_one_audio_per_scene_in_order`, `test_narrate_empty_audio_raises_voice_error_naming_scene`, `test_narrate_provider_error_propagates_without_partial_result`. Usar un `TtsProvider` falso cuyo `speak` devuelve un MP3 mínimo válido (reutilizar el helper de bytes de `tests/test_run.py`).
- [ ] **Step 2: Run** `pytest tests/test_voice.py tests/test_run.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** moviendo la lógica de duración a `radio/audio.py` y escribiendo `narrate`.
- [ ] **Step 4: Run** `pytest -q`. Expected: todos PASS.
- [ ] **Step 5: Commit** `git add radio/audio.py radio/video/voice.py radio/run.py tests/test_voice.py && git commit -m "feat: voz por escena y duración exacta de MP3"`

---

### Task 6: Manifiesto de render

**Files:**
- Create: `radio/video/manifest.py`
- Test: `tests/test_manifest.py`

**Interfaces:**
- Consumes: `SceneScript`, `Scene`, `short_scenes` (Task 2); `SceneAudio` (Task 5).
- Produces:
  - `FPS = 30`, `TAIL_S = 0.5` (silencio al final de cada escena)
  - `build_manifest(script: SceneScript, audios: list[SceneAudio], out_dir: Path, *, vertical: bool, week_label: str) -> Path` escribe `out_dir/audio/<scene_id>.mp3` y `out_dir/props.json`, y devuelve la ruta de `props.json`. Si `vertical`, usa solo `short_scenes`.
  - Forma de `props.json`: `{"fps": 30, "title": str, "weekLabel": str, "scenes": [{"id","kind","onScreen","value","chart":[{"label","value"}]|null,"source","audio":"audio/<id>.mp3","durationFrames": int}]}` con `durationFrames = ceil((duration_s + TAIL_S) * FPS)`.
  - `week_label(days: list[date]) -> str` por ejemplo `"17–23 de noviembre de 2026"`; si la semana cruza de mes, `"28 de noviembre – 4 de diciembre de 2026"`.

- [ ] **Step 1: Write the failing tests**: `test_manifest_horizontal_has_all_scenes`, `test_manifest_vertical_only_short_and_closing`, `test_duration_frames_include_tail`, `test_audio_files_written_next_to_props`, `test_week_label_same_month`, `test_week_label_crossing_month`.
- [ ] **Step 2: Run** `pytest tests/test_manifest.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `radio/video/manifest.py`.
- [ ] **Step 4: Run** `pytest tests/test_manifest.py -v`. Expected: PASS.
- [ ] **Step 5: Commit** `git add radio/video/manifest.py tests/test_manifest.py && git commit -m "feat: manifiesto de render del video"`

---

### Task 7: Proyecto Remotion

**Files:**
- Create: `video/package.json`, `video/tsconfig.json`, `video/remotion.config.ts`, `video/src/index.ts`, `video/src/Root.tsx`, `video/src/Semanal.tsx`, `video/src/brand.ts`, `video/src/scenes/{Titular,Cifra,Grafico,Tarjeta,Cierre}.tsx`, `video/fixtures/props.sample.json`
- Modify: `.gitignore` (`video/node_modules/`, `video/out/`)

**Interfaces:**
- Consumes: la forma de `props.json` definida en Task 6.
- Produces: composiciones `Semanal16x9` (1920×1080) y `Semanal9x16` (1080×1920), ambas a 30 fps, con duración total calculada vía `calculateMetadata` como la suma de `durationFrames`. Cada escena es un `<Sequence>` con su `<Audio src={staticFile(audio)}>`; el componente se elige por `kind`. `brand.ts` define colores, tipografía y logotipo de texto "Radio IA" una sola vez. Los componentes escalan por `useVideoConfig()` (sin tamaños en píxeles fijos del lienzo) para servir a los dos formatos.
- Comando de render: `npx remotion render Semanal16x9 out/semanal-16x9.mp4 --props=<props.json> --public-dir=<out_dir>` (la carpeta de audio del manifiesto es el `public-dir`).

- [ ] **Step 1: Crear el fixture** `video/fixtures/props.sample.json` con una escena de cada `kind` (cinco), duraciones de 90 a 150 frames, y audios de silencio generados por el paso siguiente.
- [ ] **Step 2: Generar audios de silencio** del fixture con `ffmpeg -f lavfi -i anullsrc=r=44100:cl=mono -t 3 -q:a 9 video/fixtures/audio/<id>.mp3` por escena; confirmar con `ffprobe` que duran 3 s.
- [ ] **Step 3: Implement** el proyecto: `package.json` con scripts `typecheck` (`tsc --noEmit`) y `render:sample`; `Root.tsx` registra las dos composiciones con `calculateMetadata`; un componente por `kind`; `Semanal.tsx` encadena las escenas.
- [ ] **Step 4: Verify typecheck:** `cd video && npm install && npm run typecheck`. Expected: sin errores.
- [ ] **Step 5: Verify render:** `cd video && npx remotion browser ensure && npx remotion render Semanal16x9 out/sample-16x9.mp4 --props=fixtures/props.sample.json --public-dir=fixtures && ffprobe -v error -show_entries stream=width,height,duration -of csv=p=0 out/sample-16x9.mp4`. Expected: `1920,1080` y duración = suma de `durationFrames` / 30 (±0,1 s). Repetir con `Semanal9x16` y esperar `1080,1920`.
- [ ] **Step 6: Inspección visual:** abrir un fotograma por escena (`npx remotion still Semanal16x9 out/f.png --props=... --frame=<n>`) y comprobar que el texto de 90 caracteres no desborda en ninguno de los dos formatos.
- [ ] **Step 7: Commit** `git add video .gitignore && git commit -m "feat: proyecto Remotion con composiciones 16:9 y 9:16"` (sin `node_modules` ni `out`).

---

### Task 8: Orquestación semanal

**Files:**
- Create: `radio/video/render.py`, `radio/weekly.py`
- Modify: `radio/config.py` (campo `weekly_model: str = ""`), `config.toml`, `radio/check.py` (`weekly_exists(site_dir, week_id)` y prune de videos)
- Test: `tests/test_render.py`, `tests/test_weekly.py`, `tests/test_check.py`

**Interfaces:**
- Consumes: Tasks 1 a 6, `Config`, `llm_from_config`, `provider_from_config`.
- Produces:
  - `render_video(props_path: Path, public_dir: Path, composition: str, out_path: Path, runner=subprocess.run) -> None` ejecuta `npx remotion render` dentro de `video/`; código de salida ≠ 0 → `RenderError` con las últimas líneas de stderr.
  - `@dataclass class WeeklyDeps: llm: Llm; tts: TtsProvider; site_dir: Path; work_dir: Path; render: Callable[..., None]`
  - `run_weekly(config: Config, now: datetime, deps: WeeklyDeps, *, force: bool = False) -> RunResult` (mismo `RunResult` de `radio/run.py`): exit 0 publicó, 1 falló, 2 menos de 4 registros.
  - `week_id(day: date) -> str` formato ISO `"2026-W47"`.
  - Publicación: `site/weekly/<week_id>-16x9.mp4`, `site/weekly/<week_id>-9x16.mp4` y `site/weekly.json` (lista de `{"week","label","title","video_16x9","video_9x16","published"}`, más reciente primero); se conservan los 4 más recientes y se borran los MP4 huérfanos.
  - Orden de escritura: todo se genera en `work_dir`; solo si todo salió bien se copian los MP4 y luego `weekly.json`. Cualquier fallo antes deja `site/` intacto.
  - `weekly.json` con el mismo `week_id` y `force=False` → exit 0 sin regenerar (mensaje "ya existe"); `python -m radio.weekly --force` regenera.
  - `main() -> int` como `radio/run.py::main`.

- [ ] **Step 1: Write the failing tests** (todas con dependencias falsas y `render` falso que escribe un archivo): `test_run_weekly_publishes_both_videos_and_index`, `test_run_weekly_skips_with_fewer_than_4_days_exit_2`, `test_run_weekly_works_with_gaps_and_labels_real_dates`, `test_run_weekly_is_idempotent_without_force`, `test_run_weekly_force_regenerates`, `test_tts_failure_leaves_site_untouched`, `test_render_failure_leaves_site_untouched`, `test_editor_failure_exit_1_site_untouched`, `test_keeps_only_last_4_weeks_and_prunes_mp4`. En `tests/test_render.py`: `test_render_video_builds_expected_command` (runner falso captura args: composición, salida, `--props`, `--public-dir`, `cwd` = `video/`) y `test_render_failure_raises_render_error_with_stderr_tail`.
- [ ] **Step 2: Run** `pytest tests/test_render.py tests/test_weekly.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `radio/video/render.py`, `radio/weekly.py`, el campo `weekly_model` (vacío = `model`) y `config.toml` con comentario.
- [ ] **Step 4: Run** `pytest -q`. Expected: todos PASS.
- [ ] **Step 5: Commit** `git add radio tests config.toml && git commit -m "feat: orquestación del video semanal"`

---

### Task 9: Flujo semanal de GitHub Actions

**Files:**
- Create: `.github/workflows/weekly.yml`
- Modify: `.github/workflows/daily.yml` (nada que cambiar salvo comprobar que conserva `site/days/` y `site/weekly/` al clonar `gh-pages`; documentarlo en un comentario)
- Test: ninguno automatizable; verificación con `workflow_dispatch`.

**Interfaces:**
- Consumes: `python -m radio.weekly [--force]`, `npx remotion browser ensure`.
- Produces: flujo `Video semanal` con cron `17 9 * * 0` (domingo 09:17 UTC, tras el diario), `workflow_dispatch` con entrada booleana `force`, `concurrency.group: radio-ia-daily` con `cancel-in-progress: false`, `timeout-minutes: 45`, `permissions: contents: write`.
- Pasos: checkout; `setup-python` 3.12; `setup-node` 20 con caché de `video/package-lock.json`; `pip install .`; `cd video && npm ci && npx remotion browser ensure`; clonar `gh-pages` en `site/` (mismo bloque que el diario); `python -m radio.weekly` (con `--force` si se pidió) con `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY` y los opcionales; si el código es 0 y hay cambios, publicar con commit huérfano forzado a `gh-pages` como el diario (copiando también `web/index.html`). Código 2 → `::notice` ("menos de 4 días de registros"), no `::error`.

- [ ] **Step 1: Write** `.github/workflows/weekly.yml` con lo anterior.
- [ ] **Step 2: Verify sintaxis:** `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/weekly.yml'))"`. Expected: sin salida.
- [ ] **Step 3: Commit** `git add .github && git commit -m "ci: flujo semanal del video"`
- [ ] **Step 4: Verificación real (requiere push y registros diarios):** tras ≥ 4 días con el Task 1 desplegado, lanzar `gh workflow run weekly.yml -f force=true` y comprobar con `gh run watch` que termina en verde, que `site/weekly/` en `gh-pages` contiene los dos MP4 y que ambos se reproducen. Hasta entonces la verificación de extremo a extremo se hace en local (Task 10, Step 4).

---

### Task 10: Web y documentación

**Files:**
- Modify: `web/index.html`, `README.md`
- Test: ninguno automatizable; verificación en navegador local.

**Interfaces:**
- Consumes: `site/weekly.json` (forma definida en Task 8).
- Produces: en `web/index.html`, una sección "Resumen semanal" sobre la lista de episodios que carga `weekly.json` (con `cache: "no-cache"`, como `episodes.json`), muestra el video más reciente con `<video controls>` y enlaces a la versión 9:16 y a las 3 semanas anteriores; si `weekly.json` no existe o está vacío, la sección no se muestra. Estilo coherente con la web minimalista actual. En `README.md`, una sección "Video semanal" que explica registros diarios, las tres etapas, el JSON de escenas, el flujo semanal, el límite de 4 videos y cómo regenerar (`--force`).

- [ ] **Step 1: Implement** la sección en `web/index.html` y la sección del README.
- [ ] **Step 2: Verify con datos de ejemplo:** crear `site/weekly.json` y un MP4 de prueba en un directorio temporal, servir con `python -m http.server` y comprobar en el navegador integrado que se ve el reproductor, los enlaces, y que sin `weekly.json` la sección desaparece sin errores en consola.
- [ ] **Step 3: Verificación local de extremo a extremo:** con 4 a 7 registros de prueba en `site/days/` y claves reales en el entorno, ejecutar `python -m radio.weekly` y reproducir ambos MP4 generados; comprobar que el 9:16 dura ≤ 90 s y el 16:9 entre 5 y 8 min.
- [ ] **Step 4: Commit** `git add web/index.html README.md && git commit -m "feat: sección de video semanal en la web y documentación"`

---

## Self-Review

- **Cobertura:** persistencia (1), contrato de escenas (2), Director (3), Editor con chequeo de cifras (4), voz por escena y la regla "la voz manda" (5, 6), Remotion en ambos formatos (7), orquestación, reglas de publicación y límite de 4 videos (8), Actions con render automático (9), web y docs (10).
- **Consistencia de tipos:** `DayRecord`/`ArchivedStory` (1) lo consumen 3, 4 y 8; `Scene`/`SceneScript` (2) lo consumen 4, 5 y 6; `SceneAudio` (5) lo consume 6; la forma de `props.json` (6) la consume 7; `RunResult` se reutiliza de `radio/run.py`.
- **Riesgos abiertos, no decididos aquí:** (a) la calidad visual de Task 7 solo se valida mirando fotogramas; conviene revisar el primer render a mano. (b) El tamaño de `gh-pages` con 4 videos de 5 a 8 min puede acercarse a los 100 MB por archivo si se sube el bitrate; si pasa, bajar el CRF de Remotion (`--crf=28`) o mover los videos a GitHub Releases. (c) Los primeros 3 a 4 días después de desplegar el Task 1 no habrá semana completa: el primer video real sale a la semana siguiente.
