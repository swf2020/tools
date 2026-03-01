# Spring IOC容器启动流程（refresh()方法12步详解）

## 概述

Spring Framework的核心是IOC（控制反转）容器，它负责管理应用中的所有Bean及其依赖关系。容器启动的核心入口是`AbstractApplicationContext.refresh()`方法，该方法包含了完整的容器初始化流程。本文将详细解析refresh()方法的12个关键步骤。

## refresh()方法整体流程

```java
public void refresh() throws BeansException, IllegalStateException {
    synchronized (this.startupShutdownMonitor) {
        // 步骤1：准备工作
        prepareRefresh();
        
        // 步骤2：获取BeanFactory
        ConfigurableListableBeanFactory beanFactory = obtainFreshBeanFactory();
        
        // 步骤3：配置BeanFactory
        prepareBeanFactory(beanFactory);
        
        try {
            // 步骤4：BeanFactory后置处理
            postProcessBeanFactory(beanFactory);
            
            // 步骤5：执行BeanFactoryPostProcessor
            invokeBeanFactoryPostProcessors(beanFactory);
            
            // 步骤6：注册BeanPostProcessor
            registerBeanPostProcessors(beanFactory);
            
            // 步骤7：初始化MessageSource
            initMessageSource();
            
            // 步骤8：初始化事件广播器
            initApplicationEventMulticaster();
            
            // 步骤9：子类特殊处理
            onRefresh();
            
            // 步骤10：注册监听器
            registerListeners();
            
            // 步骤11：完成BeanFactory初始化
            finishBeanFactoryInitialization(beanFactory);
            
            // 步骤12：完成刷新
            finishRefresh();
        } catch (BeansException ex) {
            // 异常处理...
            destroyBeans();
            cancelRefresh(ex);
            throw ex;
        } finally {
            // 清理资源...
            resetCommonCaches();
        }
    }
}
```

## 详细步骤解析

### 步骤1：prepareRefresh() - 准备上下文环境

**作用**：初始化Spring应用上下文的环境状态，为后续加载做准备。

**关键操作**：
- 设置容器启动时间（startupDate）
- 设置容器状态为激活（active）
- 初始化属性源（PropertySources）
- 验证必要的环境属性
- 创建早期应用事件集合（earlyApplicationEvents）

**代码要点**：
```java
protected void prepareRefresh() {
    this.startupDate = System.currentTimeMillis();
    this.closed.set(false);
    this.active.set(true);
    
    // 初始化环境属性
    initPropertySources();
    
    // 验证必要属性
    getEnvironment().validateRequiredProperties();
    
    // 初始化早期事件监听器
    this.earlyApplicationEvents = new LinkedHashSet<>();
}
```

### 步骤2：obtainFreshBeanFactory() - 获取BeanFactory

**作用**：创建或刷新BeanFactory实例，加载Bean定义。

**关键操作**：
- 刷新底层BeanFactory（AbstractRefreshableApplicationContext）
- 加载Bean定义（loadBeanDefinitions）
- 返回可配置的BeanFactory实例

**对于不同应用上下文**：
- **GenericApplicationContext**：使用内部默认的BeanFactory
- **AbstractRefreshableApplicationContext**：创建新的BeanFactory并加载定义

**代码要点**：
```java
protected ConfigurableListableBeanFactory obtainFreshBeanFactory() {
    // 如果是可刷新的应用上下文
    refreshBeanFactory();
    
    // 返回BeanFactory
    return getBeanFactory();
}
```

### 步骤3：prepareBeanFactory(beanFactory) - 配置BeanFactory

**作用**：配置BeanFactory的标准特性，如类加载器、后置处理器等。

**关键操作**：
- 设置类加载器
- 设置表达式解析器（SpEL）
- 添加属性编辑器注册器
- 添加ApplicationContextAwareProcessor
- 忽略Aware接口的依赖注入
- 注册可解析的依赖
- 注册环境Bean

