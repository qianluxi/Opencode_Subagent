# OpenCode 原生 Subagent 多智能体编排验证项目

用最小、可重复的方式验证一件事：**OpenCode 自带的 Agent / Subagent / task 委派机制，能否支撑一个
「主控拆解 → 双开发并行实现 → 独立跑测试 → 独立审查 → 主控验收」的完整闭环。**

本项目**没有**自研调度器、没有 LangGraph / Temporal / Redis，所有委派都走 OpenCode 原生的 `task` 工具。

---

## 1. 当前环境（本仓库基于此版本搭建）

| 项目 | 实测值 | 说明 |
| --- | --- | --- |
| OpenCode 版本 | **1.18.25**（桌面客户端） | `%LOCALAPPDATA%\Programs\@opencode-aidesktop\OpenCode.exe` |
| 安装形态 | **仅桌面 GUI，无 `opencode` CLI** | PATH 中没有命令行入口，因此 `opencode debug agents` 之类命令不可用 |
| 全局配置 | `~/.config/opencode/opencode.jsonc` | **本仓库不修改它** |
| 模型提供商 | 沿用已登录的 `opencode-go` | **本仓库不设置 `model`**，子 Agent 自动继承主控模型 |
| Python | 3.13 | 只用标准库，无第三方依赖 |

> 上表的版本事实来自：读取 `OpenCode.exe` 文件版本号，以及解析客户端内置核心包
> （`resources/app.asar` → `out/main/chunks/node-*.js`）中真实的 schema 与工具定义，
> 而不是照抄历史文档。逐条证据见 `reports/setup-report.md`。

### 1.18.25 的关键机制（直接决定本仓库的写法）

- Agent 定义文件位置：`.opencode/{agent,agents}/**/*.md`（单复数都扫描），文件名即 agent 名。
- Markdown frontmatter 支持：`description`、`mode`、`model`、`temperature`、`top_p`、`hidden`、
  `disable`、`steps`、`tools`（已废弃）、`permission`、`options`。
- `mode` 取值：`primary` / `subagent` / `all`；不写默认 `all`。
- **权限键名是 `bash`，不是 `shell`**（新版文档写 `shell`，1.18.25 实际是 `bash`）。
  可用键：`read` `edit` `glob` `grep` `list` `bash` `task` `external_directory`
  `todowrite` `question` `webfetch` `websearch` `lsp` `doom_loop` `skill`。
- 权限值：`allow` / `deny` / `ask`，或 `{ 模式: 动作 }` 对象；**逐条匹配，最后命中的规则生效**。
  - `edit` / `read` 的模式是**相对当前项目根目录**的路径（如 `demo/add.py`）。
  - `bash` 的模式是**命令字符串**（如 `python -m unittest*`）。
  - `task` 的模式是**子 Agent 名称**（如 `implementer-add`），可写 `"*"` 兜底。
- `subagent_depth` 默认 `1`，即**子 Agent 不能再派生孙 Agent**。本项目显式写死为 `1`。
- 原生并行方式：**在同一条 assistant 消息里并发多个 `task` 工具调用**。`task` 工具自带的说明原文是
  “Launch multiple agents concurrently whenever possible … use a single message with multiple tool uses”。
- `task` 还有一个 `background: true` 参数，但 1.18.25 需要环境变量
  `OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true` 才可用，本项目**不启用**（见第 7 节限制）。

---

## 2. 架构

```
                    ┌──────────────────────────────────────────┐
   用户一句话 ─────▶ │ orchestrator （mode: primary）            │
                    │ 只读契约 / 只能派发 4 个指定子 Agent        │
                    │ 唯一可写目录：reports/*.md                │
                    └───────┬───────────────┬──────────────────┘
          T2 task（并发一条消息）        T3 task
                            │               │
              ┌─────────────▼──┐   ┌────────▼───────────────┐
              │ implementer-add│   │ implementer-multiply   │
              │ 仅写 demo/add.py│   │ 仅写 demo/multiply.py  │
              └─────────────┬──┘   └────────┬───────────────┘
                            └───────┬───────┘
                                    │ T4（等 T2、T3 都完成）
                        ┌───────────▼────────────┐
                        │ test-runner（只读）     │ 运行 tests/test_demo.py
                        └───────────┬────────────┘
                                    │ T5
                        ┌───────────▼────────────┐
                        │ code-reviewer（只读）   │ 对照 SPEC 审查，不改代码
                        └───────────┬────────────┘
                                    │ T6
                        ┌───────────▼────────────┐
                        │ orchestrator 判定 PASS  │ → reports/phase2-run.md
                        └────────────────────────┘
```

