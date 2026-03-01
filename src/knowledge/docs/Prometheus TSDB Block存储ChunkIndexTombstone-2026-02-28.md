## **Prometheus TSDB Block存储详解 (Chunk/Index/Tombstone)**

**摘要**：本文档深入解析Prometheus时序数据库(TSDB)的核心存储结构——Block（块），重点剖析其内部三大关键组成部分：Chunk（数据块）、Index（索引）和Tombstone（墓碑文件）的设计原理、数据格式与交互机制。

---

### **1. 概述**

Prometheus TSDB将时序数据存储在磁盘上按时间维度划分的、不可变的**Block**中。每个Block代表一个特定时间范围内的所有数据（默认为2小时），并包含其自身的完整索引和数据文件。这种设计有利于数据压缩、备份和过期删除。

一个典型的Block目录结构如下：
```
<block-id>/
├── meta.json        # 块元信息
├── index            # 索引文件
├── chunks/          # 数据块目录
│   └── 000001       # 存储实际时序数据的连续chunk文件
└── tombstones       # 墓碑文件（记录数据删除操作）
```

### **2. Chunk (数据块)**

#### **2.1 作用与定位**
*   **核心数据载体**：`Chunk`是存储实际时序样本值（Timestamp-Value对）的基本单位。每个唯一的指标（Metric）+标签集（LabelSet）对应的时间序列（Time Series）在其生命周期内会由一系列`Chunk`组成。
*   **内存与磁盘的桥梁**：数据首先在内存中被组织成`Chunk`（称为“Head Chunk”），写满（通常为120个样本）或达到一定时间后，再被持久化到Block的`chunks`目录下。

#### **2.2 存储格式**
*   **目录结构**：在Block中，所有`Chunk`被连续地写入一个或多个文件（如`000001`, `000002`），存储在`chunks/`子目录下。这样做是为了减少小文件数量，提高I/O效率。
*   **内部编码**：每个`Chunk`内部采用高效的压缩编码格式，以减小存储空间。主要格式包括：
    *   **varbit**：早期的简单编码。
    *   **Promotion Delta**：历史编码。
    *   **XOR (异或编码)**：**当前默认且最高效的编码**。它利用相邻样本间Timestamp和Value的差值变化较小的特点，通过存储差值（Delta of Delta）和异或压缩值，实现高压缩比。
*   **寻址方式**：`Chunk`在文件中的位置通过`索引文件(Index)`进行映射。索引中存储的是该`Chunk`的引用（`chunks/`文件中的偏移量 `offset` 和长度 `size`）。

### **3. Index (索引文件)**

#### **3.1 作用与定位**
*   **数据查找的目录**：`Index`文件是Block的“百科全书目录”，它建立了从**指标名称（Metric Name）和标签（Label）** 到**实际数据存储位置（Chunk引用）** 的映射关系。没有索引，从海量数据中定位特定序列将极其低效。
*   **支持复杂查询**：它是实现PromQL中`{__name__="..."}`, `{label="value"}`, `{label!="value"}`等标签选择器（Label Selectors）查询的基础。

#### **3.2 核心数据结构**
`Index`文件是一个高度结构化、经过排序和压缩的二进制文件，主要包含以下部分（简化模型）：
1.  **符号表（Symbol Table）**：
    *   存储所有标签键（Label Key）和标签值（Label Value）的唯一字符串。
    *   后续部分通过引用符号表的ID来表示这些字符串，极大地节省了空间。
2.  **序列列表（Series List）**：
    *   每个时间序列（Series）对应一条记录。
    *   记录包含：
        *   **标签集（Label Set）**：该序列所有标签对的引用ID列表。
        *   **Chunk引用列表（Chunk References）**：该序列在本Block中所有`Chunk`的元数据数组，每个引用包含：
            *   `MinTime`, `MaxTime`：该Chunk覆盖的时间范围。
            *   `FileOffset`：指向`chunks/`文件中该Chunk起始位置的偏移量。
3.  **索引表（Index Tables）**：
    *   **标签值到序列的倒排索引（Postings）**：记录每个标签值（如`job="node_exporter"`）对应哪些序列ID。这是实现`{label="value"}`查询的核心。
    *   **指标名称到序列的索引**：特殊的倒排索引，用于`{__name__="http_requests_total"}`查询。
    *   **标签名索引**：加速获取所有不同标签名的操作。

