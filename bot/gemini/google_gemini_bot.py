# encoding:utf-8

"""
Google gemini bot

@author zhayujie
@Date 2023/12/15

Edited at 2026/5/20
Support new Gemini Models (e.g. Gemini 3.1 Pro)
@editor: ArcadiaE

"""

from bot.bot import Bot
from google import genai
from google.genai import types
from bot.session_manager import SessionManager
from bridge.context import ContextType, Context
from bridge.reply import Reply, ReplyType
from common.log import logger
from config import conf
from bot.chatgpt.chat_gpt_session import ChatGPTSession

class GoogleGeminiBot(Bot):

    def __init__(self):
        super().__init__()
        self.api_key = conf().get("gemini_api_key")
        self.sessions = SessionManager(ChatGPTSession, model=conf().get("model") or "gpt-3.5-turbo")
        self.model = conf().get("model") or "gemini-1.5-pro"
        if self.model == "gemini":
            self.model = "gemini-1.5-pro"

    def reply(self, query, context: Context = None) -> Reply:
        try:
            session_id = context["session_id"]

            if context.type == ContextType.IMAGE_CREATE:
                from bot.chatgpt.chat_gpt_bot import ChatGPTBot

                image_bot = ChatGPTBot()
                img_reply = image_bot.reply(query, context)

                if img_reply and img_reply.type != ReplyType.ERROR:
                    img_reply.type = ReplyType.IMAGE

                return img_reply

            if context.type != ContextType.TEXT:
                logger.warn(f"[Gemini] Unsupported message type, type={context.type}")
                return Reply(ReplyType.TEXT, None)

            logger.info(f"[Gemini] query={query}")
            session = self.sessions.session_query(query, session_id)

            gemini_messages, system_instruction = self._convert_to_gemini_messages(self.filter_messages(session.messages))
            logger.debug(f"[Gemini] messages={gemini_messages}")

            client = genai.Client(api_key=self.api_key)

            safety_settings = [
                types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
                types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            ]

            config = types.GenerateContentConfig(
                safety_settings=safety_settings,
                system_instruction=system_instruction
            )

            response = client.models.generate_content(
                model=self.model,
                contents=gemini_messages,
                config=config
            )

            if response.text:
                reply_text = response.text
                logger.info(f"[Gemini] reply={reply_text}")
                self.sessions.session_reply(reply_text, session_id)
                return Reply(ReplyType.TEXT, reply_text)
            else:
                logger.warning("[Gemini] No valid response generated.")
                error_message = "No valid response generated."
                self.sessions.session_reply(error_message, session_id)
                return Reply(ReplyType.ERROR, error_message)

        except Exception as e:
            logger.error(f"[Gemini] Error generating response: {str(e)}", exc_info=True)
            error_message = "Failed to invoke [Gemini] api!"
            # 确保在异常捕获时也能正确返回 Reply 对象
            return Reply(ReplyType.ERROR, error_message)

    def _convert_to_gemini_messages(self, messages: list):
        res = []
        system_instruction = None
        for msg in messages:
            if msg.get("role") == "system":
                system_instruction = msg.get("content")
                continue

            if msg.get("role") == "user":
                role = "user"
            elif msg.get("role") == "assistant":
                role = "model"
            else:
                continue

            res.append(types.Content(
                role=role,
                parts=[types.Part.from_text(text=msg.get("content"))]
            ))
        return res, system_instruction

    @staticmethod
    def filter_messages(messages: list):
        res = []
        turn = "user"
        if not messages:
            return res
        for i in range(len(messages) - 1, -1, -1):
            message = messages[i]
            role = message.get("role")
            if role == "system":
                res.insert(0, message)
                continue
            if role != turn:
                continue
            res.insert(0, message)
            if turn == "user":
                turn = "assistant"
            elif turn == "assistant":
                turn = "user"
        return res