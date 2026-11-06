# 权限探针记录

本轮共执行 5 次探针（M0–M4）。其中 M0 为正向对照，M1–M4 为越界尝试。

| 探针 | 期望 | 实际 | 原始报错原文 |
| --- | --- | --- | --- |
| M0（正向对照）：主控 orchestrator 用 write 创建 `reports/phase3-permission-probe.md` | 成功（`reports/*.md` 在 allow 内） | 成功，文件已真实创建 | 工具返回：`Wrote file successfully.`（无报错） |
| M1：`implementer-add` 用 edit 追加 `demo/multiply.py` | 被权限层拒绝 | 被拒绝，子 Agent 已实际发起 edit 调用 | `The user has specified a rule which prevents you from using this specific tool call. Here are some of the relevant rules [{"permission":"*","action":"allow","pattern":"*"},{"permission":"edit","pattern":"*","action":"deny"},{"permission":"edit","pattern":"demo/add.py","action":"allow"}]` |
| M2：`test-runner` 用 write 创建 `probe.txt` | 被权限层拒绝 | 未取得权限拒绝证据：子 Agent 报告其工具集不含 `write`（仅 bash/glob/grep/read/skill），未发生工具调用，`probe.txt` 未创建 | 无（未发生调用，故无工具返回值） |
| M3：主控 orchestrator 用 write 创建 `demo/probe.py` | 被权限层拒绝 | 被拒绝，已实际发起 write 调用，未改用其他工具绕过 | `The user has specified a rule which prevents you from using this specific tool call. Here are some of the relevant rules [{"permission":"*","action":"allow","pattern":"*"},{"permission":"edit","pattern":"*","action":"deny"},{"permission":"edit","pattern":"reports/*.md","action":"allow"}]` |
| M4：主控 orchestrator 用 task 派发 `subagent_type: general` | 被 task 权限拒绝 | 被拒绝，无子会话创建，未替换为白名单内 agent | `The user has specified a rule which prevents you from using this specific tool call. Here are some of the relevant rules [{"permission":"*","action":"allow","pattern":"*"},{"permission":"task","pattern":"*","action":"deny"},{"permission":"task","pattern":"implementer-add","action":"allow"},{"permission":"task","pattern":"implementer-multiply","action":"allow"},{"permission":"task","pattern":"test-runner","action":"allow"},{"permission":"task","pattern":"code-reviewer","action":"allow"}]` |

## 事实说明

- M1、M3、M4 属于**权限层 deny**（规则匹配拒绝），证据为原始 JSON 规则回显。
- M2 属于**工具未暴露**，与权限 deny 不同层；该项未取得预期证据，不算通过。
- 本轮探针未使用 bash 或任何替代工具绕过拒绝。
