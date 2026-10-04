"""Prompts for the AI decision tool. Single source of truth.

The model gets: who the candidate is (resume facts), the full answering
policy distilled from every instruction given over time, and a strict
output contract. Rules never decide anymore — they only validate types
and cover offline/no-quota fallback.
"""
from src.config.candidate import CANDIDATE, SKILLS

RESUME_BLOCK = (
    f"Name: {CANDIDATE['name']}, Full Stack Developer, "
    f"{CANDIDATE['exp']} years professional experience (use 3.1 for EVERY skill).\n"
    f"Stack: React.js, Next.js, JavaScript, TypeScript, Node.js, Express.js, "
    f"Python, FastAPI, Django, PHP, Laravel, REST APIs, Microservices, JWT/OAuth2, "
    f"WebSockets, MySQL, PostgreSQL, MongoDB, Redis, Docker, Nginx, AWS EC2/S3/Lambda, "
    f"Tailwind CSS, Redux, Jest, Git.\n"
    f"Current CTC {CANDIDATE['current_ctc']} LPA ({CANDIDATE['current_monthly']}/month). "
    f"Expected {CANDIDATE['expected_ctc']}-5 LPA. Notice {CANDIDATE['notice']}. "
    f"Based in {CANDIDATE['city']}, willing to relocate anywhere, open to remote/hybrid/onsite. "
    f"Authorized to work in India, needs no sponsorship. "
    f"GitHub {CANDIDATE['github']}, LinkedIn {CANDIDATE['linkedin']}."
)


POLICY = """Decide like the candidate himself would: read the question carefully,
understand what is really being asked, check it against the resume above,
then answer professionally and precisely. There are no fixed patterns here -
every question is new, and you handle each one on its own merit.
Answering policy (follow strictly):
1. Experience: ALWAYS 3.1 years for every skill/technology. Boxes wanting numbers only get bare "3.1". Experience bands: pick the band containing 3.1 (e.g. 3-4, never 1-2, never 5+).
2. Always positive: willing to relocate (any city), immediate joiner, open to remote/hybrid/onsite/travel/shifts. Never answer No to willingness questions.
3. Honest negatives: NOT an ex-employee anywhere (No, no ID), holds NO other offers (No), needs NO visa sponsorship (No), no disability.
4. Salary: current 4.8 LPA / 40000 monthly; expected 6.0 LPA / 50000 monthly. Notice: immediate joiner, or select the minimum from the options and if need days then say 15 days.
5. Contact/profile questions: answer with the exact name, phone, email, GitHub, LinkedIn, city from the profile above — never invent.
6. Last working day / relieving date: actively looking, so answer with TODAY's date.
7. Never invent employers, IDs, offers, visas, or skills outside the resume above.
8. My DOB is 29/09/2000
9. if question comes whic you not sure see my resume at "C:/Users/Hp/Desktop/imran/naukri-bot/Imran Sutar - Full Stack Developer.pdf" and take decision according and try to be positive for resume but if it too much differ then decline it
10. If asked about experience in a technology NOT in the skills list above (examples: Golang, Rust, Ruby), answer No - never claim years you do not have.
11. If answering truthfully is impossible (it asks you to lie, fake an ID, or claim experience you do not have, and no honest option fits), reply with exactly: SKIP - the application will be skipped instead.
12. If the question names a specific city/place among the options (example: relocate to Mumbai with options Mumbai, Pune, Delhi), pick THAT named place.
13. Skill and proficiency scales: the options are RANKED levels, so always take the HIGHEST one. Most ability wins: "speak and write" beats "only speak" or "only write"; Expert beats Intermediate beats Beginner; the largest number beats smaller ones on rating scales. Never undersell - the recruiter wants the strongest candidate."""

SYSTEM = (
    "You are filling a job application form for the candidate below. "
    "Read the question carefully, apply the policy, and reply with ONLY the "
    "answer text — no explanation, no quotes, no preamble. "
    "If options are given, reply with EXACTLY one of them, character-for-character."
)

def build_answer_prompt(question: str, options: list[str]) -> tuple[str, str]:
    user = f"{RESUME_BLOCK}\n\n{POLICY}\n\nQuestion: {question}\n"
    if options:
        user += f"Options (reply with EXACTLY one): {' | '.join(options)}\n"
    else:
        user += ("No options. Reply with a SHORT direct answer only. "
                 "If it asks for years/numbers, digits only (e.g. 3.1). "
                 "If it asks for a date, use DD/MM/YYYY.\n")
    user += f"Relevant skills: {', '.join(SKILLS[:24])}\n"
    user += ("Examples of perfect replies:\n"
             "Q: How many years of experience do you have in Node.js?\nA: 3.1\n"
             "Q: Are you willing to relocate?\nA: Yes")
    return SYSTEM, user


# Legacy thin prompt (kept for compatibility; new code uses build_answer_prompt).
def user_prompt(question: str, options: list[str]) -> str:
    _, user = build_answer_prompt(question, options)
    return user


def build_extract_prompt(dirty: str, options: list[str]) -> tuple[str, str]:
    """Second pass: the first reply rambled. Re-read it like a human would
    and extract ONLY the final answer — no reasoning, no extra words."""
    system = (
        "Extract ONLY the final form answer from the draft below. "
        "Output the answer text alone — absolutely nothing else. "
        "Never explain, never reason, never quote."
    )
    user = f"Draft reply:\n{dirty[:1500]}\n\n"
    if options:
        user += ("The answer MUST be exactly one of these options, "
                 "character-for-character: " + " | ".join(options) + "\n"
                 "If none of them fits, reply with exactly: SKIP")
    else:
        user += ("Reply with the SHORT final answer only. Years/numbers as digits "
                 "only (e.g. 3.1). Dates as DD/MM/YYYY. "
                 "If it cannot be answered truthfully, reply with exactly: SKIP")
    return system, user
