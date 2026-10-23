"""加法模块 —— 契约见 demo/SPEC.md 第 1 节与第 2 节。

仅依赖标准库，不与 demo/multiply.py 互相引用。
"""

import math


def _check_operand_type(value: object, name: str) -> None:
    """类型校验：仅接受 int / float，bool 显式拒绝。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(
            f"操作数 {name} 必须是 int 或 float，实际为 {type(value).__name__}"
        )


def _check_operand_finite(value: int | float, name: str) -> None:
    """有限性校验：float 的 nan / inf / -inf 拒绝；int 永远有限。"""
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"操作数 {name} 必须是有限数值，实际为 {value!r}")


def add(a: int | float, b: int | float) -> int | float:
    """返回两个数值之和。

    参数:
        a: 第一个加数，必须是 int 或 float；bool 视为非法输入。
        b: 第二个加数，必须是 int 或 float；bool 视为非法输入。

    返回:
        两个操作数都是 int 时返回精确的 int（任意精度，不经过 float）；
        任一操作数为 float 时返回 float（标准 IEEE-754 双精度，不做额外舍入）。
        浮点结果若等于 0.0，统一归一化为正零 0.0。

    异常:
        TypeError: a 或 b 不是 int / float（含 bool、str、None、list、dict、complex 等）。
        ValueError: a 或 b 是 nan、inf 或 -inf（仅类型校验通过后才检查）。
    """
    # 1) 类型校验优先，两个操作数都检查完再进入有限性校验
    _check_operand_type(a, "a")
    _check_operand_type(b, "b")

    # 2) 有限性校验
    _check_operand_finite(a, "a")
    _check_operand_finite(b, "b")

    # 3) 全整数路径保持精确
    if isinstance(a, int) and isinstance(b, int):
        return a + b

    result = float(a) + float(b)
    # 4) 负零归一化：-0.0 == 0.0 为真，此时直接返回正零
    return 0.0 if result == 0.0 else result