#### **3.3 查询流程**
当查询`up{instance="localhost:9090"}`在某个时间范围内的数据时：
1.  定位到时间范围对应的Block。
2.  加载Block的`Index`，在内存中进行**mmap映射**（避免全量读入）。
3.  在**标签值倒排索引**中查找`instance="localhost:9090"`对应的序列ID列表（Posting List）。
4.  遍历这些序列ID，在**序列列表**中找到对应的记录，从中筛选出`Chunk引用列表`里时间范围与查询有交集的`Chunk`。
5.  根据`Chunk引用`中的`FileOffset`和`size`，去`chunks/`文件中精确读取相应的数据块。
6.  解码`Chunk`，获取其中的样本数据。

### **4. Tombstone (墓碑文件)**

#### **4.1 作用与定位**
*   **处理数据删除**：由于Block是**不可变（Immutable）** 的，当用户通过管理接口删除某些时间序列的特定时间范围数据时，无法直接修改已存在的Block。
*   **逻辑删除标记**：`Tombstone`文件记录了在该Block中需要被“逻辑删除”的数据范围。查询时，结果会经过Tombstone过滤。

#### **4.2 工作机制**
1.  **记录格式**：`Tombstone`文件通常包含一系列记录，每条记录由**序列ID**和**要删除的时间范围（MinTime, MaxTime）** 组成。
2.  **删除过程**：
    *   当删除请求触发时，TSDB会找到包含目标时间范围的Block。
    *   在该Block的`tombstones`文件中追加一条删除记录。
    *   **原始数据（Chunk）和索引（Index）本身不会被修改**。
3.  **查询过滤**：
    *   在查询该Block数据时，引擎会同时加载`Index`和`Tombstone`。
    *   当根据索引找到一系列`Chunk`引用后，会与Tombstone中对应序列的删除时间范围进行比较。
    *   如果某个`Chunk`的`[MinTime, MaxTime]`与删除范围有重叠，则该`Chunk`的数据要么被跳过，要么返回时剔除被删除部分。
4.  **物理清理**：
    *   在Block的**压缩（Compaction）** 过程中，多个Block会合并成一个新的、更大的Block。
    *   在新Block的生成过程中，会读取旧Block的数据，并**忽略所有被Tombstone标记删除的数据**。因此，Tombstone中的删除操作在Compaction后得到**物理生效**，新Block中将不再包含已删除数据，旧Block随后可被安全删除。

### **5. 总结与协作关系**

| 组件 | 核心功能 | 可变性 | 生命周期 |
| :--- | :--- | :--- | :--- |
| **Chunk** | **存储**原始时序样本数据。 | Block内不可变 | 内存中创建 -> 持久化到Block -> 被查询读取 -> 可能因Tombstone被过滤 -> 在Compaction中被清理或重组。 |
| **Index** | **映射**标签到数据位置的索引。 | Block内不可变 | 随Block创建而生成；查询时被加载（mmap）；Compaction时重建。 |
| **Tombstone** | **标记**待删除的数据范围。 | **可追加**（逻辑删除） | 删除请求触发时写入；查询时用于过滤；Compaction时生效并物理清除。 |

**三者的协作流程**：
1.  **写入**：样本流入，在Head Block形成`Chunk`，并更新内存中的索引结构。
2.  **持久化**：Head Block成熟后，其`Chunk`数据写入磁盘，并生成最终的`Index`文件，形成一个**不可变Block**。
3.  **删除**：删除请求在该Block的`Tombstone`文件中添加记录。
4.  **查询**：结合`Index`定位数据，读取`Chunk`，并用`Tombstone`过滤结果。
5.  **压缩**：合并多个Block时，依据`Index`找到所有`Chunk`，结合`Tombstone`过滤已删除数据，写入新的`Chunk`和`Index`，生成一个干净的、不含删除标记的新Block。

通过`Chunk`、`Index`和`Tombstone`的精密配合，Prometheus TSDB在保证高吞吐量写入和高性能查询的同时，巧妙地实现了对不可变数据的删除和管理，形成了其强大而稳定的存储引擎基石。