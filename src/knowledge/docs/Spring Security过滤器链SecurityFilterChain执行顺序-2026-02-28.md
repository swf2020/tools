# Spring Security过滤器链(SecurityFilterChain)执行顺序技术文档

## 1. 概述

Spring Security的核心安全功能是通过一系列过滤器链(Filter Chain)实现的。当请求到达应用程序时，这些过滤器按特定顺序执行，共同完成认证、授权、防护等安全功能。

## 2. SecurityFilterChain基本概念

### 2.1 什么是SecurityFilterChain
SecurityFilterChain是Spring Security的核心接口，用于确定特定HTTP请求应应用哪些安全过滤器。一个应用可以配置多个SecurityFilterChain，每个链针对不同的请求模式。

### 2.2 过滤器链的工作流程
```
客户端请求 → Servlet容器 → Spring Security Filter Chain → 应用控制器
```

## 3. 默认过滤器链执行顺序

### 3.1 Spring Security 5.7+ 默认过滤器顺序
以下是Spring Security默认配置的过滤器执行顺序：

| 顺序 | 过滤器类 | 功能描述 |
|------|----------|----------|
| 1 | `ChannelProcessingFilter` | 强制使用HTTPS等特定通道 |
| 2 | `WebAsyncManagerIntegrationFilter` | 集成WebAsyncManager |
| 3 | `SecurityContextPersistenceFilter` | 在请求间存储SecurityContext |
| 4 | `HeaderWriterFilter` | 添加安全相关的HTTP头 |
| 5 | `CorsFilter` | 处理CORS跨域请求 |
| 6 | `CsrfFilter` | CSRF防护 |
| 7 | `LogoutFilter` | 处理注销请求 |
| 8 | `OAuth2AuthorizationRequestRedirectFilter` | OAuth2授权请求重定向 |
| 9 | `Saml2WebSsoAuthenticationRequestFilter` | SAML2 SSO认证请求 |
| 10 | `X509AuthenticationFilter` | X.509客户端证书认证 |
| 11 | `AbstractPreAuthenticatedProcessingFilter` | 预认证处理 |
| 12 | `CasAuthenticationFilter` | CAS认证 |
| 13 | `OAuth2LoginAuthenticationFilter` | OAuth2登录认证 |
| 14 | `Saml2WebSsoAuthenticationFilter` | SAML2 SSO认证 |
| 15 | `UsernamePasswordAuthenticationFilter` | 表单登录认证 |
| 16 | `OpenIDAuthenticationFilter` | OpenID认证 |
| 17 | `DefaultLoginPageGeneratingFilter` | 默认登录页生成 |
| 18 | `DefaultLogoutPageGeneratingFilter` | 默认注销页生成 |
| 19 | `ConcurrentSessionFilter` | 并发会话控制 |
| 20 | `DigestAuthenticationFilter` | Digest认证 |
| 21 | `BearerTokenAuthenticationFilter` | Bearer令牌认证 |
| 22 | `BasicAuthenticationFilter` | HTTP基本认证 |
| 23 | `RequestCacheAwareFilter` | 请求缓存处理 |
| 24 | `SecurityContextHolderAwareRequestFilter` | 包装请求对象 |
| 25 | `JaasApiIntegrationFilter` | JAAS集成 |
| 26 | `RememberMeAuthenticationFilter` | 记住我功能 |
| 27 | `AnonymousAuthenticationFilter` | 匿名用户认证 |
| 28 | `OAuth2AuthorizationCodeGrantFilter` | OAuth2授权码认证 |
| 29 | `SessionManagementFilter` | 会话管理 |
| 30 | `ExceptionTranslationFilter` | 安全异常转换 |
| 31 | `FilterSecurityInterceptor` | 方法安全拦截 |
| 32 | `SwitchUserFilter` | 用户切换功能 |

### 3.2 关键过滤器说明

#### 3.2.1 SecurityContextPersistenceFilter
```java
// 负责在请求之间存储和恢复SecurityContext
SecurityContext contextBeforeChainExecution = 
    securityContextRepository.loadContext(holder);
try {
    SecurityContextHolder.setContext(contextBeforeChainExecution);
    chain.doFilter(holder.getRequest(), holder.getResponse());
} finally {
    SecurityContext contextAfterChainExecution = 
        SecurityContextHolder.getContext();
    securityContextRepository.saveContext(contextAfterChainExecution, 
        holder.getRequest(), holder.getResponse());
    SecurityContextHolder.clearContext();
}
```

#### 3.2.2 ExceptionTranslationFilter
```java
// 处理安全异常，将其转换为合适的HTTP响应
try {
    chain.doFilter(request, response);
} catch (Exception ex) {
    handleSpringSecurityException(request, response, chain, ex);
}
```

#### 3.2.3 FilterSecurityInterceptor
```java
// 最后的过滤器，决定是否允许访问受保护资源
public void invoke(FilterInvocation fi) throws IOException, ServletException {
    InterceptorStatusToken token = super.beforeInvocation(fi);
    try {
        fi.getChain().doFilter(fi.getRequest(), fi.getResponse());
    } finally {
        super.afterInvocation(token, null);
    }
}
```

## 4. 自定义过滤器链配置

