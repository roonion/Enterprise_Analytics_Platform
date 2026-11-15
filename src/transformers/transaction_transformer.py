"""Transaction data transformer with currency conversion."""

from datetime import datetime
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from src.transformers.base_transformer import BaseTransformer
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class TransactionTransformer(BaseTransformer):
    """
    Transform transaction data.
    
    Handles:
    - Currency conversion to base currency
    - Payment method standardization
    - Status normalization
    - Channel normalization
    - Late arrival handling
    - Amount validation
    """
    
    # Default exchange rates (to USD)
    DEFAULT_EXCHANGE_RATES = {
        'USD': 1.0,
        'EUR': 1.08,
        'GBP': 1.26,
        'CAD': 0.74,
        'AUD': 0.65,
        'JPY': 0.0067,
        'CHF': 1.12,
        'MXN': 0.058,
        'INR': 0.012,
        'CNY': 0.14
    }
    
    def __init__(
        self,
        base_currency: str = 'USD',
        exchange_rates: Optional[Dict[str, float]] = None,
        validate_amounts: bool = True,
        handle_late_arrivals: bool = True
    ):
        """
        Initialize the transaction transformer.
        
        Args:
            base_currency: Base currency for conversion
            exchange_rates: Custom exchange rates dict
            validate_amounts: Whether to validate transaction amounts
            handle_late_arrivals: Whether to handle late-arriving transactions
        """
        super().__init__(name="TransactionTransformer")
        self.base_currency = base_currency
        self.exchange_rates = exchange_rates or self.DEFAULT_EXCHANGE_RATES
        self.validate_amounts = validate_amounts
        self.handle_late_arrivals = handle_late_arrivals
    
    def transform(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """
        Transform transaction data.
        
        Args:
            df: Input transaction DataFrame
            
        Returns:
            Transformed DataFrame
        """
        df = df.copy()
        
        # Standardize column names
        df.columns = df.columns.str.lower().str.strip()
        
        # Normalize currency and convert amounts
        df = self._normalize_currency(df)
        df = self._convert_to_base_currency(df)
        
        # Normalize payment method
        df = self._normalize_payment_method(df)
        
        # Normalize status
        df = self._normalize_status(df)
        
        # Normalize channel
        df = self._normalize_channel(df)
        
        # Validate amounts
        if self.validate_amounts:
            df = self._validate_amounts(df)
        
        # Handle late arrivals
        if self.handle_late_arrivals:
            df = self._handle_late_arrivals(df)
        
        # Parse timestamps
        df = self._parse_timestamps(df)
        
        # Calculate derived metrics
        df = self._calculate_metrics(df)
        
        return df
    
    def _normalize_currency(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize currency codes."""
        if 'currency' not in df.columns:
            df['currency'] = self.base_currency
            return df
        
        currency_mapping = {
            'usd': 'USD', 'dollar': 'USD', 'dollars': 'USD', '$': 'USD',
            'eur': 'EUR', 'euro': 'EUR', 'euros': 'EUR', '€': 'EUR',
            'gbp': 'GBP', 'pound': 'GBP', 'pounds': 'GBP', '£': 'GBP',
            'cad': 'CAD', 'canadian': 'CAD',
            'aud': 'AUD', 'australian': 'AUD',
            'jpy': 'JPY', 'yen': 'JPY', '¥': 'JPY',
            'chf': 'CHF', 'franc': 'CHF',
            'mxn': 'MXN', 'peso': 'MXN'
        }
        
        df['currency'] = (
            df['currency']
            .fillna(self.base_currency)
            .astype(str)
            .str.lower()
            .str.strip()
            .map(lambda x: currency_mapping.get(x, x.upper()))
        )
        
        # Store original currency
        df['original_currency'] = df['currency']
        
        return df
    
    def _convert_to_base_currency(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert all amounts to base currency."""
        if 'currency' not in df.columns:
            return df
        
        amount_columns = ['unit_price', 'total_amount']
        
        for col in amount_columns:
            if col not in df.columns:
                continue
            
            # Store original amount
            df[f'{col}_original'] = df[col]
            
            # Convert to base currency
            df[col] = df.apply(
                lambda row: self._convert_amount(
                    row[col],
                    row.get('currency', self.base_currency)
                ),
                axis=1
            )
        
        # Update currency to base
        df['currency'] = self.base_currency
        
        # Store exchange rate used
        df['exchange_rate'] = df['original_currency'].map(
            lambda x: self.exchange_rates.get(x, 1.0)
        )
        
        logger.info(
            "Currency conversion complete",
            base_currency=self.base_currency,
            currencies_found=df['original_currency'].nunique()
        )
        
        return df
    
    def _convert_amount(self, amount: float, currency: str) -> float:
        """Convert amount from given currency to base currency."""
        if pd.isna(amount):
            return np.nan
        
        rate = self.exchange_rates.get(currency, 1.0)
        return round(float(amount) * rate, 2)
    
    def _normalize_payment_method(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize payment method values."""
        if 'payment_method' not in df.columns:
            return df
        
        payment_mapping = {
            'credit card': 'Credit Card',
            'credit_card': 'Credit Card',
            'creditcard': 'Credit Card',
            'cc': 'Credit Card',
            'debit card': 'Debit Card',
            'debit_card': 'Debit Card',
            'debitcard': 'Debit Card',
            'paypal': 'PayPal',
            'bank transfer': 'Bank Transfer',
            'bank_transfer': 'Bank Transfer',
            'wire': 'Bank Transfer',
            'apple pay': 'Apple Pay',
            'apple_pay': 'Apple Pay',
            'applepay': 'Apple Pay',
            'google pay': 'Google Pay',
            'google_pay': 'Google Pay',
            'googlepay': 'Google Pay'
        }
        
        df['payment_method'] = (
            df['payment_method']
            .fillna('Unknown')
            .astype(str)
            .str.lower()
            .str.strip()
            .map(lambda x: payment_mapping.get(x, x.title()))
        )
        
        return df
    
    def _normalize_status(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize transaction status values."""
        if 'status' not in df.columns:
            return df
        
        status_mapping = {
            'completed': 'Completed',
            'complete': 'Completed',
            'success': 'Completed',
            'successful': 'Completed',
            'pending': 'Pending',
            'processing': 'Pending',
            'in_progress': 'Pending',
            'refunded': 'Refunded',
            'refund': 'Refunded',
            'failed': 'Failed',
            'failure': 'Failed',
            'error': 'Failed',
            'cancelled': 'Cancelled',
            'canceled': 'Cancelled',
            'void': 'Cancelled'
        }
        
        df['status'] = (
            df['status']
            .fillna('Unknown')
            .astype(str)
            .str.lower()
            .str.strip()
            .map(lambda x: status_mapping.get(x, x.title()))
        )
        
        return df
    
    def _normalize_channel(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize sales channel values."""
        if 'channel' not in df.columns:
            return df
        
        channel_mapping = {
            'web': 'Web',
            'website': 'Web',
            'online': 'Web',
            'mobile': 'Mobile',
            'app': 'Mobile',
            'mobile_app': 'Mobile',
            'store': 'Store',
            'retail': 'Store',
            'in_store': 'Store',
            'in-store': 'Store',
            'phone': 'Phone',
            'call_center': 'Phone',
            'partner': 'Partner',
            'api': 'API'
        }
        
        df['channel'] = (
            df['channel']
            .fillna('Unknown')
            .astype(str)
            .str.lower()
            .str.strip()
            .map(lambda x: channel_mapping.get(x, x.title()))
        )
        
        return df
    
    def _validate_amounts(self, df: pd.DataFrame) -> pd.DataFrame:
        """Validate transaction amounts."""
        amount_columns = ['unit_price', 'total_amount']
        
        for col in amount_columns:
            if col not in df.columns:
                continue
            
            # Mark invalid amounts
            df[f'{col}_valid'] = (
                df[col].notna() &
                (df[col] >= 0) &
                (df[col] < 1_000_000)  # Reasonable upper bound
            )
            
            invalid_count = (~df[f'{col}_valid']).sum()
            if invalid_count > 0:
                logger.warning(
                    "Invalid amounts found",
                    column=col,
                    invalid_count=int(invalid_count)
                )
        
        # Validate quantity * unit_price = total_amount (approximately)
        if all(c in df.columns for c in ['quantity', 'unit_price', 'total_amount']):
            expected_total = df['quantity'] * df['unit_price']
            df['amount_mismatch'] = abs(df['total_amount'] - expected_total) > 0.01
            
            mismatch_count = df['amount_mismatch'].sum()
            if mismatch_count > 0:
                logger.warning(
                    "Amount mismatches found",
                    count=int(mismatch_count)
                )
        
        return df
    
    def _handle_late_arrivals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Handle late-arriving transactions."""
        if 'is_late_arrival' not in df.columns:
            return df
        
        late_arrivals = df['is_late_arrival'].sum()
        
        if late_arrivals > 0:
            # Use original_date for late arrivals if available
            if 'original_date' in df.columns:
                mask = df['is_late_arrival'] == True
                df.loc[mask, 'effective_date'] = df.loc[mask, 'original_date']
                df.loc[~mask, 'effective_date'] = df.loc[~mask, 'transaction_date']
            
            logger.info(
                "Late arrivals handled",
                count=int(late_arrivals),
                percentage=f"{(late_arrivals / len(df) * 100):.2f}%"
            )
            
            self.metadata['late_arrivals'] = int(late_arrivals)
        
        return df
    
    def _parse_timestamps(self, df: pd.DataFrame) -> pd.DataFrame:
        """Parse and normalize timestamp columns."""
        timestamp_columns = ['transaction_timestamp', 'transaction_date', 'processing_date']
        
        for col in timestamp_columns:
            if col not in df.columns:
                continue
            
            # Try parsing with multiple formats
            df[col] = pd.to_datetime(df[col], errors='coerce', utc=True)
        
        # Extract date parts for analysis
        if 'transaction_timestamp' in df.columns:
            df['transaction_hour'] = df['transaction_timestamp'].dt.hour
            df['transaction_day_of_week'] = df['transaction_timestamp'].dt.dayofweek
            df['transaction_month'] = df['transaction_timestamp'].dt.month
            df['transaction_year'] = df['transaction_timestamp'].dt.year
        
        return df
    
    def _calculate_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate derived metrics."""
        # Gross margin if cost is available
        if 'unit_price' in df.columns:
            # Average order value flag
            avg_transaction = df['total_amount'].mean() if 'total_amount' in df.columns else 0
            df['is_high_value'] = df.get('total_amount', 0) > (avg_transaction * 2)
        
        # Processing delay
        if 'transaction_timestamp' in df.columns and 'processing_date' in df.columns:
            df['processing_delay_days'] = (
                pd.to_datetime(df['processing_date']) - 
                df['transaction_timestamp']
            ).dt.days
        
        return df
    
    def update_exchange_rates(self, rates: Dict[str, float]) -> None:
        """
        Update exchange rates.
        
        Args:
            rates: Dictionary of currency code to exchange rate
        """
        self.exchange_rates.update(rates)
        logger.info("Exchange rates updated", currencies=list(rates.keys()))

