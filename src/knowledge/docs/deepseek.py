import json
import os
from datetime import datetime
import httpx
from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from typing import List, Tuple

# 全局变量用于记录结果
success_topics = []
failed_topics = []
lock = threading.Lock()

def read_topics_from_json(file_path):
    """读取 JSON 文件，提取所有主题"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"找不到配置文件: {file_path}")

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    topics = []
    for category, topic_list in data.items():
        for topic in topic_list:
            topics.append(topic.strip())  # 清理首尾空格
    return topics

def read_skill_file(file_path):
    """读取 skill.md 文件内容"""
    if not os.path.exists(file_path):
        print(f"警告: 文件 {file_path} 不存在，将使用空格作为附加提示。")
        return " "

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return content

def call_deepseek_api(client, prompt):
    """调用 DeepSeek API 并返回生成的文本"""
    try:
        response = client.chat.completions.create(
            model="deepseek-reasoner",  # 指定 reasoner 模型
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0,  # 设置 temperature 为 0
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"调用 API 时发生错误: {e}")
        return None

def process_single_topic(args):
    """处理单个主题的函数，用于线程池"""
    topic, skill_content, client, topic_index, total_topics = args
    
    print(f"[{topic_index}/{total_topics}] 开始处理主题: '{topic}'")
    
    # 构建提示词
    prompt = f"按照如下提示词帮我生成一份技术文档，主题为： {topic}\n\n{skill_content}".strip()
    
    # 调用API
    generated_content = call_deepseek_api(client, prompt)
    
    if generated_content is None:
        error_msg = "API调用失败"
        with lock:
            failed_topics.append((topic, error_msg))
        print(f"[{topic_index}/{total_topics}] 处理失败: '{topic}' - {error_msg}")
        return False
    
    # 保存内容到本地文件
    today_date = datetime.now().strftime("%Y-%m-%d")
    safe_topic = "".join(c for c in topic if c.isalnum() or c in (' ', '-', '_', '.')).rstrip()
    filename = f"{safe_topic}-{today_date}.md"
    
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(generated_content)
        print(f"[{topic_index}/{total_topics}] 内容已成功保存到: {filename}")
        
        # 记录成功
        with lock:
            success_topics.append(topic)
            
        return True
    except IOError as e:
        error_msg = f"文件保存失败: {str(e)}"
        with lock:
            failed_topics.append((topic, error_msg))
        print(f"[{topic_index}/{total_topics}] 处理失败: '{topic}' - {error_msg}")
        return False

def save_results_log():
    """保存处理结果日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    
    # 保存成功主题
    if success_topics:
        success_filename = f"success_topics_{timestamp}.txt"
        with open(success_filename, 'w', encoding='utf-8') as f:
            f.write("成功处理的主题列表:\n")
            f.write("=" * 50 + "\n")
            for topic in success_topics:
                f.write(f"- {topic}\n")
        print(f"成功主题已保存到: {success_filename}")
    
    # 保存失败主题
    if failed_topics:
        failure_filename = f"failed_topics_{timestamp}.txt"
        with open(failure_filename, 'w', encoding='utf-8') as f:
            f.write("处理失败的主题列表:\n")
            f.write("=" * 50 + "\n")
            for topic, error in failed_topics:
                f.write(f"- {topic}: {error}\n")
        print(f"失败主题已保存到: {failure_filename}")

def main():
    # 0. 读取 topic.json 和 skill.md
    topic_file_path = "topics.json"
    skill_file_path = "../.claude/skills/technical-document-generator/SKILL.md"

    try:
        topics = read_topics_from_json(topic_file_path)
        skill_content = read_skill_file(skill_file_path)
    except Exception as e:
        print(f"读取配置文件时出错: {e}")
        return

    if not topics:
        print("没有找到任何主题，程序退出。")
        return

    print(f"成功读取到 {len(topics)} 个主题")

    # 初始化 OpenAI 客户端
    os.environ.setdefault("DEEPSEEK_API_KEY", "sk-32651f9e81d94185b69933d936381a0b")
    api_key = os.getenv("DEEPSEEK_API_KEY", "sk-32651f9e81d94185b69933d936381a0b")

    if api_key == "YOUR_DEEPSEEK_API_KEY_HERE":
        print("\n--- 重要提示 ---")
        print("请先设置您的 DeepSeek API Key。")
        print("方法1: 在代码中将 'YOUR_DEEPSEEK_API_KEY_HERE' 替换为您的实际 Key。")
        print("方法2 (推荐): 设置环境变量 DEEPSEEK_API_KEY。")
        print("-----------------\n")
        return

    # 创建一个不验证 SSL 证书的 httpx 客户端
    http_client = httpx.Client(verify=False)

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.deepseek.com",
        http_client=http_client
    )

    # 设置并发参数
    MAX_WORKERS = 10  # 最大线程数，可根据需要调整
    
    print(f"开始并发处理 {len(topics)} 个主题，最大并发数: {MAX_WORKERS}")
    
    # 准备任务参数
    tasks = [(topic, skill_content, client, i+1, len(topics)) for i, topic in enumerate(topics)]
    
    # 使用线程池并发处理
    successful_count = 0
    failed_count = 0
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # 提交所有任务
        future_to_topic = {executor.submit(process_single_topic, task): task[0] for task in tasks}
        
        # 处理完成的任务
        for future in as_completed(future_to_topic):
            topic = future_to_topic[future]
            try:
                result = future.result()
                if result:
                    successful_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                print(f"处理主题 '{topic}' 时发生异常: {e}")
                with lock:
                    failed_topics.append((topic, str(e)))
                failed_count += 1

    # 显示处理结果
    print(f"\n处理完成!")
    print(f"成功: {successful_count} 个主题")
    print(f"失败: {failed_count} 个主题")
    
    # 保存结果日志
    save_results_log()
    
    print(f"\n最终统计:")
    print(f"总共处理: {len(topics)} 个主题")
    print(f"成功处理: {len(success_topics)} 个")
    print(f"处理失败: {len(failed_topics)} 个")

if __name__ == "__main__":
    main()