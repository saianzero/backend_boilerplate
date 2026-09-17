# Adding a feature module

Example: a `widgets` module. Mirror `src/items` exactly.

## 1. Scaffold

```
src/widgets/
  __init__.py
  enums/widget_status.py
  models/widget.py
  repositories/widget_repository.py
  schemas/requests/{create_widget,update_widget,list_widgets}.py
  schemas/responses/widget_response.py
  services/widget_service.py
  router.py
  tasks.py                 # only if it has background work
```

## 2. Model (`models/widget.py`)

```python
from src.common.models.base import BaseDocument

class Widget(BaseDocument):
    name: str
    org_id: str = ""
    uploaded_by: str = ""

    class Settings:
        name = "widgets"
        indexes = ["org_id"]
```

Nothing else to register: `Database.connect()` imports every `src/*/models/*.py`.

## 3. Repository

```python
from src.common.repositories.base_repository import BaseRepository

class WidgetRepository(BaseRepository[Widget]):
    model = Widget
    # add model-specific queries only
```

## 4. Schemas

- Create/update bodies: plain pydantic.
- List query: subclass `ListRequestBase`, override `get_filters()` and `sort_map`.
- Responses: `PaginatedResponse.build(...)` for lists.

## 5. Service

```python
class WidgetService:
    def __init__(self, widget_repository: WidgetRepository, aws_utils: AwsUtil):
        ...
    async def _get_owned(self, widget_id, user) -> Widget: ...   # 400/404/403
    async def create/get/list/update/delete/bulk_delete/search(...)
```

Rules: take `CurrentUser`, scope by `user.org_id`, raise `HTTPException` here.

## 6. Router

Copy `src/items/router.py`, swap names. Keep handlers one line long.

## 7. Register

`src/core/container.py`:
```python
widget_repository = providers.Factory(WidgetRepository)
widget_service = providers.Factory(WidgetService, widget_repository=widget_repository, aws_utils=aws_utils)
```

`main.py`:
```python
from src.widgets.router import router as widgets_router
self.app.include_router(widgets_router)
container.wire(modules=[..., "src.widgets.router"])
```

`src/internal/router.py`: add `(Widget, "uploaded_by")` to `OWNED_MODELS`.

## 8. Background tasks (optional)

1. `src/taskiq_brokers.py`: add `"widgets"` to `SUBJECT_IDS`, `widgets_broker = create_broker("widgets")`, append to `ALL_BROKERS`.
2. `src/widgets/tasks.py`:
   ```python
   @widgets_broker.task(task_name="process_widget")
   async def process_widget_task(widget_id: str, job_id: str | None = None):
       async with JobTracker.run(job_id, widget_id):
           await _process_widget(widget_id)
   ```
3. Dispatch from the service: `await process_widget_task.kiq(widget_id, job_id)`.
4. Worker: `taskiq worker src.taskiq_brokers:widgets_broker src.widgets.tasks`
   (add a service to `docker-compose.yml`, a script under `scripts/`).

## 9. Tests

Copy `tests/test_repositories/test_item_repository.py`,
`tests/test_services/test_item_service.py`, `tests/test_routers/test_item_router.py`.
Add the model to `DOCUMENT_MODELS` in `tests/conftest.py`.

## 10. Global search (optional)

Inject the service into `CommonService` and merge its `search()` result in `global_search`.
