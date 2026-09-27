"""Adapter interface — LinkedIn later implements same methods."""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Job:
    job_id: str
    title: str
    company: str
    location: str
    url: str
    posted_ago: str = ""
    applicants: str = ""
