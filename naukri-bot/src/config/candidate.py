"""Candidate profile — 3.1 years everywhere, positive defaults."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

EXP = "3.1"
EXP_LABEL = "3.1 years"

CANDIDATE = {
    "name": "Imran Sutar",
    "email": "Imransutar9970@gmail.com",
    "phone": "9370093936",
    "city": "Pune, Maharashtra, India",
    "exp": EXP,
    "exp_label": EXP_LABEL,
    "current_ctc": "3.6",
    "current_monthly": "30000",
    "expected_ctc": "4.2",
    "expected_monthly": "35000",
    "notice": "15 days",
    "notice_short": "15",
    "relocate": "Yes",
    "immediate": "Immediate joiner",
    "linkedin": os.getenv("LINKEDIN_URL", "https://www.linkedin.com/in/imran-sutar-0a858425b"),
    "github": os.getenv("GITHUB_URL", "https://github.com/Imran2909"),
}

# Every skill from resume maps to 3.1
SKILLS = [
    "javascript", "typescript", "react", "react.js", "next", "next.js",
    "node", "node.js", "express", "express.js", "html", "css",
    "tailwind", "tailwindcss", "material ui", "mui", "bootstrap",
    "redux", "redux toolkit", "zustand",
    "python", "fastapi", "django", "php", "laravel",
    "rest", "rest api", "microservices", "jwt", "oauth2",
    "websockets", "websocket", "joi",
    "mysql", "postgresql", "postgres", "mongodb", "mongo", "mongoose",
    "redis", "sequelize", "typeorm",
    "aws", "ec2", "s3", "lambda", "docker", "nginx",
    "ci/cd", "jest", "git", "github",
    "full stack", "mern", "frontend", "backend",
]

BLOCKED_TITLES = ["wordpress", "angular", "vue", "flutter", "android", "ios",
                  "salesforce", "sap", "data scientist", "data analyst", "devops", "qa", "tester",
                  "recruiter", "bpo", "intern", "trainee",
                  # No AI/ML or Java experience — skip these roles entirely
                  "aiml", "ai/ml", "ai-ml", "ai ml", "machine learning", "ml engineer",
                  "artificial intelligence", "deep learning", "nlp engineer", "data science",
                  "java developer", "java engineer", "java backend", "core java",
                  "java spring", "spring boot", "j2ee", "java full"]
BLOCKED_COMPANIES = ["ti steps", "tele infotech"]
