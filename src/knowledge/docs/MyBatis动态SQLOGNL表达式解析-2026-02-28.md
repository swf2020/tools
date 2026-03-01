# MyBatis动态SQL中的OGNL表达式解析技术文档

## 1. 概述

### 1.1 文档目的
本文档详细解析MyBatis动态SQL中OGNL（Object-Graph Navigation Language）表达式的使用原理、语法规则、应用场景及最佳实践，为开发者提供全面的技术参考。

### 1.2 核心概念
- **OGNL表达式**：对象图导航语言，用于在MyBatis中访问和操作Java对象属性
- **动态SQL**：MyBatis根据运行时条件动态生成SQL语句的机制
- **表达式解析**：MyBatis将OGNL表达式转换为实际值的过程

## 2. OGNL基础

### 2.1 OGNL表达式语法
```
# 基本属性访问
user.name
user['name']
user["name"]

# 方法调用
user.getName()
user.setName('John')

# 导航操作
user.address.city
user.orders[0].total

# 静态方法调用
@java.lang.Math@PI
@java.util.UUID@randomUUID()

# 构造对象
new java.util.ArrayList()
```

### 2.2 MyBatis中的OGNL上下文
```java
// MyBatis为OGNL提供的默认上下文变量
- parameter // 传入的参数对象
- _parameter // 实际传入的参数（别名）
- _databaseId // 数据库厂商标识
- _parameterObject // 参数对象（内部使用）

// 命名参数
- @Param("user") User user → user.name
```

## 3. 动态SQL中的OGNL应用

### 3.1 if标签中的OGNL表达式
```xml
<select id="findUsers" resultType="User">
  SELECT * FROM users
  <where>
    <!-- 基本条件判断 -->
    <if test="name != null and name != ''">
      AND name = #{name}
    </if>
    
    <!-- 调用方法判断 -->
    <if test="isValid()">
      AND status = 1
    </if>
    
    <!-- 集合判断 -->
    <if test="ids != null and ids.size() > 0">
      AND id IN
      <foreach collection="ids" item="id" open="(" separator="," close=")">
        #{id}
      </foreach>
    </if>
  </where>
</select>
```

### 3.2 choose/when/otherwise标签
```xml
<select id="findByCondition" resultType="User">
  SELECT * FROM users
  <where>
    <choose>
      <when test="type == 'admin'">
        AND role = 'ADMIN'
      </when>
      <when test="type == 'user'">
        AND role = 'USER'
      </when>
      <otherwise>
        AND role IS NOT NULL
      </otherwise>
    </choose>
  </where>
</select>
```

### 3.3 trim/set/where标签
```xml
<update id="updateUser">
  UPDATE users
  <set>
    <if test="name != null">name = #{name},</if>
    <if test="email != null">email = #{email},</if>
    <if test="age != null">age = #{age},</if>
  </set>
  WHERE id = #{id}
</update>
```

## 4. OGNL表达式解析机制

### 4.1 解析流程
```
1. MyBatis解析XML映射文件
2. 遇到动态SQL标签（if/choose等）
3. 提取test属性中的OGNL表达式
4. 创建OGNL上下文环境
5. 绑定参数对象到上下文
6. 执行表达式求值
7. 根据布尔结果决定SQL片段是否包含
```

### 4.2 参数绑定示例
```java
public interface UserMapper {
    // 方法调用
    List<User> findUsers(@Param("query") UserQuery query);
}

// XML中的OGNL访问
<if test="query.name != null">
  AND username LIKE CONCAT('%', #{query.name}, '%')
</if>
```

### 4.3 特殊操作符支持

#### 4.3.1 空值安全操作符
```xml
<!-- 传统的空值判断 -->
<if test="user != null and user.name != null">

<!-- 使用空值安全操作符（MyBatis 3.4.2+） -->
<if test="user?.name != null">
```

#### 4.3.2 正则表达式匹配
```xml
<if test="email matches '^[A-Za-z0-9+_.-]+@(.+)$'">
  AND email_valid = 1
</if>
```

## 5. 集合和数组操作

### 5.1 集合判断和遍历
```xml
<!-- 检查集合是否为空 -->
<if test="list != null and !list.isEmpty()">
  id IN
  <foreach collection="list" item="item" open="(" separator="," close=")">
    #{item}
  </foreach>
</if>

<!-- 遍历Map -->
<foreach collection="map.entrySet()" item="value" index="key">
  #{key} = #{value}
</foreach>
```

### 5.2 索引和大小访问
```xml
<if test="array.length > 0">
<if test="list[0] != null">
<if test="map['key'] != null">
```

## 6. 内置函数和操作

### 6.1 OGNL内置函数
```xml
<!-- 字符串操作 -->
<if test="name != null and name.length() > 0">
<if test="email.indexOf('@') > -1">
<if test="description.substring(0, 10)">

<!-- 集合操作 -->
<if test="list.contains(target)">
<if test="list.indexOf(obj) != -1">
<if test="map.containsKey(key)">
```

