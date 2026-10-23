"""契约测试 —— 唯一契约来源是 demo/SPEC.md。

本文件由主控侧维护，任何实现类 Agent 都不得修改它。
测试会在被测模块尚未实现时以明确的方式失败（而不是静默跳过），
这样「未实现」和「实现错误」在测试输出里可以被区分开。

运行方式（项目根目录）：
    python -m unittest discover -s tests -t . -v
"""

from __future__ import annotations

import ast
import importlib
import inspect
import math
import sys
import unittest
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def load_module(module_name: str):
    """按契约加载被测模块；缺失时给出可读的失败原因，而不是让整个用例集静默为 0."""
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise AssertionError(
            f"模块 {module_name} 不存在（{exc}）。按 SPEC，该模块应由对应 implementer 创建。"
        ) from exc


def load_callable(module_name: str, function_name: str):
    module = load_module(module_name)
    function = getattr(module, function_name, None)
    if function is None:
        raise AssertionError(f"模块 {module_name} 中缺少契约要求的函数 {function_name}()")
    if not callable(function):
        raise AssertionError(f"{module_name}.{function_name} 不是可调用对象")
    return function


class ContractAssertions:
    """两个模块共用的断言工具."""

    func = None  # 由子类 setUpClass 注入

    def assert_int_result(self, actual, expected):
        self.assertEqual(actual, expected)
        self.assertIsInstance(actual, int)
        self.assertNotIsInstance(actual, bool, "返回值不应为 bool")

    def assert_float_result(self, actual, expected):
        self.assertIsInstance(actual, float, f"期望 float，实际得到 {type(actual)!r}")
        self.assertAlmostEqual(actual, expected, places=12)

    def assert_signature_contract(self):
        """SPEC 1.1：参数名必须恰好是 a、b，且不得用 *args / **kwargs 或第 3 个必填参数改变接口."""
        params = list(inspect.signature(self.func).parameters.values())
        self.assertEqual(
            [p.name for p in params],
            ["a", "b"],
            f"参数名必须恰好是 a、b（SPEC 1.1），实际为 {[p.name for p in params]}",
        )
        for param in params:
            self.assertIs(
                param.kind,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                f"参数 {param.name} 必须同时支持位置调用与关键字调用，实际 kind={param.kind}",
            )

    def assert_documented(self):
        """SPEC 1.4：必须带类型注解（参数 + 返回值）与 docstring."""
        signature = inspect.signature(self.func)
        for name in ("a", "b"):
            self.assertIsNot(
                signature.parameters[name].annotation,
                inspect.Parameter.empty,
                f"参数 {name} 缺少类型注解（SPEC 1.4）",
            )
        self.assertIsNot(
            signature.return_annotation,
            inspect.Signature.empty,
            "缺少返回类型注解（SPEC 1.4）",
        )
        self.assertTrue(
            (self.func.__doc__ or "").strip(),
            "缺少 docstring（SPEC 1.4）",
        )

    def assert_rejects_decimal(self):
        """SPEC 1.2：Decimal 属于「其他类型」，必须抛 TypeError，不做隐式数值转换."""
        with self.assertRaises(TypeError):
            self.func(Decimal("1.5"), 1)
        with self.assertRaises(TypeError):
            self.func(1, Decimal("1.5"))

    def assert_positive_float_zero(self, result, label: str):
        """SPEC 1.3：浮点零必须是 float 且必须是正零."""
        self.assertIsInstance(
            result, float, f"{label} 的浮点零必须是 float，实际为 {type(result)!r}"
        )
        self.assertEqual(result, 0.0)
        self.assertGreater(
            math.copysign(1.0, result), 0.0, f"{label} 不得返回负零 -0.0"
        )


