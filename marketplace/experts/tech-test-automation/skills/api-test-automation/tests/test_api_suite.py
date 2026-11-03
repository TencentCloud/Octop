#!/usr/bin/env python3
"""
API Test Automation - Unit Tests

Comprehensive test suite for the API Test Automation Skill.

Run with:
    pytest tests/test_api_suite.py -v
    pytest tests/test_api_suite.py -v --cov=src
    pytest tests/test_api_suite.py -v --alluredir=./allure-results
"""

import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import httpx
import requests

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rest_client import RestClient, RestConfig, AsyncRestClient
from graphql_client import GraphQLClient, GraphQLError
from performance import PerformanceTester, PerformanceResults
from mock_server import MockServer, MockRoute, MockBuilder
from reporter import TestReporter, TestReport, TestResult
from contract_tester import ContractTester, ContractValidationError
from assertions import Assertions


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def rest_config():
    """Create a test REST config."""
    return RestConfig(
        base_url="https://jsonplaceholder.typicode.com",
        timeout=30,
        retries=3
    )


@pytest.fixture
def rest_client(rest_config):
    """Create a test REST client."""
    return RestClient(rest_config)


@pytest.fixture
def graphql_client():
    """Create a test GraphQL client."""
    return GraphQLClient(
        endpoint="https://api.example.com/graphql",
        headers={"Authorization": "Bearer test-token"}
    )


@pytest.fixture
def mock_server():
    """Create and manage a mock server."""
    server = MockServer(host="127.0.0.1", port=8888)
    yield server
    server.stop()


# ============================================================
# REST Client Tests
# ============================================================

class TestRestClient:
    """Tests for REST Client."""
    
    def test_client_initialization(self, rest_config):
        """Test client initialization."""
        client = RestClient(rest_config)
        assert client.config == rest_config
        assert client.session is not None
        client.close()
    
    def test_default_config(self):
        """Test default configuration."""
        client = RestClient()
        assert client.config.base_url == ""
        assert client.config.timeout == 30
        client.close()
    
    def test_set_auth_bearer(self):
        """Test bearer token authentication."""
        client = RestClient()
        client.set_auth(token="test-token")
        assert client.session.headers["Authorization"] == "Bearer test-token"
        client.close()
    
    def test_set_auth_basic(self):
        """Test basic authentication."""
        client = RestClient()
        client.set_auth(username="user", password="pass")
        assert client.session.auth == ("user", "pass")
        client.close()
    
    def test_url_building_with_base(self):
        """Test URL building with base URL."""
        config = RestConfig(base_url="https://api.example.com")
        client = RestClient(config)
        url = client._url("/users")
        assert url == "https://api.example.com/users"
        client.close()
    
    def test_url_building_without_base(self):
        """Test URL building without base URL."""
        client = RestClient()
        url = client._url("https://api.example.com/users")
        assert url == "https://api.example.com/users"
        client.close()
    
    @patch('requests.Session.request')
    def test_get_request(self, mock_request, rest_client):
        """Test GET request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response
        
        response = rest_client.get("/posts/1")
        
        assert response.status_code == 200
        mock_request.assert_called_once()
        rest_client.close()
    
    @patch('requests.Session.request')
    def test_post_request(self, mock_request, rest_client):
        """Test POST request."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_request.return_value = mock_response
        
        data = {"title": "test"}
        response = rest_client.post("/posts", json=data)
        
        assert response.status_code == 201
        rest_client.close()
    
    @patch('requests.Session.request')
    def test_interceptors(self, mock_request, rest_client):
        """Test request/response interceptors."""
        interceptor = Mock()
        interceptor.before_request = Mock()
        interceptor.after_response = Mock()
        
        rest_client.add_interceptor(interceptor)
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response
        
        rest_client.get("/test")
        
        interceptor.before_request.assert_called_once()
        interceptor.after_response.assert_called_once()
        rest_client.close()


