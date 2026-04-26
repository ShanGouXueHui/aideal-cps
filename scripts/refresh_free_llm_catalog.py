from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
# FREE_LLM_SCRIPT_SYSPATH_GATE

from app.services.free_llm.model_catalog_refresh_service import refresh_free_llm_model_catalog

if __name__ == "__main__":
    result = refresh_free_llm_model_catalog()
    print("FREE_LLM_CATALOG_REFRESH_OK")
    print("candidate_count =", result.get("candidate_count"))
    for item in result.get("provider_summaries", []):
        print(item)
