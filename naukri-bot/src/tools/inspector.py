"""Global stuck-resolver tool. Reusable by every site bot (Naukri, LinkedIn,
future boards): when the normal flow gets stuck, this tool looks at the
live page like a human opening Inspect Element, figures out what is
actually there and what to do, and the brain decides the action.

Division of labor (perception vs secrets):
- The TOOL reads structure: URL, title, headings, error banners, and a
  compact list of visible interactive elements (never field VALUES).
- The BRAIN (AI model) decides: which element (by ref) + what kind of
  action, returned as strict JSON.
- SECRETS NEVER reach the model: for credential fills the model only
  outputs a *purpose* ("email"/"password") and the caller maps it to the
  real value locally via fill_map.

Main entry: resolve_stuck(page, goal, context="", fill_map=None)
-> {"ok": bool, "diagnosis": str, "detail": str}
"""
from __future__ import annotations

import json

from loguru import logger
from playwright.async_api import Page

from src.browser.human import act_delay, human_type, nap

SNAP_SELECTOR = ("input,select,textarea,button,a,"
                 "[role=button],[role=checkbox],[role=radio]")

MAX_ELEMENTS = 40

# Never touch these, no matter what the model says.
DENY_TEXT = ("log out", "logout", "sign out", "delete account",
             "close account", "report", "block user")

_SNAP_JS = """() => {
  const vis = n => { try { const r = n.getBoundingClientRect();
    return r.width > 0 && r.height > 0; } catch (e) { return false; } };
  const out = {url: location.href, title: document.title,
               headings: [], alerts: [], body: '', elements: []};
  try {
    out.headings = [...document.querySelectorAll('h1,h2,h3')]
      .filter(vis).map(e => e.innerText.trim().slice(0, 120))
      .filter(Boolean).slice(0, 8);
  } catch (e) {}
  try {
    out.alerts = [...document.querySelectorAll('[role=alert],.alert,.error')]
      .filter(vis).map(e => e.innerText.trim().slice(0, 200))
      .filter(Boolean).slice(0, 5);
  } catch (e) {}
  try {
    out.body = (document.body ? document.body.innerText : '')
      .trim().replace(/\\s+/g, ' ').slice(0, 800);
  } catch (e) {}
  try {
    const nodes = [...document.querySelectorAll(
      "input,select,textarea,button,a,"
      + "[role=button],[role=checkbox],[role=radio]")];
    let ref = 0;
    for (const n of nodes) {
      if (!vis(n) || ref >= 40) {
        if (ref >= 40) break;
        continue;
      }
      n.setAttribute('data-inspect-ref', String(ref));
      const cls = (typeof n.className === 'string' ? n.className : '')
        .split(' ').filter(Boolean).slice(0, 2).join('.');
      let label = '';
      try {
        label = ((n.getAttribute('aria-label') || '') + ' '
          + (n.innerText || '')).trim().replace(/\\s+/g, ' ').slice(0, 60);
      } catch (e) {}
      out.elements.push({
        ref: ref,
        tag: (n.tagName || '').toLowerCase(),
        type: n.type || '',
        text: label,
        id: (n.id || '').slice(0, 40),
        name: (n.name || '').slice(0, 40),
        placeholder: ((n.placeholder || '').slice(0, 60)),
        value_present: !!(n.value && String(n.value).length > 0),
        checked: n.checked === true,
        disabled: n.disabled === true,
      });
      ref += 1;
    }
  } catch (e) {}
  return out;
}"""


async def snapshot_page(page: Page) -> dict:
    """DOM snapshot: structure only, never field values."""
    try:
        snap = await page.evaluate(_SNAP_JS)
        if isinstance(snap, dict):
            snap.setdefault("elements", [])
            return snap
    except Exception as e:
        logger.debug(f"inspector snapshot: {e}")
    try:
        return {"url": page.url, "title": "", "headings": [],
                "alerts": [], "body": "", "elements": []}
    except Exception:
        return {"url": "", "title": "", "headings": [],
                "alerts": [], "body": "", "elements": []}


def _parse_decision(raw: str):
    """Strict JSON extraction. Returns dict or None (never raises)."""
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        d = json.loads(raw[start:end])
        act = d.get("action", {})
        t = str(act.get("type", "")).strip().lower()
        if t not in ("click", "fill", "select", "wait", "snapshot", "give_up"):
            return None
        try:
            target = int(act.get("target", -1))
        except (TypeError, ValueError):
            target = -1
        return {
            "diagnosis": str(d.get("diagnosis", ""))[:300],
            "action": t,
            "target": target,
            "value": str(act.get("value", ""))[:500],
            "purpose": str(act.get("purpose") or "")[:50],
            "reason": str(d.get("reason", ""))[:300],
        }
    except Exception:
        return None


