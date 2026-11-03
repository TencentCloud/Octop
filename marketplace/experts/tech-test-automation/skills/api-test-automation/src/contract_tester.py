"""Contract Testing Module

Provides OpenAPI/Swagger contract validation and schema testing.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import schemathesis
import yaml
from jsonschema import validate, ValidationError


class ContractTester:
    """Contract testing for API validation."""
    
    def __init__(self, schema: Optional[Dict[str, Any]] = None, schema_path: Optional[str] = None):
        self.schema = schema
        self.schema_path = schema_path
        
        if schema_path and not schema:
            self.schema = self._load_schema(schema_path)
    
    @classmethod
    def from_openapi(cls, path: str) -> "ContractTester":
        """Create tester from OpenAPI specification file."""
        return cls(schema_path=path)
    
    def _load_schema(self, path: str) -> Dict[str, Any]:
        """Load schema from file."""
        path = Path(path)
        with open(path, 'r') as f:
            if path.suffix in ['.yaml', '.yml']:
                return yaml.safe_load(f)
            return json.load(f)
    
    def validate_endpoint(self, path: str, method: str = "GET", 
                         response_schema: Optional[Dict] = None) -> bool:
        """Validate API endpoint against schema."""
        if not self.schema:
            raise ValueError("No schema provided")
        
        # Find path in schema
        paths = self.schema.get("paths", {})
        if path not in paths:
            raise ValueError(f"Path {path} not found in schema")
        
        path_item = paths[path]
        if method.lower() not in [m.lower() for m in path_item.keys()]:
            raise ValueError(f"Method {method} not defined for path {path}")
        
        return True
    
    def validate_response(self, response_data: Any, schema_ref: Optional[str] = None,
                         schema: Optional[Dict] = None) -> bool:
        """Validate response data against JSON schema."""
        validation_schema = schema or self._resolve_schema_ref(schema_ref)
        if not validation_schema:
            raise ValueError("No schema provided for validation")
        
        try:
            validate(instance=response_data, schema=validation_schema)
            return True
        except ValidationError as e:
            raise ContractValidationError(f"Response validation failed: {e.message}")
    
    def _resolve_schema_ref(self, ref: Optional[str]) -> Optional[Dict]:
        """Resolve schema reference."""
        if not ref or not self.schema:
            return None
        
        components = self.schema.get("components", {}).get("schemas", {})
        if ref.startswith("#/components/schemas/"):
            schema_name = ref.split("/")[-1]
            return components.get(schema_name)
        return components.get(ref)
    
    def run_schemathesis_tests(self, base_url: str, checks: Optional[List[str]] = None) -> Any:
        """Run automated Schemathesis tests."""
        if not self.schema:
            raise ValueError("No schema provided")
        
        # Create Schemathesis schema
        schema = schemathesis.from_dict(self.schema, base_url=base_url)
        
        # Run tests
        @schema.parametrize()
        def test_api(case):
            case.call_and_validate()
        
        return test_api
    
    def generate_test_data(self, schema_ref: str, count: int = 1) -> List[Dict]:
        """Generate test data based on schema."""
        schema = self._resolve_schema_ref(schema_ref)
        if not schema:
            raise ValueError(f"Schema reference {schema_ref} not found")
        
        data = []
        for _ in range(count):
            data.append(self._generate_from_schema(schema))
        return data
    
    def _generate_from_schema(self, schema: Dict) -> Any:
        """Generate data from JSON schema."""
        schema_type = schema.get("type", "object")
        
        if schema_type == "object":
            result = {}
            properties = schema.get("properties", {})
            for prop, prop_schema in properties.items():
                result[prop] = self._generate_from_schema(prop_schema)
            return result
        
        elif schema_type == "array":
            item_schema = schema.get("items", {})
            return [self._generate_from_schema(item_schema)]
        
        elif schema_type == "string":
            if "enum" in schema:
                return schema["enum"][0]
            if schema.get("format") == "email":
                return "test@example.com"
            if schema.get("format") == "date":
                return "2024-01-01"
            if schema.get("format") == "date-time":
                return "2024-01-01T00:00:00Z"
            return "string"
        
        elif schema_type == "integer":
            minimum = schema.get("minimum", 0)
            return minimum
        
        elif schema_type == "number":
            return 0.0
        
        elif schema_type == "boolean":
            return True
        
        return None
    
    def extract_endpoints(self) -> List[Dict[str, str]]:
        """Extract all endpoints from OpenAPI schema."""
        if not self.schema:
            return []
        
        endpoints = []
        paths = self.schema.get("paths", {})
        
        for path, methods in paths.items():
            for method in methods.keys():
                if method.lower() not in ["get", "post", "put", "patch", "delete"]:
                    continue
                endpoints.append({
                    "path": path,
                    "method": method.upper(),
                    "operation_id": methods[method].get("operationId", ""),
                    "summary": methods[method].get("summary", "")
                })
        
        return endpoints


class ContractValidationError(Exception):
    """Contract validation error."""
    pass
