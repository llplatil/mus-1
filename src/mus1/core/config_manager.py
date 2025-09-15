"""
Unified Configuration Manager for MUS1

This module provides a single, hierarchical configuration system that replaces
the scattered configuration approach used throughout the application.

Configuration Hierarchy (highest to lowest precedence):
1. Runtime Overrides (CLI args, environment variables)
2. Project Context
3. Lab Context
4. User Profile
5. Installation Defaults


Date: 2025-09-14
"""

import os
import json
import sqlite3
import logging
import platform
from pathlib import Path
from typing import Dict, Any, Optional, List, Union, Callable
from dataclasses import dataclass, field
from datetime import datetime
from contextlib import contextmanager
import hashlib

logger = logging.getLogger("mus1.core.config_manager")


# ===========================================
# MUS1 ROOT RESOLUTION - SIMPLE & DETERMINISTIC
# ===========================================

def resolve_mus1_root() -> Path:
    """
    Deterministically resolve MUS1 root directory.

    Priority (highest to lowest):
    1. MUS1_ROOT environment variable (if set and valid)
    2. Existing MUS1 root in platform default location
    3. Create/use platform default location

    Returns:
        Path to MUS1 root directory (guaranteed to exist)
    """
    # Priority 1: Environment variable
    env_root = os.environ.get("MUS1_ROOT")
    if env_root:
        root_path = Path(env_root).expanduser().resolve()
        if _is_valid_mus1_root(root_path):
            return root_path
        logger.warning(f"MUS1_ROOT environment variable points to invalid location: {root_path}")

    # Priority 2: Platform default with existing config
    default_root = _get_platform_default_mus1_root()
    if _is_valid_mus1_root(default_root):
        return default_root

    # Priority 3: Create platform default
    return _create_mus1_root(default_root)


def _get_platform_default_mus1_root() -> Path:
    """Get platform-specific default MUS1 root location."""
    if platform.system() == "Darwin":  # macOS
        return Path.home() / "Library" / "Application Support" / "MUS1"
    elif platform.system() == "Windows":
        appdata = os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))
        return Path(appdata) / "MUS1"
    else:  # Linux/Unix
        xdg_config = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        return Path(xdg_config) / "mus1"


def _is_valid_mus1_root(path: Path) -> bool:
    """Check if path is a valid MUS1 root directory."""
    if not path.exists() or not path.is_dir():
        return False

    # Check for config directory and database
    config_dir = path / "config"
    if not config_dir.exists():
        return False

    db_path = config_dir / "config.db"
    return db_path.exists() and db_path.is_file()


def _create_mus1_root(root_path: Path) -> Path:
    """Create MUS1 root directory structure."""
    try:
        # Create main directory
        root_path.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        subdirs = ["config", "logs", "cache", "temp"]
        for subdir in subdirs:
            (root_path / subdir).mkdir(exist_ok=True)

        logger.info(f"Created MUS1 root directory at: {root_path}")
        return root_path

    except Exception as e:
        # Fallback to current working directory if creation fails
        fallback_root = Path.cwd() / ".mus1"
        fallback_root.mkdir(parents=True, exist_ok=True)
        logger.warning(f"Failed to create default MUS1 root, using fallback: {fallback_root} ({e})")
        return fallback_root


# ===========================================
# CONFIG MANAGER (SIMPLIFIED)
# ===========================================


@dataclass
class ConfigScope:
    """Represents a configuration scope in the hierarchy."""
    name: str
    level: int  # Higher numbers = higher precedence
    path: Optional[Path] = None
    data: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = True


