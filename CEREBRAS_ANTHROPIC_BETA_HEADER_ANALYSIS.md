# Cerebras Support Analysis: Anthropic Beta Parameter Issues

## Executive Summary

When using Anthropic models through the Cerebras provider, LiteLLM's Anthropic beta parameter filtering mechanism breaks because **Cerebras is not defined in the `anthropic_beta_headers_config.json` configuration file**. This causes inconsistent behavior:

1. **Current Behavior**: Unknown/unsupported beta parameters are dropped (because Cerebras isn't in the config)
2. **Intended Behavior**: Beta parameters should only be applied when the target provider supports them
3. **The Problem**: When the proxy routes `anthropic → cerebras → anthropic`, the handler passes `custom_llm_provider="cerebras"`, but Cerebras has no entry in the beta config, resulting in all beta parameters being filtered out inappropriately

## Note on Beta Parameter Formats

Anthropic beta features are passed to the API in three ways:
1. **HTTP Header**: `anthropic-beta: feature-2025-01-01` (primary method)
2. **Request Body**: `{"anthropic_beta": ["feature-2025-01-01"]}` (body parameter)
3. **Query Parameter**: `?beta=true` (used for specific endpoints like Skills API)

This analysis covers the header and body parameter filtering. The query parameter approach is endpoint-specific.

---

## Root Cause Analysis

### The Anthropic Beta Parameters Filtering System

LiteLLM maintains centralized control of Anthropic beta parameters through:

**File**: `litellm/anthropic_beta_headers_manager.py`

**Config**: `litellm/anthropic_beta_headers_config.json`

#### How It Works

1. **Configuration-Driven**: `anthropic_beta_headers_config.json` contains a mapping of which beta parameters each provider supports (used for both HTTP headers and request body fields)
   ```json
   {
     "anthropic": {
       "fast-mode-2026-02-01": "fast-mode-2026-02-01",
       "web-fetch-2025-09-10": "web-fetch-2025-09-10",
       ...
     },
     "azure_ai": { ... },
     "bedrock": { ... },
     "vertex_ai": { ... },
     // BUT NO "cerebras" ENTRY!
   }
   ```

2. **Filtering at Request Time**: Before sending any Anthropic request, `update_request_with_filtered_beta()` is called to filter BOTH HTTP headers and request body parameters:
   ```python
   # litellm/llms/anthropic/chat/handler.py, line 377-381
   headers, data = update_request_with_filtered_beta(
       headers=headers,              # Filters anthropic-beta HTTP header
       request_data=data,            # Filters anthropic_beta request body field
       provider=custom_llm_provider,  # This is "cerebras", "azure_ai", etc.
   )
   ```

3. **The Filtering Logic**: The function filters both HTTP headers and request body parameters:

   **HTTP Header Filtering** (`update_headers_with_filtered_beta`):
   - Reads: `headers["anthropic-beta"]` (comma-separated string)
   - Filters using: `filter_and_transform_beta_headers()`
   - Writes back: `headers["anthropic-beta"]` (updated or removed)

   **Request Body Filtering** (`update_request_with_filtered_beta`):
   - Reads: `request_data["anthropic_beta"]` (list of strings)
   - Filters using: Same `filter_and_transform_beta_headers()`
   - Writes back: `request_data["anthropic_beta"]` (updated or removed)

   **Core Logic**: `filter_and_transform_beta_headers()` checks each beta parameter against the provider's mapping:
   ```python
   # litellm/anthropic_beta_headers_manager.py, line 224-277
   def filter_and_transform_beta_headers(
       beta_headers: List[str],
       provider: str,
   ) -> List[str]:
       config = _load_beta_headers_config()
       provider_mapping = config.get(provider, {})  # Returns {} for unknown providers!
       
       for header in beta_headers:
           if header not in provider_mapping:
               verbose_logger.debug(
                   f"Dropping unknown beta header '{header}' for provider '{provider}'"
               )
               continue  # SKIPPED - header dropped!
           
           mapped_header = provider_mapping[header]
           if mapped_header is None:
               continue  # SKIPPED - unsupported header dropped!
           
           filtered_headers.add(mapped_header)
       
       return sorted(list(filtered_headers))
   ```

### The Cerebras Gap

**Problem**: When `provider="cerebras"`, the config lookup returns an empty dict:
```python
provider_mapping = config.get("cerebras", {})  # Returns {}
```

**Consequence**: ALL beta headers are dropped because the mapping is empty.

### Where Cerebras is Used

**Scenario**: Proxy routing `Anthropic model → Cerebras API → Anthropic response`

1. **User Request**: Client calls proxy with model="claude-3-opus" (Anthropic model)
2. **Proxy Routing**: Router detects Cerebras has lower cost or better latency, routes through Cerebras
3. **Handler Initialization**: `AnthropicChatCompletion.acompletion()` is invoked with `custom_llm_provider="cerebras"`
4. **Beta Header Filtering**: `update_request_with_filtered_beta()` called with `provider="cerebras"`
5. **Filter Result**: Cerebras not in config → all beta headers dropped
6. **Outcome**: Request sent to Cerebras without any beta headers (even those Cerebras might support)

---

## Technical Details

### Call Stack

```
proxy/proxy_server.py (chat_completion endpoint)
  ↓
router.completion(model="claude-3-opus")
  ↓
litellm/main.py acompletion()
  ↓
litellm/llms/anthropic/chat/handler.py AnthropicChatCompletion.acompletion()
  ↓ (custom_llm_provider="cerebras")
  ↓
anthropic_beta_headers_manager.update_request_with_filtered_beta(provider="cerebras")
  ↓
filter_and_transform_beta_headers(beta_headers=[...], provider="cerebras")
  ↓
config.get("cerebras", {}) → {}  # UNKNOWN PROVIDER!
  ↓
All headers dropped (because mapping is empty)
```

### Affected Code Locations

| File | Line(s) | Issue |
|------|---------|-------|
| `litellm/anthropic_beta_headers_config.json` | - | Missing "cerebras" and "cerebras_ai" entries |
| `litellm/llms/anthropic/chat/handler.py` | 377-381 | Passes `custom_llm_provider` to filter without fallback |
| `litellm/anthropic_beta_headers_manager.py` | 250 | `config.get(provider, {})` returns empty dict for unknown providers |
| `litellm/anthropic_beta_headers_manager.py` | 258-262 | Logic assumes all unknown headers should be dropped |

---

## Impact Assessment

### Severity: **MEDIUM-HIGH**

**Affected Users**:
- Anyone routing Anthropic models through Cerebras (direct SDK users + proxy users)
- Enterprise deployments using cost-optimized routing

**Failure Modes**:

1. **Beta Features Disabled Silently**
   - Features like `web-fetch-2025-09-10`, `fast-mode-2026-02-01` are silently dropped when routing through Cerebras
   - User code expects features to work but they don't
   - No error message; just silent feature degradation

2. **Response API Failures** (if Response API is being used)
   - If Response API beta header was being set, it would be dropped
   - Response API calls would fail with "unsupported" error from Cerebras
   - Proxy error: `400 Bad Request` from Cerebras due to unknown beta header

3. **Inconsistent Behavior**
   - `router.acompletion(model="claude-opus")` with Cerebras ≠ direct Anthropic call
   - Same request with different routing produces different results
   - Makes debugging impossible for users

### Examples of Impact

**Example 1: Web Fetch Feature**
```python
# User code
response = await litellm.acompletion(
    model="claude-3-opus",
    messages=[...],
    tools=[{
        "type": "web_fetch",  # Uses hosted web fetch tool
        "fetch_url": "https://..."
    }]
)

# What happens:
# 1. Anthropic handler adds: anthropic-beta: web-fetch-2025-09-10
# 2. update_request_with_filtered_beta() called with provider="cerebras"
# 3. Beta header DROPPED because Cerebras not in config
# 4. Request sent to Cerebras WITHOUT web-fetch header
# 5. Cerebras doesn't recognize tool type → 400 error
```

**Example 2: Fast Mode**
```python
response = await litellm.acompletion(
    model="claude-3-opus",
    messages=[...],
    speed="fast"  # Triggers fast-mode-2026-02-01 beta header
)

# Result: Beta header dropped → Request sent without fast mode → slower inference
```

---

## Root Cause: Configuration Gap

The `anthropic_beta_headers_config.json` has entries for:
- ✅ `anthropic` — Direct Anthropic API
- ✅ `azure_ai` — Azure AI Anthropic
- ✅ `bedrock` — AWS Bedrock (with Claude models)
- ✅ `bedrock_converse` — AWS Bedrock Converse API
- ✅ `vertex_ai` — Google Vertex AI
- ✅ `databricks` — Databricks
- ❌ **`cerebras` — MISSING**
- ❌ **`cerebras_ai` — MISSING**

### Why This Matters

When LiteLLM routes through a provider not in the config, it has two choices:

**Current Behavior** (line 250 in `anthropic_beta_headers_manager.py`):
```python
provider_mapping = config.get(provider, {})  # Defaults to empty dict
```

**Result**: Unknown providers → empty mapping → all headers filtered out

**Better Behavior** (Proposed):
```python
provider_mapping = config.get(provider)
if provider_mapping is None:
    # Fallback to anthropic defaults for unknown providers
    provider_mapping = config.get("anthropic", {})
    # Or raise an error, or log a warning
```

---

## Recommended Fixes

### Fix 1: Add Cerebras to Configuration (IMMEDIATE)

**File**: `litellm/anthropic_beta_headers_config.json`

Add entries for Cerebras:
```json
{
  ...existing entries...
  "cerebras": {
    "advisor-tool-2026-03-01": null,
    "advanced-tool-use-2025-11-20": null,
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
    "output-128k-2025-02-19": null,
    "prompt-caching-scope-2026-01-05": null,
    "skills-2025-10-02": null,
    "structured-outputs-2025-11-13": null,
    "token-efficient-tools-2025-02-19": null,
    "web-fetch-2025-09-10": null,
    "web-search-2025-03-05": null
  },
  "cerebras_ai": {
    // Same as cerebras, all null for now
    // Update as Cerebras adds support
  }
}
```

**Rationale**:
- Cerebras (as of April 2026) does **not** support Anthropic beta features
- Setting all values to `null` ensures beta headers are properly filtered out
- Future updates to Cerebras support can enable specific headers

### Fix 2: Add Graceful Fallback (DEFENSIVE)

**File**: `litellm/anthropic_beta_headers_manager.py`

```python
def filter_and_transform_beta_headers(
    beta_headers: List[str],
    provider: str,
) -> List[str]:
    if not beta_headers:
        return []
    
    config = _load_beta_headers_config()
    provider = get_provider_name(provider)
    
    # Get the header mapping for this provider
    provider_mapping = config.get(provider)
    
    # NEW: Graceful fallback if provider not found
    if provider_mapping is None:
        verbose_logger.warning(
            f"Provider '{provider}' not found in beta headers config. "
            f"Falling back to 'anthropic' defaults. "
            f"(This may indicate a new provider that needs to be added to the config)"
        )
        provider_mapping = config.get("anthropic", {})
    
    # ... rest of filtering logic ...
```

**Why**: Ensures unknown providers don't silently drop all headers; instead, defaults to Anthropic behavior with a warning.

### Fix 3: Add Provider Validation (SAFEGUARD)

**File**: `litellm/llms/anthropic/chat/handler.py`

Add validation before calling filter:
```python
if custom_llm_provider not in ["anthropic", "azure_ai", "bedrock", "vertex_ai", "databricks", "cerebras", "cerebras_ai"]:
    verbose_logger.warning(
        f"Anthropic handler called with unknown provider: '{custom_llm_provider}'. "
        f"Beta header filtering behavior is undefined. "
        f"Consider adding '{custom_llm_provider}' to anthropic_beta_headers_config.json"
    )

headers, data = update_request_with_filtered_beta(
    headers=headers,
    request_data=data,
    provider=custom_llm_provider,
)
```

---

## Testing Strategy

### Unit Tests to Add

1. **Test Cerebras filtering**:
   ```python
   def test_cerebras_filters_all_beta_headers():
       headers = {"anthropic-beta": "web-fetch-2025-09-10,fast-mode-2026-02-01"}
       filtered = filter_and_transform_beta_headers(
           ["web-fetch-2025-09-10", "fast-mode-2026-02-01"],
           provider="cerebras"
       )
       assert filtered == []  # All should be filtered
   ```

2. **Test fallback behavior**:
   ```python
   def test_unknown_provider_uses_fallback():
       # Should not raise, should use anthropic defaults
       filtered = filter_and_transform_beta_headers(
           ["web-fetch-2025-09-10"],
           provider="unknown_future_provider"
       )
       assert "web-fetch-2025-09-10" in filtered
   ```

### Integration Tests

1. Verify Anthropic-only beta features fail gracefully through Cerebras
2. Verify Anthropic direct calls still work with all beta features
3. Test routing through Cerebras doesn't send unsupported beta headers

### E2E Tests

```python
async def test_anthropic_to_cerebras_routing():
    """Verify routing anthropic models through cerebras works without beta errors"""
    response = await router.acompletion(
        model="claude-3-opus",
        messages=[...],
        tools=[...],
        speed="fast"  # Would normally add fast-mode beta header
    )
    # Should succeed (features may not work, but no 400 error)
```

---

## Migration Path

### Phase 1: Add Cerebras Config (this sprint)
1. Add `cerebras` and `cerebras_ai` to `anthropic_beta_headers_config.json`
2. Set all values to `null` (no beta support yet)
3. Add warning logs when config is missing

### Phase 2: Add Fallback Logic (next sprint)
1. Implement graceful fallback for unknown providers
2. Add validation to warn on unregistered providers
3. Test end-to-end routing

### Phase 3: Enable Cerebras Features (when available)
1. Monitor Cerebras release notes for beta feature support
2. Update config entries from `null` to actual header names as features land
3. Add tests for each newly supported feature

---

## Environment Variable Overrides

For immediate workarounds, users can:

```bash
# Force use of local config only (don't fetch remote)
export LITELLM_LOCAL_ANTHROPIC_BETA_HEADERS=True

# Custom config URL (if maintaining fork with Cerebras support)
export LITELLM_ANTHROPIC_BETA_HEADERS_URL="https://your-domain/anthropic_beta_headers_config.json"
```

---

## Summary of Changes Needed

| Component | Change | Priority | Complexity |
|-----------|--------|----------|-----------|
| Config JSON | Add "cerebras" entry with all null values | P0 | Low |
| Config JSON | Add "cerebras_ai" entry with all null values | P0 | Low |
| Beta Headers Manager | Add fallback for unknown providers | P1 | Low |
| Anthropic Handler | Add provider validation logging | P2 | Low |
| Tests | Add Cerebras-specific filtering tests | P1 | Medium |
| E2E | Test routing through Cerebras | P1 | Medium |
| Docs | Document Cerebras limitations re: beta features | P2 | Low |

---

## Appendix: Cerebras vs Anthropic API Compatibility

| Feature | Anthropic | Cerebras | Status |
|---------|-----------|----------|--------|
| Chat Completions | ✅ | ✅ | Works |
| Streaming | ✅ | ✅ | Works |
| Tool Use (basic) | ✅ | ✅ | Works |
| Web Fetch | ✅ (beta) | ❌ | Not supported |
| Fast Mode | ✅ (beta) | ❌ | Not supported |
| Computer Use | ✅ (beta) | ❌ | Not supported |
| Context Management | ✅ (beta) | ❌ | Not supported |
| File API | ✅ (beta) | ❌ | Not supported |
| Skills API | ✅ (beta) | ❌ | Not supported |

**Note**: This comparison is as of April 2026. Update as Cerebras adds feature support.
