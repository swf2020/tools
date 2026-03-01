# select/poll/epoll 三种I/O多路复用技术对比

## 1. 概述
I/O多路复用是一种允许单个进程或线程同时监视多个文件描述符（通常是网络套接字）的机制，当其中某些描述符准备好进行I/O操作时，系统会通知应用程序。select、poll和epoll是Linux系统中三种主要的I/O多路复用实现。

## 2. 技术细节对比

### 2.1 select
```c
#include <sys/select.h>

int select(int nfds, fd_set *readfds, fd_set *writefds,
           fd_set *exceptfds, struct timeval *timeout);
```

**核心特性：**
- 使用位图(fd_set)存储文件描述符，大小固定为FD_SETSIZE（通常1024）
- 每次调用需要将整个fd_set从用户空间复制到内核空间
- 返回时需要遍历所有描述符检查就绪状态
- 时间复杂度：O(n)

**优缺点：**
- 优点：跨平台支持良好（POSIX标准）
- 缺点：
  - 文件描述符数量有限制
  - 线性扫描效率低
  - 需要每次重置fd_set

### 2.2 poll
```c
#include <poll.h>

int poll(struct pollfd *fds, nfds_t nfds, int timeout);

struct pollfd {
    int fd;         // 文件描述符
    short events;   // 等待的事件
    short revents;  // 实际发生的事件
};
```

**核心特性：**
- 使用pollfd数组，无固定大小限制
- 每次调用仍需复制整个数组到内核空间
- 返回后仍需遍历整个数组
- 时间复杂度：O(n)

**优缺点：**
- 优点：无文件描述符数量限制
- 缺点：
  - 大量连接时性能下降
  - 仍需线性扫描
  - 水平触发模式

### 2.3 epoll
```c
#include <sys/epoll.h>

int epoll_create(int size);
int epoll_ctl(int epfd, int op, int fd, struct epoll_event *event);
int epoll_wait(int epfd, struct epoll_event *events,
               int maxevents, int timeout);
```

**核心特性：**
- 使用红黑树管理描述符，哈希表存储就绪事件
- 支持边沿触发(ET)和水平触发(LT)模式
- 仅返回就绪的描述符
- 时间复杂度：O(1)（就绪事件数量）

**三种触发模式：**
- **水平触发（LT，默认）**：只要文件描述符可读/可写，epoll_wait就会返回
- **边沿触发（ET）**：只有状态变化时才会通知，需要一次性处理完所有数据
- **EPOLLONESHOT**：事件被处理后，描述符会被禁用，需重新注册

**优缺点：**
- 优点：
  - 高性能，尤其在大规模并发连接时
  - 无描述符数量限制
  - 仅返回就绪的描述符
- 缺点：Linux特有，不具跨平台性

## 3. 详细对比表格

| 特性 | select | poll | epoll |
|------|--------|------|-------|
| **跨平台** | 是（POSIX） | 是（大部分Unix） | 否（Linux特有） |
| **最大描述符数** | FD_SETSIZE（通常1024） | 无限制（系统资源限制） | 无限制（系统资源限制） |
| **数据结构** | 位图(fd_set) | pollfd数组 | 红黑树+就绪链表 |
| **时间复杂度** | O(n) | O(n) | O(1)（就绪事件数） |
| **内存拷贝** | 每次调用都需要复制fd_set | 每次调用都需要复制pollfd数组 | 首次注册后不再需要 |
| **触发模式** | 水平触发 | 水平触发 | 水平触发/边沿触发 |
| **适用场景** | 连接数少，跨平台需求 | 连接数中等，需要更多描述符 | 高并发，大量连接 |

## 4. 性能对比分析

### 4.1 小规模连接（< 1000）
- select/poll：性能差异不大
- epoll：优势不明显，但编程模型更清晰

### 4.2 中大规模连接（1000-10000）
- select：性能急剧下降
- poll：仍可工作但效率降低
- epoll：性能优势显著

### 4.3 超大规模连接（> 10000）
- select/poll：基本不可用
- epoll：仍能保持良好性能

## 5. 编程模型对比

### select示例
```c
fd_set readfds;
FD_ZERO(&readfds);
FD_SET(sockfd, &readfds);

while (1) {
    fd_set tmp = readfds;
    int ret = select(maxfd+1, &tmp, NULL, NULL, NULL);
    
    for (int i = 0; i <= maxfd; i++) {
        if (FD_ISSET(i, &tmp)) {
            // 处理就绪的描述符
        }
    }
}
```

### epoll示例
```c
int epfd = epoll_create(1);
struct epoll_event ev, events[MAX_EVENTS];

ev.events = EPOLLIN;
ev.data.fd = sockfd;
epoll_ctl(epfd, EPOLL_CTL_ADD, sockfd, &ev);

while (1) {
    int nfds = epoll_wait(epfd, events, MAX_EVENTS, -1);
    
    for (int i = 0; i < nfds; i++) {
        // 处理events[i].data.fd
    }
}
```

## 6. 选择建议

### 使用select的情况：
1. 需要跨平台兼容性
2. 连接数较少（< 1024）
3. 对性能要求不高

### 使用poll的情况：
1. 需要支持超过1024个连接
2. 不需要epoll的高级特性
3. 希望在Unix系统间保持可移植性

### 使用epoll的情况：
1. Linux平台下的高性能服务器
2. 需要处理数万甚至数十万并发连接
3. 需要边沿触发模式
4. 对性能有极致要求

## 7. 最佳实践

1. **连接数少时**：选择简单、可移植的方案
2. **高并发场景**：首选epoll
3. **混合场景**：可考虑使用libevent、libuv等封装库
4. **现代开发**：考虑使用io_uring（Linux 5.1+）

## 8. 总结

select作为最古老的I/O多路复用接口，因其限制和性能问题已逐渐被淘汰。poll解决了select的描述符数量限制，但性能问题依然存在。epoll凭借其高效的数据结构和事件通知机制，成为Linux下高并发网络编程的首选方案。

在实际项目中，建议根据具体需求选择：
- 追求性能且仅面向Linux：epoll
- 需要跨平台：考虑封装库（如libevent）
- 连接数有限且简单场景：select或poll

随着Linux内核的不断发展，io_uring等新技术正在成为未来的趋势，但对于大多数现有应用，epoll仍然是成熟且高性能的选择。