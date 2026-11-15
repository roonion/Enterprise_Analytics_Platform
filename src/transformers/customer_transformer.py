"""Customer data transformer with fuzzy matching for deduplication."""

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

from src.transformers.base_transformer import BaseTransformer
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class CustomerTransformer(BaseTransformer):
    """
    Transform and deduplicate customer data.
    
    Handles:
    - Fuzzy matching for duplicate detection
    - Name standardization
    - Email normalization
    - Phone number formatting
    - Address standardization
    - Segment normalization
    """
    
    def __init__(
        self,
        fuzzy_threshold: int = 85,
        deduplicate: bool = True,
        mask_pii: bool = False
    ):
        """
        Initialize the customer transformer.
        
        Args:
            fuzzy_threshold: Minimum score for fuzzy match (0-100)
            deduplicate: Whether to remove duplicates
            mask_pii: Whether to mask PII for dev environments
        """
        super().__init__(name="CustomerTransformer")
        self.fuzzy_threshold = fuzzy_threshold
        self.deduplicate = deduplicate
        self.mask_pii = mask_pii
    
    def transform(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """
        Transform customer data.
        
        Args:
            df: Input customer DataFrame
            
        Returns:
            Transformed DataFrame
        """
        df = df.copy()
        
        # Standardize column names
        df.columns = df.columns.str.lower().str.strip()
        
        # Normalize names
        df = self._normalize_names(df)
        
        # Normalize email
        df = self._normalize_email(df)
        
        # Normalize phone
        df = self._normalize_phone(df)
        
        # Normalize segment
        df = self._normalize_segment(df)
        
        # Normalize country
        df = self._normalize_country(df)
        
        # Normalize boolean fields
        df = self._normalize_booleans(df)
        
        # Handle duplicates
        if self.deduplicate:
            df = self._deduplicate_fuzzy(df)
        
        # Mask PII if requested
        if self.mask_pii:
            df = self._mask_pii_fields(df)
        
        return df
    
    def _normalize_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize first and last name fields."""
        name_columns = ['first_name', 'last_name', 'full_name']
        
        for col in name_columns:
            if col in df.columns:
                df[col] = (
                    df[col]
                    .fillna('')
                    .astype(str)
                    .str.strip()
                    .str.title()
                )
        
        # Create full_name if not exists
        if 'full_name' not in df.columns and all(c in df.columns for c in ['first_name', 'last_name']):
            df['full_name'] = df['first_name'] + ' ' + df['last_name']
        
        return df
    
    def _normalize_email(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize email addresses."""
        if 'email' not in df.columns:
            return df
        
        df['email'] = (
            df['email']
            .fillna('')
            .astype(str)
            .str.lower()
            .str.strip()
        )
        
        # Extract email domain
        df['email_domain'] = df['email'].str.extract(r'@([\w\.-]+)', expand=False)
        
        # Validate email format
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        df['email_valid'] = df['email'].str.match(email_pattern, na=False)
        
        return df
    
    def _normalize_phone(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize phone numbers to consistent format."""
        if 'phone' not in df.columns:
            return df
        
        # Remove all non-numeric characters
        df['phone_normalized'] = (
            df['phone']
            .fillna('')
            .astype(str)
            .str.replace(r'[^\d]', '', regex=True)
        )
        
        # Add country code if missing (assume US)
        df['phone_normalized'] = df['phone_normalized'].apply(
            lambda x: f"1{x}" if len(x) == 10 else x
        )
        
        # Format as standard phone number
        df['phone_formatted'] = df['phone_normalized'].apply(self._format_phone)
        
        return df
    
    def _format_phone(self, phone: str) -> Optional[str]:
        """Format phone number to standard format."""
        if not phone or len(phone) < 10:
            return None
        
        # US phone format: +1 (XXX) XXX-XXXX
        if len(phone) == 11 and phone.startswith('1'):
            return f"+1 ({phone[1:4]}) {phone[4:7]}-{phone[7:11]}"
        elif len(phone) == 10:
            return f"+1 ({phone[0:3]}) {phone[3:6]}-{phone[6:10]}"
        else:
            return phone
    
    def _normalize_segment(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize customer segment values."""
        if 'customer_segment' not in df.columns:
            return df
        
        segment_mapping = {
            'enterprise': 'Enterprise',
            'smb': 'SMB',
            'consumer': 'Consumer',
            'small business': 'SMB',
            'large': 'Enterprise',
            'individual': 'Consumer'
        }
        
        df['customer_segment'] = (
            df['customer_segment']
            .fillna('Unknown')
            .astype(str)
            .str.lower()
            .str.strip()
            .map(lambda x: segment_mapping.get(x, x.title()))
        )
        
        return df
    
    def _normalize_country(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize country codes."""
        if 'country' not in df.columns:
            return df
        
        country_mapping = {
            'us': 'US',
            'usa': 'US',
            'united states': 'US',
            'united states of america': 'US',
            'ca': 'CA',
            'canada': 'CA',
            'uk': 'GB',
            'gb': 'GB',
            'great britain': 'GB',
            'united kingdom': 'GB',
            'de': 'DE',
            'germany': 'DE',
            'fr': 'FR',
            'france': 'FR'
        }
        
        df['country'] = (
            df['country']
            .fillna('')
            .astype(str)
            .str.lower()
            .str.strip()
            .map(lambda x: country_mapping.get(x, x.upper()))
        )
        
        return df
    
    def _normalize_booleans(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize boolean fields."""
        bool_mapping = {
            'true': True, 'false': False,
            'yes': True, 'no': False,
            'y': True, 'n': False,
            '1': True, '0': False,
            1: True, 0: False,
            True: True, False: False
        }
        
        bool_columns = ['is_active']
        
        for col in bool_columns:
            if col in df.columns:
                df[col] = (
                    df[col]
                    .apply(lambda x: bool_mapping.get(
                        str(x).lower() if pd.notna(x) else None, 
                        None
                    ))
                )
        
        return df
    
    def _deduplicate_fuzzy(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Remove duplicates using fuzzy matching.
        
        Returns the best record from each group of duplicates.
        """
        if len(df) == 0:
            return df
        
        # Create matching key
        df['_match_key'] = df.apply(self._create_match_key, axis=1)
        
        # Find duplicate groups
        duplicate_groups = self._find_duplicate_groups(df)
        
        if not duplicate_groups:
            df = df.drop(columns=['_match_key'])
            return df
        
        # Mark duplicates
        df['_duplicate_group'] = None
        for group_id, indices in enumerate(duplicate_groups):
            for idx in indices:
                df.loc[idx, '_duplicate_group'] = group_id
        
        # Keep best record from each group
        records_to_drop = []
        for group_id, indices in enumerate(duplicate_groups):
            group_df = df.loc[indices]
            best_idx = self._select_best_record(group_df)
            records_to_drop.extend([idx for idx in indices if idx != best_idx])
        
        duplicates_removed = len(records_to_drop)
        df = df.drop(index=records_to_drop)
        df = df.drop(columns=['_match_key', '_duplicate_group'], errors='ignore')
        
        logger.info(
            "Fuzzy deduplication complete",
            duplicates_found=len(duplicate_groups),
            records_removed=duplicates_removed
        )
        
        self.metadata['duplicates_removed'] = duplicates_removed
        
        return df
    
    def _create_match_key(self, row: pd.Series) -> str:
        """Create a key for fuzzy matching."""
        parts = []
        
        if 'first_name' in row.index and pd.notna(row['first_name']):
            parts.append(str(row['first_name']).lower())
        if 'last_name' in row.index and pd.notna(row['last_name']):
            parts.append(str(row['last_name']).lower())
        if 'email' in row.index and pd.notna(row['email']):
            parts.append(str(row['email']).lower())
        
        return ' '.join(parts)
    
    def _find_duplicate_groups(self, df: pd.DataFrame) -> List[List[int]]:
        """Find groups of potential duplicates."""
        match_keys = df['_match_key'].tolist()
        indices = df.index.tolist()
        
        seen = set()
        duplicate_groups = []
        
        for i, key_i in enumerate(match_keys):
            if i in seen:
                continue
            
            group = [indices[i]]
            
            for j, key_j in enumerate(match_keys[i+1:], start=i+1):
                if j in seen:
                    continue
                
                score = fuzz.token_sort_ratio(key_i, key_j)
                if score >= self.fuzzy_threshold:
                    group.append(indices[j])
                    seen.add(j)
            
            if len(group) > 1:
                duplicate_groups.append(group)
                seen.add(i)
        
        return duplicate_groups
    
    def _select_best_record(self, group_df: pd.DataFrame) -> int:
        """Select the best record from a group of duplicates."""
        # Score each record based on completeness
        scores = group_df.apply(
            lambda row: row.notna().sum() + (1 if row.get('email_valid', False) else 0),
            axis=1
        )
        
        return scores.idxmax()
    
    def _mask_pii_fields(self, df: pd.DataFrame) -> pd.DataFrame:
        """Mask PII fields for development environments."""
        import hashlib
        
        pii_columns = ['first_name', 'last_name', 'email', 'phone', 'address']
        
        for col in pii_columns:
            if col in df.columns:
                df[col] = df[col].apply(
                    lambda x: hashlib.md5(str(x).encode()).hexdigest()[:12]
                    if pd.notna(x) else None
                )
        
        logger.info("PII fields masked", columns=pii_columns)
        
        return df

