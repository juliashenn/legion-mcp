#!/usr/bin/env python

import logging
import os
import json
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass
from dotenv import load_dotenv
from typing import Dict, List, Any, Optional, Tuple
from mcp.server.fastmcp import FastMCP, Context
from legion_query_runner import QueryRunner
import sys
import argparse

# Load environment variables
load_dotenv()
logger = logging.getLogger("server")

# Structure for database configuration
@dataclass
class DbConfig:
    id: str
    db_type: str
    configuration: Dict[str, Any]
    description: str
    schema: Optional[List[Dict[str, Any]]] = None
    query_runner: Optional[QueryRunner] = None

# Initialize the Legion Query Runners
def init_config(testing=False, test_db_type=None, test_db_config=None, test_db_configs=None) -> Dict[str, DbConfig]:
    """
    Initialize the Legion Query Runners
    
    Args:
        testing: If True, use test arguments instead of parsing command line
        test_db_type: Test database type (for testing)
        test_db_config: Test database config (for testing)
        test_db_configs: Test database configs (for testing)
    """
    if not testing:
    # Use command line arguments for direct execution
        parser = argparse.ArgumentParser(description='Legion MCP Server')
        parser.add_argument('--db-type', required=False, help='Database type (e.g., mysql, postgresql)')
        parser.add_argument('--db-config', required=False, help='JSON string containing database configuration')
        parser.add_argument('--db-configs', required=False, help='JSON string array containing multiple database configurations')

        args = parser.parse_args()
        
        # Check for multiple database configuration first
        db_configs_str = args.db_configs
        if not db_configs_str:
            db_configs_str = os.getenv("DB_CONFIGS", "")
        
        # Get single database config if needed
        db_type = args.db_type
        db_config_str = args.db_config
    else:
        # For testing, use provided test values
        db_configs_str = test_db_configs
        db_type = test_db_type
        db_config_str = test_db_config
        
        # Fallback to environment variables
        if not db_configs_str:
            db_configs_str = os.getenv("DB_CONFIGS", "")
        if not db_type:
            db_type = os.getenv("DB_TYPE", "")
        if not db_config_str:
            db_config_str = os.getenv("DB_CONFIG", "")
    
    # If we have multiple database configs
    if db_configs_str:
        try:
            db_configs_list = json.loads(db_configs_str) if isinstance(db_configs_str, str) else db_configs_str
            if not isinstance(db_configs_list, list) or len(db_configs_list) == 0:
                raise ValueError("DB_CONFIGS must be a non-empty JSON array")
            
            db_configs = {}
            for i, config in enumerate(db_configs_list):
                if not isinstance(config, dict) or "db_type" not in config or "configuration" not in config or "description" not in config:
                    raise ValueError("Each DB_CONFIG must contain db_type, configuration, and description")
                
                # Generate a meaningful ID if not provided
                db_id = config.get("id", "")
                if not db_id:
                    # Create an ID based on database type and description
                    db_type_abbr = config["db_type"][:2].lower()
                    desc_part = ''.join(c for c in config["description"] if c.isalnum())[:8].lower()
                    db_id = f"{db_type_abbr}_{desc_part}_{i}"
                
                db_config = DbConfig(
                    db_type=config["db_type"],
                    configuration=config["configuration"],
                    description=config["description"],
                    id=db_id
                )
                
                # print(f"Initializing query runner for {db_config.db_type} database: {db_config.description}")
                db_config.query_runner = QueryRunner(db_type=db_config.db_type, configuration=db_config.configuration)
                db_configs[db_id] = db_config
                
            print(f"Initialized {len(db_configs)} database connections")
            return db_configs
        except json.JSONDecodeError as e:
            print(f"Error parsing DB_CONFIGS: {str(e)}")
            raise
    
    # Fallback to single database configuration
    # Only parse args if we're not in MCP CLI mode
    if not db_type:
        db_type = os.getenv("DB_TYPE", "pg")
    if not db_config_str:
        db_config_str = os.getenv("DB_CONFIG", "")
    
    try:
        db_config = json.loads(db_config_str) if isinstance(db_config_str, str) else db_config_str
        if isinstance(db_config, str):
            db_config = json.loads(db_config)  # Handle double-string JSON
    except json.JSONDecodeError as e:
        print(f"Error parsing DB_CONFIG: {str(e)}")
        raise

    # Allowing for empty configuration for now, this will render this MCP server useless
    # but it will not crash
    if not db_type or not db_config:
        print("Database type and configuration are required...")
        return {}

    # print(f"Initializing single query runner for {db_type} database")
    
    # Generate a meaningful ID for the single database
    db_id = f"{db_type.lower()}_default"
    
    db_config_obj = DbConfig(
        db_type=db_type,
        configuration=db_config,
        description="Default database connection",
        id=db_id
    )
    db_config_obj.query_runner = QueryRunner(db_type=db_type, configuration=db_config)
    
    db_configs = {db_id: db_config_obj}
    return db_configs

