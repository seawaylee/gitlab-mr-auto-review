from datetime import datetime, timezone

from mr_auto_reviewer.models import Change, MergeRequest, ReviewResult
from mr_auto_reviewer.reporting import build_gitlab_comment, build_markdown_report


def test_build_markdown_report_contains_required_sections():
    mr = MergeRequest(
        project_id=100,
        iid=88,
        title="feat: add jwt middleware",
        web_url="https://gitlab.example.com/group/repo/-/merge_requests/88",
        source_branch="feature/jwt",
        target_branch="main",
        author="alice",
        sha="abc123",
        description="引入 JWT 鉴权中间件并给用户 API 增加权限校验。",
        changes=[Change(new_path="auth/middleware.py", diff="+def verify_jwt(...): ...")],
    )
    review = ReviewResult(
        mr_purpose="新增 JWT 鉴权中间件并在核心接口启用权限校验。",
        summary="实现方向正确，整体改动聚焦。",
        verdict="request_changes",
        risk_level="medium",
        findings=["`verify_jwt` 对过期 token 的异常处理不完整。"],
        suggestions=["补充 token 过期单元测试并统一 401 返回体。"],
    )

    markdown = build_markdown_report(
        mr=mr,
        review=review,
        generated_at=datetime(2026, 3, 2, 9, 30, tzinfo=timezone.utc),
    )

    assert "# Merge Request Review 报告" in markdown
    assert "## 这次 MR 在做什么" in markdown
    assert "新增 JWT 鉴权中间件" in markdown
    assert "## Review 结论" in markdown
    assert "需修改后再提交" in markdown
    assert "## 风险级别" in markdown
    assert "中" in markdown
    assert "## 主要问题" in markdown
    assert "verify_jwt" in markdown
    assert "## 建议" in markdown


def test_build_gitlab_comment_uses_current_style_sections():
    mr = MergeRequest(
        project_id=100,
        iid=89,
        title="fix: normalize login error response",
        web_url="https://gitlab.example.com/group/repo/-/merge_requests/89",
        source_branch="fix/login-error",
        target_branch="main",
        author="charlie",
        sha="def456",
    )
    review = ReviewResult(
        mr_purpose="统一登录失败时的响应结构并补充错误码。",
        summary="实现清晰，兼容性风险较低。",
        verdict="comment",
        risk_level="low",
        findings=["登录失败分支仍有一个路径返回旧字段名。"],
        suggestions=["补充回归测试覆盖旧字段兼容路径。"],
    )

    comment = build_gitlab_comment(
        mr=mr,
        review=review,
        generated_at=datetime(2026, 3, 3, 10, 0, tzinfo=timezone.utc),
    )

    assert "## 自动化 Code Review" in comment
    assert "行业规范" not in comment
    assert "### 变更意图" in comment
    assert "### 审查结论" in comment
    assert "建议关注" in comment
    assert "风险等级: 低" in comment
    assert "### 主要问题" in comment
    assert "- [低] 登录失败分支仍有一个路径返回旧字段名。" in comment
    assert "### 对非本次修改意图的影响" in comment
    assert "### 建议动作" in comment


def test_build_gitlab_comment_displays_generated_time_in_beijing_time():
    mr = MergeRequest(
        project_id=100,
        iid=90,
        title="chore: refresh review template",
        web_url="https://gitlab.example.com/group/repo/-/merge_requests/90",
        source_branch="chore/review-template",
        target_branch="main",
        author="diana",
        sha="ghi789",
    )
    review = ReviewResult(
        mr_purpose="调整自动化审查模板文案。",
        summary="无功能逻辑改动。",
        verdict="approve",
        risk_level="low",
        findings=[],
        suggestions=[],
    )

    comment = build_gitlab_comment(
        mr=mr,
        review=review,
        generated_at=datetime(2026, 3, 10, 2, 22, 57, tzinfo=timezone.utc),
    )

    assert "生成时间: 2026-03-10 10:22:57 北京时间" in comment


def test_build_gitlab_comment_mentions_current_review_inputs():
    mr = MergeRequest(
        project_id=100,
        iid=91,
        title="feat: expand review context",
        web_url="https://gitlab.example.com/group/repo/-/merge_requests/91",
        source_branch="feature/context",
        target_branch="main",
        author="eva",
        sha="jkl012",
    )
    review = ReviewResult(
        mr_purpose="为自动化审查补充有限扩展阅读。",
        summary="reviewer 会读取关联代码上下文。",
        verdict="comment",
        risk_level="low",
        findings=[],
        suggestions=[],
    )

    comment = build_gitlab_comment(
        mr=mr,
        review=review,
        generated_at=datetime(2026, 3, 11, 9, 0, tzinfo=timezone.utc),
    )

    assert "已结合 MR 改动、有限扩展阅读以及仓库规则（如存在）" in comment


def test_build_gitlab_comment_shows_non_target_impacts_when_present():
    mr = MergeRequest(
        project_id=100,
        iid=92,
        title="feat: split cache routes",
        web_url="https://gitlab.example.com/group/repo/-/merge_requests/92",
        source_branch="feature/cache",
        target_branch="main",
        author="frank",
        sha="mno345",
    )
    review = ReviewResult(
        mr_purpose="拆分作者页缓存路由。",
        summary="核心改动清晰。",
        verdict="comment",
        risk_level="medium",
        findings=["缓存语义发生变化。"],
        non_target_impacts=["作者相关旧链路如果漏传 isPage，可能读到错误缓存。"],
        suggestions=["补一轮旧链路回归验证。"],
    )

    comment = build_gitlab_comment(
        mr=mr,
        review=review,
        generated_at=datetime(2026, 3, 11, 9, 30, tzinfo=timezone.utc),
    )

    assert "### 对非本次修改意图的影响" in comment
    assert "作者相关旧链路如果漏传 isPage，可能读到错误缓存。" in comment
