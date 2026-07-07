import base64
from datetime import datetime, timedelta
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

class GmailService:
    def __init__(self, creds_data: dict):
        """
        使用 OAuth 凭证初始化 Gmail 服务客户端。
        :param creds_data: 存储于 Session 中的 Google OAuth 凭证字典
        """
        self.creds = Credentials(
            token=creds_data.get('token'),
            refresh_token=creds_data.get('refresh_token'),
            token_uri=creds_data.get('token_uri'),
            client_id=creds_data.get('client_id'),
            client_secret=creds_data.get('client_secret'),
            scopes=creds_data.get('scopes')
        )
        self.service = build('gmail', 'v1', credentials=self.creds)

    def get_unread_emails(self, max_results: int = 50, days_ago: int = 7) -> list:
        """
        获取最近 X 天内的未读邮件，最多获取 max_results 封。
        遵循安全规范：只读取邮件内容，不进行持久化存储。
        """
        # 计算日期阈值 (以 YYYY/MM/DD 格式化以支持 Gmail query)
        date_threshold = (datetime.now() - timedelta(days=days_ago)).strftime('%Y/%m/%d')
        # 查询条件：未读，且在 date_threshold 日期之后
        query = f"is:unread after:{date_threshold}"
        
        try:
            results = self.service.users().messages().list(
                userId='me', q=query, maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            email_list = []
            
            for msg_ref in messages:
                # 获取单封邮件的完整细节
                msg = self.service.users().messages().get(
                    userId='me', id=msg_ref['id'], format='full'
                ).execute()
                
                email_data = self._parse_message_detail(msg)
                email_list.append(email_data)
                
            return email_list
        except Exception as e:
            print(f"Error fetching Gmail messages: {str(e)}")
            raise e

    def execute_batch_action(self, action: str, msg_ids: list):
        """
        批量对邮件进行操作 (标记已读、归档、彻底删除)。
        对于删除操作，前端需要支持二次确认。
        """
        if not msg_ids:
            return {"status": "success", "message": "No messages specified."}
            
        try:
            if action == "mark_read":
                # 标记已读：移除 UNREAD 标签
                self.service.users().messages().batchModify(
                    userId='me',
                    body={
                        "ids": msg_ids,
                        "removeLabelIds": ["UNREAD"]
                    }
                ).execute()
            elif action == "archive":
                # 归档：从收件箱移除 (移除 INBOX 标签)
                self.service.users().messages().batchModify(
                    userId='me',
                    body={
                        "ids": msg_ids,
                        "removeLabelIds": ["INBOX"]
                    }
                ).execute()
            elif action == "delete":
                # 删除：直接移到垃圾桶 (Trash)
                # 安全规范：删除是高危操作，但我们只对选中的邮件进行批量垃圾桶化，不进行彻底不可恢复的删除 (delete)。
                # 调用 batchDelete 会直接彻底销毁，我们推荐使用 batchModify 移除 INBOX 并加入 TRASH 标签，或者直接调用 trash 接口。
                for msg_id in msg_ids:
                    self.service.users().messages().trash(userId='me', id=msg_id).execute()
            else:
                raise ValueError(f"Unknown action: {action}")
                
            return {"status": "success", "message": f"Successfully performed action '{action}' on {len(msg_ids)} messages."}
        except Exception as e:
            print(f"Error executing batch action: {str(e)}")
            raise e

    def _parse_message_detail(self, msg: dict) -> dict:
        """
        解析 Gmail Message 详情，提取发件人、主题、正文、接收时间等字段。
        """
        payload = msg.get('payload', {})
        headers = payload.get('headers', [])
        
        # 提取核心 Header 字段
        subject = ""
        sender = ""
        date_str = ""
        
        for header in headers:
            name = header.get('name', '').lower()
            if name == 'subject':
                subject = header.get('value', '')
            elif name == 'from':
                sender = header.get('value', '')
            elif name == 'date':
                date_str = header.get('value', '')

        # 解析邮件正文
        body = self._extract_body(payload)
        
        return {
            "id": msg.get('id'),
            "threadId": msg.get('threadId'),
            "subject": subject,
            "sender": sender,
            "date": date_str,
            "snippet": msg.get('snippet', ''),
            "body": body[:2000]  # 仅截取前 2000 字符，保证输入给 Gemini API 时不会超出 Token 限制，并且保障隐私
        }

    def _extract_body(self, payload: dict) -> str:
        """
        递归解析 MIME 多部分结构中的文本正文。
        """
        body_text = ""
        
        # 如果有 parts，需要递归解析每一部分
        parts = payload.get('parts', [])
        if parts:
            for part in parts:
                body_text += self._extract_body(part)
        else:
            # 如果没有 parts，直接提取 body 数据
            body_data = payload.get('body', {}).get('data', '')
            mime_type = payload.get('mimeType', '')
            
            # 我们主要处理纯文本或 HTML 内容
            if ('text/plain' in mime_type or 'text/html' in mime_type) and body_data:
                try:
                    # Base64url 解码
                    decoded_bytes = base64.urlsafe_b64decode(body_data.encode('utf-8'))
                    body_text = decoded_bytes.decode('utf-8', errors='ignore')
                except Exception as e:
                    print(f"Error decoding body part: {str(e)}")
                    
        return body_text
