from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Change:
    new_path: str
    diff: str
    old_path: Optional[str] = None


@dataclass
class MergeRequest:
    project_id: int
    iid: int
    title: str
    web_url: str
    source_branch: str
    target_branch: str
    author: str
    sha: str
    description: str = ""
    changes: List[Change] = field(default_factory=list)

    @property
    def unique_key(self) -> str:
        return f"{self.project_id}:{self.iid}:{self.sha}"


@dataclass
class ReviewResult:
    mr_purpose: str
    summary: str
    verdict: str
    risk_level: str
    findings: List[str]
    suggestions: List[str]
