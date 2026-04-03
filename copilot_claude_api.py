import json
import logging

import requests

from copilot_api import CopilotApi, Selection, ASSISTANT_START, ASSISTANT_END
from templates import SYSTEM_RULES

class CopilotClaudeApi(CopilotApi):
  URL = 'https://api.anthropic.com/v1/messages'
  
  api_version = '2023-06-01'
  
  TOKENS_STD = 8192
  TOKENS_ADV = 16384
  
  def __init__(self):
    super().__init__()
    self.url = self.url or self.URL
  
  def get_code(self, text: str, selection: Selection, file: str, indent: int = None) -> str:
    rules = self._build_code_rules(text, selection, file, indent)
    system_prompt = self.__convert_to_system_prompt(rules)
    messages = self.__convert_to_messages(rules)
    
    return self.__send_messages(messages, system_prompt)
  
  def get_context_chat_response(self, text: str, selection: Selection, file: str) -> str:
    rules = self._build_context_chat_rules(text, selection, file)
    system_prompt = self.__convert_to_system_prompt(rules)
    messages = self.__convert_to_messages(rules)
    
    result = self.__send_messages(messages, system_prompt)
    result = f'{ASSISTANT_START}\n{result}\n{ASSISTANT_END}'
    return result
  
  def get_chat_response(self, text: str) -> str:
    system_prompt = SYSTEM_RULES.strip()
    messages = self.__convert_to_messages(self._parse_chat_input(text))
    
    result = self.__send_messages(messages, system_prompt)
    result = f'{ASSISTANT_START}\n{result}\n{ASSISTANT_END}'
    return result
  
  @classmethod
  def get_models(cls) -> list:
    logger = logging.getLogger('copilot')
    headers = cls._get_headers()
    url = 'https://api.anthropic.com/v1/models'
    
    logger.info(url)
    response = requests.get(url, headers=headers)
    
    if response.ok:
      data = response.json()
      logger.debug(data)
      
      result = [item['id'] for item in data['data']]
      return result
    
    logger.error(f'{response.status_code} :: {response.text}')
    return []
  
  @classmethod
  def _get_headers(cls) -> dict:
    return {
      'x-api-key': cls.token,
      'anthropic-version': cls.api_version,
    }
  
  def __send_messages(self, messages: list, system_prompt: str) -> str:
    body = {
      'messages': messages,
      'model': self.model,
      'temperature': 0,
      'max_tokens': self.TOKENS_STD,
      'system': [{
        'text': system_prompt,
        'type': 'text',
        'cache_control': {'type': 'ephemeral'}
      }]
    }
    
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

    if data.get('content'):
      try:
        result = data['content'][0]['text']
      except KeyError as ex:
        self.logger.error(f'Response parse key error: {ex}')
        return text
    
    return result
  
  def __convert_to_messages(self, rules: list) -> list:
    result = []
    for rule in rules:
      if rule['role'] in ['user', 'assistant']:
        result.append(rule)
    return result

  def __convert_to_system_prompt(self, rules: list) -> str:
    result = ''
    for rule in rules:
      if rule['role'] == 'system':
        result += rule['content']
    return result
