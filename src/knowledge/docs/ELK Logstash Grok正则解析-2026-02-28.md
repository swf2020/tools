## ELK Logstash Grok正则解析技术文档

### 1. 概述

#### 1.1 Grok简介
Grok是Logstash中最强大、最常用的过滤器插件，主要用于将非结构化日志数据解析为结构化和可查询的字段。它基于正则表达式构建，提供了大量预定义的模式（patterns），使得日志解析变得更加简单高效。

#### 1.2 工作原理
Grok通过将文本模式与日志事件进行匹配，提取出有意义的字段。其核心是将正则表达式组合成可重用的模式，实现"一次定义，多处使用"。

### 2. Grok基础语法

#### 2.1 基本语法格式
```
%{SYNTAX:SEMANTIC:TYPE}
```

- **SYNTAX**: 模式名称（预定义或自定义）
- **SEMANTIC**: 匹配成功后赋予的字段名称
- **TYPE**: 数据类型（可选，如int, float等）

示例：
```
%{NUMBER:duration:float} %{IP:client_ip}
```

#### 2.2 常用内置模式
Logstash预定义了丰富的模式，位于：
- 内置模式：包含在Logstash核心中
- 自定义模式文件：`/usr/share/logstash/patterns/*`

常见内置模式：
```
NUMBER      # 数字（整数或浮点数）
INT         # 整数
FLOAT       # 浮点数
WORD        # 单词字符
DATA        # 任意数据
GREEDYDATA  # 贪婪匹配任意数据
IP          # IPv4或IPv6地址
HOSTNAME    # 主机名
PATH        # 文件路径
URIPATH     # URI路径
```

### 3. Grok配置与使用

#### 3.1 Logstash配置示例
```ruby
input {
  file {
    path => "/var/log/nginx/access.log"
    start_position => "beginning"
  }
}

filter {
  grok {
    match => { "message" => "%{COMBINEDAPACHELOG}" }
  }
}

output {
  elasticsearch {
    hosts => ["localhost:9200"]
    index => "nginx-logs-%{+YYYY.MM.dd}"
  }
}
```

#### 3.2 自定义模式文件
创建自定义模式文件 `patterns/myapp`:
```
MYAPP_LOGLEVEL [A-Z]+
MYAPP_TIMESTAMP %{YEAR}-%{MONTHNUM}-%{MONTHDAY} %{TIME}
MYAPP_UUID [a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}
```

在Logstash配置中引用：
```ruby
filter {
  grok {
    patterns_dir => ["/path/to/patterns"]
    match => { "message" => "%{MYAPP_TIMESTAMP:timestamp} %{MYAPP_LOGLEVEL:level}" }
  }
}
```

### 4. 高级模式匹配

#### 4.1 多重模式匹配
```ruby
grok {
  match => {
    "message" => [
      "%{SYSLOGTIMESTAMP:timestamp} %{SYSLOGHOST:hostname} %{DATA:program}: %{GREEDYDATA:message}",
      "%{TIMESTAMP_ISO8601:timestamp} %{LOGLEVEL:level} %{GREEDYDATA:message}"
    ]
  }
  overwrite => ["message"]
}
```

#### 4.2 条件匹配
```ruby
filter {
  if [type] == "nginx-access" {
    grok {
      match => { "message" => "%{COMBINEDAPACHELOG}" }
    }
  } else if [type] == "syslog" {
    grok {
      match => { "message" => "%{SYSLOGLINE}" }
    }
  }
}
```

#### 4.3 字段重命名和转换
```ruby
grok {
  match => { "message" => "%{NUMBER:duration:float} seconds" }
  mutate {
    convert => { "duration" => "float" }
    rename => { "duration" => "response_time" }
  }
}
```

### 5. 实际应用案例

#### 5.1 Nginx访问日志解析
```ruby
# 使用预定义模式
match => { "message" => "%{COMBINEDAPACHELOG}" }

# 自定义详细解析
match => { 
  "message" => '%{IPORHOST:client_ip} - %{USER:remote_user} \[%{HTTPDATE:timestamp}\] "%{WORD:method} %{URIPATHPARAM:request} HTTP/%{NUMBER:http_version}" %{NUMBER:status} %{NUMBER:body_bytes_sent} "%{DATA:referrer}" "%{DATA:user_agent}"' 
}
```

#### 5.2 Java应用日志解析
```ruby
grok {
  match => { 
    "message" => '%{TIMESTAMP_ISO8601:timestamp} %{LOGLEVEL:level} \[%{DATA:thread}\] %{DATA:class} - %{GREEDYDATA:log_message}'
  }
}
```

#### 5.3 多行日志处理
```ruby
input {
  file {
    path => "/var/log/myapp.log"
    codec => multiline {
      pattern => "^%{TIMESTAMP_ISO8601} "
      negate => true
      what => "previous"
    }
  }
}

filter {
  grok {
    match => { 
      "message" => '%{TIMESTAMP_ISO8601:timestamp} %{LOGLEVEL:level} %{GREEDYDATA:message}'
    }
  }
}
```

### 6. 调试与优化

#### 6.1 Grok调试工具
1. **Grok Debugger**: Kibana内置工具
2. **在线调试器**: https://grokdebug.herokuapp.com/
3. **命令行测试**:
```bash
# 使用logstash测试
bin/logstash -e 'input { stdin {} } filter { grok { match => { "message" => "%{COMBINEDAPACHELOG}" } } } output { stdout { codec => rubydebug } }'
```

#### 6.2 调试技巧
```ruby
grok {
  match => { "message" => "%{PATTERN}" }
  # 开启调试
  tag_on_failure => ["_grokparsefailure"]
  # 添加原始消息
  add_tag => ["grok_processed"]
}
```

#### 6.3 性能优化建议
1. **模式优化**:
   - 避免过度使用`GREEDYDATA`
   - 使用更具体的模式代替通配符
   - 合理安排模式顺序

2. **缓存配置**:
```ruby
grok {
  match => { "message" => "%{PATTERN}" }
  break_on_match => false
  keep_empty_captures => true
}
```

### 7. 常见问题与解决方案

#### 7.1 匹配失败处理
```ruby
filter {
  grok {
    match => { "message" => "%{PATTERN}" }
    # 添加标签标记失败
    tag_on_failure => ["_grokparsefailure"]
  }
  
  # 处理匹配失败的日志
  if "_grokparsefailure" in [tags] {
    # 备用处理逻辑
    mutate {
      add_field => { "parse_error" => "true" }
    }
  }
}
```

#### 7.2 字段覆盖问题
```ruby
grok {
  match => { "message" => "%{DATA:existing_field}" }
  # 避免覆盖已有字段
  overwrite => []
}
```

### 8. 最佳实践

1. **模式设计原则**:
   - 从简单到复杂逐步构建
   - 使用预定义模式组合
   - 为每个模式添加注释

2. **测试策略**:
   - 使用真实日志样本测试
   - 覆盖各种边界情况
   - 定期更新模式库

3. **维护建议**:
   - 统一管理模式文件
   - 记录模式变更历史
   - 监控解析失败率

### 9. 参考资料

- [官方文档](https://www.elastic.co/guide/en/logstash/current/plugins-filters-grok.html)
- [预定义模式列表](https://github.com/elastic/logstash/tree/v7.14.0/patterns)
- [Grok模式构建器](https://grokconstructor.appspot.com/)

---

**文档版本**: v1.0  
**最后更新**: 2024年  
**适用版本**: Logstash 7.x+  
**作者**: ELK技术团队