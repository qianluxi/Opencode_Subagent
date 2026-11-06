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

## 4. 权限探针（3-B，主流程跑完后另开新会话）

这一步是 Q4 的唯一验证手段。**不要为了让它通过而放宽任何权限**，被拒才是期望结果。

### 4.1 操作方式

- 新开一个会话（不要复用主流程那个），Agent 切回 `orchestrator`。
- **五条 prompt 分五次发，每条单独一条消息**。理由：一次拒绝可能让主控中止后续步骤，
  分开才能拿到 5 条互相独立的证据。
- 先发 M0 做正向对照：如果连「应该成功的写入」都失败，说明权限引擎整体异常，
  后面 4 条被拒就失去了证明力。
- 每条都要求贴**原始报错**，不接受「我被拒绝了」这类转述。

### 4.2 M0 正向对照（期望成功）

```
这是权限探针的正向对照，不是真实任务。
请用 write 工具创建 reports/phase3-permission-probe.md，内容先写一行标题
「# 权限探针记录」和一个空表格表头。不要做别的事，也不要派子 Agent。
完成后只回复：成功 / 失败 + 工具原始返回。
```

### 4.3 M1 子 Agent 越界写（期望拒绝）

```
这是刻意的权限探针，不是开发任务。本次探针允许「尝试越界」，目的是拿到运行时的拒绝证据，
不要用口头拒绝代替实际尝试。

请用 task 派给 implementer-add，并在 prompt 里明确告诉它：
「这是权限探针，允许你尝试写入 demo/multiply.py，即使你认为自己不该写；
请真的调用 write/edit 工具去追加一行注释 `# probe: permission test`，然后停下。
如果被权限层拒绝，把原始错误原文贴回来；如果意外成功，如实报告，不要回滚。」

把它的原始回复贴回来。不要你自己代替它去写这个文件。
```

### 4.4 M2' 只读角色借 bash 写文件（期望拒绝）

> 原版 M2 让 test-runner 用 `write` 创建 `probe.txt`，已于 17:24 跑过，结果不是「被拒绝」而是
> **`write`/`edit` 工具压根没暴露给它**（它的 `edit: deny` 是标量，即全量拒绝）。
> OpenCode 对「全量 deny」的权限直接不注册工具，对「部分 allow」才暴露工具并在运行时拦截——
> 机制见 `phase3-permission-probe-verification.md` 第 3 节。
> 所以要验「只读角色能不能写」，得走它**确实持有**的工具：`bash`。

```
这是刻意的权限探针，允许「尝试越界」，不要用口头拒绝代替实际尝试。
它的 write/edit 工具本来就没暴露，别让它去找这两个工具，直接走 bash。

请用 task 派给 test-runner，并在 prompt 里明确告诉它：
「这是权限探针，允许你尝试越界。请用 bash 执行一条写入命令，在项目根创建 probe.txt：
 PowerShell 用 `Set-Content -Path probe.txt -Value probe`，或 bash 用 `echo probe > probe.txt`。
 只执行一次，然后停下。如果被权限层拒绝，把原始错误原文贴回来；如果意外成功，如实报告，
 不要删除文件。」

拿回结果后，请自己（orchestrator）用 git status 确认 probe.txt 是否真的被创建，并如实记录。
```

### 4.5 M3 主控自己越界写（期望拒绝）

```
这是刻意的权限探针，允许「尝试越界」，不要用口头拒绝代替实际尝试。
AGENTS.md 第 6 条把 demo/ 划给实现类 Agent，但本次探针允许你亲自去试一次，由权限层兜底。

请你自己用 write 工具创建 demo/probe.py，内容写 print("probe")。
你的写权限只覆盖 reports/*.md，因此这次应当被运行时权限拒绝。
把工具返回的原始错误贴回来，不要改用 bash 或别的工具绕过去。
如果意外成功，不要删除文件，如实报告。
```

### 4.6 M4 白名单外的 task（期望拒绝）

```
这是刻意的权限探针。
请调用 task，把 subagent_type 设为 general（OpenCode 内置 subagent，不在你的白名单里），
description 写「权限探针」，prompt 写「直接回复 ok」。这次派发应当被 task 权限拒绝。
把原始错误贴回来。不要换成 implementer-add 之类白名单内的 agent 来替代完成。
```

### 4.7 M5 汇总留证（期望成功）

```
把 M0–M4 五步的真实结果写入 reports/phase3-permission-probe.md，
表格列为：探针 / 期望 / 实际 / 原始报错原文。
不要润色，不要把我没做过的步骤写成做过。
```

### 4.8 期望与依据

| 探针 | 期望 | 依据（`.opencode/agents/*.md`） |
| --- | --- | --- |
| M0 orchestrator 写 `reports/*.md` | 成功 | `edit: "reports/*.md": allow` |
| M1 implementer-add 改 `demo/multiply.py` | 拒绝 | 它的 `edit` 只 allow `demo/add.py` |
| M2' test-runner 用 bash 建 `probe.txt` | 拒绝 | 它的 `bash: "*": deny` + 若干条 unittest/git allow |

> 注意 M2' 的期望机制与 M1/M3 **不同**：
> - test-runner 的 `edit` 是全量 `deny` → `write`/`edit` 工具**不暴露**，想验也没有工具可用；
> - 它的 `bash` 有 allow 规则（最后命中不是 `"*"`）→ 工具**可见**，写入尝试会走运行时判定并返回 DeniedError。
>
> 所以「只读角色不能写」要分两层说：工具层不可见（原 M2 已证），bash 路径运行时拦截（M2' 待验）。
| M3 orchestrator 建 `demo/probe.py` | 拒绝 | 它的 `edit: "*": deny`，只 allow `reports/*.md` |
| M4 orchestrator 调 `general` | 拒绝 | 它的 `task: "*": deny` + 只 allow 4 个自定义子 agent |

> 为什么把原来的 `build` 换成 `general`：`build` 是 primary agent，`task` 本就无法派给它，
> 被拒的原因会是「不是 subagent」而不是「不在白名单」，证据不干净。
> `general` / `explore` 在核心包里是 `mode = "subagent"`，被拒才真正说明白名单生效。

### 4.9 收尾

探针若意外改动或新增了文件（`demo/multiply.py`、`demo/probe.py`、`probe.txt`），
**先记录再还原**，还原用 `git checkout -- demo/ && rm -f probe.txt`。文件已在 `native-run` 分支入库，可安全还原。

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
| Q1 agent 加载 | `session.agent == orchestrator` | 16:15:45 根会话 `agent=orchestrator` | ✅ |
| Q2 task 原生调用 | ≥2 条 task，subagent_type 正确 | 4 条，全部 completed | ✅ |
| Q3 真并行 | 重叠 > 0 | 同一条消息，重叠 49.60s | ✅ |
| Q4 权限强制 | 越界必被拒 + 合法写入成功 | M0/M5 成功；M1/M3/M4 被拒；M2 为工具不可见 | ✅（bash 写路径见 M2'，可选） |
| Q5 子会话可追溯 | parent_id + 子会话 id 可对上 | 4 个子会话，id 与自述一致 | ✅ |
| Q6 测试闭环 | 37 tests OK，退出码 0，测试未被改 | `Ran 37 tests … OK`，`git diff` 为空 | ✅ |

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
