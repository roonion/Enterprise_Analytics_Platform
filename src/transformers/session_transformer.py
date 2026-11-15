"""Session/behavioral data transformer."""

from typing import Any, Dict, List, Optional

import pandas as pd

from src.transformers.base_transformer import BaseTransformer
from src.utils.logging_config import get_logger

logger = get_logger(__name__)


class SessionTransformer(BaseTransformer):
    """
    Transform customer session and behavioral data.
    
    Handles:
    - Device type normalization
    - Browser/OS standardization
    - Referrer categorization
    - Session metric calculations
    - Conversion tracking
    """
    
    def __init__(
        self,
        calculate_engagement_score: bool = True,
        categorize_sessions: bool = True
    ):
        """
        Initialize the session transformer.
        
        Args:
            calculate_engagement_score: Whether to calculate engagement scores
            categorize_sessions: Whether to categorize session types
        """
        super().__init__(name="SessionTransformer")
        self.calculate_engagement = calculate_engagement_score
        self.categorize_sessions = categorize_sessions
    
    def transform(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """
        Transform session data.
        
        Args:
            df: Input session DataFrame
            
        Returns:
            Transformed DataFrame
        """
        df = df.copy()
        
        # Standardize column names
        df.columns = df.columns.str.lower().str.strip()
        
        # Normalize device type
        df = self._normalize_device_type(df)
        
        # Normalize browser
        df = self._normalize_browser(df)
        
        # Normalize OS
        df = self._normalize_os(df)
        
        # Categorize referrer
        df = self._categorize_referrer(df)
        
        # Parse timestamps
        df = self._parse_timestamps(df)
        
        # Calculate session metrics
        df = self._calculate_session_metrics(df)
        
        # Calculate engagement score
        if self.calculate_engagement:
            df = self._calculate_engagement_score(df)
        
        # Categorize sessions
        if self.categorize_sessions:
            df = self._categorize_sessions(df)
        
        return df
    
    def _normalize_device_type(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize device type values."""
        if 'device_type' not in df.columns:
            return df
        
        device_mapping = {
            'desktop': 'Desktop',
            'pc': 'Desktop',
            'computer': 'Desktop',
            'mobile': 'Mobile',
            'phone': 'Mobile',
            'smartphone': 'Mobile',
            'tablet': 'Tablet',
            'ipad': 'Tablet',
            'tv': 'Smart TV',
            'smart tv': 'Smart TV',
            'smarttv': 'Smart TV'
        }
        
        df['device_type'] = (
            df['device_type']
            .fillna('Unknown')
            .astype(str)
            .str.lower()
            .str.strip()
            .map(lambda x: device_mapping.get(x, x.title()))
        )
        
        return df
    
    def _normalize_browser(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize browser values."""
        if 'browser' not in df.columns:
            return df
        
        browser_mapping = {
            'chrome': 'Chrome',
            'google chrome': 'Chrome',
            'safari': 'Safari',
            'firefox': 'Firefox',
            'mozilla': 'Firefox',
            'edge': 'Edge',
            'microsoft edge': 'Edge',
            'ie': 'Internet Explorer',
            'internet explorer': 'Internet Explorer',
            'opera': 'Opera',
            'brave': 'Brave',
            'samsung': 'Samsung Browser',
            'samsung browser': 'Samsung Browser'
        }
        
        df['browser'] = (
            df['browser']
            .fillna('Unknown')
            .astype(str)
            .str.lower()
            .str.strip()
            .map(lambda x: browser_mapping.get(x, x.title()))
        )
        
        # Extract browser family
        df['browser_family'] = df['browser'].apply(self._get_browser_family)
        
        return df
    
    def _get_browser_family(self, browser: str) -> str:
        """Get browser family from browser name."""
        chromium_browsers = ['Chrome', 'Edge', 'Brave', 'Opera', 'Samsung Browser']
        if browser in chromium_browsers:
            return 'Chromium'
        elif browser == 'Safari':
            return 'WebKit'
        elif browser == 'Firefox':
            return 'Gecko'
        else:
            return 'Other'
    
    def _normalize_os(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize operating system values."""
        if 'os' not in df.columns:
            return df
        
        os_mapping = {
            'windows': 'Windows',
            'win': 'Windows',
            'windows 10': 'Windows',
            'windows 11': 'Windows',
            'macos': 'macOS',
            'mac os': 'macOS',
            'mac': 'macOS',
            'osx': 'macOS',
            'ios': 'iOS',
            'iphone': 'iOS',
            'ipad': 'iOS',
            'android': 'Android',
            'linux': 'Linux',
            'ubuntu': 'Linux',
            'chrome os': 'Chrome OS',
            'chromeos': 'Chrome OS'
        }
        
        df['os'] = (
            df['os']
            .fillna('Unknown')
            .astype(str)
            .str.lower()
            .str.strip()
            .map(lambda x: os_mapping.get(x, x.title()))
        )
        
        # Categorize OS type
        mobile_os = ['iOS', 'Android']
        df['is_mobile_os'] = df['os'].isin(mobile_os)
        
        return df
    
    def _categorize_referrer(self, df: pd.DataFrame) -> pd.DataFrame:
        """Categorize traffic sources from referrer."""
        if 'referrer' not in df.columns:
            return df
        
        def categorize(referrer: str) -> str:
            if pd.isna(referrer) or referrer in ['', 'direct', 'none', 'unknown', '(direct)']:
                return 'Direct'
            
            referrer = str(referrer).lower()
            
            # Search engines
            search_engines = ['google', 'bing', 'yahoo', 'duckduckgo', 'baidu', 'yandex']
            if any(se in referrer for se in search_engines):
                return 'Organic Search'
            
            # Social media
            social = ['facebook', 'twitter', 'instagram', 'linkedin', 'tiktok', 'pinterest', 'reddit', 'youtube']
            if any(s in referrer for s in social):
                return 'Social'
            
            # Email
            if any(e in referrer for e in ['email', 'mail', 'newsletter']):
                return 'Email'
            
            # Paid
            if any(p in referrer for p in ['ad', 'cpc', 'ppc', 'paid']):
                return 'Paid'
            
            return 'Referral'
        
        df['traffic_source'] = df['referrer'].apply(categorize)
        
        return df
    
    def _parse_timestamps(self, df: pd.DataFrame) -> pd.DataFrame:
        """Parse session timestamps."""
        timestamp_columns = ['session_start', 'session_end']
        
        for col in timestamp_columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
        
        # Extract time parts
        if 'session_start' in df.columns:
            df['session_hour'] = df['session_start'].dt.hour
            df['session_day_of_week'] = df['session_start'].dt.dayofweek
            df['session_date'] = df['session_start'].dt.date
            
            # Categorize time of day
            df['time_of_day'] = pd.cut(
                df['session_hour'],
                bins=[0, 6, 12, 18, 24],
                labels=['Night', 'Morning', 'Afternoon', 'Evening'],
                include_lowest=True
            )
        
        return df
    
    def _calculate_session_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate session metrics."""
        # Calculate duration if not present
        if 'duration_seconds' not in df.columns:
            if all(c in df.columns for c in ['session_start', 'session_end']):
                df['duration_seconds'] = (
                    df['session_end'] - df['session_start']
                ).dt.total_seconds()
        
        # Duration in minutes
        if 'duration_seconds' in df.columns:
            df['duration_minutes'] = df['duration_seconds'] / 60
        
        # Pages per minute
        if all(c in df.columns for c in ['page_views', 'duration_minutes']):
            df['pages_per_minute'] = df.apply(
                lambda r: r['page_views'] / r['duration_minutes'] 
                if r['duration_minutes'] > 0 else 0,
                axis=1
            )
        
        # Bounce rate indicator (single page view)
        if 'page_views' in df.columns:
            df['is_bounce'] = df['page_views'] == 1
        
        return df
    
    def _calculate_engagement_score(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate engagement score (0-100) based on session metrics.
        
        Score components:
        - Duration (max 30 points)
        - Page views (max 30 points)
        - Events (max 20 points)
        - Conversion (20 points)
        """
        df['engagement_score'] = 0.0
        
        # Duration component (up to 30 points, max at 10 minutes)
        if 'duration_minutes' in df.columns:
            df['engagement_score'] += (
                df['duration_minutes'].clip(0, 10) / 10 * 30
            )
        
        # Page views component (up to 30 points, max at 10 pages)
        if 'page_views' in df.columns:
            df['engagement_score'] += (
                df['page_views'].clip(0, 10) / 10 * 30
            )
        
        # Events component (up to 20 points, max at 20 events)
        if 'events_count' in df.columns:
            df['engagement_score'] += (
                df['events_count'].clip(0, 20) / 20 * 20
            )
        
        # Conversion component (20 points)
        if 'conversion' in df.columns:
            df['engagement_score'] += df['conversion'].astype(int) * 20
        
        df['engagement_score'] = df['engagement_score'].round(1)
        
        return df
    
    def _categorize_sessions(self, df: pd.DataFrame) -> pd.DataFrame:
        """Categorize sessions based on behavior."""
        def categorize(row: pd.Series) -> str:
            # Check for conversion
            if row.get('conversion', False):
                return 'Converter'
            
            # Check engagement level
            engagement = row.get('engagement_score', 0)
            page_views = row.get('page_views', 0)
            duration = row.get('duration_minutes', 0)
            
            if page_views == 1 and duration < 0.5:
                return 'Bouncer'
            elif engagement >= 70:
                return 'Highly Engaged'
            elif engagement >= 40:
                return 'Engaged'
            elif engagement >= 20:
                return 'Browser'
            else:
                return 'Low Engagement'
        
        df['session_category'] = df.apply(categorize, axis=1)
        
        return df

