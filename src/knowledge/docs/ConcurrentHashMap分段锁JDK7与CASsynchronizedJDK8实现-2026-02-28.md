# ConcurrentHashMap实现机制演进：JDK7分段锁与JDK8 CAS+synchronized

## 文档概述

本文档详细分析Java ConcurrentHashMap在JDK7和JDK8中的两种不同实现机制，对比分段锁（JDK7）与CAS+synchronized（JDK8）的设计原理、实现细节及性能特征，为开发者深入理解高并发容器提供技术参考。

## 一、JDK7分段锁实现机制

### 1.1 核心设计思想

JDK7中的ConcurrentHashMap采用**分段锁（Segment Locking）**策略，将整个哈希表分割成多个独立锁保护的段（Segment），通过锁分离技术实现更细粒度的并发控制。

```java
// JDK7 ConcurrentHashMap 核心结构示意
public class ConcurrentHashMap<K, V> extends AbstractMap<K, V> 
        implements ConcurrentMap<K, V>, Serializable {
    
    // 分段数组 - 每个Segment独立加锁
    final Segment<K,V>[] segments;
    
    // 每个Segment内部是一个哈希表
    static final class Segment<K,V> extends ReentrantLock {
        // Segment内部的HashEntry数组
        transient volatile HashEntry<K,V>[] table;
        // Segment元素计数
        transient int count;
    }
    
    // 哈希表节点
    static final class HashEntry<K,V> {
        final int hash;
        final K key;
        volatile V value;
        volatile HashEntry<K,V> next;
    }
}
```

### 1.2 分段锁实现细节

#### 1.2.1 数据结构设计
- **默认分段数**：16（可通过构造函数指定）
- **每个Segment**：独立的ReentrantLock锁 + HashEntry数组
- **锁粒度**：针对单个Segment操作需要获取该Segment的独占锁

#### 1.2.2 关键操作实现

**put操作流程**：
```java
public V put(K key, V value) {
    // 1. 计算key的hash值
    int hash = hash(key);
    // 2. 根据hash定位到对应的Segment
    int segmentIndex = (hash >>> segmentShift) & segmentMask;
    Segment<K,V> segment = ensureSegment(segmentIndex);
    // 3. 调用Segment的put方法（内部加锁）
    return segment.put(key, hash, value, false);
}

// Segment内部put方法
final V put(K key, int hash, V value, boolean onlyIfAbsent) {
    // 获取该Segment的锁
    HashEntry<K,V> node = tryLock() ? null : scanAndLockForPut(key, hash, value);
    try {
        // 在锁保护下执行插入操作
        HashEntry<K,V>[] tab = table;
        int index = (tab.length - 1) & hash;
        HashEntry<K,V> first = entryAt(tab, index);
        
        // 遍历链表，查找key是否已存在
        for (HashEntry<K,V> e = first;;) {
            if (e != null) {
                K k;
                if ((k = e.key) == key || (e.hash == hash && key.equals(k))) {
                    // 更新现有值
                    V oldValue = e.value;
                    if (!onlyIfAbsent) {
                        e.value = value;
                        ++modCount;
                    }
                    return oldValue;
                }
                e = e.next;
            } else {
                // 插入新节点
                if (node != null)
                    node.setNext(first);
                else
                    node = new HashEntry<K,V>(hash, key, value, first);
                int c = count + 1;
                if (c > threshold && tab.length < MAXIMUM_CAPACITY)
                    rehash(node); // 扩容
                else
                    setEntryAt(tab, index, node);
                ++modCount;
                count = c;
                return null;
            }
        }
    } finally {
        // 释放锁
        unlock();
    }
}
```

**get操作特点**：
- 不需要加锁（value使用volatile保证可见性）
- 弱一致性：可能读取到稍旧的数据

### 1.3 分段锁的优缺点

#### 优势：
1. **并发度可预测**：并发度等于Segment数量（默认16）
2. **锁竞争减少**：不同Segment操作互不干扰
3. **读操作无锁**：通过volatile保证可见性，读性能高

#### 局限性：
1. **锁粒度过粗**：一个Segment内所有操作串行化
2. **内存开销大**：每个Segment独立维护数组和计数器
3. **扩容效率低**：Segment独立扩容，无法整体协调
4. **哈希冲突处理**：链表过长时性能下降