class AddContractTest(ContractAssertions, unittest.TestCase):
    """demo/add.py::add(a, b) 的契约测试."""

    @classmethod
    def setUpClass(cls):
        cls.func = staticmethod(load_callable("demo.add", "add"))

    def test_returns_sum_of_integers(self):
        self.assert_int_result(self.func(2, 3), 5)

    def test_handles_negative_operands(self):
        self.assert_int_result(self.func(-4, 1), -3)
        self.assert_int_result(self.func(-4, -6), -10)
        self.assert_int_result(self.func(-4, 4), 0)

    def test_handles_zero(self):
        self.assert_int_result(self.func(0, 0), 0)
        self.assert_int_result(self.func(7, 0), 7)
        self.assert_int_result(self.func(0, 7), 7)

    def test_handles_float_operands(self):
        self.assert_float_result(self.func(0.5, 1.25), 1.75)
        # 标准 IEEE-754 双精度结果，SPEC 要求不做额外舍入
        self.assert_float_result(self.func(0.1, 0.2), 0.30000000000000004)

    def test_float_result_is_not_rounded(self):
        # SPEC 1.3「不做额外舍入」：必须逐位等于 IEEE-754 原始结果。
        # 用 assertAlmostEqual 会让「round(x, 12) 成 0.3」的实现蒙混过关，所以这里用精确相等。
        self.assertEqual(self.func(0.1, 0.2), 0.30000000000000004)
        self.assertEqual(self.func(0.1, 0.7), 0.7999999999999999)

    def test_mixed_int_and_float_returns_float(self):
        self.assert_float_result(self.func(1, 2.5), 3.5)
        self.assert_float_result(self.func(2.5, 1), 3.5)

    def test_preserves_big_integer_precision(self):
        self.assert_int_result(self.func(10**18, 10**18), 2 * 10**18)
        self.assert_int_result(self.func(2**70, 1), 2**70 + 1)

    def test_accepts_keyword_arguments(self):
        self.assertEqual(self.func(a=2, b=5), 7)

    def test_float_zero_is_normalized_to_positive_zero(self):
        self.assert_positive_float_zero(self.func(-0.0, -0.0), "add(-0.0, -0.0)")
        self.assert_positive_float_zero(self.func(-0.0, 0.0), "add(-0.0, 0.0)")
        self.assert_positive_float_zero(self.func(0.0, -0.0), "add(0.0, -0.0)")

    def test_int_zero_stays_int(self):
        # 全整数路径不能因为负零归一化被误改成 float
        self.assert_int_result(self.func(0, 0), 0)
        self.assert_int_result(self.func(-3, 3), 0)

    def test_rejects_bool_operands(self):
        with self.assertRaises(TypeError):
            self.func(True, 1)
        with self.assertRaises(TypeError):
            self.func(1, False)

    def test_rejects_non_numeric_operands(self):
        for bad in ("1", None, [1], {"a": 1}, complex(1, 2)):
            with self.subTest(operand=bad):
                with self.assertRaises(TypeError):
                    self.func(bad, 2)
                with self.assertRaises(TypeError):
                    self.func(2, bad)

    def test_rejects_nan_operands(self):
        with self.assertRaises(ValueError):
            self.func(float("nan"), 1)
        with self.assertRaises(ValueError):
            self.func(1, float("nan"))

    def test_rejects_infinite_operands(self):
        with self.assertRaises(ValueError):
            self.func(float("inf"), 1)
        with self.assertRaises(ValueError):
            self.func(1, float("-inf"))

    def test_type_error_takes_precedence_over_value_error(self):
        # SPEC 1.2：先类型校验，后有限性校验；与参数顺序无关
        with self.assertRaises(TypeError):
            self.func("1", float("inf"))
        with self.assertRaises(TypeError):
            self.func(float("inf"), "1")

    def test_signature_matches_contract(self):
        # SPEC 1.1：def add(a, b, c) 或 def add(*args) 都必须被判失败
        self.assert_signature_contract()

    def test_is_annotated_and_documented(self):
        # SPEC 1.4
        self.assert_documented()

    def test_rejects_decimal_operands(self):
        # SPEC 1.2 明确把 Decimal 列为非法输入
        self.assert_rejects_decimal()


