"""安全的公式表达式解析与求值。

公式只接受 Python expression AST 的受限子集。这里不调用 eval/exec，
所有函数均由白名单映射到本模块中的普通 Python 函数。
"""
from __future__ import annotations

import ast
import calendar
import math
from datetime import date, datetime, timedelta
from typing import Any, Callable


class FormulaError(ValueError):
    """用户可修正的公式语法、字段或计算错误。"""


def _parse_datetime(value: Any) -> date | datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (date, datetime)):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            try:
                return date.fromisoformat(text)
            except ValueError as exc:
                raise FormulaError(f"无法解析日期：{value}") from exc
    raise FormulaError(f"值不是日期：{value}")


def _as_date(value: Any) -> date | None:
    parsed = _parse_datetime(value)
    return parsed.date() if isinstance(parsed, datetime) else parsed


def _as_number(value: Any) -> int | float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return value
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise FormulaError(f"值不是数字：{value}") from exc
    return int(number) if number.is_integer() else number


def _flatten_values(args: tuple[Any, ...]) -> list[Any]:
    if len(args) == 1 and isinstance(args[0], (list, tuple)):
        return list(args[0])
    return list(args)


def _numeric_values(args: tuple[Any, ...]) -> list[int | float]:
    values = []
    for value in _flatten_values(args):
        number = _as_number(value)
        if number is not None:
            values.append(number)
    return values


def _concat(*args: Any) -> str:
    return "".join("" if value is None else str(value) for value in args)


def _substring(value: Any, start: Any, length: Any = None) -> str:
    text = "" if value is None else str(value)
    begin = int(_as_number(start) or 0)
    if length is None:
        return text[begin:]
    return text[begin:begin + int(_as_number(length) or 0)]


def _date_diff(end: Any, start: Any, unit: Any = "day") -> int | float | None:
    end_date = _as_date(end)
    start_date = _as_date(start)
    if end_date is None or start_date is None:
        return None
    unit_name = str(unit or "day").lower()
    days = (end_date - start_date).days
    if unit_name in {"day", "days", "d"}:
        return days
    if unit_name in {"week", "weeks", "w"}:
        return days // 7
    months = (end_date.year - start_date.year) * 12 + end_date.month - start_date.month
    if end_date.day < start_date.day:
        months -= 1
    if unit_name in {"month", "months", "m"}:
        return months
    if unit_name in {"quarter", "quarters", "q"}:
        return months // 3
    if unit_name in {"year", "years", "y"}:
        return end_date.year - start_date.year - (
            (end_date.month, end_date.day) < (start_date.month, start_date.day)
        )
    raise FormulaError(f"DATEDIFF 不支持单位：{unit}")


def _date_add(value: Any, amount: Any, unit: Any = "day") -> date | None:
    current = _as_date(value)
    if current is None:
        return None
    number = int(_as_number(amount) or 0)
    unit_name = str(unit or "day").lower()
    if unit_name in {"day", "days", "d"}:
        return current + timedelta(days=number)
    if unit_name in {"week", "weeks", "w"}:
        return current + timedelta(weeks=number)
    if unit_name in {"month", "months", "m"}:
        month_index = current.month - 1 + number
        year = current.year + month_index // 12
        month = month_index % 12 + 1
        day = min(current.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)
    if unit_name in {"year", "years", "y"}:
        day = min(current.day, calendar.monthrange(current.year + number, current.month)[1])
        return date(current.year + number, current.month, day)
    raise FormulaError(f"DATEADD 不支持单位：{unit}")


def _text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _number(value: Any) -> int | float | None:
    return _as_number(value)


def _boolean(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "是"}
    return bool(value)


