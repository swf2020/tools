# Nginx 事件驱动模型（master-worker 进程）技术文档

> **概念层级定位：技术点（Technical Point）**
>
> Nginx 的 master-worker + 事件驱动模型是 Nginx 这款软件中实现高并发连接处理的核心原子性机制，属于「技术点」层级。它依托 epoll/kqueue 等操作系统内核机制，是"事件驱动架构"这一抽象技术在 Web Server 中的具体实现单元。

---

## 0. 定位声明

```
适用版本：Nginx 1.18.x ~ 1.27.x（主流稳定版），OpenResty 1.21.x
前置知识：
  - 理解 Linux 进程与线程的区别
  - 了解文件描述符（fd）概念
  - 掌握基本的 TCP 连接建立流程（三次握手）
  - 了解同步/异步、阻塞/非阻塞的概念区别

不适用范围：
  - 本文不覆盖 Nginx Unit（独立的应用服务器产品，线程模型不同）
  - 不涉及 Windows 版 Nginx（使用 select 而非 epoll，性能差异显著）
  - 不覆盖 Tengine / OpenResty 的扩展特性（机制一致，但配置项有差异）
```

---

## 1. 一句话本质

**Nginx 在做什么？**

> Nginx 就像一个超级高效的总机接线员：只有 1 个大厅（主进程）负责接待和管理，几个窗口（worker 进程）实际干活。每个窗口的工作人员不会因为等一个客户打电话（IO 等待）而发呆，而是同时帮几千个客户处理事情——哪个客户有消息了，马上切过去处理，没消息就去处理别人的请求。

**它解决什么问题？**

> 传统 Web 服务器（Apache prefork）的做法是：来一个客户就分配一个员工（线程/进程），员工在客户等待期间无事可做却占着资源。当并发连接达到数万时，内存和 CPU 上下文切换开销会压垮服务器（即 **C10K 问题**）。Nginx 用"事件通知 + 非阻塞 IO"彻底解决了这个问题。

---

## 2. 背景与根本矛盾

### 2.1 历史背景

2002 年，Igor Sysoev 在 Rambler（俄罗斯门户网站）面临单台服务器需支撑 **10,000 个并发连接**的挑战（C10K Problem，Dan Kegel 1999 年提出）。当时 Apache 的 prefork/worker MPM 在高并发下暴露出严重的内存消耗问题（每进程/线程约 8MB 内存，10K 并发 = 80GB 内存需求，不可行）。

Sysoev 从 2002 年开始以副业形式开发 Nginx，2004 年发布 0.1.0，核心设计就是基于 **epoll 的异步非阻塞事件循环**。

### 2.2 根本矛盾（Trade-off）

| 维度 | Nginx 的选择 | 代价 |
|------|-------------|------|
| **并发 vs 编程复杂度** | 事件驱动（高并发） | 代码逻辑碎片化，难以编写有状态逻辑 |
| **CPU 利用率 vs 进程数** | worker 数 = CPU 核数（减少上下文切换） | 单个请求不能使用多核并行加速 |
| **隔离性 vs 性能** | 多进程（worker 隔离） | 进程间共享数据需 shm，有同步开销 |
| **吞吐量 vs 延迟** | 批量事件处理（吞吐优先） | 极端情况下单请求延迟不如多线程模型 |

**最核心的 Trade-off：**
- **高并发连接数（C10K）** vs **低内存/CPU 开销** → 选择"少量进程 + 事件多路复用"，而非"每连接一进程/线程"

---

## 3. 核心概念与领域模型

### 3.1 关键术语表

| 术语 | 费曼式解释 | 正式定义 |
|------|-----------|---------|
| **master 进程** | 工厂厂长，不直接干活，负责招聘（fork worker）、发工资（信号管理）、监工（监控 worker 存活） | Nginx 主进程，PID 写入 `nginx.pid`，负责读取配置、绑定端口（特权操作）、管理 worker 生命周期 |
| **worker 进程** | 具体干活的工人，每人同时服务成千上万个客户 | Nginx 工作进程，实际处理 HTTP 连接和请求，数量通常等于 CPU 核数 |
| **事件循环（Event Loop）** | 工人的工作方式：不停地问"谁有活干？"，有的话立刻处理，没有的话继续问 | 基于 epoll/kqueue 的 I/O 多路复用循环，单线程内处理多个文件描述符的就绪事件 |
| **epoll** | 操作系统提供的"监控板"，同时监视几万个连接，谁有数据来了就通知你 | Linux 内核提供的 I/O 事件通知接口（2.6+ 内核），时间复杂度 O(1)，相较 select/poll 的 O(n) 性能大幅提升 |
| **非阻塞 I/O** | 打电话问"有数据吗？"，对方说"没有"时你可以挂断去干别的，而不是傻等 | 系统调用立即返回，若资源未就绪则返回 EAGAIN/EWOULDBLOCK，不挂起进程 |
| **连接池（Connection Pool）** | 预先准备好的"连接工具箱"，不用每次都重新造工具 | Nginx 预分配的 `ngx_connection_t` 结构体数组，避免运行时动态分配内存 |
| **upstream** | 后端服务器，Nginx 把请求转发给它 | Nginx 反向代理的上游服务节点，通常是应用服务器（Node.js、PHP-FPM、Java 等） |

