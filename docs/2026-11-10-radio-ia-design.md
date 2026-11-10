# Radio IA: podcast diario privado sobre IA y economía

## Intención
Diego quiere sentirse informado sobre el acontecer de la IA y su impacto en la economía sin leer: un episodio de audio cada mañana, escuchable en teléfono y laptop, como una radio personal.

## Objetivos
- Un episodio diario en español, de 8 a 10 minutos, listo antes de las 6 am.
- Se escucha en cualquier app de podcasts (Apple Podcasts, Spotify, Overcast) vía un feed RSS privado; descarga offline y reproducción en segundo plano.
- Contenido: lo más relevante del día en IA con foco en impacto económico (inversión, empleo, mercados, regulación, movimientos de empresas), con contexto de por qué importa.
- Funciona solo, sin intervención diaria, y con costo bajo (objetivo: menos de ~1 USD por episodio).

## No objetivos
- Radio continua en streaming.
- App propia o interacción (preguntas, filtros). Una página con texto y fuentes queda como mejora futura.
- Publicación abierta o audiencia pública.

## Anti-objetivos (sería un fracaso aunque funcione)
- Episodios que inventan datos o cifras: cada afirmación debe salir de las fuentes recogidas.
- Relleno o resumen genérico de titulares sin análisis de impacto.
- Voz robótica que cansa a los 10 minutos.
- Que falle en silencio: si un día no hay episodio, debe notarse.

## Enfoque (elegido: podcast privado)
Alternativas consideradas: (B) web app con reproductor propio, más control y texto pero mucho más trabajo y peor para oír con pantalla apagada; (C) streaming continuo, descartada por complejidad. Diego eligió A, el podcast privado.

Tubería diaria:
1. **Recolectar**: leer feeds RSS/APIs de fuentes de noticias de IA y economía de las últimas ~24 h.
2. **Seleccionar y escribir**: Claude elige las 4-6 historias más relevantes y escribe un guion hablado en español, con tono de radio matinal, citando la fuente de cada dato.
3. **Voz**: texto a voz de calidad natural en español, genera el MP3.
4. **Publicar**: sube el MP3 y actualiza `feed.xml` en un hosting estático; Diego se suscribe una vez a esa URL.
5. **Programar**: ejecución automática cada madrugada.

## Decisiones tomadas por mí (corregibles)
- Idioma español, duración 8-10 min, listo antes de las 6 am.
- Hosting: GitHub Pages (feed y MP3 estáticos, gratis) y ejecución con GitHub Actions programado. Ventaja: no depende de que la laptop esté encendida.
- El feed es "privado" por URL no listada, no por autenticación (las apps de podcasts no soportan bien login).
- Guion con Claude vía API; voz con un servicio TTS comercial con buenas voces en español (se elige al construir, probando 2-3 muestras con Diego).
- Fuentes iniciales a definir con Diego al construir; punto de partida: medios de tecnología y economía en inglés y español, más blogs oficiales de laboratorios de IA.

## Decisiones añadidas tras la revisión (mis llamadas, corregibles)
- Todo dato (cifra, fecha, nombre) debe salir de texto realmente leído por el sistema. El análisis de impacto lo escribe Claude y se marca en voz como interpretación. Se lee el artículo completo si es público; con paywall, solo titular y resumen.
- Día flojo: se publica un episodio más corto. Con menos de 2 historias relevantes no se publica y se envía aviso.
- Errores: se reemplaza el episodio afectado y el siguiente incluye una corrección breve.
- Confirmado por Diego: repo público con feed no listado es aceptable.
- Zona horaria: Chile hasta el 7 de diciembre de 2026; después cambia a una zona aún no definida. La zona y la hora objetivo son un ajuste único de configuración. El cron (en UTC) se programa varias horas antes de las 6 am locales por los retrasos de GitHub Actions, y se recalcula al cambiar de zona.

## Pendiente para quien construya
- Elegir proveedor TTS y voz (probar muestras).
- Lista concreta de fuentes y cómo manejar paywalls (usar solo titulares y resúmenes públicos).
- Formato del guion: apertura fija, bloques por historia, cierre con "qué mirar mañana".
- Aviso de fallo (por ejemplo correo o notificación si el episodio no se genera).
- Depuración de duplicados entre días para no repetir historias.
