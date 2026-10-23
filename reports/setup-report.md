# 第一阶段搭建报告（Setup Report）

- 生成时间：2026-10-23
- 项目根目录：`F:\project\PyProject\Opencode_Subagent`
- 目标：搭建 OpenCode **原生** Subagent 多智能体编排验证环境（不含自研调度器）
- 状态：**第一阶段完成，但未做任何真实多 Agent 运行**。本文所有结论仅限「静态可验证」的部分。

> **后续更新（2026-10-23，第二轮之后）**：本文是第一阶段快照，其中「27 条测试」的计数已不再准确——
> 第二轮跑完后，测试缺口被补齐到 **37 条**（18 加法 + 17 乘法 + 2 隔离），全部通过。
> 运行结果与缺口闭环见 `reports/phase2-run.md`。本文其余结论（环境取证、权限设计）未变。


---

## 1. 环境事实与取证方式

| 事实 | 值 | 取证方式 |
| --- | --- | --- |
| OpenCode 版本 | `1.18.25` | `OpenCode.exe` 的 `FileVersion` / `ProductVersion` |
| 安装位置 | `%LOCALAPPDATA%\Programs\@opencode-aidesktop` | 目录扫描 |
| 形态 | 仅 Electron 桌面客户端，**无 CLI** | PATH 中无 `opencode`；`app.asar/out/main/index.js` 只处理 `opencode://` 深链，无子命令解析 |
| 全局配置 | `~/.config/opencode/opencode.jsonc`（内容仅 `$schema`） | 直接读取，**未修改** |
| 已登录提供商 | `opencode-go`（仅记录名称，未读取任何密钥内容） | 只输出 `auth.json` 的键名，未打印值 |
| Python | `python` → 3.13.14；`py -3` → 3.14.7 | `python --version` / `py --version` |

### 关键配置格式（从客户端内置核心包中核实，非照抄文档）

内置核心包 = `resources/app.asar` 中的 `out/main/chunks/node-*.js`（34 MB，客户端实际运行的 OpenCode 服务端代码）。
以下结论均有对应代码位置：

| 机制 | 1.18.25 的实际行为 | 依据 |
| --- | --- | --- |
| Agent 定义目录 | `.opencode/{agent,agents}/**/*.md`（单复数都扫描，文件名即 agent 名） | `Glob.scan("{agent,agents}/**/*.md", …)` |
| frontmatter 字段 | `description` `mode` `model` `temperature` `top_p` `hidden` `disable` `steps` `tools`(deprecated) `permission` `options` | `ConfigAgentV1` schema |
| `mode` 取值 | `subagent` / `primary` / `all`（缺省 `all`） | schema `Literals(["subagent","primary","all"])` |
| 权限键 | `read` `edit` `glob` `grep` `list` **`bash`** `task` `external_directory` `todowrite` `question` `webfetch` `websearch` `lsp` `doom_loop` `skill` | `InputObject` 结构定义 |
| 权限值 | `allow`/`deny`/`ask`，或 `{pattern: action}`；**最后命中的规则生效** | `Rule = Union[Action, Record<String, Action>]` |
| `edit` 的模式基准 | **相对 worktree 根目录**的路径 | edit 工具：`patterns: [path.relative(instance.worktree, filePath)]` |
| `bash` 的模式基准 | 命令字符串 | bash 工具权限检查 |
| `task` 的模式基准 | 子 Agent 名称 | task 工具：`ctx.ask({permission:"task", patterns:[params.subagent_type]})` |
| 子 Agent 嵌套 | `subagent_depth` 默认 **1**，即子 Agent 不能再生子 Agent | `if depth >= (cfg.subagent_depth ?? 1) fail` |
| 并行方式 | 同一条消息内并发多个 `task` 调用 | task 工具描述原文：*"Launch multiple agents concurrently whenever possible … use a single message with multiple tool uses"* |
| `background` 参数 | 存在，但需 `OPENCODE_EXPERIMENTAL_BACKGROUND_SUBAGENTS=true` | 代码中显式检查该 flag，未开启直接报错 |
| 默认 Agent | `default_agent`（必须是 primary，否则回落 `build`） | config schema 描述 |

**重要差异**：公开文档（较新版本）使用权限键 `shell`，而 **1.18.25 实际是 `bash`**。
本项目按实际版本写 `bash`；若将来升级客户端后发现权限不生效，第一件事就是查这个键名。

---

## 2. 已完成项（文件清单）

