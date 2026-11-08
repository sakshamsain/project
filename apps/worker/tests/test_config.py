from pathlib import Path

import pytest

from finn.core.config import load_env_file, load_settings


def test_env_file_is_parsed_without_evaluation(tmp_path: Path) -> None:
    f = tmp_path / "x.env"
    f.write_text('# comment\nGROQ_API_KEY="abc"\n\nBAD LINE\nDATABASE_URL=postgres://u@h/db?x=1\n')
    assert load_env_file(f) == {"GROQ_API_KEY": "abc", "DATABASE_URL": "postgres://u@h/db?x=1"}


def test_process_env_wins_over_file(tmp_path: Path) -> None:
    f = tmp_path / "x.env"
    f.write_text("GROQ_API_KEY=from_file\nTAVILY_API_KEY=t\n")
    s = load_settings({"FINN_ENV_FILE": str(f), "GROQ_API_KEY": "from_env"})
    assert s.groq_api_key == "from_env"
    assert s.tavily_api_key == "t"


def test_require_names_what_is_missing() -> None:
    s = load_settings({})
    with pytest.raises(RuntimeError, match="database_url"):
        s.require("database_url")
