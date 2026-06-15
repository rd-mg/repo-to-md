import logging

# Configure structured logging
logger = logging.getLogger(__name__)

class BaseProcessor:
    def __init__(self, log_callback=None, progress_callback=None):
        self.log_callback = log_callback or logger.info
        self.progress_callback = progress_callback or (lambda x: None)

    def log(self, message):
        self.log_callback(message)
