from cube import config


@config("scheduled_refresh_contexts")
def scheduled_refresh_contexts() -> list[object]:
    return [
        {
            "securityContext": {
                "tenant_id": '0',
                "destination_config": {
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


# from cube import file_repository
# @config('repository_factory')
# def repository_factory(ctx: dict) -> list[dict]:
#     return file_repository(f"model/{ctx['securityContext']['tenant_id']}")


@config("driver_factory")
def driver_factory(ctx: dict) -> None:
    print(ctx)
    context = ctx["securityContext"]
    if not context:
        print("[driver_factory] context empty security context")
        return

    destination_config = context.get("destination_config")
    if not destination_config:
        print("[driver_factory] destination_config not found in security context")
        return

    if destination_config["type"] == "postgres":
        driver_config = {
            "type": "postgres",
            "host": destination_config["hostname"],
            "port": destination_config["port"],
            "database": destination_config["database"],
            "user": destination_config["username"],
            "password": destination_config["password"],
        }
    else:
        raise NotImplementedError(
            f"[driver_factory] type {destination_config['type']} not implemented"
        )

    return driver_config
