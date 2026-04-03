import os
import json
import time
import logging

from abc import ABC, abstractmethod
from dataclasses import dataclass

import requests

from templates import (
  ADD_CODE_SYSTEM_RULES, EDIT_CODE_SYSTEM_RULES, NEW_CODE_SYSTEM_RULES, CODE_USER_REQUEST, PYTHON_RULES, JAVA_RULES,
  SYSTEM_RULES, CONTEXT_SELECTION, CONTEXT_FILE, USER_REQUEST,
)
from utils import get_line_number

ASSISTANT_START = '[[ ASSISTANT ]]'
ASSISTANT_END = '[[ #ASSISTANT ]]'

class CopilotConfigurationError(Exception): pass
class CopilotRequestError(Exception): pass

@dataclass
class Selection:
  text: str
  context: str
  type: str
  start: int
  end: int

  @property
  def is_selected(self) -> bool:
    return bool(self.text.strip())

  @property
  def is_empty_context(self) -> bool:
    return not self.context.strip()

  def start_line(self) -> int:
    return get_line_number(self.context, self.start)

  def end_line(self) -> int:
    return get_line_number(self.context, self.end)


class CopilotApi(ABC):
  url = None
  model = None
  token = None

  def __init__(self):
    self.logger = logging.getLogger('copilot')

  @abstractmethod
  def get_code(self, text: str, selection: Selection, file: str, indent: int = None) -> str:
    """
    text: the user code request
    selection: currently selected text in the context, full text and selected positions in it
    file: current context file path, or null for a new view
    indent: preferred indentation for the response
    """

  @abstractmethod
  def get_context_chat_response(self, text: str, selection: Selection, file: str) -> str:
    """
    text: the entire current chat text, initial user request, or full history with user/assistant content
    selection: currently selected text in the context, full text and selected positions in it
    file: current context file path, or null for a new view
    """

  @abstractmethod
  def get_chat_response(self, text: str) -> str:
    """
    Chat flow includes a chain of pairs of user request and assistant response delimited by defined strings
    Each consecutive user request is sent with the current context in the form of all previous request/response pairs
    Example of chat flow (each real sequence is separated visually with multiple new lines):
    [user request 1]
    [[ ASSISTANT ]]
    [response 1]
    [[ #ASSISTANT ]]
    [user request 2]
    [[ ASSISTANT ]]
    [response 2]
    [[ #ASSISTANT ]]
    """

  @classmethod
  @abstractmethod
  def get_models(cls) -> list:
    pass

  @classmethod
  @abstractmethod
  def _get_headers(cls) -> dict:
    pass

  def _send_request(self, body: dict) -> str:
    headers = self._get_headers()

    self.logger.info(self.url)
    self.logger.info(f">> {self.model}")
    self.logger.debug(f'>> {json.dumps(body)}')

    start_time = time.time()
    response = requests.post(self.url, headers=headers, json=body)

    self.logger.debug(f'time: {(time.time() - start_time):.2f} s')

    if response.ok:
      self.logger.debug(f'<< {response.text}')
      return response.text

    error = f'{response.status_code} :: {response.text}'
    self.logger.error(error)
    raise CopilotRequestError(error)

  def _build_code_rules(self, user_request: str, selection: Selection, file: str, indent: int) -> list:
    file = file or 'untitled'

    return [
      {
        'role': 'system',
        'content': self.__build_code_system_rules(selection.is_empty_context, selection.is_selected, selection.type, indent)
      },
      {
        'role': 'user',
        'content': self.__build_code_request(user_request, selection, file)
      },
    ]

  def _build_context_chat_rules(self, user_request: str, selection: Selection, file: str) -> list:
    file = file or 'untitled'

    messages = [{
      'role': 'system',
      'content': SYSTEM_RULES.strip()
    }]

    history = self._parse_chat_input(user_request)
    messages.extend(history[:-1])

    # Add context with full file text, selection, before the current user query
    file_name = os.path.basename(file)

    content = '<attachments>'
    if selection.is_selected:
      text = CONTEXT_SELECTION.format(
        file_name=file_name,
        type=selection.type or '',
        start_line=selection.start_line(),
        end_line=selection.end_line(),
        text=selection.text
      )
      content += text
    content += CONTEXT_FILE.format(name=file_name, path=file, text=selection.context)
    content += '</attachments>'

    messages.append({
      'role': 'user',
      'content': content
    })

    user_request = history[-1]['content']
    messages.append({
      'role': 'user',
      'content': USER_REQUEST.format(content=user_request).strip()
    })

    return messages

  def _parse_chat_input(self, text: str) -> list:
    messages = []
    content = ''

    lines = text.strip().split('\n')
    total = len(lines)

    for i in range(total):
      line = lines[i]

      if line == ASSISTANT_START:
        current_role = 'user'
      if line == ASSISTANT_END:
        current_role = 'assistant'

      if line in [ASSISTANT_START, ASSISTANT_END]:
        messages.append({
          'role': current_role,
          'content': content.strip()
        })
        content = ''
        continue

      content += line + '\n'

    if content.strip():
      messages.append({
        'role': 'user',
        'content': content.strip()
      })

    return messages

  def __build_code_system_rules(self, is_empty_file: bool, is_selected: bool, type: str, indent: int) -> str:
    if is_empty_file:
      content = NEW_CODE_SYSTEM_RULES
    else:
      content = EDIT_CODE_SYSTEM_RULES if is_selected else ADD_CODE_SYSTEM_RULES

    if indent:
      content += f'Use indentation equal to {indent} spaces.\n'

    if type == 'python':
      content += PYTHON_RULES
    if type == 'java':
      content += JAVA_RULES

    return content.strip()

  def __build_code_request(self, user_request: str, selection: Selection, file: str) -> str:
    if selection.is_empty_context:
      return CODE_USER_REQUEST.format(content=user_request).strip()

    file_name = os.path.basename(file)

    content = '<attachments>'
    if selection.is_selected:
      text = CONTEXT_SELECTION.format(
        file_name=file_name,
        type=selection.type or '',
        start_line=selection.start_line(),
        end_line=selection.end_line(),
        text=selection.text
      )
      content += text
    content += CONTEXT_FILE.format(name=file_name, path=file, text=selection.context)
    content += '</attachments>'

    if selection.is_selected:
      content += CODE_USER_REQUEST.format(content=user_request)
      content += f'The modified selected code from position {selection.start} to {selection.end} without ``` is:'
      return content.strip()

    content += CODE_USER_REQUEST.format(content=user_request)
    content += f'The code that would fit at position {selection.start} without ``` is:'
    return content.strip()


class TokenManager:
  cache_path = f'{os.path.dirname(os.path.realpath(__file__))}/.cache'

  @classmethod
  def cache_token(cls, key: str, token: str) -> None:
    cache_data = {}

    if os.path.exists(cls.cache_path):
      with open(cls.cache_path, 'r') as f:
        data = f.read()
      if data.strip():
        cache_data = json.loads(data)

    cache_data[key] = token
    with open(cls.cache_path, 'w') as f:
      json.dump(cache_data, f)

  @classmethod
  def uncache_token(cls, key: str) -> str:
    if not os.path.exists(cls.cache_path):
      return None

    with open(cls.cache_path, 'r') as f:
      data = f.read()

    if not data.strip():
      return None

    cache_data = json.loads(data)
    return cache_data.get(key)
