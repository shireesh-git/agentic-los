"""Configuration, engine toggles, LLM provider selection and agent catalogue."""

from fastapi import APIRouter, HTTPException, Request

from src.agents.pipeline import SuperAgent
from src.core.config_manager import config
from src.core.engine_registry import registry
from src.core.llm_provider import create_llm_provider

router = APIRouter(prefix="/api", tags=["admin"])


@router.get("/config")
async def get_all_config():
    config.reload()
    return config.all_configs()


@router.get("/config/{section}")
async def get_config_section(section: str):
    config.reload()
    data = config.get(section)
    if data is None:
        raise HTTPException(404, f"Config section '{section}' not found")
    return data


@router.put("/config/{section}")
async def update_config_section(section: str, request: Request):
    config.update_config(section, await request.json())
    return {"status": "updated", "section": section}


@router.get("/engines")
async def list_engines():
    return {"engines": registry.list_engines()}


@router.put("/engines/{name}/toggle")
async def toggle_engine(name: str):
    engines = {e["name"]: e for e in registry.list_engines()}
    if name not in engines:
        raise HTTPException(404, f"Engine '{name}' not found")
    if engines[name]["enabled"]:
        registry.disable(name)
    else:
        registry.enable(name)
    return {"name": name, "enabled": registry.is_enabled(name)}


@router.get("/llm/providers")
async def llm_providers():
    lc = config.get_llm_config()
    active = lc.get("active_provider", "mock")
    return {
        "active_provider": active,
        "narrative_mode": lc.get("narrative", {}).get("mode", "template"),
        "providers": [
            {"id": k, "name": v.get("name", k), "type": v.get("type"), "active": k == active}
            for k, v in lc.get("providers", {}).items()
        ],
    }


@router.put("/llm/active")
async def set_active_llm(request: Request):
    body = await request.json()
    lc = config.get_llm_config()
    provider_id = body.get("provider")
    narrative_mode = body.get("narrative_mode")
    if provider_id:
        if provider_id not in lc.get("providers", {}):
            raise HTTPException(404, f"Provider '{provider_id}' not found")
        lc["active_provider"] = provider_id
    if narrative_mode:
        lc.setdefault("narrative", {})["mode"] = narrative_mode
    config.update_config("llm_providers", lc)
    return {"active_provider": lc["active_provider"],
            "narrative_mode": lc.get("narrative", {}).get("mode")}


@router.post("/llm/test")
async def test_llm():
    return create_llm_provider(config.get_active_llm_provider()).test_connection()


@router.get("/agents")
async def list_agents():
    return {"agents": SuperAgent().get_agent_list()}
