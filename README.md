# GitLab MR Auto Review

自动检测分配给你的 GitLab Merge Request，生成自动 review 报告，并把结果推送到 OpenClaw 的 `sohu` agent（默认）+ 飞书在线文档。

## Features

- 拉取 `reviewer_username=<你自己>` 的 opened Merge Request
- 对每个未处理 commit SHA 做自动 review
- Review 引擎可切换：默认使用 OpenClaw `sohu` agent（可切回 OpenAI）
- 生成 Markdown 报告（包含 "这次 MR 在做什么" + review 结论）
- 产出 review 后，直接在对应 GitLab MR 下发布行业规范 comment
- 默认通过 OpenClaw 推送报告到 `sohu` agent（支持自动识别最近飞书会话目标）
- 可选兼容 sohu agent webhook 推送
- 将报告发布为飞书在线文档并发送文档链接给 agent 侧留档（默认不再发送 `.md` 附件）
- 本地状态去重，避免同一 SHA 重复发送

## Quick Start

1. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. 配置环境变量

```bash
cp .env.example .env
```

至少需要：

- `GITLAB_URL`
- `GITLAB_REVIEWER_USERNAME`
- `GITLAB_REVIEW_SCOPE`（`reviewer` / `assignee` / `reviewer_or_assignee`，默认 `reviewer_or_assignee`）
- `GITLAB_PRIVATE_TOKEN` 或 `GITLAB_USERNAME` + `GITLAB_PASSWORD`
- 内网自签证书可配置：`GITLAB_SSL_VERIFY=false`（或指定 CA 证书路径）
- `REVIEW_PROVIDER=openclaw`（默认）时，需要本机可用 `openclaw` 且 `sohu` agent 可调用
- OpenClaw 模式（默认）：`SOHU_PUSH_MODE=openclaw`
- OpenClaw 可执行文件可被找到（默认自动找 `openclaw`）
- OpenClaw `sohu` account 可用；`SOHU_OPENCLAW_TARGET` 留空时会自动读取最近会话目标
- 若改用 webhook 模式：`SOHU_PUSH_MODE=webhook` + `SOHU_AGENT_WEBHOOK_URL`
- 发布飞书在线文档所需：`FEISHU_APP_ID`, `FEISHU_APP_SECRET`
- 可选文档目录：`FEISHU_DOC_FOLDER_TOKEN`
- 可选链接兜底前缀：`FEISHU_DOC_URL_BASE`（示例：`https://sohu.feishu.cn/docx`）
- 如仍需附件：`SOHU_ATTACH_REPORT=true`

3. 单次执行

```bash
python3 -m mr_auto_reviewer.main run-once
```

BTC 监控同款参数（可选）：

```bash
python3 -m mr_auto_reviewer.main run-once \
  --channel feishu \
  --account sohu \
  --target user:ou_xxx \
  --dry-run
```

4. 持续轮询

```bash
python3 -m mr_auto_reviewer.main watch --interval 300
```

## Output

- 报告默认保存到 `reports/`
- 已处理 MR SHA 保存到 `data/processed_mrs.json`
- `watch` 默认单实例，PID 文件为 `logs/mr_watch.pid`

## Notes

- 生产环境建议使用 `GITLAB_PRIVATE_TOKEN`，不要长期使用账号密码。
- 未配置 `OPENAI_API_KEY` 时会自动降级为基础摘要模式（不阻塞推送）。
- 默认推荐 OpenClaw 模式，不需要单独提供 sohu webhook。
- 为了和 BTC 监控一致，`run-once` 失败时默认返回 `0`（便于外部定时器持续运行）。
