import sublime
from sublime import Region, Edit, View, Window, Settings

import re
import textwrap

ERROR_POPUP_STYLE = '''
<style>
  html {
    background-color: #333;
    border: 1px solid #bb4444;
    margin: 0;
    padding: 0;
  }
  body {
    margin: 5px 10px 6px;
    padding: 0;
    color: #eee;
  }
</style>
'''

class ViewUtilsMixin:
  view: View
  window: Window
  
  def _insert(self, text: str, view: View = None, end: bool = False) -> None:
    view = view or self.view
    
    if end:
      view.sel().clear()
      view.sel().add(view.size())
    
    auto_indent = view.settings().get('auto_indent')
    view.settings().set('auto_indent', False)
    view.run_command('insert', {'characters': text})
    view.settings().set('auto_indent', auto_indent)
  
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
      text = textwrap.indent(text, fix_indent * ' ')
    
    elif fix_indent < 0:
      text = textwrap.dedent(text)
      text = textwrap.indent(text, abs(fix_indent) * ' ')
    
    # Remove first line indent if selection is empty or its start is not on the line start
    if start != view.line(start).a:
      text = text.lstrip()
    
    return text
  
  def _split_view(self) -> None:
    if self.window.num_groups() == 1:
      self.window.set_layout({'cells': [[0, 0, 1, 1], [1, 0, 2, 1]], 'cols': [0.0, 0.5, 1.0], 'rows': [0.0, 1.0]})
  
  def _show_error(self, text: str) -> None:
    self._show_popup(ERROR_POPUP_STYLE + text)

  def _show_popup(self, text: str) -> None:
    self.view.show_popup(text, max_width=1000)

  def _show_status(self, text: str, view: View = None) -> None:
    view = view or self.view
    view.set_status('copilot_status', text)

  def _hide_status(self, view: View = None) -> None:
    view = view or self.view
    view.erase_status('copilot_status')

  def _detect_code_type(self) -> str:
    view_scope = self.view.syntax().scope.lower()
    
    scopes = {
      'text.plain': None,
      'text.html.markdown': None,
      
      'source.actionscript': 'as',
      'source.applescript': 'applescript',
      'source.asp': 'asp',
      'source.c++': 'cpp',
      'source.clojure': 'clojure',
      'source.cmake': 'cmake',
      'source.css': 'css',
      'source.diff': 'diff',
      'source.dosbatch': 'bat',
      'source.erlang': 'erlang',
      'source.groovy': 'groovy',
      'source.haskell': 'haskell',
      'source.java': 'java',
      'source.json': 'json',
      'source.jsx': 'jsx',
      'source.kotlin': 'kotlin',
      'source.lisp': 'lisp',
      'source.lua': 'lua',
      'source.makefile': 'make',
      'source.matlab': 'matlab',
      'source.objc++': 'objectivecpp',
      'source.ocaml': 'ocaml',
      'source.pascal': 'pascal',
      'source.perl': 'perl',
      'source.python': 'python',
      'source.ruby': 'ruby',
      'source.rust': 'rust',
      'source.scala': 'scala',
      'source.shell.bash': 'bash',
      'source.sql': 'sql',
      'source.ts': 'typescript',
      'source.vbs': 'vbs',
      'source.yaml': 'yaml',
      
      'text.haml': 'haml',
      'text.html.basic': 'html',
      'text.html.jsp': 'jsp',
      'text.html.vue': 'vue',

      'source.d': 'd',
      'source.cs': 'csharp',
      'source.c': 'c',
      'source.go': 'go',
      'source.js': 'javascript',
      'source.objc': 'objectivec',
      'source.r': 'r',
      'text.xml': 'xml',
      'text.html': 'html',
      'embedding.php': 'php',
      'source.php': 'php',
    }
    
    for scope, language in scopes.items():
      if view_scope == scope or view_scope.startswith(scope + '.'):
        return language
    
    return None
  
  def set_syntax_by_language(self, language: str) -> None:
    language = language.strip()
    syntax = next((item for item in sublime.list_syntaxes() if item.name.lower() == language.lower()), None)
    if not syntax: return
    self.view.assign_syntax(syntax.path)


def reset_view_settings(settings: Settings) -> None:
  for key in settings.to_dict():
    settings.erase(key)


def extract_code(text: str) -> str:
  """
  Get code from Markdown blocks
  Works with ```language, with ``` only
  Merges multiple blocks
  Returns the first language if present
  """
  pattern = r'```([^\n]*)\n(.*?)\n```'
  matches = re.findall(pattern, text.strip(), re.DOTALL)
  if not matches:
    return text.strip(), None
  language = matches[0][0].strip()
  code = '\n'.join([code.strip() for _, code in matches])
  return code, language


def get_line_number(text: str, position: int) -> int:
  return text.count('\n', 0, position) + 1
