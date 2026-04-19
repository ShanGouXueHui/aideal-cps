from app.services.free_llm.health_probe_service import refresh_free_llm_health

if __name__ == "__main__":
    result = refresh_free_llm_health()
    print("FREE_LLM_HEALTH_PROBE_OK")
    print("probe_count =", result.get("probe_count"))
    print("success_count =", result.get("success_count"))
    routes = result.get("routes") or {}
    for task, rows in routes.items():
        print("task =", task, "route_count =", len(rows))
        for row in rows[:5]:
            print(" ", row)
