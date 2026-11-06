"""加法模块：提供契约要求的 ``add(a, b)``。

契约来源：``demo/SPEC.md`` 第 1 节（通用接口约定）与第 2 节（add 契约）。
本模块只依赖 Python 标准库，导入时不产生任何副作用。
"""

from __future__ import annotations

import math


def add(a: int | float, b: int | float) -> int | float:
    """返回两个数值之和。

    参数:
        a: 第一个操作数，必须是 ``int`` 或 ``float``（``bool`` 被显式排除）。
        b: 第二个操作数，必须是 ``int`` 或 ``float``（``bool`` 被显式排除）。

    返回:
        两个操作数都是 ``int`` 时返回精确的 ``int``（任意精度）；
        任一操作数为 ``float`` 时返回 ``float``（IEEE-754 双精度原始结果，
        不做任何舍入修正）。浮点零结果统一归一化为正零 ``0.0``。

    异常:
        TypeError: 任一操作数不是 ``int`` 或 ``float``（包括 ``bool``、
            ``str``、``None``、``list``、``dict``、``complex``、``Decimal`` 等）。
        ValueError: 类型均合法，但任一操作数为 ``NaN``、``+inf`` 或 ``-inf``。

    校验顺序:
        先对两个操作数做类型校验，全部通过后再做有限性校验；因此
        ``add("1", float("inf"))`` 抛出 ``TypeError`` 而不是 ``ValueError``。
    """
    # 1) 类型校验：两个操作数都必须是 int 或 float；bool 是 int 的子类，必须显式排除。
    for value in (a, b):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(
                f"add() 的操作数必须是 int 或 float，收到 {type(value).__name__!r}"
            )

    # 2) 有限性校验：类型全部合法之后才检查 float 的 NaN / inf；int 永远有限。
    for value in (a, b):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError(f"add() 的操作数必须是有限数值，收到 {value!r}")

    result = a + b

    # 负零归一化：仅对浮点结果生效，整数 0 保持为 int 0。
    if isinstance(result, float) and result == 0.0:
        result = 0.0

    return result