async def _resolve_ref(page: Page, ref: int):
    try:
        if ref is None or int(ref) < 0:
            return None
        el = await page.query_selector(f'[data-inspect-ref="{int(ref)}"]')
        if el and await el.is_visible():
            return el
    except Exception:
        pass
    return None


def _denied(el_text: str) -> bool:
    low = (el_text or "").lower()
    return any(d in low for d in DENY_TEXT)


async def _apply(page: Page, dec: dict, fill_map: dict | None) -> tuple[bool, str]:
    """Execute the decided action. Returns (ok, detail)."""
    t = dec["action"]
    if t in ("snapshot", "give_up"):
        return False, f"no action ({t}): {dec['reason']}"[:200]
    if t == "wait":
        from src.browser.human import nap as _nap
        await _nap(2, 4)
        return True, "waited for page to settle"
    el = await _resolve_ref(page, dec["target"])
    if el is None:
        return False, f"target ref {dec['target']} not found"
    try:
        txt = ((await el.inner_text()) or "").strip()[:80]
    except Exception:
        txt = ""
    if _denied(txt):
        return False, f"refused destructive target: {txt}"[:120]
    try:
        if t == "click":
            await act_delay()
            try:
                await el.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass
            await el.click(timeout=5000)
            return True, f"clicked ref {dec['target']} ({txt})"[:200]
        if t == "fill":
            val = None
            if dec["purpose"] and fill_map:
                val = fill_map.get(dec["purpose"])
            if val is None:
                val = dec["value"]
            if not val:
                return False, "fill with empty value refused"
            await human_type(el, val)
            return True, f"filled ref {dec['target']} ({txt or dec['purpose']})"[:200]
        if t == "select":
            want = (dec["value"] or "").strip().lower()
            if not want:
                return False, "select with empty value refused"
            pairs = await el.evaluate(
                "e => Array.from(e.options || []).map(o => ({t: (o.text || '').trim(), v: o.value}))")
            val = None
            for p in pairs:
                if p["t"] and p["t"].lower() == want:
                    val = p["v"]
                    break
            if val is None and len(want) > 3:
                for p in pairs:
                    if p["t"] and (want in p["t"].lower() or p["t"].lower() in want):
                        val = p["v"]
                        break
            if val is None:
                return False, f"option '{dec['value'][:40]}' not in dropdown"
            await el.evaluate(
                "(el, v) => { el.value = v; el.dispatchEvent(new Event('change', {bubbles:true})); }",
                val)
            return True, f"selected '{dec['value'][:40]}'"
    except Exception as e:
        return False, f"action failed: {type(e).__name__}"
    return False, "unknown action"


async def resolve_stuck(page: Page, goal: str, context: str = "",
                        fill_map: dict | None = None) -> dict:
    """One stuck-resolution cycle: look -> brain decides -> act.

    Logs exactly what the tool sees and decides (INFO, so it shows in the
    terminal next to Q/A lines). Returns {"ok", "diagnosis", "detail"}.
    The CALLER verifies the outcome and continues its own flow.
    """
    from src.brain.ai_client import complete
    from src.brain.prompts import build_inspect_prompt

    snap = await snapshot_page(page)
    logger.info(
        f"Inspector sees ({(snap.get('url') or '')[:80]}): "
        f"{len(snap.get('elements', []))} interactive elements, "
        f"headings={snap.get('headings', [])[:3]}, alerts={snap.get('alerts', [])[:2]}")
    try:
        system, user = build_inspect_prompt(snap, goal, context)
        raw = (await complete(system, user, max_tokens=250, temperature=0.1)).strip()
    except Exception as e:
        logger.debug(f"inspector transport failed: {e}")
        return {"ok": False, "diagnosis": "model unreachable", "detail": str(e)[:150]}
    dec = _parse_decision(raw)
    if dec is None:
        logger.warning(f"Inspector output unparseable, no action taken. Raw: {raw[:200]}")
        return {"ok": False, "diagnosis": "unparseable decision", "detail": raw[:200]}
    logger.info(f"Inspector diagnosis: {dec['diagnosis'][:150]}")
    logger.info(f"Inspector action: {dec['action']} ref={dec['target']} "
                f"{('purpose=' + dec['purpose']) if dec['purpose'] else ''} ({dec['reason'][:120]})")
    ok, detail = await _apply(page, dec, fill_map or {})
    logger.info(f"Inspector result: ok={ok} ({detail[:150]})")
    return {"ok": ok, "diagnosis": dec["diagnosis"], "detail": detail}
