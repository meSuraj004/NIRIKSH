"""
Rule Repository Interface and JSON implementation.
Provides an abstraction layer for loading and querying rules, designed to be swapped
with SQLiteRuleRepository or PostgresRuleRepository without modifying engine logic.
"""

import json
import os
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from .models import RuleBook, RuleDefinition


class RuleRepository(ABC):
    """Abstract interface for rule storage and retrieval."""

    @abstractmethod
    def load_rulebook(self) -> RuleBook:
        """Loads and returns the active rulebook."""
        pass

    @abstractmethod
    def get_rule_by_id(self, rule_id: str) -> Optional[RuleDefinition]:
        """Retrieves a specific rule by ID."""
        pass

    @abstractmethod
    def get_rules_by_parameter(self, parameter: str) -> List[RuleDefinition]:
        """Retrieves all rules applicable to a specific parameter (e.g. mrp, manufacture_date, expiry_date)."""
        pass


class JSONRuleRepository(RuleRepository):
    """
    JSON-backed repository for LMPC 2011 rules.
    Reads rule definitions directly from structured JSON rulebooks.
    """

    def __init__(self, json_file_path: Optional[str] = None):
        if json_file_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            json_file_path = os.path.join(base_dir, "rules", "rulebook_lmpc_2011.json")
        self.file_path = json_file_path
        self._cached_rulebook: Optional[RuleBook] = None
        self._rules_by_id: Dict[str, RuleDefinition] = {}
        self._rules_by_param: Dict[str, List[RuleDefinition]] = {}
        self._load()

    def _load(self):
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Rulebook JSON not found at: {self.file_path}")
        with open(self.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self._cached_rulebook = RuleBook(**data)
        self._rules_by_id = {r.rule_id: r for r in self._cached_rulebook.rules}
        self._rules_by_param = {}
        for r in self._cached_rulebook.rules:
            self._rules_by_param.setdefault(r.parameter.lower(), []).append(r)

    def load_rulebook(self) -> RuleBook:
        if self._cached_rulebook is None:
            self._load()
        return self._cached_rulebook

    def get_rule_by_id(self, rule_id: str) -> Optional[RuleDefinition]:
        if not self._rules_by_id:
            self._load()
        return self._rules_by_id.get(rule_id)

    def get_rules_by_parameter(self, parameter: str) -> List[RuleDefinition]:
        if not self._rules_by_param:
            self._load()
        return self._rules_by_param.get(parameter.lower(), [])


class SQLiteRuleRepositoryStub(RuleRepository):
    """
    Stub for future SQLite / PostgreSQL database migration.
    Ready for SQL query integration when database layer is connected.
    """

    def __init__(self, db_connection_string: str):
        self.conn_str = db_connection_string

    def load_rulebook(self) -> RuleBook:
        raise NotImplementedError("SQLite / Postgres DB repository will be activated in future DB migration.")

    def get_rule_by_id(self, rule_id: str) -> Optional[RuleDefinition]:
        raise NotImplementedError("SQLite / Postgres DB repository will be activated in future DB migration.")

    def get_rules_by_parameter(self, parameter: str) -> List[RuleDefinition]:
        raise NotImplementedError("SQLite / Postgres DB repository will be activated in future DB migration.")
