import json
import logging

import requests

from copilot_api import CopilotApi, Selection, ASSISTANT_START, ASSISTANT_END
from templates import SYSTEM_RULES

class CopilotGeminiApi(CopilotApi):
  URL = 'https://generativelanguage.googleapis.com/v1beta'
  
  def __init__(self):
    super().__init__()
    self.url = self.url or self.URL
    self.url += f'/models/{self.model}:generateContent'
  
  def get_code(self, text: str, selection: Selection, file: str, indent: int = None) -> str:
    rules = self._build_code_rules(text, selection, file, indent)
    system_prompt = self.__convert_to_system_prompt(rules)
    contents = self.__convert_to_contents(rules)

    return self.__send_contents(contents, system_prompt)
  
  def get_context_chat_response(self, text: str, selection: Selection, file: str) -> str:
    rules = self._build_context_chat_rules(text, selection, file)
    system_prompt = self.__convert_to_system_prompt(rules)
    contents = self.__convert_to_contents(rules)
    
    result = self.__send_contents(contents, system_prompt)
    result = f'{ASSISTANT_START}\n{result}\n{ASSISTANT_END}'
    return result
  
  def get_chat_response(self, text: str) -> str:
    system_prompt = SYSTEM_RULES.strip()
    contents = self.__convert_to_contents(self._parse_chat_input(text))
    
    result = self.__send_contents(contents, system_prompt)
    result = f'{ASSISTANT_START}\n{result}\n{ASSISTANT_END}'
    return result
  
  @classmethod
  def get_models(cls) -> list:
    logger = logging.getLogger('copilot')
    headers = cls._get_headers()
    url = cls.url or cls.URL
    url += '/models'
    
    logger.info(url)
    response = requests.get(url, headers=headers)
    
    if response.ok:
      data = response.json()
      logger.debug(data)
      
      result = []
      for item in data['models']:
        model = item['name'].replace('models/', '')
        if model.startswith('gemini-'):
          result.append(model)
      return result

    logger.error(f'{response.status_code} :: {response.text}')
    return []
  
  @classmethod
  def _get_headers(cls) -> dict:
    return {
      'x-goog-api-key': cls.token,
    }
  
  def __send_contents(self, contents: list, system_prompt: str) -> str:
    body = {
      'contents': contents,
      'systemInstruction': {
        'parts': [{'text': system_prompt}]
      },
      'generationConfig': {
        'temperature': 0,
        'candidateCount': 1,
      },
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

    if data.get('candidates'):
      try:
        result = data['candidates'][0]['content']['parts'][0]['text']
      except KeyError as ex:
        self.logger.error(f'Response parse key error: {ex}')
        return text
    
    return result
  
  def __convert_to_contents(self, rules: list) -> list:
    result = []
    for rule in rules:
      role = rule['role']
      
      if role == 'assistant':
        result.append({
          'role': 'model',
          'parts': [{'text': rule['content']}]
        })
      
      if role == 'user':
        result.append({
          'role': 'user',
          'parts': [{'text': rule['content']}]
        })
    return result

  def __convert_to_system_prompt(self, rules: list) -> str:
    result = ''
    for rule in rules:
      if rule['role'] == 'system':
        result += rule['content']
    return result
