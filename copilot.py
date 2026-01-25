import sublime_plugin
import sublime
from sublime import Region, Edit, View

import sys
import os
import re
import time
import threading

from requests.exceptions import ConnectionError

cur_path = os.path.dirname(__file__)
if cur_path not in sys.path:
  sys.path.insert(0, cur_path)

import config

from copilot_api import Copilot, Selection, ASSISTANT_START, ASSISTANT_END
from history import HistoryManager
from utils import ViewUtilsMixin, extract_code


SETTING_CHAT_VIEW_ID = 'CONTEXT_CHAT_VIEW_ID'
SETTING_IS_COPILOT_PANEL = 'isCopilotPanel'
SETTING_PANEL_HISTORY_KEY = 'panelHistoryKey'

CHAT_VIEW_NAME = 'Copilot Chat'
CONTEXT_CHAT_VIEW_NAME = 'Copilot Context Chat'

CHAT_LOADING_MESSAGE = 'Waiting for chat response...'
CODE_LOADING_MESSAGE = 'Waiting for code generation...'

class ChatType:
  copilot = 'COPILOT_CHAT'
  context = 'CONTEXT_CHAT'


# Clear the last chat ID on plugin loading
for window in sublime.windows():
  window.settings().erase(SETTING_CHAT_VIEW_ID)