**代码要点**：
```java
protected void prepareBeanFactory(ConfigurableListableBeanFactory beanFactory) {
    // 设置类加载器
    beanFactory.setBeanClassLoader(getClassLoader());
    
    // 设置SpEL表达式解析器
    beanFactory.setBeanExpressionResolver(new StandardBeanExpressionResolver(beanFactory.getBeanClassLoader()));
    
    // 添加属性编辑器注册器
    beanFactory.addPropertyEditorRegistrar(new ResourceEditorRegistrar(this, getEnvironment()));
    
    // 添加ApplicationContextAwareProcessor
    beanFactory.addBeanPostProcessor(new ApplicationContextAwareProcessor(this));
    
    // 忽略特定接口的自动装配
    beanFactory.ignoreDependencyInterface(EnvironmentAware.class);
    beanFactory.ignoreDependencyInterface(EmbeddedValueResolverAware.class);
    // ... 其他Aware接口
    
    // 注册可解析依赖
    beanFactory.registerResolvableDependency(BeanFactory.class, beanFactory);
    beanFactory.registerResolvableDependency(ResourceLoader.class, this);
    beanFactory.registerResolvableDependency(ApplicationEventPublisher.class, this);
    beanFactory.registerResolvableDependency(ApplicationContext.class, this);
}
```

### 步骤4：postProcessBeanFactory(beanFactory) - BeanFactory后置处理

**作用**：允许子类在标准初始化后对BeanFactory进行自定义配置。

**关键操作**：
- 模板方法，默认空实现
- Web应用上下文会注册Servlet相关的作用域
- 添加Web特定的Bean后置处理器

**扩展点**：这是Spring留给子类进行扩展的关键步骤，子类可以重写此方法来添加自定义配置。

### 步骤5：invokeBeanFactoryPostProcessors(beanFactory) - 执行BeanFactoryPostProcessor

**作用**：调用所有已注册的BeanFactoryPostProcessor，修改Bean定义。

**关键操作**：
- 识别并执行实现了PriorityOrdered、Ordered接口的BeanFactoryPostProcessor
- 执行普通的BeanFactoryPostProcessor
- 处理BeanDefinitionRegistryPostProcessor（特殊的BeanFactoryPostProcessor）
- ConfigurationClassPostProcessor在此步骤处理@Configuration类

**执行顺序**：
1. BeanDefinitionRegistryPostProcessor（实现PriorityOrdered）
2. BeanDefinitionRegistryPostProcessor（实现Ordered）
3. 其他BeanDefinitionRegistryPostProcessor
4. BeanFactoryPostProcessor（实现PriorityOrdered）
5. BeanFactoryPostProcessor（实现Ordered）
6. 其他BeanFactoryPostProcessor

**代码要点**：
```java
protected void invokeBeanFactoryPostProcessors(ConfigurableListableBeanFactory beanFactory) {
    PostProcessorRegistrationDelegate.invokeBeanFactoryPostProcessors(beanFactory, getBeanFactoryPostProcessors());
    
    // 关键处理器：ConfigurationClassPostProcessor
    // 负责处理@Configuration、@ComponentScan、@Import、@Bean等注解
}
```

### 步骤6：registerBeanPostProcessors(beanFactory) - 注册BeanPostProcessor

**作用**：注册BeanPostProcessor，用于在Bean初始化前后进行拦截处理。

**关键操作**：
- 获取所有BeanPostProcessor类型的Bean定义
- 按照优先级排序并注册到BeanFactory
- 实际调用在Bean创建过程中进行

**BeanPostProcessor类型**：
- **实例化前**：InstantiationAwareBeanPostProcessor
- **实例化后**：MergedBeanDefinitionPostProcessor
- **依赖注入后**：AutowiredAnnotationBeanPostProcessor
- **初始化前后**：CommonAnnotationBeanPostProcessor等

**执行顺序**：
1. PriorityOrdered接口的BeanPostProcessor
2. Ordered接口的BeanPostProcessor
3. 普通的BeanPostProcessor
4. 内部使用的BeanPostProcessor

### 步骤7：initMessageSource() - 初始化消息源

**作用**：初始化国际化消息源，用于支持i18n。

