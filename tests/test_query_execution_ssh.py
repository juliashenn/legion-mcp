import pytest
import json
import sys
from unittest.mock import patch, MagicMock
from legion_query_runner import QueryRunner
from mcp.server.fastmcp import FastMCP, Context

# Create mocks for the MCP modules
class MockContext:
    def __init__(self):
        self.request_context = MagicMock()
        self.request_context.lifespan_context = MagicMock()
        self.request_context.lifespan_context.db_configs = {}
        self.request_context.lifespan_context.query_history = []


class MockFastMCP:
    def __init__(self, *args, **kwargs):
        self.name = kwargs.get('name', 'Mock MCP')
        self.lifespan = kwargs.get('lifespan', None)
        self.resources = {}
        self.tools = {}
        self.prompts = {}
    
    def resource(self, path):
        def decorator(func):
            self.resources[path] = func
            return func
        return decorator
    
    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func
        return decorator
    
    def prompt(self):
        def decorator(func):
            self.prompts[func.__name__] = func
            return func
        return decorator
    
    def run(self):
        pass

# Patch modules before imports
with patch.dict('sys.modules', {
    'mcp.server.fastmcp': MagicMock(FastMCP=MockFastMCP, Context=MockContext),
    'legion_query_runner': MagicMock(QueryRunner=QueryRunner)
}):
    from database_mcp.mcp_server import (
        DbConfig,
        execute_query,
        describe_table,
        get_table_sample,
        get_query_history,
    )

@pytest.fixture
def db_config_class():
    """Create a DbConfig class for testing"""
    from dataclasses import dataclass
    from typing import Dict, Any, Optional, List
    
    @dataclass
    class DbConfig:
        id: str
        db_type: str
        configuration: Dict[str, Any]
        description: str
        schema: Optional[List[Dict[str, Any]]] = None
        query_runner: Optional[Any] = None
    
    return DbConfig


@pytest.fixture
def db_config(db_config_class):

    # Create mock DbConfigs
    db_config = db_config_class(
        id="mysql_db",
        db_type="mysql",
        configuration={"host": "mysql-legion-test","port": 3306,"user": "root","passwd":"pass","db":"legionTest",
                        "ssh_tunnel_enabled": True,"ssh_host": "localhost", "ssh_port": 2222,"ssh_username": "root"},
        description="mysql DB"
    )
    db_config.query_runner = QueryRunner("mysql", db_config.configuration)
    db_config.description = "Test DB"
    return db_config

@pytest.fixture
def ctx(db_config_class):
    """Create a mock context with lifespan_context for database tools"""
    ctx = MockContext()
    # Create mock DbConfigs
    db_config = db_config_class(
        id="mysql_db",
        db_type="mysql",
        configuration={"host": "mysql-legion-test","port": 3306,"user": "root","passwd":"pass","db":"legionTest",
                        "ssh_tunnel_enabled": True,"ssh_host": "localhost", "ssh_port": 2222,"ssh_username": "root"},
        description="mysql DB",
        # schema=schema
    )
    ctx.request_context.lifespan_context.db_configs = {0: db_config}
    ctx.request_context.lifespan_context.query_history = []
    return ctx

def test_execute_query(ctx: Context, db_config):
    """Test execute_query function"""
    ctx.request_context.lifespan_context.db_configs = {0: db_config}
    
    # Mock query
    query = "SELECT * FROM users"
    
    # Test with a valid database index
    result = execute_query(query=query, ctx=ctx, db_id=0)
    
    # Verify result
    # print(result)
    # assert False
    assert "Query executed on Database: Test DB" in result
    assert "id" in result
    assert "name" in result
    assert "email" in result
    assert "created_at" in result
    assert "John Doe" in result
    assert "john@example.com" in result
    assert "Jane Smith" in result
    assert "jane@example.com" in result
    
    # Verify query is added to history
    assert len(ctx.request_context.lifespan_context.query_history) == 1
    assert query in ctx.request_context.lifespan_context.query_history[0]
    

def test_describe_table(ctx: Context, db_config):
    """Test describe_table function"""
    ctx.request_context.lifespan_context.db_configs = {0: db_config}
    # Test with valid parameters
        
    result = describe_table(ctx, table_name="users", db_id=0)
    # result = db_config.query_runner.get_table_types("users")
    
    # print(result)
    # result = db_config.query_runner.get_table_columns("users")

    # Verify result
    print(result)
    assert "Table: users in Database: Test DB" in result
    assert "id (int)" in result
    assert "name (varchar)" in result
    assert "email (varchar)" in result
    assert "created_at (timestamp)" in result


def describe_table_query(ctx: Context, table_name: str, db_id: str) ->str:
    try:
        db_context = ctx.request_context.lifespan_context

        if db_id not in db_context.db_configs:
            return f"Error: Invalid database ID {db_id}"
        
        db_config = db_context.db_configs[db_id]

        custom_query = f"""
            SELECT 
                COLUMN_NAME,
                DATA_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS 
            WHERE TABLE_SCHEMA = 'legionTest' 
            AND TABLE_NAME = 'users'
            ORDER BY ORDINAL_POSITION;"""
        
        result = db_config.query_runner.run_query(custom_query)
        
        # Get column names and types
        columns = [row['COLUMN_NAME'] for row in result['rows']]
        types = {row['COLUMN_NAME']: row['DATA_TYPE'] for row in result["rows"]}

        # Build description
        description = f"Table: users in Database: {db_config.description} (ID: 0)\n\n"
        description += "Columns:\n"
        
        for column in columns:
            column_type = types.get(column, "unknown")
            description += f"- {column} ({column_type})\n"
        
        return description
    except Exception as e:
        return f"Error describing table {table_name} using query: {str(e)}"

def test_describe_table_query(ctx: Context, db_config):
    """Test describe_table function"""
    ctx.request_context.lifespan_context.db_configs = {0: db_config}
    # Test with valid parameters
        
    result = describe_table_query(ctx, table_name="users", db_id=0)
    
    # Verify result
    # print(result)
    # assert False
    assert "Table: users in Database: Test DB" in result
    assert "id (int)" in result
    assert "name (varchar)" in result
    assert "email (varchar)" in result
    assert "created_at (timestamp)" in result

def test_describe_table_invalid_index(ctx, db_config):
    """Test describe_table with invalid database index"""
    # Test with an invalid database index
    result = describe_table(ctx, table_name="users", db_id=1)
    
    # Verify error message
    assert "Error: Invalid database ID" in result

def test_get_table_sample(ctx, db_config):
    """Test get_table_sample function"""
    ctx.request_context.lifespan_context.db_configs = {0: db_config}
    
    # Test with valid parameters
    result = get_table_sample(ctx, table_name="users", db_id=0, limit=2)
    
    # Verify result contains sample data
    # print(result)
    # assert False
    assert "Sample data from table 'users' in Database: Test DB" in result
    assert "id" in result
    assert "name" in result
    assert "email" in result
    assert "created_at" in result
    assert "John Doe" in result
    assert "Jane Smith" in result