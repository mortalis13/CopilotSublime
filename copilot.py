import sublime_plugin
from sublime import Region, Edit

import sys
import os
import logging
import time
from textwrap import indent, dedent

cur_path = os.path.dirname(__file__)
if cur_path not in sys.path:
  sys.path.insert(0, cur_path)

# from api import api
from code_parser import Parser
from history import HistoryManager
import config


# ------
import os
import re
import requests
import json
import threading


class Copilot:
  def __init__(self):
    self.logger = logging.getLogger('copilot')
  
  def _get_token(self) -> str:
    self.logger.debug(f'get token')
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
    self.logger.debug(f'>> {body}')
    response = requests.post(url, headers=headers, json=body)
    
    try:
      self.logger.debug(f'<< {response.json()}')
      self.logger.debug(f"<< {response.json()['model']}")
    except:
      self.logger.debug(f'<< Raw text response: {response.text}')
    
    if response.status_code > 300:
      error = f'{response.status_code} :: {response.text}'
      self.logger.error(error)
      raise Exception(error)
    
    result = None
    
    choices = response.json().get('choices')
    if choices:
      try:
        result = choices[0]['message']['content']
      except KeyError:
        pass
    
    self.logger.debug(f"'''''''''''''\n{result}\n'''''''''''''")
    return result

    
  def get_docstring(self, code: str, file: str, include_code: bool = False) -> str:
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
    
    return self._chat_completion(messages)


  def get_code(self, code: str, text: str, code_context: str, file: str, type: str = 'python') -> str:
    self.logger.info(f'>> "{text}"')
    file = '/' + os.path.normpath(file).replace('\\', '/') if file else 'untitled'
    
    # Rules for selected code
    if code:
      sys_rules = [
        'The user needs help to modify some code.',
        'The user includes existing code and marks with $SELECTION_PLACEHOLDER$ where the selected code should go.',
      ]
      request = f'<currentDocument> \nI have the following code in a file called `{file}`:\n```{type}\n{code_context}\n```\n<selection> \nThe $SELECTION_PLACEHOLDER$ code is:\n```{type}\n{code}\n``` \n</selection>\n \n</currentDocument>\n<userPrompt> \n{text}\n \n</userPrompt>\nThe modified $SELECTION_PLACEHOLDER$ code without ``` is:'
    
    else:
      sys_rules = [
        'The user needs help to write some new code.',
        'The user includes existing code and marks with $PLACEHOLDER$ where the new code should go.',
        'Do not include the text "$PLACEHOLDER$" in your reply.',
      ]
      request = f'<currentDocument> \nI have the following code in a file called `{file}`:\n```{type}\n{code_context}\n```\n \n</currentDocument>\n<userPrompt> \n{text}\n \n</userPrompt>\nDo not repeat the source code from the file in the response.\nThe code that would fit at $PLACEHOLDER$ without ``` is:'

    # Common rules
    sys_rules.extend([
      'Generate docstrings for added methods.',
      'Do not repeat the provided code in your reply.',
      f'Respond with direct {type} code, without wrapping it with ``` blocks.',
    ])
    
    if type == 'python':
      sys_rules.extend([
        'If docstring is requested, do not repeat given code, only reply with docstring wrapped in """.',
        'Always add type hints to the methods signatures using Python 3.10 built-in types rather that the typing library.',
        'Use single quotes for strings.'
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
    
    return self._chat_completion(messages)


  def get_chat_response(self, text: str) -> str:
    messages = [
      {
        'role': 'user',
        'content': text
      }
    ]
    return self._chat_completion(messages)
# ------


class Runner:
  def __init__(self, view):
    self.view = view
    self.logger = config.config_logger()
    self.loading = False
    self.loader_text = ''
    self.error = ''
  
  def __del__(self):
    config.release_logger(self.logger)
  
  def doc_command(self):
    def run():
      view = self.view
      sel = view.sel()[0]
      code = view.substr(sel)
      file = view.file_name()
      
      is_selected = True if code.strip() else False
      
      if is_selected:
        result = Copilot().get_docstring(code, file, include_code=True)
      
      else:
        code_region = Parser(view).find_definition_bounds()
        if not code_region:
          return
        code = self.view.substr(code_region)
        
        result = Copilot().get_docstring(code, file)
        result = self._reindent(result)
      
      self.loading = False
      self._insert(result)
      
    threading.Thread(target=self._loader).start()
    threading.Thread(target=run).start()

  def inline_code_command(self):
    view = self.view
    
    HistoryManager.reset_index()
    
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
      
      try:
        result = Copilot().get_code(code, text, code_context, file)
      
      except Exception as ex:
        self.logger.exception(ex)
        self.error = 'Error getting code completion'
        return

      result = self._reindent(result)
      
      self.loading = False
      self._insert(result)
      
    def on_panel(text: str):
      HistoryManager.add(text)
      threading.Thread(target=self._loader).start()
      threading.Thread(target=run, args=(text,)).start()
    
    input_view = view.window().show_input_panel('Copilot Request: ', '', on_panel, None, None)
    input_view.settings().set('isCopilotPanel', True)

  def chat_command(self):
    def run():
      view = self.view
      view.set_syntax_file('Packages/Markdown/Markdown.sublime-syntax')
      
      text = view.substr(Region(0, view.size()))
      try:
        result = Copilot().get_chat_response(text)
      
      except Exception as ex:
        self.logger.exception(ex)
        self.error = 'Error getting chat response'
        return
      
      pos = view.line(Region(0, 0)).b
      
      view.sel().clear()
      view.sel().add(view.size())
      
      self.loading = False
      self._insert(result, wrap=('\n\n-------------\n', '\n'))
    
    threading.Thread(target=self._loader).start()
    threading.Thread(target=run).start()
  
  def _reindent(self, text: str) -> str:
    view = self.view
    sel = view.sel()[0]
    
    start = min(sel.a, sel.b)
    
    # Detect selection indentation
    sel_indent = 0
    
    line = view.substr(view.line(start))
    if line.startswith(' '):
      match = re.match(r' *', line)
      sel_indent = len(match.group(0))
    
    # Detect text indentation
    text_indent = 0
    
    lines = text.split('\n')
    for line in lines:
      if not line.lstrip(): continue
      text_indent = len(line) - len(line.lstrip())
      break
    
    # Fix indentation
    fix_indent = sel_indent - text_indent
    if fix_indent > 0:
      text = indent(text, fix_indent * ' ')
    
    elif fix_indent < 0:
      text = dedent(text)
      text = indent(text, abs(fix_indent) * ' ')
    
    # Remove first line indent if selection is empty or its start is not on the line start
    if start != view.line(start).a:
      text = text.lstrip()
    
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
  
  def _loader(self):
    self.loading = True
  
    while self.loading:
      if self.error:
        self.view.update_popup(self.error)
        return
        
      self.loader_text += '.'
      if len(self.loader_text) > 3:
        self.loader_text = ''
      
      text = self.loader_text
      if len(text) < 3:
        text += (3 - len(text)) * ' '
      
      text = text.replace(' ', '&nbsp;')
      
      if not self.view.is_popup_visible():
        self.view.show_popup(text)
      else:
        self.view.update_popup(text)
      
      time.sleep(0.2)

    self.view.hide_popup()


class CopilotInlineCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    Runner(self.view).inline_code_command()


class CopilotDocCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    Runner(self.view).doc_command()


class CopilotChatCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    Runner(self.view).chat_command()


class GetCopilotHistoryEntryCommand(sublime_plugin.TextCommand):
  # Command for input panel view
  def run(self, edit: Edit, up: bool):
    if up:
      entry = HistoryManager.prev()
    else:
      entry = HistoryManager.next()
    
    if entry is None:
      entry = self.view.substr(Region(0, self.view.size()))
    
    self.view.erase(edit, Region(0, self.view.size()))
    self.view.insert(edit, 0, entry)
