# Java Switch表达式增强技术文档

## 摘要
Java Switch表达式是Java 12中引入的预览特性，在Java 14中正式成为标准功能。这一增强彻底改变了传统switch语句的编写方式，提供了更简洁、更安全、更具表达力的语法。新特性包括箭头语法（`->`）、多值匹配、表达式返回值等，显著减少了模板代码，避免了传统switch中常见的fall-through问题。

## 历史演进
| 版本 | 状态 | 主要改进 |
|------|------|----------|
| Java 7 | 正式 | 支持字符串类型的switch |
| Java 12 | 预览 | 引入Switch表达式（JEP 325） |
| Java 13 | 预览 | 改进`yield`语句（JEP 354） |
| Java 14 | 正式 | 成为标准特性（JEP 361） |
| Java 17 | 正式 | 长期支持版本中的标准功能 |

## 特性详解

### 1. 箭头语法（`->`）
- 替代传统的`:`和`break`语句
- 右侧可以是表达式、代码块或`throw`语句
- 自动避免fall-through行为

### 2. 多值匹配
```java
case 1, 2, 3 -> System.out.println("小数字");
```

### 3. 表达式返回值
- Switch可以作为表达式使用，返回一个值
- 必须穷举所有可能情况或提供`default`分支
- 使用`yield`在代码块中返回值

### 4. 模式匹配（Java 17预览，Java 21增强）
```java
switch (obj) {
    case String s -> System.out.println("字符串: " + s);
    case Integer i -> System.out.println("整数: " + i);
    default -> System.out.println("其他类型");
}
```

## 代码示例

### 传统switch语句 vs Switch表达式

**传统写法：**
```java
DayOfWeek day = DayOfWeek.MONDAY;
String type;
switch (day) {
    case MONDAY:
    case FRIDAY:
    case SUNDAY:
        type = "工作日";
        break;
    case TUESDAY:
        type = "会议日";
        break;
    case THURSDAY:
    case SATURDAY:
        type = "休息日";
        break;
    default:
        throw new IllegalArgumentException("无效的日期");
}
```

**Switch表达式写法：**
```java
DayOfWeek day = DayOfWeek.MONDAY;
String type = switch (day) {
    case MONDAY, FRIDAY, SUNDAY -> "工作日";
    case TUESDAY -> "会议日";
    case THURSDAY, SATURDAY -> "休息日";
    default -> throw new IllegalArgumentException("无效的日期");
};
```

### 使用yield返回值
```java
int num = 2;
String result = switch (num) {
    case 1 -> "一";
    case 2 -> {
        System.out.println("处理数字2");
        yield "二";  // 使用yield返回值
    }
    case 3 -> "三";
    default -> "其他";
};
```

### 模式匹配示例（Java 17+）
```java
Object obj = "Hello";
String formatted = switch (obj) {
    case Integer i -> String.format("整数: %d", i);
    case Long l    -> String.format("长整数: %d", l);
    case Double d  -> String.format("浮点数: %f", d);
    case String s  -> String.format("字符串: %s", s);
    case null      -> "空值";
    default        -> obj.toString();
};
```

## 性能比较
Switch表达式在编译时被转换为与原始switch语句相似的字节码，因此在性能上没有显著差异。主要改进体现在：
1. **编译时检查增强**：编译器可以验证穷尽性
2. **代码可读性提升**：减少模板代码
3. **运行时安全**：避免意外的fall-through错误

## 最佳实践

### 推荐使用场景
1. **返回值计算**：当需要根据条件计算并返回一个值时
2. **简单的分支逻辑**：分支逻辑简单，适合单行表达式
3. **枚举处理**：处理枚举值时特别简洁
4. **模式匹配**：Java 17+中处理多类型场景

### 注意事项
1. **穷尽性检查**：作为表达式时必须覆盖所有情况
2. **yield使用**：在代码块中必须使用yield返回值
3. **可读性平衡**：避免在单个case中编写过于复杂的逻辑
4. **向后兼容**：传统switch语句仍被支持，可根据场景选择

### 代码风格建议
```java
// 好的实践：简洁明了
return switch (status) {
    case SUCCESS -> "成功";
    case FAILURE -> "失败";
    case PENDING -> "处理中";
};

// 避免：过于复杂的逻辑放在switch中
String result = switch (input) {
    case "A" -> {
        // 避免在这里写多行复杂逻辑
        // 考虑提取到独立方法
        yield processA(input);
    }
    // ...
};
```

## 总结
Java Switch表达式是现代Java语言发展中的重要改进，它通过引入函数式编程风格，显著提升了代码的简洁性和安全性。随着模式匹配特性的不断成熟，Switch表达式将在类型安全编程中发挥更大作用。开发者应逐步采用这一特性，特别是在新项目和Java 17+环境中，以编写更现代、更安全的Java代码。