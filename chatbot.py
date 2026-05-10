"""Naukri chatbot handler — detects and answers chatbot questions after clicking Apply."""
from __future__ import annotations

import logging
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from answer_engine import answer_question, rule_answer, llm_answer
from login import human_delay, human_type

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants: confirmed Naukri chatbot selectors (verified March 2026)
# ---------------------------------------------------------------------------
PANEL_SEL = ".chatbot_Drawer"
CHAT_LIST_SEL = 'ul.list[id^="chatList_"]'
BOT_MSG_SEL = "li.botItem div.botMsg"
RADIO_CONTAINER_SEL = ".ssrc__radio-btn-container"
RADIO_INPUT_SEL = ".ssrc__radio"
TEXT_INPUT_SEL = "div.textArea"
CLOSE_SEL = ".crossIcon.chatBot"

CITY_ALIASES = {
    "bangalore": "bengaluru", "bengaluru": "bangalore",
    "mumbai": "bombay", "bombay": "mumbai",
    "chennai": "madras", "madras": "chennai",
    "kolkata": "calcutta", "calcutta": "kolkata",
}

# ---------------------------------------------------------------------------
# Snapshot JS — reads chatbot panel state in one evaluate call
# ---------------------------------------------------------------------------
SNAPSHOT_JS = """() => {
    const panel = document.querySelector('.chatbot_Drawer');
    if (!panel) return null;

    // Tag panel for later submit calls
    panel.setAttribute('data-nk-panel', '1');

    // --- Question: last bot message ---
    let question = '';
    const botMsgs = panel.querySelectorAll('li.botItem div.botMsg');
    if (botMsgs.length > 0) {
        question = botMsgs[botMsgs.length - 1].textContent.trim();
    }

    // --- Radio options (.ssrc__radio-btn-container + generic fallback) ---
    const options = [];
    const skipOptionRe = /skip\\s*(this)?\\s*question/i;
    const seenOpts = new Set();
    let hasSkip = false;

    // Naukri-specific radio containers
    panel.querySelectorAll('.ssrc__radio-btn-container').forEach(container => {
        const label = container.querySelector('label');
        const input = container.querySelector('input');
        if (label) {
            const t = label.textContent.trim();
            if (skipOptionRe.test(t)) { hasSkip = true; return; }
            if (t && !seenOpts.has(t)) {
                seenOpts.add(t);
                options.push({ text: t, type: 'radio', value: input ? input.id || input.value : '' });
            }
        }
    });

    // Generic: any input[type=radio] with label (if no Naukri-specific found)
    if (options.length === 0) {
        panel.querySelectorAll('input[type=radio]').forEach(inp => {
            const lbl = inp.closest('label') || (inp.id ? panel.querySelector('label[for="'+inp.id+'"]') : null) || inp.parentElement;
            const t = (lbl?.textContent || '').trim();
            if (t && !seenOpts.has(t) && !skipOptionRe.test(t)) {
                seenOpts.add(t);
                options.push({ text: t, type: 'radio', value: inp.id || inp.value || '' });
            }
        });
    }

    // Checkboxes (multi-select like city selection)
    panel.querySelectorAll('input[type=checkbox]').forEach(inp => {
        const lbl = inp.closest('label') || (inp.id ? panel.querySelector('label[for="'+inp.id+'"]') : null) || inp.parentElement;
        const t = (lbl?.textContent || '').trim();
        if (t && !seenOpts.has(t) && !skipOptionRe.test(t)) {
            seenOpts.add(t);
            options.push({ text: t, type: 'checkbox', value: inp.id || inp.value || '' });
        }
    });

    // --- Button options (not system buttons) ---
    const sysRe = /^(save|submit|close|cancel|apply|ok|done|x|×)$/i;
    const skipRe = /skip\\s*(this)?\\s*question/i;
    panel.querySelectorAll('button, [role=button]').forEach(btn => {
        const t = btn.textContent.trim();
        const r = btn.getBoundingClientRect();
        if (!t || t.length > 100 || r.width < 15 || r.height < 10) return;
        if (skipRe.test(t)) { hasSkip = true; return; }
        if (sysRe.test(t)) return;
        if (!options.some(o => o.text === t)) {
            options.push({ text: t, type: 'button' });
        }
    });

    // --- Text input (div.textArea or input with message placeholder) ---
    let textInput = null;
    const ti = panel.querySelector('div.textArea, input[placeholder*="message" i], textarea');
    if (ti) {
        const r = ti.getBoundingClientRect();
        if (r.width > 30 && r.height > 5) {
            textInput = { placeholder: ti.placeholder || '', id: ti.id || '' };
            ti.setAttribute('data-nk-input', '1');
        }
    }

    // --- Save button inside panel ---
    const hasSave = [...panel.querySelectorAll('button')]
        .some(b => /^save$/i.test(b.textContent.trim()));

    return { question, options, text_input: textInput, has_save: hasSave, has_skip: hasSkip };
}"""

