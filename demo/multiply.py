"""乘法模块（演示用）。

契约来源：``demo/SPEC.md`` 第 1 节「通用接口约定」与第 3 节「multiply 契约」。
本模块只依赖标准库，且不 import 加法模块。
"""

from __future__ import annotations

import math


def _check_type(value: object, name: str) -> None:
    """第一阶段：类型校验，非法则抛 ``TypeError``（``bool`` 显式拒绝）。"""
    if isinstance(value, bool):  # bool 是 int 的子类，必须先排除
        raise TypeError(f"参数 {name} 不能是 bool")
    if not isinstance(value, (int, float)):
        raise TypeError(
            f"参数 {name} 必须是 int 或 float，实际类型为 {type(value).__name__}"
        )


def _check_finite(value: object, name: str) -> None:
    """第二阶段：有限性校验，``nan``/``inf`` 抛 ``ValueError``（``int`` 永远有限）。"""
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"参数 {name} 必须是有限数值，实际为 {value!r}")


def multiply(a: int | float, b: int | float) -> int | float:
    """返回两个数的乘积。

    参数:
        a: 被乘数，必须是 ``int`` 或 ``float``（``bool`` 非法）。
        b: 乘数，必须是 ``int`` 或 ``float``（``bool`` 非法）。

    返回:
        - 当 ``a`` 与 ``b`` 都是 ``int`` 时返回 ``int``，任意精度、不做 float 转换；
        - 否则返回 ``float``；若浮点结果为 ``0.0``，统一归一化为正零 ``0.0``。

    异常:
        TypeError: ``a`` 或 ``b`` 不是 ``int``/``float``（含 ``bool``、``str``、
            ``None``、``list``、``dict``、``complex``、``Decimal`` 等）。
            类型校验优先于有限性校验。
        ValueError: 类型合法但取值为 ``nan``、``inf`` 或 ``-inf``。
    """
    # 两阶段校验：先把两个操作数的类型都校验完，再做有限性校验
    _check_type(a, "a")
    _check_type(b, "b")
    _check_finite(a, "a")
    _check_finite(b, "b")

    # 两个都是 int：整数乘法，天然精确，绝不经过 float
    if isinstance(a, int) and isinstance(b, int):
        return a * b

    # 任一为 float：走 IEEE-754 双精度，不做额外舍入
    result = a * b
    if result == 0.0:  # 命中 +0.0 / -0.0，统一归一化为正零
        return 0.0
    return result
