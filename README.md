# AI Calendar Management Agent

A LangGraph-based intelligent calendar management system that processes audio input through UDP and provides automated scheduling, task management, and calendar organization capabilities.

## Overview

This project combines real-time audio processing with intelligent calendar management, allowing users to send voice commands that are transcribed and converted into calendar events, tasks, and organized schedules. The system uses LangGraph for agent orchestration and integrates with Google Calendar and Tavily search for comprehensive calendar management.

### Demo Video

Watch how this AI Calendar Management Agent can be used with cardputer:

[![AI Calendar Management Agent with Cardputer](https://img.youtube.com/vi/qJXeVfc1xkE/0.jpg)](https://www.youtube.com/watch?v=qJXeVfc1xkE)

## Architecture

The system consists of several key components:

- **UDP Audio Server**: Receives and processes audio packets in real-time
- **LangGraph Agent**: Orchestrates calendar management workflows
- **Audio Transcription**: Converts speech to text using Eleven Labs API
- **Calendar Integration**: Manages Google Calendar events and tasks
- **Search Integration**: Provides real-time information for calendar planning

## Key Features

- Real-time audio processing via UDP protocol
- Speech-to-text transcription using Eleven Labs
- Intelligent calendar event creation and management
- Task planning and todo list management
- Internet search for enhanced calendar context
- Multi-calendar support with Google Calendar integration
- Virtual file system for context persistence

---

## 1. UDP Server

The UDP Audio Server (`src/udp_audio_server.py`) is the entry point for receiving audio data from clients.

### How it Works

- **Listens on port 9876** for incoming UDP packets containing audio data
- **Manages client sessions** with packet buffering and timeout handling
- **Processes audio in chunks** and waits 2 seconds after the last packet before processing
- **Handles concurrent clients** using thread pools

### Key Components

- `ClientSession`: Manages individual client connections and audio buffering
- `AudioConversionService`: Handles audio format conversion and transcription
- `UdpAudioServer`: Main server class that orchestrates the entire process

### Audio Processing Flow

1. Client sends audio packets to UDP port 9876
2. Server buffers packets per client session
3. After 2 seconds of inactivity, complete audio is processed
4. Audio is converted to WAV format
5. Eleven Labs API transcribes the audio to text
6. Transcription is passed to the LangGraph agent for processing

---

## 2. LangGraph Agent Invocation

The LangGraph agent is invoked automatically when audio transcription is complete.

### Invocation Process

Located in `src/udp_audio_server.py` lines 355-372:

```python
# Generate random thread ID for session isolation
random_thread_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
config = {"configurable": {"thread_id": random_thread_id}, "recursion_limit": 50}

# Invoke agent with transcription and available tools
output = graph.invoke({"messages": transcript, 'tools': MyTools().getAllTools()}, config=config)
```

### Agent Workflow

The agent workflow is defined in `src/AI_Scope_Agent/basic_agent.py`:

1. **Input Processing**: Receives transcribed text and available tools
2. **Tool Requirement Analysis**: Determines if calendar tools are needed
3. **Tool Execution**: Uses appropriate calendar management tools
4. **Response Generation**: Returns confirmation and results to client

### Graph Structure

- **START** → **llm_with_tools** → **tool_node** (if tools needed) → **llm_with_tools**
- Uses conditional routing based on tool requirements
- Maintains conversation state and context

---

## 3. API Key Configuration

### Eleven Labs API Key

**File**: `src/udp_audio_server.py` (line 412)

```python
ELEVEN_LABS_API_KEY = "<key>"  # Replace with your actual Eleven Labs API key
```

**To update**: Replace the placeholder `"<key>"` with your actual Eleven Labs API key.

### Tavily and Google API Keys

**File**: `src/AI_Tools/tools.py`

- **Tavily API Key** (line 252):
  ```python
  tavily_client = TavilyClient(api_key="<api-key>")  # Replace with your Tavily API key
  ```

- **Google Calendar API** (lines 96-101):
  ```python
  credentials = get_google_credentials(
      token_file="token.json",
      scopes=["https://www.googleapis.com/auth/calendar"],
      client_secrets_file="gcp-oauth.keys.json.json",
  )
  ```

- **Calendar ID Configuration** (line 241):
  ```python
  {"id": "<primary-calendar-id>", "summary": "<primary-calendar-summary>", "timeZone": "<timezone>"}
  ```

**To update**:
1. Replace `"<api-key>"` with your Tavily API key
2. Ensure `gcp-oauth.keys.json.json` contains your Google Calendar API credentials

**Important Note**: The `search_calendar_event` tool from MCP is not properly functioning, so we have created a custom implementation. Please ensure to update your calendar ID in the `SEARCH_CALENDAR_EVENT` tool (line 241 in `tools.py`) with your actual Google Calendar ID, summary, and timezone.

---

## 4. System Prompt

The system prompt is located in `src/AI_Sys_Prompt/system_prompt_todo_req.txt` and defines the AI agent's behavior and capabilities.

### Purpose

The system prompt instructs the AI to act as an **AI Calendar Management Assistant** with the following responsibilities:

- Convert user requests into well-planned calendar tasks and events
- Create calendar events for specific tasks and recurring schedules
- Find optimal time slots based on user availability
- Organize learning plans with structured timelines
- Manage calendar events across multiple calendars

### Key Features Defined

1. **Calendar Management Tools**: Detailed instructions for using CREATE_CALENDAR_EVENT, SEARCH_CALENDAR_EVENT, UPDATE_CALENDAR_EVENT, and DELETE_CALENDAR_EVENT
2. **Internet Search Integration**: Guidelines for using Tavily search to enhance calendar events with relevant resources
3. **Internal Workflow**: Mandatory use of todo management tools for task tracking
4. **Virtual File System**: Instructions for maintaining context and saving user requests

### Workflow Process

The prompt enforces a structured workflow:
1. Create TODO list at the start of each request
2. Check availability and plan calendar events
3. Use search tools when real-time information is needed
4. Manage virtual file system for context persistence
5. Provide clear final confirmations

---

## Installation and Setup

### Prerequisites

- Python 3.8+
- Eleven Labs API key
- Tavily API key
- Google Calendar API credentials

Configure Google Calendar OAuth:
- Place your client secrets in `src/gcp-oauth.keys.json.json`
- Ensure `token.json` is properly configured

### Running the Server

```bash
cd src
python udp_audio_server.py
```

The server will start listening on port 9876 for audio input.

## Usage

1. Send audio packets to `localhost:9876` via UDP
2. Wait for transcription and agent processing
3. Receive calendar management responses via UDP

## License

See LICENSE file for details.
