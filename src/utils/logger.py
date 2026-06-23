import logging
import logging.handlers
import os

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

def get_logger(name: str, log_file: str = "agent.log", level=logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        logger.setLevel(level)
        
        # Rotating file handler
        file_path = os.path.join(LOG_DIR, log_file)
        file_handler = logging.handlers.RotatingFileHandler(
            file_path, maxBytes=5*1024*1024, backupCount=3, encoding="utf-8"
        )
        
        # Console handler
        console_handler = logging.StreamHandler()
        
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | [%(name)s] | %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
    return logger
