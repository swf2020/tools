# Java Record 不可变数据类实现指南

## 1. 概述

Java Record 是 Java 14 引入的预览特性，在 Java 16 中成为正式特性。它是一种特殊的类，旨在以简洁的方式声明不可变数据载体（data carrier）类，主要用于存储和传输不可变数据。

## 2. Record 的基本语法

```java
// 基本声明
public record Person(String name, int age, String email) {}

// 使用示例
public class RecordExample {
    public static void main(String[] args) {
        // 创建 Record 实例
        Person person = new Person("张三", 30, "zhangsan@example.com");
        
        // 访问字段（自动生成的getter方法，但不带"get"前缀）
        System.out.println("姓名: " + person.name());
        System.out.println("年龄: " + person.age());
        System.out.println("邮箱: " + person.email());
        
        // 自动生成的 toString() 方法
        System.out.println(person); // 输出: Person[name=张三, age=30, email=zhangsan@example.com]
        
        // 自动生成的 equals() 和 hashCode() 方法
        Person person2 = new Person("张三", 30, "zhangsan@example.com");
        System.out.println("person.equals(person2): " + person.equals(person2)); // true
    }
}
```

## 3. Record 的核心特性

### 3.1 自动生成的方法
Record 自动生成以下方法：
- 规范的构造器（canonical constructor）
- 所有字段的访问器方法（field accessors）
- `equals()` 和 `hashCode()` 方法
- `toString()` 方法

### 3.2 不可变性保证
```java
public record ImmutablePoint(int x, int y) {
    // 所有字段都是隐式 final 的
    // Record 类本身也是隐式 final 的，不能被继承
}

// 尝试修改字段会导致编译错误
public class TestImmutable {
    public static void main(String[] args) {
        ImmutablePoint point = new ImmutablePoint(10, 20);
        // point.x = 30; // 编译错误：无法为final变量x赋值
    }
}
```

## 4. 自定义 Record 实现

### 4.1 添加自定义构造器
```java
public record Person(String name, int age, String email) {
    // 紧凑构造器（compact constructor） - 推荐方式
    public Person {
        // 参数验证
        if (age < 0) {
            throw new IllegalArgumentException("年龄不能为负数: " + age);
        }
        if (email != null && !email.contains("@")) {
            throw new IllegalArgumentException("邮箱格式不正确: " + email);
        }
        
        // 紧凑构造器中可以直接使用参数，无需显式赋值
        // 编译器会自动将参数值赋给相应的字段
    }
    
    // 自定义构造器
    public Person(String name, int age) {
        this(name, age, null); // 必须委托给主构造器
    }
    
    // 静态工厂方法
    public static Person createWithDefaultEmail(String name, int age) {
        return new Person(name, age, name.toLowerCase() + "@default.com");
    }
}
```

### 4.2 添加自定义方法
```java
public record Product(
    String id, 
    String name, 
    BigDecimal price, 
    Category category
) {
    // 实例方法
    public String getDisplayName() {
        return name + " (" + category + ")";
    }
    
    public BigDecimal getPriceWithTax(BigDecimal taxRate) {
        return price.multiply(BigDecimal.ONE.add(taxRate));
    }
    
    // 静态方法
    public static Product createDefault() {
        return new Product("default-001", "默认产品", 
                          BigDecimal.valueOf(99.99), Category.ELECTRONICS);
    }
    
    // 嵌套枚举
    public enum Category {
        ELECTRONICS, CLOTHING, BOOKS, FOOD
    }
}
```

### 4.3 处理可变组件
```java
import java.util.List;
import java.util.Collections;

public record Order(
    String orderId, 
    List<String> items,  // List 是可变的
    double totalAmount
) {
    // 处理可变组件的防御性拷贝
    public Order {
        // 创建不可修改的副本
        items = List.copyOf(items); // Java 10+ 的方法
        
        // 或者使用旧版本的方式
        // items = Collections.unmodifiableList(new ArrayList<>(items));
    }
    
    // 重写访问器方法以返回不可修改的视图
    @Override
    public List<String> items() {
        return Collections.unmodifiableList(items);
    }
}
```

## 5. Record 与传统 JavaBean 的对比

| 特性 | Record | 传统 JavaBean |
|------|--------|---------------|
| 代码简洁性 | 高（自动生成方法） | 低（需手动编写或使用Lombok） |
| 不可变性 | 默认不可变 | 默认可变（需额外处理） |
| 继承 | 不能继承其他类（隐式 final） | 可以继承 |
| 字段 | 自动成为 final | 可以是 final 或非 final |
| 构造器 | 自动生成规范构造器 | 需手动定义 |
| equals/hashCode | 基于所有字段自动生成 | 需手动实现或使用 IDE 生成 |
| toString | 自动生成 | 需手动实现或使用 IDE 生成 |