| 文件 | 作用 |
| --- | --- |
| `opencode.json` | `default_agent=orchestrator`、`subagent_depth=1`、全局兜底禁用 `external_directory`/`webfetch`/`websearch` |
| `AGENTS.md` | 所有 Agent 自动加载的通用规则：契约唯一来源、测试只读、禁改全局配置、禁读密钥、禁止伪造证据、文件边界 = 权限边界 |
| `.opencode/agents/orchestrator.md` | 主控：primary，只写 `reports/*.md`，`task` 白名单锁定 4 个子 Agent，bash 只放行测试/编译/git 只读 |
| `.opencode/agents/implementer-add.md` | 只写 `demo/add.py`，`task: deny`，只能编译自己文件 + 跑 `-k AddContractTest` |
| `.opencode/agents/implementer-multiply.md` | 只写 `demo/multiply.py`，`task: deny`，只能编译自己文件 + 跑 `-k MultiplyContractTest` |
| `.opencode/agents/test-runner.md` | `edit: deny`，bash 只放行 `python -m unittest*` 等 |
| `.opencode/agents/code-reviewer.md` | `edit: deny`，bash 只放行 `git status`/`git diff` |
| `demo/SPEC.md` | 接口契约：签名、校验顺序、返回类型、负零归一化、边界表、验收条件、禁止项 |
| `tests/__init__.py` | 使 `-t .` 形式的 discover 与按类运行可用 |
| `tests/test_demo.py` | 27 条契约测试（13 加法 + 12 乘法 + 2 模块隔离） |
| `README.md` | 架构、角色、加载方式、重启、触发流程、取证方式、已知限制 |
| `reports/setup-report.md` | 本文件 |

> **刻意不存在**：`demo/add.py`、`demo/multiply.py`。它们必须由第二轮的开发 Agent 创建。

---

## 3. 静态检查结果（全部为真实执行）

### 3.1 JSON 语法与字段

```
$ python -c "json.load(open('opencode.json'))"
JSON OK, keys: ['$schema', 'default_agent', 'subagent_depth', 'permission']
```

- `$schema` → `https://opencode.ai/config.json`（与全局 `opencode.jsonc` 一致）
- `default_agent` / `subagent_depth` / `permission` 三个键均在 1.18.25 的 config schema 中存在（见第 1 节）。

### 3.2 Agent frontmatter YAML 与权限键合法性

用客户端自带的 `yaml` 包解析 5 个 agent 文件，并用 1.18.25 的权限键集合校验：

```
code-reviewer.md         mode=subagent task=deny edited=deny ok
implementer-add.md       mode=subagent task=deny edited=scoped ok
implementer-multiply.md  mode=subagent task=deny edited=scoped ok
orchestrator.md          mode=primary  task={"*":"deny","implementer-add":"allow",
                                       "implementer-multiply":"allow","test-runner":"allow",
                                       "code-reviewer":"allow"}          edited=scoped ok
test-runner.md           mode=subagent task=deny edited=deny ok
```

### 3.3 角色间权限自洽性

```
subagents        : code-reviewer,implementer-add,implementer-multiply,test-runner
orchestrator允许 : code-reviewer,implementer-add,implementer-multiply,test-runner
白名单是否闭合   : true
子Agent均禁止task: true
可写路径         : implementer-add -> demo/add.py | implementer-multiply -> demo/multiply.py | orchestrator -> reports/*.md
是否有Agent能写tests/: false
```

解读：
- 主控的 `task` 白名单与「存在的 subagent 集合」完全一致 —— 既没有漏放（导致派发被拒），也没有多放（放行无关 Agent）。
- 所有 subagent `task: deny`，即使绕过 `subagent_depth` 也无法自行向下派发。
- 写权限只有三处且互不重叠；**没有任何 Agent 能写 `tests/`、`demo/SPEC.md`、`opencode.json`、`.opencode/`**，
  即契约与配置在运行期对所有 Agent 都是只读的。

### 3.4 代码语法

```
$ python -m py_compile tests/test_demo.py
OK
```

（第一轮不存在 `demo/add.py`、`demo/multiply.py`，故无对应编译对象。）

### 3.5 契约与测试一致性（关键检查）

做法：**在项目之外的临时目录** `/tmp/verify` 拷贝 `demo/` 与 `tests/`，写一份参考实现，跑测试，然后整体删除。
项目仓库内不留下任何实现文件。

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 契约可被满足 | `python -m unittest discover -s tests -t . -v`（临时目录） | `Ran 27 tests … OK`，退出码 0 —— 说明 27 条断言彼此不冲突、SPEC 与测试可同时满足 |
| 测试是否有牙齿（变异 1） | 去掉 `bool` 排除校验 | `FAILED (failures=2)` —— `test_rejects_bool_operands` 在两个模块各抓一次 |
| 测试是否有牙齿（变异 2） | 去掉负零归一化 | `FAILED (failures=2)` —— `test_float_zero_is_normalized_to_positive_zero` 生效 |
| 修正历史 bug | 初版 `add(2**70, 1)` 期望值误写成 `2**70`（少加 1） | 由参考实现校验发现并已修正为 `2**70 + 1`；这正是"先验证契约再交付"的价值 |

### 3.6 基线（未实现状态）—— 第二轮开始前的预期输出

```
$ python -m unittest discover -s tests -t . -v
setUpClass (tests.test_demo.AddContractTest) ... ERROR
test_add_module_does_not_import_multiply ... FAIL
test_multiply_module_does_not_import_add ... FAIL
setUpClass (tests.test_demo.MultiplyContractTest) ... ERROR
Ran 2 tests … FAILED (failures=2, errors=2)     # 退出码 1
```

