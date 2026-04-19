from app.services.free_llm.model_catalog_refresh_service import refresh_free_llm_model_catalog

if __name__ == "__main__":
    result = refresh_free_llm_model_catalog()
    print("FREE_LLM_CATALOG_REFRESH_OK")
    print("candidate_count =", result.get("candidate_count"))
    for item in result.get("provider_summaries", []):
        print(item)
