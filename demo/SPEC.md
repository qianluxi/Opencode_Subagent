# SPEC — 演示模块接口契约

本文件是**唯一契约来源**。实现方（两个 implementer）、测试方（test-runner）与审查方（code-reviewer）
都以本文件为准；`tests/test_demo.py` 是本契约的机械表达。

本阶段只需要交付两个彼此独立的模块：

| 文件 | 负责 Agent | 公开接口 |
| --- | --- | --- |
| `demo/add.py` | `implementer-add` | `add(a, b)` |
| `demo/multiply.py` | `implementer-multiply` | `multiply(a, b)` |

两个文件**不得互相 import**，不得依赖任何第三方包（只用 Python 标准库），不得修改测试。

---

## 1. 通用接口约定（两个模块都必须遵守）

### 1.1 签名

```python
def add(a, b): ...        # demo/add.py
def multiply(a, b): ...   # demo/multiply.py
```

- 参数名必须是 `a`、`b`，且都必须支持**位置调用**和**关键字调用**：`add(2, 3)` 与 `add(a=2, b=3)` 都要可用。
- 不允许有第 3 个必需参数；不允许通过 `*args` / `**kwargs` 改变参数名。

### 1.2 输入校验（顺序敏感）

按以下顺序校验，先命中先抛出：

1. **类型校验 → `TypeError`**
   两个操作数都必须是 `int` 或 `float`，且**必须是有限数值语义**。
   - `bool` 视为非法输入（Python 中 `bool` 是 `int` 的子类，必须显式排除）：`add(True, 1)` → `TypeError`
   - `str`、`None`、`list`、`dict`、`complex`、`Decimal` 等其他类型 → `TypeError`
   - 只有其中一个非法，也要抛 `TypeError`（不要求指明是哪一个）
2. **有限性校验 → `ValueError`**
   类型合法后，如果任一操作数是 `float('nan')`、`float('inf')`、`float('-inf')` → `ValueError`
   - 注意：`int` 永远有限，不会触发 `ValueError`
   - 校验顺序必须是「先类型后有限性」，因此 `add("1", float("inf"))` 抛 `TypeError`（类型优先）

### 1.3 返回类型

| 操作数类型 | 返回类型 |
| --- | --- |
| 两个都是 `int` | `int`（精确整数，任意精度，**不得**转成 float） |
| 任一为 `float` | `float`（IEEE-754 双精度，不做额外舍入） |

- 返回值不能是 `bool`。
- `int` 结果必须精确：`add(10**18, 10**18) == 2 * 10**18`，`multiply(2**70, 3) == 3 * 2**70`。
- **负零归一化**：如果结果是浮点 `0.0`，必须返回**正零** `0.0`，不得返回 `-0.0`
  （例如 `add(-0.0, -0.0)`、`multiply(-0.0, 0.0)` 都应得到 `math.copysign(1.0, r) > 0`）。

### 1.4 文档要求

- 带类型注解（`def add(a: int | float, b: int | float) -> int | float:`）。
- 带 docstring，说明用途、参数、返回、可能抛出的异常。

---

## 2. `add` 契约（`demo/add.py`）

`add(a, b)` 返回两数之和。

| 调用 | 期望结果 | 备注 |
| --- | --- | --- |
| `add(2, 3)` | `5`（`int`） | 基本用例 |
| `add(-4, 1)` | `-3`（`int`） | 负数 |
| `add(-4, -6)` | `-10`（`int`） | 双负数 |
| `add(0, 0)` | `0`（`int`） | 零 |
| `add(7, 0)` / `add(0, 7)` | `7`（`int`） | 零元 |
| `add(1, 2.5)` | `3.5`（`float`） | 混合类型 → float |
| `add(0.1, 0.2)` | `0.30000000000000004`（`float`） | 标准双精度，**不做**舍入修正 |
| `add(10**18, 10**18)` | `2 * 10**18`（`int`） | 大整数精度 |
| `add(-0.0, -0.0)` | `0.0`（正零） | 负零归一化 |
| `add(True, 1)` | 抛 `TypeError` | `bool` 非法 |
| `add("1", 2)` | 抛 `TypeError` | 非数值 |
| `add(None, 1)` | 抛 `TypeError` | 非数值 |
| `add(float("nan"), 1)` | 抛 `ValueError` | 非有限 |
| `add(float("inf"), 1)` | 抛 `ValueError` | 非有限 |

---

## 3. `multiply` 契约（`demo/multiply.py`）

`multiply(a, b)` 返回两数之积，输入校验与返回类型规则与第 1 节完全相同。

| 调用 | 期望结果 | 备注 |
| --- | --- | --- |
| `multiply(3, 4)` | `12`（`int`） | 基本用例 |
| `multiply(-4, 3)` | `-12`（`int`） | 一负一正 |
| `multiply(-4, -6)` | `24`（`int`） | 双负数 |
| `multiply(0, 0)` / `multiply(9, 0)` / `multiply(0, 9)` | `0`（`int`） | 零 |
| `multiply(-5, 0)` | `0`（`int`），且**不是** `-0.0` | 负零陷阱 |
| `multiply(0.5, 4)` | `2.0`（`float`） | 浮点 |
| `multiply(2, 2.5)` | `5.0`（`float`） | 混合类型 → float |
| `multiply(2**70, 3)` | `3 * 2**70`（`int`） | 大整数精度 |
| `multiply(-0.0, 0.0)` | `0.0`（正零） | 负零归一化 |
| `multiply(True, 2)` | 抛 `TypeError` | `bool` 非法 |
| `multiply("2", 3)` | 抛 `TypeError` | 非数值 |
| `multiply(float("nan"), 2)` | 抛 `ValueError` | 非有限 |
| `multiply(2, float("-inf"))` | 抛 `ValueError` | 非有限 |

---

## 4. 验收条件

本阶段（第二轮）的验收，必须同时满足：

1. `demo/add.py` 与 `demo/multiply.py` 真实存在，且能被导入。
2. 在项目根目录执行 `python -m unittest discover -s tests -t . -v`，退出码为 `0`，
   且 `tests/test_demo.py` 中的全部用例通过（不允许通过修改/删除测试达成）。
3. `code-reviewer` 未给出阻断问题（`FAIL`）。
4. 主控 Agent 自己独立执行过一次测试，结果与 test-runner 一致。

任一条不满足，本轮判定为 `FAIL`。

---

## 5. 明确禁止

- 修改 `tests/test_demo.py`、`demo/SPEC.md`、`AGENTS.md`、`opencode.json`、`.opencode/agents/*.md`。
- 引入第三方依赖、修改 `sys.path` 做 hack、或在被测模块导入时产生副作用。
- 针对测试中的具体数值硬编码返回值。
- 修改全局 OpenCode 配置、模型提供商配置，或读取/打印任何 API Key。
- 两个模块互相 import 或共享私有实现文件（本阶段要求完全独立）。
