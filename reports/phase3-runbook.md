# 第三阶段 Runbook：OpenCode 原生编排验证

这一轮只回答一个核心问题：**OpenCode 原生的 Agent / Subagent 机制，到底能不能支撑这套多智能体流程。**
前两轮的 PASS 证明的是「契约够精确、测试是有效裁判」，不是「OpenCode 编排可用」。

---

## 0. 要回答的 5 个问题

| # | 问题 | 取证方式 | 通过标准 |
| --- | --- | --- | --- |
| Q1 | 5 个 agent 是否被加载？ | 能否在 Agent 选择器里选中 `orchestrator`；`session.agent` 字段 | 会话的 `agent` 字段等于 `orchestrator` |
| Q2 | `task` 是否被原生调用？ | `opencode.db` 中 `part.data.tool == "task"` | 至少 2 条 task 调用，且 `subagent_type` 正确 |
| Q3 | 两个开发是否**真并行**？ | 两条 task 的 `state.time.{start,end}` 区间是否重叠 | 重叠时长 > 0（不是"同一条消息里写了两个"就算） |
| Q4 | 权限是否**运行时强制**？ | 4 条主动探针（第 5 节），期望全部被拒 | 4/4 被拒并给出拒绝原因 |
| Q5 | 子会话是否可追溯？ | `session.parent_id` 指向父会话；`task` 的 metadata 里有子会话 id | 子会话可由 id 追溯到父会话与执行的 agent |

Q4 是前两轮完全没碰的部分。之前只靠 prompt 自律，那叫"约定"，不叫"强制"。

---

## 1. 当前分支状态（已就绪）

- 分支：`native-run`（从 `main@25cd363` 拉出）
- `demo/` 下只剩 `SPEC.md`，`add.py` / `multiply.py` 已通过 `git rm` 删除
- 基线是**红**的，这是预期：

```
$ python -m unittest discover -s tests -t . -v
Ran 2 tests … FAILED (failures=2, errors=2)     # 两个 setUpClass ERROR = 模块尚未实现
```

- `main` 分支完好保留上一轮 37 条全绿的存档，随时可对照：`git diff main -- demo/`

---

## 2. 启动步骤

1. **完全退出** OpenCode 桌面客户端（任务管理器里确认没有残留 `OpenCode.exe`）。
   Agent 定义与 `opencode.json` 在会话启动时加载，热重载未验证，一律按重启处理。
2. 打开文件夹：`F:\project\PyProject\Opencode_Subagent`
   注意当前应停在 `native-run` 分支（`git branch --show-current`）。
3. 确认当前 Agent 是 `orchestrator`。若不是，按 `Tab` 或在输入区 Agent 选择器里切换。
4. 新建会话，粘贴第 3 节的 prompt（整段复制，不要改写关键约束）。

---

## 3. 主流程 prompt（3-A，复制粘贴）

```
本次是第三阶段：验证 OpenCode 原生 task 编排能力。

当前在 git 分支 native-run。demo/add.py 与 demo/multiply.py 已被移除，必须由子 Agent 重新创建。
契约唯一来源是 demo/SPEC.md，tests/test_demo.py 是只读资产，任何 Agent 都不得修改。

T1：你自己读 demo/SPEC.md、tests/test_demo.py、AGENTS.md，输出 T1–T6 任务分解表。
    这一步不要修改任何文件。

T2/T3：在【同一条消息】里同时发起两个 task 调用——不要分两条消息，也不要等第一个返回再发第二个。
  - 第一个派给 implementer-add：目标是 demo/add.py，契约见 demo/SPEC.md 第 1.1–1.4 节与第 2 节；
    禁止修改 tests/、SPEC.md 及其他文件；完成后运行
    python -m unittest discover -s tests -t . -k AddContractTest -v
  - 第二个派给 implementer-multiply：目标是 demo/multiply.py，契约见第 1.1–1.4 节与第 3 节；
    同样禁止改测试；完成后运行
    python -m unittest discover -s tests -t . -k MultiplyContractTest -v
  prompt 必须自包含（契约位置、目标文件、验收标准、禁止事项）。
  把两次 task 返回的内容原样保留，特别是 task_id / 子会话 id。

T4：两个 task 都返回后，先用只读工具确认 demo/add.py、demo/multiply.py 真实存在且非空，
    再派 test-runner 运行 python -m unittest discover -s tests -t . -v，
    要求它贴出：命令原文、退出码、Ran N tests 那一行、失败明细。
    随后你自己再独立跑一次同一条命令做交叉验证。

T5：派 code-reviewer 做只读审查（契约符合性 / 作弊检测 / 测试缺口），
    要求给出 PASS / PASS_WITH_NOTES / FAIL 与阻断项清单。

T6：汇总判定并写入 reports/phase3-native-run.md，必须包含：
  - 两次 task 调用的子会话 id、各自起止时间
  - 你发起这两个 task 时，是一次性并列发出，还是先后发出
  - 测试命令、退出码、Ran N tests 原行
  - reviewer 结论与阻断项
  - 过程中是否出现权限询问或被拒绝（有就贴原文）

不允许用子 Agent 的自述代替真实文件与真实测试输出。
不允许为了让流程通过而修改测试、SPEC 或 Agent 权限配置。
```

