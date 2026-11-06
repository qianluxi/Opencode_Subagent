# 第三阶段核对报告（Phase 3 Verification）

- 核对时间：2026-11-06 16:49（+08:00）
- 核对对象：`reports/phase3-native-run.md`（主控自述）+ `opencode.db` 客观记录 + 真实工作区
- 分支：`native-run`
- 核对人：WorkBuddy（非本轮参与方，独立取证）
- 核对方式：`tools/opencode_forensics.py`（只读快照解析 `~/.local/share/opencode/opencode.db`）
  + 本地实跑测试 + `git diff` + 逐行读实现

---

## 0. 一句话结论

**这一轮真的跑通了原生编排，而且比主控自己说的更强**：4 次原生 `task` 调用、子会话 agent 全部正确、
两个开发任务在**同一条消息**内派发且执行区间**真实重叠 49.6 秒**。主控因为「拿不到子会话时间戳」
而拒绝声称并行——这个顾虑在它自己的环境里成立，但库里有精确时间戳，事实可以确认。

权限方面：**bash 规则被运行时强制**（5 次拦截，含 reviewer 的 `python -c`），
但 `edit` 越界与 `task` 白名单外调用**从未被触碰**，因此这两条仍是未验证，需要 3-B 探针。

---

## 1. Q1–Q6 判定

| # | 问题 | 结论 | 客观证据 |
| --- | --- | --- | --- |
| Q1 | 5 个 agent 是否被加载 | ✅ 通过 | 根会话 `session.agent = orchestrator`；4 个子会话 agent 分别为 `implementer-add` / `implementer-multiply` / `test-runner` / `code-reviewer`，与配置文件一一对应 |
| Q2 | `task` 是否被原生调用 | ✅ 通过 | 库中 4 条 `tool == "task"`，`subagent_type` 全部正确，状态均 `completed`；全库此前为 0，本轮首次出现 |
| Q3 | 两个开发是否真并行 | ✅ 通过 | 两条 task 属于**同一条消息** `msg_1aff2eb76001Z6Z1oYtT3no5t9`；执行区间重叠 **49.60s**（16:23:01.215–16:23:50.815 完全落在 add 的 16:22:47.358–16:28:08.824 之内） |
| Q4 | 权限是否运行时强制 | ✅ 通过（3-B 探针已闭环） | 主流程：5 次工具调用被引擎拦截。3-B 探针：M1 `implementer-add` 越界 `edit demo/multiply.py` 被拒、M3 主控 `write demo/probe.py` 被拒、M4 `task → general` 1ms 内被拒且不产生子会话，三条错误原文入库且与自述逐字一致；M0/M5 两次合法写入成功（正向对照）。详见 `phase3-permission-probe-verification.md` |
| Q5 | 子会话可追溯 | ✅ 通过 | 4 个子会话 `parent_id` 均指向根会话，id 与主控报告列出的 task_id 完全一致 |
| Q6 | 测试闭环 | ✅ 通过 | 本地实跑 `Ran 37 tests … OK`，退出码 0；`git diff` 为空 → `tests/`、`SPEC.md`、配置均未被改 |

---

## 2. 客观时间线

| 时刻 | 事件 | 来源 |
| --- | --- | --- |
| 16:15:45 | 根会话建立，`agent=orchestrator` | `session.time_created` |
| 16:16:44 | 主控自查分支与文件 | bash part |
| 16:21:35 | 含 2 个 `task` 调用的助手消息创建 | `message.time_created` |
| 16:22:47.355 | 子会话 `implementer-add` 创建 | `session` |
| 16:22:47.358 | task#1 开始 | `part.state.time.start` |
| 16:23:01.213 | 子会话 `implementer-multiply` 创建 | `session` |
| 16:23:01.215 | task#2 开始 | 同上 |
| 16:23:24.647 | multiply 写入 `demo/multiply.py` | `write` part |
| 16:23:50.815 | task#2 结束（49.6s） | 同上 |
| 16:24:48.645 | add 写入 `demo/add.py` | `write` part |
| 16:28:08.824 | task#1 结束（5m21.5s） | 同上 |
| 16:32:22.781 → 16:33:06.851 | test-runner 执行（44.07s） | task#3 |
| 16:34:05.307 → 16:39:38.944 | code-reviewer 审查（5m33.6s） | task#4 |
| 16:41:24.572 | 主控写入 `reports/phase3-native-run.md` | `write` part |

