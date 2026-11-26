#!/usr/bin/env python3
"""Vigila cambios de Google Search y avisa por Telegram y/o ntfy.

Modos:
  fast  -> Status Dashboard, blog de Search Central, rangos de IP de los
           rastreadores y las páginas de novedades (/search/updates y el
           changelog de /crawling). Pensado para cada 10 minutos.
  docs  -> rastreo completo de /search/docs y /crawling/docs con diff del
           texto de cada página, más el PDF de las Quality Rater Guidelines.
  all   -> los dos.

El estado se guarda en ./state (o en STATE_DIR) y GitHub Actions lo commitea,
así que el historial de git es también un archivo de todos los cambios.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import difflib
import hashlib
import html
import json
import os
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parent
STATE = Path(os.environ.get("STATE_DIR", ROOT / "state"))
DOCS_DIR = STATE / "docs"
TZ = ZoneInfo(os.environ.get("MONITOR_TZ", "Europe/Madrid"))

BASE = "https://developers.google.com"
STATUS_JSON = "https://status.search.google.com/incidents.json"
STATUS_URL = "https://status.search.google.com/"
BLOG_FEED = f"{BASE}/search/blog/feed.xml"
QRG_PDF = ("https://static.googleusercontent.com/media/guidelines.raterhub.com"
           "/en//searchqualityevaluatorguidelines.pdf")
IP_RANGES = {
    "common-crawlers": f"{BASE}/static/crawling/ipranges/common-crawlers.json",
    "special-crawlers": f"{BASE}/static/crawling/ipranges/special-crawlers.json",
    "user-triggered-fetchers": f"{BASE}/static/crawling/ipranges/user-triggered-fetchers.json",
    "user-triggered-fetchers-google": f"{BASE}/static/crawling/ipranges/user-triggered-fetchers-google.json",
}
# Páginas donde Google anuncia novedades: se miran también en modo fast.
FAST_PAGES = ["/search/updates", "/crawling/docs/changelog"]
# Qué parte de developers.google.com se rastrea en modo docs.
DOC_PREFIXES = ("/search/docs", "/search/updates", "/crawling/docs")
DOC_SEEDS = ["/search/docs", "/search/updates", "/crawling/docs/about-crawling",
             "/crawling/docs/changelog"]
MAX_DOC_PAGES = 2000
MASS_CHANGE = 25          # más cambios que esto en una pasada -> un solo aviso
MAX_DIFF_LINES = 20       # líneas del diff que van en la notificación

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "Mozilla/5.0 (compatible; search-docs-monitor/1.0)"
SESSION.mount("https://", HTTPAdapter(max_retries=Retry(
    total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "POST"])))


# ---------------------------------------------------------------- utilidades

def get(url: str, **kw) -> requests.Response:
    r = SESSION.get(url, timeout=30, **kw)
    r.raise_for_status()
    return r


def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                    encoding="utf-8")


def local_time(iso: str | None) -> str:
    if not iso:
        return "—"
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TZ)
    return dt.strftime("%d/%m/%Y %H:%M")


def repo_link(rel_path: str) -> str | None:
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        return None
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    return f"https://github.com/{repo}/commits/{branch}/{rel_path}"


def event(kind: str, emoji: str, title: str, body: str, url: str | None = None,
          diff: list[str] | None = None, context: str = "", history: str | None = None) -> dict:
    """Un aviso. `context` es lo que se le pasa a Claude para resumir."""
    return {"kind": kind, "emoji": emoji, "title": title, "body": body, "url": url,
            "diff": diff or [], "context": context, "history": history}


# ------------------------------------------------------- 1. Status Dashboard

def check_status() -> tuple[list[dict], callable]:
    path = STATE / "status.json"
    known = load_json(path)
    first_run = known is None
    known = dict(known or {})
    events = []
    for inc in get(STATUS_JSON).json():
        iid = inc["id"]
        n_updates = len(inc.get("updates", []))
        end = inc.get("end")
        prev = known.get(iid)
        kind = None
        if not first_run:
            if prev is None:
                kind = "nuevo"
            elif end and not prev.get("end"):
                kind = "fin"
            elif n_updates > prev.get("n", 0):
                kind = "actualizacion"
        if kind:
            events.append(status_event(inc, kind))
        known[iid] = {"n": n_updates, "end": end, "name": inc.get("external_desc", "")}
    if first_run:
        events.append(event("info", "🟢", "Monitor del Status Dashboard activado",
                            f"Siguiendo {len(known)} incidentes recientes. Avisaré de los "
                            "nuevos, de sus actualizaciones y de cuándo terminan.",
                            STATUS_URL))
    return events, lambda: save_json(path, known)


def status_event(inc: dict, kind: str) -> dict:
    labels = {"nuevo": ("🚨", "Nuevo en el Status Dashboard"),
              "actualizacion": ("🔄", "Actualización en el Status Dashboard"),
              "fin": ("✅", "Terminado")}
    emoji, label = labels[kind]
    name = inc.get("external_desc", "Incidente")
    service = inc.get("service_name", "")
    last = (inc.get("most_recent_update") or {}).get("text", "").strip()
    body = (f"{service} · inicio {local_time(inc.get('begin'))}"
            + (f" · fin {local_time(inc.get('end'))}" if inc.get("end") else "")
            + f"\n\n{last}")
    url = urljoin(STATUS_URL, inc.get("uri", ""))
    context = f"Servicio: {service}\nIncidente: {name}\nTipo de aviso: {kind}\nTexto oficial:\n{last}"
    return event("status", emoji, f"{label}: {name}", body, url, context=context)


# ------------------------------------------------------------- 2. Blog

def check_blog() -> tuple[list[dict], callable]:
    path = STATE / "blog.json"
    seen = load_json(path)
    first_run = seen is None
    seen = list(seen or [])
    root = ET.fromstring(get(BLOG_FEED).content)
    items = []
    for it in root.iter("item"):
        link = (it.findtext("link") or "").strip()
        title = (it.findtext("title") or "").strip()
        desc = BeautifulSoup(it.findtext("description") or "", "lxml").get_text(" ", strip=True)
        if link:
            items.append((link, title, " ".join(desc.split())))
    events = []
    if not first_run:
        for link, title, desc in items:
            if link not in seen:
                events.append(event("blog", "📰", f"Blog de Search Central: {title}",
                                    desc[:700], link, context=f"Título: {title}\nEntradilla: {desc}"))
    seen = [link for link, _, _ in items] + [s for s in seen if s not in {l for l, _, _ in items}]
    return events, lambda: save_json(path, seen[:200])


# ------------------------------------------------------ 3. Rangos de IP

def check_ipranges() -> tuple[list[dict], callable]:
    events, writes = [], []
    for name, url in IP_RANGES.items():
        path = STATE / "ipranges" / f"{name}.txt"
        data = get(url).json()
        prefixes = sorted({p.get("ipv4Prefix") or p.get("ipv6Prefix")
                           for p in data.get("prefixes", [])} - {None})
        new_text = "\n".join(prefixes) + "\n"
        old_text = path.read_text(encoding="utf-8") if path.exists() else None
        if old_text is not None and old_text != new_text:
            old = set(old_text.split())
            added = [p for p in prefixes if p not in old]
            removed = sorted(old - set(prefixes))
            diff = [f"+ {p}" for p in added] + [f"- {p}" for p in removed]
            events.append(event("ipranges", "🌐", f"Cambian los rangos de IP: {name}",
                                f"{len(added)} rangos añadidos y {len(removed)} eliminados.",
                                url, diff=diff, history=repo_link(f"state/ipranges/{name}.txt")))
        if old_text != new_text:
            writes.append((path, new_text))

    def commit():
        for path, text in writes:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    return events, commit


# ------------------------------------------------------ 4. Documentación

SKIP_TAGS = {"script", "style", "noscript", "template", "devsite-hats-survey",
             "devsite-thumb-rating", "devsite-feedback", "button", "svg",
             "form", "textarea", "input", "select"}  # p. ej. el botón oculto del Rich Results Test
BLOCK_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "td", "th", "dt", "dd",
              "blockquote", "caption", "figcaption", "div", "ul", "ol", "dl", "table",
              "thead", "tbody", "tfoot", "tr", "section", "aside", "figure", "details",
              "summary", "devsite-code", "devsite-selector", "section", "article", "hr"}


def _prefix(tag: Tag) -> str:
    if tag.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
        return "#" * int(tag.name[1]) + " "
    if tag.name == "li":
        return "- "
    return ""


def _walk(node: Tag, out: list[str]) -> None:
    if node.name == "pre":
        out.extend("    " + line.rstrip() for line in node.get_text().splitlines() if line.strip())
        return
    buf: list[str] = []

    def flush():
        text = " ".join("".join(buf).split())
        buf.clear()
        if text:
            out.append(_prefix(node) + text)

    for child in node.children:
        if isinstance(child, Comment):
            continue
        if isinstance(child, NavigableString):
            buf.append(str(child))
        elif isinstance(child, Tag):
            if child.name in SKIP_TAGS:
                continue
            if child.name in BLOCK_TAGS or child.find(BLOCK_TAGS):
                flush()
                _walk(child, out)
            else:
                buf.append(child.get_text())
    flush()


def extract_page(html_text: str) -> tuple[str, list[str], set[str]] | None:
    soup = BeautifulSoup(html_text, "lxml")
    article = soup.select_one(".devsite-article-body")
    if article is None:
        return None
    links = {a["href"] for a in soup.select("a[href]")}
    title = (soup.title.get_text() if soup.title else "").split("|")[0].strip()
    lines: list[str] = []
    _walk(article, lines)
    return title, lines, links


def norm_path(href: str, base_url: str) -> str | None:
    u = urlsplit(urljoin(base_url, href))
    if u.netloc != "developers.google.com":
        return None
    path = u.path.rstrip("/") or "/"
    if not path.startswith(DOC_PREFIXES) or "." in path.rsplit("/", 1)[-1]:
        return None
    return path


def snapshot_path(page: str) -> Path:
    return DOCS_DIR / (page.lstrip("/") + ".md")


def fetch_doc(page: str) -> dict:
    """Devuelve {'status': ok|gone|moved|error, ...}."""
    url = f"{BASE}{page}?hl=en"
    try:
        r = SESSION.get(url, timeout=30)
    except requests.RequestException as e:
        return {"page": page, "status": "error", "error": str(e)}
    if r.status_code in (404, 410):
        return {"page": page, "status": "gone"}
    if r.status_code != 200:
        return {"page": page, "status": "error", "error": f"HTTP {r.status_code}"}
    final = norm_path(r.url, r.url) or urlsplit(r.url).path
    if final != page:
        return {"page": page, "status": "moved", "to": final}
    parsed = extract_page(r.text)
    if parsed is None:
        return {"page": page, "status": "error", "error": "sin cuerpo de artículo"}
    title, lines, hrefs = parsed
    links = {p for h in hrefs if (p := norm_path(h, r.url))}
    return {"page": page, "status": "ok", "title": title, "lines": lines, "links": links}


def render_snapshot(page: str, title: str, lines: list[str]) -> str:
    return f"# {title}\n<{BASE}{page}>\n\n" + "\n".join(lines) + "\n"


def doc_events(results: list[dict], baseline: bool) -> tuple[list[dict], list[tuple]]:
    """Compara cada página con su copia guardada. Devuelve avisos y escrituras."""
    events, writes = [], []
    for res in results:
        page = res["page"]
        path = snapshot_path(page)
        rel = path.relative_to(STATE.parent).as_posix() if STATE.parent in path.parents else path.as_posix()
        history = repo_link(rel)
        old = path.read_text(encoding="utf-8") if path.exists() else None
        url = f"{BASE}{page}"
        if res["status"] == "ok":
            new = render_snapshot(page, res["title"], res["lines"])
            if old == new:
                continue
            writes.append((path, new))
            if baseline:
                continue
            if old is None:
                preview = "\n".join(res["lines"][:6])
                events.append(event("doc_new", "🆕", f"Página nueva: {res['title']}",
                                    preview[:600], url, context=f"Página nueva.\n{new[:20000]}",
                                    history=history))
            else:
                diff = [l for l in difflib.unified_diff(old.splitlines(), new.splitlines(),
                                                         lineterm="", n=2)
                        if not l.startswith(("---", "+++"))]
                changed = [l for l in diff if l[:1] in "+-"]
                events.append(event("doc_change", "📝", f"Cambio en la documentación: {res['title']}",
                                    f"{sum(l[:1] == '+' for l in changed)} líneas añadidas, "
                                    f"{sum(l[:1] == '-' for l in changed)} eliminadas.",
                                    url, diff=changed,
                                    context=f"Página: {res['title']}\nURL: {url}\nDiff:\n" + "\n".join(diff),
                                    history=history))
        elif res["status"] in ("gone", "moved") and old is not None:
            writes.append((path, None))
            title = old.splitlines()[0].lstrip("# ").strip()
            if res["status"] == "gone":
                events.append(event("doc_gone", "🗑️", f"Página eliminada: {title}",
                                    "La página ya devuelve 404.", url, history=history))
            else:
                events.append(event("doc_moved", "↪️", f"Página redirigida: {title}",
                                    f"Ahora redirige a {BASE}{res['to']}", f"{BASE}{res['to']}",
                                    history=history))
    return events, writes


def apply_writes(writes: list[tuple]) -> None:
    for path, text in writes:
        if text is None:
            path.unlink(missing_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")


def known_pages() -> list[str]:
    if not DOCS_DIR.exists():
        return []
    return sorted("/" + p.relative_to(DOCS_DIR).as_posix()[:-3] for p in DOCS_DIR.rglob("*.md"))


def check_fast_pages() -> tuple[list[dict], callable]:
    if not known_pages():          # la línea base la crea el modo docs
        return [], lambda: None
    results = [fetch_doc(p) for p in FAST_PAGES]
    events, writes = doc_events([r for r in results if r["status"] != "error"], baseline=False)
    return events, lambda: apply_writes(writes)


def check_docs() -> tuple[list[dict], callable]:
    previous = known_pages()
    baseline = not previous
    queue = list(dict.fromkeys(DOC_SEEDS + previous))
    seen = set(queue)
    results: list[dict] = []
    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        while queue and len(results) < MAX_DOC_PAGES:
            batch, queue = queue, []
            for res in pool.map(fetch_doc, batch):
                results.append(res)
                for link in res.get("links", ()):
                    if link not in seen:
                        seen.add(link)
                        queue.append(link)
                if res["status"] == "moved" and res["to"] not in seen \
                        and res["to"].startswith(DOC_PREFIXES):
                    seen.add(res["to"])
                    queue.append(res["to"])
    errors = [r for r in results if r["status"] == "error"]
    ok = [r for r in results if r["status"] == "ok"]
    print(f"docs: {len(ok)} páginas leídas, {len(errors)} errores")
    if len(errors) > max(10, len(results) * 0.2):
        raise RuntimeError(f"Demasiados errores leyendo la documentación ({len(errors)}); "
                           "no se toca el estado en esta pasada.")
    events, writes = doc_events([r for r in results if r["status"] != "error"], baseline)
    if baseline:
        events = [event("info", "🟢", "Monitor de documentación activado",
                        f"Línea base creada con {len(ok)} páginas de /search/docs y /crawling/docs. "
                        "A partir de ahora avisaré de cada cambio.", f"{BASE}/search/docs")]
    elif len([e for e in events if e["kind"].startswith("doc_")]) > MASS_CHANGE:
        doc = [e for e in events if e["kind"].startswith("doc_")]
        listing = "\n".join(f"• {e['title'].split(': ', 1)[-1]}" for e in doc[:30])
        events = [e for e in events if not e["kind"].startswith("doc_")] + [
            event("doc_mass", "📚", f"{len(doc)} páginas de la documentación han cambiado a la vez",
                  "Puede ser una reorganización o un cambio de plantilla. Revisa el historial.\n\n"
                  + listing, repo_link("state/docs"))]
    return events, lambda: apply_writes(writes)


# ------------------------------------------------------ 5. Quality Rater Guidelines

def check_qrg() -> tuple[list[dict], callable]:
    path = STATE / "qrg.json"
    old = load_json(path)
    r = get(QRG_PDF)
    new = {"sha256": hashlib.sha256(r.content).hexdigest(), "bytes": len(r.content),
           "last_modified": r.headers.get("Last-Modified")}
    events = []
    if old and old.get("sha256") != new["sha256"]:
        events.append(event("qrg", "📘", "Nueva versión de las Quality Rater Guidelines",
                            f"El PDF ha cambiado ({old.get('bytes')} → {new['bytes']} bytes, "
                            f"Last-Modified: {new['last_modified']}).", QRG_PDF))
    return events, (lambda: save_json(path, new)) if old != new else (lambda: None)


# ------------------------------------------------------ Resumen con Claude

SYSTEM_PROMPT = (
    "Eres un consultor SEO senior. Recibes un cambio detectado automáticamente en una fuente "
    "oficial de Google Search: su documentación, su Status Dashboard o su blog. Explica en "
    "español, en 2 a 4 frases directas, qué ha cambiado exactamente y qué implicación práctica "
    "tiene para quien hace SEO. Si el cambio es solo cosmético (erratas, formato, enlaces, "
    "reordenación sin cambio de significado), dilo en una sola frase. No inventes nada que no "
    "esté en el texto recibido. Responde en texto plano, sin Markdown ni saludos."
)


MAX_CONTEXT_CHARS = 400_000


def summarize(events: list[dict]) -> None:
    """Añade ev['summary']. Usa DeepSeek si hay DEEPSEEK_API_KEY; si no, Claude
    si hay ANTHROPIC_API_KEY; si no hay ninguna, los avisos van sin resumen."""
    pending = [ev for ev in events if ev["context"]]
    for ev in pending:
        if len(ev["context"]) > MAX_CONTEXT_CHARS:
            ev["summary"] = "(El cambio es demasiado grande para resumirlo automáticamente.)"
    pending = [ev for ev in pending if "summary" not in ev]
    if not pending:
        return
    if os.environ.get("DEEPSEEK_API_KEY"):
        summarize_deepseek(pending)
    elif os.environ.get("ANTHROPIC_API_KEY"):
        summarize_claude(pending)


def summarize_deepseek(events: list[dict]) -> None:
    key = os.environ["DEEPSEEK_API_KEY"]
    model = os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")
    for ev in events:
        try:
            r = SESSION.post(
                "https://api.deepseek.com/chat/completions", timeout=120,
                headers={"Authorization": f"Bearer {key}"},
                json={"model": model,
                      "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                                   {"role": "user", "content": ev["context"]}],
                      "thinking": {"type": "disabled"},
                      "max_tokens": 1000,
                      "temperature": 0.3,
                      "stream": False})
            if r.status_code != 200:
                print(f"::warning::DeepSeek respondió {r.status_code} al resumir "
                      f"«{ev['title']}»: {r.text[:300]}")
                if r.status_code in (401, 402, 403):   # key mala o sin saldo: no insistir
                    return
                continue
            choice = r.json()["choices"][0]
        except (requests.RequestException, ValueError, KeyError, IndexError) as e:
            print(f"::warning::DeepSeek no pudo resumir «{ev['title']}»: {e}")
            continue
        text = (choice.get("message") or {}).get("content") or ""
        if choice.get("finish_reason") in ("stop", "length") and text.strip():
            ev["summary"] = text.strip()


def summarize_claude(events: list[dict]) -> None:
    import anthropic
    client = anthropic.Anthropic()
    for ev in events:
        try:
            resp = client.beta.messages.create(
                model="claude-opus-5-5",
                max_tokens=4000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                output_config={"effort": "low"},
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": ev["context"]}],
            )
        except anthropic.APIError as e:
            print(f"Claude no pudo resumir «{ev['title']}»: {e}", file=sys.stderr)
            continue
        if resp.stop_reason == "refusal":
            continue
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        if text:
            ev["summary"] = text


# ------------------------------------------------------ Notificaciones

def diff_snippet(diff: list[str], limit_chars: int = 1500) -> str:
    lines = [l if len(l) <= 300 else l[:297] + "…" for l in diff[:MAX_DIFF_LINES]]
    text = "\n".join(lines)
    if len(text) > limit_chars:
        text = text[:limit_chars] + "…"
    if len(diff) > MAX_DIFF_LINES:
        text += f"\n… y {len(diff) - MAX_DIFF_LINES} líneas más"
    return text


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def telegram_text(ev: dict) -> str:
    parts = [f"<b>{ev['emoji']} {esc(ev['title'])}</b>"]
    if ev.get("summary"):
        parts.append("🤖 " + esc(ev["summary"]))
    parts.append(esc(ev["body"]))
    if ev["diff"]:
        parts.append(f"<pre>{esc(diff_snippet(ev['diff']))}</pre>")
    links = []
    if ev["url"]:
        links.append(f'<a href="{html.escape(ev["url"])}">Abrir</a>')
    if ev.get("history"):
        links.append(f'<a href="{html.escape(ev["history"])}">Historial / diff completo</a>')
    if links:
        parts.append(" · ".join(links))
    text = "\n\n".join(parts)
    if len(text) > 4000:  # límite de Telegram: 4096
        text = "\n\n".join(p for p in parts if not p.startswith("<pre>"))[:4000]
    return text


def ntfy_payload(ev: dict, topic: str) -> dict:
    parts = []
    if ev.get("summary"):
        parts.append(ev["summary"])
    parts.append(ev["body"])
    if ev["diff"]:
        parts.append("```\n" + diff_snippet(ev["diff"], 1200) + "\n```")
    if ev.get("history"):
        parts.append(f"[Historial / diff completo]({ev['history']})")
    payload = {"topic": topic, "title": f"{ev['emoji']} {ev['title']}"[:250],
               "message": "\n\n".join(parts)[:3800], "markdown": True,
               "priority": 5 if ev["kind"] == "status" else 3}
    if ev["url"]:
        payload["click"] = ev["url"]
    return payload


def notify(events: list[dict], dry_run: bool) -> None:
    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID")
    ntfy_topic = os.environ.get("NTFY_TOPIC")
    ntfy_server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    channels = (bool(tg_token and tg_chat), bool(ntfy_topic))
    for ev in events:
        if dry_run or not any(channels):
            print("\n" + "=" * 70 + "\n" + telegram_text(ev))
            continue
        if channels[0]:
            r = SESSION.post(f"https://api.telegram.org/bot{tg_token}/sendMessage", timeout=30,
                             json={"chat_id": tg_chat, "text": telegram_text(ev),
                                   "parse_mode": "HTML", "disable_web_page_preview": True})
            if r.status_code != 200:
                raise RuntimeError(f"Telegram respondió {r.status_code}: {r.text[:300]}")
        if channels[1]:
            r = SESSION.post(ntfy_server, json=ntfy_payload(ev, ntfy_topic), timeout=30)
            r.raise_for_status()
        time.sleep(1)
    if events and not dry_run and not any(channels):
        print("\n(No hay ningún canal configurado: define TELEGRAM_BOT_TOKEN + "
              "TELEGRAM_CHAT_ID o NTFY_TOPIC para recibir los avisos.)")


# ------------------------------------------------------ main

def heartbeat() -> None:
    """Un commit al mes para que GitHub no desactive el cron por inactividad."""
    path = STATE / "heartbeat.txt"
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    if not path.exists() or path.read_text().strip() != month:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(month + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["fast", "docs", "all", "test"])
    ap.add_argument("--dry-run", action="store_true",
                    help="no envía nada: imprime los avisos (y sí guarda el estado)")
    args = ap.parse_args()

    if args.mode == "test":
        ev = event("test", "🧪", "Prueba del monitor de Google Search",
                   "Si lees esto, las notificaciones funcionan.", STATUS_URL,
                   diff=["+ línea añadida de ejemplo", "- línea eliminada de ejemplo"],
                   context="Cambio de prueba: Google ha añadido la frase «línea añadida de "
                           "ejemplo» y ha quitado «línea eliminada de ejemplo».")
        summarize([ev])
        notify([ev], args.dry_run)
        print("Resumen IA: " + (ev.get("summary") or "(no configurado o sin respuesta)"))
        return 0

    checks = []
    if args.mode in ("fast", "all"):
        checks += [check_status, check_blog, check_ipranges, check_fast_pages]
    if args.mode in ("docs", "all"):
        checks += [check_docs, check_qrg]

    events, commits, failures = [], [], []
    for check in checks:
        try:
            evs, commit = check()
        except Exception as e:  # una fuente caída no debe tapar a las demás
            failures.append(f"{check.__name__}: {e}")
            # Aviso en el log de Actions sin marcar la ejecución como fallida:
            # un fallo puntual de una fuente se reintenta solo en la siguiente pasada.
            print(f"::warning::{check.__name__} falló: {e}")
            continue
        events += evs
        commits.append(commit)

    summarize(events)
    notify(events, args.dry_run)       # si falla, no se guarda el estado y se reintenta
    for commit in commits:
        commit()
    if args.mode in ("fast", "all"):
        heartbeat()
    print(f"\n{len(events)} aviso(s) enviados. Fuentes con error: {len(failures)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
