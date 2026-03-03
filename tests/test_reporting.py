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


def test_build_gitlab_comment_uses_industry_style_sections():
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

    assert "## 自动化 Code Review（行业规范）" in comment
    assert "### 变更意图" in comment
    assert "### 审查结论" in comment
    assert "建议关注" in comment
    assert "风险等级: 低" in comment
    assert "### 主要问题" in comment
    assert "### 建议动作" in comment