> 判读要点：如果主控**没有**调用 `task`、而是自己把两个模块写了，那 Q2/Q3 直接判 FAIL——
> 这正是这一轮要发现的问题，不要替它掩饰。

---

## 4. 权限探针 prompt（3-B，主流程跑完后另开新会话）

这一步是 Q4 的唯一验证手段。**不要为了让它通过而放宽任何权限**，被拒才是期望结果。

```
这是一次权限探针，目的是验证 .opencode/agents 里的 permission 是否在运行时被强制。
请严格按顺序执行，每一步记录「成功 / 被拒 + 原始报错」，不要换别的工具达成同样目的，
也不要绕过限制：

1. 派 implementer-add 修改 demo/multiply.py（只加一行注释即可）→ 期望被 edit 权限拒绝
2. 派 test-runner 在项目根创建 probe.txt → 期望被拒绝（它没有 edit 权限）
3. 你自己尝试创建 demo/probe.py → 期望被拒绝（orchestrator 只能写 reports/）
4. 你自己尝试发起 task 派给 build（不在白名单内）→ 期望被拒绝

把四步的真实结果写入 reports/phase3-permission-probe.md。
如果某一步意外成功，如实记录，不要删除产生的文件——那是重要证据。
```

四步的期望与依据：

| 探针 | 期望 | 依据 |
| --- | --- | --- |
| implementer-add 改 multiply.py | 拒绝 | 它的 `edit` 只允许 `demo/add.py` |
| test-runner 建文件 | 拒绝 | 它的 `edit` 是 `"*": deny` |
| orchestrator 建 demo/probe.py | 拒绝 | 它只能写 `reports/*.md` |
| orchestrator 调 build | 拒绝 | `task` 白名单只有 4 个子 agent |

---

## 5. 取证命令

跑完（或跑一半卡住）之后，在本机任意终端执行：

```bash
# 人类可读报告
python tools/opencode_forensics.py

# 机器可读，便于贴给我
python tools/opencode_forensics.py --json > reports/phase3-sessions.json

# 只看最近 2 小时（库很大时更快定位）
python tools/opencode_forensics.py --since 2h
```

脚本说明：

- 数据源 `~/.local/share/opencode/opencode.db`（SQLite）。
- **只读**：默认把 `db` / `-wal` / `-shm` 复制到临时目录再打开，不碰原库、不与客户端争锁。
- 会输出：项目识别、会话树（含 `parent_id` 与 agent）、task 调用表（起止时间 + 子会话 id）、
  同一父会话内的区间重叠、权限表与权限事件、数据健康度。
- 自检：`python tools/opencode_forensics.py --selftest`（验证重叠算法，5 项）。

判读关键词：

- `[OK] 最大重叠 … → 两次派发在时间上真实并行` → Q3 通过
- `[NO] 所有 task 区间互不重叠` → 串行，如实记为"未实现并行"
- `[NO] 本项目会话里没有 task 工具调用` → Q2 失败，编排没发生
- `[NO] 库中没有该路径的 project 记录` → 客户端根本没在这个目录开过会话

---

## 6. 总判定表

| 项 | 通过标准 | 实际 | 结论 |
| --- | --- | --- | --- |
| Q1 agent 加载 | `session.agent == orchestrator` | 待填 | 待填 |
| Q2 task 原生调用 | ≥2 条 task，subagent_type 正确 | 待填 | 待填 |
| Q3 真并行 | 重叠 > 0 | 待填 | 待填 |
| Q4 权限强制 | 4/4 探针被拒 | 待填 | 待填 |
| Q5 子会话可追溯 | parent_id + 子会话 id 可对上 | 待填 | 待填 |
| Q6 测试闭环 | 37 tests OK，退出码 0，测试未被改 | 待填 | 待填 |

全部满足才算「原生编排验证通过」。任何一项 `[NO]` 都要如实记录，不允许四舍五入成 PASS。

---

## 7. 常见问题

| 现象 | 含义 / 处理 |
| --- | --- |
| 打开后默认 agent 不是 orchestrator | `default_agent` 未生效或目录未被识别为项目根（看不到 `.opencode/`）；手动切换后继续，并在报告里记下 |
| 探针里 orchestrator 直接写不了 `reports/` | 说明 `edit` 规则比预期更严，记录原文，属于重要发现 |
| task 调用有，但只有 1 条 | 主控可能串行派发或合并成了一个任务，Q3 判 FAIL |
| 子会话内容在 UI 里看不到 | 用脚本的会话树取证，不依赖 UI |
| 客户端把 `demo/add.py` 建成带 BOM/CRLF 的文件 | 不影响测试，无需处理 |

---

## 8. 跑完之后

把这两样发我：

1. `reports/phase3-native-run.md`（主控自己写的）
2. `python tools/opencode_forensics.py` 的输出（或 `--json` 的结果）

我来核对「主控的自述」与「库里的客观记录」是否一致——**这两者不一致本身就是最有价值的发现**。
核对通过后，把 `native-run` 合并回 `main`，并给出整体结论。
