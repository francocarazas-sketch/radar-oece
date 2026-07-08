# Radar OECE 🇵🇪

Monitor automático diario de licitaciones públicas del Perú (obras de agua y saneamiento), con dashboard web propio. Consulta la API OCDS del Portal de Contrataciones Abiertas del OECE dos veces al día, filtra las convocatorias según tus criterios y publica los resultados en una página que puedes abrir desde cualquier dispositivo.

**Costo: S/ 0.** Todo corre en la capa gratuita de GitHub.

---

## Cómo funciona

```
GitHub Actions (5:30 am y 12:00 pm, hora de Lima)
        │
        ▼
fetch_licitaciones.py ──consulta──▶ API OCDS del OECE
        │                            (releasesAfter, orden descendente)
        ▼
filtra por palabras clave, categoría, departamento y monto (config.json)
        │
        ▼
docs/data.json  ──publicado por──▶  GitHub Pages
        │
        ▼
docs/index.html  ◀── tú abres esta URL cada mañana
```

---

## Instalación paso a paso (una sola vez, ~20 minutos)

### 1. Crea el repositorio

1. Entra a [github.com](https://github.com) (crea una cuenta gratuita si no tienes).
2. Clic en **New repository** (botón verde).
3. Nombre: `radar-oece` (o el que quieras). Marca **Public** (necesario para GitHub Pages gratuito). Clic en **Create repository**.

### 2. Sube los archivos

1. En la página del repositorio nuevo, clic en **uploading an existing file**.
2. Arrastra **todo el contenido** de esta carpeta: `fetch_licitaciones.py`, `config.json`, `README.md`, `requirements.txt` y la carpeta `docs` con `index.html` y `data.json`.
3. **Importante:** la carpeta `.github/workflows/actualizar-datos.yml` a veces no se sube al arrastrar (las carpetas que empiezan con punto están ocultas). Si no aparece, créala a mano: clic en **Add file → Create new file**, en el nombre escribe exactamente `.github/workflows/actualizar-datos.yml` (GitHub crea las carpetas automáticamente al escribir las barras), pega el contenido del archivo y guarda con **Commit changes**.

### 3. Activa GitHub Pages

1. En el repositorio: **Settings → Pages** (menú lateral izquierdo).
2. En "Build and deployment", Source: **Deploy from a branch**.
3. Branch: **main**, carpeta: **/docs**. Clic en **Save**.
4. En 1-2 minutos tu dashboard estará en: `https://TU-USUARIO.github.io/radar-oece/`
   (la URL exacta aparece en esa misma página de Settings → Pages).

### 4. Activa y prueba el workflow

1. Pestaña **Actions** del repositorio. Si aparece un aviso para habilitar workflows, acéptalo.
2. En la lista de la izquierda, clic en **Actualizar licitaciones OECE**.
3. Clic en **Run workflow → Run workflow** (ejecución manual de prueba).
4. Espera 2-5 minutos. Si sale ✅ verde, entra a tu URL de Pages: verás las convocatorias reales de los últimos días. A partir de aquí, se actualiza solo todos los días.

> Si sale ❌ rojo, abre la ejecución fallida y revisa el log del paso "Consultar API del OECE" — casi siempre es un problema temporal del servidor del OECE y se resuelve re-ejecutando.

### 5. (Opcional) Resúmenes con IA

Si quieres que Claude genere un resumen ejecutivo de cada convocatoria nueva:

1. Consigue una API key en [console.anthropic.com](https://console.anthropic.com) (servicio de pago por uso; el modelo Haiku usado aquí cuesta centavos por día).
2. En el repositorio: **Settings → Secrets and variables → Actions → New repository secret**. Nombre: `ANTHROPIC_API_KEY`, valor: tu key.
3. En `config.json`, cambia `"resumen_ia": false` por `true`.

---

## Personalizar los filtros

Edita `config.json` directamente en GitHub (ícono de lápiz) y guarda con Commit. El siguiente ciclo del workflow usará los nuevos filtros. Las opciones principales:

| Campo | Qué hace | Ejemplo |
|---|---|---|
| `palabras_clave` | Solo pasa si el objeto contiene alguna | `["agua potable", "PTAR"]` |
| `palabras_excluir` | Descarta si contiene alguna | `["supervisión"]` |
| `categorias` | `works`=obras, `goods`=bienes, `services`=servicios | `["works"]` |
| `departamentos` | Lista vacía = todo el Perú | `["JUNIN", "CUSCO"]` |
| `monto_minimo` / `monto_maximo` | Rango de valor referencial en soles | `500000` / `15000000` |
| `dias_atras` | Ventana de búsqueda por corrida | `3` |
| `dias_historial` | Cuántos días viven las fichas en el dashboard | `21` |

Tras editar los filtros puedes ejecutar el workflow manualmente (paso 4) para ver los cambios de inmediato en lugar de esperar a la siguiente corrida programada.

## Cambiar el horario

En `.github/workflows/actualizar-datos.yml`, las líneas `cron` están en **hora UTC** (Lima = UTC−5). Ejemplo: `"30 10 * * *"` = 5:30 am en Lima.

---

## Notas y límites

- Los datos provienen del Portal de Contrataciones Abiertas del OECE (licencia CC BY 4.0) e incluyen los procedimientos de selección registrados en el SEACE (LP, CP, AS, SIE, etc.). No incluyen contrataciones menores sin procedimiento.
- Este monitor es informativo. **Siempre verifica la ficha oficial en el SEACE** (cronograma, bases, absolución de consultas) antes de tomar decisiones de participación.
- El cron de GitHub Actions puede retrasarse algunos minutos en horas de alta demanda; es normal.
- Si el OECE cambia la estructura de su API, el script podría requerir un ajuste menor.
