from cube import config, file_repository
from pathlib import Path

CUBE_DIR = Path().cwd()


@config("scheduled_refresh_contexts")
def scheduled_refresh_contexts() -> list[object]:
    return [
        {
            "securityContext": {
                "tenant_id": '0',
                "tenant_name": 'example_name',
                "data_models": [],
                "destination": {
                    "type": "postgres",
                    "hostname": "",
                    "port": None,
                    "database": "",
                    "password": "",
                    "username": "",
                },
            }
        },
    ]


@config("context_to_app_id")
def context_to_app_id(ctx: dict) -> str:
    context = ctx["securityContext"]
    if not context:
        print("[context_to_app_id] context empty security context")
        return

    tenant_id = context.get("tenant_id")
    if not tenant_id:
        print("[context_to_app_id] tenant_id not found in security context")
        return

    return f"CUBE_APP_{tenant_id}"


@config("context_to_orchestrator_id")
def context_to_orchestrator_id(ctx: dict) -> str:
    context = ctx["securityContext"]
    if not context:
        print("[context_to_orchestrator_id] context empty security context")
        return

    tenant_id = context.get("tenant_id")
    if not tenant_id:
        print("[context_to_orchestrator_id] tenant_id not found in security context")
        return

    return f"CUBE_APP_{tenant_id}"


@config("pre_aggregations_schema")
def pre_aggregations_schema(ctx: dict) -> str:
    context = ctx["securityContext"]
    if not context:
        print("[pre_aggregations_schema] context empty security context")
        return

    tenant_id = context.get("tenant_id")
    if not tenant_id:
        print("[pre_aggregations_schema] tenant_id not found in security context")
        return

    return f"pre_aggregations_{tenant_id}"


@config('repository_factory')
def repository_factory(ctx: dict) -> list[dict]:
    context = ctx["securityContext"]
    if not context:
        print("[repository_factory] context empty security context")
        return

    data_models = context.get("data_models")
    if not data_models:
        print("[repository_factory] data models found in security context")
        return

    model_respositories = []
    for data_model in data_models:
        path = CUBE_DIR / f"model/cubes/{data_model}"
        model_respositories += file_repository(path)

    from pprint import pprint
    print("model repositories: ", pprint(model_respositories))

    return model_respositories


@config("driver_factory")
def driver_factory(ctx: dict) -> None:
    context = ctx["securityContext"]
    if not context:
        print("[driver_factory] context empty security context")
        return

    destination = context.get("destination")
    if not destination:
        print("[driver_factory] destination not found in security context")
        return

    if destination["type"] == "postgres":
        driver_config = {
            "type": "postgres",
            "host": destination["hostname"],
            "port": destination["port"],
            "database": destination["database"],
            "user": destination["username"],
            "password": destination["password"],
        }
    else:
        raise NotImplementedError(
            f"[driver_factory] type {destination['type']} not implemented"
        )

    return driver_config
