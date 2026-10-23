# AGENTS.md — 本项目对 OpenCode Agent 的通用约定

本项目是一个 **OpenCode 原生 Subagent 编排验证项目**。这里的代码不是产品代码，而是用来验证
「主控 Agent 通过原生 `task` 工具派发子任务、两个开发 Agent 并行实现、独立测试与独立审查」
这条链路能否真的跑通。

## 所有 Agent 的共同硬性规则

1. **契约唯一来源是 `demo/SPEC.md`**。任何实现细节以 SPEC 为准；SPEC 没写的行为不得自行发明后当作契约。
2. **测试是只读资产**。`tests/test_demo.py` 由主控方维护，任何 Agent 不得修改、删除或跳过测试来让结果变绿。
3. **不要触碰全局环境**：
   - 不得修改 `~/.config/opencode/` 下的任何文件（全局配置、`opencode.jsonc`、`package.json`）。
   - 不得读取、打印、复制、回显 `~/.local/share/opencode/auth.json` 或任何 API Key、Token。
   - 不得修改模型提供商配置。
4. **不做破坏性操作**：不执行 `git reset --hard`、`git clean -fdx`、批量删除、格式化磁盘、安装全局包、`pip install` 等与任务无关的命令。
5. **不得伪造证据**：测试是否通过，以真实命令的退出码和输出为准；文件是否交付，以真实文件内容为准。
   不许用「我已完成」「应该可以」代替实际执行。
6. **文件边界即为权限边界**：
   - `demo/add.py` 只属于 `implementer-add`
   - `demo/multiply.py` 只属于 `implementer-multiply`
   - `tests/test_demo.py`、`demo/SPEC.md`、`AGENTS.md`、`opencode.json`、`.opencode/agents/*.md` 不属于任何实现类 Agent
   - `reports/*.md` 只由 `orchestrator` 写入
7. **只读角色不写文件**：`test-runner` 与 `code-reviewer` 一律不修改仓库内容，只返回结论。
8. 实现只用 **Python 标准库**，不引入任何第三方依赖。

## 目录约定

```
opencode.json            项目级 OpenCode 配置（default_agent / subagent_depth / 全局 permission 兜底）
AGENTS.md                本文件，所有 Agent 自动加载
.opencode/agents/*.md    5 个 Agent 的定义（frontmatter + 提示词）
demo/SPEC.md             接口契约与验收条件（唯一契约来源）
demo/add.py              由 implementer-add 创建
demo/multiply.py         由 implementer-multiply 创建
tests/test_demo.py       契约测试（只读，禁止改动）
reports/                 主控 Agent 写出的运行记录
```

## 测试命令（唯一标准命令）

在项目根目录执行：

```bash
python -m unittest discover -s tests -t . -v
```

退出码 `0` 表示全部通过；非 `0` 表示存在失败或错误。任何 Agent 报告测试结果时必须附带该命令的
真实输出摘要（通过数 / 失败数 / 错误数）。

如果环境里没有 `python`（Windows 常见），可用 `py -3 -m unittest discover -s tests -t . -v` 或
`python3 -m unittest ...`；这三条已被各 Agent 的 bash 白名单允许。
