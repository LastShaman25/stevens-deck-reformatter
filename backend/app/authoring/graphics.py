"""Deterministic graphics. Mathematical input is parsed, never executed."""
import ast
import re
from pathlib import Path
from threading import Lock
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
from matplotlib.mathtext import MathTextParser

_lock = Lock()
_math_parser = MathTextParser('agg')
FUNCTIONS = {k: getattr(np, v) for k, v in {'sin':'sin', 'cos':'cos', 'tan':'tan', 'sqrt':'sqrt',
    'log':'log', 'log10':'log10', 'exp':'exp', 'abs':'abs', 'arcsin':'arcsin', 'arccos':'arccos'}.items()}


def evaluate(expression, x):
    if len(expression) > 300:
        raise ValueError('Function expression is too long.')
    try:
        tree = ast.parse(expression.strip().replace('^', '**'), mode='eval')
    except SyntaxError as exc:
        raise ValueError("Plot functions must be expressions such as sin(x) or (x-1)/2, without 'y =' assignments. "
                         'Use only x, pi, e and explicit numeric parameter values.') from exc
    if len(list(ast.walk(tree))) > 80:
        raise ValueError('Function expression is too complex.')
    def visit(node, depth=0):
        if depth > 15:
            raise ValueError('Function nesting is too deep.')
        if isinstance(node, ast.Expression): return visit(node.body, depth+1)
        if isinstance(node, ast.Constant) and type(node.value) in (float, int) and abs(node.value) <= 1e6:
            return float(node.value)
        if isinstance(node, ast.Name) and node.id in ('x', 'pi', 'e'):
            return {'x': x, 'pi': np.pi, 'e': np.e}[node.id]
        if isinstance(node, ast.Name):
            raise ValueError(f'Undefined plot parameter {node.id!r}. Only x, pi and e are supported; '
                             'supply source-supported numeric values or label explicitly illustrative choices.')
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand, depth+1)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            left, right = visit(node.left, depth+1), visit(node.right, depth+1)
            if isinstance(node.op, ast.Pow) and (not np.isfinite(right).all() or np.any(np.abs(right)>1000)):
                raise ValueError('Exponent exceeds supported complexity.')
            return {ast.Add: np.add, ast.Sub: np.subtract, ast.Mult: np.multiply,
                    ast.Div: np.divide, ast.Pow: np.power}[type(node.op)](left, right)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS and len(node.args) == 1 and not node.keywords:
            return FUNCTIONS[node.func.id](visit(node.args[0], depth+1))
        raise ValueError('Unsupported function syntax. Use x, pi, e, arithmetic, and supported mathematical functions.')
    with np.errstate(all='ignore'):
        return np.broadcast_to(np.asarray(visit(tree), dtype=float), np.shape(x)).copy()


def function_samples(spec):
    if not spec.functions: raise ValueError('No functions supplied.')
    if spec.log_x and spec.x_min <= 0: raise ValueError('Log axis requires a positive domain.')
    x = np.linspace(spec.x_min, spec.x_max, 1201)
    curves = []
    for expression in spec.functions:
        y = evaluate(expression, x)
        y[~np.isfinite(y)] = np.nan
        # Break abrupt jumps and poles, including poles between samples.
        mid = evaluate(expression, (x[:-1]+x[1:])/2)
        scale = max(1., float(np.nanmedian(np.abs(y))) if np.isfinite(y).any() else 1.)
        bad = ~np.isfinite(mid) | (np.abs(np.diff(y)) > 20*scale) | (np.abs(mid-(y[:-1]+y[1:])/2) > 5*scale)
        y[1:][bad] = np.nan
        if spec.log_y: y[y <= 0] = np.nan
        if not np.isfinite(y).any(): raise ValueError('Function has no finite values in this domain.')
        curves.append(y)
    return x, curves


def validate_plot(spec):
    """Use the same executable grammar/domain checks before accepting AI content."""
    if spec.kind == 'function':
        function_samples(spec)
    elif spec.kind == 'scatter':
        if not spec.x or len(spec.x) != len(spec.y): raise ValueError('Scatter x/y lengths must match.')
        if (spec.log_x and min(spec.x)<=0) or (spec.log_y and min(spec.y)<=0): raise ValueError('Log axes require positive data.')
    elif spec.kind == 'histogram':
        if not spec.x: raise ValueError('Histogram data is empty.')
    elif not spec.matrix or not spec.matrix[0] or len({len(row) for row in spec.matrix}) != 1:
        raise ValueError('Heatmap must be nonempty and rectangular.')