class Runner(ViewUtilsMixin):
  def __init__(self, view):
    self.view = view
    self.window = view.window()
    self.logger = config.config_logger()
  
  def __del__(self):
    config.release_logger(self.logger)
  
  def inline_code_command(self) -> None:
    view = self.view
    
    history_key = 'inline_code_history'
    HistoryManager.reset_index()
    
    def run(text: str):
      sel = view.sel()[0]
      code = view.substr(sel)
      indent = view.settings().get('tab_size')
      
      file = view.file_name()
      file_text = view.substr(Region(0, view.size()))
      
      type = self._detect_code_type()
      self.logger.debug(f'code type: {type}')
      
      selection = Selection(code, file_text, type, min(sel.a, sel.b), max(sel.a, sel.b))
      
      try:
        result = Copilot().get_code(text, selection, file, indent)
      
      except Exception as ex:
        self._handle_exception(ex)
        return
      self._hide_status()

      result = extract_code(result)
      result = self._reindent(result)
      
      self._insert(result)
      
    def _on_panel(text: str):
      self.logger.info(f'>> "{text}"')
      HistoryManager.add(text, history_key)
      
      self._show_status(CODE_LOADING_MESSAGE)
      threading.Thread(target=run, args=(text,)).start()
    
    input_view = self.window.show_input_panel('Copilot Request: ', '', _on_panel, None, None)
    input_view.settings().set(SETTING_IS_COPILOT_PANEL, True)
    self.window.settings().set(SETTING_PANEL_HISTORY_KEY, history_key)


  def _run_context_chat(self) -> None:
    history_key = 'context_chat_history'
    HistoryManager.reset_index()
    
    def run(context_view: View, chat_view: View):
      sel = context_view.sel()[0]
      code = context_view.substr(sel)
      
      file = context_view.file_name()
      file_text = context_view.substr(Region(0, context_view.size()))
      
      chat_length = chat_view.size()
      chat_text = chat_view.substr(Region(0, chat_length))
      
      type = self._detect_code_type()
      selection = Selection(code, file_text, type, min(sel.a, sel.b), max(sel.a, sel.b))
      
      try:
        result = Copilot().get_context_chat_response(chat_text, selection, file)
      
      except Exception as ex:
        self._handle_exception(ex)
        return
      self._hide_status()

      if not result: return
      
      self._insert(f'\n\n\n{result}\n\n\n', chat_view, end=True)
      response_pos = chat_length + 1
      
      chat_view.sel().clear()
      chat_view.sel().add(response_pos)
      chat_view.show(response_pos)
      
    def _run_chat(chat_view: View):
      self._split_view()
      
      # Ensure chat view is in the side panel
      if self.window.get_view_index(chat_view) != (1, 0):
        self.window.set_view_index(chat_view, 1, 0)
      
      context_view = self.view
      if self._is_focused_chat_view():
        context_view = self.window.active_view_in_group(0)
      
      self._show_status(CHAT_LOADING_MESSAGE)
      threading.Thread(target=run, args=(context_view, chat_view,)).start()
    
    def _on_panel(text: str):
      self.logger.info(f'>> "{text}"')
      HistoryManager.add(text, history_key)
      
      chat_view = self._get_chat_view()
      self._insert(text, chat_view, end=True)
      
      _run_chat(chat_view)
    
    # -----------
    open_panel = True
    
    if self._is_focused_chat_view():
      chat_view = self.view
      chat_input = self._find_chat_request(chat_view)
      if chat_input:
        open_panel = False
        _run_chat(chat_view)
    
    if open_panel:
      input_view = self.window.show_input_panel('Copilot Context Request: ', '', _on_panel, None, None)
      input_view.settings().set(SETTING_IS_COPILOT_PANEL, True)
      self.window.settings().set(SETTING_PANEL_HISTORY_KEY, history_key)


  def _run_copilot_chat(self) -> None:
    history_key = 'chat_history'
    HistoryManager.reset_index()
    
    view = self.view
    
    def run():
      chat_text = view.substr(Region(0, view.size()))
      
      try:
        result = Copilot().get_chat_response(chat_text)
      
      except Exception as ex:
        self._handle_exception(ex)
        return
      self._hide_status()
  
      self._insert(f'\n\n\n{result}\n\n\n', end=True)
      
      response_pos = len(chat_text) + 1
      view.sel().clear()
      view.sel().add(response_pos)
      view.show(response_pos)
    
    def _run_chat():
      view.assign_syntax('Packages/Markdown/Markdown.sublime-syntax')
      view.set_scratch(True)
      view.set_name(CHAT_VIEW_NAME)
      
      self._show_status(CHAT_LOADING_MESSAGE)
      threading.Thread(target=run).start()
    
    def _on_panel(text: str):
      HistoryManager.add(text, history_key)
      self._insert(text, end=True)
      _run_chat()

    chat_input = self._find_chat_request(self.view)
    if not chat_input:
      input_view = self.window.show_input_panel('Copilot Chat Request: ', '', _on_panel, None, None)
      input_view.settings().set(SETTING_IS_COPILOT_PANEL, True)
      self.window.settings().set(SETTING_PANEL_HISTORY_KEY, history_key)
    
    else:
      _run_chat()


  def chat_command(self) -> None:
    chat_type = self._chat_type()
    if chat_type == ChatType.copilot:
      self._run_copilot_chat()
      
    if chat_type == ChatType.context:
      self._run_context_chat()


  def _find_chat_request(self, chat_view: View) -> str:
    chat_lines = []
    lines = chat_view.lines(Region(0, chat_view.size()))
    
    for line in reversed(lines):
      text = chat_view.substr(line)
      if text == ASSISTANT_END:
        break
      chat_lines.append(text)
    
    chat_input = '\n'.join(chat_lines[::-1]).strip()
    return chat_input
  
  def _handle_exception(self, exception: Exception) -> None:
    self._hide_status()
    if isinstance(exception, ConnectionError):
      self.logger.exception('Connection error:')
      self._show_error('Connection error, try again later')
    
    else:
      self.logger.exception('Generic error:')
      self._show_error('Error getting Copilot response, check the logs')
  
  def _create_chat_view(self) -> View:
    chat_view = self.window.new_file(syntax='Packages/Markdown/Markdown.sublime-syntax')
    chat_view.set_scratch(True)
    chat_view.set_name(CONTEXT_CHAT_VIEW_NAME)
    self.window.settings().set(SETTING_CHAT_VIEW_ID, chat_view.id())
    return chat_view
  
  def _get_chat_view(self) -> View:
    chat_view_id = self.window.settings().get(SETTING_CHAT_VIEW_ID)
    chat_view = next(filter(lambda _view: _view.id() == chat_view_id, self.window.views()), None)
    return chat_view or self._create_chat_view()
  
  def _is_focused_chat_view(self) -> bool:
    chat_view_id = self.window.settings().get(SETTING_CHAT_VIEW_ID)
    return self.view.id() == chat_view_id
  
  def _split_view(self) -> None:
    if self.window.num_groups() == 1:
      self.window.set_layout({'cells': [[0, 0, 1, 1], [1, 0, 2, 1]], 'cols': [0.0, 0.5, 1.0], 'rows': [0.0, 1.0]})
  
  def _chat_type(self):
    view = self.view
    
    if view.name() == CONTEXT_CHAT_VIEW_NAME:
      return ChatType.context
      
    if view.name() == CHAT_VIEW_NAME:
      return ChatType.copilot
    
    if view.file_name():
      return ChatType.context
  
    text = view.substr(Region(0, view.size()))
    if not text.strip():
      return ChatType.copilot
    
    if self._detect_code_type():
      return ChatType.context
    
    sel = view.sel()[0]
    if sel.a != sel.b:
      return ChatType.context
    
    return ChatType.copilot
  

class CopilotInlineCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    Runner(self.view).inline_code_command()
    

class CopilotChatCommand(sublime_plugin.TextCommand):
  def run(self, edit):
    Runner(self.view).chat_command()
  

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
    if chat_view_id and self.view.id() == chat_view_id:
      # Restore default layout
      window.set_layout({'cells': [[0, 0, 1, 1]], 'cols': [0.0, 1.0], 'rows': [0.0, 1.0]})
      window.settings().erase(SETTING_CHAT_VIEW_ID)
  

class GetCopilotHistoryEntryCommand(sublime_plugin.TextCommand):
  # Command for input panel view
  def run(self, edit: Edit, up: bool):
    key = self.view.window().settings().get(SETTING_PANEL_HISTORY_KEY)
    
    if up:
      entry = HistoryManager.prev(key)
    else:
      entry = HistoryManager.next(key)
    
    if entry is None:
      entry = self.view.substr(Region(0, self.view.size()))
    
    self.view.erase(edit, Region(0, self.view.size()))
    self.view.insert(edit, 0, entry)
