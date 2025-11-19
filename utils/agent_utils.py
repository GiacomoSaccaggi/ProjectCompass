
# pip install llama-index-llms-ollama llama-index-embeddings-ollama
# pip install "llama-index-core>=0.10.0"
# pip install llama-index-experimental
# pip install llama-index-agents
# pip install llama-index-legacy
# pip install --upgrade mistralai
# pip install pandas

# pip install --upgrade llama-index-core llama-index-experimental mistralai

import os

# Ollama connection llm local
from llama_index.core import Settings
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
ollama_base_url = "http://localhost:11434"
local_llm = Ollama(model="llama3", base_url=ollama_base_url)
local_embed_model = OllamaEmbedding(model_name="nomic-embed-text", base_url=ollama_base_url)
Settings.llm = local_llm
Settings.embed_model = local_embed_model


from llama_index.core import SimpleDirectoryReader, VectorStoreIndex
from llama_index.core.tools import QueryEngineTool, ToolMetadata, FunctionTool
from llama_index.core.query_engine import RouterQueryEngine
from llama_index.core.selectors import LLMSingleSelector
from llama_index.core.query_engine import RouterQueryEngine
from llama_index.core.readers.base import BaseReader
from llama_index.core.schema import Document
import pandas as pd
# Nuova importazione necessaria
from llama_index.core.query_engine import CustomQueryEngine
from llama_index.core.query_engine import CustomQueryEngine
from pydantic import Field
from typing import Callable # Questo rimane corretto
from typing import Callable


class DataForemanQueryEngine(CustomQueryEngine):
    """A QueryEngine that wraps the dataframe analysis function."""

    # 1. Definisci l'attributo come campo Pydantic
    analyze_fn: Callable = Field(
        default=..., description="The function used to execute Python code on the DataFrame."
    )

    # 2. Inizializzazione pulita
    def __init__(self, analyze_fn: Callable, **kwargs):
        # Assegna la funzione come un attributo standard (Pydantic lo gestisce internamente)
        super().__init__(analyze_fn=analyze_fn, **kwargs)

    def custom_query(self, query_str: str):
        # Prompt per la generazione del codice
        prompt = f"""
        You are an expert Python data analyst. Your task is to convert the user's natural language request 
        into a single, executable Python expression that operates on the pandas DataFrame variable 'main_df'.

        ONLY output the Python expression. Do not include any explanation or extra text.

        User Request: {query_str}

        Valid Examples:
            Request: "count the unique values in the 'category' column" -> Output: "main_df['category'].nunique()" -> Description: Returns the total number of distinct, non-null entries in the specified Series.
            Request: "how many rows have the dataframe?" -> Output: "len(main_df)" -> Description: Gets the total count of rows in the DataFrame.
            Request: "what are the columns?" -> Output: "main_df.columns.tolist()" -> Description: Returns a Python list containing the names of all columns.
            Request: "show the first 10 rows" -> Output: "main_df.head(10)" -> Description: Displays the top 10 rows of the DataFrame for quick inspection.
            Request: "show the data type for each column" -> Output: "main_df.dtypes" -> Description: Prints the data type (e.g., int64, object) for every column.
            Request: "get descriptive statistics for numeric columns" -> Output: "main_df.describe()" -> Description: Calculates count, mean, std, min, max, and quartiles for numeric columns.
            Request: "count the frequency of each unique value in 'city'" -> Output: "main_df['city'].value_counts()" -> Description: Shows the distribution of unique values in the 'city' column, sorted by count.
            Request: "filter rows where 'age' is less than 25" -> Output: "main_df[main_df['age'] < 25]" -> Description: Selects a subset of the DataFrame based on a simple numeric condition.
            Request: "filter rows where 'status' is 'Completed' AND 'amount' is greater than 100" -> Output: "main_df[(main_df['status'] == 'Completed') & (main_df['amount'] > 100)]" -> Description: Filters based on multiple conditions using the logical AND operator (&).
            Request: "select only the 'name' and 'email' columns" -> Output: "main_df[['name', 'email']]" -> Description: Subset selection returning a new DataFrame with only the specified columns.
            Request: "group by 'country' and sum the 'sales'" -> Output: "main_df.groupby('country')['sales'].sum()" -> Description: Calculates the total sales aggregate for each distinct country.
            Request: "sort the dataframe by 'date' descending" -> Output: "main_df.sort_values(by='date', ascending=False)" -> Description: Reorders the rows based on the 'date' column, showing the latest dates first.
            Request: "check for the total number of missing values in the dataframe" -> Output: "main_df.isnull().sum().sum()" -> Description: Counts all NaN entries across the entire DataFrame.
            Request: "drop rows with any missing values" -> Output: "main_df.dropna()" -> Description: Creates a new DataFrame excluding any row that contains at least one missing value (NaN).
            Request: "fill missing values in 'commission' with zero" -> Output: "main_df['commission'].fillna(0)" -> Description: Replaces all NaN values in the 'commission' column with the integer 0.
            Request: "create a new column 'is_high' which is True if 'score' is above 90" -> Output: "main_df['is_high'] = main_df['score'] > 90" -> Description: Creates a new boolean flag column based on a condition on an existing column.

        Expression:
        """

        # CORREZIONE QUI: Usa Settings.llm (l'LLM globale) al posto di self.llm (che non è stato assegnato)
        llm_response = Settings.llm.complete(prompt)
        python_expression = str(llm_response).strip().replace('\n', ' ')

        # Chiamiamo la funzione di analisi con l'espressione generata
        return self.analyze_fn(python_expression)

