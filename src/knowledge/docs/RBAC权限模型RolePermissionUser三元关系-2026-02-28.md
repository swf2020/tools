# RBAC权限模型技术文档

## 1. 概述
基于角色的访问控制（Role-Based Access Control，简称RBAC）是一种广泛应用于系统权限管理的模型。其核心思想是将用户（User）、角色（Role）和权限（Permission）解耦，通过角色作为中间桥梁，实现灵活、可扩展的权限管理体系。

---

## 2. 核心概念与关系

### 2.1 三元关系定义

```
User (用户) -- 分配 --> Role (角色) -- 关联 --> Permission (权限)
```

1. **用户（User）**：系统的使用者，如员工、管理员等。
2. **角色（Role）**：权限的集合，代表一类职责或岗位，如“管理员”、“编辑员”、“访客”等。
3. **权限（Permission）**：对系统资源（如页面、接口、数据）的操作许可，通常由“资源+操作”构成，例如：
   - `user:create`（创建用户）
   - `article:delete`（删除文章）
   - `report:view`（查看报表）

### 2.2 关键关系

- **用户-角色关系（User-Role Assignment）**：多对多关系，一个用户可拥有多个角色，一个角色可分配给多个用户。
- **角色-权限关系（Role-Permission Assignment）**：多对多关系，一个角色可包含多个权限，一个权限可授予多个角色。
- **用户-权限关系（间接）**：用户通过角色间接获得权限，避免直接绑定，提高管理效率。

---

## 3. 核心优势

1. **简化权限管理**：只需调整角色权限，即可批量更新用户权限。
2. **职责分离**：角色按职责定义，符合企业组织架构。
3. **最小权限原则**：用户仅拥有完成任务所需的最小权限集。
4. **易于审计**：通过角色追溯权限分配，便于合规检查。

---

## 4. 数据库设计示例

### 4.1 表结构
```sql
-- 用户表
CREATE TABLE user (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    -- 其他业务字段...
);

-- 角色表
CREATE TABLE role (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    code VARCHAR(50) UNIQUE NOT NULL, -- 角色编码，如 ADMIN
    name VARCHAR(100) NOT NULL,        -- 角色名称
    description VARCHAR(255)
);

-- 权限表
CREATE TABLE permission (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    resource VARCHAR(100) NOT NULL,   -- 资源标识，如 user, article
    action VARCHAR(50) NOT NULL,      -- 操作类型，如 create, delete
    UNIQUE KEY uk_resource_action (resource, action)
);

-- 用户-角色关联表
CREATE TABLE user_role (
    user_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    PRIMARY KEY (user_id, role_id),
    FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE,
    FOREIGN KEY (role_id) REFERENCES role(id) ON DELETE CASCADE
);

-- 角色-权限关联表
CREATE TABLE role_permission (
    role_id BIGINT NOT NULL,
    permission_id BIGINT NOT NULL,
    PRIMARY KEY (role_id, permission_id),
    FOREIGN KEY (role_id) REFERENCES role(id) ON DELETE CASCADE,
    FOREIGN KEY (permission_id) REFERENCES permission(id) ON DELETE CASCADE
);
```

### 4.2 数据示例
```sql
-- 权限数据
INSERT INTO permission (resource, action) VALUES
('user', 'create'),
('user', 'view'),
('article', 'edit'),
('article', 'delete');

-- 角色数据
INSERT INTO role (code, name) VALUES
('ADMIN', '系统管理员'),
('EDITOR', '内容编辑员');

-- 关联数据：管理员拥有所有权限
INSERT INTO role_permission (role_id, permission_id)
SELECT r.id, p.id FROM role r, permission p WHERE r.code = 'ADMIN';

-- 关联数据：编辑员仅拥有文章编辑权限
INSERT INTO role_permission (role_id, permission_id)
SELECT r.id, p.id FROM role r, permission p 
WHERE r.code = 'EDITOR' AND p.resource = 'article' AND p.action = 'edit';
```

---

## 5. 权限校验流程

```python
def check_permission(user_id: int, required_permission: str) -> bool:
    """
    检查用户是否拥有指定权限
    :param user_id: 用户ID
    :param required_permission: 所需权限（格式：resource:action）
    :return: 是否拥有权限
    """
    # 查询用户所有角色关联的权限
    permissions = db.query("""
        SELECT p.resource, p.action 
        FROM user_role ur
        JOIN role_permission rp ON ur.role_id = rp.role_id
        JOIN permission p ON rp.permission_id = p.id
        WHERE ur.user_id = %s
    """, (user_id,))
    
    # 构造权限字符串集合
    user_permissions = {f"{p.resource}:{p.action}" for p in permissions}
    
    return required_permission in user_permissions
```

---

## 6. 扩展模式

### 6.1 角色继承（Role Hierarchy）
- 支持角色间的继承关系，如：
  ```
  超级管理员 → 管理员 → 普通用户
  ```
- 高级角色自动继承低级角色的所有权限。

### 6.2 会话管理（Session）
- 用户登录后创建会话，可激活部分角色。
- 支持动态角色切换（如临时提升权限）。

### 6.3 约束规则（Constraints）
- **互斥角色**：同一用户不能同时拥有互斥角色（如“会计”与“出纳”）。
- **基数约束**：限制角色分配数量（如“超级管理员”最多3人）。

---

## 7. 最佳实践

1. **粒度控制**：权限粒度不宜过细，避免管理复杂度激增。
2. **角色标准化**：基于组织实际职责定义角色，避免随意创建。
3. **定期审计**：周期性检查角色权限分配，清理无效配置。
4. **结合属性**：在复杂场景中，可结合ABAC（基于属性的访问控制）进行补充。

---

## 8. 常见问题

**Q1：如何处理临时权限？**
- 方案：通过临时角色或基于时间的权限分配实现。

**Q2：用户量巨大时如何优化性能？**
- 方案：缓存用户权限集合，采用增量更新策略。

**Q3：如何支持数据级权限控制？**
- 方案：RBAC控制功能权限，数据权限通过业务逻辑或ABAC扩展实现。

---

## 9. 总结
RBAC模型通过清晰的“用户-角色-权限”三元关系，实现了权限管理的规范化与自动化。在设计系统时，应结合业务需求选择合适的扩展模式，并建立配套的权限审计机制，确保系统安全与可维护性。

---

*文档版本：v1.1  
最后更新日期：2023年10月*