CLICK_RADIO_JS = """(optionText) => {
    const panel = document.querySelector('[data-nk-panel]');
    if (!panel) return false;
    const lo = optionText.toLowerCase();

    function clickRadio(container, label, input) {
        // Click the container div (Naukri binds click handlers here)
        container.click();
        // Also click label for good measure
        if (label) label.click();
        // Set the input checked and dispatch change event
        if (input) {
            input.checked = true;
            input.dispatchEvent(new Event('change', { bubbles: true }));
            input.dispatchEvent(new Event('click', { bubbles: true }));
        }
        return true;
    }

    // Naukri-specific: .ssrc__radio-btn-container
    for (const container of panel.querySelectorAll('.ssrc__radio-btn-container')) {
        const label = container.querySelector('label');
        const input = container.querySelector('input');
        if (!label) continue;
        const t = label.textContent.trim().toLowerCase();
        if (t === lo || t.includes(lo) || lo.includes(t)) {
            return clickRadio(container, label, input);
        }
    }
    // Fallback: generic radio buttons
    for (const r of panel.querySelectorAll('input[type=radio]')) {
        const lbl = r.closest('label') || r.parentElement;
        const t = (lbl?.textContent || '').trim().toLowerCase();
        if (t === lo || t.includes(lo) || lo.includes(t)) {
            const container = r.closest('.ssrc__radio-btn-container') || r.parentElement;
            return clickRadio(container, lbl, r);
        }
    }
    return false;
}"""

CLICK_CHECKBOX_JS = """(answerText) => {
    const drawer = document.querySelector('.chatbot_Drawer')
        || document.querySelector('[data-nk-panel]');
    if (!drawer) return false;
    const lo = answerText.toLowerCase();
    let clicked = false;

    for (const cb of drawer.querySelectorAll('input[type=checkbox]')) {
        const lbl = cb.closest('label')
            || (cb.id ? drawer.querySelector('label[for="'+cb.id+'"]') : null)
            || cb.parentElement;
        const t = (lbl?.textContent || '').trim().toLowerCase();
        if (!t) continue;
        if (t === lo || t.includes(lo) || lo.includes(t)) {
            (lbl || cb.parentElement).scrollIntoView({block: 'center'});
            cb.click();
            clicked = true;
        }
    }
    return clicked;
}"""

CLICK_BUTTON_JS = """(answerText) => {
    const panel = document.querySelector('[data-nk-panel]');
    if (!panel) return false;
    const lo = answerText.toLowerCase();
    for (const b of panel.querySelectorAll('button, [role=button]')) {
        const t = b.textContent.trim();
        if (t.toLowerCase() === lo) { b.click(); return true; }
    }
    for (const b of panel.querySelectorAll('button, [role=button]')) {
        const t = b.textContent.trim().toLowerCase();
        if (lo.includes(t) || t.includes(lo)) { b.click(); return true; }
    }
    return false;
}"""

CLICK_SKIP_JS = """() => {
    const panel = document.querySelector('[data-nk-panel]');
    if (!panel) return false;
    for (const b of panel.querySelectorAll('button, [role=button]')) {
        if (/skip\\s*(this)?\\s*question/i.test(b.textContent.trim())) {
            b.click();
            return true;
        }
    }
    return false;
}"""

