# API Test Automation Skill

一个功能强大的API测试自动化工具，支持REST API和GraphQL的全面测试。

## 功能特性

### 1. REST API 测试
- 同步/异步 HTTP 请求
- 自动重试机制
- 请求/响应拦截器
- Cookie 和 Session 管理
- 自定义 headers 和认证

### 2. GraphQL 测试
- Query 和 Mutation 支持
- 变量传递
- 片段(Fragments)支持
- 内省(Introspection)查询
- 订阅(Subscription)测试

### 3. 性能测试
- 并发请求测试
- 负载测试
- 响应时间统计
- 吞吐量分析
- 压力测试报告

### 4. 契约测试
- OpenAPI/Swagger 验证
- JSON Schema 验证
- 自动化边界测试
- 数据生成

### 5. Mock 服务
- 快速启动 Mock 服务器
- 动态响应配置
- 请求记录和验证
- 延迟模拟

### 6. 测试报告
- HTML 报告生成
- Allure 集成
- JUnit XML 输出
- 自定义报告模板

## 安装

```bash
# 安装依赖
pip install -r requirements.txt
```

## 使用示例

### REST API 测试

```python
from api_test_automation import RestClient, RestConfig

# 创建客户端
config = RestConfig(
    base_url="https://jsonplaceholder.typicode.com",
    timeout=30,
    retries=3
)
client = RestClient(config)

# GET 请求
response = client.get("/posts/1")
print(response.json())

# POST 请求
data = {"title": "foo", "body": "bar", "userId": 1}
response = client.post("/posts", json=data)
print(response.status_code)

# 使用认证
client.set_auth(token="your-api-token")
response = client.get("/protected-resource")

# 异步请求
import asyncio

async def test_async():
    async with client.async_session() as session:
        response = await session.get("/posts/1")
        return response.json()

result = asyncio.run(test_async())
```

### GraphQL 测试

```python
from api_test_automation import GraphQLClient

# 创建客户端
client = GraphQLClient(endpoint="https://api.example.com/graphql")

# Query 查询
query = """
query GetUser($id: ID!) {
    user(id: $id) {
        id
        name
        email
    }
}
"""
result = client.query(query, variables={"id": "123"})
print(result)

# Mutation 操作
mutation = """
mutation CreateUser($input: CreateUserInput!) {
    createUser(input: $input) {
        id
        name
    }
}
"""
result = client.mutate(mutation, variables={"input": {"name": "John"}})

# 内省查询
schema = client.introspect()
print(schema)
```

### 性能测试

```python
from api_test_automation import PerformanceTester

# 创建性能测试器
tester = PerformanceTester(
    base_url="https://api.example.com",
    concurrency=50,
    duration=60
)

# 定义测试场景
async def scenario():
    return await tester.client.get("/api/users")

# 运行负载测试
results = tester.run_load_test(scenario, total_requests=1000)

# 生成报告
print(f"平均响应时间: {results.avg_response_time}ms")
print(f"吞吐量: {results.throughput} req/s")
print(f"错误率: {results.error_rate}%")
```

### 契约测试

```python
from api_test_automation import ContractTester

# 从 OpenAPI 规范创建测试
tester = ContractTester.from_openapi("openapi.yaml")

# 验证端点
tester.validate_endpoint("/users", method="GET")

# 使用 Schemathesis 进行自动化测试
tester.run_schemathesis_tests(base_url="https://api.example.com")
```

### Mock 服务

```python
from api_test_automation import MockServer, MockRoute

# 创建 Mock 服务器
server = MockServer(port=8080)

# 添加路由
server.add_route(
    MockRoute()
    .method("GET")
    .path("/api/users")
    .response(200, {"users": [{"id": 1, "name": "Alice"}]})
    .delay(0.1)
)

server.add_route(
    MockRoute()
    .method("POST")
    .path("/api/users")
    .response(201, {"id": 2, "name": "Bob"})
)

# 启动服务器
server.start()

# 使用 Mock 进行测试
# ... 你的测试代码 ...

# 停止服务器
server.stop()
```

### 测试报告

```python
from api_test_automation import TestReporter

# 创建报告器
reporter = TestReporter(output_dir="./reports")

# 生成 HTML 报告
reporter.generate_html_report(test_results)

# 生成 Allure 报告
reporter.generate_allure_report(test_results)

# 生成 JUnit XML
reporter.generate_junit_xml(test_results)
```

## 运行测试

```bash
# 运行所有测试
pytest tests/

# 运行特定测试
pytest tests/test_api_suite.py -v

# 生成 Allure 报告
pytest tests/ --alluredir=./allure-results
allure serve ./allure-results
```

## 配置文件

可以使用 YAML 文件配置测试：

```yaml
# api-config.yaml
base_url: https://api.example.com
auth:
  type: bearer
  token: ${API_TOKEN}
endpoints:
  - name: get_users
    path: /users
    method: GET
    expected_status: 200
  - name: create_user
    path: /users
    method: POST
    expected_status: 201
performance:
  concurrency: 50
  duration: 60
  ramp_up: 10
```

## 进阶用法

### 自定义请求拦截器

```python
from api_test_automation import RestClient

class LoggingInterceptor:
    def before_request(self, request):
        print(f"Request: {request.method} {request.url}")
    
    def after_response(self, response):
        print(f"Response: {response.status_code}")

client = RestClient()
client.add_interceptor(LoggingInterceptor())
```

### 数据驱动测试

```python
import pytest
from api_test_automation import RestClient

client = RestClient(base_url="https://api.example.com")

@pytest.mark.parametrize("user_id,expected_name", [
    (1, "Alice"),
    (2, "Bob"),
    (3, "Charlie"),
])
def test_get_user(user_id, expected_name):
    response = client.get(f"/users/{user_id}")
    assert response.json()["name"] == expected_name
```

### 断言工具

```python
from api_test_automation import Assertions

response = client.get("/api/users")

# JSON 断言
Assertions.assert_json_contains(response, "users")
Assertions.assert_json_path(response, "$.users[0].name", "Alice")

# Schema 断言
Assertions.assert_json_schema(response, user_schema)

# Header 断言
Assertions.assert_header_contains(response, "content-type", "application/json")
```

## 许可证

MIT License
