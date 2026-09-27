"""System prompts for OpenRouter fallback."""
from src.config.candidate import CANDIDATE, SKILLS

SYSTEM = (
    "You fill job applications. Reply with ONLY the answer, no explanation. "
    "Always positive (Yes, willing, immediate joiner). "
    f"Experience is {CANDIDATE['exp']} years for everything."
)

def user_prompt(question: str, options: list[str]) -> str:
    base = (
        f"Candidate: {CANDIDATE['name']}, {CANDIDATE['exp']} yrs Full Stack "
        f"(React, Next, Node, Express, Python, FastAPI, MySQL, Postgres, Mongo, AWS, Docker). "
        f"Current CTC {CANDIDATE['current_ctc']} LPA, Expected {CANDIDATE['expected_ctc']}-5 LPA, "
        f"Notice {CANDIDATE['notice']}, Location {CANDIDATE['city']} willing to relocate, remote OK.\n"
        f"Question: {question}\n"
    )
    if options:
        base += f"Options: {', '.join(options)}. Reply with EXACTLY one option."
    else:
        base += "Short direct answer only. Numbers only for numeric Q."
    base += f"\nSkills: {', '.join(SKILLS[:20])}"
    return base