## 二、JDK8 CAS+synchronized实现机制

### 2.1 设计哲学转变

JDK8对ConcurrentHashMap进行了彻底重构，摒弃分段锁模式，采用：
- **CAS（Compare And Swap）**：用于无锁化的状态控制和计数器更新
- **synchronized**：仅锁住单个哈希桶（链表头/红黑树根节点）
- **红黑树优化**：链表长度超过阈值时转换为红黑树

### 2.2 核心数据结构

```java
// JDK8 ConcurrentHashMap 核心结构
public class ConcurrentHashMap<K,V> extends AbstractMap<K,V>
    implements ConcurrentMap<K,V>, Serializable {
    
    // 核心哈希表数组
    transient volatile Node<K,V>[] table;
    
    // 扩容时使用的下一张表
    private transient volatile Node<K,V>[] nextTable;
    
    // 基础计数器，通过CAS更新
    private transient volatile long baseCount;
    
    // 控制标识符，用于扩容、初始化等
    private transient volatile int sizeCtl;
    
    // 节点定义
    static class Node<K,V> implements Map.Entry<K,V> {
        final int hash;
        final K key;
        volatile V val;
        volatile Node<K,V> next;
    }
    
    // 红黑树节点
    static final class TreeNode<K,V> extends Node<K,V> {
        TreeNode<K,V> parent;  // red-black tree links
        TreeNode<K,V> left;
        TreeNode<K,V> right;
        TreeNode<K,V> prev;    // needed to unlink next upon deletion
        boolean red;
    }
    
    // 转换期间的包装节点
    static final class TreeBin<K,V> extends Node<K,V> {
        TreeNode<K,V> root;
        volatile TreeNode<K,V> first;
        volatile Thread waiter;
        volatile int lockState;
    }
}
```

### 2.3 CAS+synchronized实现细节

#### 2.3.1 关键状态控制

**sizeCtl字段的多重含义**：
- `-1`：表正在初始化
- `-N`：有N-1个线程正在进行扩容
- `0`：默认值
- `>0`：下一次扩容的阈值或初始表大小

#### 2.3.2 put操作实现

```java
final V putVal(K key, V value, boolean onlyIfAbsent) {
    if (key == null || value == null) throw new NullPointerException();
    
    // 1. 计算hash值（优化散列）
    int hash = spread(key.hashCode());
    int binCount = 0;
    
    // 2. 自旋插入（CAS失败时重试）
    for (Node<K,V>[] tab = table;;) {
        Node<K,V> f; int n, i, fh;
        
        // 延迟初始化表
        if (tab == null || (n = tab.length) == 0)
            tab = initTable();
        
        // 3. 定位桶位置，如果为空则CAS插入
        else if ((f = tabAt(tab, i = (n - 1) & hash)) == null) {
            // 使用CAS尝试设置新节点
            if (casTabAt(tab, i, null, new Node<K,V>(hash, key, value, null)))
                break; // 插入成功，退出循环
        }
        
        // 4. 检测到扩容标记，帮助扩容
        else if ((fh = f.hash) == MOVED)
            tab = helpTransfer(tab, f);
        
        // 5. 桶不为空，需要锁住桶头节点
        else {
            V oldVal = null;
            synchronized (f) { // 锁住单个桶
                if (tabAt(tab, i) == f) { // 双重检查
                    // 链表情况
                    if (fh >= 0) {
                        binCount = 1;
                        for (Node<K,V> e = f;; ++binCount) {
                            K ek;
                            // 找到相同key，更新值
                            if (e.hash == hash && ((ek = e.key) == key || 
                                (ek != null && key.equals(ek)))) {
                                oldVal = e.val;
                                if (!onlyIfAbsent)
                                    e.val = value;
                                break;
                            }
                            Node<K,V> pred = e;
                            // 到达链表尾部，插入新节点
                            if ((e = e.next) == null) {
                                pred.next = new Node<K,V>(hash, key, value, null);
                                break;
                            }
                        }
                    }
                    // 红黑树情况
                    else if (f instanceof TreeBin) {
                        Node<K,V> p;
                        binCount = 2;
                        // 红黑树插入
                        if ((p = ((TreeBin<K,V>)f).putTreeVal(hash, key, value)) != null) {
                            oldVal = p.val;
                            if (!onlyIfAbsent)
                                p.val = value;
                        }
                    }
                }
            }
            
            // 6. 检查是否需要树化
            if (binCount != 0) {
                if (binCount >= TREEIFY_THRESHOLD)
                    treeifyBin(tab, i);
                if (oldVal != null)
                    return oldVal;
                break;
            }
        }
    }
    
    // 7. 使用LongAdder风格计数器更新size
    addCount(1L, binCount);
    return null;
}
```

