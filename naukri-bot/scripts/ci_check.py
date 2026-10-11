"""CI safety checks: no network, no browser, no secrets needed.

Asserts the SAFETY CONTRACT (not specific answers — the AI decides those):
- reasoning dumps are rejected, normal answers pass validation,
- dead transport -> decline (""), never garbage,
- prompt carries resume facts + SKIP contract,
- blocklist + profile data intact.
Run:  python scripts/ci_check.py   (from naukri-bot/)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # naukri-bot/


def check(name, cond, extra=""):
    print(("ok   " if cond else "FAIL ") + name + (f" [{extra}]" if extra and not cond else ""))
    return bool(cond)


async def _amain() -> bool:
    import src.brain.ai_client as AC
    import src.brain.answer_tool as AT
    from src.brain.prompts import build_answer_prompt
    from src.config.candidate import CANDIDATE
    from src.tools.blocklist import is_company_blocked

    results = []

    # validation rejects thinking dumps, accepts real answers + SKIP
    results.append(check("reject reasoning dump",
                         AT.looks_like_reasoning("Here's a thinking process:\n1. **Analyze this")))
    results.append(check("reject overlong", AT.looks_like_reasoning("x" * 301)))
    results.append(check("accept short answer", not AT.looks_like_reasoning("3.2")))
    results.append(check("accept SKIP sentinel", not AT.looks_like_reasoning("SKIP")))
    results.append(check("strip think tags",
                         AT.clean_model_text("<think>hmm</think>Yes") == "Yes"))
    # verdict salvage finds embedded decisions without any model call
    results.append(check("salvage exact option",
                         AT._match_option("Yes", ["Yes", "No"]) == "Yes"))
    results.append(check("salvage from ramble",
                         AT._match_option("Analysis done... therefore No", ["Yes", "No"]) == "No"))
    results.append(check("salvage nothing -> None",
                         AT._match_option("blah blah", ["Yes", "No"]) is None))

    # fixed fact: experience in ANY tech stack is always 3.2 (no model call)
    results.append(check("exp any stack -> 3.2",
                         await AT.prepare_answer("How many years of experience in banking solutions?", []) == "3.2"))
    results.append(check("exp bands -> 3-4",
                         await AT.prepare_answer("Total Years of experience", ["1-2", "2-3", "3-4", "4-5", "5+"]) == "3-4"))

    # dead transport -> decline "", never a filed answer
    async def _dead(*a, **k):
        raise RuntimeError("no network")

    real_complete = AC.complete
    AC.complete = _dead
    try:
        results.append(check("decline free-text offline",
                             await AT.prepare_answer("Anything at all?", []) == ""))
        results.append(check("decline options offline",
                             await AT.prepare_answer("Pick?", ["Yes", "No"]) == ""))
        results.append(check("expertise untouched by exp hook",
                             await AT.prepare_answer("Describe your expertise in React", []) == ""))
        results.append(check("salary untouched by exp hook",
                             await AT.prepare_answer("What is your expected CTC?", []) == ""))
    finally:
        AC.complete = real_complete

    # prompt carries resume facts + contracts
    _, user = build_answer_prompt("Q?", [])
    results.append(check("prompt has github", "github.com/Imran2909" in user))
    results.append(check("prompt has 3.2 policy", "3.2" in user))
    results.append(check("prompt has SKIP contract", "SKIP" in user))

    # blocklist + profile data
    results.append(check("blocklist typo -> Infosys",
                         is_company_blocked("Infosis Pvt Ltd", ["Infosys"])[0] is True))
    results.append(check("blocklist clean -> False",
                         is_company_blocked("TechNeutron Ltd", ["Infosys"])[0] is False))
    results.append(check("github link", CANDIDATE["github"] == "https://github.com/Imran2909"))
    results.append(check("linkedin link", CANDIDATE["linkedin"] == "https://www.linkedin.com/in/imran-sutar-0a858425b"))

    # inspector: strict JSON parsing + destructive-target refusal (no browser)
    from src.tools.inspector import _parse_decision, _denied
    _good = _parse_decision('{"diagnosis": "d", "action": {"type": "fill", '
                            '"target": 2, "purpose": "email"}, "reason": "r"}')
    results.append(check("inspector parses decision",
                         _good is not None and _good["action"] == "fill"
                         and _good["target"] == 2 and _good["purpose"] == "email"))
    results.append(check("inspector rejects garbage",
                         _parse_decision("hmm, looks like a page") is None))
    results.append(check("inspector rejects bad action",
                         _parse_decision('{"diagnosis":"d","action":{"type":"delete"}}') is None))
    results.append(check("inspector refuses logout/delete",
                         _denied("Sign out") and _denied("Delete account") and not _denied("Sign in")))

    # orchestrator site adapters resolve for both sites (no browser)
    from src.orchestrator.run import _site_modules
    for _site in ("naukri", "linkedin"):
        _s = _site_modules(_site)
        results.append(check(
            f"site adapter resolves: {_site}",
            all(callable(getattr(_s, k, None))
                for k in ("login", "search_jobs", "fetch_detail", "apply_to_job"))))

    # scoring offline paths (blocked + clear match; borderline needs network)
    from src.brain.ai_client import score_job
    _, _, ok_blocked = await score_job("Java Developer", "java 2-3 years", "SomeCo")
    _, _, ok_react = await score_job("React Developer", "react node 2-3 years", "SomeCo")
    results.append(check("java title blocked", ok_blocked is False))
    results.append(check("react title applies", ok_react is True))

    print("CI CHECKS PASS" if all(results) else "CI CHECKS FAILED")
    return all(results)


def main() -> int:
    import asyncio
    return 0 if asyncio.run(_amain()) else 1


if __name__ == "__main__":
    sys.exit(main())