class MultiplyContractTest(ContractAssertions, unittest.TestCase):
    """demo/multiply.py::multiply(a, b) 的契约测试."""

    @classmethod
    def setUpClass(cls):
        cls.func = staticmethod(load_callable("demo.multiply", "multiply"))

    def test_returns_product_of_integers(self):
        self.assert_int_result(self.func(3, 4), 12)

    def test_handles_negative_operands(self):
        self.assert_int_result(self.func(-4, 3), -12)
        self.assert_int_result(self.func(-4, -6), 24)
        self.assert_int_result(self.func(4, -3), -12)

    def test_handles_zero(self):
        self.assert_int_result(self.func(0, 0), 0)
        self.assert_int_result(self.func(9, 0), 0)
        self.assert_int_result(self.func(0, 9), 0)
        # 负零陷阱：结果必须是整数 0，而不是 -0.0
        self.assert_int_result(self.func(-5, 0), 0)

    def test_handles_float_operands(self):
        self.assert_float_result(self.func(0.5, 4), 2.0)
        self.assert_float_result(self.func(-0.5, 4), -2.0)

    def test_float_result_is_not_rounded(self):
        # SPEC 1.3「不做额外舍入」：必须逐位等于 IEEE-754 原始结果。
        self.assertEqual(self.func(0.1, 3), 0.30000000000000004)
        self.assertEqual(self.func(0.1, 0.2), 0.020000000000000004)

    def test_mixed_int_and_float_returns_float(self):
        self.assert_float_result(self.func(2, 2.5), 5.0)
        self.assert_float_result(self.func(2.5, 2), 5.0)

    def test_preserves_big_integer_precision(self):
        self.assert_int_result(self.func(2**70, 3), 3 * 2**70)
        self.assert_int_result(self.func(10**18, 10**18), 10**36)

    def test_accepts_keyword_arguments(self):
        self.assertEqual(self.func(a=3, b=5), 15)

    def test_rejects_bool_operands(self):
        with self.assertRaises(TypeError):
            self.func(True, 2)
        with self.assertRaises(TypeError):
            self.func(2, False)

    def test_rejects_non_numeric_operands(self):
        for bad in ("2", None, [2], {"a": 2}, complex(2, 3)):
            with self.subTest(operand=bad):
                with self.assertRaises(TypeError):
                    self.func(bad, 3)
                with self.assertRaises(TypeError):
                    self.func(3, bad)

    def test_rejects_nan_operands(self):
        with self.assertRaises(ValueError):
            self.func(float("nan"), 2)
        with self.assertRaises(ValueError):
            self.func(2, float("nan"))

    def test_rejects_infinite_operands(self):
        with self.assertRaises(ValueError):
            self.func(2, float("-inf"))
        with self.assertRaises(ValueError):
            self.func(float("inf"), 2)

    def test_float_zero_is_normalized_to_positive_zero(self):
        self.assert_positive_float_zero(self.func(-0.0, 0.0), "multiply(-0.0, 0.0)")
        self.assert_positive_float_zero(self.func(-0.0, -0.0), "multiply(-0.0, -0.0)")
        # 混合路径：0 是 int，但任一操作数为 float，结果仍是 float 的 -0.0
        self.assert_positive_float_zero(self.func(-1.0, 0), "multiply(-1.0, 0)")

    def test_type_error_takes_precedence_over_value_error(self):
        # SPEC 1.2：先类型校验，后有限性校验；与参数顺序无关。
        # 上一轮 multiply 的校验顺序偏差正是因为没有这条测试才被漏过。
        with self.assertRaises(TypeError):
            self.func("2", float("inf"))
        with self.assertRaises(TypeError):
            self.func(float("nan"), "x")
        with self.assertRaises(TypeError):
            self.func("x", float("nan"))

    def test_signature_matches_contract(self):
        # SPEC 1.1：def multiply(a, b, c) 或 def multiply(*args) 都必须被判失败
        self.assert_signature_contract()

    def test_is_annotated_and_documented(self):
        # SPEC 1.4
        self.assert_documented()

    def test_rejects_decimal_operands(self):
        # SPEC 1.2 明确把 Decimal 列为非法输入
        self.assert_rejects_decimal()


def imported_modules(module) -> set[str]:
    """解析模块源码，返回它 import 的模块名集合."""
    source = Path(module.__file__).read_text(encoding="utf-8")
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


class ModuleIsolationTest(unittest.TestCase):
    """两个模块必须彼此独立（SPEC 第 5 节）."""

    def test_add_module_does_not_import_multiply(self):
        module = load_module("demo.add")
        self.assertFalse(
            {"multiply", "demo.multiply"} & imported_modules(module),
            "demo/add.py 不应 import 乘法模块",
        )

    def test_multiply_module_does_not_import_add(self):
        module = load_module("demo.multiply")
        self.assertFalse(
            {"add", "demo.add"} & imported_modules(module),
            "demo/multiply.py 不应 import 加法模块",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
