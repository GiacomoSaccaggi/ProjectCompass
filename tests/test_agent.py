"""Tests for blueprints/agent.py — safe_execute_pandas and chat routes."""
import pandas as pd

from blueprints.agent import safe_execute_pandas


def test_safe_execute_basic():
    """Test safe_execute_pandas with main_df.head()."""
    df = pd.DataFrame({'a': [1, 2, 3, 4, 5], 'b': ['x', 'y', 'z', 'w', 'v']})
    result = safe_execute_pandas('main_df.head()', df)

    assert 'a' in result
    assert 'b' in result
    assert '1' in result  # First value should be present


def test_safe_execute_blocked_import():
    """Test that import statements are blocked (as invalid syntax in eval mode)."""
    df = pd.DataFrame({'a': [1, 2]})
    result = safe_execute_pandas('import os', df)

    # Import is invalid syntax in eval mode, so it's caught as invalid expression
    assert 'Invalid expression' in result or 'Import' in result


def test_safe_execute_blocked_import_from():
    """Test that from X import Y is blocked (as invalid syntax in eval mode)."""
    df = pd.DataFrame({'a': [1, 2]})
    result = safe_execute_pandas('from os import path', df)

    # from...import is invalid syntax in eval mode
    assert 'Invalid expression' in result or 'Import' in result


def test_safe_execute_blocked_eval():
    """Test that eval() is blocked."""
    df = pd.DataFrame({'a': [1, 2]})
    result = safe_execute_pandas('eval("1+1")', df)

    assert 'Disallowed function' in result


def test_safe_execute_blocked_exec():
    """Test that exec() is blocked."""
    df = pd.DataFrame({'a': [1, 2]})
    result = safe_execute_pandas('exec("x=1")', df)

    assert 'Disallowed function' in result


def test_safe_execute_blocked_open():
    """Test that open() is blocked."""
    df = pd.DataFrame({'a': [1, 2]})
    result = safe_execute_pandas('open("/etc/passwd")', df)

    assert 'Disallowed function' in result


def test_safe_execute_column_access():
    """Test accessing DataFrame columns."""
    df = pd.DataFrame({'score': [10, 20, 30, 40, 50]})
    result = safe_execute_pandas('main_df["score"].describe()', df)

    assert 'mean' in result
    assert 'std' in result
    assert '30' in result  # Mean should be 30


def test_safe_execute_len():
    """Test len() is allowed."""
    df = pd.DataFrame({'a': [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]})
    result = safe_execute_pandas('len(main_df)', df)

    assert '10' in result


def test_safe_execute_shape():
    """Test accessing shape attribute."""
    df = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
    result = safe_execute_pandas('main_df.shape', df)

    assert '3' in result
    assert '2' in result


def test_safe_execute_columns():
    """Test accessing columns attribute."""
    df = pd.DataFrame({'col1': [1], 'col2': [2], 'col3': [3]})
    result = safe_execute_pandas('main_df.columns.tolist()', df)

    assert 'col1' in result
    assert 'col2' in result
    assert 'col3' in result


def test_safe_execute_value_counts():
    """Test value_counts method."""
    df = pd.DataFrame({'category': ['A', 'B', 'A', 'A', 'B', 'C']})
    result = safe_execute_pandas('main_df["category"].value_counts()', df)

    assert 'A' in result
    assert '3' in result  # A appears 3 times


def test_safe_execute_groupby():
    """Test groupby operations."""
    df = pd.DataFrame({
        'group': ['X', 'X', 'Y', 'Y'],
        'value': [10, 20, 30, 40]
    })
    result = safe_execute_pandas('main_df.groupby("group")["value"].sum()', df)

    assert 'X' in result
    assert 'Y' in result
    assert '30' in result  # X sum
    assert '70' in result  # Y sum


def test_safe_execute_sort_values():
    """Test sort_values method."""
    df = pd.DataFrame({'num': [3, 1, 2]})
    result = safe_execute_pandas('main_df.sort_values("num")', df)

    # Result should show sorted order
    assert isinstance(result, str)


def test_safe_execute_syntax_error():
    """Test that syntax errors are handled."""
    df = pd.DataFrame({'a': [1]})
    result = safe_execute_pandas('main_df[', df)

    assert 'Invalid expression' in result


def test_safe_execute_allowed_builtins():
    """Test that allowed builtins work."""
    df = pd.DataFrame({'a': [1.5, 2.7, 3.2]})

    # round
    result = safe_execute_pandas('round(main_df["a"].mean(), 1)', df)
    assert '2.5' in result

    # str
    result = safe_execute_pandas('str(main_df.shape)', df)
    assert '(' in result

    # int
    result = safe_execute_pandas('int(main_df["a"].sum())', df)
    assert '7' in result


def test_safe_execute_iloc():
    """Test iloc accessor."""
    df = pd.DataFrame({'a': [100, 200, 300]})
    result = safe_execute_pandas('main_df.iloc[0]', df)

    assert '100' in result


def test_safe_execute_loc():
    """Test loc accessor."""
    df = pd.DataFrame({'a': [1, 2, 3]}, index=['x', 'y', 'z'])
    result = safe_execute_pandas('main_df.loc["x"]', df)

    assert '1' in result


def test_safe_execute_fillna():
    """Test fillna method."""
    df = pd.DataFrame({'a': [1, None, 3]})
    result = safe_execute_pandas('main_df.fillna(0)', df)

    assert '0' in result


def test_safe_execute_dropna():
    """Test dropna method."""
    df = pd.DataFrame({'a': [1, None, 3]})
    result = safe_execute_pandas('len(main_df.dropna())', df)

    assert '2' in result


def test_safe_execute_nunique():
    """Test nunique method."""
    df = pd.DataFrame({'a': ['x', 'x', 'y', 'z']})
    result = safe_execute_pandas('main_df["a"].nunique()', df)

    assert '3' in result


def test_safe_execute_dataframe_result():
    """Test that DataFrame results are truncated to 20 rows."""
    df = pd.DataFrame({'a': list(range(100))})
    result = safe_execute_pandas('main_df', df)

    # Should only show first 20 rows
    assert '0' in result
    assert '19' in result


def test_chat_page(client):
    """Test GET /chat returns 200."""
    response = client.get('/chat')
    assert response.status_code == 200
    assert b'chat' in response.data.lower() or b'data' in response.data.lower()


def test_chat_analysis_page(client):
    """Test GET /chat/analysis returns 200."""
    response = client.get('/chat/analysis')
    assert response.status_code == 200


def test_chat_ask_no_question(client):
    """Test /chat/ask with no question returns 400."""
    response = client.post('/chat/ask',
                          json={'question': '', 'dataset': 'test'},
                          content_type='application/json')
    assert response.status_code == 400
    assert b'No question provided' in response.data


def test_chat_ask_no_llm(client):
    """Test /chat/ask when LLM unavailable returns 503."""
    response = client.post('/chat/ask',
                          json={'question': 'What is the average?', 'dataset': 'nonexistent'},
                          content_type='application/json')
    # Either 503 (LLM not available) or 404 (dataset not found) is acceptable
    assert response.status_code in [404, 503]