**关键操作**：
- 检查是否已存在名为"messageSource"的Bean
- 不存在则创建DelegatingMessageSource作为默认实现
- 注册到容器中

**代码要点**：
```java
protected void initMessageSource() {
    ConfigurableListableBeanFactory beanFactory = getBeanFactory();
    
    if (beanFactory.containsLocalBean(MESSAGE_SOURCE_BEAN_NAME)) {
        // 使用用户定义的消息源
        this.messageSource = beanFactory.getBean(MESSAGE_SOURCE_BEAN_NAME, MessageSource.class);
    } else {
        // 创建默认消息源
        DelegatingMessageSource dms = new DelegatingMessageSource();
        dms.setParentMessageSource(getInternalParentMessageSource());
        this.messageSource = dms;
        beanFactory.registerSingleton(MESSAGE_SOURCE_BEAN_NAME, this.messageSource);
    }
}
```

### 步骤8：initApplicationEventMulticaster() - 初始化事件广播器

**作用**：初始化应用事件广播器，用于发布和监听应用事件。

**关键操作**：
- 检查是否已存在名为"applicationEventMulticaster"的Bean
- 不存在则创建SimpleApplicationEventMulticaster作为默认实现
- 注册到容器中

**代码要点**：
```java
protected void initApplicationEventMulticaster() {
    ConfigurableListableBeanFactory beanFactory = getBeanFactory();
    
    if (beanFactory.containsLocalBean(APPLICATION_EVENT_MULTICASTER_BEAN_NAME)) {
        // 使用用户定义的事件广播器
        this.applicationEventMulticaster = beanFactory.getBean(
            APPLICATION_EVENT_MULTICASTER_BEAN_NAME, ApplicationEventMulticaster.class);
    } else {
        // 创建默认事件广播器
        this.applicationEventMulticaster = new SimpleApplicationEventMulticaster(beanFactory);
        beanFactory.registerSingleton(APPLICATION_EVENT_MULTICASTER_BEAN_NAME, 
                                     this.applicationEventMulticaster);
    }
}
```

### 步骤9：onRefresh() - 子类特殊处理

**作用**：模板方法，允许子类在Bean初始化前进行特殊处理。

**关键操作**：
- 默认空实现
- Web应用上下文（如Spring Boot）在此初始化主题源
- 启动内嵌Web服务器（Spring Boot）

**扩展点**：子类可以重写此方法实现特定的初始化逻辑。

### 步骤10：registerListeners() - 注册监听器

**作用**：注册应用事件监听器，包括早期事件的处理。

**关键操作**：
- 注册静态指定的监听器
- 注册实现了ApplicationListener接口的Bean
- 发布早期应用事件

**代码要点**：
```java
protected void registerListeners() {
    // 注册静态指定的监听器
    for (ApplicationListener<?> listener : getApplicationListeners()) {
        getApplicationEventMulticaster().addApplicationListener(listener);
    }
    
    // 注册实现了ApplicationListener接口的Bean
    String[] listenerBeanNames = getBeanNamesForType(ApplicationListener.class, true, false);
    for (String listenerBeanName : listenerBeanNames) {
        getApplicationEventMulticaster().addApplicationListenerBean(listenerBeanName);
    }
    
    // 发布早期事件
    Set<ApplicationEvent> earlyEventsToProcess = this.earlyApplicationEvents;
    this.earlyApplicationEvents = null;
    if (earlyEventsToProcess != null) {
        for (ApplicationEvent earlyEvent : earlyEventsToProcess) {
            getApplicationEventMulticaster().multicastEvent(earlyEvent);
        }
    }
}
```

### 步骤11：finishBeanFactoryInitialization(beanFactory) - 完成BeanFactory初始化

**作用**：**核心步骤**，初始化所有剩余的单例Bean（非懒加载）。

**关键操作**：
- 初始化ConversionService（类型转换服务）
- 注册默认的嵌入值解析器
- 初始化LoadTimeWeaverAware Bean
- 停止使用临时类加载器
- 冻结Bean定义配置
- 预实例化所有单例Bean

**核心方法**：`beanFactory.preInstantiateSingletons()`