两个 task **不是同一瞬间启动**：第二个比第一个晚 13.86 秒。但 multiply 的整个执行期都落在 add 的执行期内，
重叠 49.6 秒，且两者各写各的文件（`multiply.py` 16:23:24、`add.py` 16:24:48，都在重叠窗口内）。
所以准确表述是：**并发派发成立、执行区间真实重叠，但启动有约 14 秒的错峰**。

---

## 3. 主控自述 vs 客观记录

| 主控的说法 | 核对结果 |
| --- | --- |
| 「两个 task 在同一条消息中一次性并列发出」 | ✅ 属实，两条 task 的 `message_id` 相同 |
| 「无法获取子会话墙钟时间，因此不声称并行」 | ⚠️ **自述过于保守**。库里有每个 task 的 `start/end`，重叠 49.6s 可以确认；主控只是拿不到这些字段 |
| 「派发前 16:21:34」 | ✅ 与 16:21:35 的派发消息吻合 |
| 「收到两个结果后、下一条工具调用 16:31:45」 | ⚠️ 口径不准：add 在 16:28:08.824 就返回，16:28:09 已有下一条助手消息；16:31:45 是更晚的一次自查。不影响结论，但时间线需修正 |
| 「git status 只有两个新增文件」 | ✅ 写入时属实；现在多出 `reports/phase3-native-run.md`（主控 16:41 自己写的），正常 |
| 「reviewer 因 bash 受限只能静态审查」 | ✅ 属实，且库中确有 16:36:42 的 `python -c` 被拒记录 |
| 「4 次子会话 id」 | ✅ 与 `session` 表逐一对应，无一虚构 |

**这轮最有说服力的一点**：主控在自己的报告里主动写「不声称并行」「子 Agent 自述不作为通过依据」，
而客观记录显示它既没有虚报、也没有掩盖 reviewer 无法动态验证的局限。**自述的保守程度超过了事实要求**——
这是比"漂亮结论"更值钱的东西。

---

## 4. 实现是否可信（防作弊核对）

| 检查 | 结果 |
| --- | --- |
| 与第二轮版本是否雷同 | ❌ 不相同：add 改成 `for` 循环两阶段校验、去掉了私有 helper；multiply 改为逐参数展开、显式 `float(result)`。两个 agent 的风格彼此不同，不像互相抄袭或复制历史版本 |
| 是否硬编码测试数值 | 未发现：实现走通用类型/有限性校验，无针对 `0.30000000000000004`、`2**70` 等常量的分支 |
| 交叉 import | 无：两份实现都只 `import math` |
| 测试是否被改 | 未改：`git diff` 为空，测试 37 条全绿 |
| 导入期副作用 | 无，模块级只有常量与函数定义 |

---

## 5. 权限的实证与空白

**已被运行时强制（有据）**——5 次拦截：

| 时刻 | Agent | 被拒命令（截断） |
| --- | --- | --- |
| 16:24:02 | implementer-add | `python --version; if ($?) { Write-Output "python-ok" }` |
| 16:26:21 | implementer-add | `python -m unittest … -k AddContractTest -v; Write-Output "EXIT_CODE=…"` |
| 16:32:38 | test-runner | `python -m unittest … 2>&1 \| Out-String -Width 4096 \| Write-Output; …` |
| 16:35:23 | code-reviewer | `git status --porcelain; echo "---DIFF-TESTS---"; git diff …` |
| 16:36:42 | code-reviewer | `python -c "import sys; sys.path.insert(0,'.'); import demo.add as m; print(m.add(2,3))"` |

