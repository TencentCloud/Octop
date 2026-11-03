"""GraphQL Client Module

Provides GraphQL query and mutation support.
"""

import json
from typing import Any, Dict, Optional

import httpx
import requests


class GraphQLClient:
    """GraphQL Client for API testing."""
    
    def __init__(self, endpoint: str, headers: Optional[Dict[str, str]] = None):
        self.endpoint = endpoint
        self.headers = headers or {}
        self.headers.setdefault("Content-Type", "application/json")
        
    def set_auth(self, token: str):
        """Set authentication token."""
        self.headers["Authorization"] = f"Bearer {token}"
    
    def query(self, query: str, variables: Optional[Dict[str, Any]] = None,
              operation_name: Optional[str] = None) -> Dict[str, Any]:
        """Execute GraphQL query synchronously."""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        if operation_name:
            payload["operationName"] = operation_name
            
        response = requests.post(
            self.endpoint,
            headers=self.headers,
            json=payload
        )
        response.raise_for_status()
        
        result = response.json()
        if "errors" in result:
            raise GraphQLError(result["errors"])
        
        return result.get("data", {})
    
    async def query_async(self, query: str, variables: Optional[Dict[str, Any]] = None,
                          operation_name: Optional[str] = None) -> Dict[str, Any]:
        """Execute GraphQL query asynchronously."""
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        if operation_name:
            payload["operationName"] = operation_name
            
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.endpoint,
                headers=self.headers,
                json=payload
            )
            response.raise_for_status()
            
            result = response.json()
            if "errors" in result:
                raise GraphQLError(result["errors"])
            
            return result.get("data", {})
    
    def mutate(self, mutation: str, variables: Optional[Dict[str, Any]] = None,
               operation_name: Optional[str] = None) -> Dict[str, Any]:
        """Execute GraphQL mutation."""
        return self.query(mutation, variables, operation_name)
    
    async def mutate_async(self, mutation: str, variables: Optional[Dict[str, Any]] = None,
                           operation_name: Optional[str] = None) -> Dict[str, Any]:
        """Execute GraphQL mutation asynchronously."""
        return await self.query_async(mutation, variables, operation_name)
    
    def introspect(self) -> Dict[str, Any]:
        """Get GraphQL schema introspection."""
        introspection_query = """
        {
          __schema {
            queryType { name }
            mutationType { name }
            subscriptionType { name }
            types {
              name
              kind
              fields {
                name
                type {
                  name
                  kind
                }
              }
            }
          }
        }
        """
        return self.query(introspection_query)
    
    def validate_query(self, query: str) -> bool:
        """Validate if query is syntactically correct."""
        try:
            # Basic syntax validation
            query = query.strip()
            if not query:
                return False
            if not (query.startswith("query") or query.startswith("mutation") 
                    or query.startswith("subscription") or query.startswith("{")):
                return False
            return True
        except Exception:
            return False


class GraphQLError(Exception):
    """GraphQL error exception."""
    
    def __init__(self, errors):
        self.errors = errors
        message = errors[0].get("message", "Unknown GraphQL error") if errors else "GraphQL error"
        super().__init__(message)
