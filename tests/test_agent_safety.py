import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from blueprints.agent import safe_execute_pandas


def test_safe_basic_expression():
    df = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
    result = safe_execute_pandas("len(main_df)", df)
    assert '3' in result


def test_safe_column_access():
    df = pd.DataFrame({'name': ['alice', 'bob'], 'age': [30, 25]})
    result = safe_execute_pandas("main_df['age'].mean()", df)
    assert '27.5' in result


def test_safe_head():
    df = pd.DataFrame({'x': range(100)})
    result = safe_execute_pandas("main_df.head(5)", df)
    assert '4' in result  # last row of head(5)


def test_blocks_import():
    df = pd.DataFrame({'x': [1]})
    result = safe_execute_pandas("__import__('os').system('echo hacked')", df)
    assert 'Disallowed' in result or 'error' in result.lower()


def test_blocks_eval_in_expression():
    df = pd.DataFrame({'x': [1]})
    result = safe_execute_pandas("eval('1+1')", df)
    assert 'Disallowed' in result or 'error' in result.lower()


def test_blocks_exec():
    df = pd.DataFrame({'x': [1]})
    result = safe_execute_pandas("exec('import os')", df)
    assert 'Disallowed' in result or 'error' in result.lower()


def test_blocks_open():
    df = pd.DataFrame({'x': [1]})
    result = safe_execute_pandas("open('/etc/passwd').read()", df)
    assert 'Disallowed' in result or 'error' in result.lower()


def test_syntax_error():
    df = pd.DataFrame({'x': [1]})
    result = safe_execute_pandas("def foo():", df)
    assert 'Invalid' in result or 'error' in result.lower()


def test_describe():
    df = pd.DataFrame({'val': [10, 20, 30, 40, 50]})
    result = safe_execute_pandas("main_df.describe()", df)
    assert 'mean' in result or '30' in result
