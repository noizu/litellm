# Cerebras Beta Parameter Issue - Idiomatic Fix

## The Problem

When routing Anthropic models through Cerebras, LiteLLM filters Anthropic beta parameters incorrectly because **Cerebras is not in the configuration**.

**What happens:**
1. Client sends request with Anthropic beta features
2. Router selects Cerebras as optimal provider
3. `update_request_with_filtered_beta(provider="cerebras")` called
4. `config.get("cerebras", {})` returns empty dict
5. All beta parameters filtered out (safe-fail pattern)
6. Request sent without beta parameters

## Root Cause

**File**: `litellm/anthropic_beta_headers_config.json`

**Missing**:
- ❌ `"cerebras"`
- ❌ `"cerebras_ai"`

**Defined**:
- ✅ `"anthropic"`, `"azure_ai"`, `"bedrock"`, `"bedrock_converse"`, `"vertex_ai"`, `"databricks"`

---

## The Idiomatic Fix

### Single Config Change (No Code Changes)

**File**: `litellm/anthropic_beta_headers_config.json`

Add at the end (before closing `}`):
```json
  "cerebras": {
    "advisor-tool-2026-03-01": null,
    "advanced-tool-use-2025-11-20": null,
    "bash_20241022": null,
    "bash_20250124": null,
    "code-execution-2025-08-25": null,
    "compact-2026-01-12": null,
    "computer-use-2025-01-24": null,
    "computer-use-2025-11-24": null,
    "context-1m-2025-08-07": null,
    "context-management-2025-06-27": null,
    "effort-2025-11-24": null,
    "fast-mode-2026-02-01": null,
    "files-api-2025-04-14": null,
    "fine-grained-tool-streaming-2025-05-14": null,
    "interleaved-thinking-2025-05-14": null,
    "mcp-client-2025-11-20": null,
    "mcp-client-2025-04-04": null,
    "mcp-servers-2025-12-04": null,
    "oauth-2025-04-20": null,
    "output-128k-2025-02-19": null,
    "prompt-caching-scope-2026-01-05": null,
    "skills-2025-10-02": null,
    "structured-output-2024-03-01": null,
    "structured-outputs-2025-11-13": null,
    "text_editor_20241022": null,
    "text_editor_20250124": null,
    "token-efficient-tools-2025-02-19": null,
    "web-fetch-2025-09-10": null,
    "web-search-2025-03-05": null
  },
  "cerebras_ai": {
    "advisor-tool-2026-03-01": null,
    "advanced-tool-use-2025-11-20": null,
    "bash_20241022": null,
    "bash_20250124": null,
    "code-execution-2025-08-25": null,
    "compact-2026-01-12": null,
    "computer-use-2025-01-24": null,
    "computer-use-2025-11-24": null,
    "context-1m-2025-08-07": null,
    "context-management-2025-06-27": null,
    "effort-2025-11-24": null,
    "fast-mode-2026-02-01": null,
    "files-api-2025-04-14": null,
    "fine-grained-tool-streaming-2025-05-14": null,
    "interleaved-thinking-2025-05-14": null,
    "mcp-client-2025-11-20": null,
    "mcp-client-2025-04-04": null,
    "mcp-servers-2025-12-04": null,
    "oauth-2025-04-20": null,
    "output-128k-2025-02-19": null,
    "prompt-caching-scope-2026-01-05": null,
    "skills-2025-10-02": null,
    "structured-output-2024-03-01": null,
    "structured-outputs-2025-11-13": null,
    "text_editor_20241022": null,
    "text_editor_20250124": null,
    "token-efficient-tools-2025-02-19": null,
    "web-fetch-2025-09-10": null,
    "web-search-2025-03-05": null
  }
```

**That's the entire fix.**

---

## Why This Is Idiomatic

✅ **Config-driven design**: LiteLLM uses configuration, not hardcoded logic
✅ **Safe-fail pattern**: `config.get("cerebras", {})` returns empty dict
✅ **Explicit over implicit**: Each provider explicitly declared
✅ **Future-proof**: Add support by changing `null` → feature name when Cerebras adds features
✅ **No code changes**: Filtering logic already handles this correctly

---

## Why NOT the Fallback Approach

❌ **Not idiomatic**: Hardcoded fallback logic defeats config-driven design
❌ **Code duplication**: Creates maintenance burden (KNOWN_PROVIDERS list)
❌ **Silent magic**: Anthropic defaults != Cerebras capabilities
❌ **Non-explicit**: Config should be complete, not rely on implicit defaults

---

## What This Accomplishes

| Scenario | Result |
|----------|--------|
| Route Anthropic model through Cerebras | Beta params properly filtered (safe) ✅ |
| Unknown provider (typo) | Beta params silently filtered (safe) ✅ |
| Cerebras adds feature support | Update config, done (no code change) ✅ |

---

## Testing

```python
def test_cerebras_filters_unsupported_beta():
    """Verify Cerebras doesn't support beta features"""
    headers = {"anthropic-beta": "fast-mode-2026-02-01"}
    request_data = {"anthropic_beta": ["fast-mode-2026-02-01"]}
    
    h, d = update_request_with_filtered_beta(
        headers=headers,
        request_data=request_data,
        provider="cerebras"
    )
    
    # All beta params filtered
    assert "anthropic-beta" not in h
    assert "anthropic_beta" not in d
```

---

## Summary

- **Change**: Config only (add 2 provider entries)
- **Complexity**: Minimal (copy-paste from databricks entry, all values null)
- **Code changes**: Zero
- **Pattern**: Follows existing LiteLLM configuration paradigm
- **Future support**: Just update config values from null to feature names