class ConfigManager:
    """
    Unified configuration manager that provides hierarchical configuration
    with SQLite persistence and automatic migration support.
    """

    # Configuration scope levels (higher = higher precedence)
    SCOPE_INSTALL = 10
    SCOPE_USER = 20
    SCOPE_LAB = 30
    SCOPE_PROJECT = 40
    SCOPE_RUNTIME = 50

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize the configuration manager.

        Args:
            db_path: Path to SQLite database. If None, uses MUS1 root resolution.
        """
        # Use deterministic MUS1 root resolution if no explicit path provided
        if db_path is None:
            mus1_root = resolve_mus1_root()
            config_dir = mus1_root / "config"
            config_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = config_dir / "config.db"
        else:
            self.db_path = db_path
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._connection: Optional[sqlite3.Connection] = None
        self._scopes: Dict[str, ConfigScope] = {}
        self._cache: Dict[str, Any] = {}
        self._cache_dirty = False

        # Initialize database and scopes
        self._init_database()
        self._init_scopes()

        logger.info(f"ConfigManager initialized with database at {self.db_path}")

    @contextmanager
    def _get_connection(self):
        """Get a database connection with proper cleanup."""
        if self._connection is None:
            self._connection = sqlite3.connect(str(self.db_path))
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.row_factory = sqlite3.Row

        try:
            yield self._connection
        except Exception as e:
            logger.error(f"Database operation failed: {e}")
            if self._connection:
                self._connection.rollback()
            raise
        finally:
            # Keep connection alive for performance
            pass

    def _init_database(self):
        """Initialize the database schema."""
        with self._get_connection() as conn:
            # Create configuration scopes table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS config_scopes (
                    id INTEGER PRIMARY KEY,
                    scope_name TEXT UNIQUE NOT NULL,
                    scope_level INTEGER NOT NULL,
                    scope_path TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create configuration entries table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS config_entries (
                    id INTEGER PRIMARY KEY,
                    scope_name TEXT NOT NULL,
                    key_path TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (scope_name) REFERENCES config_scopes(scope_name) ON DELETE CASCADE,
                    UNIQUE(scope_name, key_path)
                )
            """)

            # Create migrations table for schema versioning
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id INTEGER PRIMARY KEY,
                    migration_name TEXT UNIQUE NOT NULL,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes for performance
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_config_entries_scope_key
                ON config_entries(scope_name, key_path)
            """)

            conn.commit()

    def _init_scopes(self):
        """Initialize the standard configuration scopes."""
        scopes_data = [
            ("install", self.SCOPE_INSTALL, None),
            ("user", self.SCOPE_USER, None),
            ("lab", self.SCOPE_LAB, None),
            ("project", self.SCOPE_PROJECT, None),
            ("runtime", self.SCOPE_RUNTIME, None),
        ]

        with self._get_connection() as conn:
            for scope_name, level, path in scopes_data:
                conn.execute("""
                    INSERT OR IGNORE INTO config_scopes
                    (scope_name, scope_level, scope_path, is_active)
                    VALUES (?, ?, ?, 1)
                """, (scope_name, level, path))

                # Load existing data for this scope
                self._load_scope_data(scope_name)

            conn.commit()

    def _load_scope_data(self, scope_name: str):
        """Load configuration data for a scope from the database."""
        with self._get_connection() as conn:
            cursor = conn.execute("""
                SELECT key_path, value_json FROM config_entries
                WHERE scope_name = ? ORDER BY updated_at DESC
            """, (scope_name,))

            scope_data = {}
            for row in cursor:
                try:
                    value = json.loads(row['value_json'])
                    self._set_nested_value(scope_data, row['key_path'], value)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to decode config value for {row['key_path']}: {e}")

            self._scopes[scope_name] = ConfigScope(
                name=scope_name,
                level=self._get_scope_level(scope_name),
                data=scope_data
            )

    def _get_scope_level(self, scope_name: str) -> int:
        """Get the precedence level for a scope."""
        levels = {
            "install": self.SCOPE_INSTALL,
            "user": self.SCOPE_USER,
            "lab": self.SCOPE_LAB,
            "project": self.SCOPE_PROJECT,
            "runtime": self.SCOPE_RUNTIME,
        }
        return levels.get(scope_name, 0)

    def _set_nested_value(self, data: dict, key_path: str, value: Any):
        """Set a value in a nested dictionary using dot notation."""
        keys = key_path.split('.')
        current = data

        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        current[keys[-1]] = value

    def _get_nested_value(self, data: dict, key_path: str, default=None):
        """Get a value from a nested dictionary using dot notation."""
        keys = key_path.split('.')
        current = data

        try:
            for key in keys:
                current = current[key]
            return current
        except (KeyError, TypeError):
            return default

    def get(self, key: str, default=None, scope: Optional[str] = None) -> Any:
        """
        Get a configuration value using hierarchical lookup.

        Args:
            key: Dot-separated key path (e.g., "ui.theme", "data.import.format")
            default: Default value if key not found
            scope: Specific scope to query (bypasses hierarchy)

        Returns:
            Configuration value or default
        """
        if scope:
            # Query specific scope only
            scope_obj = self._scopes.get(scope)
            if scope_obj and scope_obj.is_active:
                return self._get_nested_value(scope_obj.data, key, default)
            return default

        # Hierarchical lookup (highest precedence first)
        sorted_scopes = sorted(
            [s for s in self._scopes.values() if s.is_active],
            key=lambda s: s.level,
            reverse=True
        )

        for scope_obj in sorted_scopes:
            value = self._get_nested_value(scope_obj.data, key)
            if value is not None:
                return value

        return default

    def set(self, key: str, value: Any, scope: str = "user", persist: bool = True):
        """
        Set a configuration value.

        Args:
            key: Dot-separated key path
            value: Value to set (will be JSON serialized)
            scope: Scope to store in
            persist: Whether to persist to database immediately
        """
        if scope not in self._scopes:
            raise ValueError(f"Unknown scope: {scope}")

        scope_obj = self._scopes[scope]
        self._set_nested_value(scope_obj.data, key, value)

        if persist:
            self._persist_value(scope, key, value)

        # Invalidate cache
        self._cache_dirty = True
        logger.debug(f"Set config {scope}.{key} = {value}")

    def _persist_value(self, scope: str, key: str, value: Any):
        """Persist a configuration value to the database."""
        with self._get_connection() as conn:
            value_json = json.dumps(value, default=str)

            conn.execute("""
                INSERT OR REPLACE INTO config_entries
                (scope_name, key_path, value_json, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (scope, key, value_json))

            conn.commit()

    def delete(self, key: str, scope: str):
        """Delete a configuration key."""
        if scope not in self._scopes:
            raise ValueError(f"Unknown scope: {scope}")

        scope_obj = self._scopes[scope]
        self._delete_nested_value(scope_obj.data, key)

        with self._get_connection() as conn:
            conn.execute("""
                DELETE FROM config_entries
                WHERE scope_name = ? AND key_path = ?
            """, (scope, key))
            conn.commit()

        self._cache_dirty = True

    def _delete_nested_value(self, data: dict, key_path: str):
        """Delete a value from a nested dictionary using dot notation."""
        keys = key_path.split('.')
        current = data

        try:
            for key in keys[:-1]:
                current = current[key]

            if keys[-1] in current:
                del current[keys[-1]]
        except (KeyError, TypeError):
            pass

    def set_scope_path(self, scope: str, path: Optional[Path]):
        """Set the filesystem path associated with a scope."""
        if scope not in self._scopes:
            raise ValueError(f"Unknown scope: {scope}")

        self._scopes[scope].path = path

        with self._get_connection() as conn:
            conn.execute("""
                UPDATE config_scopes
                SET scope_path = ?, updated_at = CURRENT_TIMESTAMP
                WHERE scope_name = ?
            """, (str(path) if path else None, scope))
            conn.commit()

    def get_scope_path(self, scope: str) -> Optional[Path]:
        """Get the filesystem path associated with a scope."""
        scope_obj = self._scopes.get(scope)
        return scope_obj.path if scope_obj else None

    def activate_scope(self, scope: str):
        """Activate a configuration scope."""
        if scope not in self._scopes:
            raise ValueError(f"Unknown scope: {scope}")

        self._scopes[scope].is_active = True

        with self._get_connection() as conn:
            conn.execute("""
                UPDATE config_scopes
                SET is_active = 1, updated_at = CURRENT_TIMESTAMP
                WHERE scope_name = ?
            """, (scope,))
            conn.commit()

    def deactivate_scope(self, scope: str):
        """Deactivate a configuration scope."""
        if scope not in self._scopes:
            raise ValueError(f"Unknown scope: {scope}")

        self._scopes[scope].is_active = False

        with self._get_connection() as conn:
            conn.execute("""
                UPDATE config_scopes
                SET is_active = 0, updated_at = CURRENT_TIMESTAMP
                WHERE scope_name = ?
            """, (scope,))
            conn.commit()

        self._cache_dirty = True

    def get_all_scopes(self) -> Dict[str, ConfigScope]:
        """Get all configuration scopes."""
        return self._scopes.copy()

    def get_scope_data(self, scope: str) -> Dict[str, Any]:
        """Get all data for a specific scope."""
        scope_obj = self._scopes.get(scope)
        return scope_obj.data.copy() if scope_obj else {}

    def export_scope(self, scope: str, file_path: Path):
        """Export a scope's configuration to a JSON file."""
        data = self.get_scope_data(scope)

        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)

        logger.info(f"Exported {scope} configuration to {file_path}")

    def import_scope(self, scope: str, file_path: Path, merge: bool = True):
        """Import configuration from a JSON file."""
        with open(file_path, 'r') as f:
            data = json.load(f)

        if not merge:
            # Clear existing data for this scope
            self._clear_scope_data(scope)

        # Import the new data
        self._import_nested_data(scope, data, "")

    def _clear_scope_data(self, scope: str):
        """Clear all data for a scope."""
        if scope in self._scopes:
            self._scopes[scope].data.clear()

        with self._get_connection() as conn:
            conn.execute("DELETE FROM config_entries WHERE scope_name = ?", (scope,))
            conn.commit()

    def _import_nested_data(self, scope: str, data: dict, prefix: str):
        """Recursively import nested configuration data."""
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key

            if isinstance(value, dict):
                self._import_nested_data(scope, value, full_key)
            else:
                self.set(full_key, value, scope)

    def get_config_hash(self) -> str:
        """Get a hash of the current configuration state."""
        config_str = json.dumps(self._get_hierarchical_config(), sort_keys=True, default=str)
        return hashlib.sha256(config_str.encode()).hexdigest()

    def _get_hierarchical_config(self) -> Dict[str, Any]:
        """Get the complete hierarchical configuration."""
        result = {}

        # Get all active scopes sorted by precedence
        sorted_scopes = sorted(
            [s for s in self._scopes.values() if s.is_active],
            key=lambda s: s.level,
            reverse=True
        )

        for scope in sorted_scopes:
            self._merge_config_dicts(result, scope.data)

        return result

    def _merge_config_dicts(self, target: dict, source: dict):
        """Recursively merge source dict into target dict."""
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._merge_config_dicts(target[key], value)
            else:
                target[key] = value

    def cleanup(self):
        """Clean up resources."""
        if self._connection:
            self._connection.close()
            self._connection = None

        logger.info("ConfigManager cleanup completed")


# Global configuration manager instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get the global configuration manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
    return _config_manager


def init_config_manager(db_path: Optional[Path] = None) -> ConfigManager:
    """Initialize the global configuration manager."""
    global _config_manager
    _config_manager = ConfigManager(db_path)
    return _config_manager


# Convenience functions for common configuration operations
def get_config(key: str, default=None, scope: Optional[str] = None) -> Any:
    """Get a configuration value."""
    return get_config_manager().get(key, default, scope)


def set_config(key: str, value: Any, scope: str = "user", persist: bool = True):
    """Set a configuration value."""
    get_config_manager().set(key, value, scope, persist)


def delete_config(key: str, scope: str):
    """Delete a configuration key."""
    get_config_manager().delete(key, scope)
