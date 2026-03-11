import os
from pathlib import Path


DEFAULT_REVIEW_PRINCIPLES_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "review-principles.md"
)

FALLBACK_REVIEW_PRINCIPLES = """# Code Review 原则（fallback）

- 重点发现开发遗漏的关键场景、关键分支、关键保护。
- 优先关注正确性、回归风险、兼容性和高影响问题。
- 不对断言粒度、日志精度、表达颗粒度做吹毛求疵式挑刺。
"""


def load_review_principles() -> str:
    path_raw = os.getenv("REVIEW_PRINCIPLES_PATH", "").strip()
    path = Path(path_raw).expanduser() if path_raw else DEFAULT_REVIEW_PRINCIPLES_PATH
    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError:
        return FALLBACK_REVIEW_PRINCIPLES
    return content or FALLBACK_REVIEW_PRINCIPLES


def build_effective_review_principles(
    default_principles: str,
    repo_review_principles: str = "",
) -> str:
    repo_principles = (repo_review_principles or "").strip()
    if not repo_principles:
        return default_principles

    return (
        "仓库级 CR.md（优先遵循）:\n"
        f"{repo_principles}\n\n"
        "默认审查原则（仓库 CR.md 未覆盖时作为兜底）:\n"
        f"{default_principles}"
    )
