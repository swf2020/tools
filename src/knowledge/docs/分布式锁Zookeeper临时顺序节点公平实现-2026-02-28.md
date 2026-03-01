# 分布式锁：基于Zookeeper临时顺序节点的公平实现

## 摘要
本文详细阐述了一种基于Apache Zookeeper**临时顺序节点**特性实现的**公平分布式锁**方案。该方案通过为每个锁竞争者创建具有全局顺序编号的临时节点，并利用Zookeeper的原生特性（如会话绑定、节点监视），实现了锁的**公平获取**、**自动释放**及**高可靠性**。核心优势在于解决了非公平锁可能导致的“饥饿”问题，并通过避免“羊群效应”优化了性能。

---

## 1. 概述
在分布式系统中，协调多个进程或服务对共享资源的互斥访问是一个经典问题。分布式锁是解决该问题的关键组件。Zookeeper作为一个高性能的协调服务，其数据模型和原语特别适合构建此类同步原语。

基于Zookeeper的分布式锁主要有两种常见实现：
1.  **临时节点锁**：利用`EPHEMERAL`节点，锁持有者会话断开时自动释放。
2.  **临时顺序节点锁**：在临时节点基础上，增加`SEQUENTIAL`后缀，生成全局有序的节点路径，是实现**公平锁**的理想选择。

本文重点讨论第二种，即**公平分布式锁**的实现。

---

## 2. 实现原理

### 2.1 Zookeeper 基础特性利用
- **临时节点（Ephemeral Nodes）**：节点生命周期与创建它的客户端会话绑定。会话结束（超时或主动关闭）时，节点自动被Zookeeper服务器删除。这天然实现了**锁的自动释放**，防止了持有者崩溃导致的死锁。
- **顺序节点（Sequential Nodes）**：创建节点时，Zookeeper会自动在路径后缀一个单调递增的、由父节点维护的全局顺序编号（如`lock-0000000001`）。这为所有锁请求提供了明确的全局顺序。
- **节点监视（Watcher）**：客户端可以在指定节点上设置监听器（Watcher），当该节点发生变化（如被删除）时，Zookeeper会通知监听客户端。这是实现锁等待和唤醒机制的基础。

### 2.2 核心工作流程与公平性体现

```
[锁资源]
    |
    `-- /lock (持久节点，锁的根目录)
         |
         |-- /lock/lock-0000000001 (临时顺序节点，客户端A)
         |-- /lock/lock-0000000002 (临时顺序节点，客户端B)
         `-- /lock/lock-0000000003 (临时顺序节点，客户端C)
```

1.  **尝试加锁**：所有客户端在同一个持久父节点（如`/locks/resource1`）下，创建**临时顺序子节点**。
2.  **判断顺序**：客户端创建节点后，获取父节点下的所有子节点列表，并按顺序编号排序。
3.  **锁获取规则**：
    - **公平性核心**：如果自身创建的节点是序列中**编号最小**的，则成功获取锁。
    - 如果自身节点不是最小的，则**监听**排在它前面的**相邻前一个节点**（`lock-<自身编号-1>`）。例如，持有`lock-0000000002`的客户端B需要监听`lock-0000000001`。
4.  **等待与唤醒**：
    - 未获得锁的客户端进入等待状态，不进行轮询。
    - 当前驱节点被删除（意味着前一个锁持有者释放了锁）时，Zookeeper会通过Watcher通知该客户端。
    - 被通知的客户端被唤醒，重新执行步骤2（获取子节点列表并排序），判断自己是否已成为最小的节点。
5.  **释放锁**：客户端完成操作后，**主动删除**自己创建的临时节点。由于是临时节点，即使客户端崩溃，会话超时后节点也会被自动删除，锁终将被释放。下一个顺序的客户端将收到通知并尝试获取锁。

**公平性保证**：请求按到达Zookeeper的顺序（体现为节点编号顺序）依次获得锁，先到先得，严格有序，杜绝了“饥饿”现象。

---

## 3. 具体实现步骤 (伪代码/逻辑描述)

### 3.1 初始化与节点路径
```java
// 1. 连接到Zookeeper集群
ZooKeeper zk = new ZooKeeper(connectString, sessionTimeout, watcher);
// 2. 确保锁的根节点存在（持久节点）
if (zk.exists("/locks/resource1", false) == null) {
    zk.create("/locks/resource1", new byte[0], ZooDefs.Ids.OPEN_ACL_UNSAFE, CreateMode.PERSISTENT);
}
```

