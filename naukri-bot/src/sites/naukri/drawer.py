"""Drawer QA tool — built against Naukri's real chatbot drawer.

Real structure (captured from live page):
  div.chatbot_Drawer
    li.botItem .botMsg span   -> chat messages; LAST one = current question
    .ssrc__radio + label      -> single-select options (Yes / No / Skip this question)
    div.textArea[contenteditable] -> free-text answers (hidden via d-none for choice Qs)
    div.sendMsg ("Save")      -> submit; a DIV, not a button. Parent .send.disabled
                                until answered.
    input.chatbot_Uploader    -> resume file; touch ONLY when explicitly asked.

Phases per round: READ current question -> ANSWER visible widget -> SAVE.
Repeat until drawer closes or success text appears.
"""
from __future__ import annotations

import random
from loguru import logger
from playwright.async_api import Page

from src.brain.ai_client import ai_answer
from src.brain.rules import rule_answer, strip_to_number
from src.browser.human import nap
from src.config.candidate import CANDIDATE
from src.config.settings import SETTINGS

DRAWER_SELECTORS = [
    "div.chatbot_Drawer",
    "div[class*='chatbot_Drawer']",
    "div[class*='chatbot']",
    "div[class*='drawer']",
    "div[class*='modal']",
]

GREETING_HINTS = ("thank you for showing interest", "kindly answer all")

SUCCESS_TEXTS = (
    "application submitted",
    "successfully applied",
    "you have applied",
    "applied successfully",
)

ERROR_HINTS = ("number", "digit", "numeric", "invalid", "enter valid", "only digits")


async def _drawer_scope(page: Page):
    for sel in DRAWER_SELECTORS:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                return el
        except Exception:
            pass
    return await page.query_selector("body")


async def read_current_question(scope) -> str:
    """READ ONLY. Returns the latest bot question, '' if none yet."""
    try:
        spans = await scope.query_selector_all("li.botItem .botMsg span, li.botItem .botMsg")
        texts = []
        for s in spans:
            try:
                t = (await s.inner_text()).strip()
                if t:
                    texts.append(t)
            except Exception:
                pass
        if not texts:
            return ""
        if len(texts) == 1 and any(h in texts[0].lower() for h in GREETING_HINTS):
            return ""  # greeting only, question not loaded yet
        for t in reversed(texts):  # latest non-greeting message
            if not any(h in t.lower() for h in GREETING_HINTS):
                return t[:500]
        return texts[-1][:500]
    except Exception:
        return ""


async def _radio_options(scope) -> list[tuple[object, str]]:
    """Visible single-select radios as (input_el, label)."""
    out = []
    try:
        els = await scope.query_selector_all("input.ssrc__radio, input[type='radio']")
        for el in els:
            try:
                if not await el.is_visible():
                    continue
                lab = await el.evaluate(
                    """e => {
                      const l = e.id ? document.querySelector(`label[for="${CSS.escape(e.id)}"]`) : null;
                      const t = l ? l.innerText : ((e.closest('div') || {}).innerText || '');
                      return (t || '').trim().slice(0, 60);
                    }"""
                )
                if lab:
                    out.append((el, lab))
            except Exception:
                pass
    except Exception:
        pass
    return out


async def _chat_box(scope):
    """Visible contenteditable answer box, or None."""
    try:
        els = await scope.query_selector_all("div.textArea[contenteditable='true'], div[contenteditable='true']")
        for el in els:
            try:
                if await el.is_visible():
                    return el
            except Exception:
                pass
    except Exception:
        pass
    return None


async def _type_chat(page: Page, el, text: str) -> str:
    """Human-like typing into contenteditable. Returns text actually present."""
    await el.click()
    await nap(0.3, 0.6)
    await el.evaluate("e => { e.focus(); document.execCommand('selectAll', false, null); }")
    for ch in text:
        await page.keyboard.type(ch, delay=random.randint(40, 120))
    await nap(0.2, 0.5)
    try:
        return ((await el.inner_text()) or "").strip()
    except Exception:
        return text


async def _click_save(scope, page: Page) -> bool:
    """Click the Save/Submit div. Waits for it to enable first."""
    for _ in range(10):  # ~5s for .send.disabled to clear after answering
        try:
            send = await scope.query_selector(".sendMsgbtn_container .send, .sendMsgbtn_container")
            if send:
                cls = (await send.get_attribute("class")) or ""
                if "disabled" not in cls:
                    break
        except Exception:
            pass
        await nap(0.4, 0.6)
    for sel in ("div.sendMsg", ".sendMsg"):
        try:
            btn = await scope.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                return True
        except Exception:
            pass
    # fallback: any button-ish submit
    for sel in ("button:has-text('Save')", "button:has-text('Submit')", "button:has-text('Continue')"):
        try:
            btn = await scope.query_selector(sel) or await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                return True
        except Exception:
            pass
    return False