# Initialize query_runners as a dictionary
config_map: Dict[str, DbConfig] = {} 

# Initialize only if not being imported by test
_is_test = 'pytest' in sys.modules
if not _is_test:
    try:
        config_map = init_config()
    except Exception as e:
        print(f"Error initializing query runners: {str(e)}")
        print("\nUsage:")
        print("1. For MCP CLI mode with single database:")
        print("   Set environment variables: DB_TYPE, DB_CONFIG")
        print("   Or for multiple databases: DB_CONFIGS='[{\"db_type\":\"pg\",\"configuration\":{...},\"description\":\"My PostgreSQL DB\"}]'")
        print("   Then run: mcp install mcp_server.py")
        print("   Or: mcp dev mcp_server.py")
        print("\n2. For direct execution with single database:")
        print("   python mcp_server.py --db-type <db_type> --db-config '<json_config>'")
        print("   Example: python mcp_server.py --db-type mysql --db-config '{\"host\":\"localhost\",\"port\":3306,\"user\":\"root\",\"password\":\"pass\",\"database\":\"test\"}'")
        print("\n3. For direct execution with single database via ssh tunneling:")
        print("   python mcp_server.py --db-type <db_type> --db-config '[{\"host\":\"localhost\",\"port\":5432,\"user\":\"user\",\"passwd\":\"pw\",\"db\":\"dbname\",\"ssh_tunnel_enabled\":true,\"ssh_host\":\"ssh.example.com\",\"ssh_port\":22,\"ssh_username\":\"ssh_user\"}]'")
        print("\n4. For direct execution with multiple databases:")
        print("   python mcp_server.py --db-configs '[{\"db_type\":\"pg\",\"configuration\":{\"host\":\"localhost\"},\"description\":\"My PostgreSQL DB\"}]'")
        sys.exit(1)

    # Fetch schema information for all databases
    for db_config in config_map.values():
        try:
            db_config.schema = db_config.query_runner.get_schema()
        except Exception as e:
            print(f"Warning: Could not fetch schema for {db_config.description}: {str(e)}")


# Define database context that will be available to all handlers
@dataclass
class DbContext:
    db_configs: Dict[str, DbConfig]
    last_query: Optional[str] = None
    last_result: Optional[Dict[str, Any]] = None
    query_history: List[str] = None
    
    def __post_init__(self):
        if self.query_history is None:
            self.query_history = []
    
    def get_default_query_runner(self) -> QueryRunner:
        """Gets the default query runner (first one if multiple exist)"""
        if not self.db_configs:
            raise ValueError("No database connections available")
        # Get the first database in the dictionary
        first_db_id = next(iter(self.db_configs))
        return self.db_configs[first_db_id].query_runner

# Server lifespan manager
@asynccontextmanager
async def db_lifespan(server: FastMCP) -> AsyncIterator[DbContext]:
    """Initialize database connections on startup and provide context to handlers"""
    
    # Initialize context
    db_context = DbContext(
        db_configs=config_map,
    )
    
    try:
        # Test connection on startup for all databases
        for db_config in db_context.db_configs.values():
            try:
                db_config.query_runner.test_connection()
                print(f"Successfully connected to {db_config.description}")
            except Exception as e:
                print(f"Warning: Connection test failed for {db_config.description}: {str(e)}")
        
        yield db_context
    finally:
        # Cleanup could happen here if needed
        pass

# Pass lifespan to server
mcp = FastMCP("Legion Multi-Database Access", lifespan=db_lifespan)