SAFE_FUNCTIONS: dict[str, Callable[..., Any]] = {
    "ABS": lambda value: abs(_as_number(value) or 0),
    "ROUND": lambda value, digits=0: round(_as_number(value) or 0, int(_as_number(digits) or 0)),
    "FLOOR": lambda value: math.floor(_as_number(value) or 0),
    "CEIL": lambda value: math.ceil(_as_number(value) or 0),
    "MAX": lambda *args: max(_numeric_values(args)) if _numeric_values(args) else None,
    "MIN": lambda *args: min(_numeric_values(args)) if _numeric_values(args) else None,
    "SUM": lambda *args: sum(_numeric_values(args)),
    "AVG": lambda *args: (
        sum(_numeric_values(args)) / len(_numeric_values(args))
        if _numeric_values(args) else None
    ),
    "POWER": lambda value, exponent: (_as_number(value) or 0) ** (_as_number(exponent) or 0),
    "SQRT": lambda value: math.sqrt(_as_number(value) or 0),
    "LOG": lambda value, base=10: math.log(_as_number(value) or 0, _as_number(base) or 10),
    "LN": lambda value: math.log(_as_number(value) or 0),
    "CONCAT": _concat,
    "LEN": lambda value: len("" if value is None else str(value)),
    "UPPER": lambda value: ("" if value is None else str(value)).upper(),
    "LOWER": lambda value: ("" if value is None else str(value)).lower(),
    "TRIM": lambda value: ("" if value is None else str(value)).strip(),
    "SUBSTRING": _substring,
    "REPLACE": lambda value, old, new: ("" if value is None else str(value)).replace(str(old), str(new)),
    "SPLIT": lambda value, separator: ("" if value is None else str(value)).split(str(separator)),
    "CONTAINS": lambda value, part: part in value if isinstance(value, (list, tuple, str)) else False,
    "STARTS_WITH": lambda value, prefix: ("" if value is None else str(value)).startswith(str(prefix)),
    "ENDS_WITH": lambda value, suffix: ("" if value is None else str(value)).endswith(str(suffix)),
    "TODAY": lambda: date.today(),
    "NOW": lambda: datetime.now(),
    "YEAR": lambda value: (_as_date(value).year if _as_date(value) else None),
    "MONTH": lambda value: (_as_date(value).month if _as_date(value) else None),
    "DAY": lambda value: (_as_date(value).day if _as_date(value) else None),
    "DATEDIFF": _date_diff,
    "DATEADD": _date_add,
    "WEEKDAY": lambda value: (_as_date(value).weekday() if _as_date(value) else None),
    "IF": lambda condition, when_true, when_false=None: when_true if condition else when_false,
    "AND": lambda *args: all(bool(value) for value in args),
    "OR": lambda *args: any(bool(value) for value in args),
    "NOT": lambda value: not bool(value),
    "IS_EMPTY": lambda value: value is None or value == "" or value == [],
    "IS_NOT_EMPTY": lambda value: not (value is None or value == "" or value == []),
    "COALESCE": lambda *args: next((value for value in args if value is not None and value != ""), None),
    "TEXT": _text,
    "NUMBER": _number,
    "BOOLEAN": _boolean,
}


FUNCTION_DEFINITIONS = [
    {"name": name, "category": category, "description": description}
    for category, names in {
        "数学": ["ABS", "ROUND", "FLOOR", "CEIL", "MAX", "MIN", "SUM", "AVG", "POWER", "SQRT", "LOG", "LN"],
        "文本": ["CONCAT", "LEN", "UPPER", "LOWER", "TRIM", "SUBSTRING", "REPLACE", "SPLIT", "CONTAINS", "STARTS_WITH", "ENDS_WITH"],
        "日期": ["TODAY", "NOW", "YEAR", "MONTH", "DAY", "DATEDIFF", "DATEADD", "WEEKDAY"],
        "逻辑": ["IF", "AND", "OR", "NOT", "IS_EMPTY", "IS_NOT_EMPTY", "COALESCE"],
        "类型": ["TEXT", "NUMBER", "BOOLEAN"],
    }.items()
    for name in names
    for description in [f"{category}函数 {name}"]
]


class _FormulaValidator(ast.NodeVisitor):
    """拒绝属性访问、下标访问、lambda、推导式和任意未知调用。"""

    allowed_binary = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow)
    allowed_compare = (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn)

    def visit_Constant(self, node: ast.Constant) -> None:
        if not isinstance(node.value, (str, int, float, bool, type(None))):
            raise FormulaError("公式包含不支持的常量类型")

    def visit_Name(self, node: ast.Name) -> None:
        if not node.id.isidentifier():
            raise FormulaError(f"字段名不合法：{node.id}")

    def visit_Call(self, node: ast.Call) -> None:
        if not isinstance(node.func, ast.Name) or node.func.id not in SAFE_FUNCTIONS:
            raise FormulaError("公式只能调用白名单函数")
        if node.keywords:
            raise FormulaError("公式函数不支持命名参数")
        self.generic_visit(node)

    def visit_BinOp(self, node: ast.BinOp) -> None:
        if not isinstance(node.op, self.allowed_binary):
            raise FormulaError("公式包含不支持的运算符")
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        if any(not isinstance(op, self.allowed_compare) for op in node.ops):
            raise FormulaError("公式包含不支持的比较运算符")
        self.generic_visit(node)

    def visit_UnaryOp(self, node: ast.UnaryOp) -> None:
        if not isinstance(node.op, (ast.UAdd, ast.USub, ast.Not)):
            raise FormulaError("公式包含不支持的一元运算符")
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        if not isinstance(node.op, (ast.And, ast.Or)):
            raise FormulaError("公式包含不支持的逻辑运算符")
        self.generic_visit(node)

    def visit_List(self, node: ast.List) -> None:
        self.generic_visit(node)

    def visit_Tuple(self, node: ast.Tuple) -> None:
        self.generic_visit(node)

    def generic_visit(self, node: ast.AST) -> None:
        allowed = (
            ast.Expression, ast.Load, ast.operator, ast.unaryop, ast.boolop,
            ast.cmpop, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow,
            ast.UAdd, ast.USub, ast.Not, ast.And, ast.Or, ast.Eq, ast.NotEq,
            ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
        )
        if not isinstance(node, allowed) and not isinstance(
            node, (ast.Constant, ast.Name, ast.Call, ast.BinOp, ast.Compare, ast.UnaryOp, ast.BoolOp, ast.List, ast.Tuple)
        ):
            raise FormulaError(f"公式包含不支持的语法：{type(node).__name__}")
        super().generic_visit(node)


