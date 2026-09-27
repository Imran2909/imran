"""CI smoke checks: brain rules, blocklist, candidate profile.

No network, no browser, no secrets needed. Fails loudly on first problem.
Run:  python scripts/ci_check.py   (from naukri-bot/)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # naukri-bot/


def check(name, actual, expected):
    if actual != expected:
        print(f"FAIL {name}: got {actual!r}, want {expected!r}")
        return False
    print(f"ok   {name}")
    return True


def main() -> int:
    from src.brain.rules import rule_answer, pick_experience_option
    from src.config.candidate import CANDIDATE
    from src.tools.blocklist import is_company_blocked

    results = [
        check("offer-in-hand -> No",
              rule_answer("Do you have any other offer in hand?", []), "No"),
        check("holding offer -> No",
              rule_answer("Are you holding any offers currently?", ["Yes", "No"]), "No"),
        check("exp band -> 3-4",
              pick_experience_option(["1-2", "2-3", "3-4", "4-5", "5+"]), "3-4"),
        check("blocklist typo -> Infosys",
              is_company_blocked("Infosis Pvt Ltd", ["Infosys"])[0], True),
        check("blocklist clean -> False",
              is_company_blocked("TechNeutron Ltd", ["Infosys"])[0], False),
        check("github link",
              CANDIDATE["github"], "https://github.com/Imran2909"),
        check("linkedin link",
              CANDIDATE["linkedin"], "https://www.linkedin.com/in/imran-sutar-0a858425b"),
    ]
    print("CI CHECKS PASS" if all(results) else "CI CHECKS FAILED")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
