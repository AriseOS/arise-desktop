"""
Storage Agent - Persistent data storage using LLM-generated SQL
"""
import json
import hashlib
import logging
import aiosqlite
from typing import Any, Dict, Optional, List, Tuple
from datetime import datetime
from pathlib import Path

try:
    from .base_agent import BaseStepAgent, AgentMetadata
    from ..core.schemas import AgentContext, AgentInput, AgentOutput
except ImportError:
    from base_agent.agents.base_agent import BaseStepAgent, AgentMetadata
    from base_agent.core.schemas import AgentContext, AgentInput, AgentOutput


logger = logging.getLogger(__name__)


class StorageAgent(BaseStepAgent):
    """
    Storage Agent for persistent data storage using LLM-generated SQL

    Supports three operations:
    - store: Insert data into collection
    - query: Query data with filters
    - export: Export data to CSV/Excel/JSON

    Uses LLM to generate SQL scripts and caches them in Memory KV Storage.
    """

    SYSTEM_PROMPT_SCHEMA = """You are a SQLite schema expert. Generate CREATE TABLE statement based on data structure.

Rules:
1. Table name: {table_name}
2. Always include: id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL
3. Infer optimal SQLite types from data (INTEGER, REAL, TEXT)
4. **IMPORTANT**: Use the EXACT field names from the data dictionary keys - DO NOT expand or flatten nested structures
5. **IMPORTANT**: If a field value is a list or dict (nested structure), create it as TEXT type to store JSON
6. Return ONLY the CREATE TABLE SQL, no explanations
7. Use IF NOT EXISTS clause

Example 1 (simple flat data):
Input data: {{"name": "Product A", "price": 10.99, "rating": 5}}
CREATE TABLE IF NOT EXISTS products_alice (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    price REAL NOT NULL,
    rating INTEGER,
    created_at TEXT NOT NULL
)

Example 2 (nested data - DO NOT FLATTEN):
Input data: {{"product": [{{"name": "X", "price": 10}}], "team": [{{"name": "Y"}}]}}
CREATE TABLE IF NOT EXISTS products_alice (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product TEXT NOT NULL,
    team TEXT NOT NULL,
    created_at TEXT NOT NULL
)"""

    SYSTEM_PROMPT_INSERT = """You are a SQL expert. Generate INSERT statement for the table.

Rules:
1. Table name: {table_name}
2. Fields: {fields}
3. Always include created_at as the last field
4. Return ONLY the INSERT SQL with placeholders (?), no explanations

Example output:
INSERT INTO products_alice (name, price, rating, created_at) VALUES (?, ?, ?, ?)"""

    SYSTEM_PROMPT_QUERY = """You are a SQL query expert. Generate SELECT statement based on requirements.

Rules:
1. Table name: {table_name}
2. Return ONLY the SELECT SQL with placeholders (?), no explanations
3. Use parameterized queries for security
4. Return parameter order as comment at end (# params: field1, field2, ...)

Example output:
SELECT * FROM products_alice WHERE price < ? AND rating > ? LIMIT ?
# params: price, rating, limit"""

    def __init__(self):
        metadata = AgentMetadata(
            name="storage_agent",
            description="Persistent data storage agent with store/query/export operations"
        )
        super().__init__(metadata)
        self.provider = None
        self.db_path = None
        self.config_service = None
        self.logger = logging.getLogger(__name__)

    async def initialize(self, context: AgentContext) -> bool:
        """Initialize Storage Agent"""
        if not context.agent_instance:
            return False

        # Get provider
        if not hasattr(context.agent_instance, 'provider') or not context.agent_instance.provider:
            if context.logger:
                context.logger.error("Provider not available")
            return False

        self.provider = context.agent_instance.provider

        # Get config service
        if hasattr(context.agent_instance, 'config_service'):
            self.config_service = context.agent_instance.config_service
        else:
            if context.logger:
                context.logger.error("ConfigService not available")
            return False

        # Get database path
        try:
            self.db_path = self.config_service.get_path("data.databases.storage")
            # Ensure parent directory exists
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Storage database path: {self.db_path}")
        except Exception as e:
            if context.logger:
                context.logger.error(f"Failed to get database path: {e}")
            return False

        self.is_initialized = True
        return True

    async def validate_input(self, input_data: Any) -> bool:
        """Validate input data"""
        from ..core.schemas import AgentInput

        # Handle AgentInput wrapper (from workflow engine)
        if isinstance(input_data, AgentInput):
            input_data = input_data.data

        if not isinstance(input_data, dict):
            logger.error(f"❌ Input validation failed: input_data is not a dict, got {type(input_data)}")
            return False

        operation = input_data.get('operation')
        if operation not in ['store', 'query', 'export']:
            logger.error(f"❌ Input validation failed: invalid operation '{operation}', must be 'store', 'query', or 'export'")
            return False

        collection = input_data.get('collection')
        if not collection or not isinstance(collection, str):
            logger.error(f"❌ Input validation failed: collection is missing or not a string, got {collection}")
            return False

        if operation == 'store':
            data = input_data.get('data')
            if not data:
                logger.error(f"❌ Input validation failed: 'data' field is missing or empty for store operation")
                logger.error(f"   Input keys: {list(input_data.keys())}")
                return False
            if isinstance(data, list):
                if len(data) == 0:
                    logger.error(f"❌ Input validation failed: data list is empty (no items to store)")
                    return False
                if not all(isinstance(item, dict) for item in data):
                    logger.error(f"❌ Input validation failed: data list contains non-dict items")
                    return False
                return True
            if isinstance(data, dict):
                return True
            logger.error(f"❌ Input validation failed: data must be dict or list of dicts, got {type(data)}")
            return False

        elif operation == 'query':
            return True  # filters, limit, order_by are optional

        elif operation == 'export':
            format_type = input_data.get('format')
            output_path = input_data.get('output_path')
            if format_type not in ['csv', 'excel', 'json']:
                logger.error(f"❌ Input validation failed: invalid format '{format_type}', must be 'csv', 'excel', or 'json'")
                return False
            if not isinstance(output_path, str):
                logger.error(f"❌ Input validation failed: output_path must be a string, got {type(output_path)}")
                return False
            return True

        return False

    async def execute(self, input_data: AgentInput, context: AgentContext) -> AgentOutput:
        """Execute storage operation"""
        from ..core.schemas import AgentInput as AgentInputSchema

        try:
            # Handle AgentInput wrapper (from workflow engine)
            if isinstance(input_data, AgentInputSchema):
                input_dict = input_data.data
            else:
                input_dict = input_data

            operation = input_dict.get('operation')

            if operation == 'store':
                result = await self._store(input_dict, context)
            elif operation == 'query':
                result = await self._query(input_dict, context)
            elif operation == 'export':
                result = await self._export(input_dict, context)
            else:
                raise ValueError(f"Unsupported operation: {operation}")

            return AgentOutput(
                success=True,
                data=result,
                message=result.get('message', 'Operation completed')
            )

        except Exception as e:
            self.logger.error(f"Storage operation failed: {e}", exc_info=True)
            return AgentOutput(
                success=False,
                message=f"Storage operation failed: {e}",
                data={"error": str(e)}
            )

    async def _store(self, input_data: Dict, context: AgentContext) -> Dict:
        """Store data to collection"""
        collection = input_data.get('collection')
        data = input_data.get('data')
        # Get user_id from MemoryManager (single source of truth)
        user_id = context.memory_manager.user_id if context.memory_manager else 'default_user'

        # Handle list of data
        if isinstance(data, list):
            count = 0
            for item in data:
                await self._store_single(collection, item, user_id, context)
                count += 1

            # Send user-friendly log output via WebSocket
            if context.logger:
                context.logger.info(f"✅ Successfully stored {count} records to collection '{collection}'")

            return {
                "message": f"Stored {count} records to collection '{collection}'",
                "collection": collection,
                "rows_stored": count
            }
        else:
            # Single data
            await self._store_single(collection, data, user_id, context)

            # Send user-friendly log output via WebSocket
            if context.logger:
                context.logger.info(f"✅ Successfully stored 1 record to collection '{collection}'")

            return {
                "message": f"Stored 1 record to collection '{collection}'",
                "collection": collection,
                "rows_stored": 1
            }

    async def _store_single(
        self,
        collection: str,
        data: dict,
        user_id: str,
        context: AgentContext
    ):
        """Store single data record"""
        table_name = f"{collection}_{user_id}"

        # Log table and data info for debugging
        self.logger.info(f"Storing to table: {table_name}, data fields: {list(data.keys())}")

        # Generate cache key with user_id for easy deletion
        cache_key = f"storage_insert_{collection}_{user_id}"

        # Try to load cached script
        cached = await context.memory_manager.get_data(cache_key)

        if not cached:
            self.logger.info(f"First time storing to {table_name}, generating SQL scripts...")

            # Check if table already exists
            check_table_sql = f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'"
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(check_table_sql) as cursor:
                    existing_table = await cursor.fetchone()
                    if existing_table:
                        self.logger.warning(f"Table {table_name} already exists but no cache found!")
                        # Get existing table schema
                        async with db.execute(f"PRAGMA table_info({table_name})") as cursor:
                            columns = await cursor.fetchall()
                            # Filter out system columns: id, created_at
                            existing_fields = [col[1] for col in columns if col[1] not in ('id', 'created_at')]
                            self.logger.warning(f"Existing table schema: {existing_fields}")
                            self.logger.warning(f"New data fields: {list(data.keys())}")

            # Use data.keys() directly as field order (no flattening)
            field_order = list(data.keys())
            self.logger.info(f"Field order: {field_order}")

            # Generate SQL scripts using LLM
            create_sql = await self._generate_create_table_sql(table_name, data)
            insert_sql = await self._generate_insert_sql(table_name, field_order, create_sql)

            self.logger.info(f"Generated CREATE TABLE SQL: {create_sql}")
            self.logger.info(f"Generated INSERT SQL: {insert_sql}")

            # Create table
            await self._execute_sql(create_sql)

            # Cache script
            await context.memory_manager.set_data(cache_key, {
                "table_name": table_name,
                "create_table_sql": create_sql,
                "insert_sql": insert_sql,
                "field_order": field_order
            })

            cached = await context.memory_manager.get_data(cache_key)
            self.logger.info(f"Cached INSERT script for {table_name}, schema fields: {cached['field_order']}")
        else:
            self.logger.info(f"Using cached schema for {table_name}, schema fields: {cached['field_order']}")

            # Verify table actually exists
            check_table_sql = f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'"
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(check_table_sql) as cursor:
                    existing_table = await cursor.fetchone()
                    if not existing_table:
                        self.logger.error(f"Cache exists but table {table_name} does not exist!")
                        self.logger.error(f"Cache key: {cache_key}")
                        self.logger.error(f"Cached schema: {cached['field_order']}")
                        raise Exception(f"Table {table_name} does not exist but cache was found. Cache may be stale.")
                    else:
                        # Verify schema matches
                        async with db.execute(f"PRAGMA table_info({table_name})") as cursor:
                            columns = await cursor.fetchall()
                            # Filter out system columns: id, created_at
                            existing_fields = [col[1] for col in columns if col[1] not in ('id', 'created_at')]
                            self.logger.info(f"Actual table schema: {existing_fields}")
                            if existing_fields != cached['field_order']:
                                self.logger.error(f"Schema mismatch detected!")
                                self.logger.error(f"Cached schema: {cached['field_order']}")
                                self.logger.error(f"Actual schema: {existing_fields}")
                                raise Exception(f"Table schema mismatch. Cached: {cached['field_order']}, Actual: {existing_fields}")

        # Validate data fields
        self._validate_fields(data, cached["field_order"])

        # Prepare values
        values = []
        for field in cached["field_order"]:
            value = data[field]
            # Handle None values - convert to empty string
            if value is None:
                value = ""
            # Convert complex types to JSON
            elif isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            values.append(value)

        # Add system field: created_at
        values.append(datetime.now().isoformat())

        # Execute INSERT
        await self._execute_sql(cached["insert_sql"], tuple(values))

    async def _query(self, input_data: Dict, context: AgentContext) -> Dict:
        """Query data from collection"""
        collection = input_data.get('collection')
        filters = input_data.get('filters', {})
        limit = input_data.get('limit')
        order_by = input_data.get('order_by')
        # Get user_id from MemoryManager (single source of truth)
        user_id = context.memory_manager.user_id if context.memory_manager else 'default_user'

        table_name = f"{collection}_{user_id}"

        # Generate cache key (include query config hash, no user_id - MemoryManager handles isolation)
        query_config = {
            "filters": filters,
            "order_by": order_by,
            "limit": limit
        }
        config_hash = self._hash_config(query_config)
        cache_key = f"storage_query_{collection}_{user_id}_{config_hash}"

        # Try to load cached script
        cached = await context.memory_manager.get_data(cache_key)

        if not cached:
            self.logger.info(f"First time querying {table_name} with this config, generating SQL...")

            # Generate query SQL using LLM
            query_sql, params_order = await self._generate_query_sql(
                table_name, filters, order_by, limit
            )

            # Cache script
            await context.memory_manager.set_data(cache_key, {
                "table_name": table_name,
                "query_sql": query_sql,
                "params_order": params_order
            })

            cached = await context.memory_manager.get_data(cache_key)
            self.logger.info(f"Cached QUERY script for {table_name}")

        # Prepare parameters
        params = self._prepare_query_params(
            cached["params_order"], filters, limit
        )

        # Execute query
        rows = await self._query_sql(cached["query_sql"], params)

        return {
            "message": f"Retrieved {len(rows)} records from collection '{collection}'",
            "operation": "query",
            "collection": collection,
            "total_count": len(rows),
            "data": rows
        }

    async def _export(self, input_data: Dict, context: AgentContext) -> Dict:
        """Export data to file"""
        collection = input_data.get('collection')
        format_type = input_data.get('format')
        output_path = input_data.get('output_path')
        filters = input_data.get('filters', {})
        # Get user_id from MemoryManager (single source of truth)
        user_id = context.memory_manager.user_id if context.memory_manager else 'default_user'

        table_name = f"{collection}_{user_id}"

        # Generate cache key (no user_id - MemoryManager handles isolation)
        export_config = {
            "filters": filters,
            "format": format_type
        }
        config_hash = self._hash_config(export_config)
        cache_key = f"storage_export_{collection}_{user_id}_{config_hash}"

        # Try to load cached script
        cached = await context.memory_manager.get_data(cache_key)

        if not cached:
            self.logger.info(f"First time exporting {table_name} with this config, generating SQL...")

            # Generate query SQL (same as query operation)
            query_sql, params_order = await self._generate_query_sql(
                table_name, filters, order_by=None, limit=None
            )

            # Cache script
            await context.memory_manager.set_data(cache_key, {
                "table_name": table_name,
                "query_sql": query_sql,
                "params_order": params_order,
                "format": format_type
            })

            cached = await context.memory_manager.get_data(cache_key)
            self.logger.info(f"Cached EXPORT script for {table_name}")

        # Prepare parameters
        params = self._prepare_query_params(
            cached["params_order"], filters, None
        )

        # Execute query
        rows = await self._query_sql(cached["query_sql"], params)

        # Export to file
        if format_type == "csv":
            self._export_to_csv(rows, output_path)
        elif format_type == "excel":
            self._export_to_excel(rows, output_path)
        elif format_type == "json":
            self._export_to_json(rows, output_path)

        return {
            "message": f"Exported {len(rows)} records to {output_path}",
            "operation": "export",
            "collection": collection,
            "format": format_type,
            "output_path": output_path,
            "rows_exported": len(rows)
        }

    async def _generate_create_table_sql(
        self,
        table_name: str,
        data: dict
    ) -> str:
        """Generate CREATE TABLE SQL using LLM"""
        # Build prompt
        system_prompt = self.SYSTEM_PROMPT_SCHEMA.format(table_name=table_name)

        data_desc = json.dumps(data, indent=2, ensure_ascii=False)
        user_prompt = f"""Generate CREATE TABLE statement for this data:

{data_desc}

Remember:
- Table name: {table_name}
- Include: id INTEGER PRIMARY KEY AUTOINCREMENT
- Include: created_at TEXT NOT NULL
- Infer types from data values"""

        # Call LLM
        response = await self.provider.generate_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt
        )

        # Extract SQL from response
        create_sql = self._extract_sql(response)
        self.logger.debug(f"Generated CREATE TABLE SQL: {create_sql}")
        return create_sql

    async def _generate_insert_sql(
        self,
        table_name: str,
        fields: List[str],
        create_table_sql: str = None
    ) -> str:
        """Generate INSERT SQL using LLM

        Args:
            table_name: Table name
            fields: Field names from data
            create_table_sql: CREATE TABLE SQL for reference (to ensure consistency)
        """
        # If CREATE TABLE SQL is provided, extract actual column names from it
        # This ensures INSERT SQL matches CREATE TABLE SQL exactly
        if create_table_sql:
            system_prompt = f"""You are a SQL expert. Generate INSERT statement that matches the CREATE TABLE schema.

Rules:
1. Table name: {table_name}
2. Extract column names from CREATE TABLE below (exclude id and created_at)
3. Add created_at as the last field
4. Return ONLY the INSERT SQL with placeholders (?), no explanations

CREATE TABLE SQL:
{create_table_sql}

Example output:
INSERT INTO products_alice (name, price, rating, created_at) VALUES (?, ?, ?, ?)"""

            user_prompt = f"""Generate INSERT statement for table: {table_name}

Use the column names from the CREATE TABLE above (exclude id, include created_at at the end).
Return INSERT SQL with placeholders (?)."""
        else:
            # Fallback: use fields directly
            system_prompt = self.SYSTEM_PROMPT_INSERT.format(
                table_name=table_name,
                fields=", ".join(fields)
            )

            user_prompt = f"""Generate INSERT statement for table: {table_name}

Fields to insert: {", ".join(fields)}
System fields: created_at

Return INSERT SQL with placeholders (?)."""

        # Call LLM
        response = await self.provider.generate_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt
        )

        # Extract SQL from response
        insert_sql = self._extract_sql(response)
        self.logger.debug(f"Generated INSERT SQL: {insert_sql}")
        return insert_sql

    async def _generate_query_sql(
        self,
        table_name: str,
        filters: dict,
        order_by: Optional[str],
        limit: Optional[int]
    ) -> Tuple[str, List[str]]:
        """Generate SELECT SQL using LLM"""
        # Build prompt
        system_prompt = self.SYSTEM_PROMPT_QUERY.format(table_name=table_name)

        user_prompt = f"""Generate SELECT query for table: {table_name}

Requirements:
- Filters: {json.dumps(filters, ensure_ascii=False)}
- Order by: {order_by or 'None'}
- Limit: {limit or 'None'}

Return:
1. SELECT SQL with placeholders (?)
2. Parameter order as comment

Example:
SELECT * FROM table WHERE price < ? AND rating > ? LIMIT ?
# params: price, rating, limit"""

        # Call LLM
        response = await self.provider.generate_response(
            system_prompt=system_prompt,
            user_prompt=user_prompt
        )

        # Extract SQL and params order
        query_sql = self._extract_sql(response)

        # Extract params order from comment
        params_order = []
        if "# params:" in response:
            params_line = response.split("# params:")[1].split("\n")[0]
            params_order = [p.strip() for p in params_line.split(",")]

        self.logger.debug(f"Generated QUERY SQL: {query_sql}")
        self.logger.debug(f"Params order: {params_order}")
        return query_sql, params_order

    def _extract_sql(self, llm_response: str) -> str:
        """Extract SQL from LLM response and remove comments"""
        # Remove markdown code blocks
        if "```sql" in llm_response:
            llm_response = llm_response.split("```sql")[1].split("```")[0]
        elif "```" in llm_response:
            llm_response = llm_response.split("```")[1].split("```")[0]

        # Remove comment lines (lines starting with # or --)
        lines = llm_response.strip().split('\n')
        sql_lines = []
        for line in lines:
            stripped = line.strip()
            # Skip comment lines
            if stripped.startswith('#') or stripped.startswith('--'):
                continue
            # Remove inline comments
            if '#' in line:
                line = line.split('#')[0]
            if '--' in line:
                line = line.split('--')[0]
            sql_lines.append(line)

        return ' '.join(sql_lines).strip()

    def _validate_fields(self, data: dict, field_order: list):
        """Validate data fields"""
        data_fields = set(data.keys())
        schema_fields = set(field_order)

        # Check missing fields
        missing = schema_fields - data_fields
        if missing:
            raise ValueError(f"Missing required fields: {missing}")

        # Check extra fields
        extra = data_fields - schema_fields
        if extra:
            raise ValueError(f"Extra fields not in schema: {extra}")

    def _prepare_query_params(
        self,
        params_order: List[str],
        filters: dict,
        limit: Optional[int]
    ) -> List[Any]:
        """Prepare parameters for query"""
        params = []

        for param in params_order:
            if param == "limit":
                params.append(limit)
            elif param in filters:
                filter_val = filters[param]
                if isinstance(filter_val, dict):
                    # Handle comparison operators
                    params.append(list(filter_val.values())[0])
                else:
                    params.append(filter_val)

        return params

    def _hash_config(self, config: dict) -> str:
        """Generate hash for config"""
        config_str = json.dumps(config, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()[:8]

    async def _execute_sql(self, sql: str, params: Optional[Tuple] = None):
        """Execute SQL statement"""
        self.logger.info(f"Executing SQL: {sql}")
        if params:
            self.logger.info(f"SQL params: {params}")

        async with aiosqlite.connect(self.db_path) as db:
            try:
                if params:
                    await db.execute(sql, params)
                else:
                    await db.execute(sql)
                await db.commit()
                self.logger.info("SQL execution successful")
            except Exception as e:
                self.logger.error(f"SQL execution failed: {e}")
                self.logger.error(f"Failed SQL: {sql}")
                if params:
                    self.logger.error(f"Failed params: {params}")
                raise

    async def _query_sql(self, sql: str, params: Optional[List] = None) -> List[Dict]:
        """Execute SELECT query"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if params:
                cursor = await db.execute(sql, params)
            else:
                cursor = await db.execute(sql)
            rows = await cursor.fetchall()
            # Convert to list of dicts
            return [dict(row) for row in rows]

    def _export_to_csv(self, rows: List[Dict], output_path: str):
        """Export to CSV"""
        import pandas as pd
        df = pd.DataFrame(rows)
        df.to_csv(output_path, index=False)

    def _export_to_excel(self, rows: List[Dict], output_path: str):
        """Export to Excel"""
        import pandas as pd
        df = pd.DataFrame(rows)
        df.to_excel(output_path, index=False, engine='openpyxl')

    def _export_to_json(self, rows: List[Dict], output_path: str):
        """Export to JSON"""
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(rows, f, indent=2, ensure_ascii=False)
