import json
import logging

import requests

from copilot_api import CopilotApi, Selection, ASSISTANT_START, ASSISTANT_END
from templates import SYSTEM_RULES

class CopilotGptApi(CopilotApi):
  URL = 'https://api.openai.com/v1/chat/completions'
  
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
    url = 'https://api.openai.com/v1/models'
    
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
      'Authorization': f'Bearer {cls.token}',
    }
  
  def __chat_completion(self, messages: list) -> str:
    body = {
      'messages': messages,
      'model': self.model,
      'n': 1,
    }
    
    if self.__supports_temperature():
      body.update({'temperature': 0})
    
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
  
  def __supports_temperature(self) -> bool:
    return not any(self.model.startswith(prefix) for prefix in ['gpt-5-', 'o1-', 'o3-', 'o4-'])
