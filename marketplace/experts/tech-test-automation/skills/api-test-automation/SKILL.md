---
name: api-test-automation
description: API接口测试自动化工具，支持REST/GraphQL，包含接口测试、性能测试、契约测试、Mock服务等功能 | API Test Automation for REST/GraphQL with performance, contract testing and Mock services
homepage: https://github.com/kaiyuelv/api-test-automation
category: devops
tags:
  - api
  - testing
  - rest
  - graphql
  - pytest
  - automation
  - performance
  - mock
version: 1.0.0
---

# API Test Automation

API接口测试自动化工具，支持REST/GraphQL，包含接口测试、性能测试、契约测试、Mock服务等功能。

## 概述

本Skill提供完整的API测试解决方案，支持：
- REST API 功能测试
- GraphQL 查询测试
- 性能测试（并发、响应时间、吞吐量）
- 契约测试（OpenAPI/Swagger 验证）
- Mock 服务
- 测试报告生成

## 依赖

- Python >= 3.8
- requests >= 2.28.0
- httpx >= 0.24.0
- pytest >= 7.0.0
- pytest-asyncio >= 0.21.0
- schemathesis >= 3.19.0
- hypothesis >= 6.82.0
- aiohttp >= 3.8.0
- uvicorn >= 0.23.0
- starlette >= 0.27.0
- jsonschema >= 4.19.0
- pyyaml >= 6.0
- allure-pytest >= 2.13.0

## 文件结构

```
api-test-automation/
├── SKILL.md                  # 本文件
├── README.md                 # 使用文档
├── requirements.txt          # 依赖声明
├── examples/
│   └── run_tests.py         # 使用示例
├── tests/
│   └── test_api_suite.py    # 单元测试
└── src/
    ├── __init__.py
    ├── rest_client.py       # REST API 客户端
    ├── graphql_client.py    # GraphQL 客户端
    ├── performance.py       # 性能测试工具
    ├── contract_tester.py   # 契约测试
    ├── mock_server.py       # Mock 服务
    └── reporter.py          # 报告生成
```

## 快速开始

```python
from api_test_automation import RestClient, GraphQLClient, PerformanceTester

# REST API 测试
client = RestClient(base_url="https://api.example.com")
response = client.get("/users")
assert response.status_code == 200

# GraphQL 测试
graphql = GraphQLClient(endpoint="https://api.example.com/graphql")
result = graphql.query("{ users { id name } }")
```

## 许可证

MIT

---

# API Test Automation (English)

A comprehensive API testing automation tool supporting REST/GraphQL with functional testing, performance testing, contract testing, and Mock services.

## Overview

This Skill provides a complete API testing solution:
- REST API functional testing
- GraphQL query testing
- Performance testing (concurrency, response time, throughput)
- Contract testing (OpenAPI/Swagger validation)
- Mock services
- Test report generation

## Dependencies

- Python >= 3.8
- requests >= 2.28.0
- httpx >= 0.24.0
- pytest >= 7.0.0
- pytest-asyncio >= 0.21.0
- schemathesis >= 3.19.0
- hypothesis >= 6.82.0
- aiohttp >= 3.8.0
- uvicorn >= 0.23.0
- starlette >= 0.27.0
- jsonschema >= 4.19.0
- pyyaml >= 6.0
- allure-pytest >= 2.13.0

## File Structure

```
api-test-automation/
├── SKILL.md                  # This file
├── README.md                 # Usage documentation
├── requirements.txt          # Dependencies
├── examples/
│   └── run_tests.py         # Usage examples
├── tests/
│   └── test_api_suite.py    # Unit tests
└── src/
    ├── __init__.py
    ├── rest_client.py       # REST API client
    ├── graphql_client.py    # GraphQL client
    ├── performance.py       # Performance testing tools
    ├── contract_tester.py   # Contract testing
    ├── mock_server.py       # Mock server
    └── reporter.py          # Report generation
```

## Quick Start

```python
from api_test_automation import RestClient, GraphQLClient, PerformanceTester

# REST API Testing
client = RestClient(base_url="https://api.example.com")
response = client.get("/users")
assert response.status_code == 200

# GraphQL Testing
graphql = GraphQLClient(endpoint="https://api.example.com/graphql")
result = graphql.query("{ users { id name } }")
```

## License

MIT