# Define resources
@mcp.resource("resource://schema/{database_id}")
def get_schema(database_id: Optional[str] = None) -> str:
    """Get the database schemas for all databases or a specific database
    
    Args:
        database_id: Optional database ID to get schema for. If None, get schemas for all databases.
    """
    try:
        schemas = []
        
        if database_id is not None and database_id != "all":
            # Get schema for specific database
            if database_id not in config_map:
                return f"Error: Invalid database ID {database_id}"
            
            db_config = config_map[database_id]
            try:
                schema = db_config.query_runner.get_schema()
                schemas.append({
                    "id": database_id,
                    "description": db_config.description,
                    "db_type": db_config.db_type,
                    "schema": schema
                })
            except Exception as e:
                schemas.append({
                    "id": database_id,
                    "description": db_config.description,
                    "db_type": db_config.db_type,
                    "error": str(e)
                })
        else:
            # Get schema for all databases
            for db_id, db_config in config_map.items():
                try:
                    schema = db_config.query_runner.get_schema()
                    schemas.append({
                        "id": db_id,
                        "description": db_config.description,
                        "db_type": db_config.db_type,
                        "schema": schema
                    })
                except Exception as e:
                    schemas.append({
                        "id": db_id,
                        "description": db_config.description,
                        "db_type": db_config.db_type,
                        "error": str(e)
                    })
        
        return json.dumps(schemas)
    except Exception as e:
        return f"Error getting schemas: {str(e)}"

@mcp.tool()
def get_query_history(ctx: Context) -> str:
    """Get the recent query history"""
    db_context = ctx.request_context.lifespan_context
    
    if not db_context.query_history:
        return "No query history available"
    
    result = "Query History:\n"
    for entry in db_context.query_history:
        if isinstance(entry, str):
            result += f"- {entry}\n"
        else:
            result += f"- {entry['query']} (Database: {entry['db_name']})\n"
    
    return result

@mcp.tool()
def list_databases(ctx: Context) -> str:
    """List all available database connections"""
    db_context: DbContext = ctx.request_context.lifespan_context
    
    if not db_context.db_configs:
        return "No database connections available."
    
    db_list = []
    for db_id, db_config in db_context.db_configs.items():
        db_info = f"ID: {db_id} - {db_config.description} (Type: {db_config.db_type})"
        
        # Add table count if schema is available
        if db_config.schema:
            table_count = len(db_config.schema)
            db_info += f" - {table_count} tables"
        
        db_list.append(db_info)
    
    return "Available databases:\n" + "\n".join(db_list)

@mcp.prompt()
def select_database() -> str:
    """Help user select which database to use"""
    return "I need to determine which database to use for your query. Please use the list_databases tool first, then tell me which database ID to use."

def get_database_schema_summary(db_config: DbConfig) -> str:
    """Create a summary of the database schema for display"""
    if db_config.schema is None:
        return "Schema information not available"
    
    tables = db_config.schema
    if not tables:
        return "No tables found in schema"
    
    table_summaries = []
    for table in tables[:10]:  # Limit to first 10 tables
        table_name = table.get("name", "")
        if not table_name:
            continue
        
        columns = table.get("columns", [])
        column_names = [col.get("name", "") for col in columns[:5]]  # Limit to first 5 columns
        column_str = ", ".join(column_names)
        if len(columns) > 5:
            column_str += ", ..."
        
        table_summaries.append(f"- {table_name} ({column_str})")
    
    if len(tables) > 10:
        table_summaries.append(f"... and {len(tables) - 10} more tables")
    
    return "\n".join(table_summaries) if table_summaries else "No tables found in schema"

@mcp.tool()
def get_database_info(ctx: Context, db_id: Optional[str] = None) -> str:
    """Get detailed information about a database including schema summary"""
    db_context: DbContext = ctx.request_context.lifespan_context
    
    if db_id is None:
        # Return info for all databases
        all_info = []
        for curr_db_id, db_config in db_context.db_configs.items():
            info = f"Database ID: {curr_db_id}\n"
            info += f"Description: {db_config.description}\n"
            info += f"Type: {db_config.db_type}\n"
            info += f"Schema Summary:\n{get_database_schema_summary(db_config)}"
            all_info.append(info)
        
        return "\n\n".join(all_info)
    
    # Return info for specific database
    if db_id not in db_context.db_configs:
        return f"Invalid database ID: {db_id}"
    
    db_config = db_context.db_configs[db_id]
    info = f"Database ID: {db_id}\n"
    info += f"Description: {db_config.description}\n"
    info += f"Type: {db_config.db_type}\n"
    info += f"Schema Summary:\n{get_database_schema_summary(db_config)}"
    
    return info