## 3. 五个 Agent 的职责与权限

| Agent | mode | 可写文件 | 可调用子 Agent | bash 白名单 |
| --- | --- | --- | --- | --- |
| `orchestrator` | primary | `reports/*.md` | 仅 `implementer-add`、`implementer-multiply`、`test-runner`、`code-reviewer` | `python -m unittest*`、`python -m py_compile*`、`python tests/test_demo.py*`、`git status/diff`，其余 `ask` |
| `implementer-add` | subagent | **仅** `demo/add.py` | 无（`task: deny`） | `py_compile demo/add.py` + 只能跑 `-k AddContractTest` 的测试 |
| `implementer-multiply` | subagent | **仅** `demo/multiply.py` | 无（`task: deny`） | `py_compile demo/multiply.py` + 只能跑 `-k MultiplyContractTest` 的测试 |
| `test-runner` | subagent | 无（`edit: deny`） | 无 | 仅 `python -m unittest*`、`py_compile*`、`git status/diff` |
| `code-reviewer` | subagent | 无（`edit: deny`） | 无 | 仅 `git status/diff` |

额外兜底：`opencode.json` 里全局禁用 `external_directory` / `webfetch` / `websearch`，
并设 `default_agent: orchestrator`、`subagent_depth: 1`。

## 4. 目录结构

```
opencode.json              项目级配置（default_agent / subagent_depth / 全局权限兜底）
AGENTS.md                  所有 Agent 自动加载的通用规则（契约唯一来源、禁改测试、禁碰全局配置）
.opencode/agents/
  orchestrator.md          主控
  implementer-add.md       加法开发
  implementer-multiply.md  乘法开发
  test-runner.md           测试执行
  code-reviewer.md         独立审查
demo/SPEC.md               接口契约与验收条件（唯一契约来源）
demo/add.py                加法实现（第二轮由 implementer-add 产出）
demo/multiply.py           乘法实现（第二轮由 implementer-multiply 产出）
tests/__init__.py          让 `-t .` 形式的 discover / 按类运行可用
tests/test_demo.py         37 条契约测试（18 加法 + 17 乘法 + 2 模块隔离；只读资产，禁止任何 Agent 修改）
reports/setup-report.md    第一阶段的搭建与自检记录
reports/phase2-run.md      第二阶段的运行证据与判定
```

`demo/add.py`、`demo/multiply.py` 在第二轮由两个开发 Agent 分别创建，现已入库。
若要在客户端里重新验证「从零实现」的原生流程，删掉这两个文件即可回到未实现基线：

```bash
rm demo/add.py demo/multiply.py        # 或 git rm demo/add.py demo/multiply.py
python -m unittest discover -s tests -t .   # 会变成 2 failures + 2 errors（预期）
```

## 5. 在第一轮如何加载主控 Agent

1. 打开 OpenCode 桌面客户端。
2. 「打开文件夹 / Open Project」，选择本项目根目录：
   `F:\project\PyProject\Opencode_Subagent`
3. 因为 `opencode.json` 里设了 `"default_agent": "orchestrator"`，打开后默认主 Agent 就是
   `orchestrator`（前提是该目录被识别为项目根，即能看到 `.opencode/`）。
4. 如果不是，用桌面客户端输入区的 Agent 选择器选 `orchestrator`，或按 `Tab` 在 primary agent 之间循环，
   直到当前 Agent 显示为 `orchestrator`。
5. 想直接点名某个子 Agent 时，可以用 `@implementer-add` 这样的提及方式（用户手动调用不受 `task` 权限限制）。

## 6. 如何重启 OpenCode

Agent 定义和 `opencode.json` 在会话启动时加载，改完配置后建议重启再验证：

1. 关闭所有 OpenCode 窗口；
2. 确认进程真的退出（任务管理器里结束残留的 `OpenCode.exe`）；
3. 重新打开客户端 → 打开本项目文件夹 → 核对当前 Agent 是 `orchestrator`。

> 本项目**未验证**热重载行为，所以一律按「改配置 → 重启」处理。