def render_plot(spec, path):
    validate_plot(spec)
    with _lock, matplotlib.rc_context({'font.family':'Arial', 'font.size':16, 'legend.fontsize':14, 'axes.labelsize':16}):
        fig, ax = plt.subplots(figsize=(8, 4), layout='constrained')
        try:
            if spec.kind == 'function':
                x, curves = function_samples(spec)
                for expression, y in zip(spec.functions, curves):
                    ax.plot(x, y, label=expression)
                ax.legend()
            elif spec.kind == 'scatter':
                if not spec.x or len(spec.x) != len(spec.y): raise ValueError('Scatter x/y lengths must match.')
                if (spec.log_x and min(spec.x)<=0) or (spec.log_y and min(spec.y)<=0): raise ValueError('Log axes require positive data.')
                ax.scatter(spec.x, spec.y)
            elif spec.kind == 'histogram':
                if not spec.x: raise ValueError('Histogram data is empty.')
                ax.hist(spec.x, bins=min(30, max(1, int(len(spec.x)**.5))))
            else:
                if not spec.matrix or len({len(row) for row in spec.matrix}) != 1: raise ValueError('Heatmap must be rectangular.')
                fig.colorbar(ax.imshow(spec.matrix, aspect='auto'), ax=ax)
            if spec.log_x: ax.set_xscale('log')
            if spec.log_y: ax.set_yscale('log')
            if spec.tick_values: ax.set_xticks(spec.tick_values, spec.tick_labels)
            for point in spec.annotations:
                ax.scatter([point.x],[point.y],color='#A32537',zorder=5)
                ax.annotate(point.label,(point.x,point.y),xytext=(5,12),textcoords='offset points',fontsize=12)
            ax.set_xlabel(spec.x_label); ax.set_ylabel(spec.y_label)
            ax.grid(alpha=.2)
            fig.savefig(path, dpi=180, facecolor='white')
        finally:
            plt.close(fig)


def equation_lines(expression):
    # Normalize only exact equivalent aliases unsupported by MathText. Keep the
    # original authored expression in notes/specification for independent QA.
    if not expression.strip() or len(expression) > 1000 or '$' in expression:
        raise ValueError('Enter math syntax without dollar delimiters (maximum 1000 characters).')
    aliases = {'le':'leq', 'ge':'geq', 'ne':'neq'}
    normalized = re.sub(r'\\(le|ge|ne)(?![A-Za-z])', lambda m: '\\'+aliases[m[1]], expression)
    return normalized.splitlines()


def validate_equation(expression):
    # A single pair of dollar signs across newlines makes Matplotlib silently
    # render raw LaTeX. Parse each complete line as math before accepting it.
    lines = equation_lines(expression)
    with _lock, matplotlib.rc_context({'text.usetex': False}):
        for number, line in enumerate(lines, 1):
            if not line.strip(): continue
            try:
                _math_parser.parse('$'+line+'$', dpi=180)
            except (ValueError, RuntimeError) as exc:
                raise ValueError(f'Unsupported equation syntax on line {number}; use MathText-compatible LaTeX '
                                 'without dollar signs or environments. Each line must be a complete math expression.') from exc
    return lines


def render_equation(expression, path):
    # Matplotlib mathtext is an in-process math parser; TeX execution is disabled.
    lines = validate_equation(expression)
    with _lock, matplotlib.rc_context({'text.usetex': False}):
        fig = plt.figure(figsize=(10, max(2, .7*len(lines))))
        try:
            math = '\n'.join('$'+line+'$' if line.strip() else '' for line in lines)
            fig.text(.5, .5, math, ha='center', va='center', fontsize=30)
            fig.savefig(path, dpi=180, bbox_inches='tight', pad_inches=.3, facecolor='white')
        except (ValueError, RuntimeError) as exc:
            raise ValueError('Unsupported equation syntax; use supported LaTeX-style math notation.') from exc
        finally:
            plt.close(fig)