### 3.2 领域模型

```
操作系统
└── master 进程 (PID: 1000)
    ├── 绑定监听端口 :80 :443
    ├── 管理共享内存（统计计数器、upstream 健康状态）
    ├── 接收信号（SIGHUP=reload, SIGQUIT=graceful stop）
    │
    ├── worker 进程 #0 (PID: 1001, CPU core 0)
    │   └── epoll 实例
    │       ├── 监听 socket fd (accept 新连接)
    │       ├── 客户端 fd #5 → 正在读 Request Headers
    │       ├── 客户端 fd #6 → 正在等 upstream 响应
    │       ├── upstream fd #7 → 正在写请求到后端
    │       └── ... (可达 worker_connections 个，默认 1024)
    │
    ├── worker 进程 #1 (PID: 1002, CPU core 1)
    │   └── epoll 实例 (同上结构)
    │
    └── cache manager / cache loader 进程 (可选)
```

**关键实体关系：**

```
1 master → N worker（N = worker_processes，推荐 = CPU 核数）
1 worker → 1 epoll 实例
1 epoll 实例 → M 个活跃连接（M ≤ worker_connections，默认 1024，建议 10240~65535）
1 连接 → 1 ngx_connection_t 结构体（~232 bytes）
1 请求 → 1 ngx_http_request_t（附属于连接，keep-alive 下一连接多请求）
```

---

## 4. 对比与选型决策

### 4.1 同类技术横向对比

| 特性 | Nginx (event-driven) | Apache prefork | Apache worker | Node.js (单进程) | HAProxy |
|------|---------------------|---------------|---------------|-----------------|---------|
| 并发模型 | 多进程 + 事件循环 | 多进程（1进程/连接） | 多线程 | 单进程事件循环 | 多进程 + 事件循环 |
| 10K 并发内存 | ~150MB | ~800MB~8GB | ~200~400MB | ~200MB | ~100MB |
| 静态文件吞吐 | ~50K req/s | ~5K req/s | ~10K req/s | ~15K req/s | N/A（4层为主）|
| 配置热重载 | ✅ 零停机 | ✅（较慢） | ✅（较慢） | ❌（需重启） | ✅ 零停机 |
| 动态内容 | ❌（需 FastCGI/proxy） | ✅ 原生 mod_php | ✅ 原生 mod_php | ✅ 原生 | ❌ |
| 适合场景 | 反代/静态/API网关 | 传统 PHP 应用 | 传统 PHP 应用 | Node.js 应用 | 4/7 层负载均衡 |

> ⚠️ 存疑：以上性能数据基于通用 benchmark 报告（如 TechEmpower），实际值受硬件、内核版本、请求大小影响显著，仅供数量级参考。

### 4.2 选型决策树

```
需要处理高并发（>1000并发）？
├── 是 → 需要执行动态代码（PHP/Python）吗？
│        ├── 否 → 选 Nginx（静态文件、反向代理、API 网关）
│        └── 是 → Nginx + FastCGI（PHP-FPM）或 Nginx + uWSGI（Python）
│                  ⚠️ 别用 Apache mod_php（进程隔离成本高）
└── 否 → 并发量 <500，需要快速开发？
         └── Apache（模块生态更丰富，配置更灵活）
```

### 4.3 与上下游技术的配合关系

```
[Internet] → [Nginx] → [Application Server: PHP-FPM / uWSGI / Node.js / Tomcat]
                ↕
          [静态文件: /var/www/html]
                ↕
          [SSL 终止: Let's Encrypt / 内部 CA]
                ↕
          [上游健康检查 + 负载均衡]
```

Nginx 在技术栈中扮演**边缘代理（Edge Proxy）**角色：SSL 终止、静态文件托管、动态请求转发、限流、认证前置。

---

## 5. 工作原理与实现机制

### 5.1 静态结构：核心组件与数据结构

#### 核心数据结构

**`ngx_connection_t`（连接对象，约 232 bytes）**
```c
// nginx/src/core/ngx_connection.h（Nginx 1.24.x）
struct ngx_connection_s {
    void               *data;          // 指向请求对象（ngx_http_request_t）
    ngx_event_t        *read;          // 读事件
    ngx_event_t        *write;         // 写事件
    ngx_socket_t        fd;            // 文件描述符
    ngx_recv_pt         recv;          // 接收函数指针（封装 read 系统调用）
    ngx_send_pt         send;          // 发送函数指针
    ngx_buf_t          *buffer;        // 接收缓冲区
    ngx_pool_t         *pool;          // 内存池（请求结束时整体释放，避免内存碎片）
    struct sockaddr    *sockaddr;       // 客户端地址
    // ...
};
```