### 4.1 基础配置示例
```java
@Configuration
@EnableWebSecurity
public class SecurityConfig {
    
    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http
            .csrf().disable()  // 禁用CSRF过滤器
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .loginPage("/login")
                .permitAll()
            )
            .logout(logout -> logout
                .logoutUrl("/logout")
                .permitAll()
            )
            // 添加自定义过滤器
            .addFilterBefore(new CustomFilter(), 
                UsernamePasswordAuthenticationFilter.class)
            .addFilterAfter(new AuditFilter(), 
                SecurityContextHolderAwareRequestFilter.class);
        
        return http.build();
    }
}
```

### 4.2 多个过滤器链配置
```java
@Configuration
@EnableWebSecurity
public class MultiChainSecurityConfig {
    
    // API请求过滤器链
    @Bean
    @Order(1)
    public SecurityFilterChain apiFilterChain(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS)
            )
            .addFilterBefore(new JwtTokenFilter(), 
                UsernamePasswordAuthenticationFilter.class);
        
        return http.build();
    }
    
    // Web应用过滤器链
    @Bean
    @Order(2)
    public SecurityFilterChain webFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/css/**", "/js/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(form -> form
                .loginPage("/login")
                .permitAll()
            );
        
        return http.build();
    }
}
```

### 4.3 自定义过滤器示例
```java
@Component
public class CustomAuthenticationFilter extends OncePerRequestFilter {
    
    @Override
    protected void doFilterInternal(HttpServletRequest request,
                                    HttpServletResponse response,
                                    FilterChain filterChain)
            throws ServletException, IOException {
        
        String authHeader = request.getHeader("X-Custom-Auth");
        
        if (authHeader != null && authHeader.startsWith("Custom ")) {
            String token = authHeader.substring(7);
            // 验证token并创建Authentication对象
            Authentication auth = validateToken(token);
            SecurityContextHolder.getContext().setAuthentication(auth);
        }
        
        filterChain.doFilter(request, response);
    }
    
    private Authentication validateToken(String token) {
        // 实现token验证逻辑
        return new UsernamePasswordAuthenticationToken(
            "user", null, List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
    }
}
```

## 5. 过滤器链的匹配和执行机制

### 5.1 匹配机制
```java
// 伪代码：过滤器链选择逻辑
public SecurityFilterChain getChain(HttpServletRequest request) {
    for (SecurityFilterChain chain : filterChains) {
        if (chain.matches(request)) {
            return chain;
        }
    }
    return null; // 无匹配链，跳过Spring Security保护
}
```

### 5.2 执行流程
1. **请求到达**：Servlet容器接收HTTP请求
2. **链选择**：根据请求URL选择匹配的SecurityFilterChain
3. **过滤器执行**：按顺序执行链中的所有过滤器
4. **访问决策**：FilterSecurityInterceptor做最终访问控制
5. **资源访问**：请求到达目标控制器或资源

## 6. 常见问题和最佳实践

### 6.1 常见问题

#### 问题1：过滤器顺序错误
```java
// 错误：CORS过滤器必须在CSRF之前
http.addFilterBefore(corsFilter(), CsrfFilter.class);

// 正确
http.cors(withDefaults()); // 使用内置的CORS配置
```

#### 问题2：多个过滤器链冲突
```java
// 使用明确的路径匹配，避免重叠
@Bean
@Order(1)
public SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/api/**");
    // ... 配置
}

@Bean
@Order(2)
public SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    http.securityMatcher("/**");
    // ... 配置
}
```

### 6.2 最佳实践

1. **最小权限原则**：只添加必要的过滤器
2. **性能优化**：
   ```java
   // 对于API端点，禁用不必要的过滤器
   http
       .securityMatcher("/api/**")
       .csrf().disable()
       .sessionManagement().sessionCreationPolicy(SessionCreationPolicy.STATELESS);
   ```

3. **调试技巧**：
   ```java
   @Configuration
   public class SecurityDebugConfig {
       
       @EventListener
       public void onFilterChainBuild(FilterChainBuildEvent event) {
           // 打印过滤器链信息
           event.getSecurityFilterChains().forEach(chain -> {
               System.out.println("Filter Chain: " + chain);
           });
       }
   }
   ```

## 7. 版本差异说明

### 7.1 Spring Security 5.x vs 6.x
- **5.x**：使用`WebSecurityConfigurerAdapter`（已弃用）
- **6.x**：基于组件的配置，使用`SecurityFilterChain` Bean

### 7.2 迁移示例
```java
// Spring Security 5.x（旧方式）
@Configuration
public class OldSecurityConfig extends WebSecurityConfigurerAdapter {
    @Override
    protected void configure(HttpSecurity http) throws Exception {
        http.authorizeRequests()
            .antMatchers("/public/**").permitAll()
            .anyRequest().authenticated();
    }
}

// Spring Security 6.x（新方式）
@Configuration
public class NewSecurityConfig {
    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/public/**").permitAll()
            .anyRequest().authenticated()
        );
        return http.build();
    }
}
```

## 8. 总结

Spring Security过滤器链的执行顺序是其安全功能的基础。理解这个顺序对于：
- 正确配置安全策略
- 添加自定义安全逻辑
- 调试安全相关问题
- 优化应用性能

至关重要。通过合理配置过滤器链和顺序，可以构建既安全又高效的应用程序。

---

**文档版本**：1.0  
**适用版本**：Spring Security 5.7+  
**最后更新**：2024年1月  
**注意事项**：具体过滤器顺序可能因Spring Security版本和配置方式略有不同