class TestAsyncRestClient:
    """Tests for Async REST Client."""
    
    @pytest.mark.asyncio
    async def test_async_get(self):
        """Test async GET request."""
        config = RestConfig(base_url="https://jsonplaceholder.typicode.com")
        
        async with RestClient(config).async_session() as client:
            response = await client.get("/posts/1")
            assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_async_post(self):
        """Test async POST request."""
        config = RestConfig(base_url="https://jsonplaceholder.typicode.com")
        
        async with RestClient(config).async_session() as client:
            data = {"title": "test", "body": "content", "userId": 1}
            response = await client.post("/posts", json=data)
            assert response.status_code == 201
    
    @pytest.mark.asyncio
    async def test_concurrent_requests(self):
        """Test concurrent async requests."""
        config = RestConfig(base_url="https://jsonplaceholder.typicode.com")
        
        async with RestClient(config).async_session() as client:
            tasks = [
                client.get("/posts/1"),
                client.get("/posts/2"),
                client.get("/posts/3"),
            ]
            responses = await asyncio.gather(*tasks)
            
            assert all(r.status_code == 200 for r in responses)


# ============================================================
# GraphQL Client Tests
# ============================================================

class TestGraphQLClient:
    """Tests for GraphQL Client."""
    
    def test_initialization(self, graphql_client):
        """Test client initialization."""
        assert graphql_client.endpoint == "https://api.example.com/graphql"
        assert graphql_client.headers["Content-Type"] == "application/json"
    
    def test_set_auth(self, graphql_client):
        """Test authentication."""
        graphql_client.set_auth("new-token")
        assert graphql_client.headers["Authorization"] == "Bearer new-token"
    
    @patch('requests.post')
    def test_query_execution(self, mock_post, graphql_client):
        """Test query execution."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": {"user": {"id": "1", "name": "Test"}}}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        query = "{ user { id name } }"
        result = graphql_client.query(query)
        
        assert result["user"]["name"] == "Test"
        mock_post.assert_called_once()
    
    @patch('requests.post')
    def test_query_with_variables(self, mock_post, graphql_client):
        """Test query with variables."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": {"user": {"id": "123"}}}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        query = "query GetUser($id: ID!) { user(id: $id) { id } }"
        result = graphql_client.query(query, variables={"id": "123"})
        
        assert result["user"]["id"] == "123"
    
    @patch('requests.post')
    def test_mutation(self, mock_post, graphql_client):
        """Test mutation execution."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": {"createUser": {"id": "1"}}}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        mutation = "mutation { createUser { id } }"
        result = graphql_client.mutate(mutation)
        
        assert result["createUser"]["id"] == "1"
    
    @patch('requests.post')
    def test_graphql_error(self, mock_post, graphql_client):
        """Test GraphQL error handling."""
        mock_response = Mock()
        mock_response.json.return_value = {"errors": [{"message": "User not found"}]}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        with pytest.raises(GraphQLError) as exc_info:
            graphql_client.query("{ user { id } }")
        
        assert "User not found" in str(exc_info.value)
    
    def test_validate_valid_query(self, graphql_client):
        """Test valid query validation."""
        valid_queries = [
            "{ users { id } }",
            "query GetUsers { users { id } }",
            "mutation CreateUser { createUser { id } }",
            "subscription UserUpdates { user { id } }"
        ]
        
        for query in valid_queries:
            assert graphql_client.validate_query(query) is True
    
    def test_validate_invalid_query(self, graphql_client):
        """Test invalid query validation."""
        invalid_queries = [
            "",
            "not a query",
            "SELECT * FROM users"
        ]
        
        for query in invalid_queries:
            assert graphql_client.validate_query(query) is False


# ============================================================
# Performance Testing Tests
# ============================================================

class TestPerformanceTester:
    """Tests for Performance Tester."""
    
    @pytest.mark.asyncio
    async def test_load_test(self):
        """Test load testing."""
        tester = PerformanceTester(
            base_url="https://jsonplaceholder.typicode.com",
            concurrency=5
        )
        
        async def scenario():
            async with httpx.AsyncClient() as client:
                response = await client.get("https://jsonplaceholder.typicode.com/posts/1")
                return response.status_code == 200
        
        results = await tester.run_load_test(scenario, total_requests=10)
        
        assert results.total_requests == 10
        assert results.successful_requests > 0
        assert isinstance(results.throughput, float)
    
    def test_performance_results(self):
        """Test performance results calculation."""
        results = PerformanceResults()
        results.total_requests = 100
        results.successful_requests = 95
        results.failed_requests = 5
        results.total_time = 10.0
        results.response_times = [0.1, 0.2, 0.3, 0.4, 0.5]
        
        assert results.error_rate == 5.0
        assert results.throughput == 10.0
        
        percentiles = results.percentiles
        assert "p50" in percentiles
        assert "p90" in percentiles
    
    def test_performance_results_empty(self):
        """Test empty performance results."""
        results = PerformanceResults()
        
        assert results.throughput == 0.0
        assert results.error_rate == 0.0
        assert results.percentiles == {}


# ============================================================
# Mock Server Tests
# ============================================================

class TestMockServer:
    """Tests for Mock Server."""
    
    def test_initialization(self):
        """Test server initialization."""
        server = MockServer(host="127.0.0.1", port=9999)
        assert server.host == "127.0.0.1"
        assert server.port == 9999
        assert len(server.routes) == 0
    
    def test_add_route(self):
        """Test adding routes."""
        server = MockServer()
        route = MockRoute().method("GET").path("/test").response(200, {"test": True})
        
        server.add_route(route)
        
        assert len(server.routes) == 1
    
    def test_add_json_endpoint(self):
        """Test adding JSON endpoint."""
        server = MockServer()
        server.add_json_endpoint("/users", [{"id": 1}], method="GET", status=200)
        
        assert len(server.routes) == 1
        assert server.routes[0].path == "/users"
    
    def test_route_matching(self):
        """Test route matching."""
        route = MockRoute().method("GET").path("/users")
        
        assert route.match("GET", "/users") is True
        assert route.match("POST", "/users") is False
        assert route.match("GET", "/posts") is False
    
    def test_mock_route_builder(self):
        """Test mock route builder pattern."""
        route = (
            MockRoute()
            .method("POST")
            .path("/api/users")
            .response(201, {"id": 1})
            .delay(0.1)
        )
        
        assert route.method == "POST"
        assert route.path == "/api/users"
        assert route.response_status == 201
        assert route.delay == 0.1


# ============================================================
# Reporter Tests
# ============================================================

class TestReporter:
    """Tests for Test Reporter."""
    
    def test_initialization(self, tmp_path):
        """Test reporter initialization."""
        reporter = TestReporter(output_dir=str(tmp_path))
        assert reporter.output_dir == tmp_path
    
    def test_generate_html_report(self, tmp_path):
        """Test HTML report generation."""
        reporter = TestReporter(output_dir=str(tmp_path))
        
        results = [
            TestResult(name="test1", status="passed", duration=0.1),
            TestResult(name="test2", status="failed", duration=0.2, message="Error"),
        ]
        report = TestReport(timestamp=datetime.now(), results=results, total_duration=0.3)
        
        path = reporter.generate_html_report(report, "test.html")
        
        assert Path(path).exists()
        content = Path(path).read_text()
        assert "test1" in content
        assert "passed" in content
    
    def test_generate_json_report(self, tmp_path):
        """Test JSON report generation."""
        reporter = TestReporter(output_dir=str(tmp_path))
        
        results = [
            TestResult(name="test1", status="passed", duration=0.1),
        ]
        report = TestReport(timestamp=datetime.now(), results=results)
        
        path = reporter.generate_json_report(report, "test.json")
        
        assert Path(path).exists()
        data = json.loads(Path(path).read_text())
        assert data["summary"]["total"] == 1
        assert data["tests"][0]["name"] == "test1"
    
    def test_generate_junit_xml(self, tmp_path):
        """Test JUnit XML report generation."""
        reporter = TestReporter(output_dir=str(tmp_path))
        
        results = [
            TestResult(name="test1", status="passed", duration=0.1),
            TestResult(name="test2", status="failed", duration=0.2, message="Error"),
        ]
        report = TestReport(timestamp=datetime.now(), results=results)
        
        path = reporter.generate_junit_xml(report, "test.xml")
        
        assert Path(path).exists()
        content = Path(path).read_text()
        assert "test1" in content
        assert "failure" in content


class TestTestReport:
    """Tests for Test Report."""
    
    def test_report_calculations(self):
        """Test report calculations."""
        results = [
            TestResult(name="t1", status="passed"),
            TestResult(name="t2", status="passed"),
            TestResult(name="t3", status="failed"),
            TestResult(name="t4", status="skipped"),
        ]
        report = TestReport(timestamp=datetime.now(), results=results)
        
        assert report.total == 4
        assert report.passed == 2
        assert report.failed == 1
        assert report.skipped == 1
        assert report.pass_rate == 50.0


# ============================================================
# Contract Testing Tests
# ============================================================

class TestContractTester:
    """Tests for Contract Tester."""
    
    def test_from_openapi(self, tmp_path):
        """Test loading from OpenAPI file."""
        openapi = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/users": {
                    "get": {
                        "operationId": "getUsers",
                        "responses": {
                            "200": {"description": "OK"}
                        }
                    }
                }
            }
        }
        
        openapi_path = tmp_path / "openapi.json"
        openapi_path.write_text(json.dumps(openapi))
        
        tester = ContractTester.from_openapi(str(openapi_path))
        
        assert tester.schema is not None
    
    def test_validate_endpoint(self):
        """Test endpoint validation."""
        schema = {
            "paths": {
                "/users": {
                    "get": {"operationId": "getUsers"}
                }
            }
        }
        tester = ContractTester(schema=schema)
        
        assert tester.validate_endpoint("/users", "GET") is True
        
        with pytest.raises(ValueError):
            tester.validate_endpoint("/posts", "GET")
        
        with pytest.raises(ValueError):
            tester.validate_endpoint("/users", "POST")
    
    def test_validate_response(self):
        """Test response validation."""
        schema = {
            "components": {
                "schemas": {
                    "User": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "name": {"type": "string"}
                        },
                        "required": ["id", "name"]
                    }
                }
            }
        }
        tester = ContractTester(schema=schema)
        
        valid_data = {"id": 1, "name": "Test"}
        assert tester.validate_response(valid_data, schema_ref="User") is True
        
        invalid_data = {"id": "not-an-integer"}
        with pytest.raises(ContractValidationError):
            tester.validate_response(invalid_data, schema_ref="User")
    
    def test_generate_test_data(self):
        """Test test data generation."""
        schema = {
            "components": {
                "schemas": {
                    "User": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "name": {"type": "string"},
                            "email": {"type": "string", "format": "email"}
                        }
                    }
                }
            }
        }
        tester = ContractTester(schema=schema)
        
        data = tester.generate_test_data("User", count=2)
        
        assert len(data) == 2
        assert "id" in data[0]
        assert "name" in data[0]
        assert data[0]["email"] == "test@example.com"
    
    def test_extract_endpoints(self):
        """Test endpoint extraction."""
        schema = {
            "paths": {
                "/users": {
                    "get": {"operationId": "listUsers", "summary": "List users"},
                    "post": {"operationId": "createUser"}
                }
            }
        }
        tester = ContractTester(schema=schema)
        
        endpoints = tester.extract_endpoints()
        
        assert len(endpoints) == 2
        assert any(e["path"] == "/users" and e["method"] == "GET" for e in endpoints)
        assert any(e["path"] == "/users" and e["method"] == "POST" for e in endpoints)


# ============================================================
# Assertions Tests
# ============================================================

class TestAssertions:
    """Tests for Assertions."""
    
    def test_assert_status_code_single(self):
        """Test status code assertion with single code."""
        response = Mock()
        response.status_code = 200
        
        Assertions.assert_status_code(response, 200)  # Should not raise
        
        with pytest.raises(AssertionError):
            Assertions.assert_status_code(response, 201)
    
    def test_assert_status_code_multiple(self):
        """Test status code assertion with multiple codes."""
        response = Mock()
        response.status_code = 201
        
        Assertions.assert_status_code(response, [200, 201])  # Should not raise
        
        with pytest.raises(AssertionError):
            Assertions.assert_status_code(response, [200, 202])
    
    def test_assert_ok(self):
        """Test OK assertion."""
        response = Mock()
        response.status_code = 200
        
        Assertions.assert_ok(response)  # Should not raise
        
        response.status_code = 400
        with pytest.raises(AssertionError):
            Assertions.assert_ok(response)
    
    def test_assert_json_content_type(self):
        """Test JSON content type assertion."""
        response = Mock()
        response.headers = {"content-type": "application/json"}
        
        Assertions.assert_json_content_type(response)  # Should not raise
        
        response.headers = {"content-type": "text/html"}
        with pytest.raises(AssertionError):
            Assertions.assert_json_content_type(response)
    
    def test_assert_json_contains(self):
        """Test JSON contains assertion."""
        response = Mock()
        response.json.return_value = {"id": 1, "name": "Test"}
        
        Assertions.assert_json_contains(response, "id")  # Should not raise
        
        with pytest.raises(AssertionError):
            Assertions.assert_json_contains(response, "nonexistent")
    
    def test_assert_json_path(self):
        """Test JSON path assertion."""
        response = Mock()
        response.json.return_value = {"user": {"id": 1, "name": "Test"}}
        
        Assertions.assert_json_path(response, "user.name", "Test")  # Should not raise
        
        with pytest.raises(AssertionError):
            Assertions.assert_json_path(response, "user.name", "Wrong")
    
    def test_assert_header_contains(self):
        """Test header contains assertion."""
        response = Mock()
        response.headers = {"content-type": "application/json; charset=utf-8"}
        
        Assertions.assert_header_contains(response, "content-type", "json")  # Should not raise
        
        with pytest.raises(AssertionError):
            Assertions.assert_header_contains(response, "content-type", "xml")
    
    def test_assert_not_empty(self):
        """Test not empty assertion."""
        response = Mock()
        response.json.return_value = {"users": [1, 2, 3]}
        
        Assertions.assert_not_empty(response, "users")  # Should not raise
        
        response.json.return_value = {"users": []}
        with pytest.raises(AssertionError):
            Assertions.assert_not_empty(response, "users")


# ============================================================
# Integration Tests
# ============================================================

@pytest.mark.integration
class TestIntegration:
    """Integration tests against real APIs."""
    
    def test_real_api_get(self):
        """Test GET against real API."""
        config = RestConfig(base_url="https://jsonplaceholder.typicode.com")
        client = RestClient(config)
        
        try:
            response = client.get("/posts/1")
            Assertions.assert_status_code(response, 200)
            Assertions.assert_json_contains(response, "title")
        finally:
            client.close()
    
    @pytest.mark.asyncio
    async def test_real_api_async(self):
        """Test async requests against real API."""
        config = RestConfig(base_url="https://jsonplaceholder.typicode.com")
        
        async with RestClient(config).async_session() as client:
            response = await client.get("/posts/1")
            assert response.status_code == 200
            data = response.json()
            assert "id" in data


# ============================================================
# Run Tests
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