## 7. 如何触发完整验证流程（第二阶段）

在项目根目录打开一个新会话，Agent 选 `orchestrator`，直接发送下面这段（可原样复制）：

```
请按 AGENTS.md 与 demo/SPEC.md 执行一次完整验证：
T1 你自己读 demo/SPEC.md、tests/test_demo.py、AGENTS.md，确认契约与文件边界，输出 T1–T6 任务分解表；
T2/T3 在一条消息里同时发起两个 task 调用，分别派给 implementer-add 与 implementer-multiply，
     prompt 要自包含（契约文件、目标文件、验收标准、禁止事项）；
T4 等两个实现都返回后，先用只读工具确认文件真实存在，再调用 test-runner 运行
     python -m unittest discover -s tests -t . -v，并自己独立再跑一次做交叉验证；
T5 调用 code-reviewer 做只读审查；
T6 汇总真实证据，给出 PASS / FAIL，并写入 reports/phase2-run.md。
不允许用子 Agent 的自述代替真实文件与真实测试输出。
```

### 如何查看证据

| 想看什么 | 在哪看 |
| --- | --- |
| 子会话（每个 task 一个） | 客户端会话列表里的子会话/子任务；`task` 返回内容中也会带可复用的 `task_id` |
| 文件是否真被创建 | `demo/add.py`、`demo/multiply.py` 是否出现；或让主控贴 `git status --short` / `ls demo` |
| 测试真实结果 | 终端里自己跑一遍 `python -m unittest discover -s tests -t . -v`，与 test-runner 的 `Ran N tests` / `OK` 对照 |
| 审查结论 | code-reviewer 的返回原文（应包含 `## 结论: PASS / PASS_WITH_NOTES / FAIL` 与阻断问题清单） |
| 本轮汇总 | `reports/phase2-run.md`（主控唯一有写权限的路径） |

### 测试命令（唯一标准命令）

```bash
python -m unittest discover -s tests -t . -v
```

- 当前（未实现）基线：`Ran 2 tests … FAILED (failures=2, errors=2)`，退出码 1。
  两个 `setUpClass ... ERROR` 表示 `demo.add` / `demo.multiply` 尚不存在，这是**预期**状态。
- 全部通过时应显示 `Ran 37 tests … OK`，退出码 0。

按类单独运行（开发 Agent 的自检方式）：

```bash
python -m unittest discover -s tests -t . -k AddContractTest -v
python -m unittest discover -s tests -t . -k MultiplyContractTest -v
```

## 8. 已知限制（不要在汇报里当成已验证）

1. **没有 CLI**：无法执行 `opencode debug agents` 一类命令来列出已加载 Agent，Agent 是否真的被加载，
   只能靠「会话里能否选到 / 能否通过 task 调起」来确认。
2. **并行是否严格重叠未验证**：本仓库只能保证「按原生方式在一条消息里并发发起两个 task 调用」。
   两个子会话是否真的在时间上重叠，需要用实际的子会话日志/时间戳判断，不能凭结构推断。
3. **`background: true` 不可用**：需要 `OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true`，
   本项目不启用（避免修改用户环境变量）。未启用时传 `background` 会直接报错。
4. **热重载未验证**：改 Agent 定义后按「重启客户端」处理。
5. 桌面客户端的 Agent 选择器 / `Tab` 切换的具体交互，未在本轮逐一截图验证。

## 9. 当前状态

| 项 | 状态 |
| --- | --- |
| 第一阶段（搭建） | 完成，见 `reports/setup-report.md` |
| 第二阶段（运行） | 完成，判定 PASS，见 `reports/phase2-run.md` |
| 测试规模 | 37 条，全部通过 |
| 执行载体 | 第二轮由 WorkBuddy 主控 + 并行 subagent 执行，**不是** OpenCode 原生 `task`，故原生编排能力仍未验证（详见 `phase2-run.md` 第 0 节） |
| 远端仓库 | https://github.com/qianluxi/Opencode_Subagent （`main`） |

测试有效性（不只跑绿，还验证会红）：37 条测试对 7 种典型变异全部报红，包括
「去掉类型注解」「去掉 docstring」「改成 `*args` 签名」「隐式接受 `Decimal`」
「浮点结果四舍五入」「multiply 改回逐参数交错校验」「浮点零返回 `int 0`」。

