"""Temporary compatibility import during the experiment-session migration."""

from experiment_session import ExperimentSession


BaseGenerator = ExperimentSession

__all__ = ["BaseGenerator"]