### 6.2 MyBatis扩展函数
```xml
<!-- _parameter特殊访问 -->
<if test="_parameter instanceof java.lang.Integer">
  AND id = #{id}
</if>

<!-- 数据库厂商标识判断 -->
<if test="_databaseId == 'mysql'">
  LIMIT #{limit}
</if>
<if test="_databaseId == 'oracle'">
  AND ROWNUM &lt;= #{limit}
</if>
```

## 7. 高级应用场景

### 7.1 复杂对象图导航
```java
public class Order {
    private User user;
    private List<OrderItem> items;
    private Address shippingAddress;
}

public class User {
    private String name;
    private ContactInfo contact;
}
```

```xml
<!-- 多层对象导航 -->
<if test="order.user.contact.email != null">
  AND email = #{order.user.contact.email}
</if>

<!-- 集合元素属性访问 -->
<if test="order.items[0].product.category == 'ELECTRONICS'">
  AND priority = 'HIGH'
</if>
```

### 7.2 动态排序
```xml
<select id="findWithOrder" resultType="User">
  SELECT * FROM users
  ORDER BY 
  <choose>
    <when test="orderBy == 'name'">name</when>
    <when test="orderBy == 'email'">email</when>
    <when test="orderBy == 'createTime'">create_time</when>
    <otherwise>id</otherwise>
  </choose>
  <choose>
    <when test="orderDirection == 'desc'">DESC</when>
    <otherwise>ASC</otherwise>
  </choose>
</select>
```

## 8. 性能优化与最佳实践

### 8.1 表达式优化建议
```xml
<!-- 避免重复计算 -->
<if test="user != null and user.active">
  <!-- 而不是 -->
  <if test="user != null">
    <if test="user.active">
      
<!-- 使用短路逻辑 -->
<if test="user == null or user.name == null">
```

### 8.2 缓存配置
```properties
# mybatis-config.xml配置
<settings>
  <!-- 启用OGNL表达式缓存 -->
  <setting name="defaultScriptingLanguage" value="org.apache.ibatis.scripting.xmltags.XMLLanguageDriver"/>
</settings>
```

## 9. 常见问题与解决方案

### 9.1 空指针异常处理
```xml
<!-- 问题：当user为null时，user.name会抛出NPE -->
<if test="user.name != null">

<!-- 解决方案1：使用空值安全操作符 -->
<if test="user?.name != null">

<!-- 解决方案2：分层判断 -->
<if test="user != null and user.name != null">
```

### 9.2 类型转换问题
```xml
<!-- 字符串与数字比较 -->
<if test="status != null and status == '1'">  <!-- 可能出错 -->
<if test="status != null and status == 1">    <!-- 正确 -->

<!-- 使用toString()进行明确转换 -->
<if test="status != null and status.toString() == '1'">
```

### 9.3 调试技巧
```java
// 启用OGNL调试日志
log4j.logger.org.apache.ibatis.scripting.xmltags=DEBUG

// 在表达式中添加日志输出
<if test="@org.apache.ibatis.logging.LogFactory@getLog('test').debug('value: '+value) != null">
```

## 10. 源码解析

### 10.1 核心解析类
```java
// 主要涉及类
- org.apache.ibatis.scripting.xmltags.OgnlClassResolver
- org.apache.ibatis.scripting.xmltags.OgnlCache
- org.apache.ibatis.scripting.xmltags.ExpressionEvaluator

// 表达式求值入口
Object value = OgnlCache.getValue(expression, parameterObject);
```

### 10.2 表达式缓存机制
```java
// OgnlCache使用ConcurrentHashMap缓存解析后的表达式
private static final Map<String, Object> expressionCache = new ConcurrentHashMap<>();

// 缓存键生成
String cacheKey = expression + ":" + context.getClass().getName();
```

## 11. 总结

### 11.1 核心要点
1. OGNL是MyBatis动态SQL的核心表达式语言
2. 支持对象图导航、方法调用、静态访问等丰富特性
3. 合理使用可以极大简化动态SQL的编写
4. 需要注意空值安全和性能优化

### 11.2 推荐实践
1. 优先使用简单明确的表达式
2. 合理组织参数对象结构
3. 利用OGNL的短路特性优化性能
4. 在复杂场景下适当分层判断

---

## 附录：OGNL表达式速查表

| 表达式 | 说明 | 示例 |
|--------|------|------|
| `obj.property` | 属性访问 | `user.name` |
| `obj.method()` | 方法调用 | `list.size()` |
| `obj[index]` | 数组/列表索引 | `array[0]` |
| `obj[key]` | Map键访问 | `map['key']` |
| `@Class@method` | 静态方法 | `@Math@max(a,b)` |
| `new Class()` | 对象创建 | `new Date()` |
| `obj1 == obj2` | 相等比较 | `status == 1` |
| `obj1 != obj2` | 不等比较 | `name != null` |
| `obj1 && obj2` | 逻辑与 | `a && b` |
| `obj1 \|\| obj2` | 逻辑或 | `a \|\| b` |
| `obj1 ? obj2 : obj3` | 三元运算 | `flag ? 'Y' : 'N'` |

---

*文档版本：1.0*
*最后更新：2024年*
*适用MyBatis版本：3.5.0+*