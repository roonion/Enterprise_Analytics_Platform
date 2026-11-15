"""JSON extractor for API responses and nested data structures."""

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import pandas as pd
import requests

from src.extractors.base_extractor import BaseExtractor
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class JSONExtractor(BaseExtractor):
    """
    Extract data from JSON files or API endpoints.
    
    Handles:
    - Nested JSON structures
    - JSON Lines format
    - API pagination
    - Rate limiting
    - Authentication
    """
    
    def __init__(
        self,
        source: Union[str, Path],
        is_api: bool = False,
        data_path: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        auth: Optional[tuple] = None,
        flatten_nested: bool = True,
        json_lines: bool = False
    ):
        """
        Initialize the JSON extractor.
        
        Args:
            source: File path or API URL
            is_api: Whether source is an API endpoint
            data_path: Dot-notation path to data array (e.g., 'response.data.items')
            headers: HTTP headers for API requests
            auth: Authentication tuple (username, password)
            flatten_nested: Whether to flatten nested objects
            json_lines: Whether file is in JSON Lines format
        """
        self.source = source
        self.is_api = is_api
        self.data_path = data_path
        self.headers = headers or {}
        self.auth = auth
        self.flatten_nested = flatten_nested
        self.json_lines = json_lines
        
        source_name = str(source) if not is_api else f"API:{source}"
        super().__init__(source_name=source_name)
    
    def validate_source(self) -> bool:
        """Validate the JSON source."""
        if self.is_api:
            try:
                response = requests.head(
                    self.source,
                    headers=self.headers,
                    auth=self.auth,
                    timeout=10
                )
                return response.status_code < 400
            except Exception as e:
                logger.error("API validation failed", url=self.source, error=str(e))
                return False
        else:
            path = Path(self.source)
            if not path.exists():
                logger.error("JSON file not found", path=str(path))
                return False
            return True
    
    def _get_nested_value(self, data: Dict, path: str) -> Any:
        """
        Get value from nested dictionary using dot notation.
        
        Args:
            data: Dictionary to search
            path: Dot-separated path (e.g., 'response.data.items')
            
        Returns:
            Value at the path
        """
        keys = path.split('.')
        current = data
        
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            elif isinstance(current, list) and key.isdigit():
                current = current[int(key)]
            else:
                return None
        
        return current
    
    def _flatten_dict(
        self,
        d: Dict,
        parent_key: str = '',
        sep: str = '_'
    ) -> Dict:
        """
        Flatten a nested dictionary.
        
        Args:
            d: Dictionary to flatten
            parent_key: Prefix for keys
            sep: Separator between nested keys
            
        Returns:
            Flattened dictionary
        """
        items = []
        for k, v in d.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            
            if isinstance(v, dict):
                items.extend(self._flatten_dict(v, new_key, sep).items())
            elif isinstance(v, list):
                # Handle lists of primitives
                if v and not isinstance(v[0], dict):
                    items.append((new_key, v))
                else:
                    # For list of dicts, create separate columns
                    for i, item in enumerate(v):
                        if isinstance(item, dict):
                            items.extend(
                                self._flatten_dict(item, f"{new_key}_{i}", sep).items()
                            )
            else:
                items.append((new_key, v))
        
        return dict(items)
    
    def _extract_from_file(self) -> pd.DataFrame:
        """Extract data from JSON file."""
        path = Path(self.source)
        
        if self.json_lines:
            # JSON Lines format
            records = []
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError as e:
                            logger.warning("Skipping malformed JSON line", error=str(e))
            data = records
        else:
            # Standard JSON
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        
        # Navigate to data path if specified
        if self.data_path and isinstance(data, dict):
            data = self._get_nested_value(data, self.data_path)
        
        # Ensure we have a list
        if isinstance(data, dict):
            data = [data]
        
        # Flatten nested structures if requested
        if self.flatten_nested and data:
            data = [self._flatten_dict(d) if isinstance(d, dict) else d for d in data]
        
        return pd.DataFrame(data)
    
    def _extract_from_api(
        self,
        paginate: bool = False,
        page_param: str = 'page',
        per_page_param: str = 'per_page',
        per_page: int = 100,
        max_pages: Optional[int] = None,
        next_page_path: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Extract data from API endpoint.
        
        Args:
            paginate: Whether to handle pagination
            page_param: Query parameter for page number
            per_page_param: Query parameter for items per page
            per_page: Number of items per page
            max_pages: Maximum pages to fetch
            next_page_path: JSON path to next page URL
            
        Returns:
            DataFrame with API data
        """
        all_records = []
        page = 1
        url = self.source
        
        while True:
            # Build request
            params = {}
            if paginate:
                params[page_param] = page
                params[per_page_param] = per_page
            
            response = requests.get(
                url,
                headers=self.headers,
                auth=self.auth,
                params=params,
                timeout=30
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Extract records from response
            if self.data_path:
                records = self._get_nested_value(data, self.data_path)
            else:
                records = data if isinstance(data, list) else [data]
            
            if not records:
                break
            
            # Flatten if needed
            if self.flatten_nested:
                records = [self._flatten_dict(r) if isinstance(r, dict) else r for r in records]
            
            all_records.extend(records)
            
            logger.debug("Fetched page", page=page, records=len(records))
            
            # Check pagination
            if not paginate:
                break
            
            if max_pages and page >= max_pages:
                break
            
            # Check for next page
            if next_page_path:
                next_url = self._get_nested_value(data, next_page_path)
                if not next_url:
                    break
                url = next_url
            elif len(records) < per_page:
                # No more records
                break
            
            page += 1
        
        return pd.DataFrame(all_records)
    
    def extract(
        self,
        paginate: bool = False,
        max_pages: Optional[int] = None,
        **kwargs
    ) -> pd.DataFrame:
        """
        Extract data from the JSON source.
        
        Args:
            paginate: Enable pagination for API sources
            max_pages: Maximum pages to fetch for API
            **kwargs: Additional arguments for API extraction
            
        Returns:
            DataFrame with extracted data
        """
        if self.is_api:
            df = self._extract_from_api(paginate=paginate, max_pages=max_pages, **kwargs)
        else:
            df = self._extract_from_file()
        
        logger.info(
            "JSON extraction complete",
            source=self.source_name,
            rows=len(df),
            columns=len(df.columns)
        )
        
        return df
    
    def extract_nested_to_multiple_tables(
        self,
        nested_fields: List[str],
        id_field: str
    ) -> Dict[str, pd.DataFrame]:
        """
        Extract nested arrays into separate related tables.
        
        Args:
            nested_fields: List of fields containing nested arrays
            id_field: Field to use as foreign key
            
        Returns:
            Dictionary mapping table names to DataFrames
        """
        # Extract main data without flattening
        old_flatten = self.flatten_nested
        self.flatten_nested = False
        
        if self.is_api:
            raw_data = self._extract_from_api()
        else:
            raw_data = self._extract_from_file()
        
        self.flatten_nested = old_flatten
        
        tables = {'main': pd.DataFrame()}
        
        # Process each record
        main_records = []
        nested_records = {field: [] for field in nested_fields}
        
        for _, row in raw_data.iterrows():
            record = row.to_dict()
            id_value = record.get(id_field)
            
            # Extract nested fields
            for field in nested_fields:
                if field in record and isinstance(record[field], list):
                    for item in record[field]:
                        if isinstance(item, dict):
                            item[f'{id_field}_fk'] = id_value
                            nested_records[field].append(item)
                    del record[field]
            
            # Flatten remaining nested dicts in main record
            if self.flatten_nested:
                record = self._flatten_dict(record)
            
            main_records.append(record)
        
        # Create DataFrames
        tables['main'] = pd.DataFrame(main_records)
        for field, records in nested_records.items():
            if records:
                tables[field] = pd.DataFrame(records)
        
        return tables

