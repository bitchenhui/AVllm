"""A bounded integer calculator for local benchmark inference."""
import ast
import operator
import re

INSTRUCTIONS = (
    "可以使用本地整数计算器：需要计算时，最后一行仅写 CALC: 后接一个整数表达式，并停下来等待结果。"
    "支持 + - * // % << >> & | ^ 和括号，禁止变量、函数与浮点数。"
    "收到结果后可以继续计算，最终仍按原题格式回答。每题至多调用三次。"
)
OPERATIONS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
              ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.LShift: operator.lshift,
              ast.RShift: operator.rshift, ast.BitAnd: operator.and_, ast.BitOr: operator.or_,
              ast.BitXor: operator.xor}
MAX_ABS = 2**63 - 1


def calculate(expression):
    if not expression or len(expression) > 120 or not re.fullmatch(r"[\d ()+*/%<>|&^\-]+", expression, re.ASCII):
        raise ValueError("Unsupported expression")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as exc:
        raise ValueError("Invalid integer expression") from exc
    budget = 32

    def visit(node):
        nonlocal budget
        budget -= 1
        if budget < 0:
            raise ValueError("Expression too complex")
        if isinstance(node, ast.Constant) and type(node.value) is int:
            result = node.value
        elif isinstance(node, ast.UnaryOp) and type(node.op) in (ast.UAdd, ast.USub):
            value = visit(node.operand)
            result = value if isinstance(node.op, ast.UAdd) else -value
        elif isinstance(node, ast.BinOp) and type(node.op) in OPERATIONS:
            a, b = visit(node.left), visit(node.right)
            if isinstance(node.op, (ast.LShift, ast.RShift)) and not 0 <= b <= 63:
                raise ValueError("Shift outside 0–63")
            if isinstance(node.op, (ast.FloorDiv, ast.Mod)) and b == 0:
                raise ValueError("Division by zero")
            result = OPERATIONS[type(node.op)](a, b)
        else:
            raise ValueError("Unsupported operation")
        if abs(result) > MAX_ABS:
            raise ValueError("Integer outside supported range")
        return result

    return visit(tree.body)


def request(answer):
    lines = answer.rstrip().splitlines()
    if lines and lines[-1].startswith("CALC:"):
        return lines[-1][5:].strip()
    return None
