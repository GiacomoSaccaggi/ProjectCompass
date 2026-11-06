"""Tests for utils/chunker.py"""
import os
import tempfile

from utils.chunker import (Chunk, chunk_analysis, chunk_file, chunk_markdown,
                            chunk_python, chunk_sql, chunk_text, chunk_yaml)


def test_chunk_python_functions():
    code = '''import os

def hello():
    """Say hello."""
    print("hello")

def world():
    return "world"
'''
    chunks = chunk_python(code, 'test.py')
    func_chunks = [c for c in chunks if c.chunk_type == 'python_function']
    assert len(func_chunks) == 2
    assert func_chunks[0].metadata['name'] == 'hello'
    assert func_chunks[1].metadata['name'] == 'world'


def test_chunk_python_class():
    code = '''class MyClass:
    """A class."""
    def method(self):
        pass
'''
    chunks = chunk_python(code, 'test.py')
    class_chunks = [c for c in chunks if c.chunk_type == 'python_class']
    assert len(class_chunks) == 1
    assert class_chunks[0].metadata['name'] == 'MyClass'


def test_chunk_python_syntax_error():
    code = 'def broken(:\n    pass'
    chunks = chunk_python(code, 'test.py')
    assert len(chunks) == 1
    # scomp-link uses 'paragraph' for unparseable Python
    assert chunks[0].chunk_type in ('python_module', 'paragraph')


def test_chunk_yaml():
    content = '''title: Test Analysis
description: A test
configuration:
  param1: value1
  param2: value2
'''
    chunks = chunk_yaml(content, 'test.yaml')
    assert len(chunks) == 3
    # scomp-link uses metadata['name'] for the key
    names = [c.metadata.get('name', c.metadata.get('key', '')) for c in chunks]
    assert 'title' in names
    assert 'description' in names
    assert 'configuration' in names


def test_chunk_markdown():
    content = '''# Title
Intro text

## Section 1
Content 1

## Section 2
Content 2
'''
    chunks = chunk_markdown(content, 'test.md')
    assert len(chunks) == 3
    # scomp-link uses metadata['name'] for the header
    names = [c.metadata.get('name', c.metadata.get('header', '')) for c in chunks]
    assert 'Title' in names
    assert 'Section 1' in names


def test_chunk_sql():
    content = '''SELECT * FROM users;
INSERT INTO logs VALUES (1, 'test');
DELETE FROM temp;
'''
    chunks = chunk_sql(content, 'test.sql')
    assert len(chunks) == 3
    assert 'SELECT' in chunks[0].text


def test_chunk_text_overlap():
    para1 = ' '.join(['word'] * 300)
    para2 = ' '.join(['text'] * 300)
    content = para1 + '\n\n' + para2
    chunks = chunk_text(content, 'test.txt', max_tokens=500, overlap=50)
    assert len(chunks) >= 2


def test_chunk_file_python():
    with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
        f.write('def foo():\n    pass\n')
        f.flush()
        chunks = chunk_file(f.name)
    os.unlink(f.name)
    assert len(chunks) >= 1


def test_chunk_analysis_directory():
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, 'analysis'))
        with open(os.path.join(tmpdir, 'metadata.yaml'), 'w') as f:
            f.write('title: Test\ndescription: A test analysis\n')
        with open(os.path.join(tmpdir, 'readme.md'), 'w') as f:
            f.write('# Test\nThis is a test.\n')
        with open(os.path.join(tmpdir, 'analysis', 'main.py'), 'w') as f:
            f.write('def run():\n    return True\n')
        chunks = chunk_analysis(tmpdir)
        assert len(chunks) >= 3
        types = {c.chunk_type for c in chunks}
        assert 'yaml_section' in types or 'python_function' in types


def test_chunk_empty_file():
    with tempfile.NamedTemporaryFile(suffix='.py', mode='w', delete=False) as f:
        f.write('')
        f.flush()
        chunks = chunk_file(f.name)
    os.unlink(f.name)
    assert chunks == []
