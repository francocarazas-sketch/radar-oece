#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Radar OECE — Monitor diario de licitaciones públicas del Perú
==============================================================
Consulta la API OCDS del Portal de Contrataciones Abiertas del OECE,
filtra las convocatorias según config.json y genera docs/data.json
para el dashboard publicado en GitHub Pages.

API: https://contratacionesabiertas.oece.gob.pe/api
Datos bajo licencia CC BY 4.0 (atribución: OECE, Perú).

Uso:  python fetch_licitaciones.py
"""

import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ---------------------------------------------------------------- constantes

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
DATA_PATH = BASE_DIR / "docs" / "data.json"

API_START = (
    "https://contratacionesabiertas.oece.gob.pe/api/v1/releasesAfter"
    "?format=json&order=desc&paginateBy=50"
)
RELEASE_URL = "https://contratacionesabiertas.oece.gob.pe/api/v1/release/{}"
SEACE_BUSCADOR = "https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml"

HEADERS = {
    "User-Agent": "RadarOECE/1.0 (monitor personal de convocatorias; contacto via GitHub)",
    "Accept": "application/json",
}

LIMA_TZ = timezone(timedelta(hours=-5))

MESES = {
    "works": "Obras",
    "goods": "Bienes",
    "services": "Servicios",
    "consultingServices": "Consultoría",
}

# ---------------------------------------------------------------- utilidades


def log(msg: str) -> None:
    print(f"[{datetime.now(LIMA_TZ).strftime('%H:%M:%S')}] {msg}", flush=True)


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes, para comparar palabras clave."""
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", texto)
    sin_tildes = "".join(c for c in nfkd if not unicodedata.combining(c))
    return sin_tildes.lower()


def parsear_fecha(valor):
    """Convierte fechas ISO del API (con o sin zona horaria) a datetime aware."""
    if not valor:
        return None
    try:
        v = valor.replace("Z", "+00:00")
        dt = datetime.fromisoformat(v)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=LIMA_TZ)
        return dt
    except (ValueError, AttributeError):
        return None


def cargar_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    # Solo las llaves reales (ignora las _notas)
    return {k: v for k, v in cfg.items() if not k.startswith("_")}


