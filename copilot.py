import sublime_plugin
from sublime import Region

import sys
import os
import string

# cur_path = os.path.dirname(__file__)
# if cur_path not in sys.path:
#   sys.path.insert(0, cur_path)

# from .api import api


# ------
import os
import re
import requests
import uuid
import json
import threading


def _get_token() -> str:
  print(f'>> copilot: token')
  token_path = f'{os.path.dirname(os.path.realpath(__file__))}\\.copilot_token'
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


def _chat_completion(messages: list) -> str:
  token = _get_token()
  
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
  print(f'>> copilot: {url}')
  # print(body)
  response = requests.post(url, headers=headers, json=body)
  
  if response.status_code > 300:
    print(f'{response.status_code} :: {response.text}')
    return None
  
  result = None
  
  choices = response.json().get('choices')
  if choices:
    try:
      result = choices[0]['message']['content']
    except KeyError:
      pass
  
  return result

  
def get_docstring(code: str, file: str, include_code: bool = False) -> str:
  file = '/' + os.path.normpath(file).replace('\\', '/') if file else 'untitled'
  
  messages = [
    {
      'role': 'user',
      'content': f'I have the following code in the selection:\n```python\n# FILEPATH: {file}\n{code}\n```'
    },
    {
      'role': 'system',
      'content': f'When user asks you to document something, you must answer in the form of a python docstring only, without additional text and without the method signature. The response must contain all function arguments and return type. Don\'t use the ``` to delimit the code.'
    },
    {
      'role': 'user',
      'content': 'Please, generate docstring only. Do not repeat given code, only reply with docstring. docstring'
    }
  ]
  
  if include_code:
    messages = [
      {
        'role': 'user',
        'content': f'I have the following code in the selection:\n```{code}\n```'
      },
      {
        'role': 'system',
        'content': 'When user asks you to document something, you must answer in the form of a python code block. Don\'t use the ``` to delimit the code.'
      },
      {
        'role': 'user',
        'content': 'Generate the docstring for the selected function.'
      }
    ]
  
  return _chat_completion(messages)


def get_code(code: str, text: str, code_context: str, file: str, type: str = 'python') -> str:
  file = '/' + os.path.normpath(file).replace('\\', '/') if file else 'untitled'
  print(f'"{text}"')
  
  sys_rules = [
    'The user needs help to write some new code.',
    'The user includes existing code and marks with $PLACEHOLDER$ where the new code should go.',
    'Do not include the text "$PLACEHOLDER$" in your reply.',
  ]
  
  request = f'<currentDocument> \nI have the following code in a file called `{file}`:\n```{type}\n{code_context}\n```\n \n</currentDocument>\n<userPrompt> \n{text}\n \n</userPrompt>\nDo not repeat the source code from the file in the response.\nThe code that would fit at $PLACEHOLDER$ without ``` is:'
  
  if code:
    sys_rules = [
      'The user needs help to modify some code.',
      'The user includes existing code and marks with $SELECTION_PLACEHOLDER$ where the selected code should go.',
    ]
    
    request = f'<currentDocument> \nI have the following code in a file called `{file}`:\n```{type}\n{code_context}\n```\n<selection> \nThe $SELECTION_PLACEHOLDER$ code is:\n```{type}\n{code}\n``` \n</selection>\n \n</currentDocument>\n<userPrompt> \n{text}\n \n</userPrompt>\nThe modified $SELECTION_PLACEHOLDER$ code without ``` is:'
  
  sys_rules.extend([
    'Do not repeat the source code in your reply.',
    'Do not indent the response.',
    f'Respond with direct {type} code, without wrapping it with ``` blocks.',
    'If new methods are added to the existing code, generate docstrings for the methods.',
  ])
  
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
  
  result = _chat_completion(messages)
  return result


def get_chat_response(text: str) -> str:
  messages = [
    {
      'role': 'user',
      'content': text
    }
  ]
  return _chat_completion(messages)
# ------