class FormulaEngine:
    """受限 AST 的解析、依赖提取和求值器。"""

    @staticmethod
    def parse(expression: str) -> ast.Expression:
        if not isinstance(expression, str) or not expression.strip():
            raise FormulaError("公式不能为空")
        if len(expression) > 2000:
            raise FormulaError("公式长度不能超过 2000 个字符")
        try:
            tree = ast.parse(expression.strip(), mode="eval")
        except SyntaxError as exc:
            raise FormulaError(f"公式语法错误：{exc.msg}") from exc
        _FormulaValidator().visit(tree)
        return tree

    @staticmethod
    def extract_dependencies(tree: ast.AST) -> set[str]:
        return {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id not in SAFE_FUNCTIONS
        }

    @classmethod
    def evaluate(cls, tree: ast.Expression, field_values: dict[str, Any]) -> Any:
        try:
            return cls._eval_node(tree.body, field_values)
        except FormulaError:
            raise
        except (ArithmeticError, TypeError, ValueError) as exc:
            raise FormulaError(f"公式计算失败：{exc}") from exc

    @classmethod
    def _eval_node(cls, node: ast.AST, values: dict[str, Any]) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return values.get(node.id)
        if isinstance(node, ast.List):
            return [cls._eval_node(item, values) for item in node.elts]
        if isinstance(node, ast.Tuple):
            return tuple(cls._eval_node(item, values) for item in node.elts)
        if isinstance(node, ast.UnaryOp):
            value = cls._eval_node(node.operand, values)
            if isinstance(node.op, ast.Not):
                return not bool(value)
            number = _as_number(value) or 0
            return number if isinstance(node.op, ast.UAdd) else -number
        if isinstance(node, ast.BinOp):
            left = cls._eval_node(node.left, values)
            right = cls._eval_node(node.right, values)
            if left is None or right is None:
                return None
            operations = {
                ast.Add: lambda: left + right,
                ast.Sub: lambda: left - right,
                ast.Mult: lambda: left * right,
                ast.Div: lambda: left / right,
                ast.Mod: lambda: left % right,
                ast.Pow: lambda: left ** right,
            }
            for operation, callback in operations.items():
                if isinstance(node.op, operation):
                    return callback()
        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                result: Any = True
                for value_node in node.values:
                    result = cls._eval_node(value_node, values)
                    if not result:
                        return result
                return result
            for value_node in node.values:
                result = cls._eval_node(value_node, values)
                if result:
                    return result
            return result if node.values else False
        if isinstance(node, ast.Compare):
            left = cls._eval_node(node.left, values)
            for operation, comparator in zip(node.ops, node.comparators):
                right = cls._eval_node(comparator, values)
                if isinstance(operation, ast.Eq):
                    matches = left == right
                elif isinstance(operation, ast.NotEq):
                    matches = left != right
                elif isinstance(operation, ast.Lt):
                    matches = left is not None and right is not None and left < right
                elif isinstance(operation, ast.LtE):
                    matches = left is not None and right is not None and left <= right
                elif isinstance(operation, ast.Gt):
                    matches = left is not None and right is not None and left > right
                elif isinstance(operation, ast.GtE):
                    matches = left is not None and right is not None and left >= right
                elif isinstance(operation, ast.In):
                    matches = left in right if right is not None else False
                else:
                    matches = left not in right if right is not None else True
                if not matches:
                    return False
                left = right
            return True
        if isinstance(node, ast.Call):
            function = SAFE_FUNCTIONS[node.func.id]
            args = [cls._eval_node(arg, values) for arg in node.args]
            try:
                return function(*args)
            except (ArithmeticError, TypeError, ValueError) as exc:
                raise FormulaError(f"{node.func.id} 计算失败：{exc}") from exc
        raise FormulaError(f"公式包含不支持的节点：{type(node).__name__}")

