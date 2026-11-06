"""乘法模块 —— 契约见 ``demo/SPEC.md`` 第 1 节与第 3 节。

只依赖 Python 标准库，导入时无任何副作用，也不依赖项目内其它模块。
"""

from __future__ import annotations

import math


def multiply(a: int | float, b: int | float) -> int | float:
    """返回两个数值的乘积。

    参数:
        a: 第一个操作数，必须是 ``int`` 或 ``float``；``bool`` 视为非法输入。
        b: 第二个操作数，必须是 ``int`` 或 ``float``；``bool`` 视为非法输入。

    返回:
        - 当 ``a`` 与 ``b`` 都是 ``int`` 时，返回精确的 ``int``（任意精度，不转 float）；
        - 否则返回 ``float``（IEEE-754 双精度原始结果，不做任何额外舍入）。
        - 若浮点结果为 0，统一归一化为正零 ``0.0``（不会返回 ``-0.0``）。

    异常:
        TypeError: 任一操作数不是 ``int``/``float``（包括 ``bool``、``str``、``None``、
            ``list``、``dict``、``complex``、``Decimal`` 等）。类型校验优先于有限性校验。
        ValueError: 类型均合法，但任一操作数为 ``NaN``、``+inf`` 或 ``-inf``。
    """
    # 1) 类型校验（先于有限性校验）：显式排除 bool，因为 bool 是 int 的子类。
    if isinstance(a, bool) or not isinstance(a, (int, float)):
        raise TypeError(
            "multiply() 的参数 a 必须是 int 或 float（bool 非法），"
            f"实际类型为 {type(a).__name__}"
        )
    if isinstance(b, bool) or not isinstance(b, (int, float)):
        raise TypeError(
            "multiply() 的参数 b 必须是 int 或 float（bool 非法），"
            f"实际类型为 {type(b).__name__}"
        )

    # 2) 有限性校验：只有 float 可能非有限，int 永远有限。
    if isinstance(a, float) and not math.isfinite(a):
        raise ValueError(f"multiply() 的参数 a 必须是有限数值，实际为 {a!r}")
    if isinstance(b, float) and not math.isfinite(b):
        raise ValueError(f"multiply() 的参数 b 必须是有限数值，实际为 {b!r}")

    result = a * b

    # 全整数路径：保持 int（含 0，绝不变成 -0.0）。
    if isinstance(a, int) and isinstance(b, int):
        return result

    # 浮点路径：保持 IEEE-754 原始结果，仅把浮点负零归一化成正零。
    result = float(result)
    if result == 0.0:
        return 0.0
    return result
