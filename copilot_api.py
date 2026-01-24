import os
import json
import time
import logging
from dataclasses import dataclass

import requests

from templates import (
  ADD_CODE_SYSTEM_RULES, EDIT_CODE_SYSTEM_RULES, EDIT_CODE_CONTEXT_WITH_SELECTION, ADD_CODE_CONTEXT_FILE, CODE_USER_REQUEST,
  SYSTEM_RULES, CONTEXT_SELECTION, CONTEXT_FILE, USER_REQUEST,
)

MODEL = 'gpt-4.1'
# gpt-4.1 gpt-4o o1 gpt-4o-mini o1-mini o3-mini

ASSISTANT_START = '[[ ASSISTANT ]]'
ASSISTANT_END = '[[ #ASSISTANT ]]'
SELECTED_CODE_PLACEHOLDER = '$SELECTION_PLACEHOLDER$'
INSERT_PLACEHOLDER = '$PLACEHOLDER$'

storage = {}

@dataclass
class Selection:
  text: str
  type: str
  line_start: int
  line_end: int


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
      'editor-version': 'vscode/1.95.3',
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
      'editor-version': 'vscode/1.95.3',
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
      content = (
        'The user needs help to write some new code.\n'
        f"Respond only with a code block in {type or 'python'}.\n"
      )
    
    else:
      content = EDIT_CODE_SYSTEM_RULES if is_selected else ADD_CODE_SYSTEM_RULES
      
    if indent:
      content += f'Use indentation equal to {indent} spaces.\n'
    
    if type == 'python':
      content += (
        'Generate docstrings for new methods only.\n'
        'If an existing method does not have a docstring, leave it without a docstring\n'
        'If only docstring is requested, do not repeat given code, only reply with docstring wrapped in """.\n'
        'Always add type hints to the methods signatures using Python 3.10 built-in types rather that the typing library.\n'
        'Use single quotes for strings.\n'
      )
    
    if type == 'java':
      content += (
        'Add proper javadoc comments for methods signatures.\n'
        'In the multi-block structures, like "if-else", "try-catch" etc., the start of each block should be on its own line, as in ```if (condition) {\n}\nelse {\n}\nelse{\n}\n```.\n'
      )
    
    return content.strip()
    
  def _build_code_request(self, user_request: str, selection: Selection, file_text: str, file: str, type: str) -> str:
    is_empty_file = not file_text.strip()
    
    if is_empty_file:
      return CODE_USER_REQUEST.format(content=user_request).strip()
    
    if selection:
      content = EDIT_CODE_CONTEXT_WITH_SELECTION.format(
        file_path=file,
        file_text=file_text,
        selected_text=selection.text,
        type=type,
      )
      content += CODE_USER_REQUEST.format(content=user_request)
      content += 'The modified $SELECTION_PLACEHOLDER$ code without ``` is:'
      return content.strip()
      
    content = ADD_CODE_CONTEXT_FILE.format(file_path=file, file_text=file_text, type=type)
    content += CODE_USER_REQUEST.format(content=user_request)
    content += 'The code that would fit at $PLACEHOLDER$ without ``` is:'
    return content.strip()
    
  def get_code(self, text: str, selection: Selection, file_text: str, file: str, type: str = None, indent: int = None) -> str:
    '''
    text: the user code request
    selection: currently selected code, null if no selection
    file_text: full text of the current file or new view
    file: current context file path, null if no file is associated, as in new view
    type: code type
    indent: preferred indentation for the response
    '''
    is_empty_file = not file_text.strip()
    is_selected = selection is not None
    file = file or 'untitled'
    type = type or ''
    
    messages = [
      {
        'role': 'system',
        'content': self._build_code_system_rules(is_empty_file, is_selected, type, indent)
      },
      {
        'role': 'user',
        'content': self._build_code_request(text, selection, file_text, file, type)
      }
    ]
    
    return self._chat_completion(messages)


  # -- Context Chat
  
  def _build_chat_context(self, selection: Selection, file: str) -> str:
    if os.path.isfile(file):
      file_path = file
      file_name = os.path.basename(file_path)
      with open(file_path, 'r', encoding='utf8') as f:
        file_text = f.read()
    
    else:
      file_path = 'untitled:untitled'
      file_name = 'untitled'
      file_text = file
      
    content = '<attachments>'
    if selection:
      text = CONTEXT_SELECTION.format(
        file_name=file_name,
        type=selection.type or '',
        line_start=selection.line_start,
        line_end=selection.line_end,
        text=selection.text
      )
      content += text
    content += CONTEXT_FILE.format(name=file_name, path=file_path, text=file_text)
    content += '</attachments>'

    return content.strip()
  
  def get_context_chat_response(self, text: str, selection: Selection, file: str) -> str:
    '''
    text: the entire current chat text, initial user request, or full history with user/assistant content
    selection: currently selected text in the context, text and line numbers, null if no selection
    file: current context file path, or content of a new view, not associated with a concrete file
    '''
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
