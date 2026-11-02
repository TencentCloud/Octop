# Mermaid 产品图表绘制规范

> 来源：Mermaid 官方文档 + 产品经理实践（2026）
> https://mermaid.js.org/  https://www.diagrams.net/
> https://mermaid.js.org/syntax/flowchart.html  https://mermaid.js.org/syntax/sequenceDiagram.html
> https://mermaid.js.org/syntax/stateDiagram.html  https://mermaid.js.org/syntax/gantt.html
> https://mermaid.js.org/syntax/erDiagram.html  https://mermaid.js.org/syntax/userJourney.html

## 图表类型速查

| 类型 | 用途 | 语法关键词 |
|------|------|-----------|
| 流程图 | 业务流程、用户流程 | `flowchart TD/LR/BT/RL` |
| 时序图 | 系统交互、API调用 | `sequenceDiagram` |
| 状态图 | 状态流转、生命周期 | `stateDiagram-v2` |
| 类图 | 技术架构、数据模型 | `classDiagram` |
| ER图 | 数据库设计 | `erDiagram` |
| 甘特图 | 项目计划、里程碑 | `gantt` |
| 用户旅程 | 用户体验全流程 | `journey` |
| 饼图 | 占比展示 | `pie` |
| 思维导图 | 头脑风暴、功能拆解 | `mindmap` |
| 架构图 | 系统分层、微服务 | `C4Context` |

---

## 1. 流程图（flowchart）

### 基本语法

```mermaid
flowchart TD
    A[开始] --> B{决策}
    B -->|是| C[操作1]
    B -->|否| D[操作2]
    C --> E{再次决策}
    E -->|完成| F[结束]
    E -->|失败| G[错误处理]
    D --> F
```

### 方向指令

| 方向 | 说明 | 适用场景 |
|------|------|---------|
| TD / TB | 从上到下 | 最常用 |
| BT | 从下到上 | 流程反向时 |
| LR | 从左到右 | 横向流程 |
| RL | 从右到左 | 横向反向 |

### 节点形状

| 形状 | 语法 | 用途 |
|------|------|------|
| 圆角矩形 | `[文字]` | 开始/结束 |
| 矩形 | `[文字]` | 普通步骤 |
| 菱形 | `{决策}` | 判断节点 |
| 圆柱形 | `[(数据库)]` | 数据存储 |
| 圆形 | `((圆形))` | 关键节点 |
| 六边形 | `{{六边形}}` | 准备/判断 |
| 并行四边形 | `[/平行四边形/]` | 输入/输出 |
| 子程序 | `[[子程序]]` | 子流程 |

### 连接线样式

| 样式 | 语法 | 用途 |
|------|------|------|
| 带箭头 | `-->` | 正常流向 |
| 虚线 | `-.-` | 弱关联/可选 |
| 加粗 | `==>` | 强调/主要路径 |
| 带标签 | `-->\|标签\|` | 标注条件 |
| 开放箭头 | `-->>` | 快速/异步 |

### 示例：用户登录流程

```mermaid
flowchart TD
    subgraph 登录流程
        A([开始]) --> B[/输入用户名密码/]
        B --> C{验证格式?}
        C -->|格式错误| D[显示格式错误提示]
        D --> B
        C -->|格式正确| E[调用登录接口]
        E --> F{登录成功?}
        F -->|失败| G[显示错误信息]
        G --> B
        F -->|成功| H[跳转首页]
        H --> I([结束])
    end
```

### 示例：订单处理流程

```mermaid
flowchart LR
    A[用户下单] --> B{库存充足?}
    B -->|是| C[锁定库存]
    B -->|否| D[提示库存不足]
    D --> Z[结束]
    C --> E[计算运费]
    E --> F{使用优惠券?}
    F -->|是| G[应用优惠]
    F -->|否| H[原价计算]
    G --> I[生成订单]
    H --> I
    I --> J[选择支付方式]
    J --> K{支付成功?}
    K -->|成功| L[扣减库存]
    K -->|失败| M[释放库存]
    M --> N[提示支付失败]
    N --> J
    L --> O[发送通知]
    O --> P([订单完成])
```

---

## 2. 时序图（sequenceDiagram）

### 基本语法

```mermaid
sequenceDiagram
    participant U as 用户
    participant A as 前端
    participant B as 后端
    participant D as 数据库

    U->>A: 操作
    A->>B: 请求
    B->>D: 查询
    D-->>B: 返回结果
    B-->>A: 响应
    A-->>U: 显示结果
```

### 箭头类型

| 箭头 | 含义 |
|------|------|
| `->` | 同步请求 |
| `->>` | 同步请求（带箭头） |
| `-->` | 同步返回 |
| `-->>` | 异步返回 |
| `-)` | 异步消息（虚线箭头） |

### 示例：用户注册时序图

