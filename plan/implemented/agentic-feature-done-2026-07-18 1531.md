# Ollama Chat Agent

> **Status:** Draft  
> **Created:** 2026-07-18 14:09:34  
> **Last Updated:** 2026-07-18 14:35:00

## Overview

Add a simple chat interface that allows users to interact with an LLM running on Ollama. The interface provides a text input for user messages and displays LLM responses. Initially, the only available tool is `whoami`, which returns information about the agent.

## Motivation

The application currently processes photos using Ollama vision models, but there is no way to directly chat with the LLM. A simple chat interface enables:

- Direct interaction with the LLM for debugging and testing
- Foundation for future agentic capabilities
- User familiarity with the LLM's responses and capabilities

## Requirements

- [ ] **R1 — Chat interface:** Provide a text input field and display area for conversing with the LLM
- [ ] **R2 — Message history:** Display the conversation history (user messages and LLM responses)
- [ ] **R3 — whoami tool:** Implement a `whoami` tool/command that returns agent information
- [ ] **R4 — Connection to Ollama:** Use existing Ollama connection configuration (host, port, model)
- [ ] **R5 — Basic error handling:** Show errors if Ollama is unavailable or returns invalid responses

## Design / Approach

### Architecture

The chat interface is a simple addition to the existing web UI that sends messages to Ollama and displays responses.

```
User → Web UI (Dash) → Chat Callback → OllamaPhotoExtractor → Ollama → Response → Web UI
```

The `whoami` tool is a special command that, when detected in the user's message, returns a predefined response about the agent instead of sending the message to Ollama.

### Components

#### 1. Web UI Chat Component

Add a chat panel to the existing Dash layout:
- Text input for user messages
- Submit button
- Conversation display area (scrollable)
- Clear chat button

#### 2. Chat Callback

A new callback that:
- Receives user messages from the chat input
- Checks if the message is a tool command (e.g., `/whoami`)
- If tool command: generate response directly
- If regular message: send to Ollama and display response
- Updates conversation history

#### 3. whoami Tool

A simple function that returns a formatted string describing the agent:
```python
def whoami() -> str:
    return "I am the Open Photo Agent, a tool for extracting features from photos using Ollama vision models."
```

### Files to modify

```
src/layout.py
  - Add chat interface section to the main layout
  - Include: chat history display, message input, submit button, clear button

src/callbacks/__init__.py
  - Import and register new chat callback

src/callbacks/chat.py (NEW)
  - register_chat_callback() - Main chat callback
  - register_clear_chat_callback() - Clear conversation history
  - whoami_tool() - The whoami tool implementation

src/components.py
  - build_chat_interface() - Create chat UI components
  - build_chat_message() - Render individual chat messages

app.py
  - No changes needed (chat is purely frontend + callback)

src/config.py
  - No changes needed (uses existing LLM config)
```

### Database changes

None. The chat interface does not require persistent storage (conversation history is session-based).

### API changes

None. The chat operates through existing Dash callback mechanisms.

## Implementation Steps

1. Create `src/callbacks/chat.py` with chat callback and whoami tool
2. Add chat UI components to `src/components.py`
3. Add chat section to `src/layout.py`
4. Register chat callbacks in `src/callbacks/__init__.py`
5. Test the chat interface manually

## Testing Plan

- [ ] Unit tests for whoami tool
- [ ] Manual test: chat interface renders correctly
- [ ] Manual test: regular messages are sent to Ollama and responses displayed
- [ ] Manual test: `/whoami` command returns agent description
- [ ] Manual test: error handling when Ollama is unavailable

## Edge Cases & Risks

- **Ollama unavailable:** Display clear error message to user
- **Empty messages:** Ignore or show validation error
- **Long responses:** Ensure chat display handles long LLM responses (scrollable area)
- **Model differences:** Different models may respond differently; this is expected behavior

## References

- `src/callbacks/prompt_tester.py` - Existing pattern for LLM interaction callbacks
- `src/layout.py` - Layout structure for adding new sections
- `src/components.py` - Component building patterns
- `plugins/llm/ollama.py` - OllamaPhotoExtractor for sending messages
