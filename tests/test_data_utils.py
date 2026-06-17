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
