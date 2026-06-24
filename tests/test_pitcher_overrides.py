import pytest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from pitcher_overrides import load_pitcher_overrides

def test_returns_empty_dict_when_file_missing():
    result = load_pitcher_overrides("nonexistent_file_xyz.txt")
    assert result == {}

def test_parses_sp_and_rp_overrides(tmp_path):
    f = tmp_path / "overrides.txt"
    f.write_text("Spencer Strider = SP\nTrevor Williams = RP\n")
    result = load_pitcher_overrides(str(f))
    assert result == {"Spencer Strider": "SP", "Trevor Williams": "RP"}

def test_ignores_comments_and_blank_lines(tmp_path):
    f = tmp_path / "overrides.txt"
    f.write_text("# comment\n\nSpencer Strider = SP\n")
    result = load_pitcher_overrides(str(f))
    assert result == {"Spencer Strider": "SP"}

def test_role_is_case_insensitive(tmp_path):
    f = tmp_path / "overrides.txt"
    f.write_text("Spencer Strider = sp\n")
    result = load_pitcher_overrides(str(f))
    assert result == {"Spencer Strider": "SP"}

def test_warns_and_skips_malformed_line(tmp_path, capsys):
    f = tmp_path / "overrides.txt"
    f.write_text("Spencer Strider SP\n")
    result = load_pitcher_overrides(str(f))
    assert result == {}
    assert "Warning" in capsys.readouterr().out

def test_warns_and_skips_unrecognized_role(tmp_path, capsys):
    f = tmp_path / "overrides.txt"
    f.write_text("Spencer Strider = CLOSER\n")
    result = load_pitcher_overrides(str(f))
    assert result == {}
    assert "Warning" in capsys.readouterr().out

def test_whitespace_around_name_and_role_is_trimmed(tmp_path):
    f = tmp_path / "overrides.txt"
    f.write_text("  Spencer Strider  =  SP  \n")
    result = load_pitcher_overrides(str(f))
    assert result == {"Spencer Strider": "SP"}
