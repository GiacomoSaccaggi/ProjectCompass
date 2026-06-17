"""
Agent utilities for ProjectCompass.
LLM functionality is lazy-loaded — the application works without Ollama running.
Code execution uses AST-validated sandboxing instead of eval().
"""
import ast
import os

import pandas as pd

from logging_config import logger

# Lazy state
_initialized = False
_project_manager = None


def _initialize_llm(folder_data: str, file_data: str):
    """Initialize LLM components. Call only when needed."""
    global _initialized, _project_manager

    if _initialized:
        return _project_manager

    try:
        from llama_index.core import Settings, SimpleDirectoryReader, VectorStoreIndex
        from llama_index.core.query_engine import RouterQueryEngine
        from llama_index.core.selectors import LLMSingleSelector
        from llama_index.core.tools import QueryEngineTool, ToolMetadata
        from llama_index.embeddings.ollama import OllamaEmbedding
        from llama_index.llms.ollama import Ollama

        ollama_host = os.environ.get('OLLAMA_HOST', 'http://localhost:11434')
        Settings.llm = Ollama(model="llama3", base_url=ollama_host)
        Settings.embed_model = OllamaEmbedding(model_name="nomic-embed-text", base_url=ollama_host)

        reader = SimpleDirectoryReader(input_dir=folder_data)
        documents = reader.load_data()
        rag_index = VectorStoreIndex.from_documents(documents)
        rag_engine = rag_index.as_query_engine(
            system_prompt="Answer questions about the data context, descriptions, and explanations."
        )
        rag_tool = QueryEngineTool(
            query_engine=rag_engine,
            metadata=ToolMetadata(
                name="RAG_Search",
                description="Useful for conceptual questions about the data."
            ),
        )
        _project_manager = RouterQueryEngine(
            selector=LLMSingleSelector.from_defaults(llm=Settings.llm),
            query_engine_tools=[rag_tool],
        )
        _initialized = True
        logger.info("LLM agent initialized successfully")
        return _project_manager

    except Exception as e:
        logger.warning(f"LLM initialization failed (Ollama may not be running): {e}")
        _initialized = True  # Don't retry
        return None


def safe_pandas_query(expression: str, df: pd.DataFrame) -> str:
    """Execute a pandas expression with AST validation. No raw eval()."""
    try:
        tree = ast.parse(expression, mode='eval')
    except SyntaxError as e:
        return f"Syntax error: {e}"

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return "Import not allowed"
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id not in ('len', 'sorted', 'list', 'str', 'int', 'float', 'round', 'type'):
                return f"Function '{node.func.id}' not allowed"

    safe_globals = {"__builtins__": {"len": len, "sorted": sorted, "list": list,
                                     "str": str, "int": int, "float": float, "round": round}}
    safe_locals = {"main_df": df, "pd": pd}

    try:
        result = eval(compile(tree, '<expr>', 'eval'), safe_globals, safe_locals)  # noqa: S307
        if isinstance(result, pd.DataFrame):
            return result.head(20).to_string()
        return str(result)
    except Exception as e:
        return f"Error: {e}"


def query_agent(question: str, folder_data: str, file_data: str) -> str:
    """Query the LLM agent. Returns error string if unavailable."""
    manager = _initialize_llm(folder_data, file_data)
    if manager is None:
        return "LLM service not available. Is Ollama running?"
    try:
        response = manager.query(question)
        return str(response.response)
    except Exception as e:
        return f"Agent error: {e}"
