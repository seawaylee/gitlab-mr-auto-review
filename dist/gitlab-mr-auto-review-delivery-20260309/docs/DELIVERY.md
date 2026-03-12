# GitLab MR Auto Review 交付使用说明（脱敏版）

本文档用于把 `gitlab-mr-auto-review` 项目交付给其他团队或同事使用，内容已经做过脱敏处理，只保留部署和使用所需的信息，不包含任何真实账号、令牌、历史运行记录或报告内容。

## 1. 项目用途

该项目用于自动巡检 GitLab Merge Request，并完成以下动作：

- 拉取指派给指定 reviewer 的 opened MR
- 对每个未处理的 commit SHA 生成自动 review 结论
- 在对应 GitLab MR 下发布 review comment
- 生成 Markdown 报告
- 发布飞书在线文档，并将链接推送给 `sohu` agent
- 记录已处理状态，避免同一 SHA 被重复处理

默认推荐使用 `OpenClaw + sohu agent + 飞书文档` 这条链路；如果接收方不使用 OpenClaw，也可以切换到 `OpenAI + webhook` 模式。

## 2. 本次交付包含 / 不包含什么

### 包含内容

- `src/`：项目源码
- `tests/`：单元测试
- `README.md`：项目原始说明
- `.env.example`：环境变量模板
- `requirements.txt` / `pyproject.toml`：依赖与 Python 版本要求
- `docs/DELIVERY.md`：本交付文档

### 已明确排除的敏感或运行态内容

- `.env`：本地真实配置
- `.git/`：提交历史与仓库元数据
- `.venv/`、`.pytest_cache/`、`__pycache__/`：本地环境与缓存
- `data/`：已处理 MR 状态
- `reports/`：历史生成报告
- `logs/`：运行日志与 PID 文件
- `dist/`：打包产物目录
- `docs/plans/`：内部实施计划文档

如果接收方需要重新交付给下一方，请继续沿用上述排除规则。

## 3. 运行前准备

建议接手环境满足以下条件：

- Python `3.9` 或以上
- 可以访问目标 GitLab 服务
- 如果使用默认模式，需要本机已安装并可执行 `openclaw`
- 如果需要发布飞书文档，需要具备飞书应用凭据
- 如果使用 OpenAI 模式，需要可访问对应大模型接口

## 4. 安装步骤

在项目根目录执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

如果接手方习惯使用 `pip install -e .` 也可以，但最小可用路径仍以 `requirements.txt` 为准。

## 5. 配置步骤

先复制配置模板：

```bash
cp .env.example .env
```

然后按照实际环境填写 `.env`。以下变量是最关键的：

### GitLab 必填

- `GITLAB_URL`：GitLab 地址，例如 `https://gitlab.example.com/`
- `GITLAB_REVIEWER_USERNAME`：要轮询的 reviewer 用户名
- `GITLAB_REVIEW_SCOPE`：推荐 `reviewer_or_assignee`
- 认证方式二选一：
  - 推荐：`GITLAB_PRIVATE_TOKEN`
  - 备选：`GITLAB_USERNAME` + `GITLAB_PASSWORD`

### Review 引擎

#### 方案 A：默认推荐，`OpenClaw`

- `REVIEW_PROVIDER=openclaw`
- `OPENCLAW_REVIEW_AGENT=sohu`
- `OPENCLAW_REVIEW_BIN`：可留空，前提是系统环境里能找到 `openclaw`

#### 方案 B：改用 `OpenAI`

- `REVIEW_PROVIDER=openai`
- `OPENAI_API_KEY`
- 可选：`OPENAI_MODEL`
- 可选：`OPENAI_BASE_URL`

### 推送链路

#### 方案 A：默认推荐，OpenClaw 推送给 sohu agent

- `SOHU_PUSH_MODE=openclaw`
- `SOHU_OPENCLAW_CHANNEL=feishu`
- `SOHU_OPENCLAW_ACCOUNT=sohu`
- 可选：`SOHU_OPENCLAW_TARGET`

#### 方案 B：Webhook 推送

- `SOHU_PUSH_MODE=webhook`
- `SOHU_AGENT_WEBHOOK_URL`