**为什么用内存池（`ngx_pool_t`）？**
> Trade-off：避免 `malloc/free` 碎片化 + 请求结束时一次性释放所有内存（O(1) 清理），代价是无法单独释放池中某块内存。这对 HTTP 请求场景完全合理，因为请求的所有内存生命周期一致。

**`ngx_event_t`（事件对象）**
```c
struct ngx_event_s {
    void            *data;      // 指向连接
    unsigned         write:1;   // 是读事件还是写事件
    unsigned         active:1;  // 是否已注册到 epoll
    unsigned         ready:1;   // 是否就绪（有数据可读/可写）
    ngx_event_handler_pt  handler;  // 事件回调函数（核心：状态机驱动）
    ngx_rbtree_node_t    timer;     // 超时定时器（红黑树节点）
    // ...
};
```

**为什么用红黑树管理定时器？**
> 定时器需要高效的"查找最小超时时间"（O(log n) 插入/删除，O(1) 查找最小值）。相比时间轮，红黑树在 Nginx 场景（连接数有限，精度要求不极端）是更简单的选择。

### 5.2 动态行为：关键流程

#### 流程一：启动流程

```
1. Nginx 启动 → master 进程以 root 权限执行
2. 解析 nginx.conf
3. master 绑定监听端口（80/443）→ 获取 listen fd（特权操作，此后 worker 降权运行）
4. master fork() → 创建 N 个 worker 进程
5. 每个 worker 进程：
   a. 初始化 epoll 实例（epoll_create）
   b. 将 listen fd 加入 epoll 监控（EPOLLIN）
   c. 进入事件循环（ngx_worker_process_cycle）
```

#### 流程二：请求处理时序（核心！）

```
客户端          listen fd(epoll)    worker 进程         upstream
   |                  |                  |                  |
   |──── TCP SYN ────>|                  |                  |
   |                  |── EPOLLIN 就绪 ──>|                  |
   |                  |                  |── accept() ──>新 fd|
   |                  |                  |── 注册新 fd 到 epoll|
   |──── HTTP 请求 ──────────────────────>|                  |
   |                  |── EPOLLIN 就绪 ──>|                  |
   |                  |                  |── read() 读请求头  |
   |                  |                  |── 解析 HTTP 请求   |
   |                  |                  |── connect() 建连 ─>|
   |                  |                  |── 注册 upstream fd  |
   |                  |── EPOLLOUT 就绪 ─>|                  |
   |                  |                  |── write() 发请求 ─>|
   |                  |── EPOLLIN 就绪 ──>|                  |
   |                  |                  |<── read() 读响应 ──|
   |<── HTTP 响应 ──────────────────────────                  |
   |                  |                  |── 关闭/复用连接     |
```

**关键设计：整个流程在单个 worker 进程的单个线程内完成，零线程切换开销。**

#### 流程三：热重载流程（zero-downtime reload）

```
1. 运维执行：nginx -s reload（等价于 kill -HUP <master_pid>）
2. master 收到 SIGHUP
3. master 重新解析 nginx.conf（若有语法错误，退出，老 worker 继续服务）
4. master fork 新 worker 进程（使用新配置）
5. master 向老 worker 发送 SIGQUIT（graceful shutdown）
6. 老 worker 停止 accept 新连接，等待存量连接处理完毕后退出
7. 结果：服务零中断，配置已更新
```

### 5.3 关键设计决策深析

#### 决策一：为什么用多进程而非多线程？

| | 多进程（Nginx 的选择） | 多线程 |
|-|----------------------|-------|
| 隔离性 | 一个 worker 崩溃不影响其他 worker | 一个线程崩溃可能导致整个进程崩溃 |
| 内存共享 | 需要显式 shm（共享内存） | 天然共享，但需要锁 |
| 上下文切换 | 进程切换代价高于线程 | 线程切换更轻量 |
| GIL 问题 | 无（C 语言实现） | 无（但 Python/Ruby 等语言有 GIL） |

**Nginx 的选择理由**：稳定性 > 轻量性。一个 worker 因第三方模块 bug 崩溃，master 会立即 fork 新 worker，对用户透明。而且 worker 数量等于 CPU 核数时，进程切换极少发生（每个 worker 绑定在一个核上运行）。

#### 决策二：为什么 worker 数量 = CPU 核数？

- 每个 worker 是纯事件循环，是 CPU 密集型（无 IO 等待阻塞的浪费）
- 超过核数 → 多个 worker 争同一个核 → 上下文切换增加 → 性能下降
- 少于核数 → 部分核空闲 → 吞吐量不达最大值

**例外情况**：若有大量阻塞操作（如使用了非异步的 DNS 解析、同步磁盘 IO），可适当增加 worker 数（但 Nginx 的正确做法是开启 `aio threads`）。

#### 决策三：accept_mutex vs REUSEPORT

早期 Nginx 多个 worker 同时监听同一端口，新连接到来时所有 worker 同时被唤醒（惊群问题，Thundering Herd），造成无效上下文切换。

