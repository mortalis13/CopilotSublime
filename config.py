import os
import logging
import datetime


def config_logger():
  logger = logging.getLogger('copilot')
  logger.setLevel(logging.DEBUG)

  handlers = [h.__class__ for h in logger.handlers]

  if logging.StreamHandler not in handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(asctime)s [copilot] [%(levelname)s] %(message)s')
    console_handler.setFormatter(console_formatter)
    
    logger.addHandler(console_handler)
  
  if logging.FileHandler not in handlers:
    logs_path = os.path.dirname(os.path.realpath(__file__)) + '/logs'
    if not os.path.exists(logs_path):
      os.makedirs(logs_path)
    
    log_path = f'{logs_path}/.copilot_{datetime.datetime.now().strftime("%Y%m%d")}.log'
    file_handler = logging.FileHandler(log_path, encoding='utf8')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    file_handler.setFormatter(file_formatter)
    
    logger.addHandler(file_handler)
  
  return logger


def release_logger(logger):
  for handler in logger.handlers:
    if isinstance(handler, logging.FileHandler):
      logger.removeHandler(handler)
      handler.flush()
      handler.close()
      break
