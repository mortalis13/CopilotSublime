import os
import json
import logging

import requests


ASSISTANT_START = '[[ ASSISTANT ]]'
ASSISTANT_END = '[[ #ASSISTANT ]]'
SELECTED_CODE_PLACEHOLDER = '$SELECTION_PLACEHOLDER$'
INSERT_PLACEHOLDER = '$PLACEHOLDER$'


class Copilot:
  def __init__(self):
    self.logger = logging.getLogger('copilot')
  
  def _get_token(self) -> str:
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
    return token


  def _chat_completion(self, messages: list) -> str:
    token = self._get_token()
    
    headers = {
      'authorization': f'Bearer {token}',
      'editor-version': 'vscode/1.95.3',
    }
    
    body = {
      'messages': messages,
      'model': 'gpt-4o',
      'temperature': 0.1,
      'n': 1
    }
    
    url = 'https://api.githubcopilot.com/chat/completions'
    self.logger.info(url)
    self.logger.debug(f">> {body['model']}")
    self.logger.debug(f'>> {json.dumps(body)}')
    response = requests.post(url, headers=headers, json=body)
    
    try:
      data = response.json()
      self.logger.debug(f'<< {json.dumps(data)}')
      self.logger.debug(f"<< {data['model']}")
    except:
      self.logger.debug(f'<< Raw text response: {response.text}')
    
    if response.status_code > 300:
      error = f'{response.status_code} :: {response.text}'
      self.logger.error(error)
      raise Exception(error)
    
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
      request = f'<currentDocument> \nI have the following code in a file called `{file}`:\n```{language_id}\n{code_context}\n```\n<selection> \nThe {SELECTED_CODE_PLACEHOLDER} code is:\n```{language_id}\n{code}\n``` \n</selection>\n \n</currentDocument>\n<userPrompt> \n{text}\n \n</userPrompt>\nThe modified {SELECTED_CODE_PLACEHOLDER} code without ``` is:'
    
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
  
  
  def get_context_chat_response(self, context: str, text: str, file: str, line_start: int, line_end: int, type: str = 'python') -> str:
    file = os.path.basename(file) if file else 'untitled'
    messages = self._parse_chat_input(text.strip())
    if messages:
      messages.insert(-1, {
        'role': 'user',
        'content': f"# FILE:{file} CONTEXT\nUser's active selection:\nExcerpt from {file}, lines {line_start} to {line_end}:\n```{type}\n{context}\n```"
      })
    result = self._chat_completion(messages)
    result = f'{ASSISTANT_START}\n{result}\n{ASSISTANT_END}'
    return result
  
  
  def _parse_chat_input(self, text: str) -> str:
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

      if i == total - 1 and content.strip():
        messages.append({
          'role': 'user',
          'content': content.strip()
        })
    
    return messages
