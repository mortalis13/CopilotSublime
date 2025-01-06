
class HistoryManager:
  storage = {}
  index = None

  @classmethod
  def add(cls, entry: str, key: str) -> None:
    if cls.storage.get(key) and cls.storage[key][-1] == entry:
      return
    
    if key not in cls.storage:
      cls.storage[key] = []
    
    cls.storage[key].append(entry)
  
  @classmethod
  def prev(cls, key: str) -> str:
    if not key:
      return None
    
    if not cls.storage or not cls.storage.get(key):
      return None
    
    if cls.index is None:
      cls.index = cls._total(key) - 1
 
    elif cls.index != 0:
      cls.index -= 1
      
    return cls.storage[key][cls.index]

  @classmethod
  def next(cls, key: str) -> str:
    if not key:
      return None
      
    if cls.index is None or not cls.storage.get(key):
      return None
    
    if cls.index == cls._total(key) - 1:
      cls.index = None
      return ''
    
    cls.index += 1
    return cls.storage[key][cls.index]

  @classmethod
  def reset_index(cls) -> None:
    cls.index = None
  
  @classmethod
  def _total(cls, key: str) -> int:
    return len(cls.storage.get(key, []))
