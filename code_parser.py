from sublime import Region, View


class Parser:
  def __init__(self, view: View):
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