### 3.2 加锁过程 (`lock`)
```java
public void lock() throws Exception {
    // 1. 在锁目录下创建临时顺序节点
    String myNode = zk.create("/locks/resource1/lock-", 
                              new byte[0], 
                              ZooDefs.Ids.OPEN_ACL_UNSAFE, 
                              CreateMode.EPHEMERAL_SEQUENTIAL);
    // 示例：myNode = "/locks/resource1/lock-0000000003"

    // 2. 获取锁目录下所有子节点并排序
    List<String> children = zk.getChildren("/locks/resource1", false);
    Collections.sort(children); // 按字符串顺序排序，即编号顺序

    // 3. 提取自己节点的序号部分
    String myNodeShort = myNode.substring(myNode.lastIndexOf('/') + 1); // "lock-0000000003"
    int myIndex = children.indexOf(myNodeShort);

    // 4. 判断是否为最小节点
    if (myIndex == 0) {
        // 是第一个，成功获取锁
        this.lockedNode = myNode;
        return;
    } else {
        // 5. 不是最小节点，监听前一个节点
        String prevNodeName = children.get(myIndex - 1); // "lock-0000000002"
        String prevNodeFullPath = "/locks/resource1/" + prevNodeName;

        // 设置监听器，并同步等待（CountDownLatch等）
        final CountDownLatch latch = new CountDownLatch(1);
        Stat stat = zk.exists(prevNodeFullPath, new Watcher() {
            public void process(WatchedEvent event) {
                if (event.getType() == Event.EventType.NodeDeleted) {
                    latch.countDown(); // 前驱节点被删除，唤醒
                }
            }
        });

        if (stat != null) { // 前驱节点还存在，开始等待
            latch.await();
        }
        // 6. 被唤醒后，递归或循环回到步骤2，重新检查顺序
        // 注意：必须重新获取children列表，因为序列可能已变化
        lock(); // 或者使用循环重试
    }
}
```

### 3.3 解锁过程 (`unlock`)
```java
public void unlock() throws Exception {
    if (this.lockedNode != null) {
        zk.delete(this.lockedNode, -1); // 删除自己创建的节点
        this.lockedNode = null;
    }
}
```

### 3.4 关键优化：避免“羊群效应”
在上述基础流程中，每当一个锁被释放，所有等待的客户端都会被唤醒（因为它们都监听着前一个节点，形成一个监听链）。当竞争者非常多时，这可能导致Zookeeper服务器在短时间内向大量客户端发送事件，产生压力。

**优化方案**：客户端**只监听紧邻的前一个节点**，而不是所有节点或最小节点。这样，锁释放事件只会通知到一个客户端（即下一个顺序的客户端），形成了高效的“排队队列”，将压力从服务端分散开，这是实现公平性的同时保证高性能的关键。

---

## 4. 性能与可靠性分析

### 4.1 优点
- **严格的公平性**：FIFO（先进先出）队列，请求按顺序满足。
- **高可靠性**：锁状态与Zookeeper集群保持一致，基于Paxos协议，数据强一致。
- **自动死锁处理**：临时节点机制确保了即使客户端失败，锁也能最终释放。
- **可重入性**：可通过在节点数据中存储客户端标识和重入次数来实现。
- **监听机制高效**：避免了客户端不必要的轮询，减少了网络开销。

### 4.2 潜在问题与考量
- **性能瓶颈**：所有锁操作都需要与Zookeeper集群进行网络通信和持久化，延迟高于基于内存的锁（如Redis锁）。适用于CP场景，对一致性要求高于性能的场景。
- **Zookeeper可用性**：锁服务的可用性依赖于Zookeeper集群。若Zookeeper集群瘫痪，则锁服务不可用。
- **会话管理**：客户端必须妥善管理Zookeeper会话。若因网络波动导致会话超时，临时节点会被删除，即使客户端仍在运行也会**意外释放锁**。业务代码需具备处理此类情况的能力（例如，使用`SessionConnection`重连或实现锁丢失后的安全降级）。
- **时钟同步**：Zookeeper服务器间需要时钟同步，但客户端机器时钟无需严格同步。

---

## 5. 总结
基于Zookeeper临时顺序节点实现的分布式锁，是一个经典的、**强一致的、公平的**分布式锁解决方案。它完美利用了Zookeeper提供的基础原语，通过“临时节点”保障了安全性，通过“顺序节点”和“相邻监听”实现了公平性与性能的平衡。

在选择时，需要权衡其**强一致性**和**相对较高的延迟**特性。它非常适合作为分布式系统中对数据一致性要求极高的核心组件的同步机制，例如：主备切换、全局配置更新、唯一流水号生成等场景。

**扩展思考**：此方案可与`Curator`这样的高级Zookeeper客户端库结合使用，`Curator Recipes`中提供了现成且健壮的`InterProcessMutex`（可重入公平锁）和`InterProcessSemaphoreMutex`（不可重入公平锁）实现，生产环境推荐优先使用这些经过充分测试的库。