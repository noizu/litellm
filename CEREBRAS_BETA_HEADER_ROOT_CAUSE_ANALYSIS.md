# Cerebras Beta Header Issue: Root Cause & Fix Validation

## The Problem (Your Clarification)

> "the beta header causes litellm to not proxy anthropic style calls to openai interface cerebras uses"

**What's happening:**
1. User makes Anthropic-format request (e.g., to proxy's `/v1/messages` endpoint)
2. Request includes `anthropic-beta` header with Anthropic beta features
3. Router selects Cerebras as optimal provider
4. Request sent to Cerebras (which uses OpenAI-compatible interface)
5. Cerebras rejects request because it doesn't understand `anthropic-beta` header
6. Error: Incompatible header for OpenAI interface

---

## Will My Fix Solve This?

### The Filtering Logic (Current Code)

When `update_request_with_filtered_beta()` is called with `provider="cerebras"`:

```python
# Current behavior (before fix):
provider_mapping = config.get("cerebras", {})  # Returns {} - NOT IN CONFIG
filtered_beta_values = filter_and_transform_beta_headers([...])
# Since mapping is empty, ALL headers filtered OUT

if filtered_beta_values:  # Empty list
    headers["anthropic-beta"] = ",".join(filtered_beta_values)
else:
    headers.pop("anthropic-beta", None)  # HEADER REMOVED ✓
```

### After My Fix (Adding Cerebras to Config)

```python
# After fix:
provider_mapping = config.get("cerebras", {...all null...})  # Found in config
filtered_beta_values = filter_and_transform_beta_headers([...])
# For each header, mapping[header] = null, so all filtered OUT

if filtered_beta_values:  # Still empty list
    headers["anthropic-beta"] = ",".join(filtered_beta_values)
else:
    headers.pop("anthropic-beta", None)  # HEADER STILL REMOVED ✓
```

**Result: Same outcome - header is removed either way**

---

## Critical Question: When Is Filtering Called?

The fix assumes filtering happens **before** the request is sent to Cerebras. Let me trace the flow:

### Scenario A: Anthropic Handler is Used

```
User calls proxy: POST /v1/messages (Anthropic endpoint)
    ↓
Proxy routes through Router
    ↓
Router selects: cerebras (optimal provider)
    ↓
AnthropicChatCompletion.acompletion() called with custom_llm_provider="cerebras"
    ↓
update_request_with_filtered_beta(provider="cerebras")  ← LINE 377
    ↓
anthropic-beta header FILTERED OUT ✓
    ↓
Request sent to Cerebras WITHOUT anthropic-beta ✓
```

**Result: Fix works ✓**

### Scenario B: Direct Pass-Through (Potential Problem)

```
User calls proxy: POST /v1/chat/completions (OpenAI endpoint)
    ↓
Proxy receives OpenAI-format request
    ↓
Router selects: cerebras
    ↓
Request passed directly to Cerebras
    ↓
anthropic-beta header NEVER FILTERED (never goes through Anthropic handler) ✗
    ↓
Cerebras rejects due to anthropic-beta header ✗
```

**Result: Fix won't help ✗**

---

## Root Cause Hypothesis

The real issue might be:

**Either:**
1. The request IS going through Anthropic handler but filtering isn't removing the header properly
   - **Solution**: My fix (add Cerebras to config) will help
   - **Current state without fix**: Header removed (empty dict causes filter) 
   - **With fix**: Header removed (all null values cause filter)
   - **Same outcome** but explicit

2. OR the request is NOT going through Anthropic handler at all
   - **Solution**: My fix won't help; need to add filtering in pass-through path
   - **Needed**: Strip anthropic-beta when converting Anthropic → OpenAI format

3. OR filtering is being called, but then a DIFFERENT handler re-adds the header
   - **Solution**: Need to investigate which handler is re-adding it
   - **Needed**: Prevent header re-injection

---

## What My Fix Actually Does

### Before Fix:
- Unknown provider (cerebras) → empty dict → all headers filtered
- Header is removed (safe-fail behavior)
- **But silently** (no config entry, could indicate a bug)

### After Fix:
- Known provider (cerebras) → explicit null values → all headers filtered  
- Header is removed (intentional, documented)
- **Clearly indicated** in config that Cerebras doesn't support these features

**Bottom line**: Same filtering behavior, better visibility

---

## To Confirm the Fix Will Work

Need to verify:

1. **Where does the anthropic-beta header come from?**
   - User request header?
   - Proxy-added header?
   - Transformation code adding it?

2. **When is it filtered?**
   - Anthropic handler (line 377)?
   - Somewhere else?
   - At all?

3. **After filtering, is it really removed?**
   - Or is it re-added downstream?
   - Or is the request not using the filtered headers?

4. **What does Cerebras actually reject?**
   - The header itself?
   - The header + incompatible request body?
   - Something else?

---

## Recommended Investigation

To confirm my fix will solve the issue:

```bash
# 1. Enable verbose logging
export LITELLM_LOG=debug

# 2. Make Anthropic request through proxy, route to Cerebras
curl -X POST http://localhost:4000/v1/chat/completions \
  -H "Authorization: Bearer sk-..." \
  -H "anthropic-beta: fast-mode-2026-02-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-opus",
    "messages": [{"role": "user", "content": "Hi"}]
  }'

# 3. Check logs for:
# - "anthropic" in provider name (should be "cerebras")
# - "Dropping..." messages from filter (should appear)
# - Final headers sent to Cerebras (should NOT have anthropic-beta)
```

---

## My Assessment

**Most Likely Scenario**: The request DOES go through Anthropic handler, filtering DOES happen, and header IS removed even today.

**Why my fix still helps**:
1. Makes config explicit (Cerebras intentionally doesn't support beta features)
2. Improves observability (config entry proves it was considered)
3. Enables future support (when Cerebras adds features, just update config)
4. Consistent with other providers in the config

**But**: The header might already be getting removed with today's code!

**The real issue might be**: Something else besides the header (e.g., Anthropic-specific request body fields not being converted to OpenAI format)

---

## Conclusion

**Will my fix solve the "anthropic-beta header" problem specifically?**

- **Probably yes** — it ensures headers are explicitly handled
- **But unclear if that's the REAL issue** — headers might already be filtered
- **Real problem might be elsewhere** — request body format mismatch, not headers

**Recommendation**: 
1. Apply my fix (explicitly document Cerebras in config)
2. Add verbose logging to verify filtering is working
3. Investigate if request BODY (not headers) is the actual problem
