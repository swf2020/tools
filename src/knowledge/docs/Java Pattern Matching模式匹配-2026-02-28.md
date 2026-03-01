# Java 模式匹配（Pattern Matching）技术文档

## 1. 概述

Java模式匹配是JDK 14引入的预览特性，经过多个版本的演进，现已成为Java语言的正式功能。它通过简化类型检查和转换的常见模式，使代码更简洁、安全且易于阅读。

## 2. 核心特性

### 2.1 instanceof模式匹配（JDK 16+ 正式功能）

**传统方式：**
```java
if (obj instanceof String) {
    String s = (String) obj;
    // 使用s
}
```

**模式匹配方式：**
```java
if (obj instanceof String s) {
    // 直接使用模式变量s
    System.out.println(s.length());
}
```

### 2.2 switch模式匹配（JDK 17预览，JDK 21+ 增强）

**传统switch限制：**
- 仅支持基本类型和枚举
- 类型检查需要额外的if-else链

**模式匹配switch：**
```java
// JDK 17+ 预览功能
Object obj = getObject();
String formatted = switch (obj) {
    case Integer i -> String.format("整数: %d", i);
    case String s -> String.format("字符串: %s", s);
    case null -> "null值";
    default -> obj.toString();
};
```

## 3. 语法详解

### 3.1 模式变量作用域
```java
// 模式变量的作用域仅限于条件为真的分支
if (obj instanceof String s && s.length() > 5) {
    // 这里可以访问s
} else {
    // 这里不能访问s
}
```

### 3.2 类型模式语法
```java
// 基本语法
if (obj instanceof Type identifier) {
    // identifier 自动转换为 Type 类型
}

// 结合泛型
if (list instanceof ArrayList<String> stringList) {
    // 处理字符串列表
}
```

### 3.3 守卫模式（Guard Patterns）
```java
// JDK 19+ 预览特性
Object obj = "Hello";
if (obj instanceof String s && s.length() > 3) {
    // 同时进行类型检查和条件判断
}

// switch中的守卫表达式
switch (obj) {
    case String s when s.length() > 5 -> 
        System.out.println("长字符串: " + s);
    case String s -> 
        System.out.println("短字符串: " + s);
}
```

## 4. 完整示例

### 4.1 数据类解构
```java
// 定义记录类
record Point(int x, int y) {}

// 使用模式匹配处理不同几何图形
static String processShape(Object shape) {
    return switch (shape) {
        case Point p -> 
            String.format("点坐标: (%d, %d)", p.x(), p.y());
        case Circle c when c.radius() > 10 -> 
            "大圆: " + c;
        case Circle c -> 
            "小圆: " + c;
        case null -> 
            "空形状";
        default -> 
            "未知形状";
    };
}
```

### 4.2 嵌套模式匹配
```java
// 处理嵌套数据结构
record Box(Object content) {}

String processNested(Object obj) {
    return switch (obj) {
        case Box(Point p) -> 
            "包含点的盒子: " + p;
        case Box(String s) -> 
            "包含字符串的盒子: " + s;
        case Box b -> 
            "空盒子或其他";
        default -> "未知对象";
    };
}
```

## 5. 实际应用场景

### 5.1 替换visitor模式
```java
// 传统visitor模式
interface Shape {
    void accept(Visitor v);
}

// 使用模式匹配
static double calculateArea(Object shape) {
    return switch (shape) {
        case Circle c -> Math.PI * c.radius() * c.radius();
        case Rectangle r -> r.width() * r.height();
        case Triangle t -> 0.5 * t.base() * t.height();
        default -> throw new IllegalArgumentException();
    };
}
```

### 5.2 安全类型转换
```java
// 处理异构集合
List<Object> mixedList = Arrays.asList("text", 42, 3.14);

for (Object item : mixedList) {
    switch (item) {
        case String s -> processString(s);
        case Integer i -> processInteger(i);
        case Double d -> processDouble(d);
        // 编译器确保所有情况都被处理
    }
}
```

## 6. 编译器优化

模式匹配在编译时提供以下优势：
- **类型安全性**：模式变量自动转换，避免ClassCastException
- **穷尽性检查**：switch表达式强制处理所有可能情况
- **空值处理**：明确处理null情况，减少NullPointerException

## 7. 版本兼容性

| JDK版本 | 功能状态 | 重要特性 |
|---------|---------|----------|
| JDK 14 | 预览 | instanceof模式匹配 |
| JDK 16 | 正式 | instanceof模式匹配 |
| JDK 17 | 预览 | switch模式匹配 |
| JDK 18 | 第二次预览 | 模式匹配增强 |
| JDK 19 | 第三次预览 | 记录模式、数组模式 |
| JDK 21 | 正式 | switch模式匹配正式化 |

## 8. 最佳实践

1. **优先使用模式匹配**替代显式类型转换
2. **利用编译器检查**确保处理所有情况
3. **结合记录类**使用解构模式
4. **避免过度复杂**的模式嵌套
5. **考虑向后兼容性**，如需支持旧版本

## 9. 限制与注意事项

- 某些复杂的泛型场景可能受限
- 模式变量在作用域外不可访问
- 需要JDK 16+以获得生产环境支持
- IDE支持可能因版本而异

## 10. 未来发展方向

Java模式匹配仍在持续演进：
- 支持更复杂的解构模式
- 改进数组和集合的模式匹配
- 更好的泛型类型推断
- 性能优化

## 11. 示例项目结构

```
pattern-matching-demo/
├── src/main/java/
│   └── com/example/
│       ├── model/
│       │   ├── Shape.java
│       │   ├── Circle.java
│       │   └── Rectangle.java
│       ├── service/
│       │   └── ShapeProcessor.java
│       └── Main.java
├── pom.xml
└── README.md
```

## 12. 参考文献

1. [JEP 394: Pattern Matching for instanceof](https://openjdk.org/jeps/394)
2. [JEP 406: Pattern Matching for switch (Preview)](https://openjdk.org/jeps/406)
3. [JEP 420: Pattern Matching for switch (Second Preview)](https://openjdk.org/jeps/420)
4. [Oracle Pattern Matching Documentation](https://docs.oracle.com/en/java/javase/21/language/pattern-matching.html)

---

**注意**：使用预览功能时，需要通过`--enable-preview`编译标志启用，且API可能在后续版本中变更。生产环境建议使用已正式化的功能（JDK 16+的instanceof模式匹配，JDK 21+的switch模式匹配）。