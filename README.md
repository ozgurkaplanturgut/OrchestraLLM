# OrchestraLLM: Asynchronous AI Task Orchestrator

OrchestraLLM is a Python service built on FastAPI that asynchronously executes various LLM and Multi-Agent tasks, streaming the results in real-time via WebSockets. The system is designed with a modular architecture and can manage complex tasks like Chat, Retrieval-Augmented Generation (RAG), travel planning, and recipe finding.

## Features

-   **Asynchronous Task Processing**: HTTP requests receive an immediate `task_id`, and tasks are executed in the background using `asyncio`.
-   **Real-Time Streaming**: Task progress and results (token-by-token) are streamed live to the client over WebSockets.
-   **Chat**: A basic chat capability with session-based memory stored in MongoDB.
-   **Retrieval-Augmented Generation (RAG)**: Ingests a document from a URL, chunks it, stores it as vectors in Qdrant, and allows for conversational queries over the document.
-   **Multi-Agent Systems**:
    -   **Travel Planner**: A team of agents collaborates to create a travel itinerary based on user requests.
    -   **Recipe Finder**: A team of agents searches the web to find and present cooking recipes.
-   **Containerized**: Easily deployable with Docker and Docker Compose for a consistent environment.

## Architecture Overview

The system is built on an architecture that immediately accepts tasks and processes them in the background. This approach prevents long-running LLM calls from causing HTTP timeouts and provides a scalable foundation.

1.  **Task Creation**: The client sends an HTTP POST request to a `/v1/tasks/...` endpoint to initiate a task.
2.  **Immediate Response**: The API queues the request, generates a unique `task_id`, and immediately returns it to the client.
3.  **Background Execution**: The task is executed in the background using `asyncio.create_task`. These tasks run independently within the Gunicorn workers.
4.  **Real-Time Streaming**: The client uses the received `task_id` to connect to the `/v1/stream/{task_id}` WebSocket endpoint.
5.  **Event Publishing**: As the task runs, it publishes events (status updates, LLM tokens, error messages) to both a `streams` collection in MongoDB and an in-process Event Bus.
6.  **Streaming to Client**: The WebSocket connection delivers live events from the Event Bus and also backfills historical events from MongoDB to prevent data loss if the client disconnects and reconnects.

## Technology Stack

-   **Web Framework**: FastAPI, Uvicorn, Gunicorn
-   **Vector Database**: Qdrant
-   **State/History Store**: MongoDB
-   **LLM & Embeddings**: OpenAI API
-   **Agent Frameworks**: `agno`, `autogen`, `langchain`, `langgraph` 
-   **Containerization**: Docker, Docker Compose
-   **Libraries**: `httpx`, `websockets`, `pypdf`, `pymongo`, `qdrant-client`

## Getting Started

### Prerequisites

-   [Docker](https://www.docker.com/get-started)
-   [Docker Compose](https://docs.docker.com/compose/install/)

### 1. Configuration

Create a `.env` file in the project's root directory by copying the example file.

cp .env.example .env

Next, open the `.env` file and update the `OPENAI_API_KEY` variable with your own OpenAI API key.


# .env
# OpenAI
OPENAI_API_KEY="sk-..."
OPENAI_BASE_URL="https://api.openai.com/v1"

# Other settings can remain at their default values.


### 2. Build and Run

Start all services using Docker Compose. The images will be pulled on the first run.

--> docker build -t orchestrallm:1.0 .

--> docker compose up

You can verify that the API is running by hitting the `/health` endpoint:

curl http://127.0.0.1:8076/health

A successful response will look like `{"ok":true, ...}`.

## Usage & API Endpoints

All tasks run asynchronously and return a `task_id`. To monitor the results, you need to connect to the `/v1/stream/{task_id}` WebSocket endpoint.

| Endpoint                 | Method | Description                                                               |
| ------------------------ | ------ | ------------------------------------------------------------------------- |
| `/health`                | `GET`  | Checks if the service is up and running.                                  |
| `/v1/tasks/chat`         | `POST` | Starts or continues a stateful chat session.                              |
| `/v1/tasks/ingest`       | `POST` | Downloads, processes, and ingests a document from a URL into Qdrant.      |
| `/v1/tasks/rag`          | `POST` | Performs RAG-based chat over an ingested document.                        |
| `/v1/tasks/recipes`      | `POST` | Searches for and presents recipes based on the given input.               |
| `/v1/tasks/travel`       | `POST` | Creates a travel plan using a multi-agent approach.                       |
| `/v1/stream/{task_id}`   | `WS`   | WebSocket connection to listen for the event stream of a specific task.   |

## Running the E2E Test Script

The project includes an end-to-end test script (`test.py`) that covers all major features.

1.  **Install the required Python packages:**

    ```sh
    pip install requests websockets
    ```

2.  **Configure the test script:**

    The script contains several test scenarios inside the `main()` function, which are commented out by default. To run a specific scenario, open `test.py` and uncomment the corresponding lines.

    For example, to run only the **Chat** test, modify the `main()` function at the bottom of `test.py` as follows:

    ```python
    # test.py

    def main():
        # ... (parser code)

        # 0) Health
        test_health(args.base_url)

        # 1) Chat sequence (remembering name)
        asyncio.run(test_chat_sequence(args.base_url, args.user, args.session))

        # 2) Ingest + RAG - Keep this test disabled
        # rag_qs = [...]
        # asyncio.run(test_ingest_and_rag(...))

        # 3) Recipe
        # asyncio.run(test_recipes(args.base_url, args.user, args.session))
        
        # 4) Travel - Keep this test disabled
        # travel_qs = [...]
        # asyncio.run(test_travel(...))

    if __name__ == "__main__":
        main()
    ```

3.  **Run the script:**

    In a separate terminal (while the API is running), execute the script:

    ```sh
    python3 test.py
    ```

    You will see the task progress and the live-streamed responses from the LLM directly in your terminal.

## Project Structure

```
.
├── app/                  # Main application logic
│   ├── data/             # Data processing (ingestion, chunking)
│   ├── rag/              # RAG core logic
│   ├── services/         # External service clients (OpenAI, Web Search)
│   ├── tasks/            # Asynchronous task logic (chat, ingest, rag, etc.)
│   └── travel/           # Travel agent logic
├── utils/                # Utility modules (config, db, events, etc.)
├── api_service.py        # FastAPI application and endpoint definitions
├── test.py               # E2E test script
├── Dockerfile            # Docker image definition for the API service
├── docker-compose.yml    # Service definitions (api, mongo, qdrant)
├── gunicorn.conf.py      # Gunicorn configuration
├── requirements.txt      # Python dependencies
└── README.md             # This file
```