import sublime_plugin
import sublime
from sublime import Region, Edit, View

import sys
import os
import re
import time
import threading

from textwrap import indent, dedent

cur_path = os.path.dirname(__file__)
if cur_path not in sys.path:
  sys.path.insert(0, cur_path)

import config

from copilot_api import Copilot
from code_parser import Parser
from history import HistoryManager


SETTING_CHAT_VIEW_ID = 'CONTEXT_CHAT_VIEW_ID'

LOADER_STYLE = '''
<style>
  html {
    background-color: #303030;
    border: 1px solid #bbb;
    border-radius: 1px;
    margin: 0;
    padding: 0;
  }
  body {
    margin: 0px 8px 9px;
    padding: 0;
    color: #fff;
  }
</style>
'''


class Runner:
  def __init__(self, view):
    self.view = view
    self.window = view.window()
    self.logger = config.config_logger()
    self.loading = False
    self.loader_text = ''
    self.error = ''
  
  def __del__(self):
    config.release_logger(self.logger)
  
  def inline_code_command(self):
    view = self.view
    
    history_key = 'inline_code_command'
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
      self.logger.info(f'>> "{text}"')
      HistoryManager.add(text, history_key)
      threading.Thread(target=self._loader).start()
      threading.Thread(target=run, args=(text,)).start()
    
    input_view = self.window.show_input_panel('Copilot Request: ', '', on_panel, None, None)
    input_view.settings().set('isCopilotPanel', True)
    self.window.settings().set('panelHistoryKey', history_key)


  def context_chat_command(self):
    view = self.view
    
    history_key = 'context_chat_command'
    HistoryManager.reset_index()
    
    def run(text: str):
      sel = view.sel()[0]
      code = view.substr(sel)
      file = view.file_name()
      
      line_start = view.rowcol(min(sel.a, sel.b))[0] + 1
      line_end = view.rowcol(max(sel.a, sel.b))[0] + 1
      
      is_selected = True if code.strip() else False
      if not is_selected:
        code = view.substr(Region(0, view.size()))
        line_start = 1
        line_end = view.rowcol(view.size())[0] + 1
      
      chat_view_id = self.window.settings().get(SETTING_CHAT_VIEW_ID)
      chat_view = next(filter(lambda _view: _view.id() == chat_view_id, self.window.views()), None)
        
      chat_text = text
      if chat_view:
        chat_text = chat_view.substr(Region(0, chat_view.size())) + text
      else:
        self.window.settings().erase(SETTING_CHAT_VIEW_ID)
      
      try:
        result = Copilot().get_context_chat_response(code, chat_text, file, line_start, line_end)
      
      except Exception as ex:
        self.logger.exception(ex)
        self.error = 'Error getting chat response'
        return

      self._split_view()
      
      if not chat_view:
        chat_view = self._create_chat_view()
      
      # Ensure chat view is in the side panel
      if self.window.get_view_index(chat_view) != (1, 0):
        self.window.set_view_index(chat_view, 1, 0)
      
      self.window.focus_view(view)
      
      self.loading = False
      self._insert(f'{text}\n\n\n{result}\n\n\n', chat_view, end=True)
      
      response_pos = len(chat_text) + 1
      chat_view.sel().clear()
      chat_view.sel().add(response_pos)
      chat_view.show(response_pos)
      
    def on_panel(text: str):
      self.logger.info(f'>> "{text}"')
      HistoryManager.add(text, history_key)
      threading.Thread(target=self._loader).start()
      threading.Thread(target=run, args=(text,)).start()
    
    input_view = self.window.show_input_panel('Copilot Context Request: ', '', on_panel, None, None)
    input_view.settings().set('isCopilotPanel', True)
    self.window.settings().set('panelHistoryKey', history_key)


  def chat_command(self):
    view = self.view
    view.assign_syntax('Packages/Markdown/Markdown.sublime-syntax')
    
    def run():
      chat_text = view.substr(Region(0, view.size()))
      try:
        result = Copilot().get_chat_response(chat_text)
      
      except Exception as ex:
        self.logger.exception(ex)
        self.error = 'Error getting chat response'
        return
      
      self.loading = False
      self._insert(f'\n\n\n{result}\n\n\n', end=True)
      
      response_pos = len(chat_text) + 1
      view.sel().clear()
      view.sel().add(response_pos)
      view.show(response_pos)
    
    threading.Thread(target=self._loader).start()
    threading.Thread(target=run).start()

  
  def _create_chat_view(self):
    chat_view = self.window.new_file(syntax='Packages/Markdown/Markdown.sublime-syntax')
    chat_view.set_scratch(True)
    chat_view.set_name('Copilot Chat')
    self.window.settings().set(SETTING_CHAT_VIEW_ID, chat_view.id())
    
    return chat_view
  
  def _split_view(self):
    if self.window.num_groups() == 1:
      self.window.set_layout({'cells': [[0, 0, 1, 1], [1, 0, 2, 1]], 'cols': [0.0, 0.5, 1.0], 'rows': [0.0, 1.0]})
  
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
  
  def _insert(self, text: str, view: View = None, end: bool = False):
    view = view or self.view
    
    if end:
      view.sel().clear()
      view.sel().add(view.size())
    
    auto_indent = view.settings().get('auto_indent')
    view.settings().set('auto_indent', False)
    view.run_command('insert', {'characters': text})
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
      text = LOADER_STYLE + text
      
      if not self.view.is_popup_visible():
        self.view.show_popup(text)
      else:
        self.view.update_popup(text)
      
      time.sleep(0.2)

    self.view.hide_popup()


class CopilotInlineCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    Runner(self.view).inline_code_command()
    

class CopilotChatCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    Runner(self.view).chat_command()
  

class CopilotContextChatCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    Runner(self.view).context_chat_command()
  

class ViewListener(sublime_plugin.ViewEventListener):
  def on_pre_close(self):
    if self.view.window() is None:
      return
    self.view.settings().set('window_id', self.view.window().id())
    
  def on_close(self):
    window_id = self.view.settings().get('window_id')
    if not window_id:
      return
    
    window = next(filter(lambda _window: _window.id() == window_id, sublime.windows()), None)
    if not window:
      return
    
    chat_view_id = window.settings().get(SETTING_CHAT_VIEW_ID)
    if chat_view_id and chat_view_id == self.view.id():
      # Restore default layout
      window.set_layout({'cells': [[0, 0, 1, 1]], 'cols': [0.0, 1.0], 'rows': [0.0, 1.0]})
  

class GetCopilotHistoryEntryCommand(sublime_plugin.TextCommand):
  # Command for input panel view
  def run(self, edit: Edit, up: bool):
    key = self.view.window().settings().get('panelHistoryKey')
    
    if up:
      entry = HistoryManager.prev(key)
    else:
      entry = HistoryManager.next(key)
    
    if entry is None:
      entry = self.view.substr(Region(0, self.view.size()))
    
    self.view.erase(edit, Region(0, self.view.size()))
    self.view.insert(edit, 0, entry)