#### 2.3.3 计数器实现（LongAdder风格）

```java
// 分段计数，减少CAS竞争
private final void addCount(long x, int check) {
    CounterCell[] as; long b, s;
    
    // 尝试直接更新baseCount
    if ((as = counterCells) != null ||
        !U.compareAndSwapLong(this, BASECOUNT, b = baseCount, s = b + x)) {
        
        CounterCell a; long v; int m;
        boolean uncontended = true;
        
        // 如果更新baseCount失败，使用CounterCell数组
        if (as == null || (m = as.length - 1) < 0 ||
            (a = as[ThreadLocalRandom.getProbe() & m]) == null ||
            !(uncontended = U.compareAndSwapLong(a, CELLVALUE, v = a.value, v + x))) {
            
            // 创建或扩容CounterCell数组
            fullAddCount(x, uncontended);
            return;
        }
        if (check <= 1)
            return;
        s = sumCount();
    }
    
    // 检查是否需要扩容
    if (check >= 0) {
        Node<K,V>[] tab, nt; int n, sc;
        while (s >= (long)(sc = sizeCtl) && (tab = table) != null &&
               (n = tab.length) < MAXIMUM_CAPACITY) {
            int rs = resizeStamp(n);
            if (sc < 0) {
                if ((sc >>> RESIZE_STAMP_SHIFT) != rs || sc == rs + 1 ||
                    sc == rs + MAX_RESIZERS || (nt = nextTable) == null ||
                    transferIndex <= 0)
                    break;
                // 帮助扩容
                if (U.compareAndSwapInt(this, SIZECTL, sc, sc + 1))
                    transfer(tab, nt);
            }
            // 发起扩容
            else if (U.compareAndSwapInt(this, SIZECTL, sc, (rs << RESIZE_STAMP_SHIFT) + 2))
                transfer(tab, null);
            s = sumCount();
        }
    }
}
```

### 2.4 扩容机制（并发扩容）

JDK8支持多线程并发扩容，每个线程负责一部分桶的迁移：

```java
private final void transfer(Node<K,V>[] tab, Node<K,V>[] nextTab) {
    int n = tab.length, stride;
    
    // 计算每个线程处理的桶区间
    if ((stride = (NCPU > 1) ? (n >>> 3) / NCPU : n) < MIN_TRANSFER_STRIDE)
        stride = MIN_TRANSFER_STRIDE;
    
    // 初始化扩容目标表
    if (nextTab == null) {
        try {
            @SuppressWarnings("unchecked")
            Node<K,V>[] nt = (Node<K,V>[])new Node<?,?>[n << 1];
            nextTab = nt;
        } catch (Throwable ex) {
            sizeCtl = Integer.MAX_VALUE;
            return;
        }
        nextTable = nextTab;
        transferIndex = n;
    }
    
    // 并发迁移：每个线程处理一个桶区间
    // 使用ForwardingNode标记已迁移的桶
}
```

## 三、两种实现对比分析

### 3.1 锁粒度对比

| 特性 | JDK7分段锁 | JDK8 CAS+synchronized |
|------|-----------|----------------------|
| **锁粒度** | Segment级别（默认16个锁） | 单个哈希桶级别（数千个锁） |
| **并发度** | 固定（Segment数量） | 动态（与哈希桶数量相关） |
| **锁竞争** | Segment内竞争 | 仅相同哈希桶竞争 |

### 3.2 内存效率对比