CLICK_SAVE_JS = """() => {
    const panel = document.querySelector('[data-nk-panel]');
    if (!panel) return false;
    for (const b of panel.querySelectorAll('button')) {
        if (/^save$/i.test(b.textContent.trim())) { b.click(); return true; }
    }
    return false;
}"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_answer(question: str, mapping: dict) -> str | None:
    """Case-insensitive substring match against a config mapping."""
    q = question.lower()
    for pattern, answer in mapping.items():
        if pattern.lower() in q:
            return answer
    return None


def _best_option_match(answer: str, options: list[dict]) -> dict | None:
    """Find the best matching option for an answer. Returns the option dict or None."""
    if not answer or not options:
        return None
    a = answer.strip().lower()
    texts = [o["text"] for o in options]

    # Exact match
    for o in options:
        if o["text"].lower() == a:
            return o

    # Substring match
    for o in options:
        t = o["text"].lower()
        if a in t or t in a:
            return o

    # City alias
    alias = CITY_ALIASES.get(a)
    if alias:
        for o in options:
            t = o["text"].lower()
            if alias in t or t in alias:
                return o

    # Yes/No semantic
    if a in ("yes", "true"):
        for o in options:
            t = o["text"].lower()
            if "don't" not in t and "not" not in t and "no" != t:
                return o
    if a in ("no", "false"):
        for o in options:
            t = o["text"].lower()
            if "don't" in t or "not" in t or t == "no":
                return o

    return None


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

def snapshot_panel(page: Page) -> dict | None:
    """Read the chatbot panel state in one JS call. Returns dict or None."""
    try:
        result = page.evaluate(SNAPSHOT_JS)
        if result:
            q = result["question"][:60]
            opts = [o["text"] for o in result.get("options", [])][:4]
            ti = bool(result.get("text_input"))
            logger.debug(f"Snapshot: Q=\"{q}\" opts={opts} text={ti}")
        return result
    except Exception as exc:
        logger.error(f"Snapshot error: {exc}")
        return None


# ---------------------------------------------------------------------------
# Decision engine
# ---------------------------------------------------------------------------

_METADATA_RE_PATTERNS = [
    "applicant", "days ago", "opening", "posted", "early applicant",
    "thank you", "thanks for", "responses have been",
]


def decide_answer(snapshot: dict, config: dict) -> tuple[str | None, str | None]:
    """Decide what to answer and how. Returns (answer, method) or (None, None).

    Methods: 'text', 'click_radio', 'click_button', 'click_checkbox', 'click_skip'
    """
    question = snapshot["question"]
    options = snapshot.get("options", [])
    has_text = snapshot.get("text_input") is not None
    has_skip = snapshot.get("has_skip", False)
    profile = config.get("profile", {})

    # Guard: reject metadata-like text as questions
    if not question or len(question) < 5:
        return None, None
    q_lower = question.lower()
    if any(p in q_lower for p in _METADATA_RE_PATTERNS):
        logger.debug(f"Rejected metadata question: {question[:50]}")
        return None, None

    # --- Path A: clickable options exist ---
    if options:
        option_texts = [o["text"] for o in options]

        # A1: config pattern match
        cfg = _find_answer(question, config.get("chatbot_option_answers", {}))
        if cfg:
            m = _best_option_match(cfg, options)
            if m:
                logger.debug(f"A (config→{m['type']}): {m['text']}")
                return m["text"], f"click_{m['type']}"

        # A2: rule engine
        rule = rule_answer(question, profile)
        if rule:
            m = _best_option_match(rule, options)
            if m:
                logger.debug(f"A (rule→{m['type']}): {m['text']}")
                return m["text"], f"click_{m['type']}"

        # A3: LLM with options
        llm = llm_answer(question, profile, config, available_options=option_texts)
        if llm:
            m = _best_option_match(llm, options)
            if m:
                logger.debug(f"A (LLM→{m['type']}): {m['text']}")
                return m["text"], f"click_{m['type']}"

        # Fall through to text if available
        if not has_text:
            if has_skip:
                logger.debug(f"No match for options, clicking Skip")
                return "__SKIP__", "click_skip"
            logger.warning(f"FAILED — no match: {option_texts[:6]}")
            return None, None

    # --- Path B: text input ---
    if has_text:
        answer = answer_question(question, config)
        logger.debug(f"A (text): {answer}")
        return answer, "text"

    # --- Path C: skip ---
    if has_skip:
        logger.debug(f"No input available, clicking Skip")
        return "__SKIP__", "click_skip"

    return None, None


# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------

def submit_answer(page: Page, answer: str, method: str) -> bool:
    """Submit an answer to the chatbot. Returns True on success."""
    try:
        if method == "text":
            el = page.locator('[data-nk-input="1"]').first
            try:
                if not el.is_visible(timeout=2000):
                    logger.debug("Text input not visible")
                    return False
            except (PlaywrightTimeout, Exception):
                return False
            # Clear and type
            try:
                el.fill("")
            except Exception:
                pass
            human_type(page, el, answer)
            human_delay(0.3, 0.6)
            page.keyboard.press("Enter")
            human_delay(0.5, 1.0)
            return True

        if method == "click_radio":
            # Step 1: Click the radio via Playwright (scroll into view + real mouse events)
            answer_lower = answer.lower()
            radio_clicked = False

            # Try Playwright native click on the label (scrolls into view automatically)
            labels = page.locator('.chatbot_Drawer .ssrc__radio-btn-container label')
            for i in range(labels.count()):
                label = labels.nth(i)
                try:
                    text = label.inner_text(timeout=1000).strip().lower()
                    if text == answer_lower or answer_lower in text or text in answer_lower:
                        label.scroll_into_view_if_needed(timeout=2000)
                        label.click(timeout=3000)
                        radio_clicked = True
                        logger.debug(f"Radio clicked via Playwright: {text}")
                        break
                except (PlaywrightTimeout, Exception):
                    continue

            # Fallback: JS click on input by id/value
            if not radio_clicked:
                radio_clicked = page.evaluate("""(answerText) => {
                    const panel = document.querySelector('[data-nk-panel]');
                    if (!panel) return false;
                    const lo = answerText.toLowerCase();
                    for (const inp of panel.querySelectorAll('input[type=radio]')) {
                        if (inp.id.toLowerCase() === lo || inp.value.toLowerCase() === lo) {
                            inp.scrollIntoView({block: 'center'});
                            inp.click();
                            return true;
                        }
                    }
                    return false;
                }""", answer)

            if not radio_clicked:
                logger.warning(f"Radio click failed for: {answer}")
                return False

            # Step 2: Wait for Save button to appear, then click via Playwright
            human_delay(1.0, 2.0)
            save_clicked = False

            # Try Playwright native click (handles scroll + visibility)
            try:
                save = page.locator('.chatbot_Drawer :text-is("Save")').last
                if save.is_visible(timeout=3000):
                    save.scroll_into_view_if_needed(timeout=2000)
                    save.click(timeout=3000)
                    save_clicked = True
                    logger.debug("Save clicked via Playwright")
            except (PlaywrightTimeout, Exception):
                pass

            # Fallback: JS click with scrollIntoView
            if not save_clicked:
                save_clicked = page.evaluate("""() => {
                    const panel = document.querySelector('.chatbot_Drawer') || document.querySelector('[data-nk-panel]');
                    if (!panel) return false;
                    for (const el of panel.querySelectorAll('button, div, span, a')) {
                        const t = el.textContent.trim();
                        if (/^save$/i.test(t)) {
                            el.scrollIntoView({block: 'center'});
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                if save_clicked:
                    logger.debug("Save clicked via JS fallback")

            if not save_clicked:
                logger.warning("Save button not found after radio click")

            human_delay(1.0, 1.5)
            return True

        if method == "click_checkbox":
            clicked_any = page.evaluate(CLICK_CHECKBOX_JS, answer)
            logger.info(f"Checkbox JS click for '{answer}': {'OK' if clicked_any else 'FAIL'}")

            if clicked_any:
                human_delay(1.0, 2.0)
                save_clicked = False
                try:
                    save = page.locator('.chatbot_Drawer :text-is("Save")').last
                    if save.is_visible(timeout=3000):
                        save.scroll_into_view_if_needed(timeout=2000)
                        save.click(timeout=3000)
                        save_clicked = True
                        logger.debug("Save clicked after checkbox")
                except (PlaywrightTimeout, Exception):
                    pass
                if not save_clicked:
                    page.evaluate(CLICK_SAVE_JS)
                human_delay(1.0, 1.5)
            else:
                logger.warning(f"Checkbox click failed for: {answer}")
            return clicked_any

        if method == "click_button":
            return page.evaluate(CLICK_BUTTON_JS, answer)

        if method == "click_skip":
            return page.evaluate(CLICK_SKIP_JS)

    except Exception as exc:
        logger.error(f"Submit error ({method}): {exc}")
    return False


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def handle_chatbot(page: Page, config: dict) -> str:
    """Detect and answer Naukri chatbot questions.

    Returns: 'completed', 'partial', or 'none'.
    """
    human_delay(1.5, 2.5)

    snapshot = snapshot_panel(page)
    if not snapshot:
        return "none"

    logger.info("Chatbot detected (.chatbot_Drawer)")

    max_rounds = 10
    last_question = ""
    stale_count = 0
    answered = 0
    failed = 0

    for _round in range(max_rounds):
        if _round > 0:
            human_delay(1.5, 2.5)
            snapshot = snapshot_panel(page)
            if not snapshot:
                break

        question = snapshot["question"]

        # Staleness detection: same question twice → chatbot stuck
        if question == last_question:
            stale_count += 1
            if stale_count >= 2:
                logger.warning("Chatbot stale — same question repeated, breaking")
                failed += 1
                break
            continue
        stale_count = 0
        last_question = question

        if not question:
            continue

        q_lower = question.lower()
        if any(p in q_lower for p in _METADATA_RE_PATTERNS):
            logger.info(f"Chatbot completion detected: {question[:60]}")
            break

        logger.debug(f"Q: {question[:80]}")
        if snapshot.get("options"):
            logger.debug(f"Options: {[o['text'] for o in snapshot['options'][:6]]}")

        answer, method = decide_answer(snapshot, config)

        if answer and method:
            ok = submit_answer(page, answer, method)
            if ok:
                answered += 1
            else:
                logger.warning(f"Submit failed: {answer} via {method}")
                failed += 1
        else:
            logger.warning(f"No answer found for: {question[:60]}")
            failed += 1

    # Click Save (scoped to chatbot panel)
    try:
        saved = page.evaluate(CLICK_SAVE_JS)
        if saved:
            human_delay(0.5, 1.0)
            logger.debug("Clicked Save (in panel)")
    except Exception:
        pass

    logger.info(f"Chatbot result: {answered} answered, {failed} failed")
    return "partial" if failed > 0 else "completed"