def _execute_and_get_results(query: str, ctx: Context, db_id: str) -> Dict[str, Any]:
    """Helper function to execute query and get formatted results"""
    db_context = ctx.request_context.lifespan_context
    
    if db_id not in db_context.db_configs:
        raise ValueError(f"Invalid database ID: {db_id}")
    
    # Get the selected query runner
    db_config = db_context.db_configs[db_id]
    query_runner = db_config.query_runner
    
    # Execute query
    result = query_runner.run_query(query)
    
    # Update query history in the context
    db_context.last_query = query
    db_context.last_result = result
    db_context.query_history.append(f"[{db_id}] [{db_config.description}] {query}")
    
    # Extract column info
    columns = result.get('columns', [])
    column_names = [col.get('friendly_name', col.get('name', '')) for col in columns]
    
    # Extract row data
    rows = result.get('rows', [])
    row_count = len(rows)
    
    # Process rows - each row is a dictionary with column names as keys
    processed_rows = []
    for row_dict in rows:
        # Create a row with values in the same order as column_names
        processed_row = [row_dict.get(col.get('name', '')) for col in columns]
        processed_rows.append(processed_row)
    
    return {
        'column_names': column_names,
        'columns': columns,
        'rows': processed_rows,
        'raw_rows': rows,
        'row_count': row_count,
        'database': {
            'id': db_id,
            'description': db_config.description,
            'db_type': db_config.db_type
        }
    }

# Define tools
@mcp.tool()
def execute_query(query: str, ctx: Context, db_id: str) -> str:
    """Execute a SQL query and return results as a markdown table"""
    try:
        result = _execute_and_get_results(query, ctx, db_id)
        
        # Add database info to the output
        db_info = f"Database: {result['database']['description']} (Type: {result['database']['db_type']})"
        
        # Build a markdown table for output
        header = " | ".join(result['column_names'])
        separator = " | ".join(["---"] * len(result['column_names']))
        
        table_rows = []
        for row in result['rows'][:10]:  # Limit to first 10 rows for display
            table_rows.append(" | ".join(str(cell) for cell in row))
        
        result_table = f"Query executed on Database: {result['database']['description']}\n\n"
        result_table += f"{header}\n{separator}\n" + "\n".join(table_rows)
        
        if result['row_count'] > 10:
            result_table += f"\n\n... and {result['row_count'] - 10} more rows (total: {result['row_count']})"
            
        return f"{db_info}\n\n{result_table}"
    except ValueError as e:
        if "Invalid database ID" in str(e):
            return f"Error: {str(e)}"
        return f"Error executing query: {str(e)}"
    except Exception as e:
        return f"Error executing query: {str(e)}"

@mcp.tool()
def execute_query_json(query: str, ctx: Context, db_id: str) -> str:
    """Execute a SQL query and return results as JSON"""
    try:
        result = _execute_and_get_results(query, ctx, db_id)
        
        # Create a more compact representation for JSON output
        output = {
            'database': result['database'],
            'columns': result['column_names'],
            'rows': result['raw_rows'],  # Return the original row dictionaries for JSON output
            'row_count': result['row_count']
        }
        return json.dumps(output, indent=2)
    except Exception as e:
        return f"Error executing query: {str(e)}"

@mcp.tool()
def get_table_columns(table_name: str, ctx: Context, db_id: str) -> str:
    """Get column names for a specific table"""
    try:
        db_context: DbContext = ctx.request_context.lifespan_context
        
        if db_id not in db_context.db_configs:
            raise ValueError(f"Invalid database ID: {db_id}")
        
        db_config = db_context.db_configs[db_id]
        columns = db_config.query_runner.get_table_columns(table_name)
        
        return json.dumps({
            'database': {
                'id': db_id,
                'description': db_config.description,
                'db_type': db_config.db_type
            },
            'table': table_name,
            'columns': columns
        })
    except Exception as e:
        return f"Error getting columns for table {table_name}: {str(e)}"

@mcp.tool()
def get_table_types(table_name: str, ctx: Context, db_id: str) -> str:
    """Get column types for a specific table"""
    try:
        db_context: DbContext = ctx.request_context.lifespan_context
        
        if db_id not in db_context.db_configs:
            raise ValueError(f"Invalid database ID: {db_id}")
        
        db_config = db_context.db_configs[db_id]
        types = db_config.query_runner.get_table_types(table_name)
        
        return json.dumps({
            'database': {
                'id': db_id,
                'description': db_config.description,
                'db_type': db_config.db_type
            },
            'table': table_name,
            'types': types
        })
    except Exception as e:
        return f"Error getting types for table {table_name}: {str(e)}"

