# TCC分布式事务：空回滚与悬挂问题处理方案

## 1. 概述

TCC（Try-Confirm-Cancel）是一种广泛应用于分布式系统的柔性事务解决方案。在实际应用中，由于网络延迟、服务重启等因素，会出现**空回滚（Empty Cancel）**和**悬挂（Hanging）**两大核心问题。本文将深入分析这两个问题的成因，并提供完整的解决方案。

## 2. 核心问题分析

### 2.1 空回滚问题

**定义**：当Try阶段未执行，但Cancel阶段却被触发执行的现象。

**场景示例**：
```
┌─────────┐    ┌─────────┐    ┌─────────┐
│  业务   │    │  TCC A  │    │  TCC B  │
│  发起方 │    │ (主业务)│    │(子业务) │
└─────────┘    └─────────┘    └─────────┘
      │             │              │
      │ 1.调用Try() │              │
      │───────────>│              │
      │             │              │
      │             │ 2.调用Try()  │
      │             │─────────────>│
      │             │   网络超时   │
      │             │<─────────────│
      │  3.触发Cancel()           │
      │───────────>│              │
      │             │ 4.调用Cancel() │
      │             │─────────────>│
      │             │              │ ❌ B的Try未执行，Cancel却执行了
```

**根本原因**：
- 网络延迟导致Try请求实际未到达服务B
- 服务B因超时未返回，但事务协调器已记录事务状态
- 触发全局回滚时，服务B收到Cancel请求

### 2.2 悬挂问题

**定义**：Cancel先于Try执行，导致Try永远无法被正常处理。

**场景示例**：
```
┌─────────┐    ┌─────────┐    ┌─────────┐
│  业务   │    │  TCC A  │    │  TCC B  │
│  发起方 │    │ (主业务)│    │(子业务) │
└─────────┘    └─────────┘    └─────────┘
      │             │              │
      │ 1.调用Try() │              │
      │───────────>│              │
      │             │              │
      │             │ 2.调用Try()  │
      │             │─────────────>│
      │             │              │ 网络阻塞
      │  3.触发Cancel()           │
      │───────────>│              │
      │             │ 4.调用Cancel() │
      │             │─────────────>│
      │             │              │ ✅ Cancel执行成功
      │             │              │
      │             │              │ 5.Try请求到达
      │             │<─────────────│
      │             │              │ ❌ Try在Cancel后执行，数据不一致
```

**根本原因**：
- Try请求因网络拥堵延迟到达
- 上层已触发Cancel且执行成功
- 延迟的Try请求到达后仍执行，破坏数据一致性

## 3. 解决方案设计

### 3.1 总体设计原则

```
┌─────────────────────────────────────────┐
│           事务状态追踪器                 │
│  ┌─────────────────────────────────┐  │
│  │ 事务日志表(tcc_transaction_log) │  │
│  │ • transaction_id (PK)           │  │
│  │ • branch_id                     │  │
│  │ • status                        │  │
│  │ • created_time                  │  │
│  │ • updated_time                  │  │
│  └─────────────────────────────────┘  │
└─────────────────────────────────────────┘
                    │
    ┌───────────────┼───────────────┐
    │               │               │
┌───▼────┐    ┌────▼────┐    ┌────▼────┐
│ Try阶段 │    │Confirm阶段│   │Cancel阶段│
│ -前置检查│    │-幂等检查 │   │-空回滚检查│
│ -状态记录│    │-状态校验 │   │-悬挂防护 │
└─────────┘    └─────────┘   └─────────┘
```

### 3.2 关键技术实现

#### 3.2.1 事务状态记录表设计

```sql
CREATE TABLE tcc_transaction_log (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    transaction_id VARCHAR(64) NOT NULL COMMENT '全局事务ID',
    branch_id VARCHAR(64) NOT NULL COMMENT '分支事务ID',
    status TINYINT NOT NULL COMMENT '状态：1-Trying, 2-Confirmed, 3-Cancelled',
    business_id VARCHAR(64) COMMENT '业务唯一标识',
    created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_transaction_branch (transaction_id, branch_id),
    KEY idx_business_id (business_id)
) ENGINE=InnoDB COMMENT='TCC事务状态记录表';
```

#### 3.2.2 空回滚防护方案