```mermaid
sequenceDiagram
    participant U as 用户
    participant FE as 前端
    participant BE as 后端服务
    participant DB as 数据库
    participant SMS as 短信服务
    participant EM as 邮件服务

    U->>FE: 填写注册信息
    FE->>BE: POST /api/register
    BE->>DB: 查询是否已注册
    DB-->>BE: 返回结果

    alt 已注册
        BE-->>FE: 错误：手机号已注册
        FE-->>U: 显示错误提示
    else 未注册
        BE->>DB: 创建用户记录
        DB-->>BE: 返回用户ID
        BE->>SMS: 发送验证码
        SMS-->>BE: 发送成功
        BE->>EM: 发送欢迎邮件
        EM-->>BE: 发送成功
        BE-->>FE: 注册成功
        FE-->>U: 跳转验证页
    end
```

---

## 3. 状态图（stateDiagram-v2）

### 基本语法

```mermaid
stateDiagram-v2
    [*] --> 状态1
    状态1 --> 状态2: 事件/条件
    状态2 --> [*]: 完成
```

### 示例：订单状态流转

```mermaid
stateDiagram-v2
    [*] --> 待支付
    待支付 --> 已取消: 用户取消/超时
    待支付 --> 待发货: 支付成功
    待发货 --> 配送中: 商家发货
    配送中 --> 待收货: 确认收货
    待收货 --> 已完成: 用户确认
    待收货 --> 退货中: 申请退货
    退货中 --> 已退款: 退款成功
    已完成 --> [*]
    已取消 --> [*]
    已退款 --> [*]
```

### 示例：工单状态机

```mermaid
stateDiagram-v2
    [*] --> 待受理
    待受理 --> 处理中: 客服接单
    处理中 --> 待审核: 处理完成
    待审核 --> 处理中: 驳回重处理
    待审核 --> 已解决: 主管审核通过
    已解决 --> [*]
    处理中 --> 已关闭: 用户满意关闭
    待受理 --> 已关闭: 用户撤诉
```

---

## 4. 甘特图（gantt）

### 基本语法

```mermaid
gantt
    title 项目计划
    dateFormat YYYY-MM-DD
    section 阶段一
    任务1            :a1, 2026-01-01, 30d
    任务2            :a2, after a1, 20d
    section 阶段二
    任务3            :a3, after a2, 25d
    任务4            :a4, 2026-03-15, 15d
```

### 示例：产品迭代计划

```mermaid
gantt
    title 产品v2.0迭代计划
    dateFormat  YYYY-MM-DD
    section 产品设计
    需求调研       :d1, 2026-01-01, 14d
    竞品分析       :d2, 2026-01-08, 7d
    PRD撰写        :d3, 2026-01-15, 10d
    PRD评审        :d4, 2026-01-25, 5d
    section 开发
    技术方案设计   :d5, 2026-01-20, 10d
    核心功能开发   :d6, 2026-02-01, 30d
    辅助功能开发   :d7, 2026-03-01, 15d
    section 测试
    测试用例编写   :d8, 2026-02-01, 10d
    功能测试       :d9, 2026-03-01, 20d
    回归测试       :d10, 2026-03-20, 7d
    section 上线
    灰度发布       :d11, 2026-03-28, 3d
    全量发布       :d12, 2026-03-31, 2d
    section 运营
    上线后监控     :d13, 2026-04-01, 14d
```

---

## 5. 用户旅程（journey）

```mermaid
journey
    title 用户购物流程
    section 购物流程
      搜索商品: 5: 用户
      浏览详情: 3: 用户
      加入购物车: 5: 用户
      结算: 4: 用户
      选择地址: 3: 用户
      选择支付: 4: 用户
      支付: 3: 用户
      下单成功: 5: 用户
```

---

## 6. 饼图（pie）

```mermaid
pie title 功能开发工作量分布
    "前端开发" : 35
    "后端开发" : 40
    "测试" : 15
    "运维/部署" : 10
```

---

## 7. 架构图（C4Context）

### 安装与使用

C4 模型是一种软件架构可视化方法，用 4 个层级描述系统：
- **Context（上下文）** - 系统与外部交互者
- **Container（容器）** - 应用和技术组件
- **Component（组件）** - 容器的核心组件
- **Code（代码）** - 组件的具体实现

```mermaid
C4Context
    title 系统上下文

    Person(customer, "用户", "使用移动端和Web端")
    Person(admin, "管理员", "管理系统")
    System_Boundary(sb, "产品系统") {
        System(mobile, "移动App", "React Native")
        System(web, "Web管理后台", "Vue.js")
        System(api, "API网关", "Kong")
        System_Boundary(core, "核心服务") {
            System(order, "订单服务", "Java微服务")
            System(user, "用户服务", "Java微服务")
            System(pay, "支付服务", "Java微服务")
        }
        SystemDb(db, "数据库集群", "MySQL主从")
        System(cache, "缓存", "Redis集群")
        System(mq, "消息队列", "Kafka")
    }

    customer --> mobile: 使用
    customer --> web: 使用
    admin --> web: 管理
    mobile --> api: 调用
    web --> api: 调用
    api --> order: 调用
    api --> user: 调用
    api --> pay: 调用
    order --> db: 读写
    user --> db: 读写
    pay --> db: 读写
    order --> cache: 缓存
    order --> mq: 发布事件
```

