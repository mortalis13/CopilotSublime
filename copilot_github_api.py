import json
import datetime
import logging

import requests

from copilot_api import CopilotApi, TokenManager, Selection, ASSISTANT_START, ASSISTANT_END
from templates import SYSTEM_RULES

class CopilotGithubApi(CopilotApi):
  URL = 'https://api.githubcopilot.com/chat/completions'
  
  EDITOR_VERSION = 'vscode/1.108.2'
  TOKEN_CACHE_KEY = 'github_copilot_token'
  
  def __init__(self):
    super().__init__()
    self.url = self.url or self.URL
  
  def get_code(self, text: str, selection: Selection, file: str, indent: int = None) -> str:
    messages = self._build_code_rules(text, selection, file, indent)
    return self.__chat_completion(messages)

  def get_context_chat_response(self, text: str, selection: Selection, file: str) -> str:
    messages = self._build_context_chat_rules(text, selection, file)
    result = self.__chat_completion(messages)
    result = f'{ASSISTANT_START}\n{result}\n{ASSISTANT_END}'
    return result
  
  def get_chat_response(self, text: str) -> str:
    messages = [{
      'role': 'system',
      'content': SYSTEM_RULES.strip()
    }]
    messages.extend(self._parse_chat_input(text))
    
    result = self.__chat_completion(messages)
    result = f'{ASSISTANT_START}\n{result}\n{ASSISTANT_END}'
    return result
  
  @classmethod
  def get_models(cls) -> list:
    logger = logging.getLogger('copilot')
    headers = cls._get_headers()
    url = 'https://api.githubcopilot.com/models'
    
    logger.info(url)
    response = requests.get(url, headers=headers)
    
    if response.ok:
      data = response.json()
      logger.debug(data)
      
      data['data'].sort(key=lambda item: item['capabilities']['family'])
      result = []
      for item in data['data']:
        model = item['id']
        if item['capabilities']['type'] == 'chat' and model not in result:
          result.append(model)
      return result
    
    logger.error(f'{response.status_code} :: {response.text}')
    return []

  @classmethod
  def _get_headers(cls) -> dict:
    access_token = cls.__get_access_token(cls.token)
    headers = {
      'authorization': f'Bearer {access_token}',
      'editor-version': cls.EDITOR_VERSION,
    }
    return headers
  
  def __chat_completion(self, messages: list) -> str:
    body = {
      'messages': messages,
      'model': self.model,
      'temperature': 0,
      'n': 1,
    }
    
    for message in body['messages']:
      if message['role'] in ['system', 'user']:
        message['copilot_cache_control'] = {'type': 'ephemeral'}
    
    text = self._send_request(body)
    result = self.__parse_response(text)
    
    self.logger.debug(f"'''''''''''''\n{result}\n'''''''''''''")
    return result
  
  def __parse_response(self, text: str) -> str:
    try:
      data = json.loads(text)
    except json.JSONDecodeError:
      self.logger.error(f'Response JSON parse error')
      return text

    if data.get('choices'):
      try:
        result = data['choices'][0]['message']['content']
      except KeyError as ex:
        self.logger.error(f'Response parse key error: {ex}')
        return text
    
    return result
  
  @classmethod
  def __verify_token(cls, token: str) -> bool:
    if not token:
      return False
      
    if 'exp=' not in token:
      return False

    for item in token.split(';'):
      key, value = item.split('=')
      if key == 'exp':
        exp = int(value)
        if exp <= datetime.datetime.now().timestamp():
          return False
        break

    return True
      
  @classmethod
  def __get_access_token(cls, refresh_token: str) -> str:
    token = TokenManager.uncache_token(cls.TOKEN_CACHE_KEY)
    if cls.__verify_token(token):
      return token
    
    headers = {
      'authorization': f'token {refresh_token}',
      'editor-version': cls.EDITOR_VERSION,
    }

    url = 'https://api.github.com/copilot_internal/v2/token'
    response = requests.get(url, headers=headers)

    token = response.json().get('token')
    TokenManager.cache_token(cls.TOKEN_CACHE_KEY, token)
    return token