**写操作落点**（3 次，全部合法，0 次越界尝试）：

```
implementer-multiply → demo/multiply.py      completed
implementer-add      → demo/add.py           completed
orchestrator         → reports/phase3-native-run.md  completed
```

**仍未验证（不能当成已验证）**：

1. `edit` 是否真的拦住 `implementer-add` 改 `demo/multiply.py` —— 本轮没有任何越界写入尝试；
2. `task` 白名单是否真的拦住调 `build` / 白名单外 agent —— 本轮 4 次调用全在白名单内；
3. 子会话在 UI 里是否可见（本轮只证明了库里有会话，没证明界面能点到）。

这三条正是 3-B 探针要打的点，指令见 `reports/phase3-runbook.md` 第 4 节。

---

## 6. 两个设计问题（本轮暴露，尚未修）

**6.1 `code-reviewer` 的只读权限过紧，损害了它的职责。**
它的 bash 只放行 `git status*` / `git diff*`，`python -c` 被拒，因此**无法运行任何动态校验**，
只能静态读代码，并在结论里主动声明「测试是否通过我无法核实」。诚实，但一个不会跑测试的审查者，
对"测试覆盖情况"的判断力是打折的。

建议（择一）：
- 给 `code-reviewer` 的 bash 增加一条只读校验脚本白名单，例如 `python tools/check_contract.py*`，
  让它在受限范围内做动态验证——比放开 `python -c` 安全得多（`-c` 可以写文件）；
- 或明确承认它的职责只有「静态审查」，把动态验证完全交给 test-runner，并在 SPEC 里写清。

**6.2 复合命令的匹配摩擦。**
`implementer-add` 想在测试命令后追加 `; Write-Output "EXIT_CODE=$LASTEXITCODE"` 取退出码，被拒；
而 `implementer-multiply` 用 `; "unittest exit=$LASTEXITCODE"` 却通过。两者语义等价、结果不同，
说明匹配规则对复合命令的处理不是简单的"整串 glob"。**具体机制本轮未查明**，不作为结论。
实践建议：白名单里显式加一条 `python -m unittest*-v*` 之外，直接允许 `*$LASTEXITCODE*` 这类后缀，
或者干脆让 Agent 只用「命令原文 + 退出码另取」的方式，避免踩规则。

---

## 7. 顺带修掉的工具缺陷

`tools/opencode_forensics.py` 在本轮实跑中暴露并修复了 3 个问题（都已验证）：

1. **子会话 id 解析错误**：原实现从 `metadata` 里正则抓第一个 `ses_`，结果抓到的全是**父会话 id**。
   改为按 `(parent_id, agent, time_created)` 在 `session` 表里对齐，现在 4 条 task 都能对到真实子会话。
2. **没有「同消息」证据**：新增按 `message_id` 分组，直接输出「同一条消息内并列 2 个 task 调用」。
3. **变量名覆盖**：`analyse()` 里的循环变量 `data` 覆盖了入参 `data`，导致 `KeyError: 'event_types'`。

新增能力：写操作落点、被权限引擎拒绝的调用（含原文命令）。`--selftest` 仍 5/5 通过。

---

## 8. 剩下要做的

1. ~~跑 3-B 权限探针~~ —— 已于 17:19–17:27 完成，Q4 闭环，见 `phase3-permission-probe-verification.md`；
2. 把 `native-run` 合并回 `main`（主控报告 + 两份核对报告一起入库）；
3. 可选 1：补 M2'（test-runner 走 `bash` 写文件）——目前 `bash` 写路径未单独探，见探针核对报告第 5 节；
4. 可选 2：按 6.1 给 reviewer 加只读校验脚本白名单，然后重跑一次审查，看结论是否变化。
