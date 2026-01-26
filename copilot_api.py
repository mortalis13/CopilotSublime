import os
import json
import time
import logging
from dataclasses import dataclass

import requests

from templates import (
  ADD_CODE_SYSTEM_RULES, EDIT_CODE_SYSTEM_RULES, NEW_CODE_SYSTEM_RULES, CODE_USER_REQUEST, PYTHON_RULES, JAVA_RULES,
  SYSTEM_RULES, CONTEXT_SELECTION, CONTEXT_FILE, USER_REQUEST,
)
from utils import get_line_number

MODEL = 'gpt-4.1'
# gpt-4.1 gpt-4o gpt-4o-mini
EDITOR_VERSION = 'vscode/1.108.2'

ASSISTANT_START = '[[ ASSISTANT ]]'
ASSISTANT_END = '[[ #ASSISTANT ]]'

storage = {}

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


class Copilot:
  def __init__(self):
    self.logger = logging.getLogger('copilot')
  
  def _get_token(self) -> str:
    token = storage.get('token')
    if token: return token
    
    self.logger.debug(f'get token')
    token_path = f'{os.path.dirname(os.path.realpath(__file__))}/.copilot_token'
    with open(token_path, 'r') as f:
      access_token = f.read()
    
    headers = {
      'authorization': f'token {access_token}',
      'editor-version': EDITOR_VERSION,
    }
    url = 'https://api.github.com/copilot_internal/v2/token'
    
    response = requests.get(url, headers=headers)
    token = response.json().get('token')
    
    storage['token'] = token
    return token

  def _send_request(self, body: dict) -> dict:
    token = self._get_token()
    
    headers = {
      'authorization': f'Bearer {token}',
      'editor-version': EDITOR_VERSION,
    }
    
    url = 'https://api.githubcopilot.com/chat/completions'
    self.logger.info(url)
    
    self.logger.debug(f">> {body['model']}")
    self.logger.debug(f'>> {json.dumps(body)}')
    
    start_time = time.time()
    response = requests.post(url, headers=headers, json=body)
    
    self.logger.debug(f'time: {(time.time() - start_time):.2f} s')
    
    if response.ok:
      data = response.json()
      self.logger.debug(f'<< {json.dumps(data)}')
      self.logger.debug(f"<< {data['model']}")
      return data

    self.logger.debug(f'<< Raw text response: {response.text}')
    
    if response.status_code == 401 and 'token expired' in response.text:
      if 'token' in storage: del storage['token']
      return self._send_request(body)
    
    error = f'{response.status_code} :: {response.text}'
    self.logger.error(error)
    raise Exception(error)
    
  def _chat_completion(self, messages: list) -> str:
    body = {
      'messages': messages,
      'model': MODEL,
      'temperature': 0,
      'n': 1,
    }
    
    for message in body['messages']:
      if message['role'] in ['system', 'user']:
        message['copilot_cache_control'] = {'type': 'ephemeral'}
    
    data = self._send_request(body)
    
    result = None
    if data.get('choices'):
      try:
        result = data['choices'][0]['message']['content']
      except KeyError:
        pass
    
    self.logger.debug(f"'''''''''''''\n{result}\n'''''''''''''")
    return result
  
  
  # Code Generation
  
  def _build_code_system_rules(self, is_empty_file: bool, is_selected: bool, type: str, indent: int) -> str:
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
    
  def _build_code_request(self, user_request: str, selection: Selection, file: str) -> str:
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
    
  def get_code(self, text: str, selection: Selection, file: str, indent: int = None) -> str:
    """
    text: the user code request
    selection: currently selected text in the context, full text and selected positions in it
    file: current context file path, or null for a new view
    indent: preferred indentation for the response
    """
    file = file or 'untitled'
    
    messages = [
      {
        'role': 'system',
        'content': self._build_code_system_rules(selection.is_empty_context, selection.is_selected, selection.type, indent)
      },
      {
        'role': 'user',
        'content': self._build_code_request(text, selection, file)
      }
    ]
    
    return self._chat_completion(messages)


  # -- Context Chat
  
  def _build_chat_context(self, selection: Selection, file: str) -> str:
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

    return content.strip()
  
  def get_context_chat_response(self, text: str, selection: Selection, file: str) -> str:
    """
    text: the entire current chat text, initial user request, or full history with user/assistant content
    selection: currently selected text in the context, full text and selected positions in it
    file: current context file path, or null for a new view
    """
    file = file or 'untitled'
    
    messages = [{
      'role': 'system',
      'content': SYSTEM_RULES.strip()
    }]
    
    history = self._parse_chat_input(text)
    messages.extend(history[:-1])
    
    # Add context with full file text, selection, before the current user query
    messages.append({
      'role': 'user',
      'content': self._build_chat_context(selection, file)
    })
    
    user_request = history[-1]['content']
    messages.append({
      'role': 'user',
      'content': USER_REQUEST.format(content=user_request).strip()
    })
    
    result = self._chat_completion(messages)
    result = f'{ASSISTANT_START}\n{result}\n{ASSISTANT_END}'
    return result
  
  
  # General Chat
  
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
    messages = [{
      'role': 'system',
      'content': SYSTEM_RULES.strip()
    }]
    messages.extend(self._parse_chat_input(text))
    
    result = self._chat_completion(messages)
    result = f'{ASSISTANT_START}\n{result}\n{ASSISTANT_END}'
    return result
  
  
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
