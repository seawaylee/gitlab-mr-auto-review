from mr_auto_reviewer.feishu_client import FeishuClient


class DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_publish_markdown_doc_returns_doc_url(monkeypatch):
    calls = {"post": [], "get": []}

    def fake_post(url, **kwargs):
        calls["post"].append((url, kwargs))
        if url.endswith("/open-apis/auth/v3/tenant_access_token/internal"):
            return DummyResponse({"tenant_access_token": "token"})
        if url.endswith("/open-apis/docx/v1/documents"):
            return DummyResponse({"code": 0, "data": {"document": {"document_id": "doc123"}}})
        if url.endswith("/open-apis/docx/v1/documents/blocks/convert"):
            return DummyResponse(
                {
                    "code": 0,
                    "data": {
                        "blocks": [
                            {
                                "block_type": 2,
                                "text": {
                                    "elements": [
                                        {
                                            "text_run": {
                                                "content": "hello",
                                            }
                                        }
                                    ]
                                },
                            }
                        ]
                    },
                }
            )
        if "/open-apis/docx/v1/documents/doc123/blocks/root123/children" in url:
            return DummyResponse({"code": 0, "data": {}})
        raise AssertionError(f"unexpected POST url: {url}")

    def fake_get(url, **kwargs):
        calls["get"].append((url, kwargs))
        if "/open-apis/docx/v1/documents/doc123/blocks" in url:
            return DummyResponse({"code": 0, "data": {"items": [{"block_id": "root123", "children": []}]}})
        if url.endswith("/open-apis/drive/v1/files/doc123"):
            return DummyResponse({"code": 0, "data": {"file": {"url": "https://sohu.feishu.cn/docx/doc123"}}})
        raise AssertionError(f"unexpected GET url: {url}")

    monkeypatch.setattr("mr_auto_reviewer.feishu_client.requests.post", fake_post)
    monkeypatch.setattr("mr_auto_reviewer.feishu_client.requests.get", fake_get)

    client = FeishuClient(
        app_id="app-id",
        app_secret="app-secret",
        receive_id="ou_test",
    )
    doc_url = client.publish_markdown_doc(markdown="# title\n\nbody", title="MR review")

    assert doc_url == "https://sohu.feishu.cn/docx/doc123"
    assert len(calls["post"]) == 4
    assert len(calls["get"]) == 2


def test_publish_markdown_doc_skips_when_config_missing(monkeypatch):
    called = {"post": 0}

    def fake_post(*_args, **_kwargs):
        called["post"] += 1
        raise AssertionError("should not call feishu API when config is incomplete")

    monkeypatch.setattr("mr_auto_reviewer.feishu_client.requests.post", fake_post)

    client = FeishuClient(app_id=None, app_secret=None, receive_id=None)
    assert client.publish_markdown_doc(markdown="x", title="y") is None
    assert called["post"] == 0


def test_markdown_to_structured_blocks_distinguishes_heading_body_and_list():
    markdown = """# 主标题

## 二级标题

正文内容，含 `inline code` 和 [链接](https://example.com)。

- 第一条
- 第二条
"""
    blocks = FeishuClient._markdown_to_structured_blocks(markdown)
    assert len(blocks) >= 5

    assert blocks[0]["block_type"] == 3
    assert blocks[0]["heading1"]["elements"][0]["text_run"]["content"] == "主标题"

    assert blocks[1]["block_type"] == 4
    assert blocks[1]["heading2"]["elements"][0]["text_run"]["content"] == "二级标题"

    assert blocks[2]["block_type"] == 2
    assert "inline code" in blocks[2]["text"]["elements"][0]["text_run"]["content"]
    assert "链接 (https://example.com)" in blocks[2]["text"]["elements"][0]["text_run"]["content"]

    assert blocks[3]["block_type"] == 12
    assert blocks[3]["bullet"]["elements"][0]["text_run"]["content"] == "第一条"

    assert blocks[4]["block_type"] == 12
    assert blocks[4]["bullet"]["elements"][0]["text_run"]["content"] == "第二条"
