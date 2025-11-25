import yaml
from pathlib import Path
from mithrillog.config import Settings, LoggingConfig, LoggingPatternConfig
from mithrillog.orchestrator import Orchestrator
from mithrillog.logging import LogAction

def test_logging_config_parsing(tmp_path):
    config_content = """
logging:
  patterns:
    - pattern: "suppress me"
      action: SUPPRESS
    - pattern: "allow me"
      action: ALLOW
    - pattern: "reclassify me"
      action: RECLASSIFY
      new_level: WARNING
      extra_fields:
        tag: test
"""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(config_content)
    
    settings = Settings.load(config_file)
    
    assert len(settings.logging.patterns) == 3
    
    p1 = settings.logging.patterns[0]
    assert p1.pattern == "suppress me"
    assert p1.action == "SUPPRESS"
    
    p2 = settings.logging.patterns[1]
    assert p2.pattern == "allow me"
    assert p2.action == "ALLOW"
    
    p3 = settings.logging.patterns[2]
    assert p3.pattern == "reclassify me"
    assert p3.action == "RECLASSIFY"
    assert p3.new_level == "WARNING"
    assert p3.extra_fields == {"tag": "test"}

def test_orchestrator_initialization_with_logging_config(tmp_path):
    config_content = """
logging:
  patterns:
    - pattern: "test pattern"
      action: SUPPRESS
"""
    config_file = tmp_path / "test_config.yaml"
    config_file.write_text(config_content)
    
    settings = Settings.load(config_file)
    
    # Initialize orchestrator (this triggers configure_logging)
    # We just want to make sure it doesn't crash
    orchestrator = Orchestrator(settings)
    assert orchestrator.settings.logging.patterns[0].pattern == "test pattern"
