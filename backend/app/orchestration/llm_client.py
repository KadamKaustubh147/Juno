"""The chat model, wired to an OpenAI-compatible endpoint (AICredits)."""

from langchain_openai import ChatOpenAI

from app.config import AICREDITS_API_KEY

# Per MLflow's own tracing quickstart: point at a running `mlflow server`, set an
# experiment to group traces under, then autolog. Start the server yourself first:
#   uvx mlflow server
# import mlflow
# import mlflow.langchain
# mlflow.set_tracking_uri("http://localhost:5000")
# mlflow.set_experiment("ai-therapist-chatbot")
# mlflow.langchain.autolog()

MODEL_NAME = "openai/gpt-oss-120b"
llm = ChatOpenAI(
    model=MODEL_NAME,
    base_url="https://aicredits.in/v1",
    api_key=AICREDITS_API_KEY,
)
