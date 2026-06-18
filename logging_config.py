import logging
import os
import sys


def setup_logging(app=None, level=logging.INFO):
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    log_path = os.path.join(os.path.dirname(__file__), 'static', 'logs.log')
    file_handler = logging.FileHandler(log_path, mode='w')
    file_handler.setFormatter(formatter)

    logger = logging.getLogger('projectcompass')
    logger.setLevel(level)
    logger.addHandler(handler)
    logger.addHandler(file_handler)

    if app:
        app.logger.handlers = [handler, file_handler]
        app.logger.setLevel(level)

    return logger


logger = setup_logging()