def cargar_data_previa() -> dict:
    if DATA_PATH.exists():
        try:
            with open(DATA_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            log("Aviso: data.json previo ilegible; se regenera desde cero.")
    return {"actualizado": None, "licitaciones": []}


# ---------------------------------------------------------------- extracción


def extraer_region(release: dict) -> str:
    """Busca el departamento en las direcciones de las partes o del tender."""
    candidatos = []
    for party in release.get("parties", []) or []:
        addr = party.get("address") or {}
        if addr.get("region"):
            roles = party.get("roles") or []
            peso = 0 if "buyer" in roles else 1
            candidatos.append((peso, addr["region"]))
    tender = release.get("tender") or {}
    for item in tender.get("items", []) or []:
        addr = (item.get("deliveryAddress") or {})
        if addr.get("region"):
            candidatos.append((2, addr["region"]))
    if not candidatos:
        return ""
    candidatos.sort(key=lambda x: x[0])
    return str(candidatos[0][1]).strip().upper()


def extraer_licitacion(release: dict) -> dict | None:
    """Convierte un release OCDS en el registro plano que usa el dashboard."""
    tender = release.get("tender") or {}
    if not tender:
        return None

    buyer = release.get("buyer") or {}
    valor = tender.get("value") or {}
    periodo = tender.get("tenderPeriod") or {}
    consultas = tender.get("enquiryPeriod") or {}

    fecha_pub = parsear_fecha(release.get("date"))
    fecha_limite = parsear_fecha(periodo.get("endDate"))

    return {
        "ocid": release.get("ocid", ""),
        "release_id": release.get("id", ""),
        "nomenclatura": str(tender.get("id") or "").strip(),
        "titulo": (tender.get("title") or "").strip(),
        "descripcion": (tender.get("description") or "").strip(),
        "entidad": (buyer.get("name") or "").strip(),
        "region": extraer_region(release),
        "categoria": tender.get("mainProcurementCategory") or "",
        "categoria_nombre": MESES.get(tender.get("mainProcurementCategory"), tender.get("mainProcurementCategory") or ""),
        "metodo": tender.get("procurementMethodDetails") or tender.get("procurementMethod") or "",
        "estado": tender.get("status") or "",
        "monto": valor.get("amount"),
        "moneda": valor.get("currency") or "PEN",
        "fecha_publicacion": fecha_pub.isoformat() if fecha_pub else None,
        "fecha_limite_ofertas": fecha_limite.isoformat() if fecha_limite else None,
        "fecha_fin_consultas": (parsear_fecha(consultas.get("endDate")) or fecha_limite or fecha_pub).isoformat()
        if (consultas.get("endDate") or fecha_limite or fecha_pub) else None,
        "url_ocds": RELEASE_URL.format(release.get("id", "")) if release.get("id") else "",
        "url_seace": SEACE_BUSCADOR,
        "resumen_ia": "",
    }


# ---------------------------------------------------------------- filtros


def pasa_filtros(lic: dict, cfg: dict) -> bool:
    # Categoría (obras / bienes / servicios)
    cats = cfg.get("categorias") or []
    if cats and lic["categoria"] not in cats:
        return False

    # Departamento
    deps = [normalizar(d) for d in (cfg.get("departamentos") or [])]
    if deps and normalizar(lic["region"]) not in deps:
        return False

    # Monto
    monto = lic.get("monto")
    minimo = cfg.get("monto_minimo") or 0
    maximo = cfg.get("monto_maximo")
    if monto is not None:
        if monto < minimo:
            return False
        if maximo is not None and monto > maximo:
            return False

    # Palabras clave (sobre título + descripción + nomenclatura)
    texto = normalizar(" ".join([lic["titulo"], lic["descripcion"], lic["nomenclatura"]]))
    claves = [normalizar(p) for p in (cfg.get("palabras_clave") or [])]
    if claves and not any(p in texto for p in claves):
        return False

    excluir = [normalizar(p) for p in (cfg.get("palabras_excluir") or [])]
    if excluir and any(p in texto for p in excluir):
        return False

    return True


# ---------------------------------------------------------------- API OECE


def recorrer_api(cfg: dict) -> list[dict]:
    """Recorre releasesAfter (más recientes primero) hasta superar la ventana de días."""
    corte = datetime.now(LIMA_TZ) - timedelta(days=int(cfg.get("dias_atras", 3)))
    max_paginas = int(cfg.get("max_paginas", 150))

    url = API_START
    encontradas: list[dict] = []
    vistas = 0
    pagina = 0
    sesion = requests.Session()
    sesion.headers.update(HEADERS)

    while url and pagina < max_paginas:
        pagina += 1
        try:
            resp = sesion.get(url, timeout=60)
            resp.raise_for_status()
            paquete = resp.json()
        except requests.RequestException as e:
            log(f"Error de red en página {pagina}: {e}. Reintentando en 10 s…")
            time.sleep(10)
            try:
                resp = sesion.get(url, timeout=60)
                resp.raise_for_status()
                paquete = resp.json()
            except requests.RequestException as e2:
                log(f"Fallo definitivo en página {pagina}: {e2}. Se continúa con lo obtenido.")
                break
        except json.JSONDecodeError:
            log(f"Respuesta no-JSON en página {pagina}. Se detiene el recorrido.")
            break

        releases = paquete.get("releases") or paquete.get("records") or []
        if not releases:
            log(f"Página {pagina}: sin releases. Fin del recorrido.")
            break

        mas_antigua = None
        for rel in releases:
            # En record packages, el release vigente está en compiledRelease
            release = rel.get("compiledRelease", rel) if isinstance(rel, dict) else rel
            vistas += 1
            fecha = parsear_fecha(release.get("date"))
            if fecha:
                mas_antigua = fecha if (mas_antigua is None or fecha < mas_antigua) else mas_antigua
            lic = extraer_licitacion(release)
            if not lic or not lic["ocid"]:
                continue
            if fecha and fecha < corte:
                continue
            if pasa_filtros(lic, cfg):
                encontradas.append(lic)

        log(f"Página {pagina}: {len(releases)} releases | acumulado filtrado: {len(encontradas)}")

        # Condición de parada: toda la página ya es más antigua que la ventana
        if mas_antigua and mas_antigua < corte:
            log(f"Se alcanzó la fecha de corte ({corte.date()}). Fin del recorrido.")
            break

        url = (paquete.get("links") or {}).get("next")
        time.sleep(0.4)  # cortesía con el servidor público

    log(f"Recorrido terminado: {vistas} releases revisados, {len(encontradas)} pasaron los filtros.")
    return encontradas


# ---------------------------------------------------------------- resumen IA (opcional)


def generar_resumenes_ia(nuevas: list[dict]) -> None:
    """Si hay ANTHROPIC_API_KEY y resumen_ia=true, resume cada licitación nueva."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        log("resumen_ia activo pero no hay ANTHROPIC_API_KEY; se omite.")
        return

    for lic in nuevas:
        prompt = (
            "Eres asistente de un ingeniero civil peruano especializado en obras de "
            "saneamiento rural. Resume en máximo 3 líneas esta convocatoria pública, "
            "destacando: objeto de la obra, entidad, valor referencial y cualquier dato "
            "relevante para decidir si vale la pena revisar las bases. Responde solo el "
            f"resumen, sin preámbulos.\n\nDatos:\n{json.dumps(lic, ensure_ascii=False)}"
        )
        try:
            r = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 300,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=60,
            )
            r.raise_for_status()
            contenido = r.json().get("content", [])
            texto = " ".join(b.get("text", "") for b in contenido if b.get("type") == "text").strip()
            lic["resumen_ia"] = texto
            time.sleep(0.5)
        except requests.RequestException as e:
            log(f"No se pudo resumir {lic['ocid']}: {e}")


# ---------------------------------------------------------------- principal


def main() -> int:
    cfg = cargar_config()
    log("Configuración cargada. Consultando API del OECE…")

    nuevas = recorrer_api(cfg)

    previa = cargar_data_previa()
    existentes = {l["ocid"]: l for l in previa.get("licitaciones", [])}

    # Detectar realmente nuevas (para el resumen IA y el contador)
    ocids_previos = set(existentes.keys())
    realmente_nuevas = [l for l in nuevas if l["ocid"] not in ocids_previos]

    if cfg.get("resumen_ia") and realmente_nuevas:
        generar_resumenes_ia(realmente_nuevas)

    # Merge: lo nuevo pisa lo viejo (release más reciente del mismo proceso),
    # pero conserva el resumen IA previo si el nuevo no trae uno.
    for lic in nuevas:
        anterior = existentes.get(lic["ocid"])
        if anterior and anterior.get("resumen_ia") and not lic.get("resumen_ia"):
            lic["resumen_ia"] = anterior["resumen_ia"]
        existentes[lic["ocid"]] = lic

    # Purga por antigüedad
    limite_hist = datetime.now(LIMA_TZ) - timedelta(days=int(cfg.get("dias_historial", 21)))
    vigentes = []
    for lic in existentes.values():
        f = parsear_fecha(lic.get("fecha_publicacion"))
        if f is None or f >= limite_hist:
            vigentes.append(lic)

    vigentes.sort(key=lambda l: l.get("fecha_publicacion") or "", reverse=True)

    salida = {
        "actualizado": datetime.now(LIMA_TZ).isoformat(),
        "nuevas_en_esta_corrida": len(realmente_nuevas),
        "fuente": "Portal de Contrataciones Abiertas de la Compra Pública — OECE (CC BY 4.0)",
        "licitaciones": vigentes,
    }

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=1)

    log(f"data.json escrito: {len(vigentes)} licitaciones vigentes ({len(realmente_nuevas)} nuevas hoy).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