**实现逻辑**：
```java
@Component
public class TccCancelProcessor {
    
    @Resource
    private TransactionLogDAO transactionLogDAO;
    
    /**
     * 防空回滚的Cancel执行
     */
    @Transactional(rollbackFor = Exception.class)
    public void cancelWithProtection(String transactionId, String branchId) {
        // 1. 查询事务状态
        TransactionLog log = transactionLogDAO.selectByTxAndBranch(
            transactionId, branchId);
        
        // 2. 空回滚判断
        if (log == null) {
            // 记录空回滚日志
            TransactionLog emptyLog = new TransactionLog();
            emptyLog.setTransactionId(transactionId);
            emptyLog.setBranchId(branchId);
            emptyLog.setStatus(TransactionStatus.CANCELLED.getCode());
            emptyLog.setCreatedTime(new Date());
            transactionLogDAO.insert(emptyLog);
            
            // 空回滚只需记录，不执行业务逻辑
            log.info("检测到空回滚，事务ID: {}, 分支ID: {}", 
                     transactionId, branchId);
            return;
        }
        
        // 3. 幂等性检查
        if (TransactionStatus.CANCELLED.getCode().equals(log.getStatus())) {
            log.info("Cancel已执行，直接返回，事务ID: {}", transactionId);
            return;
        }
        
        // 4. 状态校验
        if (!TransactionStatus.TRYING.getCode().equals(log.getStatus())) {
            throw new IllegalStateException(
                String.format("非法事务状态: %s，期望: TRYING", log.getStatus()));
        }
        
        // 5. 执行业务Cancel逻辑
        try {
            businessService.cancel(transactionId, branchId);
            
            // 6. 更新状态
            transactionLogDAO.updateStatus(
                transactionId, branchId, 
                TransactionStatus.CANCELLED.getCode());
                
        } catch (Exception e) {
            log.error("Cancel执行失败，事务ID: {}", transactionId, e);
            throw e;
        }
    }
}
```

#### 3.2.3 悬挂防护方案

**Try阶段防护**：
```java
@Component
public class TccTryProcessor {
    
    @Resource
    private TransactionLogDAO transactionLogDAO;
    
    /**
     * 防悬挂的Try执行
     */
    @Transactional(rollbackFor = Exception.class)
    public boolean tryWithProtection(String transactionId, 
                                     String branchId, 
                                     BusinessRequest request) {
        // 1. 悬挂检查：Cancel是否已执行
        TransactionLog existingLog = transactionLogDAO
            .selectByTxAndBranch(transactionId, branchId);
            
        if (existingLog != null) {
            if (TransactionStatus.CANCELLED.getCode()
                .equals(existingLog.getStatus())) {
                // Cancel已执行，拒绝Try操作
                log.warn("检测到悬挂，拒绝Try操作，事务ID: {}, 分支ID: {}", 
                         transactionId, branchId);
                return false;
            }
            
            // 幂等处理
            if (TransactionStatus.TRYING.getCode()
                .equals(existingLog.getStatus())) {
                log.info("Try已执行，幂等返回");
                return true;
            }
        }
        
        // 2. 执行业务Try逻辑
        try {
            // 业务资源预留
            boolean tryResult = businessService.tryReserve(
                transactionId, branchId, request);
                
            if (!tryResult) {
                return false;
            }
            
            // 3. 记录Try状态
            TransactionLog log = new TransactionLog();
            log.setTransactionId(transactionId);
            log.setBranchId(branchId);
            log.setStatus(TransactionStatus.TRYING.getCode());
            log.setBusinessId(request.getBusinessId());
            log.setCreatedTime(new Date());
            transactionLogDAO.insert(log);
            
            return true;
            
        } catch (Exception e) {
            log.error("Try执行失败，事务ID: {}", transactionId, e);
            throw new RuntimeException("Try阶段失败", e);
        }
    }
}
```

### 3.3 超时与重试机制

```yaml
# application.yml 配置示例
tcc:
  config:
    # 超时配置
    timeout:
      try: 3000    # Try阶段超时(ms)
      confirm: 5000 # Confirm阶段超时
      cancel: 5000  # Cancel阶段超时
    
    # 重试配置
    retry:
      max-attempts: 3     # 最大重试次数
      initial-interval: 1000 # 初始间隔(ms)
      multiplier: 1.5     # 间隔乘数
      max-interval: 10000 # 最大间隔(ms)
    
    # 悬挂检测
    hanging:
      check-interval: 60000 # 悬挂检查间隔(ms)
      ttl: 86400000        # 事务记录TTL(24小时)
```

## 4. 完整处理流程

### 4.1 正常流程
```
┌───────┐    ┌─────────┐    ┌─────────┐    ┌────────────┐
│调用方  │    │服务A(Try)│    │服务B(Try)│    │事务日志     │
└───────┘    └─────────┘    └─────────┘    └────────────┘
    │             │              │               │
    │ 1.发起事务   │              │               │
    │───────────> │              │               │
    │             │ 2.Try        │               │
    │             │─────────────>│               │
    │             │              │ 3.记录Try日志  │
    │             │              │──────────────>│
    │             │              │               │
    │ 4.Confirm/Cancel           │               │
    │───────────> │              │               │
    │             │ 5.Confirm/Cancel             │
    │             │─────────────>│               │
    │             │              │ 6.更新状态日志 │
    │             │              │──────────────>│
```

