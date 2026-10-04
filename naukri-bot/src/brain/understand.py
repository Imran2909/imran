"""Single entry point for answers: everything goes through the AI tool."""
from __future__ import annotations


async def understand_and_answer(question: str, options: list[str] | None = None) -> str:
    """AI decides; "" means decline (drawer skips the job). Never raises."""
    from src.brain.answer_tool import prepare_answer

    return await prepare_answer(question, options)
