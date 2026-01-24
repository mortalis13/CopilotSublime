import os
import json
import time
import logging
from dataclasses import dataclass

import requests

from templates import SYSTEM_RULES, CONTEXT_SELECTION, CONTEXT_FILE, USER_REQUEST

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
  
  def _rules_by_type(self, type: str) -> list:
    rules = []

    if type == 'python':
      rules = [
        'Generate docstrings for added methods.',
        'If only docstring is requested, do not repeat given code, only reply with docstring wrapped in """.',
        'Always add type hints to the methods signatures using Python 3.10 built-in types rather that the typing library.',
        'Use single quotes for strings.',
      ]
    
    if type == 'java':
      rules = [
        'Add proper javadoc comments for methods signatures.',
        'In the multi-block structures, like "if-else", "try-catch" etc., the start of each block should be on its own line, as in ```if (condition) {\n}\nelse {\n}\nelse{\n}\n```.'
      ]

    return rules

  
  def get_code(self, code: str, text: str, code_context: str, file: str, type: str = None, indent: int = None) -> str:
    file = '/' + os.path.normpath(file).replace('\\', '/') if file else 'untitled'
    language_id = type if type else ''
    
    # Rules for selected code
    if code:
      sys_rules = [
        'The user needs help to modify some code.',
        f'The user includes existing code and marks with {SELECTED_CODE_PLACEHOLDER} where the selected code should go.',
        'Do not repeat the provided code in your reply.',
      ]
      request = f'<currentDocument> \nI have the following code in a file called `{file}`:\n```{language_id}\n{code_context}\n```\n<selection> \nThe {SELECTED_CODE_PLACEHOLDER} code is:\n```{language_id}\n{code}\n``` \n</selection>\n \n</currentDocument>\n<userPrompt> \n{text}\n \n</userPrompt>\nThe modified {SELECTED_CODE_PLACEHOLDER} code, in a single block, without ``` is:'
    
    # Rules for the cursor position in a code file, without selection
    elif code_context:
      sys_rules = [
        'The user needs help to write some new code.',
        f'The user includes existing code and marks with {INSERT_PLACEHOLDER} where the new code should go.',
        f'Do not include the text "{INSERT_PLACEHOLDER}" in your reply.',
        'Do not repeat the provided code in your reply.',
      ]
      request = f'<currentDocument> \nI have the following code in a file called `{file}`:\n```{language_id}\n{code_context}\n```\n \n</currentDocument>\n<userPrompt> \n{text}\n \n</userPrompt>\nDo not repeat the source code from the file in the response.\nThe code that would fit at {INSERT_PLACEHOLDER} without ``` is:'
    
    # Rules for empty file
    else:
      type = type or 'python'
      sys_rules = [
        'The user needs help to write some new code.',
        f'Respond only with a code block in {type}.',
      ]
      request = f'The code that would satisfy the following request: "{text}", without ``` is:'
    
    if indent:
      sys_rules.extend([
        f'Use indentation equal to {indent} spaces.'
      ])
    sys_rules.extend(self._rules_by_type(type))

    messages = [
      {
        'role': 'system',
        'content': '\n'.join(sys_rules)
      },
      {
        'role': 'user',
        'content': request
      },
    ]
    
    return self._chat_completion(messages)


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
    messages = self._parse_chat_input(text.strip())
    result = self._chat_completion(messages)
    result = f'{ASSISTANT_START}\n{result}\n{ASSISTANT_END}'
    return result
  
  
  # -- Context chat
  
  def _get_system_rules(self) -> dict:
    return {
      'role': 'system',
      'content': SYSTEM_RULES.strip()
    }
  
  def _get_context_rule(self, selection: Selection, file: str) -> dict:
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

    return {
      'role': 'user',
      'content': content.strip()
    }
  
  def _expand_user_input(self, messages) -> None:
    content = messages[-1]['content']
    messages[-1]['content'] = USER_REQUEST.format(content=content).strip()
    
  def get_context_chat_response(self, text: str, selection: Selection, file: str) -> str:
    '''
    text: the entire current chat text, initial user request, or full history with user/assistant content
    selection: currently selected text in the context, text and line numbers, null if no selection
    file: current context file path, or content of a new tab, not associated with a concrete file
    '''
    messages = []
    messages.append(self._get_system_rules())
    messages.extend(self._parse_chat_input(text.strip()))
    
    # Add context with full file text, selection, before the current user query
    messages.insert(-1, self._get_context_rule(selection, file))
    self._expand_user_input(messages)
    
    result = self._chat_completion(messages)
    result = f'{ASSISTANT_START}\n{result}\n{ASSISTANT_END}'
    return result
  
  
  def _parse_chat_input(self, text: str) -> list:
    messages = []
    content = ''
    
    lines = text.split('\n')
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