| 方案 | 机制 | 优点 | 缺点 |
|------|------|------|------|
| `accept_mutex on`（旧默认） | 分布式锁，同一时刻只有一个 worker 接受新连接 | 消除惊群 | 锁竞争有延迟，串行化限制吞吐 |
| `reuseport`（Linux 3.9+，现代推荐） | 内核为每个 worker 维护独立的 accept 队列 | 完全并行，内核负载均衡 | 需 Linux 3.9+，连接分发略有不均 |

**推荐配置（Linux 3.9+）**：
```nginx
events {
    worker_connections 10240;
    use epoll;           # Linux 下明确指定（默认也会选 epoll）
    accept_mutex off;    # 配合 reuseport 时关闭（避免双重限制）
}

http {
    server {
        listen 80 reuseport;   # 每个 worker 独立队列，消除惊群
        listen 443 ssl reuseport;
    }
}
```

---

## 6. 高可靠性保障

### 6.1 高可用机制

**Worker 崩溃自愈**：master 通过 `waitpid()` 检测 worker 退出，立即 fork 新 worker，恢复时间 < 100ms（通常 < 10ms）。

**连接超时保护**：红黑树管理的定时器确保僵尸连接被及时清理。关键超时参数：
```nginx
http {
    keepalive_timeout 65;      # 空闲 keepalive 连接保持时间（秒）
    client_header_timeout 10;  # 读客户端请求头超时
    client_body_timeout 10;    # 读客户端请求体超时
    send_timeout 10;           # 向客户端发送响应超时
    proxy_connect_timeout 5;   # 连接 upstream 超时
    proxy_read_timeout 60;     # 读 upstream 响应超时
}
```

### 6.2 可观测性：关键监控指标

**`ngx_http_stub_status_module`** 提供基础指标（需编译时启用或使用商业版 nginx-plus）：

```nginx
location /nginx_status {
    stub_status;
    allow 127.0.0.1;
    deny all;
}
```

响应示例：
```
Active connections: 291
server accepts handled requests
 16630948 16630948 31070465
Reading: 6 Writing: 179 Waiting: 106
```

| 指标 | 含义 | 健康阈值 |
|------|------|---------|
| `Active connections` | 当前活跃连接数 | < `worker_processes × worker_connections × 0.8` |
| `accepts - handled` | 丢弃连接数（应为 0） | = 0，非 0 说明连接溢出 |
| `Reading` | 正在读请求的连接 | 通常 < 总连接的 5% |
| `Writing` | 正在发响应的连接 | 通常 < 总连接的 50% |
| `Waiting` | keepalive 空闲连接 | 与 `keepalive_timeout` 正相关，可接受较高值 |

**配合 Prometheus + nginx-prometheus-exporter 采集更细粒度指标**（推荐生产使用）：

```bash
# 关注指标
nginx_http_requests_total          # 请求总数（按 status code）
nginx_connections_accepted_total   # 接受连接总数
nginx_connections_active           # 当前活跃连接
nginx_upstream_response_time_seconds_bucket  # upstream 响应时间分布（需 opentelemetry 模块）
```

---

## 7. 使用实践与故障手册

### 7.1 生产级核心配置（Nginx 1.24.x，Linux 5.15+）

```nginx
# /etc/nginx/nginx.conf

# 工作进程数设置为 CPU 核数（auto 自动检测）
worker_processes auto;

# 绑定 worker 到 CPU 核（减少 CPU 缓存 miss）
worker_cpu_affinity auto;

# worker 进程最大打开文件数（需配合 ulimit -n）
worker_rlimit_nofile 65536;

# 错误日志级别：生产用 warn，排查问题时临时改为 info/debug
error_log /var/log/nginx/error.log warn;

events {
    # 明确使用 epoll（Linux）
    use epoll;
    
    # 每个 worker 的最大并发连接数
    # 系统最大并发 ≈ worker_processes × worker_connections
    # 注意：每个连接消耗约 232 bytes（ngx_connection_t），10240个连接 ≈ 2.4MB
    worker_connections 10240;
    
    # 允许 worker 一次 accept 尽可能多的新连接（配合 reuseport 使用）
    multi_accept on;
    
    # 使用 reuseport 时关闭 accept_mutex
    accept_mutex off;
}

http {
    # 开启 sendfile：让内核直接将文件发送到 socket，绕过用户空间拷贝
    # 静态文件服务必须开启，减少 2 次内存拷贝
    sendfile on;
    
    # 开启 TCP_CORK：将小包合并成大包发送，减少网络包数量
    tcp_nopush on;
    
    # 开启 TCP_NODELAY：关闭 Nagle 算法，减少延迟（与 tcp_nopush 配合使用）
    tcp_nodelay on;
    
    # keepalive 配置
    keepalive_timeout 65;        # 65 秒内无请求则关闭 keepalive 连接
    keepalive_requests 1000;     # 单个 keepalive 连接最多处理 1000 个请求
    
    server {
        # reuseport：每个 worker 有独立的 accept 队列，消除惊群
        listen 80 reuseport backlog=4096;
        listen 443 ssl reuseport backlog=4096;
        
        # backlog：内核 TCP accept 队列大小，需与 net.core.somaxconn 协调
        # net.core.somaxconn 默认 128（严重不足），生产建议设置为 4096 或更高
    }
}
```

