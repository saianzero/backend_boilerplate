"""
Dependency-injection container (``dependency-injector``).

Every repository, util and service is declared here once. Routers pull services
with ``Depends(Provide[Container.<name>])``; services receive their
collaborators through ``__init__``. This keeps modules decoupled and makes unit
tests trivial (pass mocks to the constructor).

Provider types
--------------
- ``providers.Singleton`` : one instance per process (DB, clients with pools).
- ``providers.Factory``   : new instance per injection (stateless repos/services).

How to register a new module
----------------------------
1. Add its repository:   ``widget_repository = providers.Factory(WidgetRepository)``
2. Add its service:      ``widget_service = providers.Factory(WidgetService,
                              widget_repository=widget_repository, aws_utils=aws_utils)``
3. Wire the router in ``main.py``: add ``"src.widgets.router"`` to ``container.wire(...)``.

Using a service in a router
---------------------------
    from dependency_injector.wiring import inject, Provide
    from src.core.container import Container

    @router.get("/")
    @inject
    async def list_widgets(
        service: WidgetService = Depends(Provide[Container.widget_service]),
    ):
        return await service.list()

Using a service outside FastAPI (tasks, scripts)
-----------------------------------------------
    container = Container()
    service = container.widget_service()
"""

import logging

from dependency_injector import containers, providers

from src.common.repositories.email_repository import EmailRepository
from src.common.repositories.file_repository import FileRepository
from src.common.services.common_service import CommonService
from src.common.services.file_service import FileService
from src.common.utils.auth_identity_client import AuthIdentityClient
from src.common.utils.aws_utils import AwsUtil
from src.common.utils.csv_utils import CSVUtil
from src.common.utils.document_utils import DocumentUtil
from src.common.utils.temp_file_utils import TempFileUtil
from src.core.config import DATABASE_NAME, DATABASE_URI
from src.core.db import Database
from src.items.repositories.item_repository import ItemRepository
from src.items.services.item_service import ItemService

logger = logging.getLogger(__name__)


class Container(containers.DeclarativeContainer):
    """Application-wide DI container."""

    # ----------------------------------------------------------------- core --
    db = providers.Singleton(Database, db_url=DATABASE_URI, db_name=DATABASE_NAME)

    # ---------------------------------------------------------------- utils --
    aws_utils = providers.Factory(AwsUtil)
    csv_util = providers.Factory(CSVUtil)
    document_util = providers.Factory(DocumentUtil)
    temp_file_util = providers.Factory(TempFileUtil)
    auth_identity_client = providers.Factory(AuthIdentityClient)

    # --------------------------------------------------------- repositories --
    email_repository = providers.Factory(EmailRepository)
    file_repository = providers.Factory(FileRepository)
    item_repository = providers.Factory(ItemRepository)

    # -------------------------------------------------------------- services --
    file_service = providers.Factory(
        FileService,
        file_repository=file_repository,
        aws_utils=aws_utils,
    )

    item_service = providers.Factory(
        ItemService,
        item_repository=item_repository,
        aws_utils=aws_utils,
    )

    common_service = providers.Factory(
        CommonService,
        item_service=item_service,
        auth_identity_client=auth_identity_client,
    )
