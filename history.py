
class HistoryManager:
  storage = []
  index = None

  @classmethod
  def add(cls, entry: str) -> None:
    if not cls.storage or entry != cls.storage[-1]:
      cls.storage.append(entry)
  
  @classmethod
  def prev(cls) -> str:
    if not cls.storage:
      return None
    
    if cls.index is None:
      cls.index = cls._total() - 1
 
    elif cls.index != 0:
      cls.index -= 1
      
    return cls.storage[cls.index]

  @classmethod
  def next(cls) -> str:
    if cls.index is None:
      return None
    
    if cls.index == cls._total() - 1:
      cls.index = None
      return ''
    
    cls.index += 1
    return cls.storage[cls.index]

  @classmethod
  def reset_index(cls) -> None:
    cls.index = None
  
  @classmethod
  def _total(cls) -> int:
    return len(cls.storage)