| 维度 | JDK7 | JDK8 |
|------|------|------|
| **数据结构** | Segment数组 + HashEntry数组 × 16 | 单一Node数组 |
| **额外开销** | 每个Segment的ReentrantLock对象 | 少量控制状态字段 |
| **节点大小** | HashEntry（4字段） | Node（4字段），TreeNode更多 |

### 3.3 性能特征对比

#### 读操作：
- **JDK7**：完全无锁，volatile读，性能极高
- **JDK8**：同样无锁，但数据结构更复杂（可能需要遍历树）

#### 写操作：
- **JDK7**：需要获取Segment锁，竞争激烈时阻塞
- **JDK8**：CAS尝试失败后才使用synchronized，减少锁竞争

#### 扩容操作：
- **JD7**：各Segment独立扩容，无法并行
- **JD8**：多线程并发扩容，效率大幅提升

### 3.4 哈希冲突处理

| 实现 | 链表阈值 | 树化阈值 | 退化阈值 |
|------|---------|---------|---------|
| JDK7 | 无限制 | 不支持红黑树 | 不适用 |
| JDK8 | 8 | 链表长度≥8且table.length≥64 | 树节点≤6时退化为链表 |

## 四、实际应用建议

### 4.1 版本选择考虑

1. **JDK7适用场景**：
   - 读操作极其频繁，写操作较少
   - 并发度要求不高（小于Segment数量）
   - 内存相对充裕

2. **JDK8优势场景**：
   - 高并发写操作
   - 哈希冲突较严重的情况
   - 内存敏感的应用
   - 需要更好扩容性能

### 4.2 性能调优建议

**JDK8参数调整**：
```java
// 初始容量（避免频繁扩容）
ConcurrentHashMap<String, Object> map = 
    new ConcurrentHashMap<>(initialCapacity);

// 并发级别（兼容性参数，JDK8实际不使用）
ConcurrentHashMap<String, Object> map = 
    new ConcurrentHashMap<>(initialCapacity, loadFactor, concurrencyLevel);
```

**避免热点桶**：
- 确保键的hashCode()分布均匀
- 考虑自定义哈希策略

### 4.3 线程安全使用注意事项

1. **复合操作仍需同步**：
```java
// 不安全：check-then-act
if (!map.containsKey(key)) {
    map.put(key, value); // 仍可能被其他线程插入
}

// 安全：使用putIfAbsent
V oldValue = map.putIfAbsent(key, value);
```

2. **迭代器弱一致性**：
   - 迭代过程中可能反映其他线程的修改
   - 不保证迭代时数据的绝对一致性

## 五、演进背后的设计思想

### 5.1 技术发展趋势

1. **锁优化**：从粗粒度锁 → 细粒度锁 → 无锁CAS
2. **数据结构**：简单链表 → 链表+红黑树混合
3. **并发控制**：静态分区 → 动态自适应

### 5.2 硬件适配考虑

- **CAS优势**：现代CPU对CAS指令优化良好
- **缓存友好**：JDK8设计更符合CPU缓存行特性
- **NUMA优化**：减少跨节点内存访问

## 六、总结

JDK7的分段锁和JDK8的CAS+synchronized代表了ConcurrentHashMap的两个重要发展阶段：

1. **分段锁设计**通过空间换时间，以固定分段数换取并发度，适合读多写少的场景。

2. **CAS+synchronized设计**则更加精细和动态：
   - 使用CAS实现无锁化状态控制
   - 将锁粒度细化到单个哈希桶
   - 引入红黑树优化极端哈希冲突
   - 支持多线程并发扩容

从性能角度看，JDK8实现在大多数场景下优于JDK7，特别是在高并发写入、哈希冲突严重和需要频繁扩容的情况下。然而，JDK7的完全无锁读操作在特定场景下仍有优势。

在实际开发中，建议使用JDK8及更高版本，除非有特殊兼容性要求。理解这两种实现机制的差异，有助于开发者更好地使用ConcurrentHashMap，并在必要时进行针对性调优。

---

## 参考资料

1. Oracle官方文档：ConcurrentHashMap JavaDoc
2. JDK源码：java.util.concurrent.ConcurrentHashMap
3. Doug Lea并发编程系列文章
4. Java性能权威指南（第2版）
5. JEP 155: Concurrency Updates（Java 8并发改进）