# src/exceptions.py

class CryptoPilotError(Exception):
    """Base exception for Crypto-Pilot application."""
    pass

class DataFeedError(CryptoPilotError):
    """Raised when data fetching fails (e.g. API timeout, invalid symbol)."""
    pass

class ModelError(CryptoPilotError):
    """Raised when model inference fails (e.g. tensor shape mismatch)."""
    pass

class StrategyError(CryptoPilotError):
    """Raised when strategy analysis fails."""
    pass

class ConfigurationError(CryptoPilotError):
    """Raised when config/thresholds are invalid."""
    pass