### 4.2 异常处理流程
```
┌───────┐    ┌─────────┐    ┌─────────┐    ┌────────────┐
│调用方  │    │服务A(Try)│    │服务B(Try)│    │事务日志     │
└───────┘    └─────────┘    └─────────┘    └────────────┘
    │             │              │               │
    │ 1.发起事务   │              │               │
    │───────────> │              │               │
    │             │ 2.Try(超时)   │               │
    │             │─────────────>│  网络问题      │
    │             │              │               │
    │ 3.触发Cancel │              │               │
    │───────────> │              │               │
    │             │ 4.查询日志    │               │
    │             │───────────────┐              │
    │             │<──────────────┘              │
    │             │ 5.空回滚处理   │               │
    │             │─────────────>│               │
    │             │              │ 6.记录空回滚日志│
    │             │              │──────────────>│
    │             │              │               │
    │             │              │ 7.Try延迟到达 │
    │             │<─────────────│               │
    │             │ 8.悬挂检查    │               │
    │             │───────────────┐              │
    │             │<──────────────┘              │
    │             │ 9.拒绝执行    │               │
```

## 5. 监控与运维建议

### 5.1 关键监控指标
- 空回滚发生率：`空回滚次数 / 总Cancel次数`
- 悬挂发生率：`悬挂拒绝次数 / 总Try次数`
- 事务成功率：`成功事务数 / 总事务数`
- 平均处理时间：各阶段耗时统计

### 5.2 日志规范
```java
@Slf4j
@Component
public class TccMonitor {
    
    // 关键节点日志记录
    public void logTransactionEvent(String transactionId, 
                                   String branchId,
                                   String phase, 
                                   String status,
                                   long costTime) {
        log.info("TCC事务事件 | txId:{} | branch:{} | phase:{} | "
                + "status:{} | cost:{}ms",
                transactionId, branchId, phase, status, costTime);
        
        // 指标上报
        Metrics.counter("tcc_transaction_total",
                "phase", phase,
                "status", status).increment();
        
        Metrics.histogram("tcc_phase_duration",
                "phase", phase).record(costTime);
    }
}
```

### 5.3 运维脚本示例
```sql
-- 查询悬挂事务
SELECT * FROM tcc_transaction_log 
WHERE status = 1  -- TRYING状态
  AND created_time < DATE_SUB(NOW(), INTERVAL 5 MINUTE)
  AND NOT EXISTS (
    SELECT 1 FROM tcc_transaction_log t2 
    WHERE t2.transaction_id = tcc_transaction_log.transaction_id
      AND t2.status IN (2, 3)  -- 没有Confirm或Cancel记录
  );

-- 清理过期事务数据
DELETE FROM tcc_transaction_log 
WHERE created_time < DATE_SUB(NOW(), INTERVAL 7 DAY);
```

## 6. 总结

TCC事务中的空回滚和悬挂问题是分布式系统必然面对的挑战。通过本文提出的解决方案：

1. **空回滚防护**：通过前置状态检查，识别并记录空回滚，避免无效业务操作
2. **悬挂防护**：在Try阶段检查Cancel状态，防止后到的Try破坏数据一致性
3. **幂等性保证**：所有阶段都需要支持幂等操作，确保重试安全
4. **状态可追溯**：完整的事务日志记录是问题诊断的基础

实际实施中，建议结合具体的业务场景调整超时时间和重试策略，并在预发环境充分测试异常场景。良好的监控和告警机制能够帮助快速发现和定位问题，确保分布式事务的最终一致性。

## 附录：核心状态机

```
                    ┌──────────────┐
                    │   INITIAL    │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │    TRYING    │◄─────────────────┐
                    └──────┬───────┘                  │
                           │                          │
         ┌─────────────────┼─────────────────┐        │
         │                 │                 │        │
    ┌────▼─────┐    ┌─────▼──────┐    ┌─────▼────┐   │
    │ CONFIRMED│    │ CANCELLED  │    │ HANGING  │   │
    └──────────┘    └────────────┘    └──────────┘   │
         │                 │                          │
         └─────────────────┼──────────────────────────┘
                           │
                    ┌──────▼───────┐
                    │   COMPLETED  │
                    └──────────────┘

状态转换规则：
1. INITIAL → TRYING: Try阶段开始
2. TRYING → CONFIRMED: Confirm成功
3. TRYING → CANCELLED: Cancel成功
4. TRYING → HANGING: Try在Cancel后到达(异常)
5. 所有状态 → COMPLETED: 事务完成清理
```

通过以上方案，可以有效解决TCC事务中的空回滚和悬挂问题，保障分布式系统的事务一致性。