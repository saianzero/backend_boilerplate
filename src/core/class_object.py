"""
Small class-level helpers.

Currently only ``singleton``. Used by ``main.AppCreator`` so that importing
``main`` twice (uvicorn reload, tests) never builds two FastAPI apps.
"""

import logging


def singleton(class_):
    """
    Decorator that turns a class into a process-wide singleton.

    The first call constructs the instance; every later call returns the same
    object. Constructor arguments are only honoured on the first call.

    Example
    -------
        @singleton
        class Settings:
            def __init__(self):
                self.value = 42

        assert Settings() is Settings()
    """
    logger = logging.getLogger(__name__)
    instances = {}

    def getinstance(*args, **kwargs):
        if class_ not in instances:
            logger.info(f"Creating new singleton instance for class: {class_.__name__}")
            instances[class_] = class_(*args, **kwargs)
        return instances[class_]

    return getinstance