**配套内核参数（/etc/sysctl.conf）**：
```bash
# TCP 连接队列
net.core.somaxconn = 4096          # listen backlog 上限
net.core.netdev_max_backlog = 4096 # 网卡收包队列
net.ipv4.tcp_max_syn_backlog = 4096

# 文件描述符
fs.file-max = 1000000              # 系统级文件描述符上限

# TIME_WAIT 优化（高并发短连接场景）
net.ipv4.tcp_tw_reuse = 1          # 允许 TIME_WAIT socket 被重用
net.ipv4.tcp_fin_timeout = 30      # 缩短 FIN_WAIT_2 超时
```

### 7.2 故障模式手册

```
【故障一：502 Bad Gateway 大量出现】
- 现象：用户看到 502，nginx error.log 报 "connect() failed (111: Connection refused)"
- 根本原因：upstream（如 PHP-FPM / Node.js）进程崩溃或未启动；或 upstream 连接池耗尽
- 预防措施：
  1. 配置 upstream 健康检查（nginx-plus 或第三方 nginx_upstream_check_module）
  2. 设置合理的 proxy_connect_timeout（5~10s）
  3. 监控 upstream 进程存活状态
- 应急处理：
  1. 检查 upstream 进程状态：`systemctl status php-fpm`
  2. 查看 upstream 自身日志定位崩溃原因
  3. 重启 upstream：`systemctl restart php-fpm`
  4. 若 upstream 过载，临时增加 worker 数或启用限流保护
```

```
【故障二：nginx: [emerg] bind() to 0.0.0.0:80 failed (98: Address in use)】
- 现象：reload 或启动失败，端口被占用
- 根本原因：
  (a) 上一个 nginx master 未正常退出（老 master 还在）
  (b) 其他进程占用了 80/443 端口
- 预防措施：规范启停流程，使用 systemd 管理 nginx 生命周期
- 应急处理：
  1. 检查占用进程：`ss -tlnp | grep :80` 或 `fuser 80/tcp`
  2. 查看 nginx 进程状态：`cat /var/run/nginx.pid && ps aux | grep nginx`
  3. 若是僵尸 nginx 进程：`kill -QUIT <old_master_pid>`（graceful）或 `kill -TERM <pid>`（强制）
```

```
【故障三：连接数爆满，worker_connections 告警】
- 现象：access log 出现 "worker_connections are not enough"，大量连接被拒绝
- 根本原因：
  (a) worker_connections 设置过低（默认 1024 对高并发不够）
  (b) upstream 响应慢导致连接堆积（upstream latency 放大了并发连接数）
  (c) keepalive_timeout 过大导致空闲连接占用资源
- 预防措施：
  1. 公式：worker_connections >= 预期峰值并发 / worker_processes × 1.5
  2. 同时提高 worker_rlimit_nofile（否则文件描述符不够）
  3. 监控 "Active connections" 指标，设置告警阈值为 worker_connections × 0.8
- 应急处理：
  1. 修改 nginx.conf：提升 worker_connections 到 65535
  2. 执行：nginx -s reload（零停机）
  3. 同步修改 ulimit：/etc/security/limits.conf 中 nginx soft nofile 65535
```

```
【故障四：CPU 单核 100%，其他核空闲】
- 现象：top 显示某个 nginx worker CPU 100%，其他 worker 很低
- 根本原因：
  (a) 未启用 reuseport，所有新连接都由 accept_mutex 获胜的 worker 处理（负载不均）
  (b) 某个耗时请求（如大文件传输）长时间占用 worker 的事件循环
- 预防措施：启用 reuseport（Linux 3.9+），配合 worker_cpu_affinity auto
- 应急处理：
  1. 短期：nginx -s reload 会重新分配连接
  2. 长期：添加 reuseport 配置并 reload
```

```
【故障五：upstream 响应慢导致雪崩（连接积压）】
- 现象：upstream 延迟从 50ms 升高到 5s，nginx 活跃连接数从 500 飙升到 50000，最终 502
- 根本原因：upstream 变慢 → 连接无法及时释放 → 新请求继续涌入 → 连接数耗尽
- 预防措施：
  1. 设置 proxy_read_timeout 不要过长（生产建议 10~30s，而非默认 60s）
  2. 配置限流（limit_req_zone）保护 upstream
  3. 配置 upstream keepalive 连接池，减少连接建立开销
- 应急处理：
  1. 临时降低 proxy_read_timeout，快速失败释放连接
  2. 启用熔断降级（nginx + lua / OpenResty）
  3. 排查 upstream 慢的根本原因
```

### 7.3 边界条件与局限性

1. **阻塞操作会卡死整个 worker**：Nginx 的事件循环是单线程的。若某个模块执行了阻塞系统调用（如同步 DNS 查询、阻塞文件 IO），该 worker 的所有其他连接都会暂停。Nginx 通过 `aio threads` 指令将磁盘 IO 卸载到线程池缓解，但 DNS 解析默认仍是阻塞的（可用 OpenResty + lua-resty-dns 解决）。

