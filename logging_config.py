import logging
import sys


def setup_logging(app=None, level=logging.INFO):
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    logger = logging.getLogger('projectcompass')
    logger.setLevel(level)
    logger.addHandler(handler)

    if app:
        app.logger.handlers = [handler]
        app.logger.setLevel(level)

    return logger


logger = setup_logging()