async def _answer_radio(scope, question: str) -> bool:
    opts = await _radio_options(scope)
    if not opts:
        return False
    labels = [lab for _, lab in opts]
    best = rule_answer(question, labels)
    if len(best) < 2 and labels:
        best = await ai_answer(question, labels)
    logger.info(f"Q: {question[:90]} -> A(radio): {best}")
    for el, lab in opts:
        if best.lower().strip() in lab.lower() or lab.lower() in best.lower().strip():
            await el.evaluate(
                """e => {
                  const l = e.id ? document.querySelector(`label[for="${CSS.escape(e.id)}"]`) : null;
                  (l || e).click();
                }"""
            )
            await nap(0.5, 1.0)
            return True
    if not hit and opts:
        el0 = opts[0][0]
        await el0.evaluate(
            """e => {
              const l = e.id ? document.querySelector(`label[for="${CSS.escape(e.id)}"]`) : null;
              (l || e).click();
            }"""
        )
        await nap(0.5, 1.0)
        return True
    return False


async def _answer_text(page: Page, scope, question: str) -> bool:
    from src.brain.understand import understand_and_answer

    ans = await understand_and_answer(question, [])
    if len(question.strip()) < 3 and ans in ("Yes", "No"):
        ans = CANDIDATE["exp"]  # bare unlabeled numeric box = experience
    logger.info(f"Q: {question[:90]} -> A(text): {ans}")
    box = await _chat_box(scope)
    if not box:
        return False
    present = await _type_chat(page, box, ans)
    if not present:
        return False
    # number-only validation retry
    try:
        drawer_txt = ((await scope.inner_text()) or "").lower()
    except Exception:
        drawer_txt = ""
    if any(h in drawer_txt for h in ERROR_HINTS) or (ans != strip_to_number(ans) and not present):
        bare = strip_to_number(ans)
        if bare != ans:
            logger.info(f"Validation wants number-only, retrying '{bare}'")
            present = await _type_chat(page, box, bare)
    return bool(present)


async def _answer_checkbox(scope, question: str) -> bool:
    import re as _re

    from src.brain.rules import pick_experience_option
    from src.config.candidate import SKILLS

    try:
        boxes = []
        for el in await scope.query_selector_all("input[type='checkbox']"):
            try:
                if not await el.is_visible():
                    continue
                lab = await el.evaluate(
                    "e => ((e.closest('label') || e.parentElement || {}).innerText || '').trim()"
                )
                if lab:
                    boxes.append((el, lab))
            except Exception:
                pass
        if not boxes:
            return False
        labels = [lab for _, lab in boxes]
        looks_like_bands = any(_re.search(r"\d\s*[-–+]", lab) for lab in labels)
        is_exp_q = looks_like_bands or any(
            k in question.lower() for k in ("experience", "exp ", "total year", "years")
        )
        if is_exp_q and looks_like_bands:
            # "Total Years of experience" [1-2, 2-3, 3-4, 4-5, 5+] -> tick 3-4 only.
            best = pick_experience_option(labels)
            logger.info(f"Q: {question[:90]} -> A(checkbox band): {best}")
            for el, lab in boxes:
                try:
                    if lab == best and not await el.is_checked():
                        await el.check()
                        return True
                except Exception:
                    pass
            return False
    except Exception:
        pass
    hit = False
    try:
        els = await scope.query_selector_all("input[type='checkbox']")
        for el in els:
            try:
                if not await el.is_visible() or await el.is_checked():
                    continue
                lab = await el.evaluate(
                    "e => ((e.closest('label') || e.parentElement || {}).innerText || '').trim().toLowerCase()"
                )
                if any(s in lab for s in SKILLS if len(s) > 2):
                    await el.check()
                    hit = True
            except Exception:
                pass
    except Exception:
        pass
    if hit:
        logger.info(f"Q: {question[:90]} -> A(checkbox): resume skills ticked")
        return True
    # Universal fallback: neither skills nor bands matched (e.g. preferred
    # cities, work modes as ticks). Pick best option via rules and tick it.
    # Exact match first; containment only for long labels to avoid
    # substring traps ("Male" is inside "Female").
    try:
        from src.brain.rules import rule_answer as _rule

        seen_boxes = []
        for el in await scope.query_selector_all("input[type='checkbox']"):
            try:
                if not await el.is_visible() or await el.is_checked():
                    continue
                lab = await el.evaluate(
                    "e => ((e.closest('label') || e.parentElement || {}).innerText || '').trim()"
                )
                if lab:
                    seen_boxes.append((el, lab))
            except Exception:
                pass
        if seen_boxes:
            labels = [lab for _, lab in seen_boxes]
            best = _rule(question or "choose option", labels)
            bl = best.lower().strip()
            ticked = False
            for el, lab in seen_boxes:  # pass 1: exact
                if lab.lower().strip() == bl:
                    await el.check()
                    ticked = True
            if not ticked and len(bl) > 4:  # pass 2: containment
                for el, lab in seen_boxes:
                    ll = lab.lower()
                    if bl in ll or ll in bl:
                        await el.check()
                        ticked = True
                        break
            if ticked:
                logger.info(f"Q: {question[:90]} -> A(checkbox fallback): {best}")
                return True
    except Exception as e:
        logger.debug(f"checkbox fallback: {e}")
    return False