2. **单个请求无法利用多核**：一个 HTTP 请求始终由同一个 worker 处理，不会跨核并行。对于超大文件传输（>1GB），单 worker 成为瓶颈。

3. **共享内存有限**：upstream 健康状态、限流计数器等存储在共享内存（`zone` 指令），默认大小通常只有几 MB。超出会导致写入失败（limit_req 计数丢失，健康检查失效）。

4. **SSL 握手是 CPU 密集操作**：大量短连接 + SSL 握手会显著增加 CPU 消耗（RSA 2048 握手约 1~5ms CPU 时间），此时应配置 SSL 会话缓存复用（`ssl_session_cache`）。

5. **`worker_connections` 包含所有连接类型**：包括到 upstream 的连接。因此反向代理场景下实际可服务的客户端连接数 = `worker_connections / 2`（每个客户端请求对应一个 upstream 连接）。

---

## 8. 性能调优指南

### 8.1 性能瓶颈识别

```bash
# 步骤 1：查看当前连接状态分布
curl http://127.0.0.1/nginx_status

# 步骤 2：查看 CPU 使用率（哪个 worker 高？）
top -p $(pgrep -d',' nginx)

# 步骤 3：查看系统调用耗时（strace 会有性能影响，仅用于排查）
strace -p <worker_pid> -c -e trace=epoll_wait,accept4,read,write

# 步骤 4：查看连接状态分布
ss -s  # 重点关注 TIME_WAIT 数量

# 步骤 5：查看文件描述符使用
ls /proc/<worker_pid>/fd | wc -l
```

**瓶颈层次判断**：

| 现象 | 可能瓶颈 | 验证命令 |
|------|---------|---------|
| CPU 高，连接数正常 | 计算密集（SSL/正则/gzip） | `perf top -p <pid>` |
| 连接数高，CPU 低 | 连接未释放（keepalive/upstream 慢） | `ss -tnp | grep nginx` |
| 网卡 rx/tx 满 | 带宽瓶颈 | `sar -n DEV 1 5` |
| 大量 TIME_WAIT | 短连接过多，端口耗尽 | `ss -s | grep TIME-WAIT` |

### 8.2 调优步骤（按优先级）

1. **调整 worker_connections 和文件描述符上限**（收益最高，成本最低）
   - 目标：`worker_connections × worker_processes` 覆盖峰值并发的 2 倍
   - 验证：`Active connections` 峰值 < `worker_connections × 0.7`

2. **启用 reuseport 消除惊群**
   - 目标：各 worker 的连接数分布均匀（标准差 < 平均值的 10%）
   - 验证：`ps aux | grep nginx` 观察各 worker CPU 利用率是否均匀

3. **sendfile + tcp_nopush + tcp_nodelay 三件套**（静态文件场景必须）
   - 目标：静态文件吞吐提升 30~50%
   - 验证：`ab -n 10000 -c 100 http://localhost/static/test.jpg`

4. **upstream keepalive 连接复用**
   - 目标：减少 upstream TCP 握手开销，提升 QPS 20~40%
   - 配置：
     ```nginx
     upstream backend {
         server 127.0.0.1:8080;
         keepalive 64;  # 每个 worker 保持的 upstream 空闲连接数
         keepalive_requests 1000;
         keepalive_timeout 60s;
     }
     http {
         proxy_http_version 1.1;
         proxy_set_header Connection "";  # 必须清除 Connection header
     }
     ```
   - 验证：`netstat -tnp | grep ESTABLISHED | grep 8080 | wc -l`

5. **SSL 会话缓存（HTTPS 场景）**
   - 目标：减少 SSL 全握手，TLS 1.2 中 session reuse 将握手时间从 ~10ms 降至 ~1ms
   - 配置：
     ```nginx
     ssl_session_cache   shared:SSL:50m;  # 50MB，约缓存 20 万个会话
     ssl_session_timeout 1d;
     ssl_session_tickets off;  # 建议关闭（安全原因：缺乏前向保密）
     ```

### 8.3 调优参数速查表

| 参数 | 默认值 | 推荐值 | 调整风险 |
|------|--------|--------|---------|
| `worker_processes` | 1 | `auto`（= CPU 核数） | 过高增加上下文切换 |
| `worker_connections` | 1024 | 10240~65535 | 过高消耗内存（每连接 ~232B） |
| `worker_rlimit_nofile` | 系统默认 | 与 worker_connections 匹配（×2） | 需配合 ulimit 修改 |
| `keepalive_timeout` | 75 | 30~65 | 过高占用连接，过低增加握手开销 |
| `keepalive_requests` | 1000 | 1000~10000 | 过高可能导致连接不均衡 |
| `proxy_read_timeout` | 60 | 10~30 | 过低导致正常慢请求超时 |
| `client_max_body_size` | 1m | 按业务需求（如 10m） | 过大允许大文件上传占用内存 |
| `gzip_comp_level` | 1 | 2~4 | 高于 6 CPU 消耗显著增加但压缩率提升有限 |
| `open_file_cache max` | off | 10000 | 过大消耗内存，适合静态文件多的场景 |