@mcp.tool()
def describe_table(ctx: Context, table_name: str, db_id: str) -> str:
    """Get detailed description of a table including column names and types"""
    try:
        db_context: DbContext = ctx.request_context.lifespan_context
        
        if db_id not in db_context.db_configs:
            return f"Error: Invalid database ID {db_id}"
        
        db_config = db_context.db_configs[db_id]
        
        # Get column names and types
        columns = db_config.query_runner.get_table_columns(table_name)
        types = db_config.query_runner.get_table_types(table_name)
        
        # Build description
        description = f"Table: {table_name} in Database: {db_config.description} (ID: {db_id})\n\n"
        description += "Columns:\n"
        
        for column in columns:
            column_type = types.get(column, "unknown")
            description += f"- {column} ({column_type})\n"
        
        return description
    except Exception as e:
        return f"Error describing table {table_name}: {str(e)}"

@mcp.tool()
def get_table_sample(ctx: Context, table_name: str, db_id: str, limit: int = 10) -> str:
    """Get a sample of data from a table"""
    try:
        db_context: DbContext = ctx.request_context.lifespan_context
        
        if db_id not in db_context.db_configs:
            return f"Error: Invalid database ID {db_id}"
        
        db_config = db_context.db_configs[db_id]
        query_runner = db_config.query_runner
        
        # Construct a safe query to sample data
        query = f"SELECT * FROM {table_name} LIMIT {min(limit, 100)}"
        result = query_runner.run_query(query)
        
        # Extract column info
        columns = result.get('columns', [])
        column_names = []
        for col in columns:
            if isinstance(col, dict):
                column_names.append(col.get('friendly_name', col.get('name', '')))
            else:
                column_names.append(col)
        
        # Format as markdown table
        header = " | ".join(column_names)
        separator = " | ".join(["---"] * len(column_names))
        
        # Extract row data
        rows = result.get('rows', [])
        
        table_rows = []
        for row in rows:
            if isinstance(row, dict):
                # Handle dict rows
                row_values = [str(row.get(col, '')) for col in column_names]
            else:
                # Handle list rows
                row_values = [str(cell) for cell in row]
            table_rows.append(" | ".join(row_values))
        
        sample_data = f"Sample data from table '{table_name}' in Database: {db_config.description} (ID: {db_id})\n\n"
        sample_data += f"{header}\n{separator}\n" + "\n".join(table_rows)
        
        if not rows:
            sample_data += "\n\nNo data found in table."
        
        return sample_data
    except Exception as e:
        return f"Error getting sample data from table {table_name}: {str(e)}"

@mcp.tool()
def find_table(table_name: str, ctx: Context) -> str:
    """Find which database contains a specific table"""
    db_context: DbContext = ctx.request_context.lifespan_context
    found_in = []
    
    for db_id, db_config in db_context.db_configs.items():
        if not db_config.schema:
            continue
        
        for table in db_config.schema:
            if table.get("name") == table_name:
                found_in.append({
                    "db_id": db_id,
                    "db_name": db_config.description,
                    "db_type": db_config.db_type
                })
                break
    
    if not found_in:
        return f"Table '{table_name}' was not found in any database schema."
    
    result = f"Table '{table_name}' was found in the following databases:\n"
    for db in found_in:
        result += f"- Database ID: {db['db_id']} - {db['db_name']} (Type: {db['db_type']})\n"
    
    return result

# Define prompts
@mcp.prompt()
def sql_query() -> str:
    """Create an SQL query against the database"""
    return "Please help me write a SQL query for the following question:\n\n"

@mcp.prompt()
def explain_query(query: str) -> str:
    """Explain what a SQL query does"""
    return f"Can you explain what the following SQL query does?\n\n```sql\n{query}\n```"

@mcp.prompt()
def optimize_query(query: str) -> str:
    """Optimize a SQL query for better performance"""
    return f"Can you optimize the following SQL query for better performance?\n\n```sql\n{query}\n```"

def main():
    # print(f"Starting Legion Multi-Database MCP server with {len(query_runners)} database connections...")
    mcp.run()

if __name__ == "__main__":
    main() 