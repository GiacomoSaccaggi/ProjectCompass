import os
import tempfile

import pandas as pd

from utils.data_utils import DataUtils


def test_list_data():
    # Create temp dir with a CSV
    with tempfile.TemporaryDirectory() as tmpdir:
        du = DataUtils.__new__(DataUtils)
        du.dir_path = tmpdir + '/'
        du.save_queries_path = os.path.join(tmpdir, 'queries')
        du.save_data_path = os.path.join(tmpdir, 'data')
        os.makedirs(du.save_data_path)
        # Create a test CSV
        pd.DataFrame({'a': [1, 2], 'b': [3, 4]}).to_csv(
            os.path.join(du.save_data_path, 'test_data.csv'), index=False)
        result = du.list_data()
        assert 'test_data' in result


def test_sql_query():
    with tempfile.TemporaryDirectory() as tmpdir:
        du = DataUtils.__new__(DataUtils)
        du.dir_path = tmpdir + '/'
        du.save_queries_path = os.path.join(tmpdir, 'queries')
        du.save_data_path = os.path.join(tmpdir, 'data')
        os.makedirs(du.save_data_path)
        pd.DataFrame({'x': [10, 20, 30], 'y': ['a', 'b', 'c']}).to_csv(
            os.path.join(du.save_data_path, 'mydata.csv'), index=False)
        result = du.sql('select x, y from mydata where x > 10')
        assert len(result) == 2
        assert list(result.columns) == ['x', 'y']


def test_sql_empty_result():
    with tempfile.TemporaryDirectory() as tmpdir:
        du = DataUtils.__new__(DataUtils)
        du.dir_path = tmpdir + '/'
        du.save_queries_path = os.path.join(tmpdir, 'queries')
        du.save_data_path = os.path.join(tmpdir, 'data')
        os.makedirs(du.save_data_path)
        pd.DataFrame({'x': [1]}).to_csv(
            os.path.join(du.save_data_path, 'empty_test.csv'), index=False)
        result = du.sql('select x from empty_test where x > 100')
        assert len(result) == 0


def test_read_data():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write('col1,col2\n1,2\n3,4\n')
        f.flush()
        df = DataUtils.read_data(f.name, separator=',', header=0)
        assert list(df.columns) == ['col1', 'col2']
        assert len(df) == 2
    os.unlink(f.name)


def test_list_data_returns_list():
    """Test list_data returns a list with correct format."""
    with tempfile.TemporaryDirectory() as tmpdir:
        du = DataUtils.__new__(DataUtils)
        du.dir_path = tmpdir + '/'
        du.save_queries_path = os.path.join(tmpdir, 'queries')
        du.save_data_path = os.path.join(tmpdir, 'data')
        os.makedirs(du.save_data_path)

        # Create multiple files
        pd.DataFrame({'a': [1]}).to_csv(
            os.path.join(du.save_data_path, 'data1.csv'), index=False)
        pd.DataFrame({'b': [2]}).to_csv(
            os.path.join(du.save_data_path, 'data2.csv'), index=False)

        result = du.list_data()
        assert isinstance(result, list)
        assert 'data1' in result
        assert 'data2' in result


def test_list_data_excludes_non_data_files():
    """Test list_data only includes csv, sqlite, db files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        du = DataUtils.__new__(DataUtils)
        du.dir_path = tmpdir + '/'
        du.save_queries_path = os.path.join(tmpdir, 'queries')
        du.save_data_path = os.path.join(tmpdir, 'data')
        os.makedirs(du.save_data_path)

        # Create valid and invalid files
        pd.DataFrame({'a': [1]}).to_csv(
            os.path.join(du.save_data_path, 'valid.csv'), index=False)
        with open(os.path.join(du.save_data_path, 'invalid.txt'), 'w') as f:
            f.write('not a data file')
        with open(os.path.join(du.save_data_path, 'also_invalid.json'), 'w') as f:
            f.write('{}')

        result = du.list_data()
        assert 'valid' in result
        assert 'invalid' not in result
        assert 'also_invalid' not in result


def test_sql_query_with_aggregation():
    """Test SQL query with GROUP BY aggregation."""
    with tempfile.TemporaryDirectory() as tmpdir:
        du = DataUtils.__new__(DataUtils)
        du.dir_path = tmpdir + '/'
        du.save_queries_path = os.path.join(tmpdir, 'queries')
        du.save_data_path = os.path.join(tmpdir, 'data')
        os.makedirs(du.save_data_path)

        # Create test data with categories
        pd.DataFrame({
            'category': ['A', 'A', 'B', 'B', 'B'],
            'value': [10, 20, 30, 40, 50]
        }).to_csv(os.path.join(du.save_data_path, 'agg_data.csv'), index=False)

        result = du.sql('SELECT category, SUM(value) as total FROM agg_data GROUP BY category ORDER BY category')

        assert len(result) == 2
        assert result[result['category'] == 'A']['total'].iloc[0] == 30
        assert result[result['category'] == 'B']['total'].iloc[0] == 120


def test_sql_query_syntax_error():
    """Test that invalid SQL returns empty DataFrame gracefully."""
    with tempfile.TemporaryDirectory() as tmpdir:
        du = DataUtils.__new__(DataUtils)
        du.dir_path = tmpdir + '/'
        du.save_queries_path = os.path.join(tmpdir, 'queries')
        du.save_data_path = os.path.join(tmpdir, 'data')
        os.makedirs(du.save_data_path)

        pd.DataFrame({'x': [1]}).to_csv(
            os.path.join(du.save_data_path, 'testdata.csv'), index=False)

        # Invalid SQL
        result = du.sql('SELEC * FORM testdata')

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0


def test_sql_query_with_subquery():
    """Test SQL query with subquery."""
    with tempfile.TemporaryDirectory() as tmpdir:
        du = DataUtils.__new__(DataUtils)
        du.dir_path = tmpdir + '/'
        du.save_queries_path = os.path.join(tmpdir, 'queries')
        du.save_data_path = os.path.join(tmpdir, 'data')
        os.makedirs(du.save_data_path)

        pd.DataFrame({
            'value': [10, 20, 30, 40, 50]
        }).to_csv(os.path.join(du.save_data_path, 'numbers.csv'), index=False)

        result = du.sql('''
            SELECT value FROM numbers WHERE value > (SELECT AVG(value) FROM numbers)
        ''')

        assert len(result) == 2
        assert list(result['value']) == [40, 50]


def test_read_data_tsv():
    """Test reading TSV file."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.tsv', delete=False) as f:
        f.write('col1\tcol2\n1\t2\n3\t4\n')
        f.flush()
        df = DataUtils.read_data(f.name, separator='\\t', header=0)
        assert list(df.columns) == ['col1', 'col2']
        assert len(df) == 2
    os.unlink(f.name)


def test_read_data_no_header():
    """Test reading file without header."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        f.write('1,2\n3,4\n')
        f.flush()
        df = DataUtils.read_data(f.name, separator=',', header=-1)
        # Should have numeric column names
        assert len(df) == 2
        assert len(df.columns) == 2
    os.unlink(f.name)


def test_read_data_file_not_found():
    """Test reading non-existent file returns empty DataFrame."""
    df = DataUtils.read_data('/nonexistent/path/file.csv', separator=',', header=0)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0
