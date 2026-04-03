import re
import json
import datetime
import logging

import requests

from copilot_api import CopilotApi, TokenManager, Selection, ASSISTANT_START, ASSISTANT_END
from copilot_claude_api import CopilotClaudeApi
from copilot_gpt_api import CopilotGptApi
from copilot_gemini_api import CopilotGeminiApi
from templates import SYSTEM_RULES
from utils import decode_jwt

class CopilotJbApi(CopilotApi):
  license = None

  URL = 'https://api.jetbrains.ai/user/v5/llm/chat/stream/v8'
  
  TOKEN_CACHE_KEY = 'jb_ai_token'
  
  def __init__(self):
    super().__init__()
    self.url = self.url or self.URL
  
  def get_code(self, text: str, selection: Selection, file: str, indent: int = None) -> str:
    rules = self._build_code_rules(text, selection, file, indent)
    messages = self.__convert_to_messages(rules)
    
    return self.__send_messages(messages)
  
  def get_context_chat_response(self, text: str, selection: Selection, file: str) -> str:
    rules = self._build_context_chat_rules(text, selection, file)
    messages = self.__convert_to_messages(rules)

    result = self.__send_messages(messages)
    result = f'{ASSISTANT_START}\n{result}\n{ASSISTANT_END}'
    return result
  
  def get_chat_response(self, text: str) -> str:
    messages = [{
      'type': 'system_message',
      'content': SYSTEM_RULES.strip()
    }]
    messages.extend(self.__convert_to_messages(self._parse_chat_input(text)))
    
    result = self.__send_messages(messages)
    result = f'{ASSISTANT_START}\n{result}\n{ASSISTANT_END}'
    return result
  
  @classmethod
  def get_models(cls) -> list:
    logger = logging.getLogger('copilot')
    headers = cls._get_headers()
    url = 'https://api.jetbrains.ai/user/v5/llm/profiles/v8'
    
    logger.info(url)
    response = requests.get(url, headers=headers)
    
    if response.ok:
      data = response.json()
      logger.debug(data)
      
      data['profiles'].sort(key=lambda item: item['provider'])
      result = [item['id'] for item in data['profiles'] if not item['id'].startswith('gpt-')]
      return result
    
    logger.error(f'{response.status_code} :: {response.text}')
    return []
  
  @classmethod
  def _get_headers(cls) -> dict:
    return cls.get_headers()
  
  def __send_messages(self, messages: list) -> str:
    body = {
      'prompt': 'ij.chat.request.new-chat',
      'profile': self.model,
      'chat': {
        'messages': messages
      },
    }
    
    text = self._send_request(body)
    result = self.__parse_response(text)
    
    self.logger.debug(f"'''''''''''''\n{result}\n'''''''''''''")
    return result
  
  def __parse_response(self, text: str) -> str:
    contents = []
    for line in text.splitlines():
      line = line.strip()
      
      if line.startswith('data: '):
        try:
          data_object = json.loads(line[6:])
          if data_object.get('type', '').lower() == 'content':
            contents.append(data_object.get('content', ''))
        except:
          self.logger.error(f'Error parsing JSON data for {line}')
          continue

    return ''.join(contents).strip()
  
  def __convert_to_messages(self, rules: list) -> list:
    result = []
    for rule in rules:
      role = rule['role']
      
      type = None
      if role == 'system':
        type = 'system_message'
      if role == 'user':
        type = 'user_message'
      if role == 'assistant':
        type = 'assistant_message_text'
        
      result.append({
        'type': type,
        'content': rule['content']
      })
    return result
  
  @classmethod
  def __verify_token(cls, token: str) -> bool:
    if not token:
      return False
    
    data = decode_jwt(token)
    if not data:
      return False
    
    if data.get('exp', 0) <= datetime.datetime.utcnow().timestamp():
      return False
    
    return True
  
  @classmethod
  def __get_access_token(cls, refresh_token: str) -> str:
    token = TokenManager.uncache_token(cls.TOKEN_CACHE_KEY)
    if cls.__verify_token(token):
      return token
    
    headers = {
      'authorization': f'Bearer {refresh_token}',
      'User-Agent': 'ktor-client',
    }
    body = {'licenseId': cls.license}
    
    url = 'https://api.jetbrains.ai/auth/jetbrains-jwt/provide-access/license/v2'
    response = requests.post(url, headers=headers, json=body)
    
    token = response.json().get('token')
    TokenManager.cache_token(cls.TOKEN_CACHE_KEY, token)
    return token
  
  @classmethod
  def get_headers(cls) -> dict:
    access_token = cls.__get_access_token(cls.token)
    headers = {
      'grazie-authenticate-jwt': access_token,
      'grazie-agent': '{"name":"aia:pycharm","version":"253.29346.331:253.29346.308"}',
      'User-Agent': 'ktor-client',
    }
    return headers
  
  @classmethod
  def extract_models_by_fail(cls, url: str, body: dict) -> list:
    logger = logging.getLogger('copilot')
    logger.info('get proxy models')
    headers = cls.get_headers()
    
    logger.info(url)
    response = requests.post(url, headers=headers, json=body)
    
    logger.debug(f'{response.status_code} :: {response.text}')
    
    result = []
    if response.status_code == 400 and 'Unsupported model' in response.text:
      matches = re.findall(r'\[(.+?)\]', response.text)
      if matches:
        result = matches[0].split(', ')
    
    return result


class CopilotClaudeJbApi(CopilotClaudeApi):
  URL = 'https://api.jetbrains.ai/user/v5/llm/anthropic/v1/messages'

  @classmethod
  def get_models(cls) -> list:
    body = {
      'messages': 'test',
      'model': 'abc',
      'max_tokens': 100,
    }
    result = CopilotJbApi.extract_models_by_fail(cls.url or cls.URL, body)
    return result
  
  @classmethod
  def _get_headers(cls) -> dict:
    return CopilotJbApi.get_headers()


class CopilotGptJbApi(CopilotGptApi):
  URL = 'https://api.jetbrains.ai/user/v5/llm/openai/v1/chat/completions'

  @classmethod
  def get_models(cls) -> list:
    body = {
      'messages': 'test',
      'model': 'abc',
    }
    result = CopilotJbApi.extract_models_by_fail(cls.url or cls.URL, body)
    return result
  
  @classmethod
  def _get_headers(cls) -> dict:
    return CopilotJbApi.get_headers()


class CopilotGeminiJbApi(CopilotGeminiApi):
  URL = 'https://api.jetbrains.ai/user/v5/llm/google/v1/vertex/v1/projects/grazie-production/locations/global/publishers/google'
  
  def __init__(self):
    self.url = self.url or self.URL
    super().__init__()

  @classmethod
  def get_models(cls) -> list:
    body = {
      'contents': 'test',
    }
    url = cls.url or cls.URL
    url += '/models/abc:generateContent'
    result = CopilotJbApi.extract_models_by_fail(url, body)
    return result
  
  @classmethod
  def _get_headers(cls) -> dict:
    return CopilotJbApi.get_headers()