### 飞书文档

如果要发布飞书在线文档，需要配置：

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- 可选：`FEISHU_RECEIVE_ID`
- 可选：`FEISHU_RECEIVE_ID_TYPE`
- 可选：`FEISHU_DOC_FOLDER_TOKEN`
- 可选：`FEISHU_DOC_URL_BASE`

### 其他建议

- `GITLAB_SSL_VERIFY` 默认应按真实网络环境设置；只有内网自签证书场景才建议设为 `false` 或指定 CA 证书路径
- `DRY_RUN=true` 适合首次联调
- `SOHU_ATTACH_REPORT=false` 表示默认只发送飞书文档链接，不再发送 Markdown 附件

## 6. 首次使用建议流程

建议按下面顺序做首次验证。

### 第一步：先做无副作用验证

```bash
python3 -m mr_auto_reviewer.main run-once --dry-run
```

作用：

- 会加载配置并执行主流程
- 不会真的向外部渠道发送消息
- 便于验证 GitLab 拉取、MR 解析、Review 生成链路是否通畅

如果需要临时指定推送目标，可以使用：

```bash
python3 -m mr_auto_reviewer.main run-once \
  --channel feishu \
  --account sohu \
  --target user:ou_xxx \
  --dry-run
```

### 第二步：确认输出目录

首次执行后通常会看到以下本地产物：

- `reports/`：生成的 Markdown 报告
- `data/processed_mrs.json`：已处理 SHA 记录

如果是 `watch` 模式，还会出现：

- `logs/mr_watch.pid`

### 第三步：切换到正式执行

确认配置无误后，执行：

```bash
python3 -m mr_auto_reviewer.main run-once
```

## 7. 持续轮询运行

如果要持续巡检，可以使用：

```bash
python3 -m mr_auto_reviewer.main watch --interval 300
```

说明：

- `--interval 300` 表示每 300 秒轮询一次
- `watch` 默认使用单实例锁，PID 文件为 `logs/mr_watch.pid`
- 适合挂在 `systemd`、`supervisord`、crontab 外层调度器或容器内长期运行

## 8. 常见问题

### 1）没有拉到任何 MR

优先检查：

- `GITLAB_REVIEWER_USERNAME` 是否正确
- `GITLAB_REVIEW_SCOPE` 是否符合当前使用场景
- 对应 MR 是否仍为 `opened`

### 2）GitLab 认证失败

优先检查：

- `GITLAB_PRIVATE_TOKEN` 是否有效
- 如果使用账号密码，确认未触发 SSO / 二次验证限制
- `GITLAB_URL` 是否带正确协议和域名

### 3）TLS / 证书报错

优先检查：

- `GITLAB_SSL_VERIFY` 是否与实际证书环境一致
- 是否误设置了失效的 `REQUESTS_CA_BUNDLE`、`SSL_CERT_FILE`、`CURL_CA_BUNDLE`

### 4）OpenClaw 找不到

优先检查：

- `openclaw` 是否已安装
- `OPENCLAW_REVIEW_BIN` 或 `SOHU_OPENCLAW_BIN` 是否指向真实可执行文件

### 5）飞书文档未成功发布

优先检查：

- `FEISHU_APP_ID` / `FEISHU_APP_SECRET`
- 飞书应用权限是否完整
- `FEISHU_DOC_FOLDER_TOKEN` 是否有写入权限

## 9. 建议的交接口径

对接收方建议明确以下几点：

- 本项目的真实敏感信息不随代码包提供，需要由接收方自行配置
- 首次部署请优先用 `--dry-run` 联调
- 若要重复处理某个 MR，需要清理 `data/processed_mrs.json` 中对应记录
- 不建议把运行中生成的 `reports/`、`logs/`、`data/` 再次对外分发

## 10. 最小验收清单

接收方拿到包后，至少应完成一次以下验证：

1. 成功安装依赖
2. 成功完成 `.env` 配置
3. 成功执行 `run-once --dry-run`
4. 确认能生成本地报告
5. 确认正式模式下可成功写入 GitLab comment 或推送到目标渠道

以上步骤完成后，即可进入正式运行或托管部署。