class Parser:
  def __init__(self, view):
    self.view = view
  
  def is_definition_start(self, line: str) -> bool:
    if not line or not line.strip():
      return False

    if any(line.find(d) == 0 for d in ['def ']):
      return True
    
    if any(line.strip().find(d) == 0 for d in ['def ']):
      return True
  
  def is_definition_end(self, line: str) -> bool:
    if not line or not line.strip():
      return False
    
    if not line[0].isspace() and line[0] != '#':
      return True
    
    if any(line.strip().find(d) == 0 for d in ['def ']):
      return True
  
  def find_definition_bounds(self) -> Region:
    view = self.view
    sel_start = view.sel()[0].a
    
    def_start = def_end = 0

    p = sel_start
    while True:
      line = view.line(p)
      text = view.substr(line)
      
      if self.is_definition_start(text):
        def_start = line.a
        break
      
      p = line.a - 1
      if p < 0:
        view.show_popup('No definition found')
        return None

    p = sel_start
    while True:
      line = view.line(p)
      text = view.substr(line)
      
      if self.is_definition_end(text):
        def_end = line.a - 1
        break
      
      p = line.b + 1
      if p >= view.size():
        def_end = view.size()
        break
    
    return Region(def_start, def_end)


class Runner:
  def __init__(self, view):
    self.view = view
  
  def doc_command(self):
    def run():
      view = self.view
      sel = view.sel()[0]
      code = view.substr(sel)
      file = view.file_name()
      
      is_selected = True if code.strip() else False
      
      if is_selected:
        result = get_docstring(code, file, include_code=True)
      
      else:
        code_region = Parser(view).find_definition_bounds()
        if not code_region:
          return
        code = self.view.substr(code_region)
        
        result = get_docstring(code, file)
        result = self._reindent(result)
      
      self._insert(result)
      
    threading.Thread(target=run).start()

  def inline_code_command(self):
    view = self.view
    
    def run(text: str):
      sel = view.sel()[0]
      code = view.substr(sel)
      file = view.file_name()
      
      is_selected = True if code.strip() else False
      
      file_text = view.substr(Region(0, view.size()))
      
      if is_selected:
        code_context = file_text[:sel.a] + '$SELECTION_PLACEHOLDER$' + file_text[sel.b:]
      else:
        code_context = file_text[:sel.a] + '$PLACEHOLDER$' + file_text[sel.a:]
      
      result = get_code(code, text, code_context, file)
      if not is_selected:
        result = self._reindent(result)
      
      self._insert(result)
      
    def on_panel(text: str):
      threading.Thread(target=run, args=(text,)).start()
    
    view.window().show_input_panel('Copilot Request:', '', on_panel, None, None)

  def chat_command(self):
    def run():
      view = self.view
      
      text = view.substr(Region(0, view.size()))
      result = get_chat_response(text)
      
      pos = view.line(Region(0, 0)).b
      
      view.sel().clear()
      view.sel().add(view.size())
      
      self._insert(result, wrap=('\n\n-------------\n', '\n'))
      
    threading.Thread(target=run).start()
  
  def _reindent(self, text: str) -> str:
    view = self.view
    sel = view.sel()[0]
    indent = (sel.a - view.line(sel).a) * ' '
    text = re.sub(r'( *\n)', rf'\1{indent}', text)
    return text
  
  def _insert(self, text, wrap=None):
    view = self.view
    auto_indent = view.settings().get('auto_indent')
    view.settings().set('auto_indent', False)
    
    if wrap:
      view.run_command('insert', {'characters': wrap[0]})
    view.run_command('insert', {'characters': text})
    if wrap:
      view.run_command('insert', {'characters': wrap[1]})
    
    view.settings().set('auto_indent', auto_indent)


class CopilotInlineCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    Runner(self.view).inline_code_command()


class CopilotDocCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    Runner(self.view).doc_command()


class CopilotChatCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    self.view.set_syntax_file('Packages/Markdown/Markdown.sublime-syntax')
    Runner(self.view).chat_command()
