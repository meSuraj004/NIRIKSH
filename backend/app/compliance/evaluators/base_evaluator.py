"""
Base class for deterministic parameter evaluators.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from ..models import RuleDefinition, ParameterEvaluationResult, ProductDataInput


class BaseParameterEvaluator(ABC):
    """Abstract base class for evaluating a specific statutory parameter."""

    def __init__(self, rule_definition: RuleDefinition):
        self.rule = rule_definition

    @abstractmethod
    def evaluate(self, product_data: ProductDataInput, context: Optional[Dict[str, Any]] = None) -> ParameterEvaluationResult:
        """
        Evaluates input product data against the rule definition.
        Returns a deterministic ParameterEvaluationResult.
        """
        pass
