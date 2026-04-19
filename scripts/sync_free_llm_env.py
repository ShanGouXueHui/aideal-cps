from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"
SRC = ROOT / ".freeLLM"

ALIASES = {
    "OPENROUTER_KEY": "OPENROUTER_API_KEY",
    "NVIDIA_NIM_API_KEY": "NVIDIA_API_KEY",
    "NVIDIA_NGC_API_KEY": "NVIDIA_API_KEY",
    "HF_TOKEN": "HUGGINGFACE_API_KEY",
    "HUGGINGFACE_HUB_TOKEN": "HUGGINGFACE_API_KEY",
    "GOOGLE_API_KEY": "GEMINI_API_KEY",
    "GOOGLE_GEMINI_API_KEY": "GEMINI_API_KEY",
    "ZHIPUAI_API_KEY": "ZHIPU_API_KEY",
    "BIGMODEL_API_KEY": "ZHIPU_API_KEY",
    "DASHSCOPE_API_KEY": "ALI_BAILIAN_API_KEY",
    "BAILIAN_API_KEY": "ALI_BAILIAN_API_KEY",
    "HUNYUAN_API_KEY": "TENCENT_HUNYUAN_API_KEY",
    "TENCENTCLOUD_HUNYUAN_API_KEY": "TENCENT_HUNYUAN_API_KEY"
}


def parse(path: Path) -> dict[str, str]:
    out = {}
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and v:
            out[k] = v
            if k in ALIASES:
                out.setdefault(ALIASES[k], v)
    return out


def render_env(existing_lines: list[str], updates: dict[str, str]) -> tuple[list[str], list[str]]:
    seen = set()
    changed_names = []
    out = []

    for raw in existing_lines:
        line = raw.rstrip("\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            out.append(line)
            continue
        prefix = ""
        body = stripped
        if body.startswith("export "):
            prefix = "export "
            body = body[len("export "):].strip()
        key = body.split("=", 1)[0].strip()
        if key in updates:
            out.append(f"{prefix}{key}={updates[key]}")
            seen.add(key)
            changed_names.append(key)
        else:
            out.append(line)

    missing = [k for k in updates if k not in seen]
    if missing:
        out.append("")
        out.append("# free LLM provider keys synced from .freeLLM")
        for key in sorted(missing):
            out.append(f"{key}={updates[key]}")
            changed_names.append(key)

    return out, sorted(set(changed_names))


def main():
    if not SRC.exists():
        print("FREE_LLM_ENV_SYNC_SKIP: .freeLLM not found")
        return

    updates = parse(SRC)
    if not updates:
        print("FREE_LLM_ENV_SYNC_SKIP: no key=value found")
        return

    existing = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    new_lines, names = render_env(existing, updates)
    ENV.write_text("\n".join(new_lines).rstrip() + "\n", encoding="utf-8")

    print("FREE_LLM_ENV_SYNC_OK")
    print("synced_key_names =", ", ".join(names))


if __name__ == "__main__":
    main()