## 6. 使用模式匹配增强 Record

```java
// Java 14+ 模式匹配 instanceof
public class RecordPatternMatching {
    public static String process(Object obj) {
        // 传统方式
        if (obj instanceof Person) {
            Person p = (Person) obj;
            return "Person: " + p.name();
        }
        
        // 模式匹配方式
        if (obj instanceof Person p) {
            return "Person: " + p.name();
        }
        
        // Java 16+ Record 模式
        if (obj instanceof Person(String name, int age, String email)) {
            return "Person named " + name + " is " + age + " years old";
        }
        
        return "Unknown type";
    }
}

// 在 switch 表达式中使用（Java 17+ 预览特性）
public class SwitchPatternMatching {
    public static String describe(Object obj) {
        return switch (obj) {
            case Person(String name, int age, String email) -> 
                "Person: " + name + ", age: " + age;
            case Product(String id, String name, BigDecimal price, Product.Category category) ->
                "Product: " + name + ", price: " + price;
            case null -> "Null object";
            default -> "Unknown type";
        };
    }
}
```

## 7. 实际应用示例

### 7.1 DTO（数据传输对象）
```java
// API 响应 DTO
public record ApiResponse<T>(
    boolean success,
    String message,
    T data,
    long timestamp
) {
    public ApiResponse {
        if (timestamp == 0) {
            timestamp = System.currentTimeMillis();
        }
    }
    
    public static <T> ApiResponse<T> success(T data) {
        return new ApiResponse<>(true, "操作成功", data, System.currentTimeMillis());
    }
    
    public static <T> ApiResponse<T> error(String message) {
        return new ApiResponse<>(false, message, null, System.currentTimeMillis());
    }
}
```

### 7.2 值对象
```java
public record Money(
    BigDecimal amount,
    Currency currency
) {
    public Money {
        if (amount.compareTo(BigDecimal.ZERO) < 0) {
            throw new IllegalArgumentException("金额不能为负数");
        }
        Objects.requireNonNull(currency, "货币单位不能为空");
    }
    
    public Money add(Money other) {
        if (!this.currency.equals(other.currency)) {
            throw new IllegalArgumentException("货币单位不一致");
        }
        return new Money(this.amount.add(other.amount), this.currency);
    }
    
    public Money subtract(Money other) {
        if (!this.currency.equals(other.currency)) {
            throw new IllegalArgumentException("货币单位不一致");
        }
        return new Money(this.amount.subtract(other.amount), this.currency);
    }
}
```

### 7.3 配置类
```java
public record DatabaseConfig(
    String url,
    String username,
    String password,
    int maxConnections,
    int timeoutSeconds
) {
    public DatabaseConfig {
        if (maxConnections <= 0) {
            maxConnections = 10; // 默认值
        }
        if (timeoutSeconds <= 0) {
            timeoutSeconds = 30; // 默认值
        }
    }
    
    public static DatabaseConfig fromProperties(Properties props) {
        return new DatabaseConfig(
            props.getProperty("db.url"),
            props.getProperty("db.username"),
            props.getProperty("db.password"),
            Integer.parseInt(props.getProperty("db.maxConnections", "10")),
            Integer.parseInt(props.getProperty("db.timeoutSeconds", "30"))
        );
    }
}
```

## 8. 限制和最佳实践

### 8.1 Record 的限制
- 不能显式继承其他类（隐式继承 `java.lang.Record`）
- 所有字段都是 final 的
- 不能添加实例字段（除了 static 字段）
- 不能声明 abstract 的 Record
- 不能声明本地 Record（Java 17 已支持）

### 8.2 最佳实践
1. **适合场景**：使用 Record 表示不可变数据，如 DTO、值对象、配置类等
2. **验证逻辑**：在紧凑构造器中添加必要的参数验证
3. **防御性拷贝**：当包含可变组件时，需要进行防御性拷贝
4. **保持简洁**：避免在 Record 中添加过多业务逻辑
5. **序列化**：Record 默认支持序列化，但需要确保所有组件都可序列化

## 9. 总结

Java Record 提供了一种简洁、安全、高效的方式来表示不可变数据类。它通过自动生成样板代码减少了开发者的工作量，同时通过不可变性保证了线程安全。虽然 Record 有一些限制，但在适合的场景下，它可以显著提高代码质量和开发效率。