# Import the required LLM (e.g., from llama_index.llms.openai import OpenAI)
# Settings.llm = OpenAI(model="gpt-4") # Use a powerful model for routing/generation

# --- Configuration & Setup ---

# 1. Custom CSV Reader for RAG Index
class CsvReader(BaseReader):
    """Loads CSV data, converting it to a string for semantic indexing."""

    def load_data(self, file_path: str):
        df = pd.read_csv(file_path)
        # Convert the entire content to a string
        text_data = df.to_csv(index=False)
        return [Document(text=text_data, metadata={"filename": file_path})]


# Assumes you have a './data_csv' directory with your CSV files
try:
    folder_data="Saved_data"
    file_data="relatedEntities.csv"
    reader = SimpleDirectoryReader(input_dir=folder_data,
                                   file_extractor={file_data: CsvReader()})
    documents = reader.load_data()

    main_df = pd.read_csv(os.path.join(folder_data, file_data))

except Exception as e:
    print(f"ERROR: Failed to load data. Make sure './data_csv' exists and contains valid CSV files. Details: {e}")
    exit()

# --- LOW-LEVEL MODULES (The Crew) ---

# 👷 1. RAG HISTORIAN (Semantic Retrieval)
rag_index = VectorStoreIndex.from_documents(documents)
rag_engine = rag_index.as_query_engine(
    # Spiritous prompt for RAG Historian
    system_prompt="You are the **RAG Historian**, the site's record keeper. Your job is to dig through dusty old "
                  "texts and blueprints (semantic records). Only answer questions related to *context, descriptions,"
                  " explanations, or specific text retrieval*. Do not attempt to calculate or count—that's the "
                  "Foreman's job! Be descriptive and use the context provided."
)

rag_tool = QueryEngineTool(
    query_engine=rag_engine,
    metadata=ToolMetadata(
        name="RAG_Historian",
        description="Useful for questions requiring conceptual context, descriptions, detailed explanations, or"
                    " retrieving specific text blocks or comments (the 'why' and 'what' of the project's history)."
    ),
)

# 📊 2. DATA FOREMAN (Structural Analysis & Calculations)
def analyze_dataframe(query: str) -> str:
    """
    Useful for questions requiring calculations, counts, aggregations, statistics (sum, average,
    min/max), or filtering the structured data (the 'how much' and 'how many').
    The input 'query' must be a single, direct, executable Python expression or function call
    that operates on the global 'main_df' pandas DataFrame and returns a simple string or number.
    """
    global main_df
    try:
        result = eval(query)
        return f"The result of the data analysis query '{query}' is: {result}"
    except Exception as e:
        return f"Data analysis failed. Error executing code: {e}"

data_foreman_engine = DataForemanQueryEngine(
    analyze_fn=analyze_dataframe,
    # Aggiungi qui l'LLM se non fosse già nelle Settings (ma è già lì, quindi è opzionale)
)

# 3. Usa il QueryEngine nel Tool (ora ha il metodo .query())
data_foreman_tool = QueryEngineTool(
    query_engine=data_foreman_engine, # <-- Ora è un CustomQueryEngine con .query()
    metadata=ToolMetadata(
        name="Data_Foreman",
        description="Useful for questions requiring calculations, counts, aggregations, statistics (sum, average,"
                    " min/max), or filtering the structured data (the 'how much' and 'how many')."
    ),
)
# --- HIGH-LEVEL MODULE (The Project Manager) ---

# 🧠 Router Agent (High-Level Decision Maker)
from llama_index.core.selectors import LLMSingleSelector
from llama_index.core.query_engine import RouterQueryEngine

project_manager = RouterQueryEngine(
    selector=LLMSingleSelector.from_defaults(llm=Settings.llm),
    query_engine_tools=[rag_tool, data_foreman_tool], # Ora entrambi sono QueryEngineTool
    verbose=True,
)

# --- Interaction Loop ---
if __name__ == "__main__":
    print("\n--- Project Manager (RouterQueryEngine) Initialized ---")
    print("Ask about context (Historian) or numbers (Foreman). Type 'exit' to quit.")
    print("-" * 50)
    # ... (Il resto del loop di interazione)
    while True:
        prompt = input("USER (Project Scope): ")
        if prompt.lower() in ['exit', 'quit']:
            break

        try:
            # The Project Manager decides which tool to use
            response = project_manager.query(prompt)
            print(f"\nMANAGER's REPORT:\n{response.response}\n")
        except Exception as e:
            print(f"\n[ERROR] Project Manager could not complete the task: {e}\n")