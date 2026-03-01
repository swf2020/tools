# Java Sealed Class（封闭类）技术文档

## 1. 引言

### 1.1 概念与背景
Java Sealed Class（封闭类）是Java 15引入的预览特性，在Java 17中正式成为标准特性。它提供了一种机制，允许类或接口的作者明确声明哪些类可以继承或实现它，从而创建**受限制的类型层级**。

### 1.2 解决的问题
在传统的Java继承模型中，存在以下问题：
- **类型安全性不足**：任何类都可以继承公开的类或接口，导致不可预见的子类扩展
- **模式匹配的局限性**：在switch表达式中进行模式匹配时，无法确保所有可能的子类型都被处理
- **API设计控制不足**：库开发者无法限制用户扩展特定的类

Sealed Class通过以下方式解决这些问题：
- 提供编译时的类型安全保证
- 支持详尽的模式匹配检查
- 增强API的封装性和可维护性

## 2. 语法与使用

### 2.1 基本定义
#### Sealed Class声明
```java
// 使用sealed关键字声明封闭类
public sealed class Shape 
    permits Circle, Rectangle, Triangle {
    // 类定义
}
```

#### Sealed Interface声明
```java
public sealed interface Transport 
    permits Car, Bike, Bus {
    // 接口定义
}
```

### 2.2 permits子句
- **作用**：明确指定允许继承/实现的类
- **要求**：
  - 允许的类必须在同一模块或包中（除非使用opens/export）
  - 允许的类必须直接继承封闭类

```java
public sealed class Expression 
    permits ConstantExpr, PlusExpr, MinusExpr, TimesExpr {
    // 允许四个具体的表达式类型
}
```

### 2.3 子类修饰符
封闭类的直接子类必须使用以下修饰符之一：

| 修饰符 | 描述 | 示例 |
|--------|------|------|
| `final` | 不能再被继承 | `final class Circle extends Shape` |
| `sealed` | 也是封闭类，需要自己的permits子句 | `sealed class Polygon extends Shape permits Triangle, Quadrilateral` |
| `non-sealed` | 重新开放继承 | `non-sealed class SpecialShape extends Shape` |

```java
// 示例：不同类型的子类
public sealed class Shape permits Circle, Rectangle, Polygon {
    // 父类定义
}

final class Circle extends Shape { 
    private final double radius;
    // 最终类，不可再继承
}

sealed class Polygon extends Shape permits Triangle, Quadrilateral {
    // 也是封闭类
}

non-sealed class SpecialShape extends Shape {
    // 开放继承，任何类都可以继承SpecialShape
}
```

## 3. 类型层级与模式匹配

### 3.1 类型系统增强
Sealed Class创建了明确的类型层级，编译器可以：
- 验证所有允许的子类都已正确定义
- 确保没有未授权的子类存在
- 提供编译时类型检查

### 3.2 模式匹配结合
#### 传统的instanceof检查
```java
if (shape instanceof Circle c) {
    System.out.println("Circle with radius: " + c.radius());
} else if (shape instanceof Rectangle r) {
    System.out.println("Rectangle");
} // 可能遗漏其他子类
```

#### 与switch表达式结合（Java 17+）
```java
// 编译器可以检查是否覆盖所有可能的子类
double area = switch(shape) {
    case Circle c -> Math.PI * c.radius() * c.radius();
    case Rectangle r -> r.width() * r.height();
    case Triangle t -> 0.5 * t.base() * t.height();
    // 不需要default分支，因为所有情况都已覆盖
};
```

#### 穷尽性检查
编译器会确保所有sealed类的子类都被处理：
```java
// 如果遗漏了某个子类，编译器会报错
String description = switch(expression) {
    case ConstantExpr c -> "Constant: " + c.value();
    case PlusExpr p -> "Addition";
    case MinusExpr m -> "Subtraction";
    // 缺少TimesExpr的情况 → 编译错误
};
```

### 3.3 记录类（Record）与Sealed Class的结合
```java
public sealed interface Expr 
    permits Constant, Add, Multiply {
    
    record Constant(int value) implements Expr {}
    record Add(Expr left, Expr right) implements Expr {}
    record Multiply(Expr left, Expr right) implements Expr {}
}

// 使用模式匹配进行计算
int evaluate(Expr expr) {
    return switch(expr) {
        case Constant(int value) -> value;
        case Add(Expr left, Expr right) -> evaluate(left) + evaluate(right);
        case Multiply(Expr left, Expr right) -> evaluate(left) * evaluate(right);
    };
}
```

## 4. 设计考量与最佳实践

### 4.1 何时使用Sealed Class
1. **固定类型集合**：当类型的集合是固定且已知的
   - 示例：AST节点、命令模式中的命令、UI组件类型

2. **增强模式匹配**：需要编译器辅助进行穷尽性检查时

3. **API设计**：库开发者希望控制扩展点

4. **领域建模**：表示有明确约束的领域概念

### 4.2 设计建议
#### 层级设计
```java
// 良好设计：清晰的层级结构
public sealed class PaymentMethod 
    permits CreditCard, BankTransfer, DigitalWallet {
    // 支付方式的固定集合
}

public sealed class DigitalWallet extends PaymentMethod
    permits PayPal, Alipay, WeChatPay {
    // 数字钱包的特定类型
}
```

#### 包组织
```java
// 将相关类组织在同一包中
package com.example.shapes;

public sealed class Shape permits 
    Circle, 
    Rectangle, 
    Triangle {
    // 所有类都在com.example.shapes包中
}
```

