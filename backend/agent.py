import os
import json
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

# 定义结构化输出模型以保证模型输出的确定性与解析的稳健性
class EmailAnalysis(BaseModel):
    category: str = Field(description="分类结果，只能是以下三者之一: '需处理', '可稍后看', '直接删'")
    summary: str = Field(description="不超过50字的中文摘要，必须准确提炼邮件正文核心内容")
    reason: str = Field(description="不超过10个字的简短分类原因，解释为什么归入这一类")

class GmailAgent:
    def __init__(self):
        """
        初始化 Gemini 客户端
        """
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is missing.")
        # 使用最新的 google-genai SDK 客户端初始化
        self.client = genai.Client(api_key=api_key)

    def analyze_emails(self, emails: list) -> list:
        """
        批量使用 Gemini 分析邮件列表并输出结构化结果
        """
        analyzed_emails = []
        
        for email in emails:
            # 拼接提示词
            prompt = f"""
你是一个邮件智能分类和整理助手。请分析以下邮件并给出一个结构化的处理建议。
发件人: {email.get('sender')}
主题: {email.get('subject')}
正文预览: {email.get('body')}

分类规则:
1. 需处理 (Action required): 包含重要通知、急需回复的个人/工作事务、账单催缴、账户安全警报、验证码等。
2. 可稍后看 (Read later): 周报、非紧急订阅、行业资讯、社群讨论更新、已完成订单的收据等。
3. 直接删 (To be deleted): 纯广告推销、垃圾邮件、促销活动推广、无关通知、明显的自动营销邮件等。

请提取不超过50个字的中文摘要，并对其进行精准分类。
"""
            try:
                # 使用推荐的 gemini-2.5-flash 模型，调用 Structured Outputs (结构化输出)
                response = self.client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=EmailAnalysis,
                        temperature=0.2, # 降低温度保证分类的稳定性和一致性
                    ),
                )
                
                # 解析结构化 JSON 响应
                analysis_result = json.loads(response.text)
                
                # 合并分析结果和原始邮件属性
                analyzed_item = {
                    **email,
                    "category": analysis_result.get("category", "可稍后看"),
                    "summary": analysis_result.get("summary", ""),
                    "reason": analysis_result.get("reason", "")
                }
                analyzed_emails.append(analyzed_item)
                
            except Exception as e:
                print(f"Error calling Gemini API for email {email.get('id')}: {str(e)}")
                # 异常容错机制：提供默认归类，防止局部失败导致整批任务崩溃
                analyzed_item = {
                    **email,
                    "category": "可稍后看",
                    "summary": email.get("snippet", "")[:50],
                    "reason": "分析服务出错"
                }
                analyzed_emails.append(analyzed_item)
                
        return analyzed_emails
