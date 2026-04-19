from app.services.free_llm.router_service import complete_free_llm_json

if __name__ == "__main__":
    result = complete_free_llm_json(
        task="catalog_whitelist_review",
        system_prompt="只输出 JSON，不要解释。",
        user_prompt='请输出 {"ok": true, "scene": "free_llm_smoke"}',
    )
    print("FREE_LLM_ROUTER_SMOKE_STATUS =", result.get("status"))
    print("provider =", result.get("provider"))
    print("model =", result.get("model"))
    print("json =", result.get("json"))
    if result.get("status") != "success":
        print("errors =", result.get("errors"))
