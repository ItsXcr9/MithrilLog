"""
MithrilLog Analytics Core

SQL query execution engine for process mining and data analytics.
Integrates with ClickHouse for scalable time-series analytics.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

import httpx

logger = logging.getLogger("mithrillog.analytics.core")


@dataclass
class QueryResult:
    """Result of an analytics query."""
    columns: List[str]
    data: List[List[Any]]
    row_count: int
    execution_time_ms: float
    query: str
    error: Optional[str] = None
    
    @property
    def is_success(self) -> bool:
        return self.error is None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "columns": self.columns,
            "data": self.data,
            "row_count": self.row_count,
            "execution_time_ms": self.execution_time_ms,
            "query": self.query,
            "error": self.error,
        }
    
    def to_records(self) -> List[Dict[str, Any]]:
        """Convert to list of dictionaries (one per row)."""
        return [dict(zip(self.columns, row)) for row in self.data]


@dataclass
class DatasetSchema:
    """Schema information for a dataset/table."""
    name: str
    columns: List[Dict[str, str]]  # [{name, type, comment}]
    row_count: int
    size_bytes: int
    engine: str
    partition_key: Optional[str] = None
    sorting_key: Optional[str] = None


class AnalyticsCore:
    """
    Core analytics engine with ClickHouse integration.
    
    Features:
    - SQL query execution with parameterization
    - Schema discovery and introspection  
    - Query validation and safety checks
    - Dataset statistics and profiling
    """
    
    # SQL keywords that are not allowed in read-only queries
    DANGEROUS_KEYWORDS = {
        "DROP", "DELETE", "TRUNCATE", "ALTER", "CREATE", 
        "INSERT", "UPDATE", "GRANT", "REVOKE", "ATTACH", "DETACH"
    }
    
    def __init__(
        self,
        host: str = None,
        port: int = None,
        database: str = None,
        user: str = None,
        password: str = None,
    ):
        """Initialize ClickHouse connection from params or environment."""
        self.host = host or os.getenv("CLICKHOUSE_HOST", "localhost")
        self.port = port or int(os.getenv("CLICKHOUSE_PORT", "8123"))
        self.database = database or os.getenv("CLICKHOUSE_DB", "mithrillog")
        self.user = user or os.getenv("CLICKHOUSE_USER", "default")
        self.password = password or os.getenv("CLICKHOUSE_PASSWORD", "")
        
        self._client: Optional[httpx.AsyncClient] = None
        logger.info(f"AnalyticsCore initialized: {self.host}:{self.port}/{self.database}")
    
    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}/"
    
    async def get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0, connect=10.0),
                follow_redirects=True,
            )
        return self._client
    
    async def test_connection(self) -> tuple[bool, str]:
        """Test basic connectivity to ClickHouse."""
        try:
            client = await self.get_client()
            url = f"{self.base_url}?query=SELECT%201&user={self.user}&password={self.password}"
            response = await client.get(url)
            if response.status_code == 200 and response.text.strip() == "1":
                return True, "Connected"
            return False, f"Unexpected response: {response.status_code} - {response.text[:200]}"
        except Exception as e:
            return False, f"Connection error: {type(e).__name__}: {str(e)}"
    
    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    def validate_query(self, sql: str, allow_write: bool = False) -> Optional[str]:
        """
        Validate SQL query for safety.
        
        Returns error message if invalid, None if valid.
        """
        sql_upper = sql.upper().strip()
        
        if not allow_write:
            for keyword in self.DANGEROUS_KEYWORDS:
                # Match keyword as whole word
                if re.search(rf'\b{keyword}\b', sql_upper):
                    return f"Query contains disallowed keyword: {keyword}"
        
        # Basic syntax check - must start with SELECT or WITH for read queries
        if not allow_write:
            if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
                return "Read queries must start with SELECT or WITH"
        
        return None
    
    async def execute(
        self,
        sql: str,
        params: Optional[Dict[str, Any]] = None,
        allow_write: bool = False,
        format: str = "JSONCompact",
    ) -> QueryResult:
        """
        Execute a SQL query against ClickHouse.
        
        Args:
            sql: SQL query to execute
            params: Query parameters for parameterized queries
            allow_write: Allow INSERT/UPDATE/DELETE operations
            format: Output format (JSONCompact, JSONEachRow, CSV, etc.)
            
        Returns:
            QueryResult with data or error
        """
        start_time = datetime.now()
        
        # Validate query
        validation_error = self.validate_query(sql, allow_write)
        if validation_error:
            return QueryResult(
                columns=[],
                data=[],
                row_count=0,
                execution_time_ms=0,
                query=sql,
                error=validation_error,
            )
        
        # Apply parameters if provided
        query = sql
        if params:
            for key, value in params.items():
                if isinstance(value, str):
                    value = f"'{value}'"
                elif isinstance(value, datetime):
                    value = f"'{value.strftime('%Y-%m-%d %H:%M:%S')}'"
                elif value is None:
                    value = "NULL"
                query = query.replace(f":{key}", str(value))
        
        try:
            client = await self.get_client()
            
            request_params = {
                "database": self.database,
                "query": f"{query} FORMAT {format}",
            }
            if self.user:
                request_params["user"] = self.user
            if self.password:
                request_params["password"] = self.password
            
            response = await client.get(self.base_url, params=request_params)
            
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            
            if response.status_code != 200:
                return QueryResult(
                    columns=[],
                    data=[],
                    row_count=0,
                    execution_time_ms=execution_time,
                    query=query,
                    error=f"ClickHouse error: {response.text[:500]}",
                )
            
            # Parse JSON response
            if format == "JSONCompact":
                result = response.json()
                columns = [col["name"] for col in result.get("meta", [])]
                data = result.get("data", [])
            elif format == "JSONEachRow":
                import json
                lines = response.text.strip().split("\n")
                if lines and lines[0]:
                    first_row = json.loads(lines[0])
                    columns = list(first_row.keys())
                    data = [list(json.loads(line).values()) for line in lines if line]
                else:
                    columns = []
                    data = []
            else:
                # Return raw for other formats
                columns = ["result"]
                data = [[response.text]]
            
            return QueryResult(
                columns=columns,
                data=data,
                row_count=len(data),
                execution_time_ms=execution_time,
                query=query,
            )
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds() * 1000
            logger.exception("Query execution failed")
            return QueryResult(
                columns=[],
                data=[],
                row_count=0,
                execution_time_ms=execution_time,
                query=query,
                error=str(e),
            )
    
    async def discover_schemas(self) -> List[DatasetSchema]:
        """Discover all tables and their schemas in the database."""
        result = await self.execute("""
            SELECT 
                name,
                engine,
                total_rows,
                total_bytes,
                partition_key,
                sorting_key
            FROM system.tables
            WHERE database = currentDatabase()
            ORDER BY name
        """)
        
        if not result.is_success:
            logger.error(f"Schema discovery failed: {result.error}")
            return []
        
        schemas = []
        for row in result.data:
            name, engine, rows, bytes_, partition, sorting = row
            
            # Get column info
            col_result = await self.execute(f"""
                SELECT name, type, comment
                FROM system.columns
                WHERE database = currentDatabase() AND table = '{name}'
                ORDER BY position
            """)
            
            columns = []
            if col_result.is_success:
                columns = [
                    {"name": r[0], "type": r[1], "comment": r[2] or ""}
                    for r in col_result.data
                ]
            
            schemas.append(DatasetSchema(
                name=name,
                columns=columns,
                row_count=rows or 0,
                size_bytes=bytes_ or 0,
                engine=engine,
                partition_key=partition,
                sorting_key=sorting,
            ))
        
        return schemas
    
    async def get_table_stats(self, table: str) -> Dict[str, Any]:
        """Get statistics for a specific table."""
        result = await self.execute(f"""
            SELECT 
                count() as row_count,
                min(timestamp) as min_time,
                max(timestamp) as max_time,
                uniq(tenant_id) as tenant_count
            FROM {table}
        """)
        
        if result.is_success and result.data:
            row = result.data[0]
            return {
                "table": table,
                "row_count": row[0],
                "min_timestamp": row[1],
                "max_timestamp": row[2],
                "tenant_count": row[3],
            }
        
        return {"table": table, "error": result.error}
    
    async def profile_column(
        self, 
        table: str, 
        column: str, 
        limit: int = 100
    ) -> Dict[str, Any]:
        """Profile a column for data discovery."""
        # Get cardinality and sample values
        result = await self.execute(f"""
            SELECT 
                uniq({column}) as cardinality,
                count() as total,
                countIf({column} IS NULL) as null_count
            FROM {table}
        """)
        
        profile = {
            "column": column,
            "table": table,
        }
        
        if result.is_success and result.data:
            row = result.data[0]
            profile["cardinality"] = row[0]
            profile["total_count"] = row[1]
            profile["null_count"] = row[2]
            profile["null_percent"] = (row[2] / row[1] * 100) if row[1] > 0 else 0
        
        # Get top values
        top_result = await self.execute(f"""
            SELECT {column}, count() as cnt
            FROM {table}
            WHERE {column} IS NOT NULL
            GROUP BY {column}
            ORDER BY cnt DESC
            LIMIT {limit}
        """)
        
        if top_result.is_success:
            profile["top_values"] = [
                {"value": r[0], "count": r[1]}
                for r in top_result.data
            ]
        
        return profile
    
    async def health_check(self) -> Dict[str, Any]:
        """Check ClickHouse connectivity and health."""
        # First test raw connectivity
        connected, conn_msg = await self.test_connection()
        
        if not connected:
            return {
                "status": "unhealthy",
                "error": conn_msg,
                "host": self.host,
                "port": self.port,
                "database": self.database,
                "base_url": self.base_url,
            }
        
        try:
            result = await self.execute("SELECT 1 as health")
            
            if result.is_success:
                schemas = await self.discover_schemas()
                return {
                    "status": "healthy",
                    "database": self.database,
                    "host": self.host,
                    "port": self.port,
                    "table_count": len(schemas),
                    "latency_ms": result.execution_time_ms,
                }
            else:
                return {
                    "status": "unhealthy",
                    "error": result.error,
                    "host": self.host,
                    "port": self.port,
                }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "host": self.host,
                "port": self.port,
            }


# Singleton instance
_analytics_core: Optional[AnalyticsCore] = None


def get_analytics_core() -> AnalyticsCore:
    """Get or create the singleton AnalyticsCore instance."""
    global _analytics_core
    if _analytics_core is None:
        _analytics_core = AnalyticsCore()
    return _analytics_core


def set_analytics_core(core: AnalyticsCore) -> None:
    """Set the singleton AnalyticsCore instance."""
    global _analytics_core
    _analytics_core = core
