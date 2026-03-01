# Nginx限流技术文档：limit_req/limit_conn的令牌桶实现

## 1. 核心概念：令牌桶算法

### 1.1 算法原理
令牌桶算法是一种常见的流量控制算法，其工作原理如下：
- **令牌生成**：系统以恒定速率向桶中添加令牌
- **令牌消耗**：每个请求到达时，必须从桶中获取一个令牌
- **桶容量限制**：桶有最大容量限制，满时新令牌被丢弃
- **请求处理**：获取到令牌的请求被处理，无令牌则被拒绝或延迟

### 1.2 算法优势
- **允许突发流量**：桶内积累的令牌可应对短期流量高峰
- **平滑限流**：长期平均速率被严格控制在令牌生成速率
- **灵活性**：可通过调整参数适应不同业务场景

## 2. Nginx限流模块实现

### 2.1 limit_req模块（请求速率限制）
基于**漏桶算法变种**实现，可视为令牌桶的逆向思维。

#### 配置语法
```nginx
limit_req_zone $binary_remote_addr zone=mylimit:10m rate=10r/s;

server {
    location /api/ {
        limit_req zone=mylimit burst=20 nodelay;
        proxy_pass http://backend;
    }
}
```

#### 参数详解
| 参数 | 说明 | 默认值 |
|------|------|--------|
| `zone` | 共享内存区名称和大小 | 必填 |
| `rate` | 请求速率（r/s或r/m） | 必填 |
| `burst` | 突发请求队列大小 | 0 |
| `nodelay` | 是否立即处理突发请求 | - |

#### 工作流程
1. **正常速率请求**：直接处理（消耗令牌）
2. **突发请求**：
   - 无`burst`：超出部分直接返回503
   - 有`burst`：超出部分进入队列等待
   - 有`burst+nodelay`：突发请求立即处理但消耗未来令牌

#### 内存数据结构
```c
// 简化示例数据结构
typedef struct {
    ngx_rbtree_node_t    node;      // 红黑树节点
    ngx_queue_t          queue;     // 队列节点
    time_t               last;      // 上次请求时间
    double               tokens;    // 当前令牌数
    ngx_uint_t           excess;    // 超出计数
} ngx_http_limit_req_node_t;
```

### 2.2 limit_conn模块（并发连接限制）
基于**连接数计数器**实现，相对简单但效果显著。

#### 配置语法
```nginx
limit_conn_zone $binary_remote_addr zone=addr:10m;

server {
    location /download/ {
        limit_conn addr 10;          # 单个IP最多10个并发连接
        limit_rate 100k;             # 限速100KB/s
    }
}
```

## 3. 令牌桶实现细节

### 3.1 令牌计算算法
```c
// 令牌计算核心逻辑
tokens = min(bucket_capacity, 
             previous_tokens + (current_time - last_update) * fill_rate);

if (tokens >= 1.0) {
    tokens -= 1.0;      // 消耗一个令牌
    allow_request();
} else {
    if (burst_mode) {
        queue_request(); // 进入突发队列
    } else {
        reject_request(); // 拒绝请求
    }
}
```

### 3.2 时间精度处理
Nginx使用毫秒级时间戳进行令牌计算：
```c
ngx_msec_t  now = ngx_current_msec;
ngx_msec_t  elapsed = now - ctx->last;

// 计算新增令牌数
double tokens = ctx->tokens + elapsed * rate / 1000.0;
```

## 4. 配置示例与场景

### 4.1 基础限流配置
```nginx
# 定义限流区域（1M内存，每秒10个请求）
limit_req_zone $binary_remote_addr zone=api_limit:1m rate=10r/s;

# 定义并发限制（1M内存）
limit_conn_zone $binary_remote_addr zone=conn_limit:1m;

server {
    location /api/v1/ {
        # 请求速率限制
        limit_req zone=api_limit burst=20 nodelay;
        
        # 并发连接限制
        limit_conn conn_limit 20;
        
        # 返回429状态码（Too Many Requests）
        limit_req_status 429;
        limit_conn_status 429;
        
        proxy_pass http://api_backend;
    }
}
```

### 4.2 分层限流策略
```nginx
# 用户级别限流
limit_req_zone $binary_remote_addr zone=user_limit:10m rate=5r/s;

# API密钥级别限流
limit_req_zone $arg_apikey zone=apikey_limit:10m rate=100r/s;

# 全局限流
limit_req_zone $server_name zone=global_limit:10m rate=1000r/s;

location /api/ {
    # 多层限流检查
    limit_req zone=global_limit burst=200 nodelay;
    limit_req zone=apikey_limit burst=50;
    limit_req zone=user_limit burst=10;
    
    proxy_pass http://backend;
}
```

### 4.3 动态限流示例
```nginx
# 基于地理位置限流
geo $limited_country {
    default         0;
    CN              1;
    US              1;
}

map $limited_country $limit_rate {
    0       10r/s;  # 一般国家：10请求/秒
    1       5r/s;   # 高流量国家：5请求/秒
}

limit_req_zone $binary_remote_addr zone=dynamic_limit:10m rate=$limit_rate;
```

## 5. 性能优化建议

### 5.1 内存优化
- 根据实际IP数量调整内存区大小
- 使用`$binary_remote_addr`代替`$remote_addr`节省空间
- 定期清理过期条目（Nginx自动处理）

### 5.2 参数调优建议
```nginx
# 优化示例
limit_req_zone $binary_remote_addr 
    zone=optimized:20m              # 充足的内存空间
    rate=100r/s;                    # 合理的基础速率

location / {
    limit_req zone=optimized 
        burst=50                    # 根据业务容忍度设置
        delay=10                    # 部分请求延迟处理
        nodelay;                    # 允许突发快速响应
    
    # 设置合理的错误码
    limit_req_status 429;
    error_page 429 /429.html;
}
```

### 5.3 监控与调试
```nginx
# 添加响应头显示限流状态
add_header X-RateLimit-Limit $limit_rate;
add_header X-RateLimit-Remaining $remaining_tokens;
add_header X-RateLimit-Reset $reset_time;

# 日志记录限流事件
log_format rate_limit '$remote_addr - $remote_user [$time_local] '
                      '"$request" $status $body_bytes_sent '
                      '"$http_referer" "$http_user_agent" '
                      'limit_req=$limit_req_status '
                      'limit_conn=$limit_conn_status';
```

## 6. 注意事项

### 6.1 常见陷阱
1. **内存估算错误**：1MB约可存储16,000个独立IP状态
2. **突发设置过大**：可能导致瞬时资源耗尽
3. **时间同步问题**：多服务器时需要时间同步
4. **代理后面真实IP**：使用`$http_x_forwarded_for`时需注意安全

### 6.2 分布式环境扩展
单机Nginx限流在集群环境下的局限性：
- 可考虑结合Redis实现分布式限流
- 使用Nginx Plus的集群限流功能
- 在负载均衡层实施统一限流策略

## 7. 故障排查命令

```bash
# 查看Nginx限流状态
tail -f /var/log/nginx/access.log | grep "429"

# 测试限流效果
ab -n 1000 -c 50 http://example.com/api/

# 监控内存使用
ngx_http_status_module  # Nginx状态模块
```

## 总结

Nginx的`limit_req`和`limit_conn`模块提供了高效的令牌桶算法实现，能够有效保护后端服务免受流量冲击。通过合理的配置和参数调优，可以在允许正常业务流量的同时，有效阻止恶意攻击和突发流量导致的系统过载。

实际部署时应根据业务特点、流量模式和系统资源情况，综合考虑限流策略，并结合监控系统实时观察限流效果，持续优化配置参数。