说明：
- 两个 `setUpClass ... ERROR` 的根因是 `ModuleNotFoundError: No module named 'demo.add' / 'demo.multiply'`，
  即"模块尚未实现"。**这是第一阶段的正确状态，不是缺陷。**
- `Ran 2 tests` 看起来少，是因为 `setUpClass` 失败会让整类用例折叠成一条类级 ERROR（Python 3.12+ 行为），
  实际用例总数是 27。第二轮实现完成后应显示 `Ran 27 tests … OK`。
- 测试特意**不**用 `skip` 跳过缺失模块，就是为了让"未实现"在日志里显式留痕，而不是静默 0 用例。

---

## 4. 未解决问题 / 不确定项

| # | 问题 | 现状 | 处理建议 |
| --- | --- | --- | --- |
| 1 | 无法用 `opencode debug agents` 确认 Agent 是否被真正加载 | 客户端无 CLI | 只能靠「会话里能否选到 orchestrator」「task 能否调起 4 个子 Agent」间接确认；第二轮记录实际现象 |
| 2 | 两个 `task` 调用是否**时间上真的重叠** | 结构上已按原生并发写法（单条消息多调用），但未观测 | 第二轮看子会话产生时间/日志；汇报时必须区分"并发派发了"与"并发执行了" |
| 3 | `permission` 规则里 `{pattern: action}` 的匹配是否为 glob 语义（`reports/*.md` 能否匹配子目录） | 代码显示为模式匹配，未实测 | 第二轮验证 orchestrator 能否成功写 `reports/phase2-run.md`；若被拒，改为更宽松写法 |
| 4 | `bash` 模式对命令字符串的匹配精度（`python -m unittest*` 是否覆盖带引号/多行的命令） | 未实测 | 第二轮观察 test-runner 是否被误拒；必要时放宽或改用 `ask` |
| 5 | 桌面客户端的 Agent 选择器 / `Tab` 切换的具体交互 | 未截图逐项验证 | 依赖 `default_agent=orchestrator` 兜底；若未生效，需人工在 UI 选择 |
| 6 | 修改 Agent 定义是否需要重启才生效（热重载） | 未验证 | 统一按"改配置 → 重启客户端"操作 |
| 7 | `demo/` 是 namespace package（无 `__init__.py`），依赖测试里手动注入项目根路径 | 已验证在本机 Python 3.13 下工作 | 若换 Python 版本或换运行目录失败，给 `demo/__init__.py` 补空文件 |
| 8 | 全局 `permission` 兜底是否会与 agent 级规则冲突 | 按"最后命中规则生效"推理，未实测 | 第二轮如有反常拒绝，优先检查规则顺序 |
| 9 | `external_directory: deny` 可能连带拒绝工具输出落盘目录（`~/.local/share/opencode/tool-output/`）的读取 | 本项目命令输出很小，未触发 | 若第二轮出现"读不到工具输出"的报错，把该键改为 `ask` 而非 `deny` |

以上均为**已知不确定**，未在任何地方宣称已验证。

---

## 5. 第二阶段必须实际验证的清单

1. `orchestrator` 能被加载并作为默认 primary agent（打开项目后即生效）。
2. 主控能在**一条消息**里并发发起 `implementer-add` 与 `implementer-multiply` 两个 `task` 调用，且两者都被接受（不因白名单被拒）。
3. 两个实现 Agent 各只创建自己的文件，且**尝试写对方文件时被拒绝**（这是权限边界的真实验证，可让主控在 prompt 里明确要求"不要越界"，越界行为由权限拒绝兜底）。
4. `test-runner` 能真实执行 `python -m unittest discover -s tests -t . -v`，输出 `Ran 27 tests … OK` 且退出码 0。
5. `code-reviewer` 的 `edit: deny` 生效（它若尝试改代码应被拒），并且其结论不是主控结论的复读。
6. 主控能成功写入 `reports/phase2-run.md`，而写入 `demo/`、`tests/` 被拒。
7. 子会话可见性：能否在客户端里看到由 task 派生的子会话。
8. 并行度观测：两个子会话的时间戳/日志是否真的重叠（若不能证明，报告必须写成"并发派发成功，重叠执行未证实"）。
9. 失败路径也要跑一次（可选但有价值）：故意让某个实现少一个校验（例如不排除 `bool`），确认 test-runner 报 FAIL、code-reviewer 报阻断问题、主控给 FAIL —— 用来证明验收不是走过场。

---

## 6. 明确没有做的事

- 没有修改 `~/.config/opencode/`、`~/.local/share/opencode/auth.json`、任何模型提供商配置或系统环境变量。
- 没有编写任何 Python 调度器/编排脚本；所有委派逻辑只存在于 `orchestrator.md` 的提示词与 OpenCode 原生 `task` 工具中。
- 没有创建 `demo/add.py`、`demo/multiply.py`（参考实现只存在于临时目录且已删除）。
- 没有为了让演示"看起来成功"而放宽任何权限；相反，权限是收敛的（写权限仅 3 处、子 Agent 禁 task、全局禁网）。