async def _answer_file(scope, question: str) -> bool:
    """Resume ONLY when explicitly asked — never blind uploads."""
    if not any(k in question.lower() for k in ("resume", "cv ", "cv", "profile", "upload")):
        return False
    try:
        els = await scope.query_selector_all("input.chatbot_Uploader, input[type='file']")
        for el in els:
            try:
                await el.evaluate("e => { e.style.display='block'; e.style.visibility='visible'; }")
                await el.set_input_files(SETTINGS.resume_path)
                logger.info("Resume uploaded (explicitly requested in drawer)")
                return True
            except Exception as e:
                logger.debug(f"resume upload: {e}")
    except Exception:
        pass
    return False


async def _drawer_gone(page: Page) -> bool:
    try:
        el = await page.query_selector("div.chatbot_Drawer")
        return not el or not await el.is_visible()
    except Exception:
        return True


async def _success(page: Page) -> bool:
    # Rendered text only — page.content() includes <script> source which
    # can contain false-positive phrases.
    try:
        txt = ((await page.evaluate("document.body ? document.body.innerText : ''")) or "")[:12000].lower()
        return any(s in txt for s in SUCCESS_TEXTS)
    except Exception:
        return False


async def _count_questions(scope) -> int:
    try:
        return len(await scope.query_selector_all("li.botItem"))
    except Exception:
        return 0


async def solve_drawer(page: Page, max_rounds: int = 10) -> bool:
    """READ current question -> ANSWER visible widget -> SAVE. Repeat per question."""
    scope = await _drawer_scope(page)
    stuck = 0  # consecutive rounds with a question but no answerable widget
    for rnd in range(max_rounds):
        if await _success(page):
            return True
        if await _drawer_gone(page):
            return await _success(page)
        scope = await _drawer_scope(page)
        question = await read_current_question(scope)
        if not question:
            await nap(1.2, 2.0)
            scope = await _drawer_scope(page)
            question = await read_current_question(scope)
            if not question:
                return await _success(page) or await _drawer_gone(page)
        logger.info(f"[round {rnd+1}] Q: {question[:120]}")
        before = await _count_questions(scope)
        answered = False
        if await _radio_options(scope):
            answered = await _answer_radio(scope, question)
        elif await _chat_box(scope):
            answered = await _answer_text(page, scope, question)
        elif await _answer_checkbox(scope, question):
            answered = True
        elif await _answer_file(scope, question):
            answered = True
        else:
            stuck += 1
            logger.warning(f"No answer widget visible for: {question[:100]} (stuck {stuck})")
            if stuck >= 2:
                # Question may be optional or already answered — try advancing.
                logger.info("Trying Save to advance past widget-less question")
                stuck = 0
                if await _click_save(scope, page):
                    await nap(1.5, 2.5)
                    continue
            await nap(1.5, 2.5)
            continue
        stuck = 0
        if not answered:
            continue
        await nap(0.6, 1.2)
        if not await _click_save(scope, page):
            logger.warning("Save button not clickable")
            continue
        # wait for next question / close / success
        for _ in range(16):
            await nap(0.5, 0.7)
            if await _success(page) or await _drawer_gone(page):
                break
            try:
                scope = await _drawer_scope(page)
                if await _count_questions(scope) > before:
                    break
            except Exception:
                break
        await nap(0.8, 1.4)
    if await _success(page):
        return True
    return await _drawer_gone(page)