**Bean创建流程**：
1. 获取Bean定义
2. 如果不是抽象、单例、非懒加载，则创建Bean
3. 如果是FactoryBean，则创建FactoryBean实例
4. 调用`getBean()` -> `doGetBean()` -> `createBean()` -> `doCreateBean()`

**doCreateBean详细流程**：
```java
protected Object doCreateBean(String beanName, RootBeanDefinition mbd, @Nullable Object[] args) {
    // 1. 实例化Bean（createBeanInstance）
    BeanWrapper instanceWrapper = createBeanInstance(beanName, mbd, args);
    
    // 2. 应用MergedBeanDefinitionPostProcessor
    applyMergedBeanDefinitionPostProcessors(mbd, beanType, beanName);
    
    // 3. 属性填充（populateBean）
    populateBean(beanName, mbd, instanceWrapper);
    
    // 4. 初始化Bean（initializeBean）
    exposedObject = initializeBean(beanName, exposedObject, mbd);
    
    // 5. 注册DisposableBean
    registerDisposableBeanIfNecessary(beanName, bean, mbd);
    
    return exposedObject;
}
```

### 步骤12：finishRefresh() - 完成刷新

**作用**：完成容器的刷新过程，发布相应事件。

**关键操作**：
- 清除资源缓存
- 初始化LifecycleProcessor
- 调用LifecycleProcessor的onRefresh()方法
- 发布ContextRefreshedEvent事件
- 向MBeanServer注册LiveBeansView

**代码要点**：
```java
protected void finishRefresh() {
    // 清除资源缓存
    clearResourceCaches();
    
    // 初始化生命周期处理器
    initLifecycleProcessor();
    
    // 调用生命周期处理器的onRefresh方法
    getLifecycleProcessor().onRefresh();
    
    // 发布容器刷新完成事件
    publishEvent(new ContextRefreshedEvent(this));
    
    // 注册到LiveBeansView（如果支持）
    LiveBeansView.registerApplicationContext(this);
}
```

## 关键扩展点总结

| 扩展点 | 接口/注解 | 执行时机 | 主要作用 |
|--------|-----------|----------|----------|
| BeanFactoryPostProcessor | BeanFactoryPostProcessor | 步骤5 | 修改Bean定义元数据 |
| BeanDefinitionRegistryPostProcessor | BeanDefinitionRegistryPostProcessor | 步骤5 | 注册额外的Bean定义 |
| BeanPostProcessor | BeanPostProcessor | Bean创建过程中 | Bean初始化前后处理 |
| Aware接口 | ApplicationContextAware等 | Bean初始化过程中 | 注入容器基础设施 |
| InitializingBean | InitializingBean | Bean初始化时 | 自定义初始化逻辑 |
| DisposableBean | DisposableBean | 容器关闭时 | 自定义销毁逻辑 |

## 常见问题与注意事项

1. **循环依赖问题**：Spring只能解决单例Bean通过setter注入的循环依赖，构造函数注入的循环依赖无法解决。

2. **BeanPostProcessor顺序**：实现PriorityOrdered和Ordered接口可以控制BeanPostProcessor的执行顺序。

3. **Bean定义加载顺序**：@Configuration类中的@Bean方法定义的Bean，其依赖关系会影响初始化顺序。

4. **懒加载Bean**：@Lazy注解标注的Bean不会在容器启动时初始化，而是在首次使用时创建。

5. **Profile激活**：@Profile注解的Bean只在对应Profile激活时才会注册。

6. **条件注解**：@Conditional注解用于条件化地注册Bean。

## 总结

Spring IOC容器的启动是一个精心设计的复杂过程，通过refresh()方法的12个步骤，容器完成了从环境准备到Bean实例化的完整生命周期。理解这一流程对于深入掌握Spring框架、排查启动问题和实现自定义扩展至关重要。每个步骤都提供了相应的扩展点，使得开发者可以在容器生命周期的不同阶段介入，实现自定义逻辑。

---

**文档版本**：1.0  
**适用版本**：Spring Framework 5.x  
**最后更新**：2024年