### 4.3 注意事项
1. **可维护性**：添加新的子类需要修改父类的permits子句
2. **序列化**：确保所有子类都正确处理序列化
3. **反射**：通过反射创建非授权子类的实例会受到限制
4. **模块化**：在模块系统中使用时需要注意访问权限

### 4.4 替代方案比较
| 方案 | 优点 | 缺点 |
|------|------|------|
| **Sealed Class** | 编译时安全，模式匹配友好 | 扩展性受限 |
| **final类** | 完全防止继承 | 完全不可扩展 |
| **包私有构造器** | 包内可控 | 包外完全不可用 |
| **传统继承** | 完全开放扩展 | 缺乏控制，类型不安全 |

## 5. 完整示例

### 5.1 领域建模：文件系统节点
```java
import java.time.Instant;
import java.util.List;

// 定义封闭的FileSystemNode接口
public sealed interface FileSystemNode 
    permits Directory, File, SymbolicLink {
    
    String name();
    Instant createdAt();
    Instant modifiedAt();
    
    // 记录类作为实现
    record Directory(
        String name,
        Instant createdAt,
        Instant modifiedAt,
        List<FileSystemNode> children
    ) implements FileSystemNode {}
    
    record File(
        String name,
        Instant createdAt,
        Instant modifiedAt,
        long size,
        String contentType
    ) implements FileSystemNode {}
    
    record SymbolicLink(
        String name,
        Instant createdAt,
        Instant modifiedAt,
        FileSystemNode target
    ) implements FileSystemNode {}
}

// 使用模式匹配处理文件系统节点
class FileSystemProcessor {
    
    // 计算目录总大小
    long totalSize(FileSystemNode node) {
        return switch(node) {
            case File f -> f.size();
            case Directory d -> 
                d.children().stream()
                    .mapToLong(this::totalSize)
                    .sum();
            case SymbolicLink s -> totalSize(s.target());
        };
    }
    
    // 查找特定文件
    List<File> findFiles(FileSystemNode node, String extension) {
        return switch(node) {
            case File f when f.name().endsWith(extension) -> 
                List.of(f);
            case File f -> List.of();
            case Directory d -> 
                d.children().stream()
                    .flatMap(child -> findFiles(child, extension).stream())
                    .toList();
            case SymbolicLink s -> findFiles(s.target(), extension);
        };
    }
}
```

### 5.2 AST（抽象语法树）示例
```java
// 定义表达式语言
public sealed interface Expr 
    permits Constant, Variable, Add, Subtract, Multiply, Divide {
    
    record Constant(double value) implements Expr {}
    record Variable(String name) implements Expr {}
    record Add(Expr left, Expr right) implements Expr {}
    record Subtract(Expr left, Expr right) implements Expr {}
    record Multiply(Expr left, Expr right) implements Expr {}
    record Divide(Expr left, Expr right) implements Expr {}
}

// 解释器
class Interpreter {
    private final java.util.Map<String, Double> variables;
    
    double evaluate(Expr expr) {
        return switch(expr) {
            case Constant c -> c.value();
            case Variable v -> variables.getOrDefault(v.name(), 0.0);
            case Add a -> evaluate(a.left()) + evaluate(a.right());
            case Subtract s -> evaluate(s.left()) - evaluate(s.right());
            case Multiply m -> evaluate(m.left()) * evaluate(m.right());
            case Divide d -> {
                double right = evaluate(d.right());
                if (right == 0) throw new ArithmeticException("Division by zero");
                yield evaluate(d.left()) / right;
            }
        };
    }
}

// 编译器验证示例
class CompilerVerifier {
    
    static void verifyExpression(Expr expr) {
        switch(expr) {
            case Constant c -> 
                System.out.println("Constant: " + c.value());
            case Variable v -> 
                System.out.println("Variable: " + v.name());
            case Add a -> {
                System.out.println("Addition operation");
                verifyExpression(a.left());
                verifyExpression(a.right());
            }
            case Subtract s -> {
                System.out.println("Subtraction operation");
                verifyExpression(s.left());
                verifyExpression(s.right());
            }
            case Multiply m -> {
                System.out.println("Multiplication operation");
                verifyExpression(m.left());
                verifyExpression(m.right());
            }
            case Divide d -> {
                System.out.println("Division operation");
                verifyExpression(d.left());
                verifyExpression(d.right());
            }
            // 不需要default，编译器知道所有情况已覆盖
        }
    }
}
```

## 6. 总结

### 6.1 核心优势
1. **类型安全**：编译时保证类型层级的完整性
2. **模式匹配友好**：支持switch表达式的穷尽性检查
3. **API控制**：库开发者可以精确控制扩展点
4. **代码清晰**：明确表达设计意图，提高代码可读性

### 6.2 适用场景
- **领域建模**：具有固定类型的领域概念
- **编译器/解释器**：AST节点、指令集
- **状态机**：有限状态集合
- **UI组件**：有限的组件类型
- **API设计**：需要控制扩展的框架

### 6.3 版本兼容性
- Java 15：预览特性（需要`--enable-preview`）
- Java 16：第二次预览
- Java 17：正式特性（JEP 409）
- Java 18+：增强模式匹配支持

### 6.4 未来发展
Sealed Class与以下特性协同发展：
- **模式匹配**：更强大的类型解构能力
- **值对象**：与Record类的深度集成
- **泛型**：可能增强泛型类型参数的限制

通过Sealed Class，Java在保持向后兼容的同时，提供了更强大的类型系统工具，使开发者能够构建更安全、更易维护的应用程序架构。