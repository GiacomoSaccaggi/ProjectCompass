import os

import duckdb
import pandas as pd


class DataUtils:
    def __init__(self, dir_path, data_dir=None, **kwargs):
        self.dir_path = dir_path
        base_data = data_dir or dir_path
        if not base_data.endswith('/'):
            base_data = base_data + '/'
        self.data_dir = base_data
        self.save_queries_path = f'{base_data}Saved_queries'
        self.save_data_path = f'{base_data}Saved_data'
        os.makedirs(self.save_queries_path, exist_ok=True)
        os.makedirs(self.save_data_path, exist_ok=True)
        super().__init__(dir_path=dir_path, data_dir=base_data, **kwargs)

    def upload_text_files(self, request):
        for file in request.files.getlist('upload_files'):
            file_name = file.filename.split('/')[-1].split('.')[0]
            file.save(f'{self.save_data_path}/tmp_{file.filename}')
            print(f"Uploading file: {file.filename}")
            df = self.read_data(file_path=f'{self.save_data_path}/tmp_{file.filename}',
                                separator=request.form['separator'],
                                header=int(request.form['header']))
            df.to_csv(f'{self.save_data_path}/{file_name}.csv', index=False)
            os.remove(f'{self.save_data_path}/tmp_{file.filename}')

    def list_data(self):
         return [
            i.split('.')[0] for i in os.listdir(self.save_data_path)
            if i.lower().endswith(('.csv', '.sqlite', '.db'))
        ]

    def sql(self, sql_query: str) -> pd.DataFrame:
        """
        Executes an SQL query against CSV files in a folder using DuckDB.

        DuckDB processes the CSV files directly by path, avoiding the need to
        load the entire content of all files into RAM at once.

        Args:
            folder_path (str): The path to the folder containing the CSV files.
            sql_query (str): The SQL query to execute. File names (without .csv)
                             should be used as table aliases in the query.

        Returns:
            pd.DataFrame: The resul t of the SQL query.
        """

        # 1. Connect to an in-memory DuckDB database
        # ':memory:' ensures the database is temporary
        conn = duckdb.connect(database=':memory:', read_only=False)

        # Dictionary to map simple table aliases (filename without extension) to full paths
        table_map = {}

        # 2. Build the path map for all CSVs and register DuckDB views
        import re
        for filename in os.listdir(self.save_data_path):
            table_alias = filename.split(".")[0]
            file_full_path = os.path.abspath(os.path.join(self.save_data_path, filename)).replace('\\', '/')
            if filename.endswith(".csv"):
                table_map[table_alias] = file_full_path
                escaped_path = file_full_path.replace("'", "''")
                escaped_alias = table_alias.replace('"', '""')
                try:
                    conn.execute(
                        f'CREATE OR REPLACE VIEW "{escaped_alias}" AS SELECT * FROM read_csv_auto(\'{escaped_path}\')'
                    )
                except Exception:
                    pass
                print(f"Mapped table alias '{table_alias}' to file: {file_full_path}")
            elif filename.lower().endswith(('.sqlite', '.db')):
                try:
                    conn.sql("INSTALL sqlite;")
                    conn.sql("LOAD sqlite;")
                except Exception as e:
                    print(f"WARNING: Unable to install/load the SQLite extension: {e}")
                sqlite_schema_name = f"sqlite_{table_alias}"
                try:
                    conn.sql(f"ATTACH '{file_full_path}' AS {sqlite_schema_name} (TYPE sqlite);")
                    print(f"Attached SQLite DB '{filename}' as schema: {sqlite_schema_name}")
                except Exception as e:
                    print(f"ERROR attaching SQLite DB '{filename}': {e}")
                    continue

        # 3. Try executing directly against registered DuckDB views first; fall back to alias substitution
        try:
            return conn.execute(sql_query).fetchdf()
        except Exception:
            pass

        processed_query = sql_query
        for alias in sorted(table_map.keys(), key=len, reverse=True):
            path = table_map[alias]
            processed_query = re.sub(
                rf"(?<![/\w.]){re.escape(alias)}(?![/\w.])",
                f"read_csv_auto('{path}') AS {alias}",
                processed_query,
            )

        print(f"\n--- Processed Query ---\n{processed_query}\n-----------------------\n")

        # 4. Execute the fallback query
        try:
            result_df = conn.execute(processed_query).fetchdf()
            return result_df
        except Exception as e:
            print(f"Error executing DuckDB query: {e}")
            return pd.DataFrame()
        finally:
            conn.close()


    def run_sql(self, sql_query: str, connection_id: int | None = None) -> pd.DataFrame:
        """Run a query locally or route it to a saved remote connection.

        Args:
            sql_query: SQL statement to execute.
            connection_id: Saved connection ID, or ``None`` for local DuckDB.

        Returns:
            The query result as a pandas DataFrame.
        """
        if connection_id is None:
            return self.sql(sql_query)
        from utils.db_connection_service import DbConnectionService

        return DbConnectionService().run_query(connection_id, sql_query)


    @staticmethod
    def read_data(
            file_path: str,  # Path to the uploaded file
            separator: str = ',',  # Value from the form's 'separator' field
            header: int | None = 0  # Value from the form's 'header' field
    ) -> pd.DataFrame:
        """
        Reads a data file (CSV, TSV, text) into a pandas DataFrame
        using specifications provided by the form.

        Args:
            file_path: The local path to the uploaded file.
            separator: The column delimiter specified by the user.
                       If it's an empty string or None, it will default to a comma.
            header: The row index to use as the header (0, 1, ...).
                    If None (or -1 passed from the form and handled), it won't use a header.

        Returns:
            A pandas DataFrame containing the read data.
        """

        # 1. Separator sanitization
        # Handles the common case where a TSV is specified using '\t'
        if separator == '\\t':
            sep_to_use = '\t'
        elif not separator:
            sep_to_use = ','  # Default to comma if not specified
        else:
            sep_to_use = separator

        # 2. Conversion of the form's 'header' value
        # If the user sets -1 in the form, we treat it as None
        if header == -1:
            header_to_use = None
        else:
            # If it's a number (e.g., 0, 1, ...), we use it directly
            header_to_use = header

        print(f"Reading file: {file_path} with separator '{sep_to_use}' and header on row {header_to_use}")

        # 3. Reading the file with pandas.read_csv
        try:
            df = pd.read_csv(
                file_path,
                sep=sep_to_use,
                header=header_to_use,
                engine='python'  # Uses the python engine for better compatibility with complex separators
            )
            return df
        except FileNotFoundError:
            print(f"ERROR: File not found at path: {file_path}")
            return pd.DataFrame()
        except Exception as e:
            print(f"ERROR during file reading: {e}")
            return pd.DataFrame()
