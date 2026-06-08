import os
from dotenv import load_dotenv

load_dotenv()


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

TARGET_LOCATIONS = [
    loc.strip().lower()
    for loc in os.getenv("TARGET_LOCATIONS", "Boston,Raleigh,Remote").split(",")
]

GRADUATION_EARLIEST = os.getenv("GRADUATION_EARLIEST", "2025-12")
GRADUATION_LATEST = os.getenv("GRADUATION_LATEST", "2026-08")

TOP_K_CANDIDATES = int(os.getenv("TOP_K_CANDIDATES", "100"))

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "mlruns")
MLFLOW_EXPERIMENT_NAME = os.getenv("MLFLOW_EXPERIMENT_NAME", "recruitment-filtration-agent")

RESUME_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "resumes")
JOB_REQUIREMENTS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "data", "job_requirements"
)
