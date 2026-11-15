"""
Data generator for creating realistic sample data with intentional messiness.
Generates CSV exports, JSON API responses, and database dumps with various
data quality issues for testing ETL pipelines.
"""

import json
import os
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from faker import Faker

from src.utils.logging_config import get_logger

logger = get_logger(__name__)

# Initialize Faker with multiple locales for international data
fake = Faker(['en_US', 'en_GB', 'de_DE', 'fr_FR', 'es_ES'])
Faker.seed(42)
random.seed(42)
np.random.seed(42)


class DataGenerator:
    """
    Generate realistic sample data with intentional data quality issues.
    
    Simulates:
    - Missing values and inconsistent formatting
    - Duplicate records with slight variations
    - Timezone inconsistencies
    - Schema changes over time
    - Late-arriving facts
    - Multi-currency transactions
    """
    
    # Currency exchange rates (to USD)
    EXCHANGE_RATES = {
        'USD': 1.0,
        'EUR': 1.08,
        'GBP': 1.26,
        'CAD': 0.74,
        'AUD': 0.65,
        'JPY': 0.0067,
        'CHF': 1.12,
        'MXN': 0.058
    }
    
    # Timezones for inconsistency simulation
    TIMEZONES = [
        'UTC', 'America/New_York', 'America/Los_Angeles', 
        'Europe/London', 'Europe/Berlin', 'Asia/Tokyo',
        'Australia/Sydney', 'America/Chicago'
    ]
    
    # Product categories
    CATEGORIES = [
        'Electronics', 'Clothing', 'Home & Garden', 'Sports',
        'Books', 'Beauty', 'Toys', 'Food & Grocery', 'Automotive'
    ]
    
    def __init__(self, output_dir: str = "data/sample"):
        """
        Initialize the data generator.
        
        Args:
            output_dir: Directory to save generated data
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate base data
        self._customers: Optional[pd.DataFrame] = None
        self._products: Optional[pd.DataFrame] = None
    
    def generate_customers(
        self,
        n_customers: int = 10000,
        duplicate_rate: float = 0.05,
        missing_rate: float = 0.08,
        include_schema_v1: bool = True
    ) -> pd.DataFrame:
        """
        Generate customer data with duplicates and missing values.
        
        Args:
            n_customers: Number of unique customers to generate
            duplicate_rate: Fraction of records to duplicate with variations
            missing_rate: Fraction of values to make null
            include_schema_v1: Include legacy schema format
            
        Returns:
            DataFrame with customer data
        """
        logger.info("Generating customer data", n_customers=n_customers)
        
        customers = []
        for i in range(n_customers):
            customer_id = f"CUST_{i:06d}"
            first_name = fake.first_name()
            last_name = fake.last_name()
            
            customer = {
                'customer_id': customer_id,
                'first_name': first_name,
                'last_name': last_name,
                'email': f"{first_name.lower()}.{last_name.lower()}@{fake.free_email_domain()}",
                'phone': self._generate_messy_phone(),
                'address': fake.street_address(),
                'city': fake.city(),
                'state': fake.state_abbr() if random.random() > 0.3 else fake.state(),
                'postal_code': self._generate_messy_postal_code(),
                'country': random.choice(['US', 'USA', 'United States', 'CA', 'UK', 'GB']),
                'registration_date': self._generate_messy_date(
                    start_date=datetime(2018, 1, 1),
                    end_date=datetime(2024, 1, 1)
                ),
                'customer_segment': random.choice(['Enterprise', 'SMB', 'Consumer', 'enterprise', 'smb']),
                'lifetime_value': round(random.uniform(0, 50000), 2),
                'is_active': random.choice([True, False, 'Y', 'N', 1, 0, 'true', 'false']),
                'source_system': random.choice(['CRM', 'Website', 'Mobile', 'Partner']),
                'created_at': datetime.now().isoformat(),
                'updated_at': datetime.now().isoformat()
            }
            customers.append(customer)
        
        df = pd.DataFrame(customers)
        
        # Add duplicates with slight variations
        n_duplicates = int(len(df) * duplicate_rate)
        duplicate_indices = random.sample(range(len(df)), n_duplicates)
        duplicates = df.iloc[duplicate_indices].copy()
        
        # Introduce variations in duplicates
        for idx in range(len(duplicates)):
            variation_type = random.choice(['typo', 'format', 'missing'])
            if variation_type == 'typo':
                # Typo in name
                name = duplicates.iloc[idx]['first_name']
                if len(name) > 2:
                    pos = random.randint(1, len(name) - 1)
                    duplicates.iloc[idx, duplicates.columns.get_loc('first_name')] = (
                        name[:pos] + random.choice('aeiou') + name[pos+1:]
                    )
            elif variation_type == 'format':
                # Different email format
                duplicates.iloc[idx, duplicates.columns.get_loc('email')] = (
                    duplicates.iloc[idx]['email'].upper()
                )
            else:
                # Missing phone
                duplicates.iloc[idx, duplicates.columns.get_loc('phone')] = None
        
        df = pd.concat([df, duplicates], ignore_index=True)
        
        # Introduce missing values
        for col in ['phone', 'address', 'postal_code', 'customer_segment']:
            mask = np.random.random(len(df)) < missing_rate
            df.loc[mask, col] = None
        
        # Store for later use
        self._customers = df
        
        logger.info("Customer data generated", total_records=len(df))
        return df
    
    def generate_products(self, n_products: int = 500) -> pd.DataFrame:
        """
        Generate product catalog data.
        
        Args:
            n_products: Number of products to generate
            
        Returns:
            DataFrame with product data
        """
        logger.info("Generating product data", n_products=n_products)
        
        products = []
        for i in range(n_products):
            category = random.choice(self.CATEGORIES)
            base_price = random.uniform(5, 500)
            
            product = {
                'product_id': f"PROD_{i:05d}",
                'product_name': f"{fake.word().title()} {fake.word().title()} {category}",
                'category': category,
                'subcategory': f"{category} - {fake.word().title()}",
                'brand': fake.company().split()[0],
                'sku': f"SKU-{fake.bothify(text='??###??').upper()}",
                'unit_price': round(base_price, 2),
                'cost_price': round(base_price * random.uniform(0.3, 0.7), 2),
                'currency': 'USD',
                'weight_kg': round(random.uniform(0.1, 50), 2),
                'is_active': random.choice([True, True, True, False]),
                'created_date': fake.date_between(start_date='-5y', end_date='-1y'),
                'last_updated': datetime.now().date()
            }
            products.append(product)
        
        df = pd.DataFrame(products)
        self._products = df
        
        logger.info("Product data generated", total_records=len(df))
        return df
    
    def generate_transactions(
        self,
        n_transactions: int = 100000,
        late_arrival_rate: float = 0.03,
        multi_currency: bool = True
    ) -> pd.DataFrame:
        """
        Generate transaction data with timezone inconsistencies and late arrivals.
        
        Args:
            n_transactions: Number of transactions to generate
            late_arrival_rate: Fraction of transactions that arrive late
            multi_currency: Include multiple currencies
            
        Returns:
            DataFrame with transaction data
        """
        if self._customers is None:
            self.generate_customers()
        if self._products is None:
            self.generate_products()
        
        logger.info("Generating transaction data", n_transactions=n_transactions)
        
        customer_ids = self._customers['customer_id'].unique()
        product_ids = self._products['product_id'].unique()
        
        transactions = []
        for i in range(n_transactions):
            # Generate transaction timestamp with timezone inconsistency
            base_date = fake.date_time_between(start_date='-2y', end_date='now')
            timezone = random.choice(self.TIMEZONES)
            
            # Some transactions have timezone info, others don't
            if random.random() > 0.4:
                timestamp = f"{base_date.isoformat()}"
            else:
                timestamp = f"{base_date.isoformat()}+{random.choice(['00:00', '05:00', '-08:00', 'Z'])}"
            
            # Currency selection
            if multi_currency:
                currency = random.choices(
                    list(self.EXCHANGE_RATES.keys()),
                    weights=[0.6, 0.15, 0.1, 0.05, 0.03, 0.03, 0.02, 0.02]
                )[0]
            else:
                currency = 'USD'
            
            product_id = random.choice(product_ids)
            product = self._products[self._products['product_id'] == product_id].iloc[0]
            quantity = random.randint(1, 10)
            unit_price = product['unit_price'] / self.EXCHANGE_RATES.get(currency, 1.0)
            
            # Add some price variations
            if random.random() < 0.2:
                unit_price *= random.uniform(0.8, 1.2)  # Discounts/markups
            
            transaction = {
                'transaction_id': f"TXN_{i:08d}",
                'customer_id': random.choice(customer_ids),
                'product_id': product_id,
                'quantity': quantity,
                'unit_price': round(unit_price, 2),
                'total_amount': round(unit_price * quantity, 2),
                'currency': currency,
                'transaction_timestamp': timestamp,
                'transaction_date': base_date.date().isoformat(),
                'payment_method': random.choice([
                    'Credit Card', 'credit_card', 'CREDIT CARD',
                    'PayPal', 'paypal', 'PAYPAL',
                    'Debit Card', 'Bank Transfer', 'Apple Pay'
                ]),
                'status': random.choices(
                    ['completed', 'COMPLETED', 'Completed', 'pending', 'refunded', 'failed'],
                    weights=[0.4, 0.3, 0.15, 0.05, 0.05, 0.05]
                )[0],
                'channel': random.choice(['web', 'mobile', 'store', 'Web', 'Mobile']),
                'source_timezone': timezone if random.random() > 0.5 else None,
                'processing_date': (base_date + timedelta(days=random.randint(0, 3))).date().isoformat()
            }
            
            # Mark some as late-arriving
            if random.random() < late_arrival_rate:
                transaction['is_late_arrival'] = True
                transaction['original_date'] = (base_date - timedelta(days=random.randint(5, 30))).date().isoformat()
            else:
                transaction['is_late_arrival'] = False
                transaction['original_date'] = None
            
            transactions.append(transaction)
        
        df = pd.DataFrame(transactions)
        
        logger.info("Transaction data generated", total_records=len(df))
        return df
    
    def generate_sessions(
        self,
        n_sessions: int = 50000,
        missing_rate: float = 0.1
    ) -> pd.DataFrame:
        """
        Generate customer session/behavioral data.
        
        Args:
            n_sessions: Number of sessions to generate
            missing_rate: Fraction of values to make null
            
        Returns:
            DataFrame with session data
        """
        if self._customers is None:
            self.generate_customers()
        
        logger.info("Generating session data", n_sessions=n_sessions)
        
        customer_ids = self._customers['customer_id'].unique()
        
        sessions = []
        for i in range(n_sessions):
            start_time = fake.date_time_between(start_date='-1y', end_date='now')
            duration_minutes = random.randint(1, 120)
            
            session = {
                'session_id': f"SESS_{i:08d}",
                'customer_id': random.choice(customer_ids) if random.random() > 0.1 else None,  # Anonymous sessions
                'session_start': start_time.isoformat(),
                'session_end': (start_time + timedelta(minutes=duration_minutes)).isoformat(),
                'duration_seconds': duration_minutes * 60 + random.randint(0, 59),
                'page_views': random.randint(1, 50),
                'device_type': random.choice(['desktop', 'mobile', 'tablet', 'Desktop', 'Mobile', None]),
                'browser': random.choice(['Chrome', 'Safari', 'Firefox', 'Edge', 'chrome', 'safari', None]),
                'os': random.choice(['Windows', 'macOS', 'iOS', 'Android', 'Linux', None]),
                'referrer': random.choice([
                    'google.com', 'facebook.com', 'direct', 'email', 
                    'twitter.com', None, '', 'unknown'
                ]),
                'landing_page': random.choice(['/home', '/products', '/sale', '/category/*', '/']),
                'exit_page': random.choice(['/checkout', '/cart', '/products', '/home', '/']),
                'events_count': random.randint(1, 100),
                'conversion': random.choices([True, False], weights=[0.15, 0.85])[0],
                'country': random.choice(['US', 'CA', 'UK', 'DE', 'FR', 'AU', None]),
                'city': fake.city() if random.random() > missing_rate else None
            }
            sessions.append(session)
        
        df = pd.DataFrame(sessions)
        
        logger.info("Session data generated", total_records=len(df))
        return df
    
    def generate_support_interactions(
        self,
        n_interactions: int = 20000
    ) -> pd.DataFrame:
        """
        Generate customer support interaction data.
        
        Args:
            n_interactions: Number of support interactions to generate
            
        Returns:
            DataFrame with support interaction data
        """
        if self._customers is None:
            self.generate_customers()
        
        logger.info("Generating support interaction data", n_interactions=n_interactions)
        
        customer_ids = self._customers['customer_id'].unique()
        
        interactions = []
        for i in range(n_interactions):
            created_at = fake.date_time_between(start_date='-2y', end_date='now')
            resolution_hours = random.randint(0, 168) if random.random() > 0.1 else None
            
            interaction = {
                'ticket_id': f"TKT_{i:07d}",
                'customer_id': random.choice(customer_ids),
                'channel': random.choice(['email', 'phone', 'chat', 'Email', 'Phone', 'Chat']),
                'category': random.choice([
                    'Billing', 'Technical', 'Shipping', 'Returns', 
                    'Product Inquiry', 'Account', 'Other'
                ]),
                'priority': random.choice(['low', 'medium', 'high', 'urgent', 'Low', 'Medium', 'High']),
                'status': random.choice(['open', 'in_progress', 'resolved', 'closed', 'Open', 'Closed']),
                'subject': fake.sentence(nb_words=6),
                'description': fake.paragraph(nb_sentences=3) if random.random() > 0.2 else None,
                'created_at': created_at.isoformat(),
                'resolved_at': (created_at + timedelta(hours=resolution_hours)).isoformat() if resolution_hours else None,
                'resolution_hours': resolution_hours,
                'satisfaction_score': random.randint(1, 5) if random.random() > 0.3 else None,
                'agent_id': f"AGENT_{random.randint(1, 50):03d}",
                'first_response_minutes': random.randint(1, 1440) if random.random() > 0.1 else None
            }
            interactions.append(interaction)
        
        df = pd.DataFrame(interactions)
        
        logger.info("Support interaction data generated", total_records=len(df))
        return df
    
    def generate_api_response(
        self,
        data_type: str = "customers",
        n_records: int = 100,
        include_nested: bool = True
    ) -> Dict[str, Any]:
        """
        Generate JSON API response with nested structures.
        
        Args:
            data_type: Type of data to generate
            n_records: Number of records
            include_nested: Include nested objects
            
        Returns:
            Dictionary representing API response
        """
        if data_type == "customers":
            df = self.generate_customers(n_customers=n_records)
        elif data_type == "transactions":
            df = self.generate_transactions(n_transactions=n_records)
        else:
            df = self.generate_sessions(n_sessions=n_records)
        
        records = df.to_dict(orient='records')
        
        if include_nested:
            for record in records:
                record['metadata'] = {
                    'source': random.choice(['api_v1', 'api_v2', 'webhook']),
                    'version': random.choice(['1.0', '1.1', '2.0']),
                    'processed_at': datetime.now().isoformat(),
                    'tags': [fake.word() for _ in range(random.randint(0, 5))]
                }
                record['audit'] = {
                    'created_by': f"system_{random.randint(1, 5)}",
                    'modified_by': f"user_{random.randint(1, 100)}",
                    'version': random.randint(1, 10)
                }
        
        response = {
            'status': 'success',
            'data': records,
            'pagination': {
                'page': 1,
                'per_page': n_records,
                'total': n_records * random.randint(10, 100),
                'total_pages': random.randint(10, 100)
            },
            'meta': {
                'api_version': '2.1',
                'request_id': fake.uuid4(),
                'timestamp': datetime.now().isoformat()
            }
        }
        
        return response
    
    def save_all_sample_data(self) -> Dict[str, str]:
        """
        Generate and save all sample data files.
        
        Returns:
            Dictionary mapping data type to file path
        """
        output_files = {}
        
        # Generate CSVs
        customers_df = self.generate_customers()
        customers_path = self.output_dir / "customers_messy.csv"
        customers_df.to_csv(customers_path, index=False)
        output_files['customers_csv'] = str(customers_path)
        
        products_df = self.generate_products()
        products_path = self.output_dir / "products.csv"
        products_df.to_csv(products_path, index=False)
        output_files['products_csv'] = str(products_path)
        
        transactions_df = self.generate_transactions()
        transactions_path = self.output_dir / "transactions_messy.csv"
        transactions_df.to_csv(transactions_path, index=False)
        output_files['transactions_csv'] = str(transactions_path)
        
        sessions_df = self.generate_sessions()
        sessions_path = self.output_dir / "sessions_messy.csv"
        sessions_df.to_csv(sessions_path, index=False)
        output_files['sessions_csv'] = str(sessions_path)
        
        support_df = self.generate_support_interactions()
        support_path = self.output_dir / "support_interactions.csv"
        support_df.to_csv(support_path, index=False)
        output_files['support_csv'] = str(support_path)
        
        # Generate JSON API responses
        for data_type in ['customers', 'transactions']:
            api_response = self.generate_api_response(data_type=data_type, n_records=500)
            json_path = self.output_dir / f"{data_type}_api_response.json"
            with open(json_path, 'w') as f:
                json.dump(api_response, f, indent=2, default=str)
            output_files[f'{data_type}_json'] = str(json_path)
        
        # Generate schema evolution files (simulating database dumps over time)
        self._generate_schema_evolution_files()
        output_files['schema_evolution'] = str(self.output_dir / "schema_versions")
        
        logger.info("All sample data saved", output_files=output_files)
        return output_files
    
    def _generate_schema_evolution_files(self) -> None:
        """Generate files showing schema evolution over time."""
        schema_dir = self.output_dir / "schema_versions"
        schema_dir.mkdir(exist_ok=True)
        
        # Version 1: Original schema (2 years ago)
        v1_customers = self._customers[['customer_id', 'first_name', 'last_name', 'email', 'phone', 'registration_date']].copy()
        v1_customers['full_name'] = v1_customers['first_name'] + ' ' + v1_customers['last_name']
        v1_customers = v1_customers.drop(['first_name', 'last_name'], axis=1)
        v1_customers.to_csv(schema_dir / "customers_v1_2022.csv", index=False)
        
        # Version 2: Added address fields (1 year ago)
        v2_customers = self._customers[['customer_id', 'first_name', 'last_name', 'email', 'phone', 
                                         'address', 'city', 'registration_date']].copy()
        v2_customers.to_csv(schema_dir / "customers_v2_2023.csv", index=False)
        
        # Version 3: Current schema with all fields
        self._customers.to_csv(schema_dir / "customers_v3_2024.csv", index=False)
    
    def _generate_messy_phone(self) -> str:
        """Generate phone number with inconsistent formatting."""
        formats = [
            "{area}-{exchange}-{number}",
            "({area}) {exchange}-{number}",
            "{area}.{exchange}.{number}",
            "+1{area}{exchange}{number}",
            "{area}{exchange}{number}",
            "+1 ({area}) {exchange}-{number}"
        ]
        
        area = str(random.randint(200, 999))
        exchange = str(random.randint(200, 999))
        number = str(random.randint(1000, 9999))
        
        return random.choice(formats).format(area=area, exchange=exchange, number=number)
    
    def _generate_messy_postal_code(self) -> str:
        """Generate postal code with inconsistent formatting."""
        if random.random() > 0.7:
            # Canadian format
            return fake.bothify(text='?#? #?#').upper()
        else:
            # US format with variations
            zip_code = str(random.randint(10000, 99999))
            if random.random() > 0.7:
                zip_code += f"-{random.randint(1000, 9999)}"
            return zip_code
    
    def _generate_messy_date(
        self,
        start_date: datetime,
        end_date: datetime
    ) -> str:
        """Generate date with inconsistent formatting."""
        date = fake.date_time_between(start_date=start_date, end_date=end_date)
        
        formats = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%d-%m-%Y",
            "%Y/%m/%d",
            "%B %d, %Y",
            "%d %b %Y"
        ]
        
        return date.strftime(random.choice(formats))


if __name__ == "__main__":
    # Generate sample data when run directly
    generator = DataGenerator()
    files = generator.save_all_sample_data()
    print("Generated files:")
    for name, path in files.items():
        print(f"  {name}: {path}")