---

## 9. 演进方向与未来趋势

### 9.1 QUIC/HTTP3 支持（已在 Nginx 1.25.x mainline 实装）

Nginx 1.25.0 开始提供实验性 QUIC + HTTP/3 支持，配置方式：

```nginx
server {
    listen 443 quic reuseport;   # UDP
    listen 443 ssl reuseport;    # TCP fallback
    ssl_protocols TLSv1.3;
    
    add_header Alt-Svc 'h3=":443"; ma=86400';  # 告知客户端支持 HTTP/3
}
```

**对使用者的影响**：QUIC 将连接迁移（网络切换不断连）和 0-RTT 握手（重连无延迟）带入 Web Server 层，移动端用户体验显著提升。但 UDP 在某些企业防火墙下会被阻断，需 TCP 并行兜底。

### 9.2 动态模块化与可编程性（OpenTelemetry / WASM）

Nginx 官方 OpenTelemetry 模块（otel-nginx）已发布，支持分布式追踪：

```nginx
load_module modules/ngx_otel_module.so;  # Nginx 1.23.4+

http {
    otel_exporter {
        endpoint localhost:4317;  # OTLP gRPC endpoint
    }
    server {
        otel_trace on;
        otel_trace_context propagate;  # 传播 W3C Trace Context
    }
}
```

**对使用者的影响**：Nginx 从"哑代理"升级为可观测的可编程网关，无需再依赖 Lua（OpenResty）实现追踪，降低了可观测性的接入门槛。

---

## 10. 面试高频题

```
【基础理解层】（考察概念掌握）

Q：Nginx 的 master 进程和 worker 进程分别负责什么？
A：master 进程负责管理工作：读取并校验配置文件、绑定监听端口（需 root 权限）、fork 和管理 worker 进程、接收并处理系统信号（SIGHUP/SIGQUIT 等）。worker 进程负责实际的网络 I/O 工作：accept 新连接、解析 HTTP 请求、与 upstream 交互、返回响应。worker 进程通常以非特权用户身份运行（如 www-data），提高安全性。
考察意图：验证候选人是否理解 Nginx 进程职责分离，以及这种设计带来的安全和稳定性优势。

Q：为什么 worker_processes 推荐设置为 CPU 核数，而不是更多？
A：每个 worker 进程运行一个事件循环，是 CPU 密集型任务（几乎没有 I/O 等待，因为所有 I/O 都是非阻塞的）。设置为 CPU 核数时，每个 worker 独占一个核，最大化 CPU 缓存命中率，避免线程调度开销。超过核数后，操作系统需要在核之间调度多个 worker，产生额外的上下文切换开销，反而降低性能。
考察意图：考察候选人对事件驱动与多核关系的理解。
```

```
【原理深挖层】（考察内部机制理解）

Q：Nginx 是如何解决 "惊群问题（Thundering Herd）" 的？
A：惊群问题是指多个 worker 同时监听同一端口时，一个新连接到来会唤醒所有 worker，但只有一个能 accept 成功，其余白白被唤醒造成资源浪费。Nginx 有两个阶段的解决方案：
  1. 早期方案：accept_mutex（互斥锁），同一时刻只有持有锁的 worker 才会将 listen fd 加入 epoll，确保只有一个 worker 被唤醒。缺点是有锁竞争延迟，限制了吞吐量。
  2. 现代方案（推荐）：SO_REUSEPORT（Linux 3.9+），内核为每个 worker 创建独立的监听 socket 和 accept 队列，新连接由内核直接分配给某个 worker，彻底消除惊群，同时实现了更好的负载均衡。
考察意图：考察候选人对 Linux 内核网络特性的了解，以及在 Nginx 中的实际应用。

Q：Nginx 的事件循环如何同时处理数万个连接，而不是一个一个处理？
A：核心是 epoll 的 I/O 多路复用。Nginx 将所有活跃连接的文件描述符注册到 epoll 中，然后调用 epoll_wait() 阻塞等待。当任意一个或多个 fd 上发生可读/可写事件时，epoll_wait() 立即返回，携带就绪 fd 列表。Nginx 遍历就绪 fd 列表，为每个就绪 fd 调用对应的事件处理回调（handler）。由于所有 I/O 操作都是非阻塞的（设置了 O_NONBLOCK），回调函数执行后立即返回，不会阻塞等待 I/O 完成，从而可以快速处理下一个就绪 fd。本质是用"轮询就绪事件"替代"等待单个 I/O"，在同一个线程内实现了并发处理。
考察意图：考察候选人对 epoll 工作原理的深度理解。
```