---

## 8. 系统架构图（自定义风格）

### 微服务架构图

```mermaid
flowchart TB
    subgraph 客户端层
        WEB["🌐 Web端<br/>(Vue.js)"]
        APP["📱 App端<br/>(React Native)"]
        MINI["📦 小程序<br/>(Taro)"]
    end

    subgraph 网关层
        GW["🚪 API网关<br/>(Kong/Nginx)"]
    end

    subgraph 服务层
        subgraph 通用服务
            USER["👤 用户服务<br/>用户/认证/权限"]
            MSG["📬 消息服务<br/>推送/短信/邮件"]
            FILE["📎 文件服务<br/>上传/存储/CDN"]
        end
        subgraph 核心业务
            PROD["📦 商品服务<br/>商品/库存/SKU"]
            ORDER["🧾 订单服务<br/>下单/支付/物流"]
            PAY["💰 支付服务<br/>微信/支付宝"]
        end
        subgraph 数据服务
            SEARCH["🔍 搜索服务<br/>(Elasticsearch)"]
            REC["🎯 推荐服务<br/>(算法引擎)"]
            BI["📊 数据服务<br/>(BI/报表)"]
        end
    end

    subgraph 数据层
        DB[("🗄️ MySQL<br/>主从集群")]
        REDIS[("⚡ Redis<br/>缓存集群")]
        MQ["📨 Kafka<br/>消息队列"]
        ES["🔍 Elasticsearch<br/>搜索引擎"]
        OSS["☁️ OSS<br/>对象存储"]
    end

    WEB & APP & MINI --> GW
    GW --> USER & MSG & FILE & PROD & ORDER & PAY & SEARCH & REC
    USER & ORDER & PAY --> DB
    PROD & ORDER --> REDIS
    ORDER --> MQ
    MQ --> MSG & REC
    ORDER --> SEARCH
    FILE --> OSS
```

---

## 9. ER 图（数据库设计）

```mermaid
erDiagram
    USER {
        bigint id PK
        string username
        string mobile UK
        string email UK
        string password
        tinyint status
        datetime created_at
        datetime updated_at
    }

    ORDER {
        bigint id PK
        bigint user_id FK
        string order_no UK
        decimal total_amount
        tinyint status
        datetime created_at
        datetime paid_at
    }

    ORDER_ITEM {
        bigint id PK
        bigint order_id FK
        bigint product_id FK
        int quantity
        decimal price
    }

    PRODUCT {
        bigint id PK
        string name
        string description
        decimal price
        int stock
        tinyint status
        datetime created_at
    }

    USER ||--o{ ORDER : places
    ORDER ||--o{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : includes
```

---

## 10. 用法建议

### 产品经理常用图表优先级

| 优先级 | 图表类型 | 使用场景 |
|--------|---------|---------|
| ⭐⭐⭐ | 流程图 | 用户流程、业务流程、系统交互 |
| ⭐⭐⭐ | 时序图 | API设计评审、技术方案沟通 |
| ⭐⭐⭐ | 甘特图 | 项目计划、里程碑展示 |
| ⭐⭐ | 状态图 | 订单状态、工单流转、生命周期 |
| ⭐⭐ | 架构图 | 系统设计、技术选型汇报 |
| ⭐ | ER图 | 数据库设计、技术评审 |

### 绘制原则

1. **简洁清晰** - 一张图说清一件事，不要试图把所有东西画在一起
2. **命名规范** - 节点命名用「谁+做什么」格式，如"用户点击登录"
3. **标注关键** - 关键判断条件、数据走向要标注清楚
4. **颜色统一** - 同类元素用同一颜色
5. **导出格式** - PRD 中使用 SVG 格式，代码评审用 Mermaid 原生

### 在不同工具中使用 Mermaid

| 工具 | 使用方式 |
|------|--------|
| Typora | 直接粘贴 Mermaid 代码块 |
| Notion | 使用 ` ```mermaid ` 代码块 |
| 飞书文档 | 使用 ` ```mermaid ` 代码块 |
| GitHub/GitLab | README.md 直接支持 |
| Draw.io | 插入 → 高级 → Mermaid |
| ProcessOn | 导入 Mermaid |
| PowerPoint | 截图或导出 SVG |

---

## 来源

> 来源：Mermaid 官方文档（2026）
> https://mermaid.js.org/
> https://mermaid.js.org/syntax/flowchart.html
> https://mermaid.js.org/syntax/sequenceDiagram.html
> https://mermaid.js.org/syntax/stateDiagram.html
> https://mermaid.js.org/syntax/gantt.html
