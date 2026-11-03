"""API Test Automation Package

A comprehensive API testing automation tool supporting REST/GraphQL.
"""

__version__ = "1.0.0"
__author__ = "ClawHub"

from .rest_client import RestClient, RestConfig
from .graphql_client import GraphQLClient
from .performance import PerformanceTester, PerformanceResults
from .contract_tester import ContractTester
from .mock_server import MockServer, MockRoute
from .reporter import TestReporter
from .assertions import Assertions

__all__ = [
    "RestClient",
    "RestConfig", 
    "GraphQLClient",
    "PerformanceTester",
    "PerformanceResults",
    "ContractTester",
    "MockServer",
    "MockRoute",
    "TestReporter",
    "Assertions",
]