```
【生产实战层】（考察工程经验）

Q：Nginx reload 是如何实现零停机的？如果 reload 期间有正在处理的长连接，会怎么处理？
A：nginx -s reload（等价于 kill -HUP master_pid）触发以下流程：
  1. master 重新解析 nginx.conf，若有语法错误则直接退出，老 worker 继续服务（这是 reload 的保护机制）
  2. master fork 新的 worker 进程，使用新配置
  3. master 向老 worker 发送 SIGQUIT（优雅停止信号）
  4. 老 worker 收到 SIGQUIT 后停止 accept 新连接，但继续处理已建立的连接，直到所有连接结束后才退出
  5. 对于 keepalive 的长连接，老 worker 会在处理完当前请求后关闭连接（而不是立即断开）
  这个机制保证了正在处理的请求不会被中断，新请求由新 worker 处理。潜在问题：如果存在非常长的连接（如 WebSocket、SSE），老 worker 可能长时间不退出，造成内存中同时存在新老两套 worker。
考察意图：考察候选人对 Nginx 运维实践的掌握，特别是对 graceful shutdown 语义的理解。

Q：生产中遇到大量 502 且 error.log 提示 "upstream timed out"，如何系统性排查？
A：按以下顺序排查：
  1. 确认 upstream 是否存活：curl upstream 地址，或 systemctl status upstream-service
  2. 检查 upstream 自身日志：是否有 OOM、慢查询、连接池耗尽
  3. 检查 proxy_read_timeout 与 upstream 实际响应时间的匹配关系：tail nginx access.log 查看 $upstream_response_time，若普遍超过 timeout 说明 upstream 本身变慢
  4. 检查 upstream 连接数是否耗尽：ss -tnp | grep <upstream_port> | wc -l，与 upstream 配置的最大连接数对比
  5. 检查 nginx→upstream 的网络延迟（若跨机房）：ping upstream_ip，tcptraceroute
  6. 若 upstream 确实过载，短期对策：降低 proxy_read_timeout 让请求快速失败 + 限流（limit_req），长期对策：扩容 upstream 或优化 upstream 处理逻辑。
考察意图：考察候选人的系统性排查思路，以及对 Nginx → upstream 整个调用链的理解。
```

---

## 11. 文档元信息

### 验证声明

```
本文档内容经过以下验证：
✅ 与官方文档一致性核查：http://nginx.org/en/docs/
✅ 核心机制描述参考 Nginx 源码（github.com/nginx/nginx）进行交叉验证
⚠️ 以下内容未经本地环境验证，仅基于文档推断：
   - 第 8.1 节 strace 性能影响数据（"会有性能影响"为经验描述，具体数值未量化）
   - 第 9.1 节 QUIC/HTTP3 配置在 Nginx 1.25.x 的实际行为（版本特性仍在快速迭代）
   - 第 4.1 节性能对比表中的具体数值（来源于公开 benchmark，非本地实测）
```

### 知识边界声明

```
本文档适用范围：
- Nginx 1.18.x ~ 1.27.x 开源版，部署于 Linux x86_64（内核 3.10+）
- 核心机制（epoll 事件循环、master-worker 模型）在 1.x 全系列基本一致

不适用场景：
- Nginx Plus 商业版（有额外的 active health check、动态 upstream 等特性）
- Windows 版 Nginx（使用 select 而非 epoll，性能和行为差异显著）
- OpenResty（基于 Nginx 但增加了 LuaJIT，扩展了事件循环能力）
- Nginx Unit（完全不同的多语言应用服务器，不适用本文内容）
```

### 参考资料

```
官方文档：
- Nginx 官方文档：http://nginx.org/en/docs/
- Nginx 开发指南：http://nginx.org/en/docs/dev/development_guide.html
- ngx_http_stub_status_module：http://nginx.org/en/docs/http/ngx_http_stub_status_module.html

核心源码：
- Nginx GitHub（官方镜像）：https://github.com/nginx/nginx
- 核心事件循环：src/event/ngx_event.c
- HTTP 请求处理：src/http/ngx_http_request.c
- 连接管理：src/core/ngx_connection.c

延伸阅读：
- C10K Problem 原文：http://www.kegel.com/c10k.html
- Linux epoll 手册：man 7 epoll
- SO_REUSEPORT 解析：https://www.nginx.com/blog/socket-sharding-nginx-release-1-9-1/
- Nginx 内部机制（agentzh 博客）：https://openresty.org/download/agentzh-nginx-internals.pdf
- Linux 高性能服务器编程（游双）- 第 9 章 I/O 复用
```

---

## 输出质量自检清单

- [x] 每个核心概念是否提供了费曼式无术语解释？（见第 1 节"一句话本质"和第 3.1 节术语表的"费曼式定义"列）
- [x] 每个设计决策是否说明了 Trade-off 而不只是结论？（见第 2.2 节根本矛盾表、第 5.3 节三个关键决策分析）
- [x] 代码示例是否注明了可运行的版本环境？（见第 7.1 节注明了 Nginx 1.24.x，Linux 5.15+）
- [x] 性能数据是否给出了具体数值而非模糊描述？（见第 4.1 节对比表、第 8.3 节调优参数表）
- [x] 不确定内容是否标注了 `⚠️ 存疑`？（见第 4.1 节性能对比数据、第 11 节验证声明）
- [x] 文档元信息（验证声明、边界、参考资料）是否完整？（见第